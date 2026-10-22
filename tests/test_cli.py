import os
from pathlib import Path
import subprocess
import sys
import unittest

from harmonic_analysis import __version__

PLAYER = Path(os.environ.get("HARMONIC_PLAYER", "build/harmonic-player")).resolve()


class CommandLineTests(unittest.TestCase):
    def information(self, command, *arguments):
        result = subprocess.run([*command, *arguments], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def check_help(self, command):
        help_text = self.information(command, "--help")
        self.assertIn("--help", help_text)
        self.assertIn("--version", help_text)
        self.assertEqual(self.information(command, "-h"), help_text)
        # Help must not try to open a recording/bundle passed before the flag.
        self.assertEqual(self.information(command, "missing-input", "-h"), help_text)

    def check_version(self, command):
        version = self.information(command, "--version")
        self.assertEqual(version.split()[-1], __version__)
        self.assertEqual(self.information(command, "-v"), version)
        self.assertEqual(self.information(command, "missing-input", "-v"), version)

    def test_analyzer_help_needs_no_input(self):
        self.check_help([sys.executable, "-m", "harmonic_analysis"])

    def test_analyzer_version_needs_no_input(self):
        self.check_version([sys.executable, "-m", "harmonic_analysis"])

    @unittest.skipUnless(PLAYER.is_file(), "Build the native player to check its CLI")
    def test_player_help_needs_no_input(self):
        self.check_help([str(PLAYER)])

    @unittest.skipUnless(PLAYER.is_file(), "Build the native player to check its CLI")
    def test_player_version_needs_no_input(self):
        self.check_version([str(PLAYER)])


if __name__ == "__main__":
    unittest.main()
