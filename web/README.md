# LLMNoteTube Web App

This version of LLMNoteTube is intentionally minimal:

- a simple email/password login gate
- anonymous YouTube search inside the protected workspace
- a backend NotebookLM wrapper powered by `notebooklm-py`
- downloadable NotebookLM output in `PDF`, `TXT`, or `DOCX`

## Local development

From the repo root:

```powershell
.\.venv\Scripts\pip install -r requirements.txt
cmd /c npm install
.\run-web.cmd
```

Then open `http://localhost:5000/login`.

## Login credentials

By default the app uses:

- email: `demo@llmnotetube.app`
- password: `llmnotetube`

Override them with:

- `WORKSPACE_LOGIN_EMAIL`
- `WORKSPACE_LOGIN_PASSWORD`

## NotebookLM backend auth

This build uses backend NotebookLM auth. Before live NotebookLM runs, authenticate the local or deployed environment once with:

```powershell
.\notebooklm.cmd login
```

The workspace `Connect NotebookLM` button checks whether that backend connection is ready.

## Frontend source

- templates: `web/templates/`
- source: `web/frontend/app.ts`
- compiled bundle: `web/static/app.js`

Useful commands:

```powershell
cmd /c npm run check:web
cmd /c npm run build:web
python scripts/sync_public.py
```
