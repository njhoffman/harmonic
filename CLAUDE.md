@AGENTS.md

# Claude Code notes

AGENTS.md (imported above) is the shared source of truth for Codex and Claude.
This file only adds what is specific to Claude Code or overrides a global rule.

## Precedence over global instructions

- **Releases push automatically here.** AGENTS.md's approved-update workflow
  overrides the global "push only when asked" rule for this repo: a direct
  implementation request or explicit approval authorizes bump, commit, tag,
  push, build, and GitHub release for that scope.
- Release flow: `just bump patch|minor|major`, complete the dated
  `CHANGELOG.md` entry (move `[Unreleased]` items into it), update `TODO.md`,
  stage only the approved files, then
  `just release "<one-line summary>" "Co-Authored-By: <attribution line>"`
  (positional: `name=value` is not parsed for recipe parameters).
  `release` fetches tags, runs `just test`, commits, tags, pushes atomically,
  builds, and runs `just publish-release X.Y.Z` (GitHub release from that
  version's CHANGELOG section). After it, compare `git tag` with
  `git ls-remote --tags origin`.
- If a stage fails after the local commit/tag: retry the push
  (`git push --atomic origin HEAD:refs/heads/main refs/tags/vX.Y.Z`) or
  `just publish-release X.Y.Z`. Never create another version or move the tag.

## Testing

- Full suite: Monitor on `~/.shell/scripts/test-progress -C . --events`; it
  falls back to `just test`, which builds the native player first.
- One file: `.venv/bin/python -m unittest tests.test_<name> -v`.
- Native, FFmpeg, and projectM tests skip when their tools are missing; report
  the skip count instead of calling a run with skips a full pass.

## Layout

- `src/harmonic_analysis/`: offline analyzer, bundle writer, catalog, SAM job,
  chunk, feature, and benchmark tooling (`harmonic-sam` CLI in `sam_cli.py`).
- `native/`: C++/SDL3/OpenGL player and offscreen checks (`render-check`,
  `compositor-check`, `projectm-check`). The bundle contract lives in
  `bundle.py` and `native/src/bundle.cpp`; change them together.
- `workers/sam_audio/`: isolated Python 3.11/CUDA worker with its own venv and
  lock. GPU host only: do not run `just sam-sync`, `sam-auth`, `sam-run`, or
  `sam-run-song` on this desktop unless asked. `workers/sam_audio/README.md`
  holds the evidence paths and limits.
- `scripts/`: `version.py` (bump/check/notes), `run_status.py` (progress
  wrapper), `install_codex_todo.py`.
- `tools/codex/`: Codex-only todo skill. In Claude, use the global `/todo`
  skill; leave these files in place.
- `data/`: ignored local recordings and evidence. Never modify existing
  bundles or results in place; preserve checksums.

## TODO.md

Global todo-status format: `- [ ] **Title.** (pN) [category]` with indented
details. Ticked items stay in their section until the whole section is done,
then move under `## Completed` as `### <heading> (completed YYYY-MM-DD)`.
