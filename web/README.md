# YouTube Research & NotebookLM - Web UI

Interactive browser workspace for the **YouTube Research** and **NotebookLM** pipeline, with both local and hosted deployment support.

## Local development

From the repo root:

```powershell
.\.venv\Scripts\pip install -r requirements.txt
.\notebooklm.cmd login
.\run-web.cmd
```

Then open `http://localhost:5000`.

## Hosted deployment

This app is designed for a persistent Python host such as Render, Railway, Fly.io, or a VPS. It is not a good fit for static or serverless-only platforms because the pipeline:

- launches Python subprocesses for `yt-dlp` and `notebooklm-py`
- writes generated artifacts to disk
- benefits from persistent NotebookLM auth storage or a secret-backed auth env var

### Required deployment pieces now included

- root `requirements.txt`
- production WSGI entrypoint `wsgi.py`
- Render blueprint `render.yaml`
- container build `Dockerfile`
- health endpoint at `/healthz`

### Environment variables

- `PORT`: port provided by your host
- `OUTPUTS_ROOT`: where generated NotebookLM files should be stored
- `NOTEBOOKLM_HOME`: where file-based NotebookLM state should live
- `NOTEBOOKLM_AUTH_JSON`: preferred for cloud deployment; set this to the full contents of your local `storage_state.json`

### Render setup

1. Create a new Blueprint deployment from this repo.
2. Keep the persistent disk mounted at `/var/data`.
3. Add a secret env var named `NOTEBOOKLM_AUTH_JSON`.
4. Redeploy.

The included `render.yaml` already points `OUTPUTS_ROOT` and `NOTEBOOKLM_HOME` at the mounted disk.

## Usage

1. Search YouTube by topic in the UI.
2. Select the videos you want to send into NotebookLM.
3. Run the NotebookLM pipeline for analysis and artifacts.
4. Download infographic, slide deck, or flashcards from the results panel.

Generated artifacts are saved under `outputs/notebooklm/<notebook-slug>/` locally, or under your configured `OUTPUTS_ROOT` in production.
