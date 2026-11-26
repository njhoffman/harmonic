# Task checklist

Use this file for current progress, [README.md](README.md) for implemented behavior,
and [PLAN.md](PLAN.md) for architecture. Check off only verified work and update
this file with each approved change. Historical release details are in
[CHANGELOG.md](CHANGELOG.md).

Reviewed: 2026-11-26

- **P1 `(p1)`**: next quality gates and validation that unblock the SAM milestone.
- **P2 `(p2)`**: reliability, local improvements, and later integration work.
- **P3 `(p3)`**: deferred scenes, library scale, services, and comparisons.

Categories are `[feature]`, `[test]`, `[perf]`, `[bug]`, `[docs]`, and `[chore]`.
`☐` means incomplete; `☑` means completed. Global `todo-status` and `todo-fzf`
show incomplete tasks by default; use `--all` for completed tasks or `--help` for
options. `just todo` retains the complete Markdown checklist.

**Current gate:** absent targets are never silent. The MUSDB18 benchmark
(2026-11-26) found that a missing vocal or drum part is filled mainly with
bass. Schema-3 bundles now carry a per-frame presence probability for each
prompt, so scenes can tell an absent vocal from bass fill-in; scene
thresholds remain open. Timing is verified, and instrument gains are
below one without a consistent correction. The benchmark scorer now removes each
stream's excerpt mean (report v2) and reproduces the archived diagnostic: the
first reference run put guitar in the vocal target (96.4% of input) and left
overtone singing in the residual, even on its own. Full-song processing and resume are
structurally validated. Billie Jean tuning is complete, 20s/2s remains the
experimental vocal setting, and full-song listening approval remains open.
Local evidence is ignored by Git. See the
[worker guide](workers/sam_audio/README.md) for paths and limits.

## Separation quality and playback gates (P1)

- [x] **Make vocal benchmark scoring account for DC offset** (p1) [bug]
  Use mean-centered waveforms for reference gains, RMS errors, active-window
  vocal scores, and the absence check. Retain raw levels and the removed
  means in the report. Preserve sample positions and the original WAVs.
  Define the outcome for silent and DC-only references so their ratios are
  handled explicitly. **Done (v0.16.0):** report kind
  `harmonic.sam-vocal-benchmark.v2` uses whole-excerpt means and keeps `raw`
  metrics and `means`. Silent, constant-only, and constant-input cases raise
  errors. Covered by `tests/test_sam_benchmark.py`.
- [x] **Re-score the three archived reference runs** (p1) [test]
  Reuse the validated mix, vocal-only, and accompaniment-only outputs under
  `data/aws-gpu/vocal-benchmark-run/output/results/`. Compare with the saved
  `scores/dc-offset-diagnostics.json`. Verify that the regular scorer shows
  the vocal mainly in the residual for the two positive cases and flags
  false extraction on the guitar-only case. Its centered target-to-input RMS
  ratio should be about 96.4%. This validation needs only local files.
  **Done (2026-11-26):** v2 scores in `data/aws-gpu/vocal-benchmark-run/scores-v2/`
  match the diagnostic to four decimals. Vocal residual gains are 0.958 (mix) and
  0.980 (vocal-only), and the residual exceeds the target in all 120 windows.
  Guitar-only gives 96.4% and fails. The earlier guitar controls in
  `data/aws-gpu/vocal-followup/scores-v2/` give 94.0% and 97.1% centered
  (52.2% and 60.6% raw) and also fail.
- [x] **Add a conventional unaccompanied singing reference** (p1) [test]
  Select a clearly licensed recording of conventional singing and pair it
  with an aligned accompaniment reference. Prepare the mixed, vocal-only,
  and accompaniment-only cases. After validating the scorer on archived
  results, use the same prompt and model settings to check whether the
  overtone fixture's failure also appears on this material.
  **Done (2026-11-26):** used MUSDB18 test songs with separate stems (see the
  worker guide). The failure reproduces on conventional singing: vocal-only
  target gain is 0.19 (Arise) and 0.43–0.47 (Al James), with Angels at 0.66–0.94.
  In mixes the vocal is extracted at 0.77–0.97.
