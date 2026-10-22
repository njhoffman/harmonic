"""Local recording identities, file locations, and verified immutable bundles."""

from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
import hashlib
import json
from pathlib import Path
import shlex
import sqlite3
import sys

from . import __version__
from .analysis import PIPELINE, SAMPLE_RATE, analyze, decode_audio, sha256_file
from .bundle import read_bundle
from .terminal import Progress, colors_enabled

APPLICATION_ID = 0x4841524D  # HARM; do not mistake another application's SQLite file for ours.
CATALOG_VERSION = 1
DEFAULT_DATABASE = Path("data/library/catalog.sqlite3")
# The pipeline identifies the fixed v1 configuration checked by read_bundle.
# Future configurable/model stages need their own parameter/revision cache keys.
CACHE_KEY = PIPELINE


def connect(database: Path, *, writable: bool) -> sqlite3.Connection:
    database = database.resolve()
    if writable:
        database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database.as_uri() + ("?mode=rwc" if writable else "?mode=ro"), uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if writable:
            connection.execute("BEGIN IMMEDIATE")
        application = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if writable and application == 0 and version == 0 and not tables:
            connection.execute("""CREATE TABLE recordings (
                source_sha256 TEXT PRIMARY KEY, pcm_sha256 TEXT NOT NULL,
                sample_count INTEGER NOT NULL, tags_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
            connection.execute("""CREATE TABLE locations (
                path TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL REFERENCES recordings,
                last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
            connection.execute("""CREATE TABLE analyses (
                manifest_path TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL REFERENCES recordings,
                cache_key TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
            connection.execute("CREATE INDEX analysis_lookup ON analyses(source_sha256, cache_key)")
            connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {CATALOG_VERSION}")
        elif application != APPLICATION_ID or version != CATALOG_VERSION:
            raise ValueError("Not a supported Harmonic catalog (application/schema version mismatch)")
        if writable:
            connection.commit()
        return connection
    except BaseException:
        connection.close()
        raise


def import_track(audio: Path, database: Path = DEFAULT_DATABASE, *, bundle: Path | None = None,
                 show_progress: bool = False) -> dict:
    audio, database = audio.resolve(), database.resolve()
    if not audio.is_file():
        raise ValueError(f"Audio file does not exist: {audio}")
    with (Progress("Checking recording identity") if show_progress else nullcontext()):
        source_hash = sha256_file(audio)
    with closing(connect(database, writable=True)) as connection:
        cached = connection.execute(
            "SELECT * FROM analyses WHERE source_sha256=? AND cache_key=? ORDER BY created_at DESC, manifest_path LIMIT 1",
            (source_hash, CACHE_KEY)).fetchone()
        if bundle is not None:
            manifest_path = bundle.resolve()
            if manifest_path.is_dir():
                manifest_path /= "manifest.json"
            known = connection.execute("SELECT * FROM analyses WHERE manifest_path=?", (str(manifest_path),)).fetchone()
            expected_hash = known["manifest_sha256"] if known else None
            state = "reused" if known else "registered"
        elif cached:
            manifest_path = Path(cached["manifest_path"])
            expected_hash = cached["manifest_sha256"]
            state = "reused"
        else:
            manifest_path = database.parent / "bundles" / source_hash / CACHE_KEY / "manifest.json"
            expected_hash = None
            if manifest_path.parent.exists():
                state = "recovered"
            else:
                analyze(audio, manifest_path.parent, show_progress=show_progress)
                state = "analyzed"
        with (Progress("Verifying analysis bundle") if show_progress else nullcontext()):
            manifest_digest = sha256_file(manifest_path)
            manifest = read_bundle(manifest_path, source_hash, manifest_hash=expected_hash)
            # Previously verified exact file bytes need no second decode. New
            # external/orphaned bundles must demonstrate their PCM provenance.
            if state in ("registered", "recovered"):
                pcm_hash = hashlib.sha256(decode_audio(audio).tobytes()).hexdigest()
                if pcm_hash != manifest["source"]["pcm_sha256"]:
                    raise ValueError("Decoded PCM checksum mismatch; analyze with the current decoder")
            if sha256_file(audio) != source_hash or sha256_file(manifest_path) != manifest_digest:
                raise ValueError("The source or manifest changed during import; retry with unchanged files")
        with connection:
            previous = connection.execute("SELECT * FROM recordings WHERE source_sha256=?", (source_hash,)).fetchone()
            if previous and (previous["pcm_sha256"] != manifest["source"]["pcm_sha256"]
                             or previous["sample_count"] != manifest["audio"]["sample_count"]):
                raise ValueError("This file already has a different canonical PCM identity in the catalog")
            connection.execute("""INSERT INTO recordings(source_sha256,pcm_sha256,sample_count,tags_json)
                VALUES(?,?,?,?) ON CONFLICT(source_sha256) DO NOTHING""",
                (source_hash, manifest["source"]["pcm_sha256"], manifest["audio"]["sample_count"],
                 json.dumps(manifest["source"].get("tags", {}))))
            connection.execute("""INSERT INTO locations(path,source_sha256) VALUES(?,?)
                ON CONFLICT(path) DO UPDATE SET source_sha256=excluded.source_sha256,
                last_seen=strftime('%Y-%m-%dT%H:%M:%fZ','now')""", (str(audio), source_hash))
            connection.execute("""INSERT INTO analyses(manifest_path,source_sha256,cache_key,manifest_sha256)
                VALUES(?,?,?,?) ON CONFLICT(manifest_path) DO NOTHING""",
                (str(manifest_path), source_hash, CACHE_KEY, manifest_digest))
    return {"status": state, "source_sha256": source_hash, "pcm_sha256": manifest["source"]["pcm_sha256"],
            "audio": str(audio), "manifest": str(manifest_path), "database": str(database)}


def list_tracks(database: Path = DEFAULT_DATABASE) -> list[dict]:
    with closing(connect(database, writable=False)) as connection:
        result = []
        for row in connection.execute("SELECT * FROM recordings ORDER BY created_at, source_sha256"):
            locations = [dict(item) for item in connection.execute(
                "SELECT path,last_seen FROM locations WHERE source_sha256=? ORDER BY path", (row["source_sha256"],))]
            bundles = [dict(item) for item in connection.execute(
                "SELECT manifest_path,cache_key,manifest_sha256 FROM analyses WHERE source_sha256=? ORDER BY manifest_path",
                (row["source_sha256"],))]
            result.append({"source_sha256": row["source_sha256"], "pcm_sha256": row["pcm_sha256"],
                           "sample_count": row["sample_count"], "tags": json.loads(row["tags_json"]),
                           "locations": locations, "bundles": bundles})
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="SQLite catalog (default: %(default)s)")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import", help="Reuse verified analysis or analyze a local recording")
    importer.add_argument("audio", type=Path)
    importer.add_argument("--bundle", type=Path, help="Register an existing bundle instead of analyzing")
    importer.add_argument("--json", action="store_true", help="Write machine-readable results to stdout")
    listing = commands.add_parser("list", help="Show recorded identities and bundle/location references")
    listing.add_argument("--json", action="store_true", help="Write machine-readable results to stdout")
    arguments = parser.parse_args()
    try:
        if arguments.command == "import":
            result = import_track(arguments.audio, arguments.database, bundle=arguments.bundle, show_progress=True)
            if arguments.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"🟢 {result['status'].capitalize()} {result['source_sha256'][:12]} · {result['manifest']}")
                print(shlex.join(["./build/harmonic-player", result["manifest"], "--audio", result["audio"]]))
        else:
            tracks = list_tracks(arguments.database)
            if arguments.json:
                print(json.dumps(tracks, indent=2))
            else:
                color = colors_enabled(sys.stdout)
                heading = f"🔵 Local catalog · {len(tracks)} recording(s)"
                print(f"\033[36m{heading}\033[0m" if color else heading)
                for track in tracks:
                    tags = {key.lower(): str(value) for key, value in track["tags"].items()}
                    title = tags.get("title") or (Path(track["locations"][0]["path"]).name if track["locations"] else "Unknown")
                    duration = track["sample_count"] / SAMPLE_RATE
                    line = (f"🟢 {track['source_sha256'][:12]}  {duration:7.2f}s  {title}"
                            f"  · {len(track['locations'])} location(s), {len(track['bundles'])} bundle(s)")
                    print(f"\033[32m{line}\033[0m" if color else line)
                    for item in track["locations"]:
                        marker = "🟢" if Path(item["path"]).is_file() else "🟡"
                        print(f"   {marker} Audio path {'exists' if marker == '🟢' else 'missing'}: {item['path']}")
                    for item in track["bundles"]:
                        print(f"   {item['manifest_path']}")
        return 0
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"🔴 harmonic-catalog: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
