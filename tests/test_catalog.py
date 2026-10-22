import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from harmonic_analysis import __version__
from harmonic_analysis.analysis import analyze, sha256_file
from harmonic_analysis.catalog import CACHE_KEY, import_track, list_tracks


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.audio = self.root / "tone with spaces.wav"
        samples = (12000 * np.sin(2 * np.pi * 440 * np.arange(4800) / 48000)).astype("<i2")
        with wave.open(str(self.audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(samples.tobytes())
        self.database = self.root / "library" / "catalog.sqlite3"

    def bundle(self):
        return analyze(self.audio, self.root / "existing bundle")

    def test_import_reuses_verified_analysis_and_tracks_relocated_bytes(self):
        first = import_track(self.audio, self.database)
        self.assertEqual(first["status"], "analyzed")
        manifest = Path(first["manifest"])
        digest = sha256_file(manifest.parent / "mix.arrow")
        moved = self.root / "moved track.wav"
        shutil.copyfile(self.audio, moved)
        self.audio.unlink()
        with patch("harmonic_analysis.catalog.analyze", side_effect=AssertionError("reanalyzed")), \
                patch("harmonic_analysis.catalog.decode_audio", side_effect=AssertionError("decoded")):
            second = import_track(moved, self.database)
        self.assertEqual(second["status"], "reused")
        self.assertEqual(first["manifest"], second["manifest"])
        self.assertEqual(digest, sha256_file(manifest.parent / "mix.arrow"))
        tracks = list_tracks(self.database)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(len(tracks[0]["locations"]), 2)
        self.assertEqual(len(tracks[0]["bundles"]), 1)
        # The saved manifest can keep its original path; playback uses --audio.
        player = Path("build/harmonic-player").resolve()
        if player.is_file():
            check = subprocess.run([str(player), str(manifest), "--audio", str(moved), "--inspect"],
                                   capture_output=True, text=True, timeout=20)
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_adopts_existing_bundle_without_feature_extraction(self):
        manifest = self.bundle()
        before = manifest.read_bytes()
        with patch("harmonic_analysis.catalog.analyze", side_effect=AssertionError("reanalyzed")):
            result = import_track(self.audio, self.database, bundle=manifest.parent)
        self.assertEqual(result["status"], "registered")
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual(list_tracks(self.database)[0]["bundles"][0]["cache_key"], CACHE_KEY)

    def test_equal_pcm_in_different_file_bytes_is_not_merged(self):
        first = import_track(self.audio, self.database)
        alternative = self.root / "same audio.flac"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(self.audio), str(alternative)], check=True)
        second = import_track(alternative, self.database)
        self.assertEqual(first["pcm_sha256"], second["pcm_sha256"])
        self.assertNotEqual(first["source_sha256"], second["source_sha256"])
        self.assertEqual(second["status"], "analyzed")
        self.assertEqual(len(list_tracks(self.database)), 2)
        # Replacing bytes at a known location updates its reference only.
        shutil.copyfile(alternative, self.audio)
        import_track(self.audio, self.database)
        rows = {item["source_sha256"]: item for item in list_tracks(self.database)}
        self.assertEqual(len(rows[first["source_sha256"]]["locations"]), 0)
        self.assertEqual(len(rows[second["source_sha256"]]["locations"]), 2)

    def test_corrupt_cached_artifact_or_manifest_is_rejected(self):
        result = import_track(self.audio, self.database)
        manifest = Path(result["manifest"])
        artifact = manifest.parent / "mix.arrow"
        original = artifact.read_bytes()
        artifact.write_bytes(original + b"corrupt")
        with self.assertRaisesRegex(ValueError, "feature checksum mismatch"):
            import_track(self.audio, self.database)
        artifact.write_bytes(original)
        manifest.write_text(manifest.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "manifest checksum mismatch"):
            import_track(self.audio, self.database)
        self.assertEqual(len(list_tracks(self.database)), 1)

    def test_external_bundle_checks_source_pcm_and_configuration(self):
        manifest = self.bundle()
        baseline = json.loads(manifest.read_text())
        for field, value, message in (("sha256", "0" * 64, "source checksum"),
                                      ("pcm_sha256", "0" * 64, "PCM checksum")):
            changed = json.loads(json.dumps(baseline))
            changed["source"][field] = value
            manifest.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, message):
                import_track(self.audio, self.database, bundle=manifest)
        changed = json.loads(json.dumps(baseline))
        changed["analysis"]["hop_size"] = 1
        manifest.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "analysis configuration"):
            import_track(self.audio, self.database, bundle=manifest)
        self.assertEqual(list_tracks(self.database), [])

    def test_arrow_timebase_is_checked_even_with_matching_artifact_hash(self):
        manifest = self.bundle()
        artifact = manifest.parent / "mix.arrow"
        with ipc.open_file(str(artifact)) as reader:
            table = reader.read_all()
        table = table.set_column(0, table.schema.field(0), pa.array([1] * table.num_rows, type=pa.int64()))
        with pa.OSFile(str(artifact), "wb") as handle:
            with ipc.new_file(handle, table.schema) as writer:
                writer.write_table(table)
        document = json.loads(manifest.read_text())
        document["streams"][0]["sha256"] = sha256_file(artifact)
        manifest.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "sample indices"):
            import_track(self.audio, self.database, bundle=manifest)
        self.assertEqual(list_tracks(self.database), [])

    def test_failed_registration_can_recover_completed_immutable_bundle(self):
        original = analyze
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("interrupted before registration")
        with patch("harmonic_analysis.catalog.analyze", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "interrupted"):
                import_track(self.audio, self.database)
        self.assertEqual(list_tracks(self.database), [])
        with patch("harmonic_analysis.catalog.analyze", side_effect=AssertionError("reanalyzed")):
            result = import_track(self.audio, self.database)
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(len(list_tracks(self.database)), 1)

    def test_listing_never_creates_database_and_foreign_database_is_untouched(self):
        with self.assertRaises(sqlite3.OperationalError):
            list_tracks(self.database)
        self.assertFalse(self.database.parent.exists())
        foreign = self.root / "other.sqlite3"
        with sqlite3.connect(foreign) as connection:
            connection.execute("CREATE TABLE other (value TEXT)")
        digest = sha256_file(foreign)
        with self.assertRaisesRegex(ValueError, "supported Harmonic catalog"):
            import_track(self.audio, foreign)
        self.assertEqual(sha256_file(foreign), digest)
        import_track(self.audio, self.database)
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA user_version = 999")
        with self.assertRaisesRegex(ValueError, "schema version"):
            list_tracks(self.database)

    def test_cli_help_version_json_and_failure_status(self):
        command = [sys.executable, "-m", "harmonic_analysis.catalog"]
        for flag in ("-h", "--help", "-v", "--version"):
            check = subprocess.run([*command, flag], capture_output=True, text=True, timeout=10)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertFalse(self.database.exists())
            self.assertIn(__version__ if flag in ("-v", "--version") else "--database", check.stdout)
        command += ["--database", str(self.database)]
        environment = {**os.environ, "NO_COLOR": "1", "FORCE_COLOR": "1"}
        imported = subprocess.run([*command, "import", str(self.audio), "--json"],
                                  capture_output=True, text=True, env=environment, timeout=20)
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertEqual(json.loads(imported.stdout)["status"], "analyzed")
        self.assertNotIn("\033[", imported.stderr)
        listing = subprocess.run([*command, "list", "--json"], capture_output=True, text=True, timeout=10)
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(len(json.loads(listing.stdout)), 1)
        bad = subprocess.run([*command, "import", str(self.root / "missing")], capture_output=True, text=True, timeout=10)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("🔴", bad.stderr)


if __name__ == "__main__":
    unittest.main()
