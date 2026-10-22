import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

from harmonic_analysis import __version__

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / "todo-status"
PICKER = ROOT / "todo-fzf"
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
            self.assertEqual(version.stdout.split()[-1], __version__)
            bad = self.run_tool(script, "--unknown")
            self.assertEqual(bad.returncode, 2)
            missing = subprocess.run([str(script), "-f"], env=self.environment,
                                     text=True, capture_output=True, timeout=10)
            self.assertEqual(missing.returncode, 2)
            self.assertIn("requires", missing.stderr)


if __name__ == "__main__":
    unittest.main()
