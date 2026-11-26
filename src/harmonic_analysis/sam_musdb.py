"""MUSDB18 multi-target SAM benchmark: prepare jobs, score results, compare context.

A run directory holds `manifest.json`, full-length decoded reference stems in
`references/<track>/<stem>.npy`, and one job per case in `jobs/<track>-<case>/`.
Every case input is a sum of decoded stems, so the references reproduce each
job exactly on its 48 kHz sample grid. Scoring removes each stream's excerpt
mean (as `sam_benchmark` v2 does), aligns each target to its reference at the
best lag within +/-100 ms, and stays on the original sample grid.

This is the project form of the 2026-11-26 evidence scripts under
`data/aws-gpu/musdb-run/`; it reproduces their scores exactly.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

import numpy as np

from .sam_benchmark import _gains
from .sam_jobs import SAMPLE_RATE, load_job, new_directory, read_wave, save_job, validate_result, write_json

MANIFEST_KIND = "harmonic.musdb-run.v1"
SCORE_KIND = "harmonic.musdb-benchmark.v1"
STEMS = {"drums": 1, "bass": 2, "other": 3, "vocals": 4}  # stream 0 is the mixture
TARGETS = {"vocals_man": "man singing", "vocals_woman": "woman singing",
           "vocals_singing": "singing voice", "drums": "drums playing", "bass": "bass guitar playing"}
EXPECTED = {"vocals_man": "vocals", "vocals_woman": "vocals", "vocals_singing": "vocals",
            "drums": "drums", "bass": "bass"}
SECOND = SAMPLE_RATE
ACTIVE_DB = -40.0  # stem RMS relative to the track's loudest stem second
MAX_LAG = SAMPLE_RATE // 10  # +-100 ms
ABSENT_LIMIT = 0.05
PRESENT_DB = -60.0  # stems quieter than this relative to the input count as absent
WINDOW = SAMPLE_RATE  # 1 s windows for dropout counting
CORE_SECONDS = 20


def decode_stem(path: Path, stream: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", f"0:a:{stream}",
                          "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24].strip("-")


def second_levels(stems: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    count = min(len(s) for s in stems.values()) // SECOND
    rms_values = {name: np.sqrt(np.mean(np.square(s[:count * SECOND].reshape(count, SECOND, 2), dtype=np.float64),
                                        axis=(1, 2))) for name, s in stems.items()}
    peak = max(float(r.max()) for r in rms_values.values())
    return {name: 20 * np.log10(np.maximum(r, 1e-12) / peak) for name, r in rms_values.items()}


def pick_windows(levels: dict[str, np.ndarray]) -> dict[str, int | None]:
    """Pick a fully active 20 s core (with room for 30 s context) and a 10 s instrumental."""
    active = {name: db > ACTIVE_DB for name, db in levels.items()}
    seconds = len(levels["vocals"])
    full = active["vocals"] & active["drums"] & active["bass"]
    # 30 s context window [s-5, s+25) must fit; the 20 s core [s, s+20) is fully active.
    core = next((s for s in range(5, seconds - 25) if full[s:s + CORE_SECONDS].all()), None)
    silent = levels["vocals"] < -60.0
    instrumental = next((s for s in range(seconds - 10)
                         if silent[s:s + 10].all() and active["drums"][s:s + 10].mean() > 0.8), None)
    return {"core": core, "instrumental": instrumental}


def cases_for(windows: dict[str, int | None]) -> dict[str, tuple[list[str], int, int]]:
    """Case name -> (included stems, start sample, seconds)."""
    cases = {}
    if windows["core"] is not None:
        core = windows["core"] * SECOND
        cases = {
            "mix": (list(STEMS), core, 20),
            "vocal-only": (["vocals"], core, 20),
            "accompaniment-only": (["drums", "bass", "other"], core, 20),
            "no-drums": (["bass", "other", "vocals"], core, 20),
            "no-bass": (["drums", "other", "vocals"], core, 20),
            "mix-ctx10a": (list(STEMS), core, 10),
            "mix-ctx10b": (list(STEMS), core + 10 * SECOND, 10),
            "mix-ctx30": (list(STEMS), core - 5 * SECOND, 30),
        }
    if windows["instrumental"] is not None:
        cases["instrumental"] = (list(STEMS), windows["instrumental"] * SECOND, 10)
    return cases


def _pcm_sha256(pcm: np.ndarray) -> str:
    return hashlib.sha256(memoryview(np.ascontiguousarray(pcm)).cast("B")).hexdigest()


def write_track(run: Path, manifest: dict, name: str, member: str, member_sha256: str,
                stems: dict[str, np.ndarray], *, provenance: bool = True) -> int:
    """Write one track's references and jobs into an open run directory; return the job count.

    `provenance=False` omits `source.stems`, reproducing jobs prepared before
    stem provenance existed (used to check archived runs).
    """
    track = slug(name)
    length = min(len(s) for s in stems.values())
    stems = {stem: s[:length] for stem, s in stems.items()}
    refs = run / "references" / track
    refs.mkdir(parents=True, exist_ok=False)
    for stem, samples in stems.items():
        np.save(refs / f"{stem}.npy", samples, allow_pickle=False)
    windows = pick_windows(second_levels(stems))
    manifest["tracks"][track] = {"name": name, "member": member, "member_sha256": member_sha256,
                                 "sample_count": length, "windows": windows}
    identities = {stem: {"member": member, "member_sha256": member_sha256, "stream": STEMS[stem],
                         "pcm_sha256": _pcm_sha256(samples)} for stem, samples in stems.items()}
    cases = cases_for(windows)
    for case, (included, start, seconds) in cases.items():
        full = np.sum([stems[s] for s in included], axis=0, dtype=np.float32).astype("<f4")
        checksum = _pcm_sha256(full)
        source = {"path": f"<musdb18 {name} {'+'.join(included)}>", "sha256": checksum,
                  "pcm_sha256": checksum, "sample_count": length}
        if provenance:
            source["stems"] = {stem: identities[stem] for stem in included}
        job = f"{track}-{case}"
        save_job(np.ascontiguousarray(full[start:start + seconds * SECOND]), run / "jobs" / job,
                 source=source, start_sample=start, targets=TARGETS)
        manifest["jobs"][job] = {"track": track, "case": case, "stems": included,
                                 "start_sample": start, "sample_count": seconds * SECOND}
    return len(cases)


def new_manifest(archive_name: str) -> dict:
    return {"kind": MANIFEST_KIND, "archive": archive_name, "targets": TARGETS, "active_db": ACTIVE_DB,
            "tracks": {}, "jobs": {}}


def prepare(archive: Path, names: list[str], output: Path, *, log=print) -> Path:
    """Decode named tracks from a MUSDB18 zip (`*.stem.mp4` members) into a new run directory."""
    if not names:
        raise ValueError("Name at least one MUSDB18 track")
    manifest = new_manifest(archive.name)
    with zipfile.ZipFile(archive) as bundle:
        members = {Path(m).name.removesuffix(".stem.mp4"): m for m in bundle.namelist() if m.endswith(".stem.mp4")}
        missing = [name for name in names if name not in members]
        if missing:
            raise ValueError("Tracks not in the archive: " + ", ".join(missing))
        if len({slug(name) for name in names}) != len(names):
            raise ValueError("Track names must have distinct slugs")
        with new_directory(output) as run, tempfile.TemporaryDirectory() as scratch:
            for name in names:
                path = Path(bundle.extract(members[name], scratch))
                member_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                stems = {stem: decode_stem(path, index) for stem, index in STEMS.items()}
                path.unlink()
                count = write_track(run, manifest, name, members[name], member_sha, stems)
                windows = manifest["tracks"][slug(name)]["windows"]
                if not count:
                    log(f"🟡 {name}: no usable window; skipped")
                else:
                    log(f"🟢 {name}: windows {windows}, {count} jobs")
            write_json(run / "manifest.json", manifest)
    return output.resolve()


def load_manifest(run: Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text())
    # Runs from the evidence scripts predate the kind field.
    if manifest.get("kind", MANIFEST_KIND) != MANIFEST_KIND or not isinstance(manifest.get("jobs"), dict):
        raise ValueError(f"Not a MUSDB benchmark run: {run}")
    return manifest


def rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if len(x) else 0.0


def centered(x) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x - x.mean()


def best_lag(estimate, reference) -> tuple[int, float | None, float | None]:
    """Lag (samples) maximizing normalized cross-correlation; positive = estimate late.

    A silent estimate or reference has no defined correlation: it reports lag 0
    and null correlations, so a total dropout is scored rather than crashing.
    """
    scale = np.linalg.norm(estimate) * np.linalg.norm(reference)
    if scale == 0:
        return 0, None, None
    n = len(estimate) + len(reference)
    size = 1 << (n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(estimate, size) * np.conj(np.fft.rfft(reference, size)), size)
    lags = np.r_[np.arange(0, MAX_LAG + 1), np.arange(-MAX_LAG, 0)]
    values = corr[lags % size]
    index = int(np.argmax(values))
    return int(lags[index]), float(values[index] / scale), float(corr[0] / scale)


def _reference_stems(run: Path, track: str, cache: dict) -> dict[str, np.ndarray]:
    if track not in cache:
        cache[track] = {s: np.load(run / "references" / track / f"{s}.npy", allow_pickle=False) for s in STEMS}
    return cache[track]


def score_job(run: Path, results: Path, job_name: str, meta: dict, cache: dict) -> dict:
    job_path = run / "jobs" / job_name / "job.json"
    report = validate_result(job_path, results / job_name)
    job, pcm = load_job(job_path)
    track, start, count = meta["track"], meta["start_sample"], meta["sample_count"]
    stems = _reference_stems(run, track, cache)
    full = np.sum([stems[s] for s in meta["stems"]], axis=0, dtype=np.float32)
    if not np.array_equal(full[start:start + count], pcm):
        raise ValueError(f"{job_name}: references do not reproduce the job PCM")
    refs = {s: centered(stems[s][start:start + count].mean(axis=1)) for s in meta["stems"]}
    mono = centered(pcm.mean(axis=1, dtype=np.float32))
    floor = rms(mono) * 10 ** (PRESENT_DB / 20)
    quiet = sorted(s for s, r in refs.items() if rms(r) <= floor)
    refs = {s: r for s, r in refs.items() if rms(r) > floor}
    targets = {}
    for target, expected in EXPECTED.items():
        directory = results / job_name
        for role in ("target", "residual"):
            # validate_result hashed these files; refuse ones replaced since then.
            if report["pairs"][target][role]["sha256"] != hashlib.sha256(
                    (directory / f"{target}-{role}.wav").read_bytes()).hexdigest():
                raise ValueError(f"{job_name}: {target}-{role}.wav changed after validation")
        estimate = np.column_stack([centered(read_wave(directory / f"{target}-{role}.wav"))
                                    for role in ("target", "residual")])
        entry = {"prompt": job["targets"][target], "expected_stem": expected,
                 "target_over_input_rms": rms(estimate[:, 0]) / rms(mono),
                 "gains": _gains(refs, estimate)}
        if expected in refs:
            lag, peak, zero = best_lag(estimate[:, 0], refs[expected])
            entry["timing"] = {"best_lag_samples": lag, "best_lag_ms": lag * 1000 / SAMPLE_RATE,
                               "normalized_correlation_best": peak, "normalized_correlation_zero": zero}
            # estimate[t] ~ reference[t - lag]: align, trimming the non-overlapping edge.
            est = estimate[lag:] if lag > 0 else estimate[:count + lag]
            aligned = {k: (v[:count - lag] if lag > 0 else v[-lag:]) for k, v in refs.items()}
            if lag:
                entry["gains_at_best_lag"] = _gains(aligned, est)
            windows = []  # lag-aligned, so a constant model delay is not counted as dropout
            for offset in range(0, len(est) - WINDOW + 1, WINDOW):
                section = slice(offset, offset + WINDOW)
                if rms(aligned[expected][section]) > 0.01 * rms(aligned[expected]):
                    gain = _gains({k: v[section] for k, v in aligned.items()}, est[section]).get(expected)
                    windows.append({"start_sample": start + offset + max(lag, 0),
                                    "target_gain": gain["target"] if gain else None})
            entry["windows"] = windows
        else:
            entry["absence_check"] = {"limit": ABSENT_LIMIT,
                                      "pass": entry["target_over_input_rms"] <= ABSENT_LIMIT}
        targets[target] = entry
    return {"kind": SCORE_KIND, "job": job_name, **meta,
            "job_sha256": report["job_sha256"], "model": report["model"],
            "auxiliary_text_model": report.get("auxiliary_text_model"),
            "seed": job["seed"], "settings": job["settings"],
            "centering": "excerpt_mean", "input_rms": rms(mono), "quiet_stems": quiet,
            "present_db": PRESENT_DB, "targets": targets}


def summary_row(entry: dict) -> dict:
    return {"expected_gain_in_target": (entry["gains"].get(entry["expected_stem"]) or {}).get("target")
            if entry["gains"] else None,
            "target_over_input_rms": entry["target_over_input_rms"],
            "lag_ms": entry.get("timing", {}).get("best_lag_ms"),
            "expected_gain_at_lag": ((entry.get("gains_at_best_lag") or {})
                                     .get(entry["expected_stem"]) or {}).get("target"),
            "absent_pass": entry.get("absence_check", {}).get("pass"),
            "weak_windows": sum(1 for w in entry.get("windows", []) if (w["target_gain"] or 0) < 0.5),
            "windows": len(entry.get("windows", []))}


def score(run: Path, results: Path, output: Path) -> dict:
    """Score every job in a run; write <job>.json and summary.json into a new directory."""
    manifest = load_manifest(run)
    scores, summary, cache = {}, {"absent_limit": ABSENT_LIMIT, "jobs": {}}, {}
    for job_name, meta in sorted(manifest["jobs"].items()):
        scores[job_name] = score_job(run, results, job_name, meta, cache)
        summary["jobs"][job_name] = {t: summary_row(e) for t, e in scores[job_name]["targets"].items()}
    with new_directory(output) as destination:
        for name, value in scores.items():
            write_json(destination / f"{name}.json", value)
        write_json(destination / "summary.json", summary)
    return summary


def summary_lines(summary: dict) -> list[str]:
    lines = []
    for name, rows in summary["jobs"].items():
        lines.append(name)
        for target, row in rows.items():
            gain = row["expected_gain_in_target"]
            lag = "-" if row["lag_ms"] is None else f"{row['lag_ms']:6.2f}ms"
            absent = "-" if row["absent_pass"] is None else row["absent_pass"]
            lines.append(f"  {target:15} gain {'-' if gain is None else f'{gain:6.3f}'}"
                         f"  ratio {row['target_over_input_rms']:6.3f}  lag {lag}"
                         f"  absent {absent}  weak {row['weak_windows']}/{row['windows']}")
    return lines


def compare_context(run: Path, results: Path) -> dict:
    """Compare 10 s (two windows), 20 s, and 30 s context on the same 20 s core region."""
    manifest = load_manifest(run)
    comparison = {}
    for track, info in manifest["tracks"].items():
        if info["windows"]["core"] is None:
            continue
        core, n = info["windows"]["core"] * SAMPLE_RATE, CORE_SECONDS * SAMPLE_RATE
        stems = {s: np.load(run / "references" / track / f"{s}.npy", allow_pickle=False)[core:core + n]
                 .mean(axis=1).astype(np.float64) for s in STEMS}
        refs = {s: v - v.mean() for s, v in stems.items()}

        def wave(job, target, role, offset):
            return read_wave(results / f"{track}-{job}" / f"{target}-{role}.wav")[offset:offset + n]

        rows = {}
        for target, stem in EXPECTED.items():
            configs = {}
            for label, pieces in {
                "10s": [("mix-ctx10a", 0), ("mix-ctx10b", 0)],
                "20s": [("mix", 0)],
                "30s": [("mix-ctx30", 5 * SAMPLE_RATE)],
            }.items():
                est = np.column_stack([np.concatenate([wave(j, target, r, o) for j, o in pieces])
                                       [:n].astype(np.float64) for r in ("target", "residual")])
                est -= est.mean(axis=0)
                gains = _gains(refs, est)
                configs[label] = {"expected_target_gain": gains[stem]["target"],
                                  "bleed": {k: v["target"] for k, v in gains.items() if k != stem}}
            rows[target] = configs
        comparison[track] = rows
    return comparison
