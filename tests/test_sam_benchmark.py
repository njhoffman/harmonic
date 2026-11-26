import hashlib
import json
import shutil
import subprocess
import sys
import wave
import tempfile
import unittest

from support import requires
from pathlib import Path
from unittest.mock import patch

import numpy as np

from harmonic_analysis.sam_benchmark import prepare_cases, score_case
from harmonic_analysis.sam_jobs import digest, load_job, save_pair, write_json


def fake_file_hash(path):
    """Most tests mock decoding with placeholder paths; hash the path instead."""
    return hashlib.sha256(str(path).encode()).hexdigest()


def setUpModule():
    patcher = patch("harmonic_analysis.sam_benchmark.sha256_file", side_effect=fake_file_hash)
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


class VocalBenchmarkTests(unittest.TestCase):
    def test_prepared_cases_score_dropout_bleed_and_false_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples = np.arange(9600) % 4
            vocal = np.repeat(np.where(samples % 2 == 0, 0.25, -0.25)[:, None], 2, axis=1).astype("<f4")
            backing = np.repeat(np.where(samples < 2, 0.125, -0.125)[:, None], 2, axis=1).astype("<f4")
            with patch("harmonic_analysis.sam_benchmark.decode_audio", side_effect=[vocal, backing]):
                jobs = prepare_cases(Path("vocal.wav"), Path("backing.wav"), root / "jobs",
                                     start=0, duration=0.2)

            def result(case, target, residual):
                path = jobs / case / "job.json"
                job, pcm = load_job(path)
                output = root / case
                output.mkdir()
                pair = save_pair(output, "vocals", target, residual, pcm.mean(axis=1), padding_limit=0)
                pair["description"] = job["targets"]["vocals"]
                report = {**job, "kind": "harmonic.sam-audio-result.v1", "channels": 1,
                          "job_sha256": digest(path), "codec_hop_samples": 1, "pairs": {"vocals": pair}}
                write_json(output / "report.json", report)
                return path, output

            voice, instruments = vocal[:, 0], backing[:, 0]
            target = voice.copy()
            target[4800:] = 0
            target += 0.25 * instruments
            path, output = result("mix", target, voice + instruments - target)
            with patch("harmonic_analysis.sam_benchmark.decode_audio", side_effect=[vocal, backing]):
                mixed = score_case(path, output, "mix", vocal=Path("vocal.wav"), accompaniment=Path("backing.wav"))
            self.assertAlmostEqual(mixed["reference_gains"]["accompaniment"]["target"], 0.25)
            for window, expected_gain in zip(mixed["vocal_windows"], (1, 0), strict=True):
                self.assertAlmostEqual(window["vocal_gain"]["target"], expected_gain)
                self.assertAlmostEqual(window["vocal_gain"]["residual"], 1 - expected_gain)
            with patch("harmonic_analysis.sam_benchmark.decode_audio", side_effect=[vocal, -backing]):
                with self.assertRaisesRegex(ValueError, "reproduce the job PCM"):
                    score_case(path, output, "mix", vocal=Path("vocal.wav"), accompaniment=Path("backing.wav"))
            # Stems other than the recorded ones are refused before decoding.
            with patch("harmonic_analysis.sam_benchmark.decode_audio") as decode:
                with self.assertRaisesRegex(ValueError, "does not match the stem recorded"):
                    score_case(path, output, "mix", vocal=Path("other.wav"), accompaniment=Path("backing.wav"))
                decode.assert_not_called()
            stems = load_job(path)[0]["source"]["stems"]
            self.assertEqual(stems["vocal"], {"path": str(Path("vocal.wav").resolve()),
                                              "sha256": fake_file_hash(Path("vocal.wav")),
                                              "pcm_sha256": hashlib.sha256(vocal.tobytes()).hexdigest()})
            self.assertEqual(mixed["reference_stems"], stems)
            self.assertEqual(mixed["source"]["stems"], stems)

            path, output = result("vocal-only", voice, np.zeros_like(voice))
            self.assertEqual(score_case(path, output, "vocal-only")["target_error_rms"], 0)
            path, output = result("accompaniment-only", 0.5 * instruments, 0.5 * instruments)
            absent = score_case(path, output, "accompaniment-only")
            self.assertEqual(absent["target_over_input_rms"], 0.5)
            self.assertFalse(absent["absence_check"]["pass"])
            self.assertTrue(score_case(path, output, "accompaniment-only", absent_limit=0.5)["absence_check"]["pass"])


