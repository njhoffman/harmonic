# Changelog

Notable changes are recorded here using [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.15.1] - 2026-11-26

### Fixed

- Correct the documented `just release` usage: the summary and trailer are
  positional (`just release "<summary>" "<Key: value>"`). `just` does not parse
  `summary=`/`trailer=` for recipe parameters, which garbled the v0.15.0
  release commit message. `release` now rejects arguments in that form.

## [0.15.0] - 2026-11-26

### Added

- `just release` creates a GitHub release from the version's changelog entry
  after pushing. `just publish-release X.Y.Z` retries or backfills one, and
  `python3 scripts/version.py notes [X.Y.Z]` prints the notes.
- Claude Code project files: `CLAUDE.md` imports `AGENTS.md` and adds
  Claude-specific notes, and `.claude/settings.json` adds a command allowlist.

### Changed

- `just release` fetches remote tags before checking the tag. It accepts
  `summary=` (the commit becomes `chore(release): vX.Y.Z - <summary>`) and
  `trailer=` for commit attribution.

### Documentation

- Full backlog review: new checklist items cover SAM scratch cleanup, excerpt
  T5 revision pinning, skipped integration tests, CLI and benchmark test gaps,
  benchmark provenance, CI, and GitHub release backfill. Completed foundation
  work moves to a Completed section.

## [0.14.2] - 2026-11-26

### Documentation

- Prioritize DC-aware vocal benchmark scoring, verification against archived
  results, and a conventional singing reference in the project checklist.

## [0.14.1] - 2026-11-26

### Validation

- Record all three Blackwell reference-case scores and a mean-centered
  diagnostic that explains how DC offset affected the raw vocal benchmark.

## [0.14.0] - 2026-11-26

### Added

- Prepare aligned mixed, vocal-only, and accompaniment-only SAM jobs from
  reference stems. Score validated outputs for vocal retention, accompaniment
  bleed, and false extraction, with sample-indexed vocal diagnostics.

### Validation

- The benchmark flags both previously reviewed guitar-only outputs under the
  default 5% target-to-input RMS limit.

## [0.13.4] - 2026-11-25

### Documentation

- Record the focused full-song vocal review, the final shifted-window
  comparison, and the acoustic-guitar control that exposed vocal-target
  leakage at both window lengths.

## [0.13.3] - 2026-11-25

### Documentation

- Record the owner’s seam and voice-and-piano findings and the validated
  full-song Billie Jean vocal comparison, with focused and full-track
  listening playlists for the 10s/2s baseline and 20s/2s candidate.

## [0.13.2] - 2026-11-25

### Documentation

- Record the listening result that favored the original vocal prompt, and
  document the 20-second Billie Jean seam test and the voice-and-piano
  comparison with sample-aligned target/residual listening clips.

## [0.13.1] - 2026-11-25

### Documentation

- Record the Billie Jean context comparison and the owner's finding that a
  20-second window partially restores the vocal while leaving bass bleed and
  some vocal in the residual.
- Document the controlled Blackwell prompt comparison and its aligned review
  playlist, with each target followed by its residual.

## [0.13.0] - 2026-11-20

### Added

- Checkpoint each finished SAM target/residual pair within an interrupted song
  chunk. Resume validates the job/run binding and waveform statistics, skips
  completed prompts, and reruns only the unfinished prompt. Synthetic recovery
  and corrupted-checkpoint rejection are tested; real CUDA OOM recovery remains
  unverified.

## [0.12.14] - 2026-11-20

### Improved

- Expand shared Python and native bundle checks for SAM model and worker hashes,
  auxiliary model revisions, codec settings, and retained chunk prompts.

## [0.12.13] - 2026-11-20

### Improved

- Reduce full-song stitching peak memory with chunk-sized float64 overlap-add,
  mono source loading, direct WAV writes, and blockwise waveform statistics.
  A local 295.892-second benchmark used 280.4 MiB peak RSS instead of 1,087.5 MiB;
  all six output WAV hashes and all 216 overlap diagnostics remain identical.
