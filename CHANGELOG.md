# Changelog

Notable changes are recorded here using [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/njhoffman/harmonic/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/njhoffman/harmonic/tree/v0.2.0
