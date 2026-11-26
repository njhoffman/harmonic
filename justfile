set shell := ["bash", "-euo", "pipefail", "-c"]
# Recipes receive their arguments as $1, $2, ... too (sam-musdb-prepare keeps
# track names with spaces intact). A setting, not the [positional-arguments]
# attribute, so the apt `just` (1.21) on the Ubuntu 24.04 GPU host parses it.
set positional-arguments

python := justfile_directory() / ".venv/bin/python"
player := justfile_directory() / "build/harmonic-player"
default_audio := "data/tracks/Michael Jackson - Billie Jean.mp3"
default_bundle := "data/analysis/billie-jean"
sam_python := justfile_directory() / "workers/sam_audio/.venv/bin/python"

# List available commands.
default:
    @just --list

# Show the task checklist with terminal colors (no build or environment needed).
todo:
    @python3 tools/codex/todo/scripts/show_todo.py

# Install the global Codex todo skill and /prompts:todo command for all projects.
install-codex-todo:
    python3 scripts/install_codex_todo.py

# Install the locked Python dependencies into the local virtual environment.
sync:
    @python3 scripts/run_status.py "Syncing dependencies" uv sync --frozen --cache-dir .cache/uv

# Configure the native build, fetching SDL3 locally if needed.
configure: sync
    @python3 scripts/run_status.py "Configuring native build" cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DPython3_EXECUTABLE={{ quote(python) }}

# Build the native player (override job count with `just build 8`).
build jobs="4": configure
    @python3 scripts/run_status.py "Building native tools" cmake --build build --parallel {{ quote(jobs) }}

# Analyze a local recording into a new bundle; existing bundles are preserved.
analyze audio=default_audio bundle=default_bundle: sync
    {{ quote(python) }} -m harmonic_analysis {{ quote(audio) }} --output {{ quote(bundle) }}

# Import a recording, reusing verified analysis or creating a managed bundle.
import audio=default_audio database="data/library/catalog.sqlite3": sync
    {{ quote(python) }} -m harmonic_analysis.catalog --database {{ quote(database) }} import {{ quote(audio) }}

# Register an existing bundle without repeating feature extraction.
catalog-add audio=default_audio bundle=default_bundle database="data/library/catalog.sqlite3": sync
    {{ quote(python) }} -m harmonic_analysis.catalog --database {{ quote(database) }} import {{ quote(audio) }} --bundle {{ quote(bundle) }}

# List local recording identities and bundle references.
catalog database="data/library/catalog.sqlite3": sync
    {{ quote(python) }} -m harmonic_analysis.catalog --database {{ quote(database) }} list

# Prepare a portable short-excerpt job; no model packages or weights are needed.
sam-prepare audio=default_audio output="data/sam-jobs/billie-jean" start="30" duration="10": sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli prepare {{ quote(audio) }} --output {{ quote(output) }} --start {{ quote(start) }} --duration {{ quote(duration) }}

# Install the separate pinned inference environment ON THE GPU HOST (large download).
sam-sync:
    @UV_PYTHON_INSTALL_DIR={{ quote(justfile_directory() / ".cache/uv-python") }} python3 scripts/run_status.py "Syncing isolated SAM worker" uv sync --project workers/sam_audio --frozen --python 3.11 --cache-dir .cache/uv

# Diagnose the worker without downloading weights; returns nonzero when not ready.
sam-doctor:
    @if test -x {{ quote(sam_python) }}; then {{ quote(sam_python) }} workers/sam_audio/worker.py doctor; else python3 workers/sam_audio/worker.py doctor; fi

# Authenticate interactively on the GPU host; tokens stay out of project files.
sam-auth:
    ./workers/sam_audio/.venv/bin/hf auth login

# Run a prepared excerpt on the GPU host; no automatic CPU fallback or installation.
sam-run job="data/sam-jobs/billie-jean" output="data/sam-results/billie-jean":
    @if test -x {{ quote(sam_python) }}; then {{ quote(sam_python) }} workers/sam_audio/worker.py run {{ quote(job) }} --output {{ quote(output) }}; else python3 workers/sam_audio/worker.py run {{ quote(job) }} --output {{ quote(output) }}; fi

