"""Prepare and score controlled vocal separation cases on the original sample grid."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

from .analysis import decode_audio
from .sam_jobs import (DEFAULT_TARGETS, SAMPLE_RATE, load_job, new_directory, read_wave,
                       save_job, validate_result)

CASES = ("mix", "vocal-only", "accompaniment-only")
WINDOW_SAMPLES = SAMPLE_RATE // 10


def _stems(vocal: Path, accompaniment: Path) -> tuple[np.ndarray, np.ndarray]:
    vocals, backing = decode_audio(vocal), decode_audio(accompaniment)
    if vocals.shape != backing.shape:
        raise ValueError("Reference stems must have equal decoded lengths and aligned starts")
    return vocals, backing


def prepare_cases(vocal: Path, accompaniment: Path, output: Path, *, start: float, duration: float,
                  prompt: str = DEFAULT_TARGETS["vocals"]) -> Path:
    if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or not 0 < duration <= 30:
        raise ValueError("Require a nonnegative start and duration of up to 30 seconds")
    vocals, backing = _stems(vocal, accompaniment)
    first, count = round(start * SAMPLE_RATE), round(duration * SAMPLE_RATE)
    if count < 1 or first + count > len(vocals):
        raise ValueError("The requested excerpt extends beyond the reference stems")
    with np.errstate(over="ignore"):
        mix = vocals + backing
    if not np.isfinite(mix).all():
        raise ValueError("The summed reference PCM exceeds float32 range")
    with new_directory(output) as destination:
        for name, pcm in zip(CASES, (mix, vocals, backing), strict=True):
            # These cases are generated recordings. Their identity derives from
            # canonical PCM, including the uncut reference timeline.
            checksum = hashlib.sha256(memoryview(pcm).cast("B")).hexdigest()
            source = {"path": f"<vocal benchmark {name}>", "sha256": checksum,
                      "pcm_sha256": checksum, "sample_count": len(pcm)}
            save_job(pcm[first:first + count], destination / name, source=source, start_sample=first,
                     targets={"vocals": prompt})
    return output.resolve()


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def _gains(refs: dict[str, np.ndarray], estimates: np.ndarray) -> dict:
    active = {name: samples for name, samples in refs.items() if np.any(samples)}
    if not active:
        return {}
    stems = np.column_stack(list(active.values())).astype(np.float64)
    norms = np.linalg.norm(stems, axis=0)
    gains, _, rank, _ = np.linalg.lstsq(stems / norms, estimates, rcond=1e-3)
    if rank != len(active):
        return dict.fromkeys(active)
    return {name: {"target": float(pair[0]), "residual": float(pair[1])}
            for name, pair in zip(active, gains / norms[:, None], strict=True)}


def score_case(job_path: Path, result_path: Path, case: str, *, vocal: Path | None = None,
               accompaniment: Path | None = None, absent_limit: float = 0.05) -> dict:
    if case not in CASES or not math.isfinite(absent_limit) or not 0 <= absent_limit <= 1:
        raise ValueError("Invalid benchmark case or absent-target limit")
    if case != "mix" and (vocal is not None or accompaniment is not None):
        raise ValueError("Reference stems apply to mixed cases")
    report = validate_result(job_path, result_path)
    job, pcm = load_job(job_path)
    if "vocals" not in report["pairs"]:
        raise ValueError("Expected a vocals target in the SAM result")
    mono = pcm.mean(axis=1, dtype=np.float32)
    if case == "mix":
        if vocal is None or accompaniment is None:
            raise ValueError("Both reference stems are required for a mixed case")
        vocals, backing = _stems(vocal, accompaniment)
        start = job["start_sample"]
        vocals, backing = vocals[start:start + len(pcm)], backing[start:start + len(pcm)]
        if not np.array_equal(vocals + backing, pcm):
            raise ValueError("Reference stems do not reproduce the job PCM on its sample grid")
        refs = {"vocal": vocals.mean(axis=1), "accompaniment": backing.mean(axis=1)}
    else:
        refs = {"vocal" if case == "vocal-only" else "accompaniment": mono}
    if any(_rms(samples) == 0 for samples in refs.values()):
        raise ValueError("Each declared present source must contain audible-channel signal")

    directory = result_path if result_path.is_dir() else result_path.parent
    target, residual = (read_wave(directory / f"vocals-{role}.wav") for role in ("target", "residual"))
    estimates = np.column_stack((target, residual)).astype(np.float64)
    mix_rms = _rms(mono)
    target_rms = _rms(target)
    ratio = target_rms / mix_rms if mix_rms else None
    output = {
        "schema_version": 1, "kind": "harmonic.sam-vocal-benchmark.v1", "case": case,
        "job_sha256": report["job_sha256"], "source": job["source"], "prompt": job["targets"]["vocals"],
        "start_sample": job["start_sample"], "sample_count": len(pcm), "sample_rate": SAMPLE_RATE,
        "model": report["model"], "auxiliary_text_model": report.get("auxiliary_text_model"),
        "seed": job["seed"], "settings": job["settings"],
        "worker_code_sha256": report.get("worker_code_sha256"),
        "worker_lock_sha256": report.get("worker_lock_sha256"),
        "target_sha256": report["pairs"]["vocals"]["target"]["sha256"],
        "residual_sha256": report["pairs"]["vocals"]["residual"]["sha256"],
        "input_rms": mix_rms, "target_rms": target_rms, "residual_rms": _rms(residual),
        "target_over_input_rms": ratio,
        "reference_gains": _gains(refs, estimates),
        "reference_mono_pcm_sha256": {name: hashlib.sha256(samples.tobytes()).hexdigest()
                                      for name, samples in refs.items()},
        "target_error_rms": _rms(estimates[:, 0] - refs.get("vocal", 0)),
        "residual_error_rms": _rms(estimates[:, 1] - refs.get("accompaniment", 0)),
    }
    if case == "accompaniment-only":
        output["absence_check"] = {"target_over_input_rms_limit": absent_limit, "pass": ratio <= absent_limit}
    else:
        vocal_floor = _rms(refs["vocal"]) * 0.01
        windows = []
        for start in range(0, len(pcm), WINDOW_SAMPLES):
            section = slice(start, min(start + WINDOW_SAMPLES, len(pcm)))
            chunk = {name: samples[section] for name, samples in refs.items()}
            if _rms(chunk["vocal"]) > vocal_floor:
                gains = _gains(chunk, estimates[section]).get("vocal")
                windows.append({"start_sample": job["start_sample"] + start,
                                "sample_count": section.stop - start, "vocal_gain": gains})
        output["vocal_windows"] = windows
    return output
