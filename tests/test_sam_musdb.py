import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np

from support import requires

from harmonic_analysis import sam_musdb as musdb
from harmonic_analysis.sam_jobs import SAMPLE_RATE, digest, load_job, new_directory, save_pair, write_json

SECONDS = 32  # the shortest track with a 20 s core and room for 30 s context


def synthetic_stems(seconds=SECONDS, seed=7):
    """Independent noise stems, identical in both channels, all active throughout."""
    rng = np.random.default_rng(seed)
    count = seconds * SAMPLE_RATE
    stems = {}
    for index, stem in enumerate(musdb.STEMS):
        mono = (0.1 * rng.standard_normal(count)).astype("<f4")
        stems[stem] = np.repeat(mono[:, None], 2, axis=1)
    return stems


def build_run(root, stems=None, name="Test Artist - Song"):
    manifest = musdb.new_manifest("synthetic.zip")
    with new_directory(root / "run") as run:
        musdb.write_track(run, manifest, name, f"test/{name}.stem.mp4", "0" * 64, stems or synthetic_stems())
        write_json(run / "manifest.json", manifest)
    return root / "run", manifest


def write_results(run, manifest, results, estimate_for):
    """Result directories as the worker writes them; estimate_for(job, target, mono) -> target wave."""
    for job_name in manifest["jobs"]:
        job_path = run / "jobs" / job_name / "job.json"
        job, pcm = load_job(job_path)
        mono = pcm.mean(axis=1)
        output = results / job_name
        output.mkdir(parents=True)
        pairs = {}
        for target in musdb.TARGETS:
            estimate = np.asarray(estimate_for(job_name, target, mono), "<f4")
            pair = save_pair(output, target, estimate, (mono - estimate).astype("<f4"), mono, padding_limit=0)
            pair["description"] = job["targets"][target]
            pairs[target] = pair
        write_json(output / "report.json", {**job, "kind": "harmonic.sam-audio-result.v1", "channels": 1,
                                            "job_sha256": digest(job_path), "codec_hop_samples": 1,
                                            "pairs": pairs})


