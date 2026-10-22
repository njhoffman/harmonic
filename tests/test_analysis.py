import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import wave

import numpy as np
import pyarrow.ipc as ipc

from harmonic_analysis.analysis import BAND_COUNT, HOP_SIZE, SAMPLE_RATE, WINDOW_SIZE, analyze, extract_features


class AnalysisTests(unittest.TestCase):
    def test_silence_is_finite_and_zero(self):
        features = extract_features(np.zeros((SAMPLE_RATE, 2), dtype=np.float32))
        self.assertEqual(len(features["rms"]), 50)
        np.testing.assert_array_equal(features["sample_index"], np.arange(50) * HOP_SIZE)
        for key in ("rms", "peak", "onset", "spectrum"):
            self.assertTrue(np.isfinite(features[key]).all())
            self.assertEqual(float(features[key].max()), 0)

    def test_tone_frequency_rms_and_antiphase_stereo(self):
        frequency = 440
        mono = 0.5 * np.sin(2 * np.pi * frequency * np.arange(SAMPLE_RATE) / SAMPLE_RATE)
        features = extract_features(np.column_stack([mono, -mono]).astype(np.float32))
        self.assertAlmostEqual(float(np.median(features["rms"][3:-3])), 0.5 / np.sqrt(2), places=3)
        energy = np.mean(features["spectrum"][3:-3] ** 2, axis=0)
        edges = features["band_edges_hz"]
        dominant = int(np.argmax(energy))
        # A sinusoid's strongest FFT bin is quantized to the window resolution;
        # a log-band boundary can lie between the actual tone and that bin.
        half_bin = SAMPLE_RATE / WINDOW_SIZE / 2
        self.assertLessEqual(edges[dominant], frequency + half_bin)
        self.assertGreaterEqual(edges[dominant + 1], frequency - half_bin)
        self.assertGreater(float(energy.sum()), 0.12)

    def test_impulse_is_centered_on_original_timeline(self):
        audio = np.zeros((SAMPLE_RATE, 2), dtype=np.float32)
        audio[SAMPLE_RATE // 2] = 1
        features = extract_features(audio)
        strongest = int(np.argmax(np.sum(features["spectrum"] ** 2, axis=1)))
        self.assertEqual(int(features["sample_index"][strongest]), SAMPLE_RATE // 2)

    def test_short_audio_has_a_frame_and_invalid_input_is_rejected(self):
        self.assertEqual(extract_features(np.zeros((1, 2), dtype=np.float32))["spectrum"].shape, (1, BAND_COUNT))
        with self.assertRaises(ValueError):
            extract_features(np.zeros((0, 2)))
        with self.assertRaises(ValueError):
            extract_features(np.full((4, 2), np.nan))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
    def test_complete_bundle_preserves_duration_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tone with spaces.wav"
            # A different source rate exercises the shared canonical timebase.
            rate = 44100
            tone = (12000 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)).astype("<i2")
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(rate)
                handle.writeframes(tone.tobytes())
            with contextlib.redirect_stdout(io.StringIO()):
                result = analyze(source, root / "bundle")
            manifest = json.loads(result.read_text())
            self.assertEqual(manifest["audio"]["sample_count"], SAMPLE_RATE)
            self.assertEqual(len(manifest["source"]["sha256"]), 64)
            with ipc.open_file(str(result.parent / "mix.arrow")) as reader:
                table = reader.read_all()
            self.assertEqual(table.num_rows, 50)
            self.assertEqual(table["spectrum"].type.list_size, BAND_COUNT)
            with self.assertRaisesRegex(ValueError, "already exists"):
                analyze(source, root / "bundle")


if __name__ == "__main__":
    unittest.main()
