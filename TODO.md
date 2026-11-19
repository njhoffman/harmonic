# Task checklist

Use this file for current progress and [PLAN.md](PLAN.md) for architecture and
rationale. Check off work only after verification; update the checklist with
each approved change. Tasks carry an explicit priority and category:

- **P1 `(p1)`**: next validation gates and work that unblocks the SAM milestone.
- **P2 `(p2)`**: implementation after those gates, or independent local improvements.
- **P3 `(p3)`**: deferred scenes, scale, service work, and optional comparisons.

Categories are `[feature]`, `[test]`, `[perf]`, `[bug]`, `[docs]`, and `[chore]`.
`☐` means incomplete; `☑` means completed. Global `todo-status` and `todo-fzf`
show incomplete tasks by default; add `--all` to include completed tasks, or
`--help` for options and examples. `just todo` retains the full Markdown checklist.

**Current gate:** the first real SAM Audio GPU benchmark passed on 2026-11-19.
The unchanged 10-second Billie Jean job ran with `facebook/sam-audio-large-tv`
on an AWS `g7e.4xlarge` in `us-east-2c`. Runtime installation, CUDA, authentication,
three prompted separations, returned-file hashes, and exact sample counts passed.
The output is saved locally under `data/aws-gpu/2026-11-19/`. Listening,
instrument-level transient alignment, cross-target overlap, and the observed
reconstruction/gain differences still need review before player integration.
The GPU quota is 16 vCPUs; the owner completed the approved Paid plan upgrade.
L40S hosts lacked capacity, so no L40S inference compatibility is claimed.
See the [worker guide](workers/sam_audio/README.md) for measurements and limits.

## SAM Audio: GPU validation (P1)

- [x] **Select the GPU worker host** (p1) [chore]
  Verified on 2026-11-19: `g7e.4xlarge` in `us-east-2c`, NVIDIA RTX PRO 6000
  Blackwell Server Edition (97,887 MiB reported memory), driver 595.112.07,
  128 GiB nominal host RAM, and 142 GiB initially free on the encrypted root
  volume. The two-hour shutdown timer was verified active during the run.
  Full-song resource use remains untested. `g6e.4xlarge` and `g6e.2xlarge` lacked capacity in all three zones.
  Applied On-Demand G/VT quota is 16 vCPUs and the Paid account plan is active.
- [x] **Transfer the release and unchanged excerpt job** (p1) [chore]
  The published `v0.10.1` source archive and unchanged
  `data/sam-jobs/billie-jean-v0.7.0/` reached the host through private encrypted
  transfers. The input hash passed on the host; no full recording was uploaded.
- [x] **Install and verify the locked GPU runtime** (p1) [test]
  `just sam-sync` installed the frozen Python 3.11/CUDA 12.8 environment.
  Torch, torchaudio, torchvision, TorchCodec, and SAM imports and a real CUDA
  tensor operation passed. Worker execution accepted the pinned source revision.
- [x] **Authenticate and verify gated checkpoint access** (p1) [chore]
  Local cached-login access to the pinned config passed on 2026-11-19.
  A restricted SecureString parameter supplied authentication to the worker;
  `sam-doctor` reports CUDA/authentication/ready true. The authenticated
  checkpoint download and inference passed. No token entered command arguments,
  logs, or Git.
- [x] **Fetch the pinned model and record auxiliary provenance** (p1) [test]
  The pinned main checkpoint/config/license hashes are recorded in `report.json`.
  Auxiliary text model: `google-t5/t5-base` at
  `a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1`; pin this revision on repeat runs.
- [x] **Benchmark vocal, drum, and bass prompts** (p1) [perf]
  The prepared 30–40 second excerpt ran in 2.197 s (vocals), 1.560 s (drums),
  and 1.562 s (bass), totaling 5.319 s of separation. Peak reserved CUDA memory
  was 19.074 GiB, peak host RSS 29.855 GiB; total run including initial downloads
  and model loading was 221.583 s. The selected Blackwell host fits this job.
- [x] **Validate returned target/residual artifacts** (p1) [test]
  `just sam-validate` passed all three pairs. Each WAV has 480,000 mono samples
  at 48 kHz, no padding trim, and verified hashes/statistics/source offset.
  Original config, worker code, and worker lock hashes match the report.
- [x] **Retrieve GPU results and remove temporary AWS resources** (p1) [chore]
  All 20 output objects are verified locally. Instance, disk, bucket, temporary
  token, role/profile, launch template, and security group were removed. Final
  checks found no active test instance, tagged test volume, or token parameter.
  A delayed normal shutdown completed after force termination.
- [ ] **Listen to returned target/residual pairs** (p1) [test]
  Inspect separation quality and cross-target overlap using the saved WAVs.
  Independent prompts must not be presented as mutually exclusive stems.
