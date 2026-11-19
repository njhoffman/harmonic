"""Validate mix and partial-coverage SAM feature bundles without model packages."""

from __future__ import annotations

import json
from pathlib import Path
import re

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from .analysis import BAND_COUNT, HOP_SIZE, PIPELINE, SAMPLE_RATE, SCHEMA_VERSION, WINDOW_SIZE, sha256_file
from .sam_jobs import MODEL, MODEL_REVISION, SOURCE_REVISION, SETTINGS, check_targets

SAM_PIPELINE = "harmonic.sam.features.v1"


def separation_report(path: Path, manifest: dict) -> dict:
    record = manifest["separation"]
    if record["artifact"] != "sam-report.json":
        raise ValueError("unexpected separation report path")
    artifact = path.parent / record["artifact"]
    if sha256_file(artifact) != record["sha256"]:
        raise ValueError("separation report checksum mismatch")
    report = json.loads(artifact.read_text())
    if (report["schema_version"] != 1 or report["kind"] != "harmonic.sam-audio-result.v1"
            or report["sample_rate"] != SAMPLE_RATE or report["channels"] != 1
            or report["settings"] != SETTINGS or report["anchors"] is not None
            or report["channel_reduction"] != "arithmetic_mean_to_mono; no_gain_normalization"
            or report["semantics"] != "independent_prompted_target_and_residual_pairs; targets_may_overlap"):
        raise ValueError("unsupported separation provenance")
    if any(report["source"][key] != manifest["source"][key] for key in ("sha256", "pcm_sha256")):
        raise ValueError("separation source identity mismatch")
    if report["source"]["sample_count"] != manifest["audio"]["sample_count"]:
        raise ValueError("separation source length mismatch")
    start, count = report["start_sample"], report["sample_count"]
    if (type(start) is not int or type(count) is not int or start < 0 or not 0 < count <= 30 * SAMPLE_RATE
            or start + count > manifest["audio"]["sample_count"]):
        raise ValueError("invalid separation coverage")
    if any(report["model"][key] != value for key, value in (
            ("id", MODEL), ("revision", MODEL_REVISION), ("source_revision", SOURCE_REVISION))):
        raise ValueError("unsupported separation model")
    for value in (report["job_sha256"], report["worker_code_sha256"], report["worker_lock_sha256"],
                  *report["model"]["files_sha256"].values()):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("invalid separation checksum provenance")
    auxiliary = report["auxiliary_text_model"]
    if not auxiliary["id"] or not re.fullmatch(r"[0-9a-f]{40}", auxiliary["revision"]):
        raise ValueError("invalid auxiliary model provenance")
    check_targets({name: pair["description"] for name, pair in report["pairs"].items()})
    hop = report["codec_hop_samples"]
    if type(hop) is not int or not 0 < hop <= SAMPLE_RATE:
        raise ValueError("invalid separation codec hop")
    if type(report["seed"]) is not int or not 0 <= report["seed"] < 2**32:
        raise ValueError("invalid separation seed")
    if set(report["model"]["files_sha256"]) != {"config.json", "checkpoint.pt", "LICENSE"}:
        raise ValueError("missing separation model hashes")
    for name, pair in report["pairs"].items():
        for role in ("target", "residual"):
            wave = pair[role]
            if (wave["artifact"] != f"{name}-{role}.wav" or not re.fullmatch(r"[0-9a-f]{64}", wave["sha256"])
                    or type(wave["sample_count"]) is not int or wave["sample_count"] != count
                    or type(wave["raw_sample_count"]) is not int
                    or not 0 <= wave["raw_sample_count"] - count < hop
                    or wave["right_trim_samples"] != wave["raw_sample_count"] - count):
                raise ValueError("invalid separation waveform provenance")
    return report


def read_stream(path: Path, stream: dict, *, start: int, count: int, version: int) -> None:
    frames = (count + HOP_SIZE - 1) // HOP_SIZE
    if stream["bands"] != BAND_COUNT or stream["frames"] != frames:
        raise ValueError("invalid feature dimensions")
    artifact = path.parent / stream["artifact"]
    if sha256_file(artifact) != stream["sha256"]:
        raise ValueError("feature checksum mismatch")
    with ipc.open_file(str(artifact)) as reader:
        table = reader.read_all()
    table.validate(full=True)
    metadata = table.schema.metadata or {}
    if (metadata.get(b"harmonic.schema_version") != str(version).encode()
            or metadata.get(b"harmonic.stream") != stream["name"].encode()):
        raise ValueError("feature metadata mismatch")
    fields = [("sample_index", pa.int64()), ("rms", pa.float32()), ("peak", pa.float32()),
              ("onset", pa.float32()), ("spectrum", pa.list_(pa.float32(), BAND_COUNT))]
    if table.num_rows != frames or table.column_names != [key for key, _ in fields]:
        raise ValueError("invalid feature dimensions")
    for name, dtype in fields:
        column = table[name].combine_chunks()
        if column.type != dtype or column.null_count:
            raise ValueError(f"invalid {name} column")
        if name == "sample_index":
            if not np.array_equal(column.to_numpy(), start + np.arange(frames, dtype=np.int64) * HOP_SIZE):
                raise ValueError("invalid sample indices")
        else:
            values = column.values if name == "spectrum" else column
            if values.null_count:
                raise ValueError(f"null {name} values")
            array = values.to_numpy()
            if not np.isfinite(array).all() or (array < 0).any():
                raise ValueError(f"invalid {name} values")
            summaries = stream["stats"][name]
            for key in ("min", "max", "p50", "p95", "p99"):
                value = summaries[key]
                if not isinstance(value, (int, float)) or not np.isfinite(value) or value < 0:
                    raise ValueError(f"invalid {name} statistics")
            # Source features must retain actual absolute levels, including >1 peaks.
            if version == 2:
                from .analysis import stats
                if any(not np.isclose(summaries[key], value, rtol=1e-6, atol=1e-9)
                       for key, value in stats(array).items()):
                    raise ValueError(f"mismatched {name} statistics")


