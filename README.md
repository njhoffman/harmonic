# Harmonic

A local music visualizer with offline, sample-aligned analysis. The first prototype
plays an original recording while displaying its frequency spectrum, RMS envelope,
peak level, and spectral-onset activity. See [PLAN.md](PLAN.md) for the longer roadmap.

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
```

Parameters can select another recording or bundle:

```sh
just analyze '/path/to/another track.flac' data/analysis/another-track
just play data/analysis/another-track
just render-check data/analysis/another-track 30 data/another-preview.ppm
```

The equivalent direct commands and prerequisites follow below.

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
| Adjust visual synchronization | Comma/period: -/+10 ms; Backspace: reset |
| Quit | Escape or close the window |

Positive synchronization offset reads features ahead of the displayed audio time.
An amber envelope marker shows the adjusted feature position. Playback starts
automatically; it pauses at the end and Play restarts it.

Additional options:

```sh
./build/harmonic-player data/analysis/billie-jean --start 30 --offset-ms 20
./build/harmonic-player data/analysis/billie-jean --audio '/new/path/to/the/same.mp3'
./build/harmonic-player --help
```

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

This milestone analyzes the original mix. Stem separation, lyric display,
semantic/mood services, a persistent catalog, and projectM compositing are later
steps. The current analyzer and player decode the complete track into memory;
long recordings need a future streaming/chunking pass. The small bitmap UI font
supports ASCII; richer typography and translated metadata need a proper text
renderer. The prototype uses native Linux OpenGL entry points; other platforms
will need a portable GL loader and packaging work.

Provider credentials and uploads are not needed for this milestone. Review the
licenses of the chosen FFmpeg/SDL/Arrow builds before distributing binaries.

## Versions and approved releases

Use [Semantic Versioning](https://semver.org/) and annotated Git tags named `vX.Y.Z`.
The public interfaces are the analyzer/player CLIs and the documented analysis
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
support `--version`. Repository instructions in [AGENTS.md](AGENTS.md) preserve
this workflow for future approved updates.