- Keep earlier result reports readable and preserve source checksums, sample
  positions, float peaks, and immutable output publication. Whole-song float32
  buffers remain; this is not yet fully bounded-memory processing.

## [0.12.12] - 2026-11-20

### Documentation

- Record the owner's listening confirmation that vocals disappear from the
  reviewed target and remain in the residual. Mark the baseline vocal-consistency
  check as failed while keeping broader seam review and full-song approval open.

## [0.12.11] - 2026-11-20

### Documentation

- Record checksum-verified recovery of SAM benchmark jobs, separation results,
  and review evidence from Charon to Minerva, with current contract validation.
- Document the original-level vocal listening playlist available on both
  computers and the pending AWS context-comparison support request. Preserve
  full-song listening and inference quality gates as incomplete.

## [0.12.10] - 2026-11-20

### Documentation

- Document a local, pinned projectM installation and CMake setup for preset
  playback without changing system packages.
- Record Minerva's verified NVIDIA preset rendering and isolated SAM package
  installation, including GTX 960 incompatibility with the pinned CUDA worker
  and the remaining authentication requirement.

## [0.12.9] - 2026-11-19

### Fixed

- Validate song-plan PCM incrementally in the GPU worker and `inspect-song`,
  avoiding a whole-track PCM allocation during those checks.
- Reject invalid retained chunk padding and level metadata consistently in the
  Python and native readers.

## [0.12.8] - 2026-11-19

### Fixed

- Reject SAM song resumes when imported worker code or the recorded runtime
  identity changed. Stamp new chunks with the run binding hash and reject
  mixed bindings while stitching or reading retained provenance.

## [0.12.7] - 2026-11-19

### Fixed

- Report full-song command time and per-stage timings so cached runs include
  preflight and reuse validation. Keep the original elapsed field for existing
  consumers and record the new timings in each invocation's history.

## [0.12.6] - 2026-11-19

### Fixed

- Remove abandoned chunk and completion scratch on a validated SAM song restart.
  Preserve published chunks, unrecognized files, and symlinks.

## [0.12.5] - 2026-11-19

### Fixed

- Prevent simultaneous full-song SAM workers from writing to the same output.
  The operating system releases the lock when the owning process exits, so the
  same worker release can resume validated chunks after an interruption.

## [0.12.4] - 2026-11-19

### Fixed

- Accept renamed SAM song-plan JSON files when building source feature bundles.
- Reject missing retained chunk indices and malformed retained job hashes in
  both the Python and native bundle readers.

## [0.12.3] - 2026-11-19

### Changed

- Record the AWS organization policy blocking the vocal context comparison and
  retain the validated comparison inputs for an approved GPU host.

## [0.12.2] - 2026-11-19

### Changed

- Document the raw vocal chunk behind the weak 82–88 second stitched interval,
  link the aligned listening clips, and record the prepared context comparison.

## [0.12.1] - 2026-11-19

### Changed

- Refresh the user guide, worker guide, and roadmap to cover full-song inference,
  chunk resume, stitching, and the scope of the AWS validation and listening review.
- Prioritize vocal consistency in the checklist and record follow-ups for resume
  provenance, plan detection, recovery, validation, and long-recording memory use.

## [0.12.0] - 2026-11-19

### Added

- Full-song SAM plans with bounded, overlapping chunks, pinned auxiliary model
  revision, exact source coordinates, and verification of the full canonical PCM.
- `sam-run-song` to process all pending chunks with one model load and validate
  matching completed chunks on restart; retain per-invocation reuse history.
- `sam-stitch` / `sam-validate-song` for complementary half-cosine overlap-add,
  full-length float WAVs, original chunk provenance, and seam diagnostics.
- Full-song source-feature adaptation and native reading while preserving
  support for existing excerpt results. Full-song result files require v0.12.0+.

### Validation

