# SAM Audio excerpt worker

The owner has access to [`facebook/sam-audio-large-tv`](https://huggingface.co/facebook/sam-audio-large-tv).
This directory prepares a **Linux x86_64 GPU worker** separate from Harmonic's
analyzer/player environment. Its dependency graph resolves and is locked; actual
package imports, GPU memory use, checkpoint authentication, and inference have
**not** been validated on a GPU host yet. No model weights were downloaded locally.

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

Use the same Harmonic release (`v0.7.0`) on the GPU host. Copy the prepared job
there, then run from the repository root:

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
Successful dependency resolution does not establish runtime compatibility.

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
Inference quality and the effects of these settings remain to be measured.

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

Listen to the target/residual files and inspect their activity before extending
the player. Full-song chunking/overlap, multi-stream bundles/native graphs,
stage-level retries, catalog caching of SAM results, and cleanup of temporary
separated audio remain future work. Preserve these experimental outputs for review.

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
