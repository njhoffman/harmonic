# Project workflow

## Approved updates and releases

- After every approved update, bump the SemVer version, update `CHANGELOG.md`,
  commit the approved changes, create an annotated `vMAJOR.MINOR.PATCH` Git tag,
  push the branch and tag to GitHub, and build the published commit.
- A direct implementation request or explicit approval authorizes this workflow
  for that scope. Do not ask again for routine commit/tag/push/build approval.
  Questions, reviews, and unapproved work in progress are not releases.
- Use `just bump patch|minor|major` to synchronize `pyproject.toml`,
  `CMakeLists.txt`, the Python package version, and `uv.lock`. Complete the dated
  changelog entry with concrete user-facing changes before releasing.
- Use minor bumps for new functionality and patch bumps for compatible fixes,
  documentation, and build maintenance. During 0.x development, incompatible
  interface changes also require a minor bump and an explicit changelog note.
  After 1.0, incompatible public interface changes require a major bump.
- Stage only the approved update, including new files, and use `just release`.
  It checks version consistency, builds/tests before committing, commits and
  creates the annotated tag, atomically pushes the branch/tag, then builds again.
- Never move or overwrite a published tag, force-push, or include unrelated work.
  If publishing fails after the local commit/tag, retry that push rather than
  creating another version or moving the tag. Report any failed stage precisely.
- Keep recordings, generated analysis, environments, and build outputs out of Git.

## Development

- Make status/progress visual: use colored status markers in chat, gradient
  terminal bars for measurable work, and activity indicators with elapsed time
  for commands with no known total. Never invent a completion percentage.
  Preserve command logs/exit codes and honor `NO_COLOR`; use `FORCE_COLOR=1`
  when a captured terminal supports ANSI but cannot be detected automatically.
- Use `just` to discover build, analysis, playback, and verification commands.
- Python extracts offline features; C++/SDL3/OpenGL handles playback/rendering.
- Preserve the sample-based feature timebase and the recording/artifact checksums.
- Read `README.md` for the bundle contract and `PLAN.md` for the roadmap.
- Keep `TODO.md` as the running task checklist. Update it with each approved
  update, check off only verified work, and record blockers such as pending
  model access without marking the dependent implementation complete.
- SAM Audio is the preferred separation engine; the owner has access to
  `facebook/sam-audio-large-tv`. The isolated worker is prepared for a GPU host;
  worker authentication and actual CUDA inference remain unverified.
  Keep Demucs optional as a comparison/fallback, and isolate model dependencies
  from the current analyzer/player environment.
