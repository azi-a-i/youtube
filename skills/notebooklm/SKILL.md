---
name: notebooklm
description: Automate the workspace-local notebooklm-py installation to create notebooks, add YouTube or web URLs as sources, ask NotebookLM for analysis, and generate deliverables such as infographics, slide decks, and flashcards. Use when Codex needs to move research into NotebookLM, synthesize findings, or download NotebookLM artifacts. If authentication has not been completed yet, stop and ask the user to open a separate terminal and run the local `.\notebooklm.cmd login` command before continuing.
---

# NotebookLM

## Overview

Use `scripts/notebooklm_pipeline.py` for programmatic NotebookLM workflows in this workspace. The script uses the installed Python API, stores auth state under the project-local `.notebooklm` folder, and can ingest the JSON output created by the `yt-research` skill.

## Authentication First

Before the first live NotebookLM operation, ask the user to open a separate terminal in this workspace and run:

```powershell
.\notebooklm.cmd login
```

Do not keep pushing NotebookLM API calls if auth is missing. The script will fail fast and remind the user to log in.

## Quick Start

Create a notebook:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' create --title "YouTube Research: AI Agents"
```

Add YouTube URLs from the `yt-research` output:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' add-urls --notebook-id "<notebook-id>" --urls-file '.\outputs\yt\agents.json'
```

Run a combined workflow:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' `
  pipeline `
  --title "YouTube Research: AI Agents" `
  --urls-file '.\outputs\yt\agents.json' `
  --analysis-prompt "Summarize the top findings across these videos." `
  --artifact infographic `
  --artifact slide-deck `
  --artifact flashcards `
  --artifact-instructions "Use a handwritten, chalkboard-style visual language for the infographic." `
  --infographic-style sketch-note `
  --output-dir '.\outputs\notebooklm\ai-agents'
```

## Workflow

1. Confirm the user has authenticated if this is the first NotebookLM run in the workspace.
2. Prefer the `pipeline` subcommand when moving URLs from `yt-research` into NotebookLM and generating one or more outputs.
3. Use `add-urls` when the notebook already exists.
4. Use `ask` for analysis-only questions.
5. Use `generate` for a single artifact when the notebook is already populated.

## Output Rules

- The script prints JSON so the result can be reused in later steps.
- Generated files are downloaded into the requested output directory.
- For infographic requests that mention handwritten, chalkboard, whiteboard, or sketchnote aesthetics, use `--infographic-style sketch-note` and include the style request in `--artifact-instructions`.
- Read [workflow.md](./references/workflow.md) when you need the argument names for artifact styles or output formats.

## Resources

- `scripts/notebooklm_pipeline.py`: Create notebooks, ingest URLs, ask for analysis, and generate/download artifacts.
- `references/workflow.md`: Quick reference for authentication, JSON inputs, and artifact tuning.
