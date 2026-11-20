# SAM Audio excerpt and full-song worker

The owner has access to [`facebook/sam-audio-large-tv`](https://huggingface.co/facebook/sam-audio-large-tv).
This directory prepares a **Linux x86_64 GPU worker** separate from Harmonic's
analyzer/player environment. The locked runtime, package imports, CUDA operation,
checkpoint authentication, and three prompted separations passed on an AWS
NVIDIA Blackwell worker on 2026-11-19. Returned artifacts passed validation;
the owner approved the three excerpt target/residual pairs by listening. The
v0.12.0 full-song run also passed artifact/feature checks and chunk resume; vocal
consistency, seam listening, and detailed alignment/gain review remain open. No model weights were downloaded locally.

The local machine exposes Intel Iris Xe graphics, 16 GB RAM, and no working CUDA
device. The selected `checkpoint.pt` alone is 14,861,356,211 bytes (14.86 GB), before
auxiliary models and initialization/activation memory. There is no verified VRAM
or host-RAM minimum for this checkpoint here. Use a GPU host with suitable capacity
and a driver supporting the pinned CUDA 12.8 wheels. TorchCodec also requires
compatible shared FFmpeg libraries; see its [installation guide](https://github.com/meta-pytorch/torchcodec#installing-torchcodec).

## Prepare locally

```sh
just sam-prepare 'data/tracks/Michael Jackson - Billie Jean.mp3' \
  data/sam-jobs/billie-jean-v0.7.0 30 10
```

The supplied recording already has a prepared 10-second job at
`data/sam-jobs/billie-jean-v0.7.0/`. Preparing requires a new output directory.
The job contains `job.json` and `input.npy`: a stereo float32 excerpt from the
canonical 48 kHz decode, original file/PCM checksums, integer source sample offset,
model/code revisions, prompts, and seed. Default prompts are `man singing`,
`drums playing`, and `bass guitar playing`. To replace them:

```sh
.venv/bin/harmonic-sam prepare '/path/track.flac' --output data/sam-jobs/custom \
  --start 20 --duration 8 --target piano='piano playing' --target vocals='woman singing'
.venv/bin/harmonic-sam inspect data/sam-jobs/custom
```

Excerpts are capped at 30 seconds for the initial experiment. Only the job
directory needs transferring to the GPU host; the full original recording is not
required there. Transfer is manual; these commands do not upload audio or start
paid infrastructure. Keep both files unchanged when copying a job.

## Set up and run on the GPU host

### AWS preparation status (2026-11-19)

AWS credentials and the applied On-Demand G/VT quota in `us-east-2` are verified.
The quota is now **16 vCPUs**. Request
`ed60a5c9da934e36bad6a3d48ebdd8953QpyhnV2` is `CASE_CLOSED`; the applied quota,
rather than the request status alone, confirms the increase:

```sh
aws service-quotas get-requested-service-quota-change --region us-east-2 \
  --request-id ed60a5c9da934e36bad6a3d48ebdd8953QpyhnV2
aws service-quotas get-service-quota --region us-east-2 \
  --service-code ec2 --quota-code L-DB2E81BA
aws freetier get-account-plan-state --region us-east-1
```

The selected candidate is one `g6e.4xlarge`: NVIDIA L40S (45,776 MiB reported
GPU memory), 128 GiB host RAM, and 16 vCPUs. The Price List API quoted
$3.00424 per Linux On-Demand instance hour in Ohio on 2026-11-19, before storage
and networking. Regional support does not reserve capacity or prove model fit.

The first launch was rejected with `InvalidParameterCombination` because the
account was on the **Free plan**, which excludes this GPU instance. A quota
increase does not remove account-plan restrictions. The owner approved and
completed a console upgrade to the Paid plan after the upgrade API returned
`ResourceNotFoundException`. The account plan is now `PAID` / `ACTIVE`.
Remaining credits carry over; usage beyond applicable credits becomes billable.
See [AWS account-plan documentation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html).

Both `g6e.4xlarge` and `g6e.2xlarge` returned `InsufficientInstanceCapacity` in
all three Ohio availability zones. Omitting the zone for `g6e.4xlarge` also
failed. A `g7e.4xlarge` launched in `us-east-2c`: NVIDIA RTX PRO 6000 Blackwell
Server Edition (97,887 MiB reported GPU memory), driver 595.112.07, 128 GiB
nominal host RAM, and 142 GiB initially available root disk space. The Price
List API quoted $3.99816 per Linux On-Demand hour before storage/networking.
The locked runtime and CUDA tensor operation passed, and the model completed
the prepared excerpt. The subsequent full-song profile is recorded below;
L40S compatibility and longer chunk settings remain unverified.

The worker uses Amazon-owned Deep Learning Base OSS NVIDIA Driver Ubuntu 24.04
x86_64 AMI `ami-0d869b870d11ff1da` (2026-11-17), an encrypted 200 GiB gp3 root
volume with deletion on termination, IMDSv2, and Session Manager access with no
inbound ports. A two-hour shutdown timer was verified active. Resolve the
current AMI and pricing again on future launches. Retrieve logs and results
before terminating the worker; stopping alone leaves billable storage.

A private temporary transfer bucket, scoped EC2/SSM role and instance profile,
security group, and launch template supported the run. The instance, root
volume, transfer bucket, SecureString, role, instance profile, launch template,
and security group were removed after retrieval. Final queries found no active
test instances, tagged test volumes, or authentication parameter. The normal
shutdown was delayed; force termination with OS shutdown bypass completed.
Identifiers, command scripts, archives, and hardware records remain in the
ignored local directory `data/aws-gpu/2026-11-19/`.
The unchanged 10-second job passed local contract/checksum inspection. The source
archive is published release `v0.10.1`; the job retains its `v0.7.0` identity.

Local Hugging Face login and authenticated access to the pinned checkpoint's
`config.json` passed on 2026-11-19; no model weights were downloaded locally.
The token was transferred through a restricted SecureString parameter using an
in-memory file; it was omitted from process arguments, user data, and logs.
The temporary role limited secret reads to this experiment's parameter. The
parameter was deleted after successful authentication/inference and retrieval
of the results.

### Worker commands

Use the matching published Harmonic source release on the GPU host. The initial
excerpt benchmark used `v0.10.1`; full-song commands require `v0.12.0` or later.
For resumes, preserve the original source and environment. The worker binds the
plan, auxiliary text revision, worker/lock, imported local modules, and recorded
runtime identity. Copy the prepared job there, then run from the repository root:

```sh
just sam-sync
just sam-auth
just sam-doctor
just sam-run data/sam-jobs/billie-jean-v0.7.0 data/sam-results/billie-jean-v0.7.0
```

`sam-sync` explicitly installs the large inference dependency set into
`workers/sam_audio/.venv/`. It does not modify the main `.venv/`. The baseline is
Python 3.11, torch/torchaudio 2.8.0, torchvision 0.23.0, TorchCodec 0.7.0,
xFormers 0.0.32.post2, CUDA 12.8 wheels, and NumPy 1.26.4. The pairings follow the
[PyTorch release installation instructions](https://pytorch.org/get-started/previous-versions/#v2-8-0)
and [TorchCodec compatibility matrix](https://github.com/meta-pytorch/torchcodec#installing-torchcodec).
The full transitive lock and exact Git commits live alongside this guide.
This combination passed imports, a CUDA tensor operation, and real inference on
the tested Blackwell host. Dependency resolution alone is not equivalent to
these runtime checks; other host/driver combinations remain unverified.

Authenticate interactively with the account granted checkpoint access. Do not
put tokens in jobs, tracked files, command arguments, or chat. The worker honors
the Hugging Face token cache and `HF_TOKEN`; diagnostics disclose presence only.
`just sam-doctor` works before installation and returns nonzero until prerequisites
are present. It downloads no weights and does not establish gated-repository
permission or prove inference works. `sam-run` fails before downloads if preflight
is incomplete. There is no automatic CPU fallback.

The worker's direct interface also supports help/version without dependencies:

```sh
python3 workers/sam_audio/worker.py -h
python3 workers/sam_audio/worker.py -v
./workers/sam_audio/.venv/bin/python workers/sam_audio/worker.py run JOB \
  --output NEW_RESULT_DIRECTORY
```

The main checkpoint revision is `b9fc94687ec044c570cbe30b8c28100cd056f1cb`;
SAM Audio source is `bb4c6999d2677c7402360e426afc01ddfad6dce0`. The worker downloads
that exact checkpoint snapshot and loads it through a local path: the pinned
upstream loader otherwise ignores its public revision argument. The auxiliary
text model is resolved to a commit and downloaded as an immutable snapshot; its
ID/revision is saved in the report. For repeat runs, pass that report's revision
using the worker's `--text-revision` option.

## Results and validation

Each prompt produces **an independent target/residual pair**. Targets can overlap;
vocals + drums + bass do not constitute an exclusive four-stem decomposition.
The processor averages the canonical stereo channels to mono. This loses stereo
width and can cancel anti-phase material; it is explicitly recorded in the job.
Outputs keep relative gain without loudness normalization or clipping.

The first baseline uses float32, one candidate, no automatic span prediction,
no temporal anchors, and a midpoint ODE step of 0.0625. Unused ranking/span models
are disabled in a temporary configuration; the Hugging Face cache stays unchanged.
The owner approved the initial excerpt by listening. Full-song prompt consistency
and controlled comparisons of these settings remain to be evaluated.

Successful runs atomically publish a new result directory containing float32 mono
48 kHz WAVs and `report.json`. The report records source/job/model hashes,
auxiliary revision, dependency versions, code/lock hashes, seed/settings, source
sample offset, per-target timings and CUDA memory, host peak RSS, and audio hashes,
RMS, peaks, and target-plus-residual error. The latter is a reconstruction
diagnostic, not a ground-truth separation-quality score. A seed does not guarantee
bitwise reproducibility across devices or dependency builds.

Only trailing codec padding within one hop is trimmed; short/nonfinite output is
rejected. Preserving the start and exact frame count does not prove perceptual
alignment. Copy results back, then validate them against the unchanged job:

```sh
just sam-validate data/sam-jobs/billie-jean-v0.7.0 data/sam-results/billie-jean-v0.7.0
```

The owner approved listening to the experiment's target/residual files. They can
now be adapted into a schema-2 bundle with `just sam-features MIX JOB RESULT NEW`;
see [source features and graphs](../../README.md#sam-source-features-and-graphs).
The adapter validates WAVs, preserves mono levels and sample positions, and
retains the report and features without embedding separated audio. The original
stereo mix remains the playback source. Full-song chunking/overlap and completed
chunk resume are implemented below. Per-prompt retries, catalog caching of SAM
results, and automated cleanup of temporary separated audio remain future work.
Preserve these experimental outputs for review.

## Full-song chunk workflow

The worker also accepts `run-song PLAN --output DIRECTORY` (or
`just sam-run-song PLAN DIRECTORY`). Prepare the complete recording locally with
`just sam-prepare-song AUDIO PLAN 10 2`; each child remains a bounded excerpt
using the existing pinned model/settings. The song plan pins the auxiliary text
revision and binds source identity, all input/job hashes, sample coordinates,
prompts, seed, chunk duration, and overlap.

One model load serves all pending chunks. A matching existing output is resumed
only after validating completed WAVs and job/model/code/lock provenance. A
completion marker is published after every chunk validates, with per-invocation
new/reused counts. Invalid partial artifacts fail explicitly; prompts in an
unfinished chunk are not individually cached. Current workers take an exclusive
Linux file lock before opening or creating an output. A competing invocation
reports the busy output and exits before model setup. Keep the hidden
`.<output-name>.lock` file beside the output even after the process exits. The
operating system releases the lock on process exit, including a forced kill.
Run on a filesystem that supports file locking and use one worker release per
output. Resume older partial runs with the original worker release. Once a
restart verifies the binding and published chunks, it removes recognized chunk
scratch directories and `.completed.json.tmp` under the lock. Cleanup stays
inside the bound output and leaves symlinks and unrecognized chunk files in place.
The run binding includes Python and installed package versions, platform, CUDA,
GPU properties, and the NVIDIA driver version when exposed. New chunk reports
carry the binding hash. Stitching and both bundle readers verify that retained
chunks agree on that hash when present. Completed legacy reports can still be
read. The binding supports job-local resume and records version identity.

The CLI prints elapsed time from command dispatch through completion publication
and lock release. `completed.json` records each invocation's `timing_seconds`
and `elapsed_seconds_through_validation`. The JSON total ends before reading
and updating the completion history. Model setup includes downloads and loading.
Pending-chunk time includes writing chunk results and closing the model session.
Both stages are zero when every chunk is reused. The older elapsed fields keep
their original start after readiness, initial plan validation, and the reuse scan.

After retrieving results, `just sam-stitch PLAN CHUNKS NEW` applies complementary
half-cosine overlap-add to new full-length float WAVs and retains every original
chunk report and checksum. The local `sam-validate-song` and `sam-features`
commands verify/consume these results without model packages. See the
[full-song guide](../../README.md#full-song-sam-processing) for commands, overlap
metrics, retention rules, and the remaining listening check.

## First AWS GPU benchmark (2026-11-19)

The unchanged 10-second Billie Jean excerpt at source samples
1,440,000–1,919,999 completed on the `g7e.4xlarge` described above. Source release
`v0.10.1`, Python 3.11.18, torch 2.8.0+cu128, and the frozen worker lock were used.
The worker's source and lock hashes match the local files. Pinned checkpoint
SHA-256: `90e047269238c498c5abe0da6e6ba40859d152111d4a09f582a209027a33b72f`.
The auxiliary text model resolved to `google-t5/t5-base` at
`a9723ea7f1b39c1eae772870f3b547bf6ef7e6c1`; use `--text-revision` with this commit
for repeat runs. The initial checkpoint/auxiliary download took 182.1 seconds.

| Target | Prompt | Separation time | Real-time factor | Peak allocated GPU | Peak reserved GPU |
| --- | --- | ---: | ---: | ---: | ---: |
| Vocals | `man singing` | 2.197 s | 0.220 | 17.255 GiB | 17.871 GiB |
| Drums | `drums playing` | 1.560 s | 0.156 | 17.256 GiB | 19.074 GiB |
| Bass | `bass guitar playing` | 1.562 s | 0.156 | 17.256 GiB | 19.074 GiB |

The three separation calls totaled 5.319 seconds; total worker elapsed time,
including initial downloads and loading, was 221.583 seconds. Peak host RSS was
29.855 GiB. These are single-run measurements for this excerpt and settings,
not full-song throughput or hardware minimums.

`just sam-validate` passed all three target/residual pairs: each WAV has 480,000
mono float32 samples at 48 kHz, no padding trim, and matching hashes, statistics,
source offset, and provenance. The source input/config and worker code/lock
hashes were checked independently after retrieval. All 20 output objects were
retrieved and their local sizes verified before AWS cleanup. Logs, original
float WAVs, `report.json`, `measurements.json`, and processor diagnostics are in
`data/aws-gpu/2026-11-19/` (ignored by Git).

A waveform correlation search of each target-plus-residual sum against the mono
input found zero global lag within ±4,800 samples (±100 ms). This does not
establish instrument-level or perceptual latency. Reconstruction RMS error was
0.091–0.093 against input RMS 0.209; best-fit reconstruction gain was
0.807–0.863. These are substantial waveform differences, not an exact mixture
partition. Inspection of the pinned model confirms that target and residual
are generated/decoded independently; residual is not computed as input minus
target. Do not apply the best-fit gain as a blanket correction or interpret
reconstruction error as a ground-truth separation-quality score.

Direct checks of the pinned processor matched arithmetic-mean mono conversion
exactly, retained a doubled input amplitude, and cancelled an anti-phase stereo
input to zero. Output peaks above 1.0 remain in float WAVs, without clipping or
normalization. On 2026-11-19, the owner listened to all three target/residual
pairs and confirmed clear instrument extraction, no audible unwanted bleed,
and no unwanted target instrument remaining in residuals. This is listening
approval for the tested excerpt; it does not establish exclusive targets,
full-song quality, or instrument-level latency. Instrument-transient and
comparative gain review remain open. The local feature adapter introduces no
additional gain or latency correction; its RMS/peak and sample-offset checks
passed for all six streams.

System-package setup initially stalled on the regional Ubuntu HTTP mirror.
Retrying with the Ubuntu HTTPS mirror and `apt-get install --no-install-recommends`
completed; both attempts' logs and exit codes were preserved. This preparation
retry did not change the worker lock, model, job, or inference settings.

## First full-song run (2026-11-19, v0.12.0)

The full 14,202,811-sample recording completed as 37 chunks (10-second maximum,
2-second overlaps) on the same tested `g7e.4xlarge` hardware type. All 111 prompt
calls completed; their separation times totaled 165.206 seconds. The initial
worker invocation measured 386.690 seconds including download/model loading,
excluding preflight. Peak reserved CUDA memory was 19.074 GiB; peak host RSS was
29.878 GiB. A second invocation reused all 37 validated chunks and performed no
new inference; per-invocation completion history was retained. The elapsed
fields exclude readiness, initial plan validation, and the reuse scan; the
all-reused field is not a measurement of total restart wall time.

All 275 remote output files were retrieved and checked locally. All chunk WAVs,
retained reports, full-length merged WAVs, features, and native compositor checks
passed. The reviewed excerpt's listening approval does not extend to this run:
neighboring vocal estimates disagree strongly at some seams, especially 80–82
and 88–90 seconds. This baseline needs full-song/seam listening and prompt
consistency review before batch use. Unnormalized left/right/blended/source
comparison clips are in `data/source-check-v0.12.0/seam-review/`.

The follow-up measured all 37 raw chunks. The 80–90 second vocal target has
RMS 0.0050 against mono mix RMS 0.243 (2.1% of mix RMS). The next lowest
chunk ratio is 32.9%. Recomputing both fades reproduced the stitched samples
exactly. The 82–88 second interval falls outside the fades and matches the raw
estimate sample for sample. The weak estimate originates during separation.
Aligned clips at their original levels and the measurements for all chunks are
in `data/source-check-v0.12.0/vocal-review/`. Listening can establish whether
vocals are missing from the target or remain in the residual at that point.

The GPU ran a recorded working-tree source snapshot before release, with
matching worker/lock hashes retained in every chunk report. Raw results, logs,
archive hashes, timing/memory/overlap summaries, and resource identifiers are
under `data/aws-gpu/song-v0.12.0/`. Full-length WAVs are in
`data/sam-results/billie-jean-song-v0.12.0/`; the ready native feature bundle is
`data/analysis/billie-jean-song-v0.12.0/`. All temporary AWS resources and the
authentication parameter were removed after verified retrieval. Final checks
found no active test instance or tagged test volume.

## License observations

The [SAM License](https://github.com/facebookresearch/sam-audio/blob/bb4c6999d2677c7402360e426afc01ddfad6dce0/LICENSE)
has been inspected for this local prototype; model access is not distribution
approval for the entire dependency tree. In particular, the selected
[Perception Models package](https://github.com/facebookresearch/perception_models/blob/e72b6810b1133e1c879f2cc965d276eb73803f1f/setup.py)
declares a FAIR Noncommercial Research License, and
[ImageBind](https://github.com/facebookresearch/ImageBind/blob/53680b02d7e37b19b124fa37bae4b6c98c38f5be/setup.py)
declares a noncommercial Creative Commons license. Review the actual licenses and
which components are used before distributing binaries, bundling model code or
weights, or offering a commercial service. That review remains open in TODO.md.