- [ ] **Complete perceptual alignment and gain validation** (p1) [test]
  Measured target-plus-residual waveform lag is zero within a ±100 ms search;
  reconstruction RMS error is 0.091–0.093 against source RMS 0.209. Best-fit
  reconstruction gain is 0.807–0.863; this is not a correction to apply blindly.
  Pinned processor checks confirm arithmetic-mean mono conversion, unchanged
  double-amplitude inputs, and complete anti-phase cancellation. The model
  generates residuals independently; exact mixture reconstruction is not enforced.
  Listening and instrument-level transient checks remain open. Float WAV peaks
  above 1.0 were preserved without normalization or clipping.

## Playback: real-device validation (P1)

- [x] **Listen through Billie Jean on the actual audio output** (p1) [test]
  Check visual alignment at the start, throughout the song, and after repeated seeks.
  Completed: owner confirmed physical-output listening validation.
- [x] **Exercise visible desktop controls and end-of-track behavior** (p1) [test]
  Verify mouse seeking, keyboard shortcuts, pause/resume, view switching, and restart.
  Completed: owner confirmed visible desktop controls and end-of-track behavior.
- [ ] **Measure 1080p frame times on the target GPU** (p1) [perf]
  Check drift/stutters and the desktop OpenGL loader, including the known GLX
  runtime-search-path warning involving `~/.local/lib`.
- [ ] **Check contrasting real recordings** (p1) [test]
  Include a cappella or instrumental material; Billie Jean is currently the only
  supplied real recording. Synthetic fixtures do not complete this listening check.

## SAM Audio: feature integration (P2)

- [ ] **Validate the adapter with real inference outputs** (p2) [feature]
  Preserve measured timing, sample rate/channel provenance, relative gain,
  prompts/anchors, settings, and model revisions when producing feature artifacts.
- [ ] **Version the multi-stream bundle contract** (p2) [feature]
  Extend JSON/Arrow validation and the native reader for mix plus named target
  streams. Bump the schema for incompatible changes and reject mismatched timelines.
- [ ] **Display separate source graphs alongside the mix** (p2) [feature]
  Use distinct activity curves without implying that independent targets sum to
  the original mix or contain stereo-width information.
- [ ] **Establish full-song chunking and overlap behavior** (p2) [test]
  Measure boundary artifacts, prompt consistency, latency, and gain across chunks
  before running catalog-wide separation.
- [ ] **Cache SAM runs with complete provenance keys** (p2) [feature]
  Include recording identity, excerpt/chunk coordinates, checkpoint/code/auxiliary
  revisions, prompts/anchors, seed, settings, and output schema in reuse decisions.
- [ ] **Resume failed stages and validate cleanup rules** (p2) [feature]
  Reuse completed prompts/chunks after interruption or OOM. Delete separated audio
  only after the completed feature artifact is validated; retain benchmark outputs
  while quality and alignment are under review.
- [ ] **Review licenses before distribution or service use** (p2) [docs]
  The SAM License was inspected for the local prototype. Perception Models and
  ImageBind have noncommercial terms; resolve dependency use and permitted outputs
  before packaging binaries, model code/weights, or a commercial service.

## Local experience: next improvements (P2)

- [ ] **Import line-timed lyrics with manual timing correction** (p2) [feature]
  Preserve recording identity, lyric provenance, and user adjustments.
- [ ] **Support Unicode text rendering** (p2) [feature]
  Replace the ASCII-only bitmap font before relying on translated lyrics and
  non-ASCII artist/title metadata in the player.
- [ ] **Evaluate one mood/genre tagger** (p2) [feature]
  Preserve provider/model provenance and user overrides; keep inferred labels
  distinct from measured audio activity.
- [ ] **Add a small scene controller and palette mappings** (p2) [feature]
  Start with restrained transitions that can use the existing mix features.
- [ ] **Connect catalog selection to playback** (p2) [feature]
  Choose a registered bundle and usable recording location, then add basic
  playlist navigation without bypassing checksum validation.
- [ ] **Make todo-fzf clipboard shortcuts portable** (p2) [bug]
  The helper exists at `~/.shell/scripts/clip/pushclip.sh` on this workstation.
  Verify Ctrl-Y/Alt-Y here and provide a supported fallback for other hosts
  without that helper; do not submit copied text to another pane.

## Later milestones (P3)

- [ ] **Build spatial, radial, and vocal/lyric scenes** (p3) [feature]
  Use validated source features and measure transitions/performance on the target GPU.
- [ ] **Add resumable library processing and resource reporting** (p3) [perf]
  Include concurrency/memory limits, runtime/storage accounting, and retries
  after the single-recording workflow is validated.
- [ ] **Build the authenticated metadata/artifact service** (p3) [feature]
  Proceed after the local experience, recording matching, and redistribution
  permissions are established; do not distribute original recordings.
- [ ] **Compare alternate checkpoints or separators only if useful** (p3) [test]
  Consider a smaller SAM checkpoint if capacity requires it and access permits;
  keep Demucs or a paid separator as optional references.

## Completed foundation

- [x] **Document objectives, stack, services, risks, and roadmap** (p2) [docs]
  Read the outline and save the architecture and rationale in PLAN.md.
