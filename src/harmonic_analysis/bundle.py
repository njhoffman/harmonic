"""Validate the current mix bundle before registering or reusing local analysis."""

from __future__ import annotations

import json
from pathlib import Path
import re

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from .analysis import BAND_COUNT, HOP_SIZE, PIPELINE, SAMPLE_RATE, SCHEMA_VERSION, WINDOW_SIZE, sha256_file


def read_bundle(path: Path, source_hash: str, *, manifest_hash: str | None = None) -> dict:
    """Check provenance, the supported configuration, and actual Arrow contents.

    Source bytes are checked by the caller. This does not decode audio; first-time
    adoption must additionally compare the manifest's PCM hash to decoded audio.
    """
    try:
        if manifest_hash is not None and sha256_file(path) != manifest_hash:
            raise ValueError("manifest checksum mismatch")
        manifest = json.loads(path.read_text())
        if manifest["schema_version"] != SCHEMA_VERSION or manifest["pipeline"] != PIPELINE:
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
        frames = (count + HOP_SIZE - 1) // HOP_SIZE
        if len(streams) != 1:
            raise ValueError("expected one mix stream")
        stream = streams[0]
        if (stream["name"] != "mix" or stream["artifact"] != "mix.arrow"
                or stream["bands"] != BAND_COUNT or stream["frames"] != frames):
            raise ValueError("invalid mix stream")
        artifact = path.parent / "mix.arrow"
        if sha256_file(artifact) != stream["sha256"]:
            raise ValueError("feature checksum mismatch")
        with ipc.open_file(str(artifact)) as reader:
            table = reader.read_all()
        table.validate(full=True)
        fields = [("sample_index", pa.int64()), ("rms", pa.float32()), ("peak", pa.float32()),
                  ("onset", pa.float32()), ("spectrum", pa.list_(pa.float32(), BAND_COUNT))]
        if table.num_rows != frames or table.column_names != [key for key, _ in fields]:
            raise ValueError("invalid feature dimensions")
        for name, dtype in fields:
            column = table[name].combine_chunks()
            if column.type != dtype or column.null_count:
                raise ValueError(f"invalid {name} column")
            if name == "sample_index":
                if not np.array_equal(column.to_numpy(), np.arange(frames, dtype=np.int64) * HOP_SIZE):
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
        return manifest
    except (OSError, KeyError, TypeError, IndexError, ValueError, pa.ArrowException) as error:
        raise ValueError(f"Invalid analysis bundle {path}: {error}") from error
