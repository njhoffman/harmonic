---
description: Show the current project's complete TODO.md with colored task status
---

Use the globally installed todo skill to display the active project's TODO.md.
Keep the working directory set to the active project. Use the skill's bundled
show_todo.py renderer: ANSI colors for terminal tool output and --format markdown
for the final response. Show every section and task, using green markers for
completed tasks and amber/yellow markers for pending tasks. Preserve notes,
continuation lines, links, and exact task status. Do not execute the tasks or
change any files. If the project has no TODO.md, report that instead of creating it.