class WindowTests(unittest.TestCase):
    def test_core_needs_twenty_active_seconds_with_context_room(self):
        levels = {stem: np.zeros(40) for stem in musdb.STEMS}
        self.assertEqual(musdb.pick_windows(levels), {"core": 5, "instrumental": None})
        levels["bass"][5:12] = -50  # inactive bass pushes the core past it
        self.assertEqual(musdb.pick_windows(levels)["core"], 12)
        short = {stem: np.zeros(30) for stem in musdb.STEMS}
        self.assertIsNone(musdb.pick_windows(short)["core"])

    def test_instrumental_needs_silent_vocals_and_active_drums(self):
        levels = {stem: np.zeros(40) for stem in musdb.STEMS}
        levels["vocals"][:] = -50
        levels["vocals"][20:30] = -70
        windows = musdb.pick_windows(levels)
        self.assertEqual(windows, {"core": None, "instrumental": 20})
        levels["drums"][20:25] = -50
        self.assertIsNone(musdb.pick_windows(levels)["instrumental"])

    def test_cases_cover_context_and_ablations(self):
        cases = musdb.cases_for({"core": 5, "instrumental": 1})
        self.assertEqual(sorted(cases), sorted(["mix", "vocal-only", "accompaniment-only", "no-drums", "no-bass",
                                                "mix-ctx10a", "mix-ctx10b", "mix-ctx30", "instrumental"]))
        self.assertEqual(cases["mix-ctx30"], (list(musdb.STEMS), 0, 30))
        self.assertEqual(cases["mix-ctx10b"][1], 15 * SAMPLE_RATE)
        self.assertEqual(cases["no-drums"][0], ["bass", "other", "vocals"])
        self.assertEqual(musdb.cases_for({"core": None, "instrumental": None}), {})

    def test_slug_matches_archived_track_directories(self):
        self.assertEqual(musdb.slug("Al James - Schoolboy Facination"), "al-james-schoolboy-facin")
        self.assertEqual(musdb.slug("Angels In Amplifiers - I'm Alright"), "angels-in-amplifiers-i-m")


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_jobs_are_stem_sums_with_provenance(self):
        stems = synthetic_stems()
        run, manifest = build_run(self.root, stems)
        track = manifest["tracks"]["test-artist-song"]
        self.assertEqual(track["windows"], {"core": 5, "instrumental": None})
        self.assertEqual(len(manifest["jobs"]), 8)
        meta = manifest["jobs"]["test-artist-song-no-drums"]
        job, pcm = load_job(run / "jobs" / "test-artist-song-no-drums")
        start = meta["start_sample"]
        expected = np.sum([stems[s] for s in meta["stems"]], axis=0, dtype=np.float32)[start:start + len(pcm)]
        self.assertTrue(np.array_equal(pcm, expected))
        self.assertEqual(sorted(job["source"]["stems"]), ["bass", "other", "vocals"])
        identity = job["source"]["stems"]["vocals"]
        self.assertEqual(identity["stream"], 4)
        self.assertEqual(identity["pcm_sha256"], hashlib.sha256(stems["vocals"].tobytes()).hexdigest())
        self.assertTrue(np.array_equal(np.load(run / "references" / "test-artist-song" / "bass.npy"), stems["bass"]))

    def test_without_provenance_matches_the_evidence_script_layout(self):
        manifest = musdb.new_manifest("synthetic.zip")
        with new_directory(self.root / "legacy") as run:
            musdb.write_track(run, manifest, "A - B", "test/A - B.stem.mp4", "0" * 64, synthetic_stems(),
                              provenance=False)
        job, _ = load_job(self.root / "legacy" / "jobs" / "a-b-mix")
        self.assertEqual(sorted(job["source"]), ["path", "pcm_sha256", "sample_count", "sha256"])

    @requires(shutil.which("ffmpeg"), "FFmpeg is required")
    def test_prepare_decodes_a_stem_archive(self):
        stem_file = self.root / "Test Artist - Song.stem.mp4"
        inputs, maps = [], []
        for index, frequency in enumerate((110, 220, 330, 440, 550)):  # mixture, drums, bass, other, vocals
            inputs += ["-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=44100:duration={SECONDS}"]
            maps += ["-map", f"{index}:a"]
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *inputs, *maps, "-c:a", "aac", "-b:a", "96k",
                        str(stem_file)], check=True, timeout=120)
        archive = self.root / "musdb18.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.write(stem_file, f"test/{stem_file.name}")
        log = []
        run = musdb.prepare(archive, ["Test Artist - Song"], self.root / "run", log=log.append)
        manifest = json.loads((run / "manifest.json").read_text())
        self.assertEqual(manifest["kind"], musdb.MANIFEST_KIND)
        track = manifest["tracks"]["test-artist-song"]
        self.assertEqual(track["member"], "test/Test Artist - Song.stem.mp4")
        self.assertEqual(track["member_sha256"], hashlib.sha256(stem_file.read_bytes()).hexdigest())
        self.assertIsNotNone(track["windows"]["core"])
        self.assertIn("8 jobs", log[0])
        bass = np.load(run / "references" / "test-artist-song" / "bass.npy")
        self.assertEqual(bass.shape, (track["sample_count"], 2))
        # The decoded bass stream is the 330 Hz tone, not another stream.
        spectrum = np.abs(np.fft.rfft(bass[SAMPLE_RATE:2 * SAMPLE_RATE, 0]))
        self.assertEqual(int(np.argmax(spectrum)), 330)
        with self.assertRaisesRegex(ValueError, "not in the archive"):
            musdb.prepare(archive, ["Missing"], self.root / "other")
        with self.assertRaisesRegex(ValueError, "already exists"):
            musdb.prepare(archive, ["Test Artist - Song"], self.root / "run")
        self.assertFalse((self.root / "other").exists())


class ScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.stems = synthetic_stems()
        cls.run_dir, cls.manifest = build_run(cls.root, cls.stems)
        cls.lag = 480  # 10 ms: the drums estimate arrives late

        def estimate(job_name, target, mono):
            meta = cls.manifest["jobs"][job_name]
            stem = musdb.EXPECTED[target]
            start, count = meta["start_sample"], meta["sample_count"]
            if stem not in meta["stems"]:
                return np.zeros_like(mono)  # a correctly silent absent target
            reference = cls.stems[stem][start:start + count].mean(axis=1)
            if stem == "drums":
                return np.concatenate([np.zeros(cls.lag, "<f4"), reference[:-cls.lag]])
            return reference

        cls.results = cls.root / "results"
        write_results(cls.run_dir, cls.manifest, cls.results, estimate)
        # Each 20 s job takes seconds to score: score only the jobs the
        # assertions need. The context comparison reads results for all of them.
        scored = cls.root / "scored-run"
        shutil.copytree(cls.run_dir, scored)
        manifest = json.loads((scored / "manifest.json").read_text())
        manifest["jobs"] = {name: meta for name, meta in manifest["jobs"].items()
                            if meta["case"] in ("mix", "no-drums", "no-bass")}
        write_json(scored / "manifest.json", manifest)
        cls.summary = musdb.score(scored, cls.results, cls.root / "scores")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_present_targets_are_extracted_on_the_sample_grid(self):
        row = self.summary["jobs"]["test-artist-song-mix"]["vocals_man"]
        self.assertAlmostEqual(row["expected_gain_in_target"], 1, places=4)
        self.assertEqual(row["lag_ms"], 0)
        self.assertEqual(row["weak_windows"], 0)
        self.assertEqual(row["windows"], 20)  # whole 1 s windows; no lag trims nothing
        self.assertIsNone(row["absent_pass"])

    def test_constant_model_delay_is_measured_and_not_counted_as_dropout(self):
        score = json.loads((self.root / "scores" / "test-artist-song-mix.json").read_text())
        drums = score["targets"]["drums"]
        self.assertEqual(drums["timing"]["best_lag_samples"], self.lag)
        self.assertAlmostEqual(drums["timing"]["best_lag_ms"], 10)
        self.assertAlmostEqual(drums["gains_at_best_lag"]["drums"]["target"], 1, places=4)
        self.assertLess(drums["gains"]["drums"]["target"], 0.5)  # unaligned, the delay looks like loss
        self.assertTrue(all(window["target_gain"] > 0.99 for window in drums["windows"]))
        self.assertEqual(score["kind"], musdb.SCORE_KIND)
        self.assertEqual(score["quiet_stems"], [])

    def test_absent_targets_get_an_absence_check(self):
        row = self.summary["jobs"]["test-artist-song-no-drums"]["drums"]
        self.assertTrue(row["absent_pass"])
        self.assertIsNone(row["lag_ms"])
        self.assertEqual(row["windows"], 0)

    def single_job_run(self, directory, job_name):
        """A copy of the run that holds only one job, so a test can rescore it quickly."""
        copy = Path(directory) / "run"
        shutil.copytree(self.run_dir, copy)
        manifest = json.loads((copy / "manifest.json").read_text())
        manifest["jobs"] = {job_name: manifest["jobs"][job_name]}
        write_json(copy / "manifest.json", manifest)
        return copy, manifest

    def test_a_silent_present_target_is_scored_as_a_dropout(self):
        with tempfile.TemporaryDirectory() as directory:
            run, manifest = self.single_job_run(directory, "test-artist-song-mix")
            results = Path(directory) / "results"
            write_results(run, manifest, results, lambda job, target, mono: np.zeros_like(mono))
            summary = musdb.score(run, results, Path(directory) / "scores")
            row = summary["jobs"]["test-artist-song-mix"]["vocals_man"]
            self.assertEqual(row["expected_gain_in_target"], 0)
            self.assertEqual((row["weak_windows"], row["windows"]), (20, 20))
            score = json.loads((Path(directory) / "scores" / "test-artist-song-mix.json").read_text())
            timing = score["targets"]["vocals_man"]["timing"]
            self.assertEqual(timing, {"best_lag_samples": 0, "best_lag_ms": 0.0,
                                      "normalized_correlation_best": None, "normalized_correlation_zero": None})

    def test_scores_go_to_a_new_directory(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            musdb.score(self.run_dir, self.results, self.root / "scores")
        lines = musdb.summary_lines(self.summary)
        self.assertIn("test-artist-song-mix", lines)

    def test_context_comparison_through_the_command_line(self):
        cli = [sys.executable, "-m", "harmonic_analysis.sam_cli"]
        context = self.root / "context.json"
        for expected in (0, 1):
            result = subprocess.run([*cli, "musdb-context", self.run_dir, self.results, "--output", context],
                                    capture_output=True, text=True, timeout=300)
            self.assertEqual(result.returncode, expected, result.stderr)
        self.assertIn("Refusing to overwrite", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        comparison = json.loads(context.read_text())
        vocals = comparison["test-artist-song"]["vocals_singing"]
        self.assertEqual(sorted(vocals), ["10s", "20s", "30s"])
        for config in vocals.values():
            self.assertAlmostEqual(config["expected_target_gain"], 1, places=4)
            self.assertEqual(sorted(config["bleed"]), ["bass", "drums", "other"])

    def test_references_that_do_not_reproduce_a_job_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "run"
            shutil.copytree(self.run_dir, copy)
            bass = copy / "references" / "test-artist-song" / "bass.npy"
            np.save(bass, -np.load(bass), allow_pickle=False)
            with self.assertRaisesRegex(ValueError, "do not reproduce the job PCM"):
                musdb.score(copy, self.results, Path(directory) / "scores")

    def test_command_line_scores_and_refuses_overwrites(self):
        cli = [sys.executable, "-m", "harmonic_analysis.sam_cli"]
        with tempfile.TemporaryDirectory() as directory:
            run, _ = self.single_job_run(directory, "test-artist-song-no-bass")
            scores = Path(directory) / "scores"
            for expected in (0, 1):
                scored = subprocess.run([*cli, "score-musdb", run, self.results, "--output", scores],
                                        capture_output=True, text=True, timeout=300)
                self.assertEqual(scored.returncode, expected, scored.stderr)
            self.assertIn("already exists", scored.stderr)
            self.assertNotIn("Traceback", scored.stderr)
            summary = json.loads((scores / "summary.json").read_text())
            self.assertEqual(summary["jobs"]["test-artist-song-no-bass"],
                             self.summary["jobs"]["test-artist-song-no-bass"])


if __name__ == "__main__":
    unittest.main()