- Complete all 37 real Billie Jean chunks and 111 prompt calls on the tested
  Blackwell host; reuse all 37 chunks without new inference on a second run.
- Validate exact full-length WAV samples, source features, and native compositor
  behavior. Record substantial vocal-estimate differences at some overlaps and
  retain comparison clips; full-song listening/prompt consistency remains open.
- Cover overlap unity gain, uneven tails, corrupt provenance, interrupted chunk
  recovery, one-model reuse, and analysis windows crossing internal chunk seams.

## [0.11.0] - 2026-11-19

### Added

- `harmonic-sam features` / `just sam-features` to turn validated SAM target and
  residual WAVs into an immutable feature bundle using the local analyzer, with
  original mono levels, sample offsets, and complete separation provenance.
- Schema-2 bundles with partial-coverage source Arrow streams and a retained SAM
  report. Existing schema-1 mix bundles remain supported; older players reject
  schema 2 and must be upgraded to read source bundles.
- Separate source RMS histories, spectra, level readouts, and onset activity
  beside the original mix. Press R or use `--sources residuals` to switch views;
  shared mix scales support level comparison, and missing coverage is explicit.

### Validation

- Verify all six real excerpt streams against original WAV windows and preserve
  source/job/model/code/lock identities without embedding separated audio.
- Cover impulse timing, non-hop-aligned offsets, mono peaks above full scale,
  moved artifacts, corruption, coverage boundaries, and original playback.
- Verify target/residual previews and source-bundle projectM pause, seek,
  offset, EOF, resize, and GL-state behavior. Keep full-song processing and
  instrument-level model latency open; the mix catalog rejects source bundles
  until SAM-specific caching is implemented.

## [0.10.4] - 2026-11-19

### Documentation

- Record owner listening approval of the three SAM Audio target/residual pairs:
  clear instrument extraction, no audible unwanted bleed, and clean residuals
  for the tested Billie Jean excerpt.
- Complete the listening checklist while retaining separate instrument-level
  timing and comparative gain checks; keep the measured reconstruction
  differences and independent-target semantics explicit.

## [0.10.3] - 2026-11-19

### Documentation

- Record the first successful SAM Audio large-TV GPU benchmark on an AWS
  NVIDIA RTX PRO 6000 Blackwell host, including verified runtime/authentication,
  model provenance, three prompt timings, and peak GPU/host memory.
- Confirm returned WAV hashes, exact 48 kHz sample counts, and zero global
  reconstruction lag in the measured window. Document substantial waveform/gain
  differences and keep listening and instrument-level alignment checks open.
- Record the completed Paid plan upgrade, L40S capacity failures, successful
  same-region fallback, system-package setup recovery, local result paths, and
  verified removal of all temporary GPU-test infrastructure and authentication.

## [0.10.2] - 2026-11-19

### Documentation

- Confirm the applied 16-vCPU AWS GPU quota and authenticated access to the
  pinned SAM Audio checkpoint configuration without downloading model weights.
- Record the Free plan GPU launch restriction, the approved Paid plan upgrade's
  API failure, and the console recovery steps. GPU inference remains unverified.
- Document the prepared private transfer resources, encrypted worker launch
  configuration, two-hour shutdown timer, and cleanup requirements.

## [0.10.1] - 2026-11-04

### Documentation

- Record verified AWS access, the proposed NVIDIA L40S test host, and the
  pending us-east-2 GPU quota increase with commands to check its status.
- Document the remaining launch, runtime, and Hugging Face authentication gates;
  keep NVIDIA validation tasks open until an actual GPU run succeeds.

## [0.10.0] - 2026-10-22

### Added

- Ctrl-D completion in the workstation's global `todo-fzf`: check the highlighted
  task and reload without exiting. Default views hide the completed item; `--all`
  keeps it checked. Python 3 performs the checkbox edit, preserving other bytes,
  line endings, and file permissions; stale snapshots refuse edits until refresh.