class CenteredScoringTests(unittest.TestCase):
    """Constant offsets must not decide benchmark outcomes."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        samples = np.arange(9600) % 4
        self.voice = np.where(samples % 2 == 0, 0.25, -0.25).astype("<f4")
        self.guitar = np.where(samples < 2, 0.125, -0.125).astype("<f4")

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, vocal, backing):
        stereo = [np.repeat(np.asarray(stem, "<f4")[:, None], 2, axis=1) for stem in (vocal, backing)]
        with patch("harmonic_analysis.sam_benchmark.decode_audio", side_effect=stereo):
            self.jobs = prepare_cases(Path("vocal.wav"), Path("backing.wav"), self.root / "jobs",
                                      start=0, duration=0.2)
        self.stems = stereo

    def result(self, case, target, residual):
        path = self.jobs / case / "job.json"
        job, pcm = load_job(path)
        output = self.root / case
        shutil.rmtree(output, ignore_errors=True)
        output.mkdir()
        pair = save_pair(output, "vocals", np.asarray(target, "<f4"), np.asarray(residual, "<f4"),
                         pcm.mean(axis=1), padding_limit=0)
        pair["description"] = job["targets"]["vocals"]
        write_json(output / "report.json", {**job, "kind": "harmonic.sam-audio-result.v1", "channels": 1,
                                            "job_sha256": digest(path), "codec_hop_samples": 1,
                                            "pairs": {"vocals": pair}})
        return path, output

    def score(self, case, target, residual, **options):
        path, output = self.result(case, target, residual)
        if case == "mix":
            with patch("harmonic_analysis.sam_benchmark.decode_audio", side_effect=list(self.stems)):
                return score_case(path, output, case, vocal=Path("vocal.wav"),
                                  accompaniment=Path("backing.wav"), **options)
        return score_case(path, output, case, **options)

    def test_large_input_offset_cannot_hide_false_extraction(self):
        offset = np.float32(-3.0)
        self.prepare(self.voice, self.guitar + offset)
        guitar = self.guitar.astype(np.float64)
        report = self.score("accompaniment-only", 0.96 * guitar, 0.04 * guitar + offset)
        self.assertEqual(report["kind"], "harmonic.sam-vocal-benchmark.v2")
        self.assertEqual(report["centering"], "excerpt_mean")
        self.assertLess(report["raw"]["target_over_input_rms"], 0.05)
        self.assertAlmostEqual(report["target_over_input_rms"], 0.96, places=5)
        self.assertFalse(report["absence_check"]["pass"])
        self.assertAlmostEqual(report["means"]["input"], -3.0, places=5)
        self.assertAlmostEqual(report["means"]["residual"], -3.0, places=5)
        self.assertAlmostEqual(report["means"]["references"]["accompaniment"], -3.0, places=5)
        self.assertAlmostEqual(report["reference_gains"]["accompaniment"]["target"], 0.96, places=5)

    def test_offset_moved_into_target_is_not_scored_as_vocal(self):
        offset = np.float32(-0.2)
        self.prepare(self.voice + offset, self.guitar)
        report = self.score("vocal-only", np.full(9600, offset), self.voice)
        self.assertGreater(report["raw"]["target_over_input_rms"], 0.6)
        self.assertAlmostEqual(report["target_over_input_rms"], 0, places=6)
        self.assertAlmostEqual(report["reference_gains"]["vocal"]["target"], 0, places=6)
        self.assertAlmostEqual(report["reference_gains"]["vocal"]["residual"], 1, places=6)
        self.assertTrue(report["vocal_windows"])
        for window in report["vocal_windows"]:
            self.assertAlmostEqual(window["vocal_gain"]["residual"], 1, places=5)

    def test_mixed_gains_ignore_stem_offsets_and_keep_sample_positions(self):
        self.prepare(self.voice - 0.036, self.guitar - 0.099)
        voice, guitar = self.voice.astype(np.float64), self.guitar.astype(np.float64)
        report = self.score("mix", voice + 0.25 * guitar, 0.75 * guitar - 0.135)
        self.assertAlmostEqual(report["reference_gains"]["vocal"]["target"], 1, places=5)
        self.assertAlmostEqual(report["reference_gains"]["accompaniment"]["target"], 0.25, places=5)
        self.assertAlmostEqual(report["reference_gains"]["accompaniment"]["residual"], 0.75, places=5)
        self.assertAlmostEqual(report["means"]["references"]["vocal"], -0.036, places=5)
        self.assertNotAlmostEqual(report["raw"]["residual_error_rms"], report["residual_error_rms"], places=3)
        self.assertEqual([window["start_sample"] for window in report["vocal_windows"]], [0, 4800])

    def test_scoring_refuses_waves_replaced_after_validation(self):
        self.prepare(self.voice, self.guitar)
        path, output = self.result("vocal-only", self.voice, np.zeros(9600))
        from harmonic_analysis import sam_benchmark
        original = sam_benchmark.validate_result

        def validate_then_replace(*args):
            report = original(*args)
            wave = output / "vocals-target.wav"
            data = bytearray(wave.read_bytes())
            data[-4:] = np.float32(0.5).tobytes()
            wave.write_bytes(bytes(data))
            return report
        with patch.object(sam_benchmark, "validate_result", side_effect=validate_then_replace):
            with self.assertRaisesRegex(ValueError, "vocals-target.wav changed after validation"):
                score_case(path, output, "vocal-only")

    def test_preparation_rejects_misaligned_or_short_stems_and_bad_windows(self):
        stems = [np.zeros((9600, 2), "<f4"), np.zeros((9599, 2), "<f4")]
        with patch("harmonic_analysis.sam_benchmark.decode_audio", side_effect=stems):
            with self.assertRaisesRegex(ValueError, "equal decoded lengths"):
                prepare_cases(Path("v.wav"), Path("a.wav"), self.root / "unequal", start=0, duration=0.1)
        for start, duration, message in ((0.15, 0.1, "beyond the reference stems"), (-1, 0.1, "nonnegative"),
                                         (0, 31, "up to 30 seconds"), (0, float("nan"), "up to 30 seconds")):
            stems = [np.zeros((9600, 2), "<f4")] * 2
            with patch("harmonic_analysis.sam_benchmark.decode_audio", side_effect=stems):
                with self.assertRaisesRegex(ValueError, message):
                    prepare_cases(Path("v.wav"), Path("a.wav"), self.root / "window", start=start, duration=duration)
        self.assertFalse((self.root / "unequal").exists() or (self.root / "window").exists())

    def test_jobs_without_stem_provenance_still_score(self):
        backing = np.where(np.arange(9600) % 4 < 2, 0.125, -0.125).astype("<f4")
        self.prepare(self.voice, backing)
        for case in ("mix", "vocal-only"):
            job_path = self.jobs / case / "job.json"
            job = json.loads(job_path.read_text())
            del job["source"]["stems"]
            write_json(job_path, job)
        report = self.score("mix", self.voice, backing)
        self.assertNotIn("stems", report["source"])
        self.assertIsNotNone(report["reference_stems"])

    def test_argument_checks_and_collinear_references(self):
        self.prepare(self.voice, self.voice)
        path, output = self.result("vocal-only", self.voice, np.zeros(9600))
        for case, options, message in (("bogus", {}, "Invalid benchmark case"),
                                       ("vocal-only", {"absent_limit": 1.5}, "absent-target limit"),
                                       ("vocal-only", {"vocal": Path("v.wav")}, "apply to mixed cases")):
            with self.assertRaisesRegex(ValueError, message):
                score_case(path, output, case, **options)
        path, output = self.result("mix", 2 * self.voice, np.zeros(9600))
        with self.assertRaisesRegex(ValueError, "Both reference stems"):
            score_case(path, output, "mix", vocal=Path("v.wav"))
        # Identical vocal and accompaniment references cannot be told apart: gains are null.
        report = self.score("mix", 2 * self.voice, np.zeros(9600))
        self.assertEqual(report["reference_gains"], {"vocal": None, "accompaniment": None})
        self.assertTrue(all(window["vocal_gain"] is None for window in report["vocal_windows"]))

    @requires(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_prepare_and_score_through_the_command_line(self):
        rate = 48000
        t = np.arange(rate) / rate
        for name, signal in (("vocal", 0.25 * np.sin(2 * np.pi * 440 * t)), ("backing", 0.125 * np.sin(2 * np.pi * 110 * t))):
            with wave.open(str(self.root / f"{name}.wav"), "wb") as handle:
                handle.setnchannels(2); handle.setsampwidth(2); handle.setframerate(rate)
                pcm = np.round(np.repeat(signal[:, None], 2, axis=1) * 32767).astype("<i2")
                handle.writeframes(pcm.tobytes())
        cli = [sys.executable, "-m", "harmonic_analysis.sam_cli"]
        jobs = self.root / "cli-jobs"
        prepared = subprocess.run([*cli, "prepare-vocal-benchmark", self.root / "vocal.wav", self.root / "backing.wav",
                                   "--output", jobs, "--duration", "0.5", "--start", "0.25"],
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.jobs = jobs
        job, pcm = load_job(jobs / "vocal-only" / "job.json")
        self.assertEqual((job["start_sample"], len(pcm)), (12000, 24000))
        path, output = self.result("vocal-only", pcm.mean(axis=1), np.zeros(len(pcm)))
        scored = subprocess.run([*cli, "benchmark-vocals", path, output, "--case", "vocal-only"],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(scored.returncode, 0, scored.stderr)
        report = json.loads(scored.stdout)
        self.assertEqual(report["kind"], "harmonic.sam-vocal-benchmark.v2")
        self.assertAlmostEqual(report["reference_gains"]["vocal"]["target"], 1, places=5)
        self.assertIsNone(report["reference_stems"])
        # The subprocess hashes the real stem files.
        stems = job["source"]["stems"]
        for role, name in (("vocal", "vocal.wav"), ("accompaniment", "backing.wav")):
            self.assertEqual(stems[role]["path"], str((self.root / name).resolve()))
            self.assertEqual(stems[role]["sha256"], hashlib.sha256((self.root / name).read_bytes()).hexdigest())
            self.assertRegex(stems[role]["pcm_sha256"], "^[0-9a-f]{64}$")
        missing = subprocess.run([*cli, "benchmark-vocals", path, output, "--case", "mix"],
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("Both reference stems", missing.stderr)
        self.assertNotIn("Traceback", missing.stderr)

    def test_constant_and_silent_references_are_rejected(self):
        self.prepare(np.full(9600, 0.1), self.guitar)
        with self.assertRaisesRegex(ValueError, "vocal reference is only a constant offset"):
            self.score("vocal-only", np.zeros(9600), np.full(9600, 0.1))
        with self.assertRaisesRegex(ValueError, "vocal reference is only a constant offset"):
            self.score("mix", np.zeros(9600), self.guitar + 0.1)
        shutil.rmtree(self.jobs)
        self.prepare(np.zeros(9600), self.guitar)
        with self.assertRaisesRegex(ValueError, "audible-channel signal"):
            self.score("vocal-only", np.zeros(9600), np.zeros(9600))
