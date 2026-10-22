from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .analysis import analyze


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Harmonic's original-mix audio features")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("audio", type=Path, help="Local audio recording (MP3, FLAC, WAV, etc.)")
    parser.add_argument("--output", type=Path, required=True, help="New analysis bundle directory")
    arguments = parser.parse_args()
    try:
        manifest = analyze(arguments.audio, arguments.output)
    except (OSError, ValueError) as error:
        print(f"harmonic-analyze: {error}", file=sys.stderr)
        return 1
    print(f"Saved {manifest}")
    return 0
