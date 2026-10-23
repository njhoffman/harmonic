import os
import fcntl
import pty
import select
import struct
import termios
import time
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
STATUS = shutil.which("todo-status")
PICKER = shutil.which("todo-fzf")
CONTENT = """# Checklist
Categories: infra

## 1. Active work

- [ ] **Normal work** (p2) [feature]
  Keep the full continuation in previews.
- [x] **Done milestone** (p1) [test] (due 2020-01-01)
  Completed details are still available with --all.
- [ ] **Urgent work** (p1) [bug] (due 2020-01-01)
  A real overdue task.

```markdown
## Not a real section
- [ ] **Phantom task** (p1) [bug]
```

## 2. Completed archive

- [X] **Archived work** (p3) [infra]
"""


@unittest.skipUnless(STATUS and PICKER, "Global todo-status and todo-fzf are optional integrations")
class TodoViewerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="harmonic todo ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.file = self.root / "TODO with spaces.md"
        self.file.write_text(CONTENT)
        self.environment = {**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "1",
                            "TODO_TODAY": "2026-10-22", "FZF_DEFAULT_OPTS_FILE": "/dev/null",
                            "FZF_DEFAULT_OPTS": ""}

    def run_tool(self, script, *arguments, environment=None):
        return subprocess.run([str(script), "-f", str(self.file), *arguments],
                              env=environment or self.environment, cwd=ROOT,
                              text=True, capture_output=True, timeout=10)

    def test_default_and_all_views_keep_task_states_and_counts(self):
        for options in ((), ("--pretty",)):
            default = self.run_tool(STATUS, *options)
            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertIn("☐", default.stdout)
            self.assertNotIn("Done milestone", default.stdout)
            self.assertNotIn("Completed archive", default.stdout)
            self.assertNotIn("Phantom task", default.stdout)
            self.assertNotIn("\033[", default.stdout)
            complete = self.run_tool(STATUS, "--all", *options)
            self.assertEqual(complete.returncode, 0, complete.stderr)
            self.assertIn("☑", complete.stdout)
            self.assertIn("Done milestone", complete.stdout)
            self.assertIn("Archived work", complete.stdout)
            self.assertIn("2 open", complete.stdout)
            self.assertIn("P1 1", complete.stdout)
            self.assertIn("1 overdue", complete.stdout)
        selected = self.run_tool(STATUS, "--all", "1")
        self.assertIn("Completed details", selected.stdout)
        self.assertIn("Keep the full continuation", selected.stdout)
        self.assertNotIn("Archived work", selected.stdout)
        default_section = self.run_tool(STATUS, "1")
        self.assertNotIn("Done milestone", default_section.stdout)
        self.assertNotIn("Completed details", default_section.stdout)

    def test_tsv_and_metadata_audit_preserve_line_ranges_and_ignore_examples(self):
        listing = self.run_tool(STATUS, "--all", "-l")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        rows = [line.split("\t") for line in listing.stdout.splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(len(row) == 10 for row in rows))
        self.assertEqual([row[8:] for row in rows], [["0", "☐"], ["1", "☑"], ["0", "☐"], ["1", "☑"]])
        for row in rows:
            first, last = map(int, row[:2])
            self.assertIn(row[3], CONTENT.splitlines()[first - 1])
            self.assertGreaterEqual(last, first)
        audited = self.run_tool(STATUS, "--all", "--check")
        self.assertEqual(audited.returncode, 0, audited.stdout + audited.stderr)
        self.file.write_text(CONTENT + "\n- [ ] Needs metadata\n")
        bad = self.run_tool(STATUS, "--check")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("missing priority, category", bad.stdout)

    def test_fzf_rows_include_completion_only_with_all_and_sort_pending_first(self):
        default = self.run_tool(PICKER, "--rows", "urgency")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertNotIn("Done milestone", default.stdout)
        complete = self.run_tool(PICKER, "--all", "--rows", "urgency")
        self.assertEqual(complete.returncode, 0, complete.stderr)
        rows = [line.split("\t") for line in complete.stdout.splitlines()]
        self.assertEqual([row[3] for row in rows], ["Urgent work", "Normal work", "Done milestone", "Archived work"])
        self.assertTrue(all(len(row) == 5 for row in rows))
        self.assertIn("☐", rows[0][2])
        self.assertIn("☑", rows[2][2])
        self.assertIn("☑", rows[2][4])
        self.assertNotIn("OVERDUE", rows[2][2])
        self.assertNotIn("\033[", complete.stdout)

    def test_completed_preview_and_order_reload_keep_file_and_all_filter(self):
        source_line = next(index for index, text in enumerate(CONTENT.splitlines(), 1) if "Done milestone" in text)
        hidden = self.run_tool(PICKER, "--card", str(source_line))
        self.assertEqual(hidden.stdout, "")
        preview = self.run_tool(PICKER, "--all", "--card", str(source_line))
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("☑ completed", preview.stdout)
        self.assertIn("Completed details", preview.stdout)
        self.assertNotIn("\033[", preview.stdout)
        state = self.root / "order"
        state.write_text("urgency\n")
        toggle = self.run_tool(PICKER, "--all", "--toggle", str(state))
        self.assertEqual(toggle.returncode, 0, toggle.stderr)
        self.assertEqual(state.read_text().strip(), "file")
        reload = toggle.stdout.strip().split("+reload(", 1)[1][:-1]
        result = subprocess.run(shlex.split(reload), env=self.environment, text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [line.split("\t") for line in result.stdout.splitlines()]
        self.assertEqual([row[3] for row in rows], ["Normal work", "Done milestone", "Urgent work", "Archived work"])

    @unittest.skipUnless(shutil.which("fzf"), "fzf is required for the actual selection check")
    def test_actual_fzf_selection_preserves_completed_icon(self):
        environment = {**self.environment, "FZF_DEFAULT_OPTS": "--filter='Done milestone'"}
        result = self.run_tool(PICKER, "--all", environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("☑", result.stdout)
        self.assertIn("Done milestone", result.stdout)
        self.assertNotIn("\033[", result.stdout)
        default = self.run_tool(PICKER, environment=environment)
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(default.stdout, "")

    def test_completion_preserves_bytes_permissions_and_refuses_stale_rows(self):
        self.file.write_bytes(CONTENT.replace("\n", "\r\n").encode())
        self.file.chmod(0o640)
        before = self.file.read_bytes()
        state = self.root / "order state"
        state.write_text("file\n")
        refreshed = self.run_tool(PICKER, "--refresh", str(state))
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        line = str(next(index for index, item in enumerate(CONTENT.splitlines(), 1) if "Normal work" in item))
        completed = self.run_tool(PICKER, "--complete", str(state), line)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("+reload(", completed.stdout)
        self.assertEqual(self.file.read_bytes(), before.replace(b"- [ ] **Normal work**", b"- [x] **Normal work**"))
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o640)
        reload = completed.stdout.strip().split("+reload(", 1)[1][:-1]
        pending = subprocess.run(shlex.split(reload), env=self.environment, text=True,
                                 capture_output=True, timeout=10)
        self.assertEqual(pending.returncode, 0, pending.stderr)
        self.assertNotIn("Normal work", pending.stdout)
        changed = b"Added externally\r\n" + self.file.read_bytes()
        self.file.write_bytes(changed)
        rejected = self.run_tool(PICKER, "--complete", str(state), line)
        self.assertIn("Check failed", rejected.stdout)
        self.assertEqual(self.file.read_bytes(), changed)

    def test_completion_with_all_keeps_checked_item_and_does_not_uncheck_it(self):
        state = self.root / "order"
        state.write_text("urgency\n")
        rows = self.run_tool(PICKER, "--all", "--refresh", str(state))
        line = next(row.split("\t")[0] for row in rows.stdout.splitlines() if "Normal work" in row)
        result = self.run_tool(PICKER, "--all", "--complete", str(state), line)
        self.assertIn("--all", result.stdout)
        updated = self.file.read_bytes()
        again = self.run_tool(PICKER, "--all", "--complete", str(state), line)
        self.assertNotIn("Check failed", again.stdout)
        self.assertEqual(self.file.read_bytes(), updated)
        rows = self.run_tool(PICKER, "--all", "--refresh", str(state))
        normal = next(row for row in rows.stdout.splitlines() if "Normal work" in row)
        self.assertIn("☑", normal)

    @unittest.skipUnless(shutil.which("fzf"), "fzf is required for the interactive completion check")
    def test_ctrl_d_completes_in_live_fzf_without_exiting(self):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 160, 0, 0))
        def terminal_session():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        environment = {**self.environment, "TERM": "xterm-256color"}
        process = subprocess.Popen([PICKER, "-f", str(self.file), "--all", "Normal work"],
                                   env=environment, stdin=slave, stdout=slave, stderr=slave,
                                   preexec_fn=terminal_session)
        os.close(slave)
        try:
            output = b""
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and b"Normal work" not in output:
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 65536)
            self.assertIn(b"Normal work", output)
            self.assertIn("\uf0ae".encode(), output)
            os.write(master, b"\x04")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if "- [x] **Normal work**" in self.file.read_text():
                    break
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 65536)
            self.assertIn("- [x] **Normal work**", self.file.read_text())
            self.assertIsNone(process.poll(), "Completing a task closed the picker")
            # Enter after the reload must return the updated, checked selection.
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and "☑".encode() not in output:
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 65536)
            self.assertIn("☑".encode(), output)
            os.write(master, b"\r")
            process.wait(timeout=5)
            self.assertEqual(process.returncode, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            os.close(master)

    def test_help_version_and_invalid_options_need_no_todo_file(self):
        self.file.unlink()
        for script in (STATUS, PICKER):
            for flag in ("-h", "--help"):
                result = self.run_tool(script, flag)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--all", result.stdout)
                self.assertIn("incomplete", result.stdout)
                self.assertIn("Examples:", result.stdout)
            version = self.run_tool(script, "-v")
            self.assertEqual(version.returncode, 0, version.stderr)
            self.assertRegex(version.stdout, r"^todo-(?:status|fzf) \d+\.\d+\.\d+\n$")
            bad = self.run_tool(script, "--unknown")
            self.assertEqual(bad.returncode, 2)
            missing = subprocess.run([str(script), "-f"], env=self.environment,
                                     text=True, capture_output=True, timeout=10)
            self.assertEqual(missing.returncode, 2)
            self.assertIn("requires", missing.stderr)


if __name__ == "__main__":
    unittest.main()
