import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from harmonic_analysis import frame_perf
from harmonic_analysis.frame_perf import latency_estimate, read_alsa_status, scenarios, summarize

PERIOD_NS = 20_000_000  # 50 Hz


def report(intervals_ms=None, frames=150, seeks=None, refresh=50.0, gpu=None):
    """A synthetic frame report: frames every 20 ms unless an interval is overridden."""
    intervals_ms = intervals_ms or {}
    swap, now = [], 0
    for index in range(frames):
        now += int(intervals_ms.get(index, 20) * 1e6)
        swap.append(now)
    begin = [value - 15_000_000 for value in swap]
    draw = [value - 10_000_000 for value in swap]
    return {
        "kind": "harmonic.frame-report.v1", "frame_count": frames, "view": "graphs", "preset": None,
        "gl": {"renderer": "Test GPU", "swap_interval": 1},
        "display": {"refresh_hz": refresh, "pixel_width": 1920, "pixel_height": 1080, "fullscreen": False},
        "audio": {"sample_rate": 48000, "device_buffer_seconds": 0.016, "driver": "dummy",
                  "device": "dummy/System audio playback device"},
        "offset": {"initial_ms": -20.0, "final_ms": -20.0, "source": "device"},
        "frames": {"begin_ns": begin, "draw_ns": draw, "swap_ns": swap,
                   "gpu_ns": gpu if gpu is not None else [2_000_000] * frames,
                   "position": [index / 50 for index in range(frames)], "queued_frames": [960] * frames},
        "seeks": seeks if seeks is not None else [],
    }


def seek(frame, settle_frame, settle_ms=30.0, present_ms=40.0, to=10.0):
    return {"frame": frame, "settle_frame": settle_frame, "requested_ns": 0, "call_ns": 1_000_000,
            "settle_ns": None if settle_ms is None else int(settle_ms * 1e6),
            "present_ns": None if present_ms is None else int(present_ms * 1e6), "from": 1.0, "to": to}


class SummarizeTests(unittest.TestCase):
    def test_steady_playback_statistics(self):
        summary = summarize(report())
        self.assertEqual(summary["kind"], frame_perf.SUMMARY_KIND)
        self.assertAlmostEqual(summary["period_ms"], 20.0)
        self.assertAlmostEqual(summary["interval"]["p50"], 20.0)
        self.assertAlmostEqual(summary["cpu"]["p50"], 5.0)
        self.assertAlmostEqual(summary["swap"]["p50"], 10.0)
        self.assertAlmostEqual(summary["gpu"]["p99"], 2.0)
        self.assertAlmostEqual(summary["fps"], 50.0)
        self.assertAlmostEqual(summary["sdl_queue"]["p50"], 20.0)
        self.assertEqual(summary["steady"], {"missed_vsync": 0, "stalls": 0})
        self.assertEqual(summary["offset"]["source"], "device")
        self.assertEqual(summary["audio_device"], "dummy/System audio playback device")
        # Frames 0-49 begin within the first second (start-up), so 100 of the
        # 149 intervals, those ending on frames 50-149, are steady playback.
        self.assertEqual(summary["frames"], 150)
        self.assertEqual(summary["steady_frames"], 100)

    def test_missed_vsync_and_stall_thresholds(self):
        # 30 ms is exactly 1.5 periods (not missed); 31 ms is missed; 50 ms is
        # exactly 2.5 periods (missed, not a stall); 51 ms is a stall.
        summary = summarize(report({100: 30, 110: 31, 120: 50, 130: 51}))
        self.assertEqual(summary["steady"], {"missed_vsync": 3, "stalls": 1})
        self.assertAlmostEqual(summary["interval"]["max"], 51)

    def test_startup_and_seek_recovery_are_excluded_from_steady(self):
        seeks = [seek(0, 1, settle_ms=200), seek(80, 82)]
        # A long interval during start-up and one inside seek recovery.
        summary = summarize(report({10: 120, 84: 90}, seeks=seeks))
        self.assertEqual(summary["steady"], {"missed_vsync": 0, "stalls": 0})
        self.assertEqual(summary["all"], {"missed_vsync": 2, "stalls": 2})
        self.assertAlmostEqual(summary["startup"]["settle_ms"], 200)
        self.assertEqual(len(summary["seeks"]), 1)
        self.assertAlmostEqual(summary["seek_settle"]["p50"], 30)
        self.assertAlmostEqual(summary["seek_present"]["max"], 40)
        self.assertAlmostEqual(summary["seek_call"]["p50"], 1)
        self.assertEqual(summary["seeks_unsettled"], 0)

    def test_unsettled_seek_is_counted_and_excludes_one_second(self):
        summary = summarize(report({100: 60}, seeks=[seek(95, None, settle_ms=None, present_ms=None)]))
        self.assertEqual(summary["seeks_unsettled"], 1)
        self.assertIsNone(summary["seek_settle"])
        self.assertEqual(summary["steady"]["stalls"], 0)

    def test_missing_gpu_samples_are_reported(self):
        gpu = [None] * 150
        summary = summarize(report(gpu=gpu))
        self.assertIsNone(summary["gpu"])
        self.assertEqual(summary["gpu_samples_missing"], 150)

    def test_invalid_reports_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Not a frame report"):
            summarize(dict(report(), kind="other"))
        with self.assertRaisesRegex(ValueError, "two presented frames"):
            summarize(report(frames=1))
        with self.assertRaisesRegex(ValueError, "refresh rate"):
            summarize(report(refresh=None))


class OutputChainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def substream(self, card, card_id, state, delay, rate=48000):
        sub = self.root / card / "pcm0p" / "sub0"
        sub.mkdir(parents=True)
        (self.root / card / "id").write_text(card_id + "\n")
        (sub / "status").write_text(f"state: {state}\nowner_pid   : 1\ndelay       : {delay}\navail       : 10\n")
        (sub / "hw_params").write_text(f"access: MMAP_INTERLEAVED\nrate: {rate} ({rate}/1)\n")

    def test_reads_running_playback_delay_only(self):
        self.substream("card1", "Xonar", "RUNNING", 2036)
        self.substream("card0", "HDMI", "SETUP", 512)
        closed = self.root / "card2" / "pcm0p" / "sub0"
        closed.mkdir(parents=True)
        (closed / "status").write_text("closed\n")
        self.assertEqual(read_alsa_status(self.root),
                         [{"device": "Xonar/pcm0p/sub0", "delay_frames": 2036, "rate": 48000}])

    def test_sampler_summary_uses_busiest_device(self):
        sampler = frame_perf.AlsaSampler(root=self.root)
        sampler.samples = [{"device": "A", "delay_frames": 4800, "rate": 48000}] * 3 + \
            [{"device": "B", "delay_frames": 480, "rate": 48000}]
        summary = sampler.summary()
        self.assertEqual(summary["device"], "A")
        self.assertAlmostEqual(summary["delay_ms"]["p50"], 100)
        self.assertEqual(summary["other_devices"], ["B"])
        self.assertIsNone(frame_perf.AlsaSampler(root=self.root).summary())

    def test_latency_estimate_subtracts_display_present(self):
        summary = {"device_buffer_ms": 16.0, "period_ms": 16.68}
        alsa = {"device": "Xonar/pcm0p/sub0", "delay_ms": {"p50": 42.4}}
        estimate = latency_estimate(summary, alsa)
        self.assertAlmostEqual(estimate["alsa_minus_refresh_ms"], 42.4 - 16.68)
        self.assertEqual(estimate["compensated_device_buffer_ms"], 16.0)
        unknown = latency_estimate(summary, None)
        self.assertIsNone(unknown["alsa_delay_ms"])
        self.assertIsNone(unknown["alsa_minus_refresh_ms"])


class DesktopLoadTests(unittest.TestCase):
    def test_pipewire_quantum_is_parsed_from_metadata_output(self):
        output = "Found \"settings\" metadata 31\nupdate: id:0 key:'clock.quantum' value:'1024' type:''"
        self.assertEqual(frame_perf.pipewire_quantum(output), 1024)
        self.assertIsNone(frame_perf.pipewire_quantum(None))
        self.assertIsNone(frame_perf.pipewire_quantum("no metadata"))

    def test_compositors_are_detected_from_process_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for pid, name in ((10, "picom"), (11, "bash"), (12, "picom")):
                (root / str(pid)).mkdir()
                (root / str(pid) / "comm").write_text(name + "\n")
            (root / "self").mkdir()
            names = frame_perf.running_processes(root)
            self.assertEqual(sorted(names), ["bash", "picom", "picom"])
            self.assertEqual(frame_perf.desktop_load(names)["compositors"], ["picom"])


