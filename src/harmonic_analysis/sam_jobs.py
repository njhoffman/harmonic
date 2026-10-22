"""Portable short-excerpt jobs for the isolated SAM Audio worker (no torch imports)."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile

import numpy as np

from . import __version__

SAMPLE_RATE = 48_000
MODEL = "facebook/sam-audio-large-tv"
MODEL_REVISION = "b9fc94687ec044c570cbe30b8c28100cd056f1cb"
SOURCE_REVISION = "bb4c6999d2677c7402360e426afc01ddfad6dce0"
DEFAULT_TARGETS = {"vocals": "man singing", "drums": "drums playing", "bass": "bass guitar playing"}
SETTINGS = {"predict_spans": False, "reranking_candidates": 1,
            "ode_method": "midpoint", "ode_step_size": 0.0625, "dtype": "float32"}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


@contextmanager
def new_directory(output: Path):
    output = output.resolve()
    if output.exists():
        raise ValueError(f"Output already exists: {output}; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        yield temporary
        os.rename(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def check_targets(targets: dict[str, str]) -> None:
    if not targets or len(targets) > 8:
        raise ValueError("Choose between one and eight independent targets")
    for name, description in targets.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name) or not description.strip():
            raise ValueError("Targets need a short lowercase name and a nonempty description")


def save_job(samples: np.ndarray, output: Path, *, source: dict, start_sample: int,
             targets: dict[str, str], seed: int = 2026) -> Path:
    check_targets(targets)
    if (samples.dtype != np.dtype("<f4") or samples.ndim != 2 or samples.shape[1] != 2
            or not 1 <= len(samples) <= 30 * SAMPLE_RATE or not np.isfinite(samples).all()):
        raise ValueError("Expected up to 30 seconds of finite stereo float32 at 48 kHz")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    if type(start_sample) is not int or start_sample < 0 or start_sample + len(samples) > source["sample_count"]:
        raise ValueError("Excerpt is outside the source timeline")
    with new_directory(output) as temporary:
        np.save(temporary / "input.npy", samples, allow_pickle=False)
        write_json(temporary / "job.json", {
            "schema_version": 1, "kind": "harmonic.sam-audio-excerpt.v1", "app_version": __version__,
            "source": source, "sample_rate": SAMPLE_RATE, "channels": 2,
            "start_sample": start_sample, "sample_count": len(samples),
            "input": {"artifact": "input.npy", "sha256": digest(temporary / "input.npy")},
            "model": {"id": MODEL, "revision": MODEL_REVISION, "source_revision": SOURCE_REVISION},
            "targets": targets, "seed": seed, "settings": SETTINGS,
            "semantics": "independent_prompted_target_and_residual_pairs; targets_may_overlap",
            "channel_reduction": "arithmetic_mean_to_mono; no_gain_normalization",
            "anchors": None,
        })
    return output.resolve() / "job.json"


def load_job(path: Path) -> tuple[dict, np.ndarray]:
    path = path.resolve()
    if path.is_dir():
        path /= "job.json"
    try:
        job = json.loads(path.read_text())
        if (type(job["schema_version"]) is not int or job["schema_version"] != 1
                or job["kind"] != "harmonic.sam-audio-excerpt.v1"):
            raise ValueError("unsupported job schema")
        if job["sample_rate"] != SAMPLE_RATE or job["channels"] != 2 or job["settings"] != SETTINGS:
            raise ValueError("unsupported sample rate, channels, or inference settings")
        if job["model"] != {"id": MODEL, "revision": MODEL_REVISION, "source_revision": SOURCE_REVISION}:
            raise ValueError("unsupported model/source revision")
        if job["anchors"] is not None or job["channel_reduction"] != "arithmetic_mean_to_mono; no_gain_normalization":
            raise ValueError("unsupported anchor/channel policy")
        if job["semantics"] != "independent_prompted_target_and_residual_pairs; targets_may_overlap":
            raise ValueError("unsupported target semantics")
        check_targets(job["targets"])
        if type(job["seed"]) is not int or not 0 <= job["seed"] < 2**32:
            raise ValueError("invalid seed")
        for key in ("sha256", "pcm_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", job["source"][key]):
                raise ValueError("invalid source identity")
        count, start = job["sample_count"], job["start_sample"]
        if (type(count) is not int or not 1 <= count <= 30 * SAMPLE_RATE or type(start) is not int
                or start < 0 or type(job["source"]["sample_count"]) is not int
                or start + count > job["source"]["sample_count"]):
            raise ValueError("invalid source timeline")
        if job["input"]["artifact"] != "input.npy":
            raise ValueError("unexpected input artifact")
        artifact = path.parent / "input.npy"
        if digest(artifact) != job["input"]["sha256"]:
            raise ValueError("input checksum mismatch")
        samples = np.load(artifact, allow_pickle=False)
        if samples.dtype != np.dtype("<f4") or samples.shape != (count, 2) or not np.isfinite(samples).all():
            raise ValueError("invalid input shape/type/values")
        return job, samples
    except (KeyError, TypeError, AttributeError, OSError, ValueError) as error:
        raise ValueError(f"Invalid SAM job {path}: {error}") from error


def save_wave(path: Path, samples: np.ndarray) -> None:
    """IEEE float32 mono WAV; preserve relative levels, including peaks above 1."""
    payload = np.asarray(samples, dtype="<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, SAMPLE_RATE, SAMPLE_RATE * 4, 4, 32)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"fact" + struct.pack("<II", 4, len(samples))
    chunks += b"data" + struct.pack("<I", len(payload)) + payload
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)


def read_wave(path: Path) -> np.ndarray:
    """Read the worker's exact float32 mono WAV contract without a new decoder."""
    contents = path.read_bytes()
    if (contents[:4] != b"RIFF" or contents[8:12] != b"WAVE" or len(contents) < 12
            or struct.unpack("<I", contents[4:8])[0] != len(contents) - 8):
        raise ValueError("Invalid worker WAV container")
    chunks = {}
    offset = 12
    while offset + 8 <= len(contents):
        name, size = contents[offset:offset + 4], struct.unpack("<I", contents[offset + 4:offset + 8])[0]
        if name in chunks or offset + 8 + size > len(contents):
            raise ValueError("Invalid worker WAV chunk")
        chunks[name] = contents[offset + 8:offset + 8 + size]
        offset += 8 + size + size % 2
    expected = struct.pack("<HHIIHH", 3, 1, SAMPLE_RATE, SAMPLE_RATE * 4, 4, 32)
    if offset != len(contents) or chunks.get(b"fmt ") != expected or len(chunks.get(b"data", b"")) % 4:
        raise ValueError("Expected 48 kHz mono IEEE float32 worker WAV")
    result = np.frombuffer(chunks.get(b"data", b""), dtype="<f4")
    if chunks.get(b"fact") != struct.pack("<I", len(result)) or not len(result) or not np.isfinite(result).all():
        raise ValueError("Invalid worker WAV sample count/values")
    return result


