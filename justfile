set shell := ["bash", "-euo", "pipefail", "-c"]

python := justfile_directory() / ".venv/bin/python"
player := justfile_directory() / "build/harmonic-player"
default_audio := "data/tracks/Michael Jackson - Billie Jean.mp3"
default_bundle := "data/analysis/billie-jean"

# List available commands.
default:
    @just --list

# Install the locked Python dependencies into the local virtual environment.
sync:
    uv sync --frozen --cache-dir .cache/uv

# Configure the native build, fetching SDL3 locally if needed.
configure: sync
    cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DPython3_EXECUTABLE={{ quote(python) }}

# Build the native player (override job count with `just build 8`).
build jobs="4": configure
    cmake --build build --parallel {{ quote(jobs) }}

# Analyze a local recording into a new bundle; existing bundles are preserved.
analyze audio=default_audio bundle=default_bundle: sync
    {{ quote(python) }} -m harmonic_analysis {{ quote(audio) }} --output {{ quote(bundle) }}

# Build and play a previously analyzed recording.
play bundle=default_bundle: build
    {{ quote(player) }} {{ quote(bundle) }}

# Build and run all Python and native integration tests.
test: build
    {{ quote(python) }} -m unittest discover -s tests -v

# Validate a bundle and its native decoding without opening audio/video devices.
inspect bundle=default_bundle: build
    {{ quote(player) }} {{ quote(bundle) }} --inspect

# Check playback, seeking, and EOF without producing sound.
audio-check bundle=default_bundle: build
    SDL_AUDIODRIVER=dummy {{ quote(player) }} {{ quote(bundle) }} --audio-check

# Render one offscreen frame to PPM (default position: 35 seconds).
render-check bundle=default_bundle seconds="35" output="data/preview.ppm": build
    {{ quote(player) }} {{ quote(bundle) }} --start {{ quote(seconds) }} --render-check {{ quote(output) }}

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