class ScenarioTests(unittest.TestCase):
    def test_each_size_runs_graphs_then_every_preset(self):
        items = scenarios([Path("a.milk"), Path("b c.milk")])
        self.assertEqual([item["name"] for item in items], [
            "1080p-window-graphs", "1080p-window-preset1", "1080p-window-preset2",
            "native-fullscreen-graphs", "native-fullscreen-preset1", "native-fullscreen-preset2"])
        self.assertEqual(items[0]["flags"], ["--size", "1920x1080"])
        self.assertEqual(items[0]["window"], (1920, 1080))
        self.assertEqual(items[5]["flags"], ["--fullscreen", "--preset", "b c.milk"])
        self.assertIsNone(items[5]["window"])

    def test_scenario_failure_requires_exit_report_and_exact_window(self):
        summary = {"pixels": [1920, 1080]}
        self.assertIsNone(frame_perf.scenario_failure({"exit_status": 0, "summary": summary}, (1920, 1080)))
        self.assertIsNone(frame_perf.scenario_failure({"exit_status": 0, "summary": {"pixels": [2560, 1440]}}, None))
        self.assertEqual(frame_perf.scenario_failure({"exit_status": 3}, None), "exit 3")
        self.assertEqual(frame_perf.scenario_failure({"exit_status": 0}, None), "no frame report")
        # A tiling window manager that ignores the requested size invalidates the run.
        tiled = {"exit_status": 0, "summary": {"pixels": [1245, 1348]}}
        self.assertEqual(frame_perf.scenario_failure(tiled, (1920, 1080)), "size 1245x1348 != 1920x1080")

    def test_cli_rejects_missing_presets_and_short_runs(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
            frame_perf.main(["run", "bundle", "--preset", "/nonexistent/preset.milk"])
        self.assertIn("Missing preset files", errors.getvalue())
        with tempfile.NamedTemporaryFile(suffix=".milk") as preset:
            with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
                frame_perf.main(["run", "bundle", "--preset", preset.name, "--duration", "2"])
        self.assertIn("Duration must exceed", errors.getvalue())

    def test_float_window_without_i3_leaves_the_window_alone(self):
        with mock.patch.object(frame_perf.shutil, "which", return_value=None), \
                mock.patch.object(frame_perf.subprocess, "run") as run:
            result = frame_perf.float_window(mock.Mock(), (1920, 1080), {})
        self.assertEqual(result, {"floated": False, "reason": "i3-msg or xdotool is unavailable"})
        run.assert_not_called()

    def test_float_window_targets_the_player_window_by_id(self):
        process = mock.Mock(pid=4242)
        process.poll.return_value = None
        replies = [mock.Mock(returncode=0, stdout="{}"), mock.Mock(returncode=0, stdout=""),
                   mock.Mock(returncode=0, stdout="77\n"), mock.Mock(returncode=0, stdout='[{"success":true}]')]
        with mock.patch.object(frame_perf.shutil, "which", return_value="/usr/bin/x"), \
                mock.patch.object(frame_perf.subprocess, "run", side_effect=replies) as run:
            result = frame_perf.float_window(process, (1920, 1080), {}, poll=0)
        self.assertTrue(result["floated"])
        self.assertEqual(result["window_id"], 77)
        self.assertIn("4242", run.call_args_list[1].args[0])
        self.assertEqual(run.call_args_list[3].args[0][1],
                         "[id=77] floating enable, resize set 1920 px 1080 px, move position center")

    def test_table_marks_failed_scenarios(self):
        results = {"scenarios": [{"name": "x", "exit_status": 1, "failure": "exit 1"}]}
        self.assertIn("exit 1", frame_perf.table(results))

    def test_summarize_command_prints_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.json"
            path.write_text(json.dumps(report()))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(frame_perf.main(["summarize", str(path)]), 0)
            self.assertEqual(json.loads(output.getvalue())["kind"], frame_perf.SUMMARY_KIND)


if __name__ == "__main__":
    unittest.main()
