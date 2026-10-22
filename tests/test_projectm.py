import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

import numpy as np

from harmonic_analysis.analysis import analyze, sha256_file

CHECKER = Path(os.environ.get("HARMONIC_PROJECTM_CHECK", "build/harmonic-projectm-check")).resolve()
PRESET = Path(__file__).parent / "fixtures" / "diagnostic.milk"


@unittest.skipUnless(CHECKER.is_file() and shutil.which("ffmpeg"), "Build the optional projectM checker to run these checks")
class ProjectMIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "tone.wav"
        rate = 48000
        tone = (12000 * np.sin(2 * np.pi * 110 * np.arange(rate) / rate)).astype("<i2")
        with wave.open(str(source), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(tone.tobytes())
        with contextlib.redirect_stdout(io.StringIO()):
            self.manifest = analyze(source, self.root / "bundle")

    def invoke(self, preset, output):
        return subprocess.run([str(CHECKER), str(self.manifest), "--preset", str(preset),
                               "--output", str(output), "--frames", "8", "--width", "960", "--height", "720"],
                              text=True, capture_output=True, timeout=45)

    def test_real_engine_renders_pcm_and_preserves_output(self):
        output = self.root / "render"
        result = self.invoke(PRESET, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        report_path = output / "report.json"
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes)
        manifest = json.loads(self.manifest.read_text())
        self.assertEqual(report["source"]["pcm_sha256"], manifest["source"]["pcm_sha256"])
        self.assertEqual(report["preset"]["sha256"], sha256_file(PRESET))
        self.assertGreater(report["pcm_frames_fed"], 0)
        self.assertGreater(report["render_ms"]["samples"], 0)
        self.assertTrue(report["gl_renderer"])
        preview = output / "preview.ppm"
        self.assertEqual(report["preview"]["sha256"], sha256_file(preview))
        with preview.open("rb") as image:
            self.assertEqual(image.readline(), b"P6\n")
            self.assertEqual(image.readline(), b"960 720\n")
            self.assertEqual(image.readline(), b"255\n")
            pixels = image.read()
        self.assertEqual(len(pixels), 960 * 720 * 3)
        self.assertGreater(max(pixels), min(pixels))
        repeated = self.invoke(PRESET, output)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("already exists", repeated.stderr)
        self.assertEqual(report_path.read_bytes(), report_bytes)

    def test_invalid_preset_is_rejected_before_rendering(self):
        preset = self.root / "invalid.milk"
        preset.write_text("This is not a MilkDrop preset.\n")
        output = self.root / "failed"
        result = self.invoke(preset, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Preset loading failed", result.stderr)
        self.assertFalse(output.exists())

    def test_library_load_error_does_not_pass_as_idle_visualization(self):
        preset = self.root / "preset.unsupported-extension"
        preset.write_text(PRESET.read_text())
        output = self.root / "failed-load"
        result = self.invoke(preset, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Preset loading failed", result.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
