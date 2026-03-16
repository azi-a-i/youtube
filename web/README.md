# LLMNoteTube Web App

LLMNoteTube is a three-page web product for:

- anonymous YouTube topic research
- browser-connected NotebookLM synthesis
- artifact generation from one workspace

Pages:

- `Overview`
- `Workflow`
- `Connect`
- `Workspace`

## Local development

From the repo root:

```powershell
.\.venv\Scripts\pip install -r requirements.txt
cmd /c npm install
.\run-web.cmd
```

Then open `http://localhost:5000`.

## NotebookLM connection model

LLMNoteTube does not require a Google site login.

YouTube search works anonymously as long as the Python backend is available.

NotebookLM synthesis requires one of these:

- a browser-provided NotebookLM session pasted into the `Connect` page or the workspace connection panel
- a deployment-level `NOTEBOOKLM_HOME` / `storage_state.json`
- a deployment-level `NOTEBOOKLM_AUTH_JSON`

The browser connection flow validates the pasted `storage_state.json` contents and then includes that session in NotebookLM pipeline requests from the workspace.

## Frontend source

- templates: `web/templates/`
- TypeScript source: `web/frontend/app.ts`
- compiled browser bundle: `web/static/app.js`

Useful commands from the repo root:

```powershell
cmd /c npm run check:web
cmd /c npm run build:web
python scripts/sync_public.py
```

## Hosted deployment

This app can render on Vercel, but the full NotebookLM pipeline is still better on a persistent Python host because it:

- launches Python subprocesses for `yt-dlp` and `notebooklm-py`
- writes generated artifacts to disk
- benefits from persistent auth storage and background job continuity

### Included deployment files

- root `requirements.txt`
- root `app.py`
- `api/index.py`
- root `pyproject.toml`
- `wsgi.py`
- `render.yaml`
- `Dockerfile`
- `Procfile`
- `vercel.json`

### Environment variables

- `PORT`: port provided by your host
- `APP_SECRET_KEY`: optional Flask secret key
- `OUTPUTS_ROOT`: where generated NotebookLM files should be stored
- `NOTEBOOKLM_HOME`: where file-based NotebookLM state should live
- `NOTEBOOKLM_AUTH_JSON`: optional shared NotebookLM session for the whole deployment

## Usage

1. Open `Overview` for the product intro.
2. Open `Connect` if you want to attach a NotebookLM browser session.
3. Use `Workspace` to search YouTube, curate videos, and run NotebookLM synthesis.

Generated artifacts are saved under `outputs/notebooklm/<notebook-slug>/` locally, or under your configured `OUTPUTS_ROOT` in production.
