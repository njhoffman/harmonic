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
  three projectM integration checks, four compositor/playback tests, nine catalog
  checks, eight SAM job/worker contract checks, and three command-status tests.
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
  Unknown-duration contexts also animate during blocking hashing/decoding work.
- [x] Verify the base player builds and runs with both optional projectM features disabled.
- [x] Add live preset playback, graph overlays, view switching, sample-clock timing,
  cached pause behavior, and feedback resets after seeks and offset changes.
- [x] Verify compositor state, pause, seeks, EOF, and resize with two real presets;
  run the actual preset playback path with dummy audio.
- [x] Add a local SQLite catalog, exact-file identities, location references,
  existing-bundle registration, and verified original-mix analysis reuse.
- [x] Verify relocated-file playback, corrupt-cache rejection, PCM/configuration
  validation, JSON/help/version output, and interrupted-registration recovery.
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

**Access granted:** the owner confirmed access to
[`facebook/sam-audio-large-tv`](https://huggingface.co/facebook/sam-audio-large-tv).
The isolated worker and dependency lock are prepared here for a GPU host, as
requested. This machine exposes Intel Iris Xe graphics, 16 GB RAM, no working
CUDA device, and no configured Hugging Face token. No checkpoint weights were
downloaded and no real SAM Audio inference has run. See the
[worker guide](workers/sam_audio/README.md) for setup and transfer instructions.

- [x] Receive checkpoint access (owner confirmation).
- [x] Prepare an isolated Python 3.11/CUDA worker with pinned source/checkpoint
  revisions and a resolved transitive dependency lock, without installing it locally.
- [x] Prepare a portable 10-second “Billie Jean” job at 30 seconds with exact
  source/PCM hashes, source sample offset, prompts, seed, and inference settings.
- [x] Verify portable input, output audio/timebase validation, corrupt-file
  rejection, mono gain/right-padding handling, and dependency-free diagnostics.
- [ ] Install the locked environment on the GPU host and verify package imports,
  CUDA functionality, available memory, authentication, and gated checkpoint access.
- [ ] Confirm license terms for eventual distribution/service use. The SAM License
  was inspected; Perception Models and ImageBind have noncommercial terms to review.
- [ ] Benchmark a short “Billie Jean” excerpt with vocal, drum, and bass prompts;
  record checkpoint revision, settings, runtime, memory, and visual usefulness.
- [x] Define target/residual and overlapping-target semantics; independently
  prompted pairs may overlap and are not four mutually exclusive stems.
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

- [x] Add recording identity/deduplication and a local catalog.
- [ ] Import line-timed lyrics and support manual timing correction.
- [ ] Evaluate one mood/genre tagger and preserve provenance and user overrides.
- [ ] Implement a small scene controller and restrained mood/palette mappings.
- [ ] Build spatial, radial drum/bass, and vocal/lyric scenes.
- [x] Integrate projectM compositing and representative preset compatibility checks.
- [ ] Add resumable library analysis and cost/resource reporting.
- [ ] Build the authenticated metadata/artifact service after the local experience
  and output-redistribution permissions are established.
