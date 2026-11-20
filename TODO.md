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
  Listen to the full targets/residuals and unnormalized left/right/blended/mix
  clips at 24, 72, 80, 88, and 264 seconds in
  `data/source-check-v0.12.0/seam-review/`. At 80–82 seconds neighboring vocal
  RMS values are 0.102 and 0.000106; at 88–90 seconds they differ by 26.6 times.
  These are diagnostic disagreements, not proof of an audible defect or a
  ground-truth quality score. Record listening findings before bulk processing.
- [ ] **Establish a consistent context and prompt policy** (p1) [test]
  Investigate the near-silent vocal estimate in the 80–90 second chunk. Compare
  longer contexts/overlaps and, if justified, anchors/span settings against the
  baseline while retaining raw gain and sample positions. Profile extra model
  dependencies and memory before enabling them. Do not mask disagreement with
  automatic level matching or time shifts; validate any changed policy by ear.
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
- [ ] **Harden interruption recovery and single-writer behavior** (p2) [feature]
  Completed-chunk resume is verified; an unfinished chunk reruns every prompt.
  Add finer checkpoints if worthwhile, explicit concurrent-writer protection,
  crash-leftover cleanup, and interruption/OOM recovery tests. Currently use one
  worker per output directory; there is no lock or automatic orphan cleanup.
- [ ] **Recognize song plans by payload kind in the feature adapter** (p2) [bug]
  `sam-features` detects a song by directory/filename `plan.json`, whereas
  `inspect-song` accepts an explicitly named plan file. A renamed valid plan is
  misclassified as an excerpt. Dispatch by validated kind and cover both forms.
- [ ] **Keep Python and native provenance validation in agreement** (p2) [test]
  Extend shared malformed-input fixtures for retained chunk reports, missing or
  inconsistent metadata, silent targets, uneven final chunks, and corruption.
  Maintain rejection parity as the duplicated readers and schemas evolve.
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
