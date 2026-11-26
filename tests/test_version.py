import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("release_version", ROOT / "scripts" / "version.py")
version = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(version)

CHANGELOG = """# Changelog

## [Unreleased]

- Pending work.

## [0.2.0] - 2026-01-02

### Added

- Second release.

## [0.1.1] - 2026-01-01

### Documentation

## [0.1.0] - 2025-12-31

### Added

- First release.

[Unreleased]: https://example.invalid/compare/v0.2.0...HEAD
[0.2.0]: https://example.invalid/tree/v0.2.0
[0.1.0]: https://example.invalid/tree/v0.1.0
"""


class ReleaseNotesTest(unittest.TestCase):
    def test_sections_are_newest_first_and_exclude_unreleased(self):
        numbers = [number for number, _, _ in version.changelog_sections(CHANGELOG)]
        self.assertEqual(numbers, ["0.2.0", "0.1.1", "0.1.0"])

    def test_notes_contain_only_that_section(self):
        notes = version.release_notes("0.2.0", CHANGELOG)
        self.assertEqual(notes, "### Added\n\n- Second release.\n")

    def test_last_section_drops_link_references(self):
        notes = version.release_notes("0.1.0", CHANGELOG)
        self.assertEqual(notes, "### Added\n\n- First release.\n")
        self.assertNotIn("example.invalid", notes)

    def test_missing_and_empty_sections_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no dated entry for 9.9.9"):
            version.release_notes("9.9.9", CHANGELOG)
        with self.assertRaisesRegex(ValueError, "0.1.1 has no items"):
            version.release_notes("0.1.1", CHANGELOG)

    def test_cli_prints_current_version_notes(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "version.py"), "notes"],
                                capture_output=True, text=True, check=True)
        self.assertRegex(result.stdout, r"(?m)^- \S")
        self.assertNotIn("## [", result.stdout)


if __name__ == "__main__":
    unittest.main()
