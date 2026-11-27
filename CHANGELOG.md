# Changelog

Notable changes are recorded here using [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.22.7] - 2026-11-26

### Validation

- Ran Billie Jean full-song with `singing voice` at 10s/2s and 20s/2s on AWS
  Blackwell, completing a 2x2 with the existing `man singing` versions.
  - The runs took 37 + 17 chunks, all validated, with stitched presence.
  - Where `singing voice` presence is high (116-124 s: 0.93), the current
    `man singing` 20s target holds 0.10 of the mix level against 0.52-0.59
    for `singing voice`.
  - Where presence is low (15-23 s: 0.08), every version's target is
    fill-in, which presence gating would remove.
  - A four-way listening packet is ready. Defaults are unchanged pending the
    owner's listening.

## [0.22.6] - 2026-11-26

### Validation

- Ran a wide MUSDB18 benchmark on AWS Blackwell: 16 more test tracks, 138 jobs
  in 1942 s, chosen by measured register, drum activity, instrumental
  sections, and quiet passages. Scored with the project commands.
  - `singing voice` is the best vocal prompt: median mix gain 0.85-0.91 in
    every group and presence AUC 0.979. `man singing` falls to 0.45-0.69 on
    high-register and sparse-drum tracks, and it detects a voice type rather
    than vocal presence.
  - Best presence thresholds, as 1 s means: `singing voice` 0.36,
    `drums playing` 0.16, and `bass guitar playing` 0.36. Bass absence
    rejection stays weak (0.69).
  - Absent targets are still filled in: 6 of 145 pass the 5% absence check.
  - 10 s context beat 20 s for `singing voice` (13 of 16 tracks) and for drums
    (12 of 16).
  - Details are in the worker guide. Prompt and chunk defaults are unchanged
    until a Billie Jean listening check.

## [0.22.5] - 2026-11-26

### Changed

- `just release` stays local. It tests, commits, creates the annotated tag, and
  builds, then reports the commits ahead and the unpushed tags
  (`just release-status`). It no longer pushes or creates the GitHub release.
- `just push-releases` pushes the branch and every unpushed version tag
  atomically, then creates each missing GitHub release, so releases go out in
  batches. AGENTS.md, CLAUDE.md, and the README describe the new flow.

## [0.22.4] - 2026-11-26

### Fixed

- The justfile parses again with the older `just` that Ubuntu 24.04 packages,
  which the GPU host bootstrap installs. v0.22.0 used the
  `[positional-arguments]` recipe attribute, which that version rejects, so
  `just sam-sync` failed before the worker could start. It now uses the
  `set positional-arguments` setting. Track names with spaces still pass to
  `sam-musdb-prepare` intact.
- CI now also parses the justfile with Ubuntu's packaged `just`.

## [0.22.3] - 2026-11-26

### Validation

- Re-measured desktop frame pacing with glava paused. The animated backdrop's
  supervisor restarted the backdrop video before the run, so it kept playing.
  - At 1920x1080, missed vsyncs fell from 10-20 to 2 a minute and interval p99
    from about 20.5 to 18.7 ms, while fps held at 59.3-59.8.
  - One swap-blocked stall a minute (45-56 ms) remains, as do 14-15 missed
    vsyncs and 3 stalls a minute at 2560x1440 fullscreen.
  - The heaviest preset is unchanged at 15 and 10 fps.
  - Runs with the backdrop stopped and without picom remain open.

## [0.22.2] - 2026-11-26

### Changed

- Decided to keep the fresh-history projectM restart on seeks. With a preset, a
  seek takes 117-133 ms instead of 33 ms, and picture and sound resume
  together. The alternatives give up reproducible preset history or move the
  stall into playback. The checklist item is now p3 and will be revisited if
  drag-to-scrub is added.

## [0.22.1] - 2026-11-26

### Validation

- Profiled the ~100 ms picture freeze on preset seeks (GTX 960):
  - Recreating the projectM engine takes 70-80 ms of it.
  - Reloading into the same engine would take only 6-17 ms, but it carries the
    old feedback image into the new history.
  - The options and their trade-offs are recorded in the checklist for an
    owner decision.

## [0.22.0] - 2026-11-26

### Added

