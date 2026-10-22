"""Terminal progress with measured totals or explicitly indeterminate activity."""

from __future__ import annotations

import os
import sys
import time


def colors_enabled(stream) -> bool:
    return ("NO_COLOR" not in os.environ
            and (os.environ.get("FORCE_COLOR", "0") not in ("", "0")
                 or (stream.isatty() and os.environ.get("TERM") != "dumb")))


def gradient(position: int, width: int) -> str:
    stops = ((56, 189, 248), (167, 139, 250), (52, 211, 153))
    fraction = position / max(1, width - 1) * 2
    index = min(1, int(fraction))
    amount = fraction - index
    channels = [round(a + (b - a) * amount) for a, b in zip(stops[index], stops[index + 1])]
    return "\033[38;2;" + ";".join(map(str, channels)) + "m"


class Progress:
    def __init__(self, label: str, total: int | None = None, stream=None):
        self.label, self.total = label, total
        self.stream = stream if stream is not None else sys.stderr
        self.color = colors_enabled(self.stream)
        self.started = time.monotonic()
        self.refreshed = 0.0
        self.done = 0
        self.finished = False
        if self.color:
            self.update(0)
        else:
            print(f"🔵 {label}", file=self.stream, flush=True)

    def clear(self):
        if self.color:
            self.stream.write("\r\033[2K")
            self.stream.flush()

    def update(self, done: int | None = None, *, force: bool = False):
        if done is not None:
            self.done = max(self.done, min(done, self.total)) if self.total else done
        now = time.monotonic()
        if not self.color or (not force and now - self.refreshed < 0.1):
            return
        self.refreshed = now
        width = 24
        filled = int(width * self.done / self.total) if self.total else 0
        pulse = int((now - self.started) * 8) % (width + 4) - 4
        bar = "".join((gradient(index, width) + "━")
                      if (index < filled if self.total else pulse <= index < pulse + 4)
                      else "\033[90m─" for index in range(width))
        count = f"{100 * self.done / self.total:5.1f}% {self.done}/{self.total}" if self.total else "working"
        self.clear()
        self.stream.write(f"🔵 {self.label} {bar}\033[0m {count}  {now - self.started:.1f}s")
        self.stream.flush()

    def finish(self, success: bool = True):
        if self.finished:
            return
        self.finished = True
        if success and self.total:
            self.update(self.total, force=True)
            if self.color:
                self.stream.write("\n")
        else:
            self.clear()
        marker, state = ("🟢", "complete") if success else ("🔴", "failed")
        color = "\033[32m" if success else "\033[31m"
        message = f"{marker} {self.label}: {state} ({time.monotonic() - self.started:.1f}s)"
        print(color + message + "\033[0m" if self.color else message, file=self.stream, flush=True)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.finish(kind is None)
