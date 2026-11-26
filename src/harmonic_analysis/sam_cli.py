"""Prepare and validate SAM excerpt/song jobs, stitch audio, and adapt source features."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from . import __version__
from .analysis import SAMPLE_RATE, decode_audio, sha256_file
from .sam_jobs import DEFAULT_TARGETS, load_job, save_job, validate_result, write_json
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
    adapter = commands.add_parser("features", help="Add validated SAM target/residual features to an original mix bundle")
    adapter.add_argument("mix", type=Path)
    adapter.add_argument("job", type=Path)
    adapter.add_argument("result", type=Path)
    adapter.add_argument("--output", required=True, type=Path)
    adapter.add_argument("--audio", type=Path, help="Relocated original recording; checksum must match")
    song = commands.add_parser("prepare-song", help="Prepare a portable overlapping full-song chunk plan")
    song.add_argument("audio", type=Path)
    song.add_argument("--output", type=Path, required=True)
    song.add_argument("--chunk-duration", type=float, default=10)
    song.add_argument("--overlap", type=float, default=2)
    song.add_argument("--seed", type=int, default=2026)
    song.add_argument("--target", action="append", metavar="NAME=DESCRIPTION")
    from .sam_chunks import TEXT_REVISION
    song.add_argument("--text-revision", default=TEXT_REVISION, help="Pinned auxiliary model commit")
    plan_check = commands.add_parser("inspect-song", help="Verify every input chunk and full canonical PCM hash")
    plan_check.add_argument("plan", type=Path)
    stitch = commands.add_parser("stitch", help="Validate chunks and overlap-add new full-length WAV pairs")
    stitch.add_argument("plan", type=Path)
    stitch.add_argument("results", type=Path)
    stitch.add_argument("--output", type=Path, required=True)
    song_check = commands.add_parser("validate-song", help="Validate stitched full-song WAVs and chunk provenance")
    song_check.add_argument("plan", type=Path)
    song_check.add_argument("result", type=Path)
    from .sam_benchmark import CASES
    benchmark_prepare = commands.add_parser("prepare-vocal-benchmark", help="Prepare mixed, vocal-only, and accompaniment-only jobs from aligned stems")
    benchmark_prepare.add_argument("vocal_stem", type=Path)
    benchmark_prepare.add_argument("accompaniment_stem", type=Path)
    benchmark_prepare.add_argument("--output", required=True, type=Path)
    benchmark_prepare.add_argument("--start", type=float, default=0)
    benchmark_prepare.add_argument("--duration", type=float, required=True)
    benchmark_prepare.add_argument("--prompt", default=DEFAULT_TARGETS["vocals"])
    benchmark = commands.add_parser("benchmark-vocals", help="Score a validated vocal result against known sources")
    benchmark.add_argument("job", type=Path)
    benchmark.add_argument("result", type=Path)
    benchmark.add_argument("--case", choices=CASES, required=True)
    benchmark.add_argument("--vocal-stem", type=Path)
    benchmark.add_argument("--accompaniment-stem", type=Path)
    benchmark.add_argument("--absent-limit", type=float, default=0.05)
    musdb_prepare = commands.add_parser("prepare-musdb", help="Decode MUSDB18 tracks into references and multi-target jobs")
    musdb_prepare.add_argument("archive", type=Path, help="musdb18.zip with *.stem.mp4 members")
    musdb_prepare.add_argument("tracks", nargs="+", help="Track names as stored in the zip, without .stem.mp4")
    musdb_prepare.add_argument("--output", required=True, type=Path, help="New run directory")
    musdb_score = commands.add_parser("score-musdb", help="Score validated MUSDB results (lag-aligned, multi-target)")
    musdb_score.add_argument("run", type=Path)
    musdb_score.add_argument("results", type=Path, help="Directory of per-job result directories")
    musdb_score.add_argument("--output", required=True, type=Path, help="New scores directory")
    musdb_context = commands.add_parser("musdb-context", help="Compare 10 s, 20 s, and 30 s context on the common core")
    musdb_context.add_argument("run", type=Path)
    musdb_context.add_argument("results", type=Path)
    musdb_context.add_argument("--output", required=True, type=Path, help="New JSON file")
    arguments = parser.parse_args()
    try:
        if arguments.command in ("prepare", "prepare-song"):
            targets = dict(DEFAULT_TARGETS)
            if arguments.target:
                pairs = [item.split("=", 1) for item in arguments.target]
                if any(len(pair) != 2 for pair in pairs) or len({pair[0] for pair in pairs}) != len(pairs):
                    raise ValueError("Each target must be a distinct NAME=DESCRIPTION pair")
                targets = dict(pairs)
            if arguments.command == "prepare-song":
                from .sam_chunks import prepare_song
                path = prepare_song(arguments.audio, arguments.output, chunk_seconds=arguments.chunk_duration,
                                    overlap_seconds=arguments.overlap, targets=targets, seed=arguments.seed,
                                    text_revision=arguments.text_revision)
            else:
                path = prepare(arguments.audio, arguments.output, start=arguments.start,
                               duration=arguments.duration, targets=targets, seed=arguments.seed)
            print(f"🟢 Saved GPU-worker job: {path}")
        elif arguments.command == "prepare-vocal-benchmark":
            from .sam_benchmark import prepare_cases
            path = prepare_cases(arguments.vocal_stem, arguments.accompaniment_stem, arguments.output,
                                 start=arguments.start, duration=arguments.duration, prompt=arguments.prompt)
            print(f"🟢 Saved vocal benchmark jobs: {path}")
        elif arguments.command == "benchmark-vocals":
            from .sam_benchmark import score_case
            report = score_case(arguments.job, arguments.result, arguments.case,
                                vocal=arguments.vocal_stem, accompaniment=arguments.accompaniment_stem,
                                absent_limit=arguments.absent_limit)
            print(json.dumps(report, indent=2, allow_nan=False))
        elif arguments.command == "prepare-musdb":
            from .sam_musdb import prepare as prepare_musdb
            path = prepare_musdb(arguments.archive, arguments.tracks, arguments.output)
            print(f"🟢 Saved MUSDB benchmark run: {path}")
        elif arguments.command == "score-musdb":
            from .sam_musdb import score, summary_lines
            summary = score(arguments.run, arguments.results, arguments.output)
            print("\n".join(summary_lines(summary)))
            print(f"🟢 Saved {len(summary['jobs'])} job scores and summary.json in {arguments.output}")
        elif arguments.command == "musdb-context":
            from .sam_musdb import compare_context
            if arguments.output.exists():
                raise ValueError(f"Refusing to overwrite {arguments.output}")
            comparison = compare_context(arguments.run, arguments.results)
            write_json(arguments.output, comparison)
            for track, rows in comparison.items():
                for target, configs in rows.items():
                    print(f"{track[:22]:22} {target:15}",
                          "  ".join(f"{k} {v['expected_target_gain']:.3f}" for k, v in configs.items()))
            print(f"🟢 Saved context comparison: {arguments.output}")
        elif arguments.command == "inspect-song":
            from .sam_chunks import validate_plan
            plan = validate_plan(arguments.plan)
            print(json.dumps(plan, indent=2))
        elif arguments.command == "stitch":
            from .sam_chunks import stitch_song
            path = stitch_song(arguments.plan, arguments.results, arguments.output)
            print(f"🟢 Saved full-song separation: {path}")
        elif arguments.command == "validate-song":
            from .sam_chunks import validate_song_result
            report = validate_song_result(arguments.plan, arguments.result)
            print(f"🟢 Validated {len(report['pairs'])} full-song pairs and chunk provenance")
        elif arguments.command == "inspect":
            job, _ = load_job(arguments.job)
            print(json.dumps(job, indent=2))
        elif arguments.command == "features":
            from .source_features import build_source_bundle
            path = build_source_bundle(arguments.mix, arguments.job, arguments.result,
                                       arguments.output, audio=arguments.audio)
            print(f"🟢 Saved source feature bundle: {path}")
        else:
            report = validate_result(arguments.job, arguments.result)
            print(f"🟢 Validated {len(report['pairs'])} target/residual pairs at sample {report['start_sample']}")
        return 0
    except (OSError, ValueError) as error:
        print(f"🔴 harmonic-sam: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