- MUSDB18 multi-target benchmark commands, replacing the local evidence
  scripts:
  - `harmonic-sam prepare-musdb ZIP TRACK... --output RUN`
    (`just sam-musdb-prepare`) decodes each track's stems and picks the
    windows. It writes references, the mix, ablation, context, and
    instrumental cases, and a manifest. Each job's `source.stems` records the
    zip member and stem identities.
  - `score-musdb RUN RESULTS --output DIR` (`just sam-musdb-score`) writes
    lag-aligned multi-target scores and a summary.
  - `musdb-context RUN RESULTS --output FILE` (`just sam-musdb-context`)
    compares 10, 20, and 30 s context on each track's common core.
  - All outputs must be new.

### Fixed

- Scoring no longer crashes on a present target that comes back silent. It now
  reports a dropout: gain 0, lag 0, and null correlations. The evidence script
  failed on that case with a NaN in its JSON output.

### Validation

- From the re-downloaded, md5-verified `musdb18.zip`, the commands reproduce
  the 2026-11-26 run exactly:
  - the manifest's windows and jobs;
  - all 16 reference stems, byte for byte;
  - all 27 job inputs, byte for byte, with metadata differing only in
    `app_version` and the added `source.stems`;
  - all 27 per-job scores, the summary, and the context comparison.

## [0.21.1] - 2026-11-26

### Added

- GitHub Actions CI (`.github/workflows/ci.yml`) runs on every push and pull
  request. It builds SDL3 and the native tools on Ubuntu 24.04, checks version
  consistency, and runs `just test` with `HARMONIC_REQUIRE_INTEGRATION=1`, so
  the FFmpeg and native-player tests must run. It uses SDL's offscreen video
  and dummy audio drivers. projectM and the global todo tools stay optional.

## [0.21.0] - 2026-11-26

### Added

- Vocal benchmark jobs record their stems under `source.stems`: resolved path,
  file sha256, and decoded-PCM sha256 for the vocal and accompaniment
  references. Results and scores carry the record, and mixed-case scores add
  `reference_stems` for the stems actually supplied.

### Changed

- Scoring a mixed case refuses reference stems whose file hash differs from the
  stem recorded in the job. Jobs prepared before this release have no stem
  record and still score.

## [0.20.1] - 2026-11-26

### Fixed

- The README's bundle-contract heading now covers schema 3, and the scope
  section no longer says validated SAM outputs become schema-2 bundles.

## [0.20.0] - 2026-11-26

### Added

- Per-device sync offsets. Press **S** during playback to save the current
  offset for the active output device (`<SDL audio driver>/<device name>`) in
  `$XDG_CONFIG_HOME/harmonic/calibration.json` (default `~/.config`).
  - The player applies the saved offset at startup, and `--offset-ms`
    overrides it.
  - `--offset-ms N --save-offset` saves an offset without playing.
  - The offset readout shows `DEVICE`, `ARG`, or `UNSAVED`.
  - Saving keeps other devices' entries and writes the file atomically.
  - A file that cannot be parsed is reported, ignored, and never overwritten.
- Frame reports and summaries record the applied offset, its source, and the
  output device.

### Changed

- **Incompatible:** `--offset-ms` now rejects values beyond +/-2000 ms, the
  range the offset keys already enforced.
- **Incompatible:** in `just perf-desktop` summaries, `audio_late_lower_bound_ms`
  is renamed `alsa_minus_refresh_ms`, and the table column `late>=` is now
  `alsa-refr`.

### Fixed

- Corrected the v0.19.0 latency reading. The ALSA queue minus one refresh is
  not a lower bound on how late audio is: the sound server and DAC add to the
  audio side, and the compositor adds frames to the picture. The real offset's
  size and sign stay unmeasured until a loopback check; until then, calibrate
  per device.

## [0.19.0] - 2026-11-26

### Added

- Player options for desktop measurement: `--size WxH`, `--fullscreen`,
  `--frame-report FILE` (requires `--exit-after`), and `--seek-every SECONDS`.
  A frame report records, for every presented frame, CPU draw time, swap time,
  GPU time (`GL_TIMESTAMP` query pairs, which cannot conflict with projectM's
  own queries), the audio clock, and the SDL queue depth. It also records each
  seek's call time, the time until the audio clock advances past the target,
  and the time until the next presented frame, plus GL, display, and audio
  provenance.
