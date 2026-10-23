# Changelog

Notable changes are recorded here using [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.9.0] - 2026-10-22

### Changed

- Remove repository-local `./todo-status` and `./todo-fzf` entry points. Use the
  global commands on PATH instead; this is an incompatible 0.x interface change.
- Discover installed global viewers for six optional integration checks and
  accept their independent SemVer versions. Skip these checks on hosts without
  the personal scripts; application verification remains available.
- Document the workstation's Alt-I tmux popup for selecting tasks and pasting
  into the Codex prompt without submitting. The global scripts and tmux binding
  are managed outside this repository; standalone viewer version lookup was
  repaired and the existing binding activated on this workstation.
- Mark owner-confirmed Billie Jean physical-output listening and visible desktop
  controls/end-of-track checks complete. Keep quantitative latency, GPU timing,
  and contrasting-recording checks pending.
- Correct the clipboard follow-up: the helper exists in the global scripts
  directory; cross-host portability and interactive shortcuts remain unverified.

## [0.8.0] - 2026-10-22

### Added

- Prioritized TODO.md backlog with explicit P1/P2/P3 levels and categories,
  consolidated completed work, and follow-ups for GPU setup, authentication,
  model provenance, actual separation quality/alignment, SAM caching/retries,
  Unicode text, catalog playback, and the missing optional clipboard helper.
- Repository-local `todo-status` and `todo-fzf` viewers with default
  incomplete-only views, `--all` for both states, and `--help`/`-h` plus
  `--version`/`-v`. Checked boxes are green; unchecked boxes are dim white,
  with two spaces before priority markers. Both honor `NO_COLOR`.
- Six integration checks for completion filtering, metadata/counts, line ranges,
  previews, urgency/file sorting, reload arguments, and actual fzf selection.

### Changed

- TSV status output retains its original eight columns and appends completion
  state and checkbox columns. Fuzzy selections retain status and line references;
  completed items sort after pending work when `--all` is used.
- Fenced Markdown examples no longer create tasks in checklist counts or audits.

## [0.7.0] - 2026-10-22

### Added

- Portable short-excerpt SAM Audio jobs through `harmonic-sam prepare/inspect`,
  preserving source/PCM checksums, exact source sample offsets, prompts, and settings.
- Isolated Linux GPU worker for the approved `facebook/sam-audio-large-tv`
  checkpoint, pinned source/model revisions, and a separate Python 3.11/CUDA 12.8
  dependency lock. The graph resolves; runtime/GPU compatibility is still unverified.
- Worker preflight diagnostics and explicit GPU-host sync/auth/run commands.
  Help/version and pre-install diagnostics require no model dependencies; missing
  prerequisites stop execution before checkpoint downloads.
- Atomic target/residual float32 mono WAV output and provenance/timing/memory
  reports, with returned-result validation via `harmonic-sam validate` and
  `just sam-validate`. Independent targets may overlap; only right codec padding
  is trimmed, without normalization or concealing short/invalid output.
- Eight contract/CLI checks and GPU setup, transfer, and dependency-license notes.
  The owner granted model access; no weights or inference stack were installed
  locally and no real separation benchmark has run yet.

## [0.6.0] - 2026-10-22

### Added

- Local SQLite recording catalog with exact-file deduplication, file-location
  references, immutable bundle provenance, and `harmonic-catalog import/list`.
  The CLI supports JSON output, `--help`/`-h`, and `--version`/`-v`.
- Verified original-mix analysis reuse, existing-bundle registration, and recovery
  of completed managed bundles after interrupted database registration. Imports
  check hashes, supported parameters, Arrow content, and sample timing; external
  bundles additionally require matching decoded PCM. Corrupt caches fail explicitly.
- `just import`, `just catalog-add`, and `just catalog`; relocated identical files
  reuse analysis and receive a player command with the correct audio override.
- Nine catalog checks for reuse, identity, relocation, corruption, provenance,
  recovery, database protection, and CLI behavior.

### Fixed

- Unknown-duration terminal contexts keep their gradient activity indicator
  moving while hashing or external decoding blocks the caller. A dedicated
  check verifies progress without displaying an invented percentage.
- Analyzer diagnostic messages use stderr, keeping catalog JSON stdout clean.

## [0.5.0] - 2026-10-22

### Added

- Optional projectM preset playback through `harmonic-player --preset`, with
  combined graph overlays, a preset view, graph-only mode, and a `V` view toggle.
