---
name: todo
description: Display the current project's TODO.md as a complete, styled task checklist. Use when the user invokes todo or asks to view the project checklist, without starting its tasks.
---

# Show the task checklist

Use the bundled `scripts/show_todo.py` to read the current project's `TODO.md`.
Run it with the working directory set to the user's active project, not this
skill directory. It finds the nearest TODO.md up to the Git root; outside Git it
checks the current directory. An explicit `--path` can select another file.

- For terminal output, run `python3 <skill-directory>/scripts/show_todo.py --color always`
  with a PTY so completed tasks are green, pending tasks amber, and headings cyan.
- For the final chat response, run the same script with `--format markdown` and
  reproduce its output. It preserves all sections, tasks, continuation lines,
  links, and notes, adding colored status markers and a completion count.
  Chat text does not support arbitrary ANSI foreground colors; do not paste raw
  escape codes into the response or claim that text color is guaranteed.
- Display the whole checklist unless the user requests a subset. Do not infer
  missing task status, execute listed work, edit files, or trigger a release.
- If TODO.md is missing, report the searched project path. Do not create a file.

The global CLI custom-prompt form is `/prompts:todo`. The skill can also be
invoked as `$todo` or selected in a skill menu. Do not promise a bare `/todo`
alias on surfaces that do not support it.
