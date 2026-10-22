"""Prepare portable excerpts for the GPU worker without installing model dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from . import __version__
from .analysis import SAMPLE_RATE, decode_audio, sha256_file
from .sam_jobs import DEFAULT_TARGETS, load_job, save_job, validate_result
from .terminal import Progress


def prepare(audio: Path, output: Path, *, start: float, duration: float,
            targets: dict[str, str], seed: int) -> Path:
    if not math.isfinite(start) or start < 0 or not math.isfinite(duration) or not 0 < duration <= 30:
        raise ValueError("Start must be nonnegative; duration must be between 0 and 30 seconds")
    if output.exists():
        raise ValueError(f"Output already exists: {output}; choose a new directory")
    audio = audio.resolve()
    with Progress("Decoding and identifying source"):
        source_hash = sha256_file(audio)
        samples = decode_audio(audio)
        if sha256_file(audio) != source_hash:
            raise ValueError("Source changed during preparation")
    first, count = round(start * SAMPLE_RATE), round(duration * SAMPLE_RATE)
    if count < 1 or first + count > len(samples):
        raise ValueError("The requested excerpt extends beyond the recording")
    with Progress("Saving portable SAM job"):
        return save_job(samples[first:first + count], output,
                        source={"path": str(audio), "sha256": source_hash,
                                "pcm_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                                "sample_count": len(samples)},
                        start_sample=first, targets=targets, seed=seed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    creator = commands.add_parser("prepare", help="Write a new self-contained, at-most-30-second excerpt job")
    creator.add_argument("audio", type=Path)
    creator.add_argument("--output", required=True, type=Path)
    creator.add_argument("--start", type=float, default=30)
    creator.add_argument("--duration", type=float, default=10)
    creator.add_argument("--seed", type=int, default=2026)
    creator.add_argument("--target", action="append", metavar="NAME=DESCRIPTION", help="Repeat to replace the default vocal/drum/bass prompts")
    checker = commands.add_parser("inspect", help="Verify a prepared job without torch, authentication, or original audio")
    checker.add_argument("job", type=Path)
    validator = commands.add_parser("validate", help="Verify returned result identity, float WAVs, and exact sample counts")
    validator.add_argument("job", type=Path)
    validator.add_argument("result", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "prepare":
            targets = dict(DEFAULT_TARGETS)
            if arguments.target:
                pairs = [item.split("=", 1) for item in arguments.target]
                if any(len(pair) != 2 for pair in pairs) or len({pair[0] for pair in pairs}) != len(pairs):
                    raise ValueError("Each target must be a distinct NAME=DESCRIPTION pair")
                targets = dict(pairs)
            path = prepare(arguments.audio, arguments.output, start=arguments.start,
                           duration=arguments.duration, targets=targets, seed=arguments.seed)
            print(f"🟢 Saved GPU-worker job: {path}")
        elif arguments.command == "inspect":
            job, _ = load_job(arguments.job)
            print(json.dumps(job, indent=2))
        else:
            report = validate_result(arguments.job, arguments.result)
            print(f"🟢 Validated {len(report['pairs'])} target/residual pairs at sample {report['start_sample']}")
        return 0
    except (OSError, ValueError) as error:
        print(f"🔴 harmonic-sam: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
