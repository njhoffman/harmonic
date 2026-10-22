import io
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from harmonic_analysis.terminal import Progress

RUNNER = Path(__file__).resolve().parent.parent / "scripts" / "run_status.py"


class CommandStatusTests(unittest.TestCase):
    def run_command(self, code):
        environment = dict(os.environ, NO_COLOR="1", FORCE_COLOR="1")
        return subprocess.run([sys.executable, str(RUNNER), "Test command", sys.executable, "-c", code],
                              env=environment, text=True, capture_output=True, timeout=10)

    def test_success_preserves_output_and_honors_no_color(self):
        result = self.run_command("print('child output')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "child output\n")
        self.assertIn("complete", result.stderr)
        self.assertNotIn("\x1b", result.stdout + result.stderr)

    def test_failure_preserves_exit_code_and_both_streams(self):
        result = self.run_command("import sys; print('partial output'); sys.stderr.write('failure detail'); sys.exit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "partial output\n")
        self.assertIn("failure detail", result.stderr)
        self.assertIn("failed", result.stderr)
        self.assertNotIn("complete", result.stderr)

    def test_unknown_duration_context_animates_while_caller_is_blocked(self):
        refreshed = threading.Event()
        class Terminal(io.StringIO):
            frames = 0
            def write(self, text):
                if "working" in text:
                    self.frames += 1
                    if self.frames >= 2 and "38;2;" in text:
                        refreshed.set()
                return super().write(text)
        stream = Terminal()
        with patch.dict(os.environ, {"FORCE_COLOR": "1"}):
            os.environ.pop("NO_COLOR", None)
            with Progress("Blocking stage", stream=stream):
                self.assertTrue(refreshed.wait(timeout=2), "Activity stopped while the caller was waiting")
                self.assertNotIn("complete", stream.getvalue())
        output = stream.getvalue()
        self.assertIn("38;2;", output)
        self.assertIn("complete", output)
        self.assertNotIn("%", output)


if __name__ == "__main__":
    unittest.main()
