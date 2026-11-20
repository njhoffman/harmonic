"""Sample-based full-song chunk plans, provenance, and complementary overlap-add."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from . import __version__
from .sam_jobs import (DEFAULT_TARGETS, MODEL, MODEL_REVISION, SOURCE_REVISION, SAMPLE_RATE, SETTINGS,
                       check_targets, digest, load_job, new_directory, read_wave, save_job, save_pair,
                       validate_pairs, validate_result, write_json)
from .terminal import Progress

PLAN_KIND = "harmonic.sam-audio-song-job.v1"
RESULT_KIND = "harmonic.sam-audio-song-result.v1"
BLEND = "half_cosine_complementary_v1"
TEXT_REVISION = "a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1"
COMMON = ("source", "model", "auxiliary_text_model", "normalized_config_sha256", "settings", "seed",
          "semantics", "channel_reduction", "anchors", "codec_hop_samples", "worker_code_sha256", "worker_lock_sha256")


def coordinates(count: int, chunk: int, overlap: int) -> list[tuple[int, int]]:
    if (any(type(v) is not int for v in (count, chunk, overlap)) or count <= 0
            or not 0 < chunk <= 30 * SAMPLE_RATE or not 0 < 2 * overlap < chunk):
        raise ValueError("Require positive sample counts, chunks <=30s, and overlap less than half a chunk")
    result = []
    start = 0
    while True:
        result.append((start, min(chunk, count - start)))
        if start + chunk >= count:
            return result
        start += chunk - overlap


def make_plan(samples: np.ndarray, source: dict, output: Path, *, chunk: int, overlap: int,
              targets: dict[str, str], seed: int = 2026, text_revision: str = TEXT_REVISION) -> Path:
    points = coordinates(len(samples), chunk, overlap)
    check_targets(targets)
    if not re.fullmatch(r"[0-9a-f]{40}", text_revision):
        raise ValueError("The auxiliary text revision must be a 40-character commit hash")
    if (source["sample_count"] != len(samples) or samples.dtype != np.dtype("<f4")
            or samples.shape != (len(samples), 2) or not np.isfinite(samples).all()
            or hashlib.sha256(samples.tobytes()).hexdigest() != source["pcm_sha256"]):
        raise ValueError("Full-song samples do not match canonical PCM identity")
    with new_directory(output) as temporary:
        chunks = []
        with Progress("Preparing song chunks", len(points)) as progress:
            for index, (start, count) in enumerate(points):
                relative = f"chunks/{index:06d}"
                path = save_job(samples[start:start + count], temporary / relative, source=source,
                                start_sample=start, targets=targets, seed=seed)
                chunks.append({"index": index, "job": relative + "/job.json", "sha256": digest(path),
                               "start_sample": start, "sample_count": count})
                progress.update(index + 1)
        plan = {"schema_version": 1, "kind": PLAN_KIND, "app_version": __version__, "source": source,
                "sample_rate": SAMPLE_RATE, "channels": 2, "sample_count": len(samples),
                "chunk_samples": chunk, "overlap_samples": overlap, "blend": BLEND,
                "model": {"id": MODEL, "revision": MODEL_REVISION, "source_revision": SOURCE_REVISION},
                "targets": targets, "seed": seed, "settings": SETTINGS,
                "text_model_revision": text_revision, "chunks": chunks}
        write_json(temporary / "plan.json", plan)
        load_plan(temporary / "plan.json")
    return output.resolve() / "plan.json"


def prepare_song(audio: Path, output: Path, *, chunk_seconds: float = 10, overlap_seconds: float = 2,
                 targets: dict[str, str] | None = None, seed: int = 2026,
                 text_revision: str = TEXT_REVISION) -> Path:
    from .analysis import decode_audio
    if not all(math.isfinite(v) for v in (chunk_seconds, overlap_seconds)):
        raise ValueError("Chunk duration and overlap must be finite")
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    audio = audio.resolve()
    with Progress("Decoding full-song canonical PCM"):
        source_hash = digest(audio)
        samples = decode_audio(audio)
        if digest(audio) != source_hash:
            raise ValueError("Recording changed during preparation")
    return make_plan(samples, {"path": str(audio), "sha256": source_hash,
                              "pcm_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                              "sample_count": len(samples)}, output,
                     chunk=round(chunk_seconds * SAMPLE_RATE), overlap=round(overlap_seconds * SAMPLE_RATE),
                     targets=targets or dict(DEFAULT_TARGETS), seed=seed, text_revision=text_revision)


def plan_path(path: Path) -> Path:
    path = path.resolve()
    return path / "plan.json" if path.is_dir() else path


def load_plan(path: Path) -> tuple[dict, np.ndarray]:
    path = plan_path(path)
    try:
        plan = json.loads(path.read_text())
        if (plan["schema_version"] != 1 or plan["kind"] != PLAN_KIND or plan["sample_rate"] != SAMPLE_RATE
                or plan["channels"] != 2 or plan["sample_count"] != plan["source"]["sample_count"]
                or plan["blend"] != BLEND or plan["settings"] != SETTINGS
                or plan["model"] != {"id": MODEL, "revision": MODEL_REVISION, "source_revision": SOURCE_REVISION}
                or not re.fullmatch(r"[0-9a-f]{40}", plan["text_model_revision"])):
            raise ValueError("unsupported plan format/settings")
        check_targets(plan["targets"])
        points = coordinates(plan["sample_count"], plan["chunk_samples"], plan["overlap_samples"])
        if len(plan["chunks"]) != len(points):
            raise ValueError("chunk coverage/count mismatch")
        # Hash the reconstructed non-overlapping PCM exactly once. Overlapping inputs must agree bit-for-bit.
        pcm_hash = hashlib.sha256()
        full = np.empty((plan["sample_count"], 2), dtype="<f4")
        filled = 0
        for index, ((start, count), entry) in enumerate(zip(points, plan["chunks"], strict=True)):
            if (entry["index"] != index or entry["job"] != f"chunks/{index:06d}/job.json"
                    or entry["start_sample"] != start or entry["sample_count"] != count):
                raise ValueError("invalid chunk coordinates/path")
            job_path = path.parent / entry["job"]
            if digest(job_path) != entry["sha256"]:
                raise ValueError("chunk job checksum mismatch")
            job, samples = load_job(job_path)
            if (job["source"] != plan["source"] or job["start_sample"] != start or job["sample_count"] != count
                    or any(job[k] != plan[k] for k in ("targets", "seed", "settings", "model"))):
                raise ValueError("chunk job provenance mismatch")
            previous = filled - start
            if previous and not np.array_equal(full[start:filled], samples[:previous]):
                raise ValueError("overlapping source PCM differs between chunks")
            full[filled:start + count] = samples[previous:]
            pcm_hash.update(samples[previous:].tobytes())
            filled = start + count
        if filled != len(full) or pcm_hash.hexdigest() != plan["source"]["pcm_sha256"]:
            raise ValueError("full-song PCM checksum mismatch")
        return plan, full
    except (KeyError, TypeError, AttributeError, OSError, ValueError) as error:
        raise ValueError(f"Invalid SAM song plan {path}: {error}") from error


def weights(count: int, overlap: int, first: bool, last: bool) -> np.ndarray:
    result = np.ones(count, dtype=np.float64)
    fade = 0.5 - 0.5 * np.cos(np.pi * (np.arange(overlap) + 0.5) / overlap)
    if not first:
        result[:overlap] = fade
    if not last:
        result[-overlap:] = 1 - fade
    return result


def overlap_metrics(left: np.ndarray, right: np.ndarray) -> dict:
    a, b = left.astype(np.float64), right.astype(np.float64)
    power_a, power_b = float(np.dot(a, a)), float(np.dot(b, b))
    rms_a, rms_b = math.sqrt(power_a / len(a)), math.sqrt(power_b / len(b))
    significant = rms_a > 1e-8 and rms_b > 1e-8
    lag = None
    if significant:
        size = 1 << (2 * len(a) - 1).bit_length()
        corr = np.fft.irfft(np.fft.rfft(b, size) * np.conj(np.fft.rfft(a, size)), size)
        limit = min(1920, len(a) // 4)
        lags = np.arange(-limit, limit + 1)
        lag = int(lags[np.argmax(corr[lags % size])])
    middle = len(a) // 2
    return {"left_rms": rms_a, "right_rms": rms_b,
            "right_to_left_rms_ratio": rms_b / rms_a if rms_a > 1e-8 else None,
            "zero_lag_correlation": float(np.dot(a, b) / math.sqrt(power_a * power_b)) if significant else None,
            "cross_correlation_peak_lag_samples": lag,
            "lag_search_limit_samples": min(1920, len(a) // 4),
            "difference_rms": float(np.sqrt(np.mean((a - b)**2))),
            "midpoint_hard_splice_step": float(abs(b[middle] - a[max(0, middle - 1)]))}


def run_binding_hash(report: dict) -> str | None:
    if "run_binding_sha256" not in report:
        return None  # Legacy reports predate the binding fingerprint.
    value = report["run_binding_sha256"]
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid song run binding hash")
    return value


def validate_song_metadata(report: dict) -> list[dict]:
    """Validate retained original chunk reports without requiring chunk WAVs or model packages."""
    try:
        if (report["kind"] != RESULT_KIND or report["start_sample"] != 0
                or report["sample_count"] != report["source"]["sample_count"]):
            raise ValueError("invalid full-song timebase")
        chunking = report["chunking"]
        if chunking["blend"] != BLEND or chunking["plan_sha256"] != report["job_sha256"]:
            raise ValueError("unsupported overlap policy/plan identity")
        points = coordinates(report["sample_count"], chunking["chunk_samples"], chunking["overlap_samples"])
        if len(points) != len(chunking["chunks"]):
            raise ValueError("chunk report count mismatch")
        binding_hash = run_binding_hash(report)
        reports = []
        for index, ((start, count), item) in enumerate(zip(points, chunking["chunks"], strict=True)):
            if type(item.get("index")) is not int or item["index"] != index:
                raise ValueError("invalid retained chunk index")
            raw = item["report_json"]
            if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != item["report_sha256"]:
                raise ValueError("retained chunk report checksum mismatch")
            child = json.loads(raw)
            if (child["kind"] != "harmonic.sam-audio-result.v1" or child["schema_version"] != 1
                    or child["start_sample"] != start or child["sample_count"] != count
                    or child["sample_rate"] != SAMPLE_RATE or child["channels"] != 1
                    or not re.fullmatch(r"[0-9a-f]{64}", child["job_sha256"])
                    or child["job_sha256"] != item["job_sha256"]
                    or run_binding_hash(child) != binding_hash
                    or any(child[k] != report[k] for k in COMMON)
                    or set(child["pairs"]) != set(report["pairs"])):
                raise ValueError("inconsistent chunk report provenance/coordinates")
            for name, pair in child["pairs"].items():
                if pair["description"] != report["pairs"][name]["description"]:
                    raise ValueError("inconsistent prompts between chunks")
                for role in ("target", "residual"):
                    record = pair[role]
                    if (record["artifact"] != f"{name}-{role}.wav" or record["sample_count"] != count
                            or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
                        raise ValueError("invalid retained chunk waveform provenance")
            reports.append(child)
        return reports
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError(f"Invalid SAM song provenance: {error}") from error


def stitch_song(plan_file: Path, results: Path, output: Path) -> Path:
    plan_file = plan_path(plan_file)
    plan_hash = digest(plan_file)
    plan, samples = load_plan(plan_file)
    mono = samples.mean(axis=1, dtype=np.float32)
    results = results.resolve()
    entries, reports = [], []
    with Progress("Validating chunk results", len(plan["chunks"])) as progress:
        for index, entry in enumerate(plan["chunks"]):
            path = results / "chunks" / f"{index:06d}" / "report.json"
            report_hash = digest(path)
            child = validate_result(plan_file.parent / entry["job"], path)
            raw = path.read_text()
            if digest(path) != report_hash:
                raise ValueError("Chunk result changed while loading")
            binding_hash = run_binding_hash(child)
            if (child["auxiliary_text_model"]["revision"] != plan["text_model_revision"]
                    or (reports and (binding_hash != run_binding_hash(reports[0])
                                     or any(child[k] != reports[0][k] for k in COMMON)))):
                raise ValueError("Chunks use different models/settings/worker revisions")
            reports.append(child)
            entries.append({"index": index, "job_sha256": entry["sha256"],
                            "report_sha256": report_hash, "report_json": raw})
            progress.update(index + 1)
    merged = copy.deepcopy(reports[0])
    merged.update(kind=RESULT_KIND, app_version=__version__, job_sha256=plan_hash,
                  start_sample=0, sample_count=len(mono), pairs={},
                  alignment="source_sample_coordinates_preserved; no_chunk_shift_or_gain_correction",
                  runtime_scope="first_chunk; all runtimes retained in chunking.chunks",
                  stitcher_code_sha256=digest(Path(__file__)),
                  chunking={"blend": BLEND, "chunk_samples": plan["chunk_samples"],
                            "overlap_samples": plan["overlap_samples"], "plan_sha256": plan_hash,
                            "chunks": entries}, boundaries=[])
    count = len(mono)
    denominator = np.zeros(count, dtype=np.float64)
    for i, entry in enumerate(plan["chunks"]):
        start, n = entry["start_sample"], entry["sample_count"]
        denominator[start:start + n] += weights(n, plan["overlap_samples"], i == 0, i == len(entries) - 1)
    if not np.allclose(denominator, 1, rtol=0, atol=1e-12):
        raise ValueError("Overlap weights leave gaps or change unity gain")
    with new_directory(output) as temporary:
        with Progress("Stitching target/residual streams", len(plan["targets"]) * 2) as progress:
            done = 0
            for name, description in plan["targets"].items():
                pair_arrays = []
                for role in ("target", "residual"):
                    joined = np.zeros(count, dtype=np.float64)
                    previous = None
                    for index, entry in enumerate(plan["chunks"]):
                        start, n = entry["start_sample"], entry["sample_count"]
                        record = reports[index]["pairs"][name][role]
                        path = results / "chunks" / f"{index:06d}" / record["artifact"]
                        raw = read_wave(path)
                        if digest(path) != record["sha256"] or len(raw) != n:
                            raise ValueError("Chunk waveform changed during stitch")
                        fade = weights(n, plan["overlap_samples"], index == 0, index == len(entries) - 1)
                        joined[start:start + n] += raw.astype(np.float64) * fade
                        if previous is not None:
                            o = plan["overlap_samples"]
                            metrics = overlap_metrics(previous[-o:], raw[:o])
                            midpoint = start + o // 2
                            metrics.update(target=name, role=role, overlap_start_sample=start,
                                           overlap_end_sample=start + o,
                                           blended_midpoint_step=float(abs(joined[midpoint] - joined[midpoint - 1])))
                            merged["boundaries"].append(metrics)
                        previous = raw
                    pair_arrays.append(joined.astype("<f4"))
                    done += 1
                    progress.update(done)
                pair = save_pair(temporary, name, *pair_arrays, mono, padding_limit=0)
                pair.update(description=description,
                            elapsed_seconds=sum(r["pairs"][name].get("elapsed_seconds", 0) for r in reports),
                            peak_cuda_allocated_bytes=max(r["pairs"][name].get("peak_cuda_allocated_bytes", 0) for r in reports),
                            peak_cuda_reserved_bytes=max(r["pairs"][name].get("peak_cuda_reserved_bytes", 0) for r in reports))
                pair["real_time_factor"] = pair["elapsed_seconds"] / (count / SAMPLE_RATE)
                merged["pairs"][name] = pair
        merged["elapsed_seconds"] = sum(r.get("elapsed_seconds", 0) for r in reports)
        merged["peak_host_rss_bytes"] = max(r.get("peak_host_rss_bytes", 0) for r in reports)
        completed = results / "completed.json"
        if completed.is_file():
            run = json.loads(completed.read_text())
            if run["plan_sha256"] != plan_hash:
                raise ValueError("Run completion record belongs to another plan")
            merged["run"] = run
        write_json(temporary / "report.json", merged)
        validate_song_result(plan_file, temporary)
        if digest(plan_file) != plan_hash:
            raise ValueError("Plan changed during stitch")
    return output.resolve() / "report.json"


def validate_song_result(plan_file: Path, result: Path) -> dict:
    plan_file = plan_path(plan_file)
    if result.is_dir():
        result /= "report.json"
    try:
        plan, samples = load_plan(plan_file)
        report = json.loads(result.read_text())
        children = validate_song_metadata(report)
        if (report["schema_version"] != 1 or report["job_sha256"] != digest(plan_file)
                or report["source"] != plan["source"] or report["sample_rate"] != SAMPLE_RATE
                or report["channels"] != 1 or set(report["pairs"]) != set(plan["targets"])
                or report["model"] != {**plan["model"], "files_sha256": report["model"]["files_sha256"]}
                or report["settings"] != plan["settings"] or report["seed"] != plan["seed"]
                or report["chunking"]["chunk_samples"] != plan["chunk_samples"]
                or report["chunking"]["overlap_samples"] != plan["overlap_samples"]
                or report["auxiliary_text_model"]["revision"] != plan["text_model_revision"]):
            raise ValueError("merged result/plan provenance mismatch")
        for entry, child in zip(plan["chunks"], children, strict=True):
            if child["job_sha256"] != entry["sha256"]:
                raise ValueError("retained report belongs to a different chunk job")
        for name, description in plan["targets"].items():
            if report["pairs"][name]["description"] != description:
                raise ValueError("merged target prompt mismatch")
        validate_pairs(report, result.parent, samples.mean(axis=1, dtype=np.float32), report["codec_hop_samples"])
        return report
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid stitched SAM result: {error}") from error
