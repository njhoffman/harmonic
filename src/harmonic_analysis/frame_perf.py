"""Desktop frame-time and output-latency measurement for the native player.

`summarize` turns a player `--frame-report` into frame-interval, CPU, GPU, and
seek statistics. `run` drives the player through fixed scenarios on a real
display while sampling the ALSA hardware queue, then writes one report, log,
and summary per scenario plus `summary.json` for the whole run.

Output latency here is a software-chain estimate: it adds up the queues the
system reports. Sound leaving the DAC and light leaving the panel are not
measured; that needs external loopback hardware.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

from . import __version__
from .terminal import Progress

SUMMARY_KIND = "harmonic.frame-summary.v1"
RUN_KIND = "harmonic.frame-run.v1"
# Frames after start-up and after each settled seek that are reported apart
# from steady playback (preset compilation and feedback resets land here).
WARMUP_SECONDS = 1.0
SEEK_RECOVERY_SECONDS = 0.25
# An interval longer than this many refresh periods missed at least one vsync;
# one longer than STALL_PERIODS dropped two or more frames in a row.
MISSED_PERIODS = 1.5
STALL_PERIODS = 2.5
DEFAULT_PRESET_ROOT = Path("~/.projectM/presets").expanduser()
# Chosen by shader cost from the local library: no warp/composite shaders, the
# median shader preset, and the heaviest one by shader-line count.
DEFAULT_PRESETS = (
    "milkdrop-original/Milkdrop-Original/BrainStain-Blackwidow.milk",
    "projectm-classic/bltc201/Rovastar + Loadus + Geiss - Tone-mapped FractalDrop 7c.milk",
    "en-d/Fumbling Foo/Fumbling_Foo__En_D_Martin_-_The_Lifeforce_of_the_music_v6b.milk",
)
# Windowed runs need an exact size. Tiling window managers ignore the request,
# so under i3 the runner floats the player's own window at that size.
SIZES = (("1080p-window", ("--size", "1920x1080"), (1920, 1080)),
         ("native-fullscreen", ("--fullscreen",), None))


def _stats(values) -> dict | None:
    array = np.asarray([value for value in values if value is not None], dtype=float)
    if array.size == 0:
        return None
    p50, p95, p99 = np.percentile(array, [50, 95, 99])
    return {"count": int(array.size), "mean": float(array.mean()), "p50": float(p50),
            "p95": float(p95), "p99": float(p99), "max": float(array.max())}


def summarize(report: dict) -> dict:
    """Summarize one frame report. Times are milliseconds."""
    if report.get("kind") != "harmonic.frame-report.v1":
        raise ValueError(f"Not a frame report: {report.get('kind')!r}")
    count = int(report["frame_count"])
    if count < 2:
        raise ValueError("A frame report needs at least two presented frames")
    frames = report["frames"]
    begin = np.asarray(frames["begin_ns"][:count], dtype=float)
    drawn = np.asarray(frames["draw_ns"][:count], dtype=float)
    swapped = np.asarray(frames["swap_ns"][:count], dtype=float)
    refresh = report["display"].get("refresh_hz")
    if not refresh or refresh <= 0:
        raise ValueError("The report has no display refresh rate")
    period = 1000.0 / refresh

    # Frames whose interval falls in start-up or seek recovery are excluded.
    excluded = np.zeros(count, dtype=bool)
    excluded[begin < begin[0] + WARMUP_SECONDS * 1e9] = True
    seeks, startup = [], None
    for index, seek in enumerate(report["seeks"]):
        first = int(seek["frame"])
        settled = seek.get("settle_frame")
        if settled is None:
            last = next((i for i in range(first, count) if begin[i] >= begin[min(first, count - 1)] + 1e9), count)
        else:
            recover_until = begin[min(int(settled), count - 1)] + SEEK_RECOVERY_SECONDS * 1e9
            last = int(np.searchsorted(begin, recover_until, side="right"))
        excluded[first:last + 1] = True
        item = {
            "from": seek["from"], "to": seek["to"],
            "call_ms": seek["call_ns"] / 1e6,
            "settle_ms": None if seek.get("settle_ns") is None else seek["settle_ns"] / 1e6,
            "present_ms": None if seek.get("present_ns") is None else seek["present_ns"] / 1e6,
        }
        if index == 0 and first == 0:
            startup = item  # The initial seek includes start-up and first preset compile.
        else:
            seeks.append(item)

    intervals = np.diff(swapped) / 1e6
    steady = ~excluded[1:]
    steady_intervals = intervals[steady]
    cpu = (drawn - begin) / 1e6
    swap = (swapped - drawn) / 1e6
    gpu = [None if value is None else value / 1e6 for value in frames["gpu_ns"][:count]]
    keep = ~excluded
    queued = np.asarray(frames["queued_frames"][:count], dtype=float)
    rate = report["audio"]["sample_rate"]
    span = (swapped[-1] - swapped[0]) / 1e9

    def counts(values):
        return {"missed_vsync": int(np.sum(values > MISSED_PERIODS * period)),
                "stalls": int(np.sum(values > STALL_PERIODS * period))}

    unsettled = sum(1 for seek in seeks if seek["settle_ms"] is None)
    return {
        "kind": SUMMARY_KIND,
        "view": report["view"],
        "preset": report.get("preset"),
        "gl_renderer": report["gl"]["renderer"],
        "swap_interval": report["gl"].get("swap_interval"),
        "refresh_hz": refresh,
        "period_ms": period,
        "pixels": [report["display"]["pixel_width"], report["display"]["pixel_height"]],
        "fullscreen": report["display"]["fullscreen"],
        "frames": count,
        "steady_frames": int(steady.sum()),
        "fps": (count - 1) / span if span > 0 else None,
        "interval": _stats(steady_intervals),
        "interval_all": _stats(intervals),
        "steady": counts(steady_intervals),
        "all": counts(intervals),
        "cpu": _stats(cpu[keep]),
        "swap": _stats(swap[keep]),
        "gpu": _stats([value for value, use in zip(gpu, keep) if use]),
        "gpu_samples_missing": int(sum(value is None for value in gpu)),
        "startup": startup,
        "seeks": seeks,
        "seek_settle": _stats(seek["settle_ms"] for seek in seeks),
        "seek_present": _stats(seek["present_ms"] for seek in seeks),
        "seek_call": _stats(seek["call_ms"] for seek in seeks),
        "seeks_unsettled": unsettled,
        "sdl_queue": _stats(queued[keep] * 1000 / rate),
        "device_buffer_ms": report["audio"]["device_buffer_seconds"] * 1000,
        "audio_driver": report["audio"]["driver"],
        "audio_device": report["audio"].get("device"),
        "offset": report.get("offset"),
    }


def read_alsa_status(root: Path = Path("/proc/asound")) -> list[dict]:
    """Return running ALSA playback substreams with their hardware queue delay."""
    running = []
    for status in sorted(root.glob("card*/pcm*p/sub*/status")):
        try:
            text = status.read_text()
            params = (status.parent / "hw_params").read_text()
        except OSError:
            continue
        if "state: RUNNING" not in text:
            continue
        delay = re.search(r"^delay\s*:\s*(-?\d+)", text, re.MULTILINE)
        rate = re.search(r"^rate:\s*(\d+)", params, re.MULTILINE)
        if not delay or not rate:
            continue
        card = status.parents[2]
        try:
            card_id = (card / "id").read_text().strip()
        except OSError:
            card_id = card.name
        running.append({"device": f"{card_id}/{status.parent.parent.name}/{status.parent.name}",
                        "delay_frames": int(delay.group(1)), "rate": int(rate.group(1))})
    return running


@dataclass
class AlsaSampler:
    """Samples ALSA playback delay on a background thread while a scenario plays."""
    interval: float = 0.1
    root: Path = Path("/proc/asound")
    samples: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self._stop.wait(self.interval):
            for item in read_alsa_status(self.root):
                self.samples.append(item)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()

    def summary(self) -> dict | None:
        if not self.samples:
            return None
        devices = {}
        for item in self.samples:
            devices.setdefault(item["device"], []).append(item["delay_frames"] * 1000 / item["rate"])
        # Report the busiest device: the one carrying this playback.
        device, delays = max(devices.items(), key=lambda pair: len(pair[1]))
        return {"device": device, "delay_ms": _stats(delays), "other_devices": sorted(set(devices) - {device})}


def latency_estimate(summary: dict, alsa: dict | None) -> dict:
    """Report the queues the system exposes; this is not an offset measurement.

    The player's clock already subtracts the SDL device buffer. The ALSA queue
    behind the sound server is not compensated, and the picture needs at least
    one refresh after its swap. `alsa_minus_refresh_ms` subtracts the second
    from the first. Both are minimums: the sound server and DAC add to the
    audio side, and a compositor adds frames to the picture side. The
    difference therefore bounds neither the size nor the sign of the real
    offset. Calibrate by ear or with a loopback.
    """
    estimate = {"compensated_device_buffer_ms": summary["device_buffer_ms"],
                "display_present_ms": summary["period_ms"], "alsa_delay_ms": None,
                "alsa_minus_refresh_ms": None,
                "basis": "reported minimums only; not a bound on the audio/picture offset"}
    if alsa and alsa["delay_ms"]:
        estimate["alsa_device"] = alsa["device"]
        estimate["alsa_delay_ms"] = alsa["delay_ms"]
        estimate["alsa_minus_refresh_ms"] = alsa["delay_ms"]["p50"] - summary["period_ms"]
    return estimate


def _command(arguments: list[str]) -> str | None:
    if not shutil.which(arguments[0]):
        return None
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def pipewire_quantum(output: str | None) -> int | None:
    """Parse `pw-metadata -n settings 0 clock.quantum` output into frames."""
    match = re.search(r"key:'clock.quantum' value:'(\d+)'", output or "")
    return int(match.group(1)) if match else None


COMPOSITORS = ("picom", "compton", "xcompmgr", "mutter", "kwin_x11", "kwin_wayland", "gnome-shell", "xfwm4", "marco")


def running_processes(root: Path = Path("/proc")) -> list[str]:
    names = []
    for comm in root.glob("[0-9]*/comm"):
        try:
            names.append(comm.read_text().strip())
        except OSError:
            continue
    return names


def desktop_load(processes: list[str]) -> dict:
    """Name the compositor and GPU clients sharing the display: results depend on them."""
    return {
        "compositors": sorted({name for name in processes if name in COMPOSITORS}),
        "gpu_utilization": _command(["nvidia-smi", "--query-gpu=utilization.gpu,pstate,clocks.gr",
                                     "--format=csv,noheader"]),
        "gpu_clients": _command(["nvidia-smi", "--query-compute-apps=name", "--format=csv,noheader"]),
    }


def environment(display: str) -> dict:
    env = dict(os.environ, DISPLAY=display)
    xrandr = None
    if shutil.which("xrandr"):
        result = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, env=env, timeout=10)
        if result.returncode == 0:
            xrandr = [line.strip() for line in result.stdout.splitlines() if " connected" in line or "*" in line]
    return {
        "display": display, "xrandr": xrandr, "kernel": platform.release(),
        "gpu": _command(["nvidia-smi", "--query-gpu=name,driver_version,pstate,temperature.gpu",
                         "--format=csv,noheader"]),
        "pipewire_quantum": pipewire_quantum(_command(["pw-metadata", "-n", "settings", "0", "clock.quantum"])),
        "default_sink": _command(["pactl", "get-default-sink"]),
        "desktop_load": desktop_load(running_processes()),
    }


def scenarios(presets: list[Path]) -> list[dict]:
    items = []
    for size, flags, window in SIZES:
        items.append({"name": f"{size}-graphs", "flags": list(flags), "preset": None, "window": window})
        for index, preset in enumerate(presets, 1):
            items.append({"name": f"{size}-preset{index}", "flags": [*flags, "--preset", str(preset)],
                          "preset": str(preset), "window": window})
    return items


def float_window(process: subprocess.Popen, size: tuple[int, int], env: dict,
                 timeout: float = 30.0, poll: float = 0.05) -> dict:
    """Float only this process's window at an exact size under i3.

    A window rule would also float ordinary player sessions, so the window is
    found by PID and changed by its X window id. Other window managers are left
    alone; the size check after the run catches any that ignore the request.
    """
    if not shutil.which("i3-msg") or not shutil.which("xdotool"):
        return {"floated": False, "reason": "i3-msg or xdotool is unavailable"}
    version = subprocess.run(["i3-msg", "-t", "get_version"], capture_output=True, text=True, env=env, timeout=10)
    if version.returncode != 0:
        return {"floated": False, "reason": "i3 is not running on this display"}
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if process.poll() is not None:
            return {"floated": False, "reason": "the player exited before its window appeared"}
        found = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(process.pid)],
                               capture_output=True, text=True, env=env, timeout=10)
        windows = found.stdout.split()
        if windows:
            width, height = size
            command = f"[id={windows[0]}] floating enable, resize set {width} px {height} px, move position center"
            reply = subprocess.run(["i3-msg", command], capture_output=True, text=True, env=env, timeout=10)
            try:
                results = json.loads(reply.stdout)
            except json.JSONDecodeError:
                results = []
            floated = reply.returncode == 0 and bool(results) and all(item.get("success") for item in results)
            return {"floated": floated, "window_id": int(windows[0]),
                    "after_seconds": round(time.monotonic() - started, 3), "i3_reply": results}
        time.sleep(poll)
    return {"floated": False, "reason": f"no window appeared within {timeout:g} s"}


def scenario_failure(entry: dict, window: tuple[int, int] | None) -> str | None:
    """Why a scenario's measurement is unusable, or None when it is valid."""
    if entry["exit_status"] != 0:
        return f"exit {entry['exit_status']}"
    summary = entry.get("summary")
    if not summary:
        return "no frame report"
    if window and summary["pixels"] != list(window):
        return f"size {summary['pixels'][0]}x{summary['pixels'][1]} != {window[0]}x{window[1]}"
    return None