- [ ] **Review full-song vocal consistency and seams** (p1) [test]
  Compare the aligned 72–98 second source, vocal target, and residual clips
  in `data/source-check-v0.12.0/vocal-review/`. Check whether a vocal phrase
  fades out of the target or stays in the residual at 80–90 seconds. Then
  review the full tracks and the unnormalized seam clips at 24, 72, 80, 88,
  and 264 seconds in `data/source-check-v0.12.0/seam-review/`. Listening
  review and approval remain incomplete. **Owner finding (2026-11-20):** vocals
  drop out of the reviewed target and remain in the residual. This confirms the
  audible dropout; other seams and the full track still need review.
  On 2026-11-20, the original artifacts were
  recovered from Charon and revalidated on Minerva. A six-clip playlist with
  72–98 and 82–88 second mix/target/residual comparisons is available on both
  computers at `data/recovery-minerva-20261120/listening/review-order.m3u`.
  The full-song vocal-only 20s/2s candidate completed on Blackwell across
  17 chunks. The checksum-verified focused and full-track playlists are under
  `data/aws-gpu/vocal-full-song/listening/` on Minerva and Charon. The owner
  reviewed five focused sections. The 20s candidate had clearer vocal entry
  at 24–36 seconds, improved the main dropout at 78–96 seconds, and stayed
  mostly vocal at 258–270 seconds. Both window lengths left singing in the
  residual at 116–124 seconds. Full-song listening approval remains open.
- [ ] **Establish a consistent context and prompt policy** (p1) [test]
  The 80–90 second repeat reproduced the dropout. The owner heard the phrase
  in the 75–95 second target with bass bleed and quieter vocals in its residual.
  The 78–88 second target mostly contained drums despite its higher RMS.
  In the controlled 75–95 second prompt comparison, the owner preferred
  `man singing`: the vocal phrase came through despite bass bleed and
  faded to a faint echo in its residual. The lead-singing variant isolated
  bass, and the melody/lyrics variant left a clearly audible vocal in the
  residual. In the subsequent 20s/2s seam comparison, the owner heard vocals
  remain audible through the left join and return through the main dropout.
  Vocal level still faded at the left join. Bass leaked into the target and
  the early residual retained some vocal. The owner’s focused full-song
  review favors 20s/2s as the experimental vocal setting. The final shifted
  windows confirmed a known dropout at 116–124 seconds. The earlier shift
  exposed a faint target vocal with a clear vocal in the residual, and the
  later shift extracted bass. Billie Jean tuning is complete.
  **MUSDB18 evidence (2026-11-26):** on a shared 20 s core, 30 s context is
  never better. 10 s and 20 s are within about ±0.03, except bass, where 10 s
  is best (0.94–0.99). The three vocal prompts agree within 0.003 in mixes,
  and `singing voice` was better on the Angels vocal-only case. Remaining
  decision: compare `singing voice` with `man singing` on Billie Jean by
  listening before changing the default prompt, and choose 10 s or 20 s chunks
  (10 s means more seams).
- [x] **Build a reference-based vocal benchmark** (p1) [test]
  Prepare mixture, vocal-only, and accompaniment-only jobs from aligned
  stems. Validate job and result identity, score reference contributions,
  and localize missed vocals on the sample grid. Both saved guitar controls
  failed the absence check. All three prepared reference jobs completed on
  Blackwell and were scored locally.
- [ ] **Check contrasting recordings and absent instruments** (p1) [test]
  The owner heard only singing in the target and only piano in the residual
  at both window lengths in Leon Lishner and Roger Nelson's 26–32 second
  voice-and-piano excerpt. The acoustic-guitar control has substantial
  vocal-target output at both window lengths, which the owner identified
  as guitar in both targets. Its aligned clips are in
  `data/aws-gpu/vocal-followup/listening/instrumental-review.m3u`.
  The three-case benchmark reproduced guitar leakage and found that the
  overtone vocal stayed mainly in the residual, even on its own. Mean-centered
  diagnostics are recorded under `data/aws-gpu/vocal-benchmark-run/scores/`.
  **MUSDB18 absent-target coverage (2026-11-26):** 30 of 31 absent targets
  (vocals, drums, or bass removed, plus instrumental sections) carried 38–77%
  of input RMS. Missing vocals or drums were replaced mainly by bass, and
  missing bass by "other". Quiet passages remain open.
