# Task checklist

Use this file for current progress and [PLAN.md](PLAN.md) for the architecture
and rationale. Check off implementation only after verification. Update this
checklist as part of each approved update.

## Completed foundation

- [x] Read the outline and document objectives, stack, services, risks, and roadmap.
- [x] Record suggested test songs and what each one exercises.
- [x] Create the Python analyzer and C++/SDL3/OpenGL player.
- [x] Analyze the supplied “Billie Jean” recording locally.
- [x] Save original-mix RMS, peak, spectral-onset activity, and 64 frequency bands
  on a 48 kHz sample timeline in versioned JSON/Arrow bundles.
- [x] Verify source, artifact, and decoded-PCM checksums between analyzer and player.
- [x] Display spectrum bars and a whole-track amplitude envelope.
- [x] Implement pause/resume, seeking, restart, normalization, and timing offset.
- [x] Pass five signal-analysis tests, six CLI checks, three player integration tests,
  three projectM integration checks, four compositor/playback tests, and two command-status tests.
- [x] Verify the real recording with dummy-audio playback/seek/end-of-track checks.
- [x] Render and visually inspect an offscreen OpenGL preview.
- [x] Add `just` commands for build, analysis, playback, verification, and release.
- [x] Support `--help`/`-h` and `--version`/`-v` in both analyzer and player,
  including invocation without a recording or bundle.
- [x] Install a global Codex `todo` skill and `/prompts:todo` command with colored
  task status; verify checklist lookup from another project's nested directory.
- [x] Add `just todo` and a repeatable global installer that preserves customized files.
- [x] Add gradient progress bars, colored status markers, and elapsed-time activity
  displays while preserving command logs, failure exit codes, and color controls.
- [x] Verify the base player builds and runs with both optional projectM features disabled.
- [x] Add live preset playback, graph overlays, view switching, sample-clock timing,
  cached pause behavior, and feedback resets after seeks and offset changes.
- [x] Verify compositor state, pause, seeks, EOF, and resize with two real presets;
  run the actual preset playback path with dummy audio.
- [x] Establish SemVer, `CHANGELOG.md`, synchronized versions, and annotated tags.
- [x] Publish the prototype and task runner as `v0.2.0`; verify its final build.

## Next: playback validation

- [ ] Listen through “Billie Jean” on the actual audio output device; check the
  visual alignment at the start, across the song, and after repeated seeks.
- [ ] Exercise mouse/keyboard controls in the visible desktop player and confirm
  behavior at the end of playback.
- [ ] Measure frame times at 1080p on the target GPU and check for drift/stutters.
- [ ] Check a contrasting recording, including a cappella or instrumental audio.
- [x] Verify classic and shader-based libprojectM presets with original-mix PCM;
  inspect 1080p previews and record software-renderer timing and API limitations.

## Next: SAM Audio separation

**Access pending:** the owner is awaiting access to the
[SAM Audio checkpoints](https://huggingface.co/collections/facebook/sam-audio).
SAM Audio is preferred over the earlier Demucs-first direction. No checkpoint
download or SAM Audio inference has been performed here.

- [ ] Receive checkpoint access and configure authentication locally.
- [ ] Select a compatible Python/PyTorch/CUDA environment for an isolated worker.
- [ ] Confirm the selected SAM License/checkpoint terms fit the intended usage.
- [ ] Benchmark a short “Billie Jean” excerpt with vocal, drum, and bass prompts;
  record checkpoint revision, settings, runtime, memory, and visual usefulness.
- [ ] Define target/residual and overlapping-target semantics; do not assume
  independently prompted outputs form four mutually exclusive stems.
- [ ] Implement an adapter that preserves sample alignment, output rate/channels,
  relative gain, prompt/anchor provenance, and reproducible inference settings.
- [ ] Establish full-song chunking/overlap behavior and test boundary artifacts.
- [ ] Extend the bundle contract and native reader/rendering for multiple streams;
  version the schema if the data contract changes incompatibly.
- [ ] Show distinct per-source frequency/amplitude graphs alongside the original mix.
- [ ] Add analysis reuse and stage-level retry behavior; delete temporary separated
  audio only after validating the completed feature artifact.
- [ ] Compare against Demucs or a paid separator only if a reference is useful.

## Later milestones

- [ ] Add recording identity/deduplication and a local catalog.
- [ ] Import line-timed lyrics and support manual timing correction.
- [ ] Evaluate one mood/genre tagger and preserve provenance and user overrides.
- [ ] Implement a small scene controller and restrained mood/palette mappings.
- [ ] Build spatial, radial drum/bass, and vocal/lyric scenes.
- [x] Integrate projectM compositing and representative preset compatibility checks.
- [ ] Add resumable library analysis and cost/resource reporting.
- [ ] Build the authenticated metadata/artifact service after the local experience
  and output-redistribution permissions are established.
