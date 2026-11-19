import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from harmonic_analysis.analysis import analyze, decode_audio, sha256_file
from harmonic_analysis.bundle import read_bundle
from harmonic_analysis.catalog import import_track
from harmonic_analysis.sam_jobs import load_job, save_job, save_pair, write_json
from harmonic_analysis.source_features import build_source_bundle

PLAYER = Path(os.environ.get("HARMONIC_PLAYER", "build/harmonic-player")).resolve()


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
class SourceFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root / "source.wav"
        signal = (13000 * np.sin(2 * np.pi * 440 * np.arange(96000) / 48000)).astype("<i2")
        with wave.open(str(self.audio), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(np.column_stack((signal, signal)).tobytes())
        self.mix = analyze(self.audio, self.root / "mix")
        m = json.loads(self.mix.read_text())
        samples = decode_audio(self.audio)
        self.start, self.count = 12345, 24000  # Intentionally not aligned to the mix hop.
        self.job = save_job(samples[self.start:self.start + self.count], self.root / "job",
                            source={**m["source"], "sample_count": len(samples)},
                            start_sample=self.start, targets={"drums": "drums playing"})
        job, excerpt = load_job(self.job)
        self.result = self.root / "result"
        self.result.mkdir()
        target = np.zeros(self.count, dtype=np.float32)
        target[4800], target[10000] = 2, -1.5
        pair = save_pair(self.result, "drums", target, excerpt.mean(axis=1) * 0.25,
                         excerpt.mean(axis=1), padding_limit=1)
        report = {k: job[k] for k in ("source", "start_sample", "sample_count", "settings", "seed",
                                      "semantics", "channel_reduction", "anchors", "model")}
        report["model"]["files_sha256"] = {k: "c" * 64 for k in ("config.json", "checkpoint.pt", "LICENSE")}
        report.update(schema_version=1, kind="harmonic.sam-audio-result.v1", sample_rate=48000, channels=1,
                      codec_hop_samples=1920, job_sha256=sha256_file(self.job),
                      worker_code_sha256="d" * 64, worker_lock_sha256="e" * 64,
                      auxiliary_text_model={"id": "google-t5/t5-base", "revision": "f" * 40},
                      pairs={"drums": {**pair, "description": "drums playing"}})
        write_json(self.result / "report.json", report)
        self.output = build_source_bundle(self.mix, self.job, self.result, self.root / "sources")
        self.manifest = json.loads(self.output.read_text())

    def native(self, *args):
        return subprocess.run([str(PLAYER), str(self.output), *args], text=True, capture_output=True,
                              env=dict(os.environ, SDL_AUDIODRIVER="dummy"), timeout=25)

    def test_offset_impulse_gain_and_portability_without_separated_audio(self):
        manifest = read_bundle(self.output, sha256_file(self.audio))
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(sha256_file(self.mix.parent / "mix.arrow"), sha256_file(self.output.parent / "mix.arrow"))
        stream = manifest["streams"][1]
        with ipc.open_file(str(self.output.parent / stream["artifact"])) as handle:
            table = handle.read_all()
        centers = table["sample_index"].to_numpy()
        np.testing.assert_array_equal(centers, self.start + np.arange(25) * 960)
        # An isolated 2.0 impulse in a 4096-sample mono window: no stereo downmix loss or rescaling.
        self.assertEqual(table["peak"][5].as_py(), 2.0)
        self.assertAlmostEqual(table["rms"][5].as_py(), 2 / np.sqrt(4096), places=8)
        self.assertEqual(stream["channels"], 1)
        self.assertEqual(stream["stats"]["peak"]["max"], 2.0)
        self.assertFalse(list(self.output.parent.glob("*.wav")))
        shutil.rmtree(self.job.parent)
        shutil.rmtree(self.result)
        moved = self.root / "moved"
        shutil.move(self.output.parent, moved)
        read_bundle(moved / "manifest.json", sha256_file(self.audio))

    def test_mutated_coverage_paths_indices_and_report_are_rejected(self):
        stream = self.manifest["streams"][1]
        for key, value in (("start_sample", self.start + 1), ("sample_count", self.count + 1),
                           ("artifact", "../outside.arrow"), ("channels", 2)):
            changed = json.loads(json.dumps(self.manifest))
            changed["streams"][1][key] = value
            write_json(self.output, changed)
            with self.assertRaises(ValueError):
                read_bundle(self.output, sha256_file(self.audio))
            if PLAYER.is_file():
                self.assertNotEqual(self.native("--inspect").returncode, 0)
        changed = json.loads(json.dumps(self.manifest))
        changed["analysis"]["band_edges_hz"][1] += 0.001
        write_json(self.output, changed)
        with self.assertRaisesRegex(ValueError, "frequency bands"):
            read_bundle(self.output, sha256_file(self.audio))
        if PLAYER.is_file():
            self.assertIn("frequency bands", self.native("--inspect").stderr)
        write_json(self.output, self.manifest)
        artifact = self.output.parent / stream["artifact"]
        with ipc.open_file(str(artifact)) as reader:
            table = reader.read_all()
        # Updating the file hash cannot disguise an off-by-one sample timeline.
        table = table.set_column(0, table.schema.field(0), pa.array(table["sample_index"].to_numpy() + 1))
        with pa.OSFile(str(artifact), "wb") as handle:
            with ipc.new_file(handle, table.schema) as writer:
                writer.write_table(table)
        self.manifest["streams"][1]["sha256"] = sha256_file(artifact)
        write_json(self.output, self.manifest)
        with self.assertRaisesRegex(ValueError, "sample indices"):
            read_bundle(self.output, sha256_file(self.audio))
        if PLAYER.is_file():
            self.assertIn("sample indices", self.native("--inspect").stderr)

    def test_adapter_refuses_overwrite_wrong_source_and_mix_catalog_reuse(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            build_source_bundle(self.mix, self.job, self.result, self.output.parent)
        report = self.result / "report.json"
        report.write_bytes(report.read_bytes() + b"\n")
        # The retained report is checksum protected even after WAVs have been discarded.
        saved = self.output.parent / "sam-report.json"
        saved.write_bytes(saved.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "report checksum"):
            read_bundle(self.output, sha256_file(self.audio))
        shutil.copyfile(report, saved)
        self.manifest["separation"]["sha256"] = sha256_file(saved)
        write_json(self.output, self.manifest)
        with self.assertRaisesRegex(ValueError, "mix catalog cache"):
            import_track(self.audio, self.root / "catalog.sqlite3", bundle=self.output)
        m = json.loads(self.mix.read_text())
        m["source"]["pcm_sha256"] = "0" * 64
        write_json(self.mix, m)
        destination = self.root / "refused"
        with self.assertRaisesRegex(ValueError, "different source"):
            build_source_bundle(self.mix, self.job, self.result, destination)
        self.assertFalse(destination.exists())

    @unittest.skipUnless(PLAYER.is_file(), "Build the native player")
    def test_native_coverage_interpolation_and_original_audio_transport(self):
        for sample, covered in ((self.start - 1, False), (self.start, True),
                                (self.start + 4800, True), (self.start + self.count - 1, True),
                                (self.start + self.count, False)):
            result = self.native("--inspect", "--start", str(sample / 48000))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(next(s for s in result.stdout.splitlines() if s.startswith("{")))
            item = data["source_features"][0]
            self.assertEqual(item["covered"], covered)
            if sample == self.start + 4800:
                self.assertAlmostEqual(item["rms"], 2 / np.sqrt(4096), places=8)
                self.assertEqual(item["peak"], 2)
            if not covered:
                self.assertNotIn("rms", item)  # Missing coverage is not a zero measurement.
        check = self.native("--audio-check")
        self.assertEqual(check.returncode, 0, check.stderr)
        artifact = self.output.parent / self.manifest["streams"][2]["artifact"]
        with artifact.open("ab") as handle:
            handle.write(b"corrupt")
        self.assertIn("feature checksum mismatch", self.native("--inspect").stderr)
