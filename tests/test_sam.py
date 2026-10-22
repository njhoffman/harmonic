import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

import numpy as np

from harmonic_analysis import __version__
from harmonic_analysis.sam_cli import prepare
from harmonic_analysis.sam_jobs import (DEFAULT_TARGETS, digest, load_job, new_directory, read_wave,
                                        save_job, save_pair, validate_result, write_json)

WORKER = Path(__file__).resolve().parent.parent / "workers" / "sam_audio" / "worker.py"


class SAMWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.samples = np.column_stack([np.linspace(-3, 3, 1000), np.linspace(-1, 1, 1000)]).astype("<f4")
        self.source = {"path": "/test-fixture.wav", "sha256": "a" * 64,
                       "pcm_sha256": "b" * 64, "sample_count": 3000}

    def job(self):
        return save_job(self.samples, self.root / "job", source=self.source,
                        start_sample=50, targets=dict(DEFAULT_TARGETS))

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_real_preparation_preserves_source_timebase_and_moves_without_source(self):
        audio = self.root / "source.wav"
        tone = (12000 * np.sin(2 * np.pi * 440 * np.arange(8000) / 8000)).astype("<i2")
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(tone.tobytes())
        path = prepare(audio, self.root / "prepared", start=0.125, duration=0.25,
                       targets=dict(DEFAULT_TARGETS), seed=2026)
        job, samples = load_job(path)
        self.assertEqual(job["start_sample"], 6000)
        self.assertEqual(job["sample_count"], 12000)
        self.assertEqual(job["source"]["sample_count"], 48000)
        self.assertEqual(job["source"]["sha256"], digest(audio))
        self.assertEqual(samples.shape, (12000, 2))
        # FFmpeg's canonical mono-to-stereo mapping applies -3 dB per channel.
        self.assertAlmostEqual(float(np.sqrt(np.mean(samples**2))), 12000 / 32768 / 2, places=3)
        moved = self.root / "moved"
        shutil.copytree(path.parent, moved)
        shutil.rmtree(path.parent)
        audio.unlink()
        np.testing.assert_array_equal(load_job(moved)[1], samples)

    def test_corrupt_or_incompatible_jobs_are_rejected(self):
        path = self.job()
        initial = json.loads(path.read_text())
        for key, value in (("sample_count", 1), ("sample_rate", 44100), ("seed", -1)):
            changed = dict(initial)
            changed[key] = value
            write_json(path, changed)
            with self.assertRaises(ValueError):
                load_job(path)
        write_json(path, initial)
        artifact = path.parent / "input.npy"
        artifact.write_bytes(artifact.read_bytes() + b"corrupt")
        with self.assertRaisesRegex(ValueError, "input checksum"):
            load_job(path)

    def test_new_job_refuses_overwrite_and_invalid_targets_ranges(self):
        path = self.job()
        checksum = digest(path)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.job()
        self.assertEqual(checksum, digest(path))
        for name in ("../escape", "Vocals", ""):
            with self.assertRaises(ValueError):
                save_job(self.samples, self.root / "bad", source=self.source, start_sample=0, targets={name: "singing"})
        for start, duration in ((-1, 1), (0, 31), (float("nan"), 1), (0, 0)):
            with self.assertRaises(ValueError):
                prepare(self.root / "missing", self.root / "bad", start=start, duration=duration,
                        targets=dict(DEFAULT_TARGETS), seed=1)
        self.assertFalse((self.root / "bad").exists())

    def test_waveforms_keep_mono_gain_and_only_trim_codec_right_padding(self):
        mono = self.samples.mean(axis=1)
        target = np.pad(mono * 0.75, (0, 2))
        residual = np.pad(mono * 0.25, (0, 2))
        pair = save_pair(self.root, "vocals", target, residual, mono, padding_limit=3)
        self.assertEqual(pair["target"]["right_trim_samples"], 2)
        self.assertGreater(pair["target"]["peak"], 1)
        self.assertLess(pair["sum_error_rms"], 1e-7)
        np.testing.assert_array_equal(read_wave(self.root / "vocals-target.wav"), target[:len(mono)])
        if shutil.which("ffprobe"):
            info = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json",
                                   str(self.root / "vocals-target.wav")], capture_output=True, text=True, check=True)
            stream = json.loads(info.stdout)["streams"][0]
            self.assertEqual(stream["codec_name"], "pcm_f32le")
            self.assertEqual(stream["channels"], 1)
            self.assertEqual(stream["sample_rate"], "48000")

    def test_short_nonfinite_or_excess_padding_results_leave_no_published_directory(self):
        mono = self.samples.mean(axis=1)
        cases = (mono[:-1], np.full(len(mono), np.nan), np.pad(mono, (0, 4)))
        for index, target in enumerate(cases):
            output = self.root / f"invalid-{index}"
            with self.assertRaises(ValueError):
                with new_directory(output) as temporary:
                    save_pair(temporary, "vocals", target, mono, mono, padding_limit=3)
            self.assertFalse(output.exists())

    def test_returned_artifacts_match_job_and_reject_corruption_and_timing_changes(self):
        path = self.job()
        job, samples = load_job(path)
        output = self.root / "result"
        output.mkdir()
        mono = samples.mean(axis=1)
        pairs = {}
        for name, description in job["targets"].items():
            pair = save_pair(output, name, mono * 0.5, mono * 0.5, mono, padding_limit=1)
            pairs[name] = {**pair, "description": description}
        report = {key: job[key] for key in ("source", "start_sample", "sample_count", "settings", "seed",
                                           "semantics", "channel_reduction", "anchors", "model")}
        report.update(schema_version=1, kind="harmonic.sam-audio-result.v1", job_sha256=digest(path),
                      sample_rate=48000, channels=1, codec_hop_samples=2, pairs=pairs,
                      test_fixture=True)  # Contract fixtures are not inference results.
        report_path = output / "report.json"
        write_json(report_path, report)
        self.assertEqual(validate_result(path, output)["start_sample"], 50)
        report["start_sample"] += 1
        write_json(report_path, report)
        with self.assertRaisesRegex(ValueError, "start_sample"):
            validate_result(path, output)
        report["start_sample"] -= 1
        write_json(report_path, report)
        artifact = output / "vocals-target.wav"
        artifact.write_bytes(artifact.read_bytes() + b"corrupt")
        with self.assertRaisesRegex(ValueError, "output checksum"):
            validate_result(path, output)

    def test_help_version_and_dependency_free_doctor_do_not_download(self):
        for command in ([sys.executable, "-m", "harmonic_analysis.sam_cli"], [sys.executable, str(WORKER)]):
            for flag in ("-h", "--help", "-v", "--version"):
                result = subprocess.run([*command, flag], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(__version__ if flag in ("-v", "--version") else "--help", result.stdout)
        # -S hides site packages: diagnostics and help must still work before sync.
        environment = {key: value for key, value in os.environ.items() if key not in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")}
        environment["HF_HOME"] = str(self.root / "no-auth")
        environment["HF_TOKEN_PATH"] = str(self.root / "no-token")
        result = subprocess.run([sys.executable, "-S", str(WORKER), "doctor"], env=environment,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ready"])
        self.assertFalse(report["cuda_available"])
        self.assertFalse(report["authenticated"])
        self.assertFalse((self.root / "no-auth").exists())

    def test_unready_worker_fails_before_input_or_weight_download(self):
        output = self.root / "result"
        result = subprocess.run([sys.executable, "-S", str(WORKER), "run", str(self.root / "missing-job"),
                                 "--output", str(output)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not ready", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
