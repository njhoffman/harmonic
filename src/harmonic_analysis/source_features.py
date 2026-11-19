"""Adapt validated SAM WAV pairs to immutable partial-coverage feature streams."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from . import __version__
from .analysis import BAND_COUNT, HOP_SIZE, extract_features, feature_table, sha256_file, stats
from .bundle import SAM_PIPELINE, read_bundle
from .sam_jobs import load_job, new_directory, read_wave, validate_result, write_json
from .terminal import Progress


def build_source_bundle(mix: Path, job: Path, result: Path, output: Path, *, audio: Path | None = None) -> Path:
    mix = mix.resolve()
    if mix.is_dir():
        mix /= "manifest.json"
    job = job.resolve()
    if job.is_dir():
        job /= "job.json"
    result = result.resolve()
    if result.is_dir():
        result /= "report.json"
    output = output.resolve()
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    initial = json.loads(mix.read_text())
    try:
        source = (audio or Path(initial["source"]["path"])).resolve()
    except (KeyError, TypeError) as error:
        raise ValueError("Invalid mix bundle source metadata") from error
    source_hash = sha256_file(source)
    mix_hash, job_hash, report_hash = (sha256_file(p) for p in (mix, job, result))
    manifest = read_bundle(mix, source_hash)
    if manifest["schema_version"] != 1:
        raise ValueError("Use an original schema-1 mix bundle as the adapter input")
    report = validate_result(job, result)
    prepared, _ = load_job(job)
    if (any(report["source"][k] != manifest["source"][k] for k in ("sha256", "pcm_sha256"))
            or report["source"]["sample_count"] != manifest["audio"]["sample_count"]):
        raise ValueError("SAM result and mix bundle have different source identities/timebases")
    frames = (report["sample_count"] + HOP_SIZE - 1) // HOP_SIZE
    with new_directory(output) as temporary:
        shutil.copyfile(mix.parent / "mix.arrow", temporary / "mix.arrow")
        shutil.copyfile(result, temporary / "sam-report.json")
        manifest["schema_version"] = 2
        manifest["pipeline"] = SAM_PIPELINE
        manifest["source"]["path"] = str(source)
        manifest["feature_extraction"] = {"app_version": __version__, "numpy_version": np.__version__,
                                          "pyarrow_version": pa.__version__,
                                          "code_sha256": sha256_file(Path(__file__)),
                                          "mix_manifest_sha256": mix_hash,
                                          "gain_correction": "none", "latency_correction_samples": 0}
        manifest["separation"] = {"artifact": "sam-report.json", "sha256": report_hash}
        with Progress("Extracting source feature frames", frames * 2 * len(report["pairs"])) as progress:
            done = 0
            for name in prepared["targets"]:
                pair = report["pairs"][name]
                for role in ("target", "residual"):
                    wave = result.parent / pair[role]["artifact"]
                    samples = read_wave(wave)
                    if sha256_file(wave) != pair[role]["sha256"]:
                        raise ValueError("Returned waveform changed during feature extraction")
                    features = extract_features(samples[:, None], progress=lambda n: progress.update(done + n))
                    features["sample_index"] += report["start_sample"]
                    stream_name = f"sam.{name}.{role}"
                    artifact = f"sam-{name}-{role}.arrow"
                    table = feature_table(features, stream_name, version=2)
                    with pa.OSFile(str(temporary / artifact), "wb") as handle:
                        with ipc.new_file(handle, table.schema) as writer:
                            writer.write_table(table)
                    manifest["streams"].append({
                        "name": stream_name, "target": name, "role": role, "prompt": pair["description"],
                        "artifact": artifact, "sha256": sha256_file(temporary / artifact),
                        "wave_sha256": pair[role]["sha256"], "frames": frames, "bands": BAND_COUNT,
                        "start_sample": report["start_sample"], "sample_count": report["sample_count"],
                        "channels": 1, "channel_reduction": "mono_no_gain_normalization",
                        "stats": {key: stats(features[key]) for key in ("rms", "peak", "onset", "spectrum")}})
                    done += frames
        write_json(temporary / "manifest.json", manifest)
        # Recheck the actual published artifacts and their provenance, including the mix copy.
        read_bundle(temporary / "manifest.json", source_hash)
        validate_result(job, result)
        if any(sha256_file(p) != h for p, h in ((mix, mix_hash), (job, job_hash), (result, report_hash), (source, source_hash))):
            raise ValueError("Inputs changed during source feature extraction")
    return output / "manifest.json"
