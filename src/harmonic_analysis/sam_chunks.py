"""Sample-based full-song chunk plans, provenance, and complementary overlap-add."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

from . import __version__
from .sam_jobs import (DEFAULT_TARGETS, MODEL, MODEL_REVISION, PRESENCE_FRAME_SAMPLES, SOURCE_REVISION,
                       SAMPLE_RATE, SETTINGS, check_targets, digest, load_job, new_directory, presence_frames,
                       presence_record, presence_values, read_wave, save_job, save_pair, validate_pairs,
                       validate_presence, validate_result, write_json)
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
        validate_plan(temporary / "plan.json")
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
    plan, full = _read_plan(path, materialize=True)
    assert full is not None
    return plan, full


def validate_plan(path: Path) -> dict:
    """Validate all child jobs and their PCM without allocating a whole-track array."""
    plan, _ = _read_plan(path, materialize=False)
    return plan


def _read_plan(path: Path, *, materialize: bool, mono: bool = False) -> tuple[dict, np.ndarray | None]:
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
        shape = plan["sample_count"] if mono else (plan["sample_count"], 2)
        full = np.empty(shape, dtype="<f4") if materialize else None
        tail = None
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
            samples = np.ascontiguousarray(samples)
            if previous and not np.array_equal(tail, samples[:previous].view(np.uint8)):
                raise ValueError("overlapping source PCM differs between chunks")
            if full is not None:
                full[filled:start + count] = (samples[previous:].mean(axis=1, dtype=np.float32)
                                             if mono else samples[previous:])
            pcm_hash.update(memoryview(samples[previous:]).cast("B"))
            filled = start + count
            if filled < plan["sample_count"]:
                tail = samples[-plan["overlap_samples"]:].view(np.uint8).copy()
        if filled != plan["sample_count"] or pcm_hash.hexdigest() != plan["source"]["pcm_sha256"]:
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


def stitch_presence(children: list[dict], points: list[tuple[int, int]], overlap: int, name: str,
                    count: int) -> dict | None:
    """Blend chunk presence onto the song's 40 ms grid with the waveform crossfade weights.

    Each song frame takes the chunk-local frames containing its center sample, so
    chunk starts need not align to the presence grid. Returns None when no chunk
    measured presence; a mixture of measured and unmeasured chunks is rejected.
    """
    measured = [child.get("presence_model") is not None for child in children]
    if not any(measured):
        return None
    if not all(measured):
        raise ValueError("some chunks lack presence measurements")
    frames = presence_frames(count)
    centers = np.minimum(np.arange(frames, dtype=np.int64) * PRESENCE_FRAME_SAMPLES + PRESENCE_FRAME_SAMPLES // 2,
                         count - 1)
    total, weight = np.zeros(frames), np.zeros(frames)
    for index, ((start, n), child) in enumerate(zip(points, children, strict=True)):
        values = presence_values(child["pairs"][name]["presence"], n).astype(np.float64)
        fade = weights(n, overlap, index == 0, index == len(points) - 1)
        inside = (centers >= start) & (centers < start + n)
        local = centers[inside] - start
        total[inside] += fade[local] * values[local // PRESENCE_FRAME_SAMPLES]
        weight[inside] += fade[local]
    if not np.allclose(weight, 1, rtol=0, atol=1e-12):
        raise ValueError("presence crossfade weights do not sum to one")
    return presence_record(np.clip(total, 0, 1), count)


def run_binding_hash(report: dict) -> str | None:
    if "run_binding_sha256" not in report:
        return None  # Legacy reports predate the binding fingerprint.
    value = report["run_binding_sha256"]
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("invalid song run binding hash")
    return value


def valid_level(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value <= sys.float_info.max


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
        hop = report["codec_hop_samples"]
        if type(hop) is not int or not 0 < hop <= SAMPLE_RATE:
            raise ValueError("invalid retained chunk codec hop")
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
                    or child.get("presence_model") != report.get("presence_model")
                    or set(child["pairs"]) != set(report["pairs"])):
                raise ValueError("inconsistent chunk report provenance/coordinates")
            validate_presence(child, count)
            for name, pair in child["pairs"].items():
                if pair["description"] != report["pairs"][name]["description"]:
                    raise ValueError("inconsistent prompts between chunks")
                if not valid_level(pair.get("sum_error_rms")):
                    raise ValueError("invalid retained chunk reconstruction level")
                for role in ("target", "residual"):
                    record = pair[role]
                    raw_count, trim = record.get("raw_sample_count"), record.get("right_trim_samples")
                    if (record["artifact"] != f"{name}-{role}.wav"
                            or type(record["sample_count"]) is not int or record["sample_count"] != count
                            or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
                            or type(raw_count) is not int or type(trim) is not int or not 0 <= trim < hop
                            or raw_count != count + trim
                            or not all(valid_level(record.get(key)) for key in ("rms", "peak"))):
                        raise ValueError("invalid retained chunk waveform provenance")
            reports.append(child)
        if validate_presence(report, report["sample_count"]):
            for name, pair in report["pairs"].items():
                expected = stitch_presence(reports, points, chunking["overlap_samples"], name, report["sample_count"])
                if expected is None or expected["sha256"] != pair["presence"]["sha256"]:
                    raise ValueError("merged presence differs from the retained chunk measurements")
        elif any(child.get("presence_model") is not None for child in reports):
            raise ValueError("merged report dropped chunk presence measurements")
        return reports
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError(f"Invalid SAM song provenance: {error}") from error


def stitch_song(plan_file: Path, results: Path, output: Path) -> Path:
    plan_file = plan_path(plan_file)
    plan_hash = digest(plan_file)
    plan, mono = _read_plan(plan_file, materialize=True, mono=True)
    assert mono is not None
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
                                     or child.get("presence_model") != reports[0].get("presence_model")
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
    previous_tail = None
    for i, entry in enumerate(plan["chunks"]):
        n, overlap = entry["sample_count"], plan["overlap_samples"]
        last = i == len(entries) - 1
        fade = weights(n, overlap, i == 0, last)
        # Validated coordinates permit at most two contributors at any sample.
        # Check their actual weights without a whole-track denominator array.
        body_start, body_end = (0 if i == 0 else overlap), (n if last else n - overlap)
        invalid_overlap = (previous_tail is not None
                           and not np.allclose(previous_tail + fade[:overlap], 1, rtol=0, atol=1e-12))
        if invalid_overlap or not np.allclose(fade[body_start:body_end], 1, rtol=0, atol=1e-12):
            raise ValueError("Overlap weights leave gaps or change unity gain")
        previous_tail = None if last else fade[-overlap:].copy()
    with new_directory(output) as temporary:
        with Progress("Stitching target/residual streams", len(plan["targets"]) * 2) as progress:
            done = 0
            for name, description in plan["targets"].items():
                pair_arrays = []
                for role in ("target", "residual"):
                    joined = np.empty(count, dtype="<f4")
                    previous = tail = None
                    for index, entry in enumerate(plan["chunks"]):
                        start, n = entry["start_sample"], entry["sample_count"]
                        record = reports[index]["pairs"][name][role]
                        path = results / "chunks" / f"{index:06d}" / record["artifact"]
                        raw = read_wave(path)
                        if digest(path) != record["sha256"] or len(raw) != n:
                            raise ValueError("Chunk waveform changed during stitch")
                        fade = weights(n, plan["overlap_samples"], index == 0, index == len(entries) - 1)
                        # Finish each sample in float64 before its only float32
                        # cast. Keep the overlap tail until the next chunk arrives.
                        blended = np.zeros(n, dtype=np.float64)
                        blended += raw.astype(np.float64) * fade
                        if tail is not None:
                            blended[:len(tail)] = tail + blended[:len(tail)]
                        if previous is not None:
                            o = plan["overlap_samples"]
                            metrics = overlap_metrics(previous[-o:], raw[:o])
                            midpoint = o // 2
                            metrics.update(target=name, role=role, overlap_start_sample=start,
                                           overlap_end_sample=start + o,
                                           blended_midpoint_step=float(abs(blended[midpoint] - blended[midpoint - 1])))
                            merged["boundaries"].append(metrics)
                        previous = raw
                        last = index == len(entries) - 1
                        ready = n if last else n - plan["overlap_samples"]
                        joined[start:start + ready] = blended[:ready]
                        tail = None if last else blended[ready:].copy()
                    pair_arrays.append(joined)
                    done += 1
                    progress.update(done)
                pair = save_pair(temporary, name, *pair_arrays, mono, padding_limit=0)
                points = [(entry["start_sample"], entry["sample_count"]) for entry in plan["chunks"]]
                presence = stitch_presence(reports, points, plan["overlap_samples"], name, count)
                if presence is not None:
                    pair["presence"] = presence
                pair.update(description=description,
                            elapsed_seconds=sum(r["pairs"][name].get("elapsed_seconds", 0) for r in reports),
                            peak_cuda_allocated_bytes=max(r["pairs"][name].get("peak_cuda_allocated_bytes", 0) for r in reports),
                            peak_cuda_reserved_bytes=max(r["pairs"][name].get("peak_cuda_reserved_bytes", 0) for r in reports))
                pair["real_time_factor"] = pair["elapsed_seconds"] / (count / SAMPLE_RATE)
                merged["pairs"][name] = pair
                del pair_arrays, joined
        del mono
        merged["elapsed_seconds"] = sum(r.get("elapsed_seconds", 0) for r in reports)
        merged["peak_host_rss_bytes"] = max(r.get("peak_host_rss_bytes", 0) for r in reports)
        completed = results / "completed.json"
        if completed.is_file():
            run = json.loads(completed.read_text())
            if not isinstance(run, dict) or not isinstance(run.get("plan_sha256"), str):
                raise ValueError("Malformed run completion record: expected an object with plan_sha256")
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
        plan, mono = _read_plan(plan_file, materialize=True, mono=True)
        assert mono is not None
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
        validate_pairs(report, result.parent, mono, report["codec_hop_samples"])
        return report
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid stitched SAM result: {error}") from error
