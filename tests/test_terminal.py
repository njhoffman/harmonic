import os
from pathlib import Path
import subprocess
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
