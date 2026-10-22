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
PLAYER = Path(os.environ.get("HARMONIC_PLAYER", "build/harmonic-player")).resolve()
PLAYBACK = (PLAYER.is_file() and "projectM playback: enabled" in
            subprocess.run([str(PLAYER), "--help"], capture_output=True, text=True, timeout=10).stdout)


class AudioBundleFixture(unittest.TestCase):
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


@unittest.skipUnless(CHECKER.is_file() and shutil.which("ffmpeg"), "Build the optional projectM checker to run these checks")
class ProjectMIntegrationTests(AudioBundleFixture):
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


@unittest.skipUnless(PLAYBACK and shutil.which("ffmpeg"), "Build the player with optional projectM playback for these checks")
class CompositorIntegrationTests(AudioBundleFixture):
    def invoke(self, *arguments, interactive=False):
        environment = dict(os.environ, SDL_AUDIODRIVER="dummy")
        if interactive:
            environment["SDL_VIDEODRIVER"] = "offscreen"
        return subprocess.run([str(PLAYER), str(self.manifest), *map(str, arguments)],
                              env=environment, text=True, capture_output=True, timeout=45)

    @staticmethod
    def pixels(path):
        with path.open("rb") as image:
            assert image.readline() == b"P6\n"
            width, height = map(int, image.readline().split())
            assert image.readline() == b"255\n"
            return np.frombuffer(image.read(), dtype=np.uint8).reshape(height, width, 3)

    def test_compositor_pause_clock_seeks_resize_and_output_preservation(self):
        output = self.root / "compositor"
        result = self.invoke("--preset", PRESET, "--start", "0.3", "--compositor-check", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        report_path = output / "report.json"
        original = report_path.read_bytes()
        report = json.loads(original)
        for check in ("graph_state_restored", "paused_frame_stable", "sample_clock_advanced",
                      "forward_and_backward_seek_reset", "end_frame_stable", "resize_passed"):
            self.assertTrue(report[check], check)
        self.assertEqual(report["source_pcm_sha256"], json.loads(self.manifest.read_text())["source"]["pcm_sha256"])
        combined, preset, graphs = (self.pixels(output / name) for name in ("combined.ppm", "preset.ppm", "graphs.ppm"))
        self.assertEqual(combined.shape, (720, 960, 3))
        # Check the visualization area, excluding headings where view labels differ.
        area = np.s_[154:424, 100:860]
        self.assertGreater(np.mean(np.any(combined[area] != graphs[area], axis=2)), 0.1)
        self.assertGreater(np.mean(np.any(combined[area] != preset[area], axis=2)), 0.1)
        repeated = self.invoke("--preset", PRESET, "--compositor-check", output)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertEqual(report_path.read_bytes(), original)

    def test_real_playback_path_with_dummy_audio(self):
        result = self.invoke("--preset", PRESET, "--start", "0.3", "--exit-after", "0.15", interactive=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decoded PCM checksums match", result.stdout)

    def test_invalid_preset_and_incompatible_modes_do_not_render(self):
        invalid = self.root / "invalid.milk"
        invalid.write_text("not a preset\n")
        output = self.root / "invalid.ppm"
        result = self.invoke("--preset", invalid, "--render-check", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        result = self.invoke("--view", "preset", "--render-check", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        result = self.invoke("--preset", PRESET, "--audio-check")
        self.assertNotEqual(result.returncode, 0)

    def test_graph_view_preserves_feature_offset_and_final_frame_time(self):
        frames, start = 3, 0.3
        expected = self.root / "expected.ppm"
        actual = self.root / "actual.ppm"
        result = self.invoke("--start", repr(start + (frames - 1) / 60), "--offset-ms", "20", "--render-check", expected)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke("--preset", PRESET, "--view", "graphs", "--start", repr(start),
                             "--offset-ms", "20", "--render-frames", str(frames), "--render-check", actual)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(actual.read_bytes(), expected.read_bytes())


if __name__ == "__main__":
    unittest.main()