def read_bundle(path: Path, source_hash: str, *, manifest_hash: str | None = None) -> dict:
    """Check identity/configuration/Arrow; the caller verifies source bytes/PCM."""
    try:
        if manifest_hash is not None and sha256_file(path) != manifest_hash:
            raise ValueError("manifest checksum mismatch")
        manifest = json.loads(path.read_text())
        version = manifest["schema_version"]
        if type(version) is not int or (version, manifest["pipeline"]) not in ((SCHEMA_VERSION, PIPELINE), (2, SAM_PIPELINE)):
            raise ValueError("unsupported schema or pipeline")
        source, audio, settings = (manifest[key] for key in ("source", "audio", "analysis"))
        if (not isinstance(source["path"], str) or not source["path"]
                or not isinstance(source.get("tags", {}), dict)
                or any(not isinstance(key, str) or not isinstance(value, str)
                       for key, value in source.get("tags", {}).items())):
            raise ValueError("invalid source metadata")
        if source["sha256"] != source_hash:
            raise ValueError("source checksum mismatch")
        if not re.fullmatch(r"[0-9a-f]{64}", source["pcm_sha256"]):
            raise ValueError("invalid PCM checksum")
        count = audio["sample_count"]
        if (type(count) is not int or count <= 0 or audio["sample_rate"] != SAMPLE_RATE
                or audio["channels"] != 2 or audio["duration_seconds"] != count / SAMPLE_RATE):
            raise ValueError("invalid audio timebase")
        expected = {"window_size": WINDOW_SIZE, "window": "hann_symmetric", "hop_size": HOP_SIZE,
                    "frame_offset_samples": 0, "padding": "zeros_centered",
                    "spectrum_scale": "linear_rms_amplitude", "channel_reduction": "mean_power"}
        if any(settings[key] != value for key, value in expected.items()):
            raise ValueError("unsupported analysis configuration")
        edges = np.asarray(settings["band_edges_hz"], dtype=np.float64)
        if edges.shape != (BAND_COUNT + 1,) or not np.array_equal(
                edges, np.geomspace(20.0, SAMPLE_RATE / 2, BAND_COUNT + 1)):
            raise ValueError("unsupported frequency bands")
        streams = manifest["streams"]
        if not streams or streams[0]["name"] != "mix" or streams[0]["artifact"] != "mix.arrow":
            raise ValueError("invalid mix stream")
        read_stream(path, streams[0], start=0, count=count, version=1)
        if version == 1:
            if len(streams) != 1:
                raise ValueError("expected one mix stream")
        else:
            extraction = manifest["feature_extraction"]
            if (extraction["gain_correction"] != "none" or type(extraction["latency_correction_samples"]) is not int
                    or extraction["latency_correction_samples"] != 0
                    or any(not isinstance(extraction[k], str) or not extraction[k]
                           for k in ("app_version", "numpy_version", "pyarrow_version"))
                    or any(not re.fullmatch(r"[0-9a-f]{64}", extraction[k])
                           for k in ("code_sha256", "mix_manifest_sha256"))):
                raise ValueError("invalid feature extraction provenance")
            report = separation_report(path, manifest)
            expected_streams = {f"sam.{name}.{role}": (name, role)
                                for name in report["pairs"] for role in ("target", "residual")}
            if len(streams) != 1 + len(expected_streams) or {s["name"] for s in streams[1:]} != set(expected_streams):
                raise ValueError("separation stream set mismatch")
            for stream in streams[1:]:
                name, role = expected_streams[stream["name"]]
                pair = report["pairs"][name]
                expected = {"artifact": f"sam-{name}-{role}.arrow", "target": name, "role": role,
                            "start_sample": report["start_sample"], "sample_count": report["sample_count"],
                            "channels": 1, "channel_reduction": "mono_no_gain_normalization",
                            "prompt": pair["description"], "wave_sha256": pair[role]["sha256"]}
                if any(stream[key] != value or type(stream[key]) is not type(value) for key, value in expected.items()):
                    raise ValueError("separation stream provenance mismatch")
                read_stream(path, stream, start=report["start_sample"], count=report["sample_count"], version=2)
        return manifest
    except (OSError, KeyError, TypeError, IndexError, AttributeError, ValueError, pa.ArrowException) as error:
        raise ValueError(f"Invalid analysis bundle {path}: {error}") from error