- Three optional integration checks for completion, stale edits, checked-item
  behavior, and a real fzf terminal remaining open after Ctrl-D.

### Changed

- The global picker's prompt uses the Nerd Font list-check icon (`U+F0AE`)
  followed by one space, with no `>` character. Help and the fzf header describe
  the new completion key. The global script remains managed outside this repo.

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

[Unreleased]: https://github.com/njhoffman/harmonic/compare/v0.15.1...HEAD
[0.2.0]: https://github.com/njhoffman/harmonic/tree/v0.2.0
[0.2.1]: https://github.com/njhoffman/harmonic/tree/v0.2.1
[0.3.0]: https://github.com/njhoffman/harmonic/tree/v0.3.0
[0.4.0]: https://github.com/njhoffman/harmonic/tree/v0.4.0
[0.5.0]: https://github.com/njhoffman/harmonic/tree/v0.5.0
[0.6.0]: https://github.com/njhoffman/harmonic/tree/v0.6.0
[0.7.0]: https://github.com/njhoffman/harmonic/tree/v0.7.0
[0.8.0]: https://github.com/njhoffman/harmonic/tree/v0.8.0
[0.9.0]: https://github.com/njhoffman/harmonic/tree/v0.9.0
[0.10.0]: https://github.com/njhoffman/harmonic/tree/v0.10.0
[0.10.1]: https://github.com/njhoffman/harmonic/tree/v0.10.1
[0.10.2]: https://github.com/njhoffman/harmonic/tree/v0.10.2
[0.10.3]: https://github.com/njhoffman/harmonic/tree/v0.10.3
[0.10.4]: https://github.com/njhoffman/harmonic/tree/v0.10.4
[0.11.0]: https://github.com/njhoffman/harmonic/tree/v0.11.0
[0.12.0]: https://github.com/njhoffman/harmonic/tree/v0.12.0
[0.12.1]: https://github.com/njhoffman/harmonic/tree/v0.12.1
[0.12.2]: https://github.com/njhoffman/harmonic/tree/v0.12.2
[0.12.3]: https://github.com/njhoffman/harmonic/tree/v0.12.3
[0.12.4]: https://github.com/njhoffman/harmonic/tree/v0.12.4
[0.12.5]: https://github.com/njhoffman/harmonic/tree/v0.12.5
[0.12.6]: https://github.com/njhoffman/harmonic/tree/v0.12.6
[0.12.7]: https://github.com/njhoffman/harmonic/tree/v0.12.7
[0.12.8]: https://github.com/njhoffman/harmonic/tree/v0.12.8
[0.12.9]: https://github.com/njhoffman/harmonic/tree/v0.12.9
[0.12.10]: https://github.com/njhoffman/harmonic/tree/v0.12.10
[0.12.11]: https://github.com/njhoffman/harmonic/tree/v0.12.11
[0.12.12]: https://github.com/njhoffman/harmonic/tree/v0.12.12
[0.12.13]: https://github.com/njhoffman/harmonic/tree/v0.12.13
[0.12.14]: https://github.com/njhoffman/harmonic/tree/v0.12.14
[0.13.0]: https://github.com/njhoffman/harmonic/tree/v0.13.0
[0.13.1]: https://github.com/njhoffman/harmonic/tree/v0.13.1
[0.13.2]: https://github.com/njhoffman/harmonic/tree/v0.13.2
[0.13.3]: https://github.com/njhoffman/harmonic/tree/v0.13.3
[0.13.4]: https://github.com/njhoffman/harmonic/tree/v0.13.4
[0.14.0]: https://github.com/njhoffman/harmonic/tree/v0.14.0
[0.14.1]: https://github.com/njhoffman/harmonic/tree/v0.14.1
[0.14.2]: https://github.com/njhoffman/harmonic/tree/v0.14.2
[0.15.0]: https://github.com/njhoffman/harmonic/tree/v0.15.0
[0.15.1]: https://github.com/njhoffman/harmonic/tree/v0.15.1
