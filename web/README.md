# YouTube Research & NotebookLM — Web UI

Interactive website to run **YouTube Research** (yt-dlp search) and the **NotebookLM pipeline** from the browser.

## Prerequisites

- Python 3.10+ with the project virtual environment (`.venv`) at the repo root, including:
  - `yt-dlp` and dependencies for the yt-research skill
  - `notebooklm-py` and dependencies for the NotebookLM skill
- For NotebookLM: run `.\notebooklm.cmd login` once from the repo root before using the pipeline.

## Install web dependencies

From the repo root:

```powershell
.\.venv\Scripts\pip install -r web\requirements.txt
```

Or from the `web` folder:

```powershell
pip install -r requirements.txt
```

## Run the app

From the **repo root** (so scripts and `.venv` are found):

```powershell
.\.venv\Scripts\python.exe web\app.py
```

Then open: **http://localhost:5000**

## Usage

1. **YouTube Research** — Enter a topic, set count/search mode/sort, then click *Search YouTube*. Results appear in a table. Use *Use these in NotebookLM →* to fill the NotebookLM URLs from the search.
2. **NotebookLM Pipeline** — Enter a notebook title and either paste the yt-research JSON or one URL per line. Choose analysis prompt and artifact types (infographic, slide deck, flashcards), then *Run NotebookLM pipeline*. Wait for the job to finish; download links for generated files appear when done.

Generated artifacts are saved under `outputs/notebooklm/<notebook-slug>/` and can be downloaded from the UI.