- `just perf-desktop` (`python -m harmonic_analysis.frame_perf run`) plays
  graphs-only and three projectM presets, both in a 1920x1080 window and
  fullscreen at the native resolution. It samples the ALSA hardware queue
  while each scenario plays, records the compositor and GPU load, and writes
  per-scenario reports, logs, exit statuses, and a `summary.json` under
  `data/perf/`. `frame_perf summarize REPORT` summarizes one report.
  Under i3 it floats only the player's own window, found by PID, at exactly
  1920x1080. A scenario whose report shows another size fails.

### Validation

- Desktop measurement on the GTX 960 (driver 580.178.04, i3 with picom,
  2560x1440 at 59.95 Hz, other GPU clients running):
  - Graphs and the light and median presets hold 59.1-59.7 fps at 1920x1080
    and 2560x1440, with GPU p99 of 6-11 ms.
  - The heaviest library preset falls to 14.9 and 9.9 fps.
  - Steady playback has 1-4 swap-blocked stalls a minute.
  - Graphs-only seeks settle in about 33 ms. Preset seeks freeze the picture
    for about 100 ms.
  - The ALSA queue holds a median 28-29 ms that the audio clock does not
    compensate, so audio trails its frame by at least about 12 ms.
  - The README has the full table. Follow-ups are in the checklist.
- The `~/.local/lib` GLX runtime-path warning no longer appears at configure.

## [0.18.0] - 2026-11-26

### Added

- Source-presence signal. For every prompt, the SAM worker measures per-frame
  presence probabilities (40 ms frames) with SAM Audio's pinned span predictor
  (`facebook/pe-a-frame-large`). It records them with model provenance and a
  float32 checksum in the result report. Separation itself is unchanged and
  stays unanchored.
- Full-song stitching blends chunk presence onto the song's 40 ms grid with
  the audio crossfade weights. Validation recomputes the blend from the
  retained chunk reports.
- Source-feature bundle schema 3 (`harmonic.sam.features.v2`) with one
  `sam-NAME-presence.arrow` stream per target. Each stream holds raw
  probabilities, no threshold, and a `reliability` label from the MUSDB18
  study: `benchmarked` for the vocal and drum prompts, `low_confidence` for
  bass, and `unbenchmarked` for other prompts.
- The source inspector draws each target's presence probability with a tick
  at the upstream default of 0.3. `--inspect` reports `presence` and
  `presence_reliability`.

### Changed

- **Incompatible bundle change:** the adapter now writes schema 3, and older
  players reject it. Schema-2 bundles remain readable.
- Results from older workers stay valid, with presence unknown (not absent):
  their bundles carry `presence: null` and no presence streams. Songs that
  mix measured and unmeasured chunks are rejected.

### Validation

- End-to-end Blackwell run of a 12.345 s excerpt and a 4-chunk 27.77 s song,
  neither length a multiple of 40 ms. The predictor returned exactly
  `ceil(samples / 1920)` frames, and the stitch, schema-3 bundles, and native
  loading all validated.

## [0.17.1] - 2026-11-26

### Validation

- Evaluated SAM Audio's span predictor as a source-presence signal on the
  MUSDB18 jobs.
  - Per-second presence AUC is 0.95 for vocals, 0.93 for drums, and 0.91 for
    bass. It correctly rejected every vocal window of an electronic
    instrumental that the hand-built cues misclassified.
  - Bass absence remains weak.
  - Anchoring separation on the predicted spans did not reduce fill-in on
    absent targets.
  - Details and a proposed integration design are in the worker guide and
    the checklist.

## [0.17.0] - 2026-11-26

### Added

- `just sam-vocal-benchmark-prepare`, `just sam-vocal-score-mix`, and
  `just sam-vocal-score-isolated` cover the reference vocal benchmark
  workflow that previously needed direct `harmonic-sam` calls.

### Changed

- `just release` runs the suite with `HARMONIC_REQUIRE_INTEGRATION=1`. FFmpeg
  and native-player tests then fail instead of skipping when their tools are
  missing. projectM, global todo tools, and fzf remain optional.
- Test files import `tests/support.py`. Run a single file with
  `python -m unittest discover -s tests -p 'test_<name>.py'`.

### Fixed

- `harmonic-sam stitch` reports a malformed run completion record as an error
  instead of a traceback.
- Vocal benchmark scoring refuses target or residual WAVs replaced after
  validation.
- Chunk tests honor `HARMONIC_PLAYER`, like the other native tests.

### Validation

