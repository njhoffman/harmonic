"""Run a command with a gradient activity bar, preserving logs and exit status."""

from __future__ import annotations

import argparse
from pathlib import Path
import queue
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from harmonic_analysis.terminal import Progress


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        parser.error("a command is required")
    progress = Progress(args.label)
    try:
        process = subprocess.Popen(args.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", bufsize=1)
    except OSError as error:
        progress.finish(False)
        print(error, file=sys.stderr)
        return 127
    events = queue.Queue()

    def forward(source, destination):
        try:
            for line in source:
                events.put((destination, line))
        finally:
            source.close()
            events.put((destination, None))

    threads = [threading.Thread(target=forward, args=(source, destination), daemon=True)
               for source, destination in ((process.stdout, sys.stdout), (process.stderr, sys.stderr))]
    for thread in threads:
        thread.start()
    active = len(threads)
    try:
        while active:
            try:
                destination, line = events.get(timeout=0.1)
                if line is None:
                    active -= 1
                else:
                    progress.clear()
                    destination.write(line)
                    destination.flush()
                    progress.update()
            except queue.Empty:
                progress.update()
        result = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        result = 130
    finally:
        for thread in threads:
            thread.join(timeout=1)
    progress.finish(result == 0)
    return result if result >= 0 else 128 - result


if __name__ == "__main__":
    raise SystemExit(main())
