"""Keep release versions synchronized without requiring the project environment."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "pyproject.toml": r'(?m)^version = "(\d+\.\d+\.\d+)"$',
    "CMakeLists.txt": r'project\(harmonic VERSION (\d+\.\d+\.\d+) LANGUAGES C CXX\)',
    "src/harmonic_analysis/__init__.py": r'(?m)^__version__ = "(\d+\.\d+\.\d+)"$',
}


def current_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def check_versions() -> str:
    version = current_version()
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError(f"Invalid release version: {version}")
    for name, pattern in PATTERNS.items():
        match = re.search(pattern, (ROOT / name).read_text())
        if not match or match.group(1) != version:
            raise ValueError(f"Version mismatch in {name}; expected {version}")
    packages = tomllib.loads((ROOT / "uv.lock").read_text())["package"]
    package = next(p for p in packages if p["name"] == "harmonic-analysis")
    if package["version"] != version:
        raise ValueError("Version mismatch in uv.lock; run uv lock --offline --cache-dir .cache/uv")
    return version


def check_changelog(version: str) -> None:
    content = (ROOT / "CHANGELOG.md").read_text()
    sections = list(re.finditer(r"(?m)^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$", content))
    if not sections or sections[0].group(1) != version:
        raise ValueError(f"The newest dated CHANGELOG.md entry must be {version}")
    date.fromisoformat(sections[0].group(2))
    end = sections[1].start() if len(sections) > 1 else len(content)
    body = content[sections[0].end():end]
    if not re.search(r"(?m)^- \S", body):
        raise ValueError("Complete the new changelog entry before releasing")


def bump(level: str) -> None:
    old = check_versions()
    major, minor, patch = map(int, old.split("."))
    new = {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0",
           "patch": f"{major}.{minor}.{patch + 1}"}[level]
    changelog = ROOT / "CHANGELOG.md"
    content = changelog.read_text()
    marker = "## [Unreleased]"
    if marker not in content:
        raise ValueError("CHANGELOG.md needs an Unreleased heading")
    for name, pattern in PATTERNS.items():
        path = ROOT / name
        value = path.read_text()
        match = re.search(pattern, value)
        assert match is not None
        path.write_text(value[:match.start(1)] + new + value[match.end(1):])
    if not re.search(rf"(?m)^## \[{re.escape(new)}\] - ", content):
        content = content.replace(marker, f"{marker}\n\n## [{new}] - {date.today().isoformat()}", 1)
    content = re.sub(r"(?m)^\[Unreleased\]: .*$",
                     f"[Unreleased]: https://github.com/njhoffman/harmonic/compare/v{new}...HEAD", content)
    if not re.search(rf"(?m)^\[{re.escape(new)}\]:", content):
        content += f"[{new}]: https://github.com/njhoffman/harmonic/tree/v{new}\n"
    changelog.write_text(content)
    subprocess.run(["uv", "lock", "--offline", "--cache-dir", ".cache/uv"], cwd=ROOT, check=True)
    print(f"Bumped {old} -> {new}. Complete the new CHANGELOG.md entry, stage approved changes, then run just release.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show")
    commands.add_parser("check")
    bump_parser = commands.add_parser("bump")
    bump_parser.add_argument("level", choices=("patch", "minor", "major"))
    arguments = parser.parse_args()
    try:
        if arguments.command == "bump":
            bump(arguments.level)
        elif arguments.command == "check":
            version = check_versions()
            check_changelog(version)
            print(f"Version {version}: source files, lockfile, and changelog agree")
        else:
            print(current_version())
    except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as error:
        print(f"version: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