- [x] **Validate instrument-level timing and relative gain** (p1) [test]
  Adapter preservation is verified, but model timing/gain against recognizable
  transients still needs review. Excerpt target-plus-residual lag measured zero
  within ±100 ms; reconstruction RMS error was 0.091–0.093 against source RMS
  0.209 and fitted gain 0.807–0.863. Independently generated residuals need not
  reconstruct exactly. These mix-level diagnostics do not prove source timing
  or justify applying gain corrections. Preserve float peaks above 1.0.
  **Done (2026-11-26):** across 97 MUSDB18 target/stem pairs, 81 have zero lag
  and the maximum is 4 samples (0.08 ms), so no latency correction is needed.
  Mix gains are vocals 0.77–0.97, drums 0.74–0.91, and bass 0.93–0.97. The
  under-extraction varies by song, so no gain correction is applied.
- [x] **Add a source-presence signal for absent targets** (p1) [feature]
  SAM always returns content for a prompt; the absent-target MUSDB18 cases
  measured 38–77% of input RMS, mostly bass. Target RMS cannot show whether a
  source is present. Evaluate cues such as similarity between the vocal and
  bass targets, or agreement across prompts (only the mismatched-gender prompt
  produced silence). Then expose a per-window presence flag in source features
  so scenes do not animate "vocals" from bass.
  **Offline cue study (2026-11-26, `data/aws-gpu/musdb-run/presence*.py`):**
  per 1 s window, target RMS cannot separate present from absent vocals
  (AUC 0.47). The target's energy fraction below 150 Hz scores AUC 0.92, and
  correlation with other targets scores 0.89 for vocals and 0.83 for drums.
  A leave-one-song-out logistic model reaches held-out AUC 0.96–0.98 on the
  sung tracks, but classified the electronic instrumental (vocal target
  filled by a synth line) as vocal in 100% of windows, and drums on reggae
  reached only 0.65. Hand-built cues catch the bass fill-in, not melodic
  fill-ins.
  **Span predictor (2026-11-26, `data/aws-gpu/musdb-spans-run/`):** zero-shot
  per-window AUC is 0.95 for vocals, 0.93 for drums, and 0.91 for bass. It
  rejected all 30 electronic-instrumental vocal windows. Vocals at threshold 0.2
  keep 88% of present windows and reject 92% of absent ones. Bass absence stays
  weak (at most 64% rejected). Anchored separation (`predict_spans=True`) does
  not reduce fill-in, so keep separation unanchored.
  **Done (2026-11-26, v0.18.0):** the worker measures per-frame presence for
  every prompt with the pinned predictor; reports, song stitching, and schema-3
  bundles carry raw probabilities with provenance; older results read as
  presence unknown; bass is flagged `low_confidence`; the source inspector
  shows the probability. Verified end to end on a Blackwell GPU.
- [ ] **Choose per-source presence thresholds for scenes** (p2) [feature]
  The bundle stores raw probabilities. Pick scene thresholds (vocals about 0.2
  on MUSDB18) and decide how scenes treat `low_confidence` bass and
  `unbenchmarked` prompts. Validate on Billie Jean by listening.
- [x] **Measure 1080p frame times and output latency on the desktop** (p1) [perf]
  Measure target-GPU frame times, stutters, and physical-output timing after
  seeks. Investigate the known GLX search-path warning involving `~/.local/lib`.
  Existing software-renderer and dummy-audio checks are separate evidence.
  **Done (v0.19.0):** `just perf-desktop` on the GTX 960 (580.178.04, i3 +
  picom, 2560x1440 at 59.95 Hz, other GPU clients running), evidence in
  `data/perf/v0.18.0-20261126-110817/`. Graphs and the light and median presets
  hold 59.1-59.7 fps in a floated 1920x1080 window and at 1440p fullscreen (GPU
  p99 6-11 ms); the heaviest preset runs at 14.9 fps (1080p) and 9.9 fps
  (1440p). Output latency is a software-chain estimate only (see the loopback
  item). The GLX runtime-path warning no longer appears: `~/.local/lib` holds no
  GL libraries.
- [x] **Calibrate the audio/picture offset per output device** (p1) [bug]
  The clock subtracts only SDL's 16 ms device buffer. The ALSA hardware queue
  behind PipeWire holds a median 28-29 ms, and the picture needs at least one
  16.7 ms refresh plus a picom frame when windowed. The real offset is unknown in
  size and sign (v0.19.0 wrongly reported a 12 ms lower bound), and SDL exposes
  no output latency, so a fixed correction would be a guess.
  **Done (v0.20.0):** **S** saves the current offset for the active
  `<driver>/<device>` in `$XDG_CONFIG_HOME/harmonic/calibration.json`. The
  saved offset is applied at startup, `--offset-ms` overrides it, and
  `--offset-ms N --save-offset` saves one without playing. Frame reports
  record the applied offset and its source. The owner still needs to save a
  value for the Xonar output.
