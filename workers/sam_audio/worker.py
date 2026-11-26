"""GPU worker for excerpts and full songs. Help and doctor need no model packages."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import resource
import shutil
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
            report["gpu"] = {"name": properties.name, "total_memory_bytes": properties.total_memory,
                             "compute_capability": [properties.major, properties.minor]}
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

    def separate_prompt(name: str, description: str, destination: Path) -> dict:
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
            pair = save_pair(destination, name, target, residual, mono,
                             padding_limit=processor.audio_hop_length - 1)
            pair.update(description=description, elapsed_seconds=elapsed,
                        real_time_factor=elapsed / (len(mono) / 48_000),
                        peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
                        peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved())
            del batch, result, target, residual
            return pair

    with new_directory(output) as temporary:
        checkpoint_dir = session.get("prompt_checkpoint_dir")
        if checkpoint_dir is None:
            for name, description in job["targets"].items():
                pairs[name] = separate_prompt(name, description, temporary)
        else:
            pairs = run_prompt_checkpoints(job, job_hash, session["run_binding_sha256"],
                                           Path(checkpoint_dir), mono, processor.audio_hop_length,
                                           separate_prompt)
            for name in pairs:
                for role in ("target", "residual"):
                    shutil.copyfile(Path(checkpoint_dir) / name / f"{name}-{role}.wav",
                                    temporary / f"{name}-{role}.wav")
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
        if "run_binding_sha256" in session:
            report["run_binding_sha256"] = session["run_binding_sha256"]
        write_json(temporary / "report.json", report)
    return output.resolve() / "report.json"


def run_prompt_checkpoints(job: dict, job_hash: str, run_binding_hash: str, checkpoint_dir: Path,
                           mono, hop: int, separate_prompt) -> dict:
    """Atomically retain and validate each finished target for interrupted song chunks."""
    from harmonic_analysis.sam_jobs import new_directory, validate_pairs, write_json

    if checkpoint_dir.is_symlink():
        raise ValueError(f"Unexpected symlink for prompt checkpoints: {checkpoint_dir}")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    pairs = {}
    for name, description in job["targets"].items():
        path = checkpoint_dir / name
        if path.exists():
            if path.is_symlink() or not path.is_dir():
                raise ValueError(f"Invalid prompt checkpoint path: {path}")
            record_path = path / "checkpoint.json"
            if record_path.is_symlink() or not record_path.is_file():
                raise ValueError(f"Missing prompt checkpoint record: {record_path}")
            if any((path / f"{name}-{role}.wav").is_symlink() for role in ("target", "residual")):
                raise ValueError(f"Invalid prompt checkpoint waveform: {path}")
            record = json.loads(record_path.read_text())
            if (record.get("schema_version") != 1 or record.get("job_sha256") != job_hash
                    or record.get("run_binding_sha256") != run_binding_hash
                    or record.get("target") != name or record.get("description") != description
                    or record.get("pair", {}).get("description") != description):
                raise ValueError(f"Incompatible prompt checkpoint: {path}")
            pair = record["pair"]
            validate_pairs({"pairs": {name: pair}}, path, mono, hop)
        else:
            with new_directory(path) as temporary:
                pair = separate_prompt(name, description, temporary)
                write_json(temporary / "checkpoint.json", {
                    "schema_version": 1, "job_sha256": job_hash,
                    "run_binding_sha256": run_binding_hash, "target": name,
                    "description": description, "pair": pair,
                })
        pairs[name] = pair
    return pairs


def run(job_path: Path, output: Path, *, text_revision: str | None = None) -> Path:
    if output.exists():
        raise ValueError(f"Output already exists: {output}; choose a new directory")
    state = ready_state()
    from harmonic_analysis.sam_chunks import TEXT_REVISION
    from harmonic_analysis.sam_jobs import load_job
    # Excerpt jobs carry no text revision; pin the same commit as song plans so
    # repeated excerpt runs never silently follow the upstream T5 head.
    text_revision = TEXT_REVISION if text_revision is None else text_revision
    job, _ = load_job(job_path)
    began = time.monotonic()
    with model_session(job, state, text_revision) as session:
        return separate_job(job_path, output, session, began=began)


@contextmanager
def song_output_lock(output: Path):
    """Hold one Linux advisory lock for the lifetime of a song invocation."""
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.with_name(f".{output.name}.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"Another SAM worker is using song output {output}") from error
        yield
    finally:
        # Keep the inode so competing invocations always lock the same file.
        os.close(fd)


def run_song(plan_file: Path, output: Path) -> Path:
    invocation_start = time.monotonic()
    output = output.resolve()
    with song_output_lock(output):
        return run_locked_song(plan_file, output, invocation_start=invocation_start)


def clean_song_scratch(output: Path, chunk_names: set[str], target_names: set[str],
                       pending_chunks: set[str]) -> int:
    """Remove abandoned worker files inside a verified, locked song output."""
    chunks = output / "chunks"
    allowed_files = {"report.json"} | {f"{name}-{role}.wav" for name in target_names
                                      for role in ("target", "residual")}
    removed = 0
    if chunks.is_dir():
        for path in chunks.iterdir():
            name = re.fullmatch(r"\.(\d+)-[a-z0-9_]{8}", path.name)
            if (name and name[1] in chunk_names and not path.is_symlink() and path.is_dir()
                    and all(file.name in allowed_files and not file.is_symlink() and file.is_file()
                            for file in path.iterdir())):
                shutil.rmtree(path)
                removed += 1
        for chunk in chunk_names:
            prompt_root = chunks / f".{chunk}-prompts"
            if prompt_root.is_symlink():
                raise ValueError(f"Unexpected symlink for prompt checkpoints: {prompt_root}")
            if not prompt_root.is_dir():
                continue
            for path in prompt_root.iterdir():
                temporary = re.fullmatch(r"\.([a-z][a-z0-9_-]{0,31})-[a-z0-9_]{8}", path.name)
                if (temporary and temporary[1] in target_names and not path.is_symlink() and path.is_dir()
                        and all(file.name in {f"{temporary[1]}-target.wav", f"{temporary[1]}-residual.wav",
                                             "checkpoint.json"}
                                and not file.is_symlink() and file.is_file() for file in path.iterdir())):
                    shutil.rmtree(path)
                    removed += 1
            if chunk not in pending_chunks:
                complete = all(path.name in target_names and not path.is_symlink() and path.is_dir()
                               and all(file.name in {f"{path.name}-target.wav", f"{path.name}-residual.wav",
                                                     "checkpoint.json"}
                                       and not file.is_symlink() and file.is_file()
                                       for file in path.iterdir()) for path in prompt_root.iterdir())
                if complete:
                    shutil.rmtree(prompt_root)
                    removed += 1
    temporary = output / ".completed.json.tmp"
    if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
        raise ValueError(f"Unexpected completion scratch path: {temporary}")
    if temporary.is_file():
        temporary.unlink()
        removed += 1
    return removed


def song_run_binding(plan_hash: str, text_revision: str, state: dict) -> dict:
    import harmonic_analysis
    from harmonic_analysis import sam_chunks, sam_jobs, terminal

    modules = (harmonic_analysis, sam_chunks, sam_jobs, terminal)
    driver_version = Path("/proc/driver/nvidia/version")
    return {
        "plan_sha256": plan_hash,
        "worker_code_sha256": sam_jobs.digest(Path(__file__)),
        "worker_lock_sha256": sam_jobs.digest(Path(__file__).with_name("uv.lock")),
        "text_model_revision": text_revision,
        "imported_code_sha256": {module.__name__: sam_jobs.digest(Path(module.__file__)) for module in modules},
        "runtime_identity": {
            **{key: state.get(key) for key in ("python", "platform", "cuda_runtime", "gpu")},
            "nvidia_driver": driver_version.read_text().strip() if driver_version.is_file() else None,
            "packages": {item.metadata["Name"]: item.version for item in metadata.distributions()},
        },
    }


def run_locked_song(plan_file: Path, output: Path, *, invocation_start: float) -> Path:
    state = ready_state()
    preflight_done = time.monotonic()
    from harmonic_analysis.sam_chunks import plan_path, validate_plan
    from harmonic_analysis.sam_jobs import digest, load_job, new_directory, validate_result, write_json
    plan_file = plan_path(plan_file)
    plan_hash = digest(plan_file)
    plan = validate_plan(plan_file)
    plan_validated = time.monotonic()
    binding = song_run_binding(plan_hash, plan["text_model_revision"], state)
    binding_hash = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    if output.exists():
        if not (output / "run.json").is_file() or json.loads((output / "run.json").read_text()) != binding:
            raise ValueError("Existing song output belongs to a different plan/worker/runtime; choose a new directory")
    else:
        with new_directory(output) as temporary:
            write_json(temporary / "run.json", binding)
    chunk_dir = output / "chunks"
    if chunk_dir.is_symlink():
        raise ValueError(f"Unexpected symlink for song chunks: {chunk_dir}")
    pending = []
    reused = 0
    for index, entry in enumerate(plan["chunks"]):
        destination = chunk_dir / f"{index:06d}"
        if destination.exists():
            report = validate_result(plan_file.parent / entry["job"], destination)
            if (report["worker_code_sha256"] != binding["worker_code_sha256"]
                    or report["worker_lock_sha256"] != binding["worker_lock_sha256"]
                    or report.get("run_binding_sha256") != binding_hash
                    or report["auxiliary_text_model"]["revision"] != plan["text_model_revision"]):
                raise ValueError("Completed chunk has incompatible provenance")
            reused += 1
        else:
            pending.append((entry, destination))
    removed = clean_song_scratch(output, {f"{entry['index']:06d}" for entry in plan["chunks"]},
                                 set(plan["targets"]),
                                 {f"{entry['index']:06d}" for entry, _ in pending})
    if removed:
        print(f"Removed {removed} abandoned SAM scratch paths from {output}", flush=True)
    began = time.monotonic()
    model_ready = began
    chunks_done = began
    if pending:
        first, _ = load_job(plan_file.parent / pending[0][0]["job"])
        with model_session(first, state, plan["text_model_revision"]) as session:
            session["run_binding_sha256"] = binding_hash
            model_ready = time.monotonic()
            with Progress("Separating full-song chunks", len(plan["chunks"])) as progress:
                progress.update(reused)
                for count, (entry, destination) in enumerate(pending, start=reused + 1):
                    checkpoint_dir = chunk_dir / f".{entry['index']:06d}-prompts"
                    session["prompt_checkpoint_dir"] = checkpoint_dir
                    separate_job(plan_file.parent / entry["job"], destination, session, began=time.monotonic())
                    if checkpoint_dir.exists():
                        shutil.rmtree(checkpoint_dir)
                    progress.update(count)
        chunks_done = time.monotonic()
    if digest(plan_file) != plan_hash:
        raise ValueError("Song plan changed during inference")
    # Revalidate all completed artifacts before atomically publishing the completion marker.
    validate_plan(plan_file)
    for entry in plan["chunks"]:
        report = validate_result(plan_file.parent / entry["job"], output / "chunks" / f"{entry['index']:06d}")
        if report["job_sha256"] != entry["sha256"] or report.get("run_binding_sha256") != binding_hash:
            raise ValueError("Completed chunk job or run identity changed")
    validated = time.monotonic()
    timing = {
        "lock_and_preflight": preflight_done - invocation_start,
        "initial_plan_validation": plan_validated - preflight_done,
        "output_setup_reuse_scan_and_cleanup": began - plan_validated,
        "model_setup": model_ready - began,
        "process_pending_chunks": chunks_done - model_ready,
        "final_validation": validated - chunks_done,
    }
    invocation = {"new_chunks": len(pending), "reused_chunks": reused, "elapsed_seconds": validated - began,
                  "elapsed_seconds_through_validation": validated - invocation_start, "timing_seconds": timing}
    summary = {**binding, "run_binding_sha256": binding_hash, "chunks": len(plan["chunks"]), "reused_chunks": reused,
               "new_chunks": len(pending), "elapsed_seconds_this_invocation": invocation["elapsed_seconds"],
               "elapsed_seconds_through_validation": invocation["elapsed_seconds_through_validation"],
               "timing_seconds": timing,
               "runtime": state, "bitwise_determinism_guaranteed": False}
    history = []
    if (output / "completed.json").is_file():
        history = json.loads((output / "completed.json").read_text()).get("invocations", [])
    summary["invocations"] = history + [invocation]
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
    runner.add_argument("--text-revision", help="Auxiliary text-model commit (default: the pinned revision song plans use)")
    song = commands.add_parser("run-song", help="Separate overlapping song chunks with one loaded model; validate and reuse completed chunks")
    song.add_argument("plan", type=Path)
    song.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            report = doctor()
            print(json.dumps(report, indent=2))
            return 0 if report["ready"] else 1
        if args.command == "run-song":
            command_start = time.monotonic()
            path = run_song(args.plan, args.output)
            print(f"🟢 Full-song run completed in {time.monotonic() - command_start:.3f} s")
        else:
            path = run(args.job, args.output, text_revision=args.text_revision)
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
