set shell := ["bash", "-euo", "pipefail", "-c"]

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
release: check-version
    #!/usr/bin/env bash
    set -euo pipefail
    release_version="$(python3 scripts/version.py show)"
    release_tag="v${release_version}"
    release_branch="$(git symbolic-ref --short HEAD)"
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
    just test
    git commit -m "chore(release): ${release_tag}"
    git tag --annotate "${release_tag}" --message "Harmonic ${release_tag}"
    git push --atomic --set-upstream origin "HEAD:refs/heads/${release_branch}" "refs/tags/${release_tag}"
    just build
