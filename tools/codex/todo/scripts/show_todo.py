"""Read-only TODO.md viewer with ANSI terminal and styled Markdown output."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

TASK = re.compile(r"^(\s*[-*]\s+)\[([ xX])\](\s+.*)$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
ANSI = {"heading": "\033[1;96m", "done": "\033[32m", "pending": "\033[33m",
        "muted": "\033[90m", "reset": "\033[0m"}


def find_todo(directory: Path) -> Path:
    try:
        result = subprocess.run(["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, check=False)
        root = Path(result.stdout.strip()).resolve() if result.returncode == 0 else directory
    except FileNotFoundError:
        root = directory
    for candidate in (directory, *directory.parents):
        path = candidate / "TODO.md"
        if path.is_file():
            return path
        if candidate == root:
            break
    raise FileNotFoundError(f"No TODO.md found between {directory} and {root}")


def render(content: str, *, markdown: bool, color: bool) -> str:
    lines = content.splitlines()
    completed = total = 0

    def paint(text: str, style: str) -> str:
        return ANSI[style] + text + ANSI["reset"] if color else text

    output = []
    continuation_style = None
    fence = None
    for line in lines:
        code = fence is not None
        boundary = FENCE.match(line)
        if boundary:
            marker, trailing = boundary.groups()
            if fence is None:
                fence = marker
                code = True
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not trailing.strip():
                fence = None
        if code:
            output.append(line if markdown else paint(line, "muted"))
            continuation_style = None
            continue
        match = TASK.match(line)
        if match:
            done = match.group(2).lower() == "x"
            total += 1
            completed += done
            continuation_style = "done" if done else "pending"
            if markdown:
                marker = "🟢" if done else "🟡"
                output.append(f"{match.group(1)}[{match.group(2)}] {marker}{match.group(3)}")
            else:
                output.append(paint(line, continuation_style))
        elif markdown:
            output.append(line)
        elif line.startswith("#"):
            continuation_style = None
            output.append(paint(line, "heading"))
        elif line.startswith((" ", "\t")) and continuation_style:
            output.append(paint(line, continuation_style))
        else:
            continuation_style = None
            style = "pending" if "pending:" in line.lower() else "muted"
            output.append(paint(line, style))
    summary = f"{completed}/{total} complete | {total - completed} pending"
    summary = f"**{summary}**" if markdown else paint(summary, "heading")
    return "\n".join([summary, "", *output]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, help="Explicit TODO file (default: current project)")
    parser.add_argument("--format", choices=("terminal", "markdown"), default="terminal")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    args = parser.parse_args()
    try:
        path = args.path.expanduser().resolve() if args.path else find_todo(Path.cwd().resolve())
        content = path.read_text(encoding="utf-8")
        color = args.color == "always" or (args.color == "auto" and sys.stdout.isatty() and "NO_COLOR" not in os.environ)
        sys.stdout.write(render(content, markdown=args.format == "markdown", color=color))
    except (OSError, UnicodeError) as error:
        print(f"todo: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