- [ ] **Measure physical audio/picture offset with a loopback** (p1) [test]
  Saved offsets are tuned by ear. The frame report adds up reported queues
  only; DAC, sound-server buffering beyond ALSA, and panel latency are
  unmeasured. Add a flash-and-click calibration view, record it with a camera
  or microphone at the desk, and save the result with `--save-offset`.
- [ ] **Accept preset seek latency; revisit with drag-to-scrub** (p3) [perf]
  Every seek with a preset leaves a 93-110 ms gap before the next presented
  frame (preset reset and first draw while the clock is held; graphs-only seeks
  settle in about 33 ms). Keep showing the last frame or the graphs while the
  preset resets, or reset without recompiling shaders.
  **Profiled 2026-11-26 (GTX 960, warm driver shader cache):** every seek runs
  `restart()`, which destroys and recreates the projectM engine.
  `projectm_create()` alone takes 70-80 ms. Loading the preset adds 3-11 ms
  (light/median presets) or 54-61 ms (heaviest), and the first frame 4-7 ms
  or about 55 ms. Reloading into the same engine plus one frame costs only
  6-17 ms for light and median presets, but it is not a fresh history: the old
  feedback image carries over (a reloaded engine differs from a fresh one
  10-60 times more than two fresh engines do). **Owner decision needed:**
  (a) reuse the engine and accept carried-over feedback (about 10-17 ms
  freeze); (b) keep fresh history and show the last frame or graphs during the
  ~80 ms reset (the frame is still blocked, so playback hitches either way);
  (c) keep a pre-created spare engine (moves the 75 ms creation to an idle
  frame, which hitches later instead). A cold shader cache made the heaviest
  preset's first load take 4.2 s.
  **Decision (2026-11-26, owner agreed):** keep the fresh-history restart. The
  audio clock is held during the reset, so picture and sound resume together:
  the cost is seek latency (117-133 ms with a preset, 33 ms without), not a
  playback hitch, and only discrete seeks (arrows, Home, click) trigger it.
  Fresh history keeps a position's image independent of how it was reached.
  The alternatives either give that up or move the stall into playback.
  Revisit if drag-to-scrub is added: reuse the engine while dragging and do one
  fresh restart on release. In-playback preset switching (scene controller)
  uses projectM's own transitions and is unaffected.
- [ ] **Set a preset GPU budget for the GTX 960** (p2) [perf]
  The heaviest library preset needs GPU p99 59 ms at 1080p and 94 ms at 1440p.
  Use per-preset GPU time from frame reports to filter or rank presets before
  the scene controller picks them.
- [ ] **Re-measure frame pacing on a quiet desktop** (p3) [test]
  Steady playback still shows 1-4 stalls a minute (47-121 ms) with the swap
  call blocked while CPU and GPU time stay small. picom, Chrome, glava, and four
  mpv clients shared the GPU. Repeat `just perf-desktop` with them closed, and
  once without picom, to separate desktop load from the player.
  **Partial (2026-11-26, `data/perf/v0.22.2-20261126-164659/`):** glava was
  paused for the run. The animated backdrop (xwinwrap + mpv) was also paused,
  but its node supervisor restarted it within 5 s, before the first scenario,
  so the backdrop video kept playing. With only glava paused, the 1080p window
  went from 10-20 to 2 missed vsyncs a minute (interval p99 about 20.5 to
  18.7 ms), but one swap-blocked stall a minute (45-56 ms) remains.
  Fullscreen 1440p still has 14-15 missed vsyncs and 3 stalls a minute.
  Remaining: stop the backdrop through its supervisor (pausing mpv makes it
  restart the backdrop) and measure once without picom.

## Processing reliability and scale (P2)

- [ ] **Define shared SAM cache and cross-version compatibility** (p2) [feature]
  Job-local resume validates code and recorded runtime identity. Evaluate
  content-level dependency fingerprints and compatibility across versions before
  registering SAM artifacts in the mix-only catalog. Full source hashes also
  invalidate reuse after docstring edits.
- [ ] **Evaluate finer checkpoints and OOM recovery** (p2) [feature]
  Per-prompt checkpoints now atomically preserve completed target/residual pairs,
  validate their run binding and audio on resume, and skip completed prompts.
  Synthetic interruption/OOM recovery is tested. Validate real CUDA OOM recovery
  and account for startup/model scratch outside the bound output.