# Verify returned audio against the prepared job before using its timeline.
sam-validate job="data/sam-jobs/billie-jean" result="data/sam-results/billie-jean": sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli validate {{ quote(job) }} {{ quote(result) }}

# Prepare mixed, vocal-only, and accompaniment-only benchmark jobs from aligned stems.
sam-vocal-benchmark-prepare vocal accompaniment output start="0" duration="12" prompt="man singing": sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli prepare-vocal-benchmark {{ quote(vocal) }} {{ quote(accompaniment) }} --output {{ quote(output) }} --start {{ quote(start) }} --duration {{ quote(duration) }} --prompt {{ quote(prompt) }}

# Score a validated mixed benchmark result against its reference stems (report v2).
sam-vocal-score-mix job result vocal accompaniment: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli benchmark-vocals {{ quote(job) }} {{ quote(result) }} --case mix --vocal-stem {{ quote(vocal) }} --accompaniment-stem {{ quote(accompaniment) }}

# Score a validated vocal-only benchmark result (the job PCM is its reference).
sam-vocal-score-isolated job result: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli benchmark-vocals {{ quote(job) }} {{ quote(result) }} --case vocal-only

# Score a saved accompaniment-only SAM result for false vocal extraction.
sam-vocal-control job result: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli benchmark-vocals {{ quote(job) }} {{ quote(result) }} --case accompaniment-only

# Decode MUSDB18 tracks into references and multi-target benchmark jobs (new run directory).
# Track names contain spaces: each stays one argument.
sam-musdb-prepare archive output +tracks: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli prepare-musdb "$1" --output "$2" "${@:3}"

# Score validated MUSDB results: lag-aligned multi-target gains, dropouts, and absence checks.
sam-musdb-score run results output: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli score-musdb {{ quote(run) }} {{ quote(results) }} --output {{ quote(output) }}

# Compare 10 s, 20 s, and 30 s context on each track's common 20 s core.
sam-musdb-context run results output: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli musdb-context {{ quote(run) }} {{ quote(results) }} --output {{ quote(output) }}

# Prepare a complete recording as <=30s chunks with sample-based overlap.
sam-prepare-song audio=default_audio output="data/sam-jobs/billie-jean-song" chunk="10" overlap="2": sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli prepare-song {{ quote(audio) }} --output {{ quote(output) }} --chunk-duration {{ quote(chunk) }} --overlap {{ quote(overlap) }}

# Separate a song with one loaded model, reusing only validated matching completed chunks.
sam-run-song plan="data/sam-jobs/billie-jean-song" output="data/sam-results/billie-jean-chunks":
    {{ quote(sam_python) }} workers/sam_audio/worker.py run-song {{ quote(plan) }} --output {{ quote(output) }}

# Validate and blend completed chunk results into new full-length WAV pairs.
sam-stitch plan chunks output: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli stitch {{ quote(plan) }} {{ quote(chunks) }} --output {{ quote(output) }}

# Verify full-song output identity, samples, statistics, and retained chunk reports.
sam-validate-song plan result: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli validate-song {{ quote(plan) }} {{ quote(result) }}

# Add validated excerpt or full-song targets/residuals to a new bundle; no GPU or model environment needed.
sam-features mix job result output: sync
    {{ quote(python) }} -m harmonic_analysis.sam_cli features {{ quote(mix) }} {{ quote(job) }} {{ quote(result) }} --output {{ quote(output) }}

# Measure frame times, seeks, and the output queue on a real display (plays audio, ~10 min).
perf-desktop bundle=default_bundle display=":0" duration="60": build
    {{ quote(python) }} -m harmonic_analysis.frame_perf run {{ quote(bundle) }} --player {{ quote(player) }} --display {{ quote(display) }} --duration {{ quote(duration) }}

# Build and play a previously analyzed recording.
play bundle=default_bundle: build
    {{ quote(player) }} {{ quote(bundle) }}

# Play a local projectM preset with graph overlays; V cycles views.
play-preset preset bundle=default_bundle view="combined": build
    {{ quote(player) }} {{ quote(bundle) }} --preset {{ quote(preset) }} --view {{ quote(view) }}

# Build and run all Python and native integration tests.
test: build
    @python3 scripts/run_status.py "Running tests" {{ quote(python) }} -m unittest discover -s tests -v

