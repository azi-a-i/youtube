# YouTube Research & NotebookLM - Web UI

Interactive browser workspace for the local **YouTube Research** and **NotebookLM** pipeline.

## Prerequisites

- Python 3.10+ with the project virtual environment (`.venv`) at the repo root
- The research and NotebookLM scripts already set up in this repository
- For NotebookLM: run `.\notebooklm.cmd login` once from the repo root before using the pipeline

## Install web dependencies

From the repo root:

```powershell
.\.venv\Scripts\pip install -r web\requirements.txt
```

## Run the app

From the repo root:

```powershell
.\run-web.cmd
```

Then open: `http://localhost:5000`

## What changed

- System readiness card for Python and NotebookLM auth
- Curated YouTube result cards with per-video selection
- One-click handoff of selected results into NotebookLM
- Prompt presets and artifact bundle controls
- Richer pipeline output with analysis text, downloads, and raw JSON

## Usage

1. Run `.\notebooklm.cmd login` once in a separate terminal.
2. Start the web app with `.\run-web.cmd`.
3. Search YouTube by topic, select the videos you want, then send them into NotebookLM.
4. Run the NotebookLM pipeline and download the generated infographic, slide deck, or flashcards from the result panel.

Generated artifacts are saved under `outputs/notebooklm/<notebook-slug>/` and can also be downloaded from the UI.