- [x] **Keep Python and native provenance validation in agreement** (p2) [test]
  Shared full-song bundle fixtures verify that both readers reject missing chunk
  indices, invalid job/model/worker hashes, mismatched run bindings, malformed
  auxiliary revisions, invalid codec hops, inconsistent chunk prompts, missing
  trim metadata, and negative levels.
- [x] **Set up Claude Code project files and GitHub release publishing** (p2) [chore]
  `CLAUDE.md` imports `AGENTS.md` and adds Claude-specific notes, and
  `.claude/settings.json` holds the command allowlist. `just release` now
  fetches tags, accepts a summary and trailer, and runs `just publish-release`,
  which builds notes from `scripts/version.py notes` (covered by
  `tests/test_version.py`).
- [ ] **Bound memory for long recordings** (p2) [perf]
  Worker plan validation and inspection now stream PCM checks by chunk.
  Stitching now bounds float64 scratch to a chunk/overlap and measures levels
  blockwise; its mono source and float32 outputs still grow with track length.
  Feature extraction and playback still load whole tracks. Continue reducing
  those allocations; the broader bounded-memory task remains incomplete.
- [ ] **Add validated artifact retention and cleanup policies** (p2) [feature]
  Keep current benchmark WAVs/jobs for quality review. Delete separated audio
  only after validating durable features/provenance and confirming retention
  needs; distinguish raw inference cache from reusable feature artifacts.
- [ ] **Review licenses before distribution or service use** (p2) [docs]
  The SAM License was inspected for the local prototype; Perception Models and
  ImageBind have noncommercial terms. Resolve dependency use, output reuse,
  binary/model redistribution, and service permissions before packaging.

- [x] **Clean prompt scratch directories whose suffix contains `_`** (p2) [bug]
  `workers/sam_audio/worker.py:293` matches `-[a-z0-9]{8}`, but `tempfile.mkdtemp`
  suffixes also use `_`, so about 20% of abandoned prompt checkpoints survive
  resume. Use `[a-z0-9_]{8}` like the chunk regex at line 280 and add an
  underscore case to `tests/test_sam_chunks.py` (around line 352).
- [x] **Pin the auxiliary T5 revision for excerpt runs** (p2) [bug]
  `worker.py run()` defaults `text_revision` to None and `just sam-run` passes
  none, so excerpt runs resolve the current T5 head. Song plans already pin
  `sam_chunks.TEXT_REVISION`. Store the revision in excerpt jobs or default it,
  and expose it in the recipe so excerpt results stay comparable.
- [x] **Fail releases when integration tests are skipped** (p2) [test]
  Native, FFmpeg, and projectM tests use `skipUnless`, so `just release` can
  publish on a host without ffmpeg or a player build. Add an opt-in flag (for
  example `HARMONIC_REQUIRE_INTEGRATION=1`, set by `release`) that turns those
  skips into failures, or at least report the skip count.
- [x] **Cover the remaining `harmonic-sam` subcommands and benchmark edges** (p2) [test]
  No argparse-level tests for `prepare-vocal-benchmark`, `benchmark-vocals`,
  `stitch`, `validate-song`, `inspect-song`, or `--target` parsing
  (`sam_cli.py`). `tests/test_sam_benchmark.py` lacks unequal stems, excerpts
  past the stem end, rank-deficient gain fits, silent references, and argument
  checks (`sam_benchmark.py:21-90`).

- [x] **Make the MUSDB multi-target benchmark a project command** (p2) [feature]
  `data/aws-gpu/musdb-run/{prepare,score,context}.py` are local evidence
  scripts. Move stem extraction, case generation, lag-aligned multi-stem
  scoring, and the common-core context comparison into `harmonic_analysis`
  with tests and `just` recipes, so future model or prompt changes can be
  re-run the same way.
  **Done (v0.22.0):** `harmonic_analysis.sam_musdb` with `prepare-musdb`,
  `score-musdb`, and `musdb-context` (`just sam-musdb-*`). From the md5-verified
  zip it reproduces the archived run's references, job inputs, scores, and
  context comparison exactly. Silent present targets now score as dropouts.

## Local experience and integration (P2)

- [ ] **Import line-timed lyrics with manual timing correction** (p2) [feature]
  Preserve recording identity, lyric provenance, and user adjustments.
