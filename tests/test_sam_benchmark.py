import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from harmonic_analysis.sam_benchmark import prepare_cases, score_case
from harmonic_analysis.sam_jobs import digest, load_job, save_pair, write_json


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
