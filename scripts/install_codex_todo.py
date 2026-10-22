"""Install the portable todo skill and custom prompt into the user's Codex home."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()
    source = ROOT / "tools" / "codex"
    files = [(path, home / "skills" / "todo" / path.relative_to(source / "todo"))
             for path in sorted((source / "todo").rglob("*")) if path.is_file() and "__pycache__" not in path.parts]
    files.append((source / "prompts" / "todo.md", home / "prompts" / "todo.md"))
    # Validate the whole install before writing: preserve existing customizations.
    for original, target in files:
        if target.exists() and (not target.is_file() or target.read_bytes() != original.read_bytes()):
            print(f"Refusing to overwrite existing custom configuration: {target}", file=sys.stderr)
            return 1
    for original, target in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        print(f"Installed {target}")
    print("Restart Codex to load /prompts:todo; the reusable skill is invoked as $todo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