# Validate a bundle and its native decoding without opening audio/video devices.
inspect bundle=default_bundle: build
    @python3 scripts/run_status.py "Validating analysis bundle" {{ quote(player) }} {{ quote(bundle) }} --inspect

# Check playback, seeking, and EOF without producing sound.
audio-check bundle=default_bundle: build
    @SDL_AUDIODRIVER=dummy python3 scripts/run_status.py "Checking audio transport" {{ quote(player) }} {{ quote(bundle) }} --audio-check

# Render one offscreen frame to PPM (default position: 35 seconds).
render-check bundle=default_bundle seconds="35" output="data/preview.ppm": build
    @python3 scripts/run_status.py "Rendering preview" {{ quote(player) }} {{ quote(bundle) }} --start {{ quote(seconds) }} --render-check {{ quote(output) }}

# Check a local projectM preset offscreen; requires installed libprojectM 4.
projectm-check preset bundle=default_bundle output="data/projectm-check" frames="180": build
    ./build/harmonic-projectm-check {{ quote(bundle) }} --preset {{ quote(preset) }} --output {{ quote(output) }} --frames {{ quote(frames) }}

# Verify preset/UI composition, pause, seeking, EOF, and resize offscreen without audio.
compositor-check preset bundle=default_bundle output="data/compositor-check": build
    {{ quote(player) }} {{ quote(bundle) }} --preset {{ quote(preset) }} --compositor-check {{ quote(output) }}

# Print the current project version.
version:
    @python3 scripts/version.py show

# Verify source/lockfile versions and the current dated changelog entry.
check-version:
    python3 scripts/version.py check

# Bump all project versions; then complete the new changelog entry before release.
bump level="patch":
    python3 scripts/version.py bump {{ quote(level) }}

# Release an already bumped, documented, and staged approved update.
release summary="" trailer="": check-version
    #!/usr/bin/env bash
    set -euo pipefail
    release_version="$(python3 scripts/version.py show)"
    release_tag="v${release_version}"
    release_branch="$(git symbolic-ref --short HEAD)"
    release_summary={{ quote(summary) }}
    release_trailer={{ quote(trailer) }}
    if [[ "${release_summary}" == summary=* || "${release_trailer}" == trailer=* ]]; then
        echo "Pass the summary and trailer positionally: just release \"<summary>\" \"<Key: value>\"" >&2; exit 1
    fi
    git fetch --tags --quiet origin
    git diff --quiet || { echo "Stage or resolve unstaged changes before releasing." >&2; exit 1; }
    test -z "$(git ls-files --others --exclude-standard)" || { echo "Stage approved new files before releasing." >&2; exit 1; }
    if git diff --cached --quiet; then
        echo "No staged approved update to release." >&2
        exit 1
    fi
    if git show-ref --verify --quiet "refs/tags/${release_tag}"; then
        echo "Tag ${release_tag} already exists; do not move it or repeat this release." >&2
        exit 1
    fi
    HARMONIC_REQUIRE_INTEGRATION=1 just test
    commit_args=(-m "chore(release): ${release_tag}${release_summary:+ - ${release_summary}}")
    if [[ -n "${release_trailer}" ]]; then commit_args+=(--trailer "${release_trailer}"); fi
    git commit "${commit_args[@]}"
    git tag --annotate "${release_tag}" --message "Harmonic ${release_tag}"
    git push --atomic --set-upstream origin "HEAD:refs/heads/${release_branch}" "refs/tags/${release_tag}"
    just build
    just publish-release "${release_version}"

# Create the GitHub release for an already pushed tag from its CHANGELOG.md entry.
publish-release version:
    #!/usr/bin/env bash
    set -euo pipefail
    version={{ quote(version) }}
    tag="v${version}"
    if ! command -v gh >/dev/null; then echo "gh not installed; create the ${tag} release manually." >&2; exit 1; fi
    if gh release view "${tag}" >/dev/null 2>&1; then echo "GitHub release ${tag} already exists."; exit 0; fi
    notes="$(mktemp)"
    trap 'rm -f "${notes}"' EXIT
    python3 scripts/version.py notes "${version}" > "${notes}"
    gh release create "${tag}" --verify-tag --title "Harmonic ${version}" --notes-file "${notes}"
