import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from support import requires
import wave

import numpy as np

from harmonic_analysis.analysis import analyze, sha256_file

PLAYER = Path(os.environ.get("HARMONIC_PLAYER", "build/harmonic-player")).resolve()


@requires(PLAYER.is_file() and shutil.which("ffmpeg"), "Build the native player to run integration checks")
class NativeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audio = self.root / "source with spaces.wav"
        rate = 44100
        tone = (12000 * np.sin(2 * np.pi * 440 * np.arange(2 * rate) / rate)).astype("<i2")
        with wave.open(str(self.audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(tone.tobytes())
        with contextlib.redirect_stdout(io.StringIO()):
            self.manifest_path = analyze(self.audio, self.root / "bundle")

    def invoke(self, *arguments, interactive=False):
        environment = dict(os.environ, SDL_AUDIODRIVER="dummy")
        if interactive:
            environment["SDL_VIDEODRIVER"] = "offscreen"
        return subprocess.run([str(PLAYER), str(self.manifest_path), *arguments],
                              text=True, capture_output=True, env=environment, timeout=20)

    def test_native_decoder_matches_resampled_analysis_and_transport(self):
        inspect = self.invoke("--inspect")
        self.assertEqual(inspect.returncode, 0, inspect.stderr)
        self.assertIn("decoded PCM checksums match", inspect.stdout)
        playback = self.invoke("--audio-check")
        self.assertEqual(playback.returncode, 0, playback.stderr)
        self.assertIn("Audio clock check passed", playback.stdout)

    def test_changed_recording_and_corrupt_features_are_rejected(self):
        manifest = json.loads(self.manifest_path.read_text())
        manifest["source"]["sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest))
        result = self.invoke("--inspect")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("audio checksum mismatch", result.stderr)
        manifest["source"]["sha256"] = sha256_file(self.audio)
        self.manifest_path.write_text(json.dumps(manifest))
        with (self.manifest_path.parent / "mix.arrow").open("ab") as handle:
            handle.write(b"corruption")
        result = self.invoke("--inspect")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("feature checksum mismatch", result.stderr)

    def test_inconsistent_timebase_is_rejected(self):
        manifest = json.loads(self.manifest_path.read_text())
        manifest["analysis"]["hop_size"] = 1
        self.manifest_path.write_text(json.dumps(manifest))
        result = self.invoke("--inspect")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frame count does not match", result.stderr)

    def test_frame_report_records_frames_and_scripted_seeks(self):
        report_path = self.root / "frames.json"
        result = self.invoke("--size", "960x720", "--exit-after", "0.8", "--seek-every", "0.3",
                             "--frame-report", str(report_path), interactive=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["kind"], "harmonic.frame-report.v1")
        self.assertEqual(report["view"], "graphs")
        self.assertIsNone(report["preset"])
        self.assertEqual(report["display"]["pixel_width"], 960)
        self.assertEqual(report["audio"]["sample_rate"], 48000)
        count = report["frame_count"]
        self.assertGreater(count, 2)
        frames = report["frames"]
        for column in ("begin_ns", "draw_ns", "swap_ns", "gpu_ns", "position", "queued_frames"):
            self.assertEqual(len(frames[column]), count, column)
        for begin, drawn, swapped in zip(frames["begin_ns"], frames["draw_ns"], frames["swap_ns"]):
            self.assertLessEqual(begin, drawn)
            self.assertLessEqual(drawn, swapped)
        self.assertEqual(frames["swap_ns"], sorted(frames["swap_ns"]))
        # The start-up seek plus two scripted seeks at 0.3 s and 0.6 s.
        seeks = report["seeks"]
        self.assertEqual(len(seeks), 3)
        self.assertEqual(seeks[0]["frame"], 0)
        for seek in seeks:
            self.assertGreaterEqual(seek["call_ns"], 0)
            self.assertGreaterEqual(seek["to"], 0)
        self.assertFalse(report_path.with_name("frames.json.tmp").exists())

    def test_frame_report_options_are_validated(self):
        report = str(self.root / "frames.json")
        cases = [
            (("--frame-report", report), "requires --exit-after"),
            (("--exit-after", "1", "--seek-every", "1"), "requires --frame-report"),
            (("--frame-report", report, "--exit-after", "1", "--seek-every", "-1"), "nonnegative"),
            (("--size", "1920"), "WxH"),
            (("--size", "100x720"), "320..7680"),
            (("--size", "1920x1080x2"), "WxH"),
            (("--size", "+920x720"), "WxH"),
            (("--fullscreen", "--inspect"), "interactive playback only"),
            (("--frame-report", report, "--exit-after", "1", "--audio-check"), "interactive playback only"),
        ]
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
        self.assertFalse(Path(report).exists())


if __name__ == "__main__":
    unittest.main()