- [ ] **Support Unicode text rendering** (p2) [feature]
  Replace the ASCII bitmap font before translated lyrics/non-ASCII metadata.
- [ ] **Evaluate one mood/genre tagger** (p2) [feature]
  Recheck provider availability/terms, retain scored labels and provenance, and
  keep inferred context distinct from measured activity and user overrides.
- [ ] **Add a small scene controller and palette mappings** (p2) [feature]
  Start with restrained transitions using existing mix/source features.
- [ ] **Connect catalog selection to playback** (p2) [feature]
  Select a registered bundle/location and add playlist navigation while retaining
  checksum validation. SAM catalog support depends on complete provenance keys.
- [ ] **Make todo-fzf clipboard shortcuts portable** (p2) [bug]
  Verify Ctrl-Y/Alt-Y with `~/.shell/scripts/clip/pushclip.sh` here and provide a
  supported fallback elsewhere. Interactive prompt pasting awaits owner use;
  do not submit copied text to another pane.

## Later milestones (P3)

- [ ] **Build spatial, radial, and vocal/lyric scenes** (p3) [feature]
  Use validated source features and measure transitions on the target GPU.
- [ ] **Add resumable library processing and resource accounting** (p3) [perf]
  Establish single-recording quality first, then concurrency/memory limits,
  runtime/storage/cost reporting, cancellation, and queue recovery.
- [ ] **Build the authenticated metadata/artifact service** (p3) [feature]
  Resolve recording matching and redistribution permissions first; do not
  distribute original recordings. Other-platform packaging is still unverified.
- [ ] **Compare alternate checkpoints or separators when useful** (p3) [test]
  Smaller SAM checkpoints, Demucs, or paid services can provide controlled
  references if access, licensing, capacity, and the quality question warrant it.

- [x] **Return clean errors for malformed stitch completion records** (p3) [bug]
  `sam_chunks.py:357-358` indexes `run["plan_sha256"]` directly; a missing key
  or a non-object JSON raises KeyError/TypeError past the CLI's OSError and
  ValueError handler (`sam_cli.py:278`). Wrap the read in ValueError.
- [x] **Re-check WAV digests when scoring the benchmark** (p3) [bug]
  `sam_benchmark.py:92-93` reads the target/residual again after validation
  without comparing them to the report sha256 (stitching does), and a
  `struct.error` from `read_wave` reaches the user as a traceback.
- [x] **Record stem provenance in benchmark jobs and scores** (p3) [feature]
  `sam_benchmark.py:43-44` stores a placeholder source path and only the PCM
  hash. Store each stem's path, sha256, and PCM sha256 so archived scores trace
  back to their source assets.
  **Done (v0.21.0):** cases record `source.stems` (path, sha256, PCM sha256);
  mixed scoring refuses unrecorded stems and reports `reference_stems`.
- [x] **Add just recipes for the vocal benchmark** (p3) [docs]
  Only `sam-vocal-control` exists. `workers/sam_audio/README.md:524-527` calls
  `harmonic-sam prepare-vocal-benchmark` and `benchmark-vocals --case mix`
  directly. Add recipes for preparing and scoring each case and update the README.
- [x] **Honor `HARMONIC_PLAYER` in the chunk tests** (p3) [test]
  `tests/test_sam_chunks.py:28` hard-codes `build/harmonic-player`, while the
  other test files accept the override.
- [ ] **Shorten the MUSDB scoring tests** (p3) [test]
  `tests/test_sam_musdb.py` takes about 75-90 s of the 134 s suite: scoring a
  fixed 20 s case costs about 3.5 s (window lstsq and 2M-point FFTs). Allow a
  shorter core for synthetic tests (a module-level length the tests override)
  or score fewer targets per job, keeping one full-length case.
- [x] **Add CI for the Python tests and native build** (p3) [chore]
  No `.github/` workflows exist; only a local `just release` runs the suite.
  A minimal workflow with ffmpeg installed and projectM optional would catch
  regressions between releases.
  **Done (v0.21.1):** `.github/workflows/ci.yml` builds SDL3 and the player on
  `ubuntu-24.04` and runs `just test` with `HARMONIC_REQUIRE_INTEGRATION=1`
  (offscreen video, dummy audio). Verified on a temporary branch before release.
- [ ] **Backfill GitHub releases for existing tags** (p3) [chore]
  Tags v0.2.0 through v0.14.2 have no GitHub releases. `just publish-release
  X.Y.Z` creates one from CHANGELOG.md. This is outward-facing, so it waits for
  owner approval.