def run(player: Path, bundle: Path, output: Path, presets: list[Path], display: str,
        duration: float, seek_every: float, start: float) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    items = scenarios(presets)
    env = dict(os.environ, DISPLAY=display)
    results = {"kind": RUN_KIND, "version": __version__,
               "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "player": str(player), "bundle": str(bundle), "duration": duration,
               "seek_every": seek_every, "start": start, "environment": environment(display),
               "scenarios": []}
    with Progress("Measuring desktop frame times", len(items)) as progress:
        for done, item in enumerate(items):
            report = output / f"{item['name']}.json"
            log = output / f"{item['name']}.log"
            command = [str(player), str(bundle), *item["flags"], "--start", str(start),
                       "--exit-after", str(duration), "--seek-every", str(seek_every),
                       "--frame-report", str(report)]
            window = None
            with AlsaSampler() as sampler, log.open("w") as handle:
                process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, env=env)
                try:
                    if item["window"]:
                        window = float_window(process, item["window"], env)
                    returncode = process.wait(timeout=duration + 120)
                except BaseException:
                    process.kill()
                    process.wait()
                    raise
            entry = {"name": item["name"], "preset": item["preset"], "command": command,
                     "exit_status": returncode, "log": str(log), "report": str(report), "window": window}
            if returncode == 0 and report.is_file():
                summary = summarize(json.loads(report.read_text()))
                alsa = sampler.summary()
                entry.update(summary=summary, alsa=alsa, latency=latency_estimate(summary, alsa))
            entry["failure"] = scenario_failure(entry, item["window"])
            results["scenarios"].append(entry)
            progress.clear()
            state = "🟢" if entry["failure"] is None else f"🔴 {entry['failure']}"
            print(f"{state} {item['name']} ({done + 1}/{len(items)})", file=sys.stderr, flush=True)
            (output / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
            progress.update(done + 1)
        failed = [entry["name"] for entry in results["scenarios"] if entry["failure"]]
        progress.finish(not failed)
    return results


def _fmt(value, digits=1):
    return "-" if value is None else f"{value:.{digits}f}"


def table(results: dict) -> str:
    rows = [("scenario", "px", "fps", "int p50", "int p99", "int max", "missed", "stalls",
             "cpu p99", "gpu p99", "seek p50", "seek max", "alsa p50", "alsa-refr")]
    for entry in results["scenarios"]:
        summary = entry.get("summary")
        if not summary:
            rows.append((entry["name"], entry.get("failure") or f"exit {entry['exit_status']}", *["-"] * 12))
            continue
        latency = entry["latency"]
        rows.append((
            entry["name"], "x".join(map(str, summary["pixels"])), _fmt(summary["fps"]),
            _fmt(summary["interval"]["p50"], 2), _fmt(summary["interval"]["p99"], 2),
            _fmt(summary["interval"]["max"], 1), str(summary["steady"]["missed_vsync"]),
            str(summary["steady"]["stalls"]), _fmt(summary["cpu"]["p99"], 2),
            _fmt(summary["gpu"]["p99"] if summary["gpu"] else None, 2),
            _fmt(summary["seek_settle"]["p50"] if summary["seek_settle"] else None),
            _fmt(summary["seek_present"]["max"] if summary["seek_present"] else None),
            _fmt(latency["alsa_delay_ms"]["p50"] if latency["alsa_delay_ms"] else None),
            _fmt(latency["alsa_minus_refresh_ms"])))
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(cell.ljust(width) for cell, width in zip(row, widths)) for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harmonic_analysis.frame_perf", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Measure the player on a real display")
    run_parser.add_argument("bundle", type=Path)
    run_parser.add_argument("--player", type=Path, default=Path("build/harmonic-player"))
    run_parser.add_argument("--output", type=Path)
    run_parser.add_argument("--preset", type=Path, action="append",
                            help=f"Preset to measure (repeatable; default: three under {DEFAULT_PRESET_ROOT})")
    run_parser.add_argument("--display", default=os.environ.get("DISPLAY", ":0"))
    run_parser.add_argument("--duration", type=float, default=60)
    run_parser.add_argument("--seek-every", type=float, default=10)
    run_parser.add_argument("--start", type=float, default=30)
    summary_parser = commands.add_parser("summarize", help="Summarize one player frame report")
    summary_parser.add_argument("report", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.command == "summarize":
        print(json.dumps(summarize(json.loads(arguments.report.read_text())), indent=2))
        return 0
    presets = arguments.preset or [DEFAULT_PRESET_ROOT / path for path in DEFAULT_PRESETS]
    missing = [str(path) for path in presets if not path.is_file()]
    if missing:
        parser.error("Missing preset files (pass --preset): " + ", ".join(missing))
    if arguments.duration <= 2 * WARMUP_SECONDS or arguments.seek_every <= 0:
        parser.error("Duration must exceed 2 seconds and seek-every must be positive")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = arguments.output or Path("data/perf") / f"v{__version__}-{stamp}"
    results = run(arguments.player.resolve(), arguments.bundle.resolve(), output, presets,
                  arguments.display, arguments.duration, arguments.seek_every, arguments.start)
    print(table(results))
    failed = [entry["name"] for entry in results["scenarios"] if entry["failure"]]
    marker = "🔴" if failed else "🟢"
    message = f"{len(failed)} scenario(s) failed: {', '.join(failed)}" if failed else "All scenarios completed"
    print(f"{marker} {message}; results in {output / 'summary.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
