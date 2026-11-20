# Task checklist

Use this file for current progress, [README.md](README.md) for implemented behavior,
and [PLAN.md](PLAN.md) for architecture. Check off only verified work and update
this file with each approved change. Reassessed after publishing v0.12.0 on
2026-11-19; historical release details are in [CHANGELOG.md](CHANGELOG.md).

- **P1 `(p1)`**: next quality gates and validation that unblock the SAM milestone.
- **P2 `(p2)`**: reliability, local improvements, and later integration work.
- **P3 `(p3)`**: deferred scenes, library scale, services, and comparisons.

Categories are `[feature]`, `[test]`, `[perf]`, `[bug]`, `[docs]`, and `[chore]`.
`☐` means incomplete; `☑` means completed. Global `todo-status` and `todo-fzf`
show incomplete tasks by default; use `--all` for completed tasks or `--help` for
options. `just todo` retains the complete Markdown checklist.

**Current gate:** full-song processing is structurally validated, with listening
and vocal consistency still open. The 295.892-second Billie Jean recording ran
as 37 chunks (10 seconds, 2-second overlap) on AWS Blackwell; all 111 prompt calls,
exact-length merged WAVs, source features, and native compositor checks passed.
A second invocation reused all 37 chunks without inference. Neighboring vocal
estimates disagree sharply around 80–90 seconds. The owner approved clear targets
and clean residuals for the earlier 30–40 second excerpt only. All temporary AWS
resources were removed after verified retrieval. Local evidence is ignored by
Git; see the [worker guide](workers/sam_audio/README.md) for paths and limits.

## Separation quality and playback gates (P1)

- [ ] **Review full-song vocal consistency and seams** (p1) [test]
  Compare the aligned 72–98 second source, vocal target, and residual clips
  in `data/source-check-v0.12.0/vocal-review/`. Check whether a vocal phrase
  fades out of the target or stays in the residual at 80–90 seconds. Then
  review the full tracks and the unnormalized seam clips at 24, 72, 80, 88,
  and 264 seconds in `data/source-check-v0.12.0/seam-review/`. Listening
  findings and approval are pending.
- [ ] **Establish a consistent context and prompt policy** (p1) [test]
  First repeat the raw 80–90 second job at the same settings, then compare
  shifted 10-second windows and a 20-second window over their shared 82–88
  second interval. Hold the checkpoint, prompt, and seed constant to isolate
  input context. Compare targets and residuals at their original levels and
  sample positions. Profile memory and evaluate anchors/span settings separately
  if context changes leave the dropout unresolved.
  Verified comparison inputs are ready in `data/sam-jobs/billie-jean-vocal-context/`.
  Use the original pinned auxiliary text revision on the GPU host.
  **Blocked (2026-11-19):** AWS Organizations policy `p-kkr52ast` explicitly
  denied `ec2:RunInstances` through `DenyCompute`. The comparison produced
  no inference results. An organization administrator must authorize the EC2
  launch, or the comparison needs another approved GPU host. Temporary AWS
  resources were removed. Run details are in `data/aws-gpu/vocal-context/`.
- [ ] **Check contrasting recordings and absent instruments** (p1) [test]
  Billie Jean is the only supplied real recording. Include a cappella,
  instrumental, quiet passages, and absent requested instruments to expose
  false extraction, dropouts, and misleading visual activity. Synthetic tests
  and one approved excerpt do not complete this gate.
- [ ] **Validate instrument-level timing and relative gain** (p1) [test]
  Adapter preservation is verified, but model timing/gain against recognizable
  transients still needs review. Excerpt target-plus-residual lag measured zero
  within ±100 ms; reconstruction RMS error was 0.091–0.093 against source RMS
  0.209 and fitted gain 0.807–0.863. Independently generated residuals need not
  reconstruct exactly. These mix-level diagnostics do not prove source timing
  or justify applying gain corrections. Preserve float peaks above 1.0.
- [ ] **Measure 1080p frame times and output latency on the desktop** (p1) [perf]
  Measure target-GPU frame times, stutters, and physical-output timing after
  seeks. Investigate the known GLX search-path warning involving `~/.local/lib`.
  Existing software-renderer and dummy-audio checks are separate evidence.

## Processing reliability and scale (P2)

- [ ] **Complete SAM provenance keys before shared or cross-version reuse** (p2) [feature]
  Job-local resume binds plan SHA, worker.py SHA, uv.lock SHA, and text revision,
  and validates chunk artifacts. Imported analyzer modules and runtime equality
  are not bound. Include effective code/runtime, recording/sample coordinates,
  models/auxiliaries, prompts/anchors, settings/seed, and schema. Hashing the whole
  worker file also invalidates resume after documentation-only edits; make the
  compatibility policy explicit. The mix-only catalog still rejects schema 2.
- [ ] **Evaluate finer checkpoints and OOM recovery** (p2) [feature]
  Completed-chunk resume is verified; an unfinished chunk reruns every prompt.
  Evaluate per-prompt checkpoints, startup/model scratch outside the bound
  output, and recovery after GPU OOM.
- [ ] **Keep Python and native provenance validation in agreement** (p2) [test]
  Shared fixtures cover missing retained chunk indices and invalid retained job
  hashes. Extend them for other missing or inconsistent metadata, silent
  targets, uneven final chunks, and corruption as both readers evolve.
- [ ] **Bound memory for long recordings** (p2) [perf]
  Plan validation reconstructs full stereo PCM; stitching uses whole-track
  accumulators, and feature extraction/player decoding also load whole tracks.
  GPU chunks alone do not bound local RAM. Measure long-recording limits and
  stream/seek local processing before treating the workflow as library-ready.
- [ ] **Report end-to-end timing and clarify seam metrics** (p2) [perf]
  Invocation elapsed fields exclude readiness, initial validation, and reuse
  scans. Add total command/stage timings before comparing cold and cached runs.
  `zero_lag_correlation` is an uncentered normalized dot product; the lag search
  is bounded to at most ±40 ms. Neither proves perceptual continuity or latency.
- [ ] **Add validated artifact retention and cleanup policies** (p2) [feature]
  Keep current benchmark WAVs/jobs for quality review. Delete separated audio
  only after validating durable features/provenance and confirming retention
  needs; distinguish raw inference cache from reusable feature artifacts.
- [ ] **Review licenses before distribution or service use** (p2) [docs]
  The SAM License was inspected for the local prototype; Perception Models and
  ImageBind have noncommercial terms. Resolve dependency use, output reuse,
  binary/model redistribution, and service permissions before packaging.

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

## Verified foundation

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
  revision; no model weights or inference environment installed on this laptop.
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