- [x] **Update stale schema references in README** (p3) [docs]
  The heading at `README.md:560` still reads "schema versions 1 and 2" though
  the section documents schema 3, and `README.md:655` says validated SAM
  outputs adapt into schema-2 bundles; the adapter writes schema 3 since
  v0.18.0. Retitle the section and update the sentence.
  **Done (v0.20.1).**

## Completed

### Verified foundation (completed 2026-11-26)


- [x] **Resume SAM song chunks at prompt boundaries** (p2) [feature]
  Each completed target/residual pair is checkpointed atomically under its
  unfinished chunk. Restart verifies job/run identity, prompt, WAV checksums,
  lengths, levels, and reconstruction statistics, then reruns only unfinished
  prompts. Synthetic interruption/OOM and checkpoint-corruption cases pass.
  Real GPU OOM recovery remains an open validation item above.

- [x] **Reduce full-song stitching scratch memory without changing audio** (p2) [perf]
  Chunk-sized float64 overlap-add, direct mono plan loading, blockwise statistics,
  and direct WAV writes lower peak RSS from 1,087.5 to 280.4 MiB in one local
  full-song restitch including validation. All six WAV hashes match the original
  benchmark and all 216 overlap diagnostics match. Checks cover short/single
  chunks, one-sample final tails, bad fade weights, padding, and exact WAV bytes.
  Measured evidence is in `data/stitch-memory-20261120/`; full-song float32 arrays
  remain and the broader memory task stays open above.

- [x] **Recover and validate Minerva's SAM benchmark artifacts** (p2) [chore]
  Copied 422 files (1,001,872,094 bytes) from Charon without overwriting files;
  every SHA-256 matched. Revalidated 37 raw chunk results, the three full-song
  target/residual pairs, the original excerpt, four context jobs, and native
  source features. Recomputed both vocal fades exactly and verified the
  unblended 82–88 second center matches the raw chunk sample for sample.
  Transfer/validation reports and the listening packet are under
  `data/recovery-minerva-20261120/`. The 12-file listening packet and reports
  were copied back to Charon and independently checked by SHA-256.
  Full-song listening approval and context inference remain open above.

- [x] **Install and verify Minerva's projectM playback setup** (p2) [chore]
  Local projectM 4.2.0 revision `9e26f5b5bf89b015f197a16a61bcb21f4946d985`
  enables the preset player/checker. All 63 tests pass (9 optional global-tool
  skips); a 180-frame 1080p diagnostic preset passed on the GTX 960, with
  1.64 ms mean and 2.33 ms p95 completed-render time after 30 warmup frames.
  This single-preset offscreen check does not establish general preset performance
  or physical-output latency. Evidence: `data/minerva-projectm-check-20261120/`.
- [x] **Install Minerva's isolated SAM dependencies** (p2) [chore]
  `just sam-sync` installs the locked Python 3.11/CUDA 12.8 environment.
  SAM Audio/processor, TorchCodec, and xformers imports pass.
  GPU inference remains blocked: the GTX 960's `sm_52` is excluded from the
  wheel's compiled architectures; a tiny CUDA operation fails with no kernel
  image. Hugging Face authentication is absent. No model weights were downloaded.

- [x] **Validate song plans without allocating a full PCM track in the worker** (p2) [perf]
  Keep an overlap tail and hash each new sample exactly once. Tests cover the
  bounded validator, conflicting overlap bytes, and the full PCM hash.

- [x] **Bind SAM resume to imported code and runtime identity** (p2) [bug]
  Reject changed local worker modules, runtime fingerprints, and mismatched chunk
  binding hashes before reuse. Both readers retain support for legacy reports.

- [x] **Report full-song run stages and end-to-end timing** (p2) [perf]
  The CLI reports elapsed time through publication and lock release, and the
  completion report keeps per-invocation stage timings. Cached runs explicitly
  record zero model-setup and inference-stage time. The guide explains the
  historical timer, uncentered correlation, and bounded seam lag search.

- [x] **Clean up abandoned files inside a bound full-song output** (p2) [bug]
  Restart removes incomplete worker scratch under the lock after provenance
  checks. Tests verify chunk reuse and preserve unrecognized files and symlinks.

- [x] **Prevent concurrent writers to a full-song SAM output** (p2) [bug]
  Competing workers fail before preflight, including when they use a symlink to
  the same output. A process-kill check verifies the next worker can acquire
  the lock and publish results. A subsequent invocation reuses those chunks.

