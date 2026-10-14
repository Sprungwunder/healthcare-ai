---
description: After a task has been completed and accepted, writes a structured log to docs/ai-agent-history/<YYYY-MM-DD_task-name>.md
allowPromptArgument: true
---

Summarize the task you just completed successfully and document it in a new, structured Markdown file in the `docs/ai-agent-history/` directory.

Additional notes or parameters, if any were passed: $prompt

### Instructions:
1. **Check/create the target directory**: Make sure `docs/ai-agent-history/` exists.
2. **Choose the file name**: Pick a concise file name in the format `<YYYY-MM-DD_task-name>.md`: the current date as `YYYY-MM-DD`, an underscore, then the task name in kebab-case (e.g. `2026-10-13_refactor-authentication.md`).
3. **Structure and write the content**: Create the file `docs/ai-agent-history/<YYYY-MM-DD_task-name>.md` using the following structure:

# Task: <Title / short description of the task>

- **Date / time**: <Current date and time in the format YYYY-MM-DD HH:MM>
- **Status**: Completed / successful

## 1. Task Overview
<Detailed description of the original request and its goal>

## 2. Steps Taken
<Chronological list of the actions, code changes and configuration changes made>

## 3. File Changes
<List of all modified or newly created files with short descriptions>

## 4. Verification & Testing
<Tests that were run (e.g. .venv/bin/python manage.py test) and their results>

## 5. Key Decisions & Notes
<Relevant architectural decisions, trade-offs or follow-up notes>