- Sample-clock-driven preset timing, a separate framebuffer that stays frozen
  during pause, and feedback resets after seeks, offset changes, resizing, and
  returning from graph-only mode. Preset preparation holds the audio clock
  during startup and explicit seek/reset operations.
- `just play-preset`, `just compositor-check`, offscreen multi-frame preview
  rendering, and compositor reports covering GL state, pause, sample advancement,
  forward/backward seeks, EOF, resize, and saved view checksums.
- Playback remains usable without projectM. Optional playback probes the actual
  frame-time/framebuffer APIs; the older-library preset checker remains separate.

### Fixed

- Dummy-audio verification now polls for actual clock progress with bounded
  deadlines and elapsed-time bounds, avoiding scheduler-dependent fixed sleeps
  while still rejecting cursor jumps, frozen playback, and incomplete EOF.

## [0.4.0] - 2026-10-22

### Added

- Optional `harmonic-projectm-check` CLI and `just projectm-check` to verify a
  local MilkDrop preset against a checksum-validated original-mix bundle, render
  a preview, and save renderer identity, provenance, and frame timing statistics.
- Gradient progress bars for feature extraction and preset rendering; gradient
  activity indicators and elapsed-time status for build, dependency, and check
  commands. Logs and failure exit codes are preserved, with `NO_COLOR` and
  `FORCE_COLOR` controls and colored status markers in captured output.
- Integration checks for preset output, invalid files, library load failures,
  immutable checker output, help/version aliases, and command status handling.

## [0.3.0] - 2026-10-22

### Added

- Portable global Codex `todo` skill and `/prompts:todo` custom prompt that read
  the active project's TODO.md, with ANSI terminal colors and colored Markdown
  status markers for chat.
- `just todo` for a local read-only checklist view and `just install-codex-todo`
  for installing the command into the user's Codex home without overwriting
  existing customized files.
- `-h` as the native player's help alias and `-v` as the analyzer/player version
  alias. Both programs support `--help`/`-h` and `--version`/`-v` without input files.

## [0.2.1] - 2026-10-22

### Added

- `TODO.md` as the running checklist, with verified work, manual playback checks,
  pending SAM Audio access, and the remaining implementation milestones.
- Standing instructions to keep the checklist current with approved updates.

### Changed

- Prefer SAM Audio for the next separation milestone, with Demucs retained as an
  optional reference/fallback. Document prompted target/residual behavior,
  provenance, timing/channel conversion, model isolation, and access/licensing
  prerequisites. SAM Audio remains uninstalled and unbenchmarked pending access.

## [0.2.0] - 2026-10-22

First tagged release, following the untagged 0.1.0 prototype.

### Added

- Local Python audio analysis with RMS/peak envelopes, spectral onsets, 64
  logarithmic frequency bands, embedded metadata, and JSON/Arrow bundles.
- C++/SDL3/OpenGL player with frequency bars, a track envelope, pause/resume,
  seeking, normalization controls, and an adjustable visual timing offset.
- Recording, artifact, and decoded PCM checksum verification; synthetic signal
  tests, native integration tests, dummy-audio checks, and offscreen rendering.
- `justfile` commands for dependencies, building, analysis, playback, checks,
  version bumps, and publishing approved releases.
- SemVer release policy, synchronized version checks, annotated GitHub tags,
  changelog maintenance, and version output in both command-line programs.
- Project objectives, implementation roadmap, provider research, suggested test
  recordings, and build/usage documentation.

### Fixed

- Playback clock anchoring at the final audio chunk, so playback reaches the
  final sample even when the UI has not queried the clock recently.

[Unreleased]: https://github.com/njhoffman/harmonic/compare/v0.9.0...HEAD
[0.2.0]: https://github.com/njhoffman/harmonic/tree/v0.2.0
[0.2.1]: https://github.com/njhoffman/harmonic/tree/v0.2.1
[0.3.0]: https://github.com/njhoffman/harmonic/tree/v0.3.0
[0.4.0]: https://github.com/njhoffman/harmonic/tree/v0.4.0
[0.5.0]: https://github.com/njhoffman/harmonic/tree/v0.5.0
[0.6.0]: https://github.com/njhoffman/harmonic/tree/v0.6.0
[0.7.0]: https://github.com/njhoffman/harmonic/tree/v0.7.0
[0.8.0]: https://github.com/njhoffman/harmonic/tree/v0.8.0
[0.9.0]: https://github.com/njhoffman/harmonic/tree/v0.9.0
