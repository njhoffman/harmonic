# Harmonic

A local music visualizer with offline, sample-aligned analysis. The first prototype
plays an original recording while displaying its frequency spectrum, RMS envelope,
peak level, and spectral-onset activity. With optional projectM support, it can
also play MilkDrop presets with graph overlays and playback controls.
See [PLAN.md](PLAN.md) for the longer roadmap.
The running task checklist is [TODO.md](TODO.md).

## Common commands

Run `just` to list available recipes. With the [just command runner](https://just.systems/)
installed, the usual workflow is:

```sh
just build
just analyze  # Creates the default Billie Jean bundle; run once per output directory.
just play
just test
just inspect
just audio-check
just render-check
just catalog-add  # Register the existing Billie Jean bundle once.
just catalog
just todo
```

Long terminal commands show gradient activity bars and elapsed time. Feature
extraction and preset rendering show measured progress; builds and other commands
with no known total show activity rather than a percentage. Logs remain visible,
and a failed command keeps its original exit code. Colors are automatic in an
interactive terminal; `FORCE_COLOR=1 just build` enables ANSI explicitly, while
`NO_COLOR=1 just build` disables it and takes precedence over `FORCE_COLOR`.
Captured output keeps colored status markers
and concise start/completion/failure lines without animation.

Parameters can select another recording or bundle:

```sh
just analyze '/path/to/another track.flac' data/analysis/another-track
just play data/analysis/another-track
just render-check data/analysis/another-track 30 data/another-preview.ppm
```

The equivalent direct commands and prerequisites follow below.

## Global Codex checklist command

Install once to make the checklist command available across projects:

```sh
just install-codex-todo
```

The installer adds the `todo` skill under `~/.codex/skills/todo` and the custom
prompt at `~/.codex/prompts/todo.md`, honoring `CODEX_HOME` when set. It preserves
existing customized files. Restart Codex, then invoke `/prompts:todo` or `$todo`
from any project's session. The documented CLI custom-prompt name is
[`/prompts:todo`](https://learn.chatgpt.com/docs/custom-prompts); a bare `/todo`
alias is not registered by this installer.

The command displays the nearest `TODO.md` between the active directory and its
Git root, or the current directory outside Git. It preserves the complete
checklist and adds a completion count. Terminal output uses green completed tasks,
amber pending tasks, and cyan headings; chat uses green/yellow status markers.
It only reads the checklist. `just todo` provides the same terminal view in this
repository without requiring a build or virtual environment.

## Global task viewers

Use the global `todo-status` and `todo-fzf` commands on your PATH. On this
workstation they live in `~/.shell/scripts/`, with both scripts kept together.
These personal tools are no longer shipped in this repository:

```sh
todo-status --pretty          # Incomplete tasks, grouped by section
todo-status --all --pretty    # Include completed tasks
todo-fzf                      # Search/select incomplete tasks
todo-fzf --all                # Search/select both states
todo-status --help
todo-fzf --help
```

Unchecked boxes (`☐`) are dim white, checked boxes (`☑`) are green, and two
spaces separate each checkbox from its priority marker. Pending priorities use
red P1, yellow P2, and dim P3 styling. `NO_COLOR` disables ANSI while preserving
the checkbox icons. The full Markdown checklist remains available through `just todo`.

TODO.md assigns explicit `(p1)`/`(p2)`/`(p3)` priorities and categories to every
task. P1 covers GPU/SAM and real-device playback validation; P2 covers integration
and local improvements; P3 covers later scenes, scaling, and services.
`todo-status --all --check` audits this metadata. Both scripts support
`--version`/`-v`, another file through `-f FILE`, and help without reading a checklist.

The picker keeps incomplete work before completed work in its urgency sort;
Ctrl-S switches to source-file order. **Ctrl-D** checks off the highlighted
task in TODO.md and reloads without closing fzf; it disappears from the default
view and stays checked with `--all`. Already completed tasks stay complete.
Checking requires Python 3. If the file changes externally, completion refuses
the stale selection; press Ctrl-S to refresh first. The prompt is the Nerd Font
list-check icon (`U+F0AE`) followed by one space. Previews and printed selections retain task
line references and completion state. Its optional clipboard helper is tracked
as a portability/verification follow-up in TODO.md. For integrations, `todo-status -l` preserves the original
eight TSV columns and appends `done` (0/1) and the checkbox icon as columns 9/10;
`--all -l` includes completed records.

In this workstation’s tmux session, **Alt-I** opens the picker in a popup from
the current pane’s directory. Press Tab to mark multiple tasks and Enter to paste
the selection into the Codex prompt. Review or edit it, then press Enter again
to submit. Escape cancels. The binding is in `~/.config/tmux/tmux.conf` and uses
`todo-fzf --paste PANE` with bracketed paste; it sends no submission key.

Nine optional integration checks discover these commands on PATH and exercise the
installed global tools. They are skipped when either command is unavailable;
the remaining application checks run normally. Viewer versions are independent
of the Harmonic application version.

## Build

The initial target is Linux with a C++20 compiler, CMake 3.24+, Ninja, pkg-config,
OpenGL development files, FFmpeg development libraries (`libavformat`, `libavcodec`,
`libavutil`, `libswresample`), JsonCpp development files, FFmpeg/ffprobe, and uv.

```sh
uv sync --cache-dir .cache/uv
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DPython3_EXECUTABLE="$PWD/.venv/bin/python"
cmake --build build --parallel 4
```

CMake uses an installed SDL3 3.2+ when available. Otherwise it downloads the pinned
SDL 3.4.18 release into `build/_deps`; it does not install system packages. The first
configure therefore needs network access. If Arrow C++ is not installed, CMake uses
the C++ headers and library included in the project's PyArrow wheel. Keep `.venv`
in place while using that development build. Dependency versions are recorded in
`uv.lock`.

## Analyze and play a recording

```sh
.venv/bin/harmonic-analyze 'data/tracks/Michael Jackson - Billie Jean.mp3' \
  --output data/analysis/billie-jean
./build/harmonic-player data/analysis/billie-jean
```

The output directory must be new: completed bundles are immutable. To reanalyze,
choose another output directory. Analysis and playback stay local. The audio,
analysis bundles, virtual environment, and build outputs are ignored by Git.

Controls:

| Action | Control |
| --- | --- |
| Play/pause | Space or the Play/Pause button |
| Seek | Click the track envelope; Left/Right for 5 seconds; Shift+Left/Right for 30 seconds |
| Restart | Home or Restart |
| Switch absolute/track-normalized display | N or the scale button |
| Cycle combined, preset, and graph views when a preset is loaded | V |
| Adjust visual synchronization | Comma/period: -/+10 ms; Backspace: reset |
| Quit | Escape or close the window |

Positive synchronization offset reads features and preset PCM ahead of the displayed audio time.
An amber envelope marker shows the adjusted feature position. Playback starts
automatically; it pauses at the end and Play restarts it.

Additional options:

```sh
./build/harmonic-player data/analysis/billie-jean --start 30 --offset-ms 20
./build/harmonic-player data/analysis/billie-jean --audio '/new/path/to/the/same.mp3'
./build/harmonic-player --help
```

Both programs support `--help`/`-h` and `--version`/`-v` without an input file:

```sh
.venv/bin/harmonic-analyze -h
.venv/bin/harmonic-analyze -v
./build/harmonic-player -h
./build/harmonic-player -v
```

## Local recording catalog

Register the existing analysis once, then import recordings as needed:

```sh
just catalog-add
just import '/path/to/another track.flac'
just catalog
```

`just catalog-add` defaults to the existing Billie Jean recording/bundle.
`just import` reuses registered analysis for identical source bytes; otherwise it
creates a new immutable bundle under `data/library/bundles/`. The SQLite catalog
defaults to `data/library/catalog.sqlite3`; its references and all media stay local
and are ignored by Git. Audio files remain in their original locations.

Direct commands offer another database, existing-bundle registration, and JSON:

```sh
.venv/bin/harmonic-catalog --database data/library/catalog.sqlite3 \
  import 'data/tracks/Michael Jackson - Billie Jean.mp3' --bundle data/analysis/billie-jean
.venv/bin/harmonic-catalog import '/new/location/the-same-recording.mp3'
.venv/bin/harmonic-catalog list --json
.venv/bin/harmonic-catalog -h
.venv/bin/harmonic-catalog -v
```

The CLI is also available as `.venv/bin/python -m harmonic_analysis.catalog`.
Place `--database` before the subcommand. JSON results go to stdout and progress
goes to stderr. Imports print a ready-to-run player command with `--audio`, so a
relocated identical file works without editing the bundle's original path.

Identity uses source-file SHA-256. Identical copies share one recording and retain
separate location references. Tag edits, alternate encodings, remasters, and
different files get separate identities, even when canonical PCM hashes match.
This conservative first version does not infer song identity from names or merge
timelines using fingerprints. Replacing a file at a known path updates that path's
reference and preserves the previous recording/bundle history.

Every reuse verifies the saved manifest checksum, source bytes, feature checksum,
supported analysis configuration, Arrow types/values, and sample timeline.
Registering an external bundle also decodes the recording and checks its PCM hash;
unchanged, previously verified inputs skip decoding and feature extraction.
The player still checks the current decoder's PCM result before playback. A corrupt
or missing cached bundle produces an error; imports never overwrite completed
analysis. Register another valid bundle with `--bundle` to replace a broken cache
reference. A completed managed bundle left by an interruption before database
registration is validated and recovered on retry.

Catalog schema version 1 stores identities, local file references, and bundle
provenance; dense features remain in Arrow files. The mix cache key is the fixed
`harmonic.mix.v1` pipeline with its validated configuration, separate from the app's
SemVer version. Future configurable/model stages need parameter/revision keys.
Listing shows saved references and current path presence; it does not hash files
or validate bundles. Bulk queues, stage retries, pruning, and a hosted catalog
remain future work.

## Verify

```sh
.venv/bin/python -m unittest discover -s tests -v
./build/harmonic-player data/analysis/billie-jean --inspect
SDL_AUDIODRIVER=dummy ./build/harmonic-player data/analysis/billie-jean --audio-check
./build/harmonic-player data/analysis/billie-jean \
  --start 30 --render-check data/analysis/billie-jean/preview.ppm
```

The inspect mode opens no audio/video device. It checks the recording and feature
checksums, Arrow schema/timebase, and native decoded PCM against the analyzer.
The dummy-audio check exercises advancement, pause, seek, resume, and reaching the
final sample without sound.
The render check uses SDL's offscreen video driver and writes a PPM screenshot;
it requires a working offscreen OpenGL/EGL implementation. These checks do not
replace listening for physical output latency on the actual audio device.

The tests use synthetic tones, silence, impulses, anti-phase stereo, resampled
audio, and invalid bundles. When `build/harmonic-player` exists, the native
integration checks run too; otherwise they are reported as skipped.

## Optional projectM playback and checks

When an installed libprojectM 4 CMake package is available, the build also creates
`harmonic-projectm-check`. Playback integration additionally requires the library's
explicit frame-time and user-framebuffer APIs; CMake probes the actual linked
symbols. `harmonic-player --help` reports whether preset playback is enabled.
Builds without those APIs retain the original graph player. Configure with both
`-DHARMONIC_PROJECTM=OFF -DHARMONIC_PROJECTM_CHECK=OFF` to build without projectM;
either option can also disable its respective feature separately.

Load a local preset for playback:

```sh
just play-preset '/path/to/preset.milk'
just play-preset '/path/to/preset.milk' data/analysis/billie-jean preset
./build/harmonic-player data/analysis/billie-jean --preset '/path/to/preset.milk' \
  --textures '/path/to/textures' --start 30 --view combined
```

The default preset view combines the background with translucent graph panels.
Press **V** to cycle combined → preset → graphs → combined. Preset view keeps the
transport, time, activity readouts, and clickable track envelope. Its animation
and PCM input follow the same corrected sample timeline as the graphs. The
preset image is cached separately from the UI, so pausing freezes feedback while
controls remain responsive. Seeking, changing the timing offset, resizing, and
returning from graph view reset preset feedback. Startup and explicit seek/reset
preparation hold the audio clock until the first preset frame is ready. Resetting
starts a fresh preset history; it does not reconstruct all preceding effects.

Verify the compositor or save a warmed-up playback preview without audio output:

```sh
just compositor-check '/path/to/preset.milk'
./build/harmonic-player data/analysis/billie-jean --preset '/path/to/preset.milk' \
  --compositor-check data/my-compositor-check --start 30
./build/harmonic-player data/analysis/billie-jean --preset '/path/to/preset.milk' \
  --render-check data/combined.ppm --render-frames 120 --start 30
```

The compositor check requires a new output directory. It verifies graph GL-state
restoration, exact paused-frame stability, sample-clock advancement, forward and
backward seek resets, EOF, and resize behavior. It saves combined/preset/graph
PPMs and a JSON report with source, preset, and preview hashes. This mode uses a
controlled timeline and opens no audio device. The test suite also exercises the
real playback path with SDL's dummy audio driver. The owner has confirmed
Billie Jean listening checks on the actual output and desktop controls, including
end-of-track behavior. Quantitative physical-output latency and target-GPU
performance remain unmeasured.
`--render-frames` renders at a 60 Hz timeline from `--start`; the screenshot shows
the last frame. Its default remains a single frame.

The independent preset checker remains available:

```sh
just projectm-check '/path/to/preset.milk'
# Or choose a bundle, new output directory, and frame count:
just projectm-check '/path/to/preset.milk' data/analysis/billie-jean data/my-preset-check 180
./build/harmonic-projectm-check data/analysis/billie-jean \
  --preset '/path/to/preset.milk' --output data/another-preset-check \
  --start 30 --frames 180 --textures '/path/to/textures'
```

Each run requires a new output directory and writes `preview.ppm` and `report.json`.
The checker validates the bundle and decoded PCM, feeds interleaved original-mix
audio in chunks within the library's capacity, and renders 1920×1080 offscreen
without audio output. It supports `--help`/`-h` and `--version`/`-v`. External
presets and textures remain local; they are not bundled with Harmonic.

The report records the library version/revision, OpenGL renderer, preset/audio
hashes, fed PCM frame count, and mean/p50/p95/p99/max completed-render times after
warmup. Timings include PCM submission, rendering, and `glFinish`; they exclude
display presentation and pacing. When supported, explicit projectM frame times
use a 60 Hz timeline independently of render speed. Older libraries use wall-clock
timing with pacing; the report identifies the mode actually used.

The checker rejects missing preset headers, explicit library
load failures, OpenGL errors, and empty/uniform final frames. libprojectM can
recover internally from shader failures without exposing them through its C API;
the report marks shader-fallback detection as unavailable. Visually review output
before claiming preset fidelity. See [PLAN.md](PLAN.md) for
the recorded results and software-rendering performance limits.

## Bundle contract: schema version 1

Each bundle contains `manifest.json` and `mix.arrow`. The manifest records the
original audio path, source-file and canonical-PCM SHA-256 checksums, embedded
format tags, decoded sample count, feature configuration, dependency versions,
artifact checksum, and measured min/max/percentile summaries. A relocated source
must still match its checksum. A different decoder result is rejected rather than
silently attaching the timeline to different PCM.

Canonical audio is stereo float32 at 48 kHz. Both paths select the first audio
stream and use FFmpeg's decoding/resampling, including MP3 skip/discard metadata.
The analyzer runs FFmpeg as a subprocess; the player links the FFmpeg libraries.

Arrow rows have the following non-null fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `sample_index` | int64 | Frame center on the original decoded timeline |
| `rms` | float32 | RMS amplitude across stereo samples in the analysis window |
| `peak` | float32 | Maximum absolute sample amplitude in the window |
| `onset` | float32 | Positive change in band amplitudes; not a beat prediction |
| `spectrum` | fixed-size list of 64 float32 | Linear RMS band amplitudes, with stereo power averaged |

The 4096-sample symmetric Hann spectral windows have zero padding at the edges,
centers at sample 0 and every 960 samples thereafter (50 frames/second), and 64
logarithmic bands spanning 20 Hz–24 kHz. The manifest contains the exact edges.
Frequency resolution is limited by the FFT window; narrow low bands can be empty.
RMS and peak use the unwindowed frame. Continuous features are interpolated during
rendering. Display normalization never changes stored measurements.

The playback clock follows source frames consumed by SDL, interpolates between
device chunks, and subtracts one reported chunk of buffering. Backend/hardware
latency can exceed this estimate; use the offset control for listening checks.
Device removal pauses playback. Automatic recovery across hardware sample-rate
changes and physical-output timestamps remain future work.

## Current scope

This milestone analyzes the original mix, supports optional projectM compositing,
and catalogs local recordings with verified analysis reuse. Stem separation,
lyric display, semantic/mood services, and bulk processing are later steps.
The analyzer and player decode the complete track into memory;
long recordings need a future streaming/chunking pass. The small bitmap UI font
supports ASCII; richer typography and translated metadata need a proper text
renderer. The prototype uses native Linux OpenGL entry points; other platforms
will need a portable GL loader and packaging work.

The owner now has access to [SAM Audio large TV](https://huggingface.co/facebook/sam-audio-large-tv).
An isolated GPU worker is prepared with pinned dependencies, portable excerpt
jobs, target/residual WAVs and provenance reports, and returned-output validation.
Its dependency graph resolves; GPU installation, authentication, inference, and
timing/quality validation remain pending. No checkpoint weights were downloaded
on this laptop. SAM outputs are not yet part of the native player bundle.
Demucs remains an optional comparison/fallback.

```sh
just sam-doctor  # Reports missing prerequisites; downloads no weights.
just sam-prepare '/path/track.flac' data/sam-jobs/my-track 30 10
# On the GPU host: just sam-sync; just sam-auth; just sam-doctor
just sam-run data/sam-jobs/my-track data/sam-results/my-track
just sam-validate data/sam-jobs/my-track data/sam-results/my-track
```

The existing Billie Jean excerpt is at `data/sam-jobs/billie-jean-v0.7.0/`.
See the [SAM worker guide](workers/sam_audio/README.md) for GPU requirements,
job transfer, inference settings, mono/overlap semantics, and dependency license
observations. Tasks remain tracked in [TODO.md](TODO.md).

Original-mix analysis/playback needs no provider credentials. The SAM worker
requires Hugging Face authentication on its GPU host. Review the
licenses of the chosen FFmpeg/SDL/Arrow builds before distributing binaries.

## Versions and approved releases

Use [Semantic Versioning](https://semver.org/) and annotated Git tags named `vX.Y.Z`.
The public interfaces are the analyzer/catalog/SAM/player/checker CLIs and the documented analysis
bundle contract. During 0.x development, new features and incompatible interface
changes increment the minor version; compatible fixes, documentation, and build
maintenance increment the patch version. After 1.0, incompatible changes require
a major version. The bundle's `schema_version` is separate from the application
version and must change when its data contract requires it.

For each approved update:

1. Implement the scoped changes and run `just bump patch` (or `minor`/`major`).
2. Complete the new dated entry in [CHANGELOG.md](CHANGELOG.md).
3. Review and stage the approved files, including new files.
4. Run `just release`.

`just release` verifies version/changelog consistency, requires staged changes
with no remaining unstaged or untracked files, builds and tests, commits, creates
an annotated tag, atomically pushes the current branch and tag to `origin`, and
builds the published commit. Published tags are immutable. If pushing fails after
the local commit/tag, retry that push; do not bump again or move the tag.

`just version` prints the source version; `just check-version` validates all
version fields and the changelog. The built player and installed analyzer also
support `--version`/`-v`. Repository instructions in [AGENTS.md](AGENTS.md) preserve
this workflow for future approved updates.