- [x] **Recognize song plans by payload kind in the feature adapter** (p2) [bug]
  `sam-features` accepts a valid renamed plan and produces the same feature
  data as the conventional filename.

- [x] **Build the analyzer and native original-mix player** (p2) [feature]
  JSON/Arrow features preserve a 48 kHz sample timeline, source/artifact/PCM
  checksums, RMS/peak/onsets, 64 frequency bands, and embedded tags.
- [x] **Verify transport and visible playback controls** (p1) [test]
  Owner confirmed physical Billie Jean playback and desktop controls/EOF.
  Automated dummy-audio seeking, pause/resume, offsets, and EOF also pass.
- [x] **Integrate projectM and graph compositing** (p2) [feature]
  Verify preset views, cached pause frames, seek/reset behavior, resize, EOF,
  offscreen previews, and base-player operation without optional projectM.
- [x] **Implement the local recording catalog and verified mix reuse** (p2) [feature]
  Exact-file identity, relocated sources, corrupt-cache rejection, configuration
  checks, and interrupted registration recovery are covered.
- [x] **Establish task, progress, and release tooling** (p2) [chore]
  just commands, colored progress/logs/exit codes, synchronized SemVer, dated
  changelog, annotated tags, atomic pushes, and published-commit builds.
- [x] **Provide global checklist viewing and fzf completion** (p2) [feature]
  Safe installation, priorities/categories, incomplete filtering, --all,
  previews/reload, and stale-safe Ctrl-D completion were verified. Optional
  external viewer integrations are separate from application tests.
- [x] **Isolate and pin the SAM GPU runtime** (p1) [feature]
  Python 3.11/CUDA 12.8 worker with pinned model/source/lock and auxiliary text
  revision; no model weights installed locally. Minerva's isolated environment
  is installed, with its GPU limitations recorded above.
- [x] **Verify authentication and real GPU inference** (p1) [test]
  AWS Blackwell g7e.4xlarge passed CUDA/import/auth checks and actual inference.
  L40S capacity was unavailable; no L40S or longer-context profile is claimed.
- [x] **Benchmark and validate the original excerpt** (p1) [test]
  Three prompts, 5.319 seconds total separation; exact 480,000-sample mono WAVs,
  hash/provenance/padding checks, and owner-approved clear targets/clean residuals.
- [x] **Preserve source-feature sample positions and mono levels** (p2) [test]
  All six real excerpt streams passed 3,000 RMS/peak window checks (maximum RMS
  error below 1.5e-8, exact peaks). Anti-phase cancellation and float peaks are
  explicit; no automatic gain or model-latency correction is applied.
- [x] **Version and display multi-source feature bundles** (p2) [feature]
  Schema 2 adds retained reports and target/residual Arrow streams. Python/native
  validation and R-toggle cards support partial/full coverage; schema 1 stays
  readable. Original stereo mix remains playback/projectM audio.
- [x] **Implement and exercise full-song chunks, stitching, and resume** (p2) [feature]
  37 chunks/111 calls, 165.206 seconds separation, 19.074 GiB peak reserved GPU
  memory, 29.878 GiB peak host RSS. All 37 chunks reused on restart; full-length
  WAVs/features/native compositor validated. Listening quality is pending above.
- [x] **Trace the weak vocal interval to the raw chunk estimate** (p1) [test]
  Compared all 37 raw chunks. The 80–90 second target RMS is 2.1% of mix RMS,
  versus 32.9% for the next lowest chunk. Recomputed both fades exactly and
  confirmed that the stitched 82–88 second center copies the raw estimate.
  Saved aligned 72–98 second clips at original levels for listening review.
- [x] **Retrieve results and remove temporary AWS resources** (p1) [chore]
  Both runs retrieved/validated; full-song transfer checked all 275 output files.
  Instances/disks, buckets, token parameters, roles/profiles, templates, and
  security groups removed; final queries found no active test hosts/tagged disks.
- [x] **Verify the v0.12.0 automated release suite** (p2) [test]
  59 tests ran successfully with 9 optional external-tool integrations skipped.
  Real GPU evidence and owner listening approval are recorded separately above.
- [x] **Reassess documentation and the running backlog** (p2) [docs]
  Review implementation/evidence after v0.12.0, remove stale future-work/access
  claims, prioritize vocal consistency, and record reliability/scale follow-ups.
