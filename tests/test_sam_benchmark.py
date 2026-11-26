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
