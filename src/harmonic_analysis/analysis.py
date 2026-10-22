"""Centered, stereo-power analysis on a single decoded sample timeline."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from .terminal import Progress

SAMPLE_RATE = 48_000
WINDOW_SIZE = 4096
HOP_SIZE = 960
BAND_COUNT = 64
SCHEMA_VERSION = 1
PIPELINE = "harmonic.mix.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_tool(arguments: list[str]) -> bytes:
    result = subprocess.run(arguments, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors="replace").strip())
    return result.stdout


def decode_audio(path: Path) -> np.ndarray:
    # ffmpeg applies codec skip/discard metadata (including MP3 encoder padding).
    # Keep these settings aligned with native/src/audio.cpp.
    raw = run_tool([
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0",
        "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1",
    ])
    samples = np.frombuffer(raw, dtype="<f4")
    if not samples.size or samples.size % 2:
        raise ValueError("The recording did not decode to nonempty stereo audio")
    if not np.isfinite(samples).all():
        raise ValueError("The decoded recording contains nonfinite samples")
    return samples.reshape(-1, 2)


def extract_features(samples: np.ndarray, *, progress: Callable[[int], None] | None = None) -> dict[str, np.ndarray]:
    if samples.ndim != 2 or samples.shape[1] != 2 or not len(samples):
        raise ValueError("Expected nonempty stereo samples shaped (frames, 2)")
    if not np.isfinite(samples).all():
        raise ValueError("Audio contains nonfinite samples")

    centers = np.arange(0, len(samples), HOP_SIZE, dtype=np.int64)
    edges = np.geomspace(20.0, SAMPLE_RATE / 2, BAND_COUNT + 1)
    frequencies = np.fft.rfftfreq(WINDOW_SIZE, 1 / SAMPLE_RATE)
    band_index = np.searchsorted(edges, frequencies, side="right") - 1
    band_index[-1] = BAND_COUNT - 1
    valid = band_index >= 0
    window = np.hanning(WINDOW_SIZE).astype(np.float32)
    power_scale = WINDOW_SIZE * np.sum(window.astype(np.float64) ** 2)
    padded = np.pad(samples, ((WINDOW_SIZE // 2, WINDOW_SIZE // 2), (0, 0)))

    rms = np.empty(len(centers), dtype=np.float32)
    peak = np.empty_like(rms)
    spectrum = np.zeros((len(centers), BAND_COUNT), dtype=np.float32)
    for row, center in enumerate(centers):
        frame = padded[center:center + WINDOW_SIZE]
        # Channel power is averaged, not the waveforms: anti-phase stereo stays visible.
        rms[row] = np.sqrt(np.mean(frame.astype(np.float64) ** 2))
        peak[row] = np.max(np.abs(frame))
        transformed = np.fft.rfft(frame * window[:, None], axis=0)
        power = np.mean(np.abs(transformed) ** 2, axis=1) / power_scale
        power[1:-1] *= 2  # one-sided power; leave DC and Nyquist alone
        band_power = np.bincount(band_index[valid], weights=power[valid], minlength=BAND_COUNT)
        spectrum[row] = np.sqrt(band_power)
        if progress is not None:
            progress(row + 1)

    # Positive spectral flux is an activity measure, not a predicted beat grid.
    onset = np.zeros(len(centers), dtype=np.float32)
    onset[1:] = np.maximum(np.diff(spectrum, axis=0), 0).sum(axis=1)
    return {"sample_index": centers, "rms": rms, "peak": peak,
            "onset": onset, "spectrum": spectrum, "band_edges_hz": edges}


def stats(values: np.ndarray) -> dict[str, float]:
    return {"min": float(values.min()), "max": float(values.max()),
            "p50": float(np.percentile(values, 50)),
            "p95": float(np.percentile(values, 95)),
            "p99": float(np.percentile(values, 99))}


def analyze(source: Path, output: Path, *, show_progress: bool = False) -> Path:
    source, output = source.resolve(), output.resolve()
    if not source.is_file():
        raise ValueError(f"Audio file does not exist: {source}")
    if output.exists():
        raise ValueError(f"Output already exists: {output}. Choose a new bundle directory.")
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise ValueError(f"{tool} is required on PATH")
    with (Progress("Inspecting and decoding audio") if show_progress else nullcontext()):
        source_hash = sha256_file(source)
        metadata = json.loads(run_tool([
            "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source),
        ]))
        samples = decode_audio(source)
    if show_progress:
        print(f"🔵 Decoded {len(samples) / SAMPLE_RATE:.2f}s at {SAMPLE_RATE} Hz; extracting features...",
              file=sys.stderr, flush=True)
    total = (len(samples) + HOP_SIZE - 1) // HOP_SIZE
    with (Progress("Extracting feature frames", total) if show_progress else nullcontext()) as tracker:
        features = extract_features(samples, progress=tracker.update if tracker else None)
    if sha256_file(source) != source_hash:
        raise ValueError("The source changed during analysis; retry with an unchanged file")

    schema = pa.schema([
        pa.field("sample_index", pa.int64(), nullable=False),
        pa.field("rms", pa.float32(), nullable=False),
        pa.field("peak", pa.float32(), nullable=False),
        pa.field("onset", pa.float32(), nullable=False),
        pa.field("spectrum", pa.list_(pa.float32(), BAND_COUNT), nullable=False),
    ], metadata={b"harmonic.schema_version": b"1", b"harmonic.stream": b"mix"})
    table = pa.Table.from_arrays([
        pa.array(features["sample_index"]), pa.array(features["rms"]),
        pa.array(features["peak"]), pa.array(features["onset"]),
        pa.FixedSizeListArray.from_arrays(pa.array(features["spectrum"].ravel()), BAND_COUNT),
    ], schema=schema)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        artifact = temporary / "mix.arrow"
        with pa.OSFile(str(artifact), "wb") as handle:
            with ipc.new_file(handle, schema) as writer:
                writer.write_table(table)
        version = run_tool(["ffmpeg", "-version"]).decode().splitlines()[0]
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pipeline": PIPELINE,
            "source": {"path": str(source), "sha256": source_hash,
                       "pcm_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                       "tags": metadata.get("format", {}).get("tags", {})},
            "audio": {"sample_rate": SAMPLE_RATE, "channels": 2,
                      "sample_count": len(samples), "duration_seconds": len(samples) / SAMPLE_RATE},
            "analysis": {"window_size": WINDOW_SIZE, "window": "hann_symmetric",
                         "hop_size": HOP_SIZE, "frame_offset_samples": 0,
                         "padding": "zeros_centered", "band_edges_hz": features["band_edges_hz"].tolist(),
                         "spectrum_scale": "linear_rms_amplitude", "channel_reduction": "mean_power",
                         "ffmpeg_version": version, "numpy_version": np.__version__,
                         "pyarrow_version": pa.__version__},
            "streams": [{"name": "mix", "artifact": "mix.arrow", "sha256": sha256_file(artifact),
                         "frames": len(features["rms"]), "bands": BAND_COUNT,
                         "stats": {key: stats(features[key]) for key in ("rms", "peak", "onset", "spectrum")}}],
        }
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        # The final directory appears only after the entire bundle is complete.
        os.rename(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return output / "manifest.json"