- [x] **Record suggested test songs and their purpose** (p2) [docs]
- [x] **Create the Python analyzer and C++/SDL3/OpenGL player** (p2) [feature]
- [x] **Analyze the supplied Billie Jean recording locally** (p2) [test]
- [x] **Store original-mix features on a 48 kHz timeline** (p2) [feature]
  Save RMS, peak, spectral-onset activity, and 64 frequency bands in JSON/Arrow bundles.
- [x] **Verify source, artifact, and decoded-PCM checksums** (p2) [test]
  Check consistency between analyzer, catalog, and native player.
- [x] **Display spectrum bars and a whole-track envelope** (p2) [feature]
- [x] **Implement transport, normalization, and timing offset** (p2) [feature]
  Include pause/resume, seeking, and restart.
- [x] **Pass the v0.7.0 automated verification suite** (p2) [test]
  Forty-one checks cover analysis, CLI behavior, native playback, projectM,
  catalog/reuse, SAM job/worker contracts, and command status. This does not
  establish real GPU inference or physical audio-output validation.
- [x] **Verify dummy-audio playback, seeking, and EOF** (p2) [test]
  Exercise the real recording without claiming physical listening validation.
- [x] **Render and visually inspect an offscreen preview** (p2) [test]
- [x] **Add task-runner and release commands** (p2) [chore]
  Cover build, analysis, catalog, playback, SAM preparation, verification, and release.
- [x] **Support help/version aliases in the project CLIs** (p2) [feature]
  Include `--help`/`-h` and `--version`/`-v` without input files.
- [x] **Install the global Codex checklist skill and prompt** (p2) [chore]
  Provide `todo` and `/prompts:todo` with colors; verify lookup in another project.
- [x] **Add the local checklist viewer and safe installer** (p2) [chore]
  `just todo` displays the full checklist; installation preserves customized files.
- [x] **Add gradient progress and colored command status** (p2) [feature]
  Preserve logs/exit codes, honor color controls, and animate unknown-duration
  activity while hashing/decoding blocks without inventing completion percentages.
- [x] **Verify a base player without optional projectM features** (p2) [test]
- [x] **Add live projectM playback and graph compositing** (p2) [feature]
  Include view switching, sample-clock timing, cached pause behavior, and feedback
  resets after seeks and timing-offset changes.
- [x] **Verify compositor state and representative presets** (p2) [test]
  Check classic/shader presets, pause, seeks, EOF, resize, dummy-audio playback,
  and 1080p software-renderer previews/timings; hardware performance remains open.
- [x] **Add recording identity and the local SQLite catalog** (p2) [feature]
  Track exact-file identities, locations, existing bundles, and verified mix reuse.
- [x] **Verify catalog recovery and relocated-file playback** (p2) [test]
  Include corrupt-cache rejection, PCM/configuration validation, JSON/CLI output,
  and recovery after interrupted registration.
- [x] **Establish SemVer, changelog, tags, and release workflow** (p2) [chore]
  Synchronize versions, commit, tag, push, and build approved updates.
- [x] **Publish the v0.2.0 prototype and verify its build** (p2) [chore]
- [x] **Publish v0.7.0 with the prepared SAM worker** (p2) [chore]
  Commit, tag, push, and build the release; no real SAM inference was claimed.
- [x] **Receive access to SAM Audio large TV** (p1) [chore]
  Owner confirmation; GPU-host authentication/access checks remain open above.
- [x] **Prepare the isolated Python 3.11/CUDA worker** (p1) [feature]
  Pin source/checkpoint revisions and resolve the full dependency lock without
  installing the inference environment on this laptop.
- [x] **Prepare the portable 10-second Billie Jean job** (p1) [feature]
  Preserve source/PCM hashes, sample offset, prompts, seed, and settings at 30 seconds.
- [x] **Verify SAM job and output contracts without inference** (p1) [test]
  Check portability, hashes, timebase, corrupt-file rejection, mono gain,
  right-padding handling, and dependency-free diagnostics.
- [x] **Define independent target/residual semantics** (p1) [docs]
  Prompted pairs may overlap; they do not form four mutually exclusive stems.
- [x] **Prioritize the backlog and update local task viewers** (p2) [feature]
  Add explicit priorities/categories, recent SAM follow-ups, help/version flags,
  default incomplete-only views, and `--all` with checked/empty boxes. Verify
  filtering, previews, sorting/reload, metadata audits, and real fzf selection.

- [x] **Use global task viewers and enable the tmux picker** (p2) [chore]
  Remove repository copies, discover optional integrations on PATH, and fix
  standalone viewer versions. Activate the existing Alt-I popup binding; six
  automated viewer checks pass. Interactive prompt pasting awaits owner use.

- [x] **Complete tasks inside the global fzf picker** (p2) [feature]
  Ctrl-D checks the highlighted task and reloads without exiting. Preserve file
  bytes/permissions, reject stale snapshots, and keep checked items with --all.
  Verify completion in a real fzf terminal; use a list-check icon prompt.