- New tests cover `inspect-song`, `stitch`, `validate-song`,
  `prepare-vocal-benchmark`, and `benchmark-vocals` through the command line,
  `--target` parsing, and benchmark edge cases (unequal stems, out-of-range
  windows, argument checks, collinear references).

### Documentation

- Record an offline study of source-presence cues on the MUSDB18 results. Two
  cues detect a bass fill-in, but neither is reliable when a melodic
  instrument fills the vocal target.

## [0.16.1] - 2026-11-26

### Validation

- MUSDB18 multi-target benchmark on Blackwell: 27 jobs across four songs with
  separate stems, scored locally after removing the excerpt means.
  - Present vocals, drums, and bass are extracted at gains of 0.74–0.97 with
    no timing offset (maximum 4 samples).
  - Absent targets are not silent: 30 of 31 carried 38–77% of input RMS,
    mostly bass.
  - The isolated-vocal failure first seen on the overtone fixture also
    occurs on conventional singing.
  - A 30-second context never improved extraction over 10 or 20 seconds.
  - Details are in the worker guide.

### Documentation

- Record the benchmark in the checklist. The singing-reference and
  timing/gain items are complete. New items cover a source-presence signal
  for absent targets and making the benchmark a project command.

## [0.16.0] - 2026-11-26

### Changed

- **Incompatible report change:** `harmonic-sam benchmark-vocals` (and
  `just sam-vocal-control`) now writes `harmonic.sam-vocal-benchmark.v2`.
  Ratios, reference gains, RMS errors, vocal windows, and the absence check
  are computed after removing each stream's excerpt mean. The uncentered
  values move to `raw` and the removed means to `means`. Existing v1 score
  files keep their old, offset-sensitive meaning.

### Fixed

- Constant sample offsets no longer decide vocal benchmark outcomes. A
  reference that is silent or only an offset, and an input with no signal
  beyond its offset, now raise explicit errors.

### Validation

- Re-scoring the archived Blackwell runs reproduces the mean-centered
  diagnostic. The vocal is mainly in the residual for the mixed and vocal-only
  cases, and the guitar-only case fails at 96.4%. The earlier guitar controls
  fail at 94.0% and 97.1%.

## [0.15.2] - 2026-11-26

### Fixed

- Full-song resume now removes abandoned prompt checkpoint directories whose
  temporary suffix contains `_` (about one in five). Before, they stayed until
  their chunk completed.
- Excerpt runs (`just sam-run`) pin the auxiliary T5 text model to the same
  commit as song plans (`a9723ea7…`) instead of resolving the current upstream
  head, so repeated excerpt results stay comparable. `--text-revision` still
  overrides it.

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

[Unreleased]: https://github.com/njhoffman/harmonic/compare/v0.22.7...HEAD
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
[0.15.2]: https://github.com/njhoffman/harmonic/tree/v0.15.2
[0.16.0]: https://github.com/njhoffman/harmonic/tree/v0.16.0
[0.16.1]: https://github.com/njhoffman/harmonic/tree/v0.16.1
[0.17.0]: https://github.com/njhoffman/harmonic/tree/v0.17.0
[0.17.1]: https://github.com/njhoffman/harmonic/tree/v0.17.1
[0.18.0]: https://github.com/njhoffman/harmonic/tree/v0.18.0
[0.19.0]: https://github.com/njhoffman/harmonic/tree/v0.19.0
[0.20.0]: https://github.com/njhoffman/harmonic/tree/v0.20.0
[0.20.1]: https://github.com/njhoffman/harmonic/tree/v0.20.1
[0.21.0]: https://github.com/njhoffman/harmonic/tree/v0.21.0
[0.21.1]: https://github.com/njhoffman/harmonic/tree/v0.21.1
[0.22.0]: https://github.com/njhoffman/harmonic/tree/v0.22.0
[0.22.1]: https://github.com/njhoffman/harmonic/tree/v0.22.1
[0.22.2]: https://github.com/njhoffman/harmonic/tree/v0.22.2
[0.22.3]: https://github.com/njhoffman/harmonic/tree/v0.22.3
[0.22.4]: https://github.com/njhoffman/harmonic/tree/v0.22.4
[0.22.5]: https://github.com/njhoffman/harmonic/tree/v0.22.5
[0.22.6]: https://github.com/njhoffman/harmonic/tree/v0.22.6
[0.22.7]: https://github.com/njhoffman/harmonic/tree/v0.22.7
