"""GPU-only short-excerpt worker. Help and doctor work without model packages."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import resource
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from harmonic_analysis import __version__
from harmonic_analysis.terminal import Progress

PACKAGES = ("torch", "torchaudio", "torchvision", "torchcodec", "sam-audio", "huggingface-hub", "numpy")


def versions() -> dict:
    result = {}
    for name in PACKAGES:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def doctor() -> dict:
    installed = versions()
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "packages": installed, "cuda_available": False, "authenticated": False, "ready": False}
    if installed["huggingface-hub"]:
        from huggingface_hub import get_token
        report["authenticated"] = bool(get_token())  # Never serialize a token.
    else:
        cache = Path(os.environ.get("HF_HOME", Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "huggingface"))
        token_file = Path(os.environ.get("HF_TOKEN_PATH", cache / "token"))
        report["authenticated"] = bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or token_file.is_file())
    if installed["torch"]:
        import torch
        report["cuda_available"] = torch.cuda.is_available()
        report["cuda_runtime"] = torch.version.cuda
        if report["cuda_available"]:
            properties = torch.cuda.get_device_properties(0)
            report["gpu"] = {"name": properties.name, "total_memory_bytes": properties.total_memory}
    report["ready"] = bool(all(installed.values()) and report["cuda_available"] and report["authenticated"]
                           and sys.version_info[:2] == (3, 11))
    report["note"] = "Readiness is preflight only; checkpoint access, package imports, memory, and inference must still succeed."
    return report


def ready_state() -> dict:
    state = doctor()
    if not state["ready"]:
        raise ValueError("Worker is not ready. Run doctor; use Python 3.11, just sam-sync, a CUDA GPU, and hf auth login on the GPU host")
    return state


@contextmanager
def model_session(job: dict, state: dict, text_revision: str | None):
    if text_revision is not None and not re.fullmatch(r"[0-9a-f]{40}", text_revision):
        raise ValueError("The auxiliary text revision must be an exact 40-character commit hash")
    import torch
    from huggingface_hub import HfApi, snapshot_download
    from sam_audio import SAMAudio, SAMAudioProcessor
    from harmonic_analysis.sam_jobs import SOURCE_REVISION, digest, write_json

    direct_url = json.loads(metadata.distribution("sam-audio").read_text("direct_url.json") or "{}")
    if direct_url.get("vcs_info", {}).get("commit_id") != SOURCE_REVISION:
        raise ValueError("SAM Audio source revision mismatch; sync the pinned worker environment")
    with Progress("Downloading pinned SAM checkpoint"):
        snapshot = Path(snapshot_download(job["model"]["id"], revision=job["model"]["revision"],
                                          allow_patterns=["config.json", "checkpoint.pt", "LICENSE"]))
        config = json.loads((snapshot / "config.json").read_text())
        text_config = dict(config.get("text_encoder") or {})
        text_id = text_config.get("name", "t5-base")
        info = HfApi().model_info(text_id, revision=text_revision)
        # Resolve the auxiliary text model to an immutable snapshot too. Prefer
        # one weight format instead of fetching duplicate TensorFlow/Flax files.
        names = {item.rfilename for item in info.siblings}
        weights = [name for name in names if name.endswith(".safetensors")]
        if not weights:
            weights = [name for name in names if name.startswith("pytorch_model") and name.endswith(".bin")]
        if not weights:
            raise ValueError("The auxiliary text model has no supported weight files")
        auxiliary = Path(snapshot_download(info.id, revision=info.sha,
            allow_patterns=weights + ["config.json", "model.safetensors.index.json", "pytorch_model.bin.index.json",
                                      "spiece.model", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]))
    model_hashes = {name: digest(snapshot / name) for name in ("config.json", "checkpoint.pt", "LICENSE")}
    text_config["name"] = str(auxiliary)
    config.update(text_encoder=text_config, span_predictor=None, text_ranker=None, visual_ranker=None)
    # Keep the HF cache immutable. The normalized local config disables unused
    # span/ranking models and prevents upstream's revision argument being ignored.
    with tempfile.TemporaryDirectory(prefix="harmonic-sam-model-") as model_directory:
        local_model = Path(model_directory)
        write_json(local_model / "config.json", config)
        (local_model / "checkpoint.pt").symlink_to(snapshot / "checkpoint.pt")
        with Progress("Loading SAM Audio on CUDA"):
            model = SAMAudio.from_pretrained(str(local_model)).eval().to(device="cuda", dtype=torch.float32)
            processor = SAMAudioProcessor.from_pretrained(str(local_model))
        if processor.audio_sampling_rate != 48_000 or model.sample_rate != 48_000:
            raise ValueError("Expected native 48 kHz model audio; refusing an implicit timebase conversion")
        yield {"model": model, "processor": processor, "state": state, "model_hashes": model_hashes,
               "info": info, "config_hash": digest(local_model / "config.json")}


def separate_job(job_path: Path, output: Path, session: dict, *, began: float) -> Path:
    import numpy as np
    import torch
    from harmonic_analysis.sam_jobs import digest, load_job, new_directory, save_pair, write_json
    job_path = job_path.resolve()
    if job_path.is_dir():
        job_path /= "job.json"
    job_hash = digest(job_path)
    job, samples = load_job(job_path)
    if digest(job_path) != job_hash:
        raise ValueError("Job changed while loading")
    model, processor = session["model"], session["processor"]
    state, info, model_hashes = session["state"], session["info"], session["model_hashes"]
    mono = samples.mean(axis=1, dtype=np.float32)
    tensor = torch.from_numpy(samples.T.copy())
    pairs = {}
    with new_directory(output) as temporary:
        for name, description in job["targets"].items():
            with Progress(f"Separating {name}"):
                torch.manual_seed(job["seed"])
                torch.cuda.manual_seed_all(job["seed"])
                batch = processor(audios=[tensor], descriptions=[description]).to("cuda")
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                with torch.inference_mode():
                    result = model.separate(batch, predict_spans=False, reranking_candidates=1,
                        ode_opt={"method": "midpoint", "options": {"step_size": 0.0625}})
                target = result.target[0].detach().float().cpu().numpy()
                residual = result.residual[0].detach().float().cpu().numpy()
                torch.cuda.synchronize()
                elapsed = time.monotonic() - started
                pair = save_pair(temporary, name, target, residual, mono,
                                 padding_limit=processor.audio_hop_length - 1)
                pair.update(description=description, elapsed_seconds=elapsed,
                            real_time_factor=elapsed / (len(mono) / 48_000),
                            peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
                            peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved())
                pairs[name] = pair
                del batch, result, target, residual
        if digest(job_path) != job_hash:
            raise ValueError("Job changed during inference")
        report = {"schema_version": 1, "kind": "harmonic.sam-audio-result.v1", "app_version": __version__,
            "job_sha256": job_hash, "source": job["source"], "start_sample": job["start_sample"],
            "sample_count": job["sample_count"], "sample_rate": 48_000, "channels": 1,
            "codec_hop_samples": processor.audio_hop_length,
            "model": {**job["model"], "files_sha256": model_hashes},
            "auxiliary_text_model": {"id": info.id, "revision": info.sha},
            "normalized_config_sha256": session["config_hash"],
            "settings": job["settings"], "seed": job["seed"], "bitwise_determinism_guaranteed": False,
            "semantics": job["semantics"], "channel_reduction": job["channel_reduction"], "anchors": None,
            "alignment": "start_preserved_and_sample_count_checked; perceptual_latency_unverified",
            "runtime": state, "packages": {item.metadata["Name"]: item.version for item in metadata.distributions()},
            "worker_lock_sha256": digest(Path(__file__).with_name("uv.lock")),
            "worker_code_sha256": digest(Path(__file__)),
            "elapsed_seconds": time.monotonic() - began,
            "peak_host_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "pairs": pairs}
        write_json(temporary / "report.json", report)
    return output.resolve() / "report.json"


def run(job_path: Path, output: Path, *, text_revision: str | None = None) -> Path:
    if output.exists():
        raise ValueError(f"Output already exists: {output}; choose a new directory")
    state = ready_state()
    from harmonic_analysis.sam_jobs import load_job
    job, _ = load_job(job_path)
    began = time.monotonic()
    with model_session(job, state, text_revision) as session:
        return separate_job(job_path, output, session, began=began)


def run_song(plan_file: Path, output: Path) -> Path:
    state = ready_state()
    from harmonic_analysis.sam_chunks import load_plan, plan_path
    from harmonic_analysis.sam_jobs import digest, load_job, new_directory, validate_result, write_json
    plan_file = plan_path(plan_file)
    plan_hash = digest(plan_file)
    plan, samples = load_plan(plan_file)
    del samples
    binding = {"plan_sha256": plan_hash, "worker_code_sha256": digest(Path(__file__)),
               "worker_lock_sha256": digest(Path(__file__).with_name("uv.lock")),
               "text_model_revision": plan["text_model_revision"]}
    output = output.resolve()
    if output.exists():
        if not (output / "run.json").is_file() or json.loads((output / "run.json").read_text()) != binding:
            raise ValueError("Existing song output belongs to a different plan/worker; choose a new directory")
    else:
        with new_directory(output) as temporary:
            write_json(temporary / "run.json", binding)
    pending = []
    reused = 0
    for index, entry in enumerate(plan["chunks"]):
        destination = output / "chunks" / f"{index:06d}"
        if destination.exists():
            report = validate_result(plan_file.parent / entry["job"], destination)
            if (report["worker_code_sha256"] != binding["worker_code_sha256"]
                    or report["worker_lock_sha256"] != binding["worker_lock_sha256"]
                    or report["auxiliary_text_model"]["revision"] != plan["text_model_revision"]):
                raise ValueError("Completed chunk has incompatible provenance")
            reused += 1
        else:
            pending.append((entry, destination))
    began = time.monotonic()
    if pending:
        first, _ = load_job(plan_file.parent / pending[0][0]["job"])
        with model_session(first, state, plan["text_model_revision"]) as session:
            with Progress("Separating full-song chunks", len(plan["chunks"])) as progress:
                progress.update(reused)
                for count, (entry, destination) in enumerate(pending, start=reused + 1):
                    separate_job(plan_file.parent / entry["job"], destination, session, began=time.monotonic())
                    progress.update(count)
    if digest(plan_file) != plan_hash:
        raise ValueError("Song plan changed during inference")
    # Revalidate all completed artifacts before atomically publishing the completion marker.
    load_plan(plan_file)
    for entry in plan["chunks"]:
        report = validate_result(plan_file.parent / entry["job"], output / "chunks" / f"{entry['index']:06d}")
        if report["job_sha256"] != entry["sha256"]:
            raise ValueError("Completed chunk job identity changed")
    summary = {**binding, "chunks": len(plan["chunks"]), "reused_chunks": reused,
               "new_chunks": len(pending), "elapsed_seconds_this_invocation": time.monotonic() - began,
               "runtime": state, "bitwise_determinism_guaranteed": False}
    history = []
    if (output / "completed.json").is_file():
        history = json.loads((output / "completed.json").read_text()).get("invocations", [])
    summary["invocations"] = history + [{"new_chunks": len(pending), "reused_chunks": reused,
                                        "elapsed_seconds": summary["elapsed_seconds_this_invocation"]}]
    temporary = output / ".completed.json.tmp"
    write_json(temporary, summary)
    temporary.replace(output / "completed.json")
    return output / "completed.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report dependencies, CUDA availability, and token presence without downloading weights")
    runner = commands.add_parser("run", help="Separate a prepared excerpt on CUDA; output directory must be new")
    runner.add_argument("job", type=Path)
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--text-revision", help="Pin the auxiliary text-model revision from a previous report")
    song = commands.add_parser("run-song", help="Separate overlapping song chunks with one loaded model; validate and reuse completed chunks")
    song.add_argument("plan", type=Path)
    song.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            report = doctor()
            print(json.dumps(report, indent=2))
            return 0 if report["ready"] else 1
        path = run_song(args.plan, args.output) if args.command == "run-song" else run(args.job, args.output, text_revision=args.text_revision)
        print(f"🟢 Saved separation report: {path}")
        return 0
    except ImportError:
        print("🔴 SAM worker: missing or incompatible inference dependencies; run just sam-sync on the GPU host", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as error:
        print(f"🔴 SAM worker: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