def save_pair(directory: Path, name: str, target: np.ndarray, residual: np.ndarray,
              mono: np.ndarray, *, padding_limit: int) -> dict:
    check_targets({name: "target"})
    result = {}
    for label, samples in (("target", target), ("residual", residual)):
        samples = np.asarray(samples)
        if (samples.ndim != 1 or not len(mono) <= len(samples) <= len(mono) + padding_limit
                or not np.isfinite(samples).all()):
            raise ValueError(f"Invalid {name} {label} waveform: length, shape, or nonfinite values")
        # The upstream codec pads the right edge to its hop. Never pad a short
        # result or shift its beginning to conceal an alignment problem.
        trimmed = samples[:len(mono)].astype("<f4")
        if not np.isfinite(trimmed).all():
            raise ValueError("Output exceeds float32 range")
        artifact = directory / f"{name}-{label}.wav"
        save_wave(artifact, trimmed)
        result[label] = {"artifact": artifact.name, "sha256": digest(artifact),
                         "sample_count": len(trimmed), "raw_sample_count": len(samples),
                         "right_trim_samples": len(samples) - len(trimmed),
                         "rms": float(np.sqrt(np.mean(trimmed.astype(np.float64) ** 2))),
                         "peak": float(np.max(np.abs(trimmed)))}
    summed = np.asarray(target[:len(mono)], dtype=np.float64) + residual[:len(mono)]
    result["sum_error_rms"] = float(np.sqrt(np.mean((summed - mono) ** 2)))
    return result


def validate_result(job_path: Path, result_path: Path) -> dict:
    job_path = job_path.resolve()
    if job_path.is_dir():
        job_path /= "job.json"
    if result_path.is_dir():
        result_path /= "report.json"
    job, samples = load_job(job_path)
    try:
        report = json.loads(result_path.read_text())
        if report["schema_version"] != 1 or report["kind"] != "harmonic.sam-audio-result.v1":
            raise ValueError("unsupported result schema")
        if report["job_sha256"] != digest(job_path) or report["source"] != job["source"]:
            raise ValueError("job/source checksum identity mismatch")
        for key in ("start_sample", "sample_count", "settings", "seed", "semantics", "channel_reduction", "anchors"):
            if report[key] != job[key]:
                raise ValueError(f"mismatched {key}")
        if report["sample_rate"] != SAMPLE_RATE or report["channels"] != 1:
            raise ValueError("invalid output timebase/channels")
        for key, value in job["model"].items():
            if report["model"][key] != value:
                raise ValueError("mismatched model provenance")
        hop = report["codec_hop_samples"]
        if type(hop) is not int or not 0 < hop <= SAMPLE_RATE:
            raise ValueError("invalid codec hop")
        if set(report["pairs"]) != set(job["targets"]):
            raise ValueError("mismatched target names")
        mono = samples.mean(axis=1, dtype=np.float32)
        for name, description in job["targets"].items():
            pair = report["pairs"][name]
            if pair["description"] != description:
                raise ValueError("mismatched target prompt")
            arrays = []
            for label in ("target", "residual"):
                record = pair[label]
                filename = f"{name}-{label}.wav"
                if record["artifact"] != filename:
                    raise ValueError("unexpected result artifact path")
                artifact = result_path.parent / filename
                if digest(artifact) != record["sha256"]:
                    raise ValueError("output checksum mismatch")
                array = read_wave(artifact)
                if record["sample_count"] != len(array) or len(array) != job["sample_count"]:
                    raise ValueError("output sample count mismatch")
                trimmed = record["raw_sample_count"] - len(array)
                if not 0 <= trimmed < hop or record["right_trim_samples"] != trimmed:
                    raise ValueError("invalid padding provenance")
                rms = float(np.sqrt(np.mean(array.astype(np.float64) ** 2)))
                peak = float(np.max(np.abs(array)))
                if not np.isclose(rms, record["rms"], rtol=1e-6, atol=1e-9) or not np.isclose(peak, record["peak"], rtol=1e-6, atol=1e-9):
                    raise ValueError("output statistics mismatch")
                arrays.append(array.astype(np.float64))
            error = float(np.sqrt(np.mean((arrays[0] + arrays[1] - mono) ** 2)))
            if not np.isclose(error, pair["sum_error_rms"], rtol=1e-6, atol=1e-9):
                raise ValueError("sum-error statistics mismatch")
        return report
    except (KeyError, TypeError, AttributeError, OSError, ValueError, struct.error) as error:
        raise ValueError(f"Invalid SAM result {result_path}: {error}") from error
