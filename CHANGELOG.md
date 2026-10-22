# Changelog

Notable changes are recorded here using [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/njhoffman/harmonic/compare/v0.3.0...HEAD
[0.2.0]: https://github.com/njhoffman/harmonic/tree/v0.2.0
[0.2.1]: https://github.com/njhoffman/harmonic/tree/v0.2.1
[0.3.0]: https://github.com/njhoffman/harmonic/tree/v0.3.0
