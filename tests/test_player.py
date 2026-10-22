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

PLAYER = Path(os.environ.get("HARMONIC_PLAYER", "build/harmonic-player")).resolve()


@unittest.skipUnless(PLAYER.is_file() and shutil.which("ffmpeg"), "Build the native player to run integration checks")
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

    def invoke(self, *arguments):
        environment = dict(os.environ, SDL_AUDIODRIVER="dummy")
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


if __name__ == "__main__":
    unittest.main()
