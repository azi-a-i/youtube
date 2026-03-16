# LLMNoteTube Web App

Interactive browser product for YouTube topic research and NotebookLM synthesis, with a three-page flow:

- `Overview`
- `Workflow`
- `Workspace`

The workspace is now gated by Google sign-in.

## Local development

From the repo root:

```powershell
.\.venv\Scripts\pip install -r requirements.txt
cmd /c npm install
set GOOGLE_CLIENT_ID=your-google-client-id
set GOOGLE_CLIENT_SECRET=your-google-client-secret
set APP_SECRET_KEY=your-session-secret
.\notebooklm.cmd login
.\run-web.cmd
```

Then open `http://localhost:5000`.

## Frontend source

The product UI now lives in Flask templates plus a TypeScript client:

- templates: `web/templates/`
- source: `web/frontend/app.ts`
- compiled browser bundle: `web/static/app.js`

Useful commands from the repo root:

```powershell
cmd /c npm run check:web
cmd /c npm run build:web
```

## Hosted deployment

This app is designed for a persistent Python host such as Render, Railway, Fly.io, or a VPS. It can render on Vercel, but the full NotebookLM pipeline is still better on a persistent host because the workflow:

- launches Python subprocesses for `yt-dlp` and `notebooklm-py`
- writes generated artifacts to disk
- benefits from persistent NotebookLM auth storage or a secret-backed auth env var

### Required deployment pieces now included

- root `requirements.txt`
- root `app.py` for Vercel/Flask detection
- root `pyproject.toml` for Vercel's current Python builder
- production WSGI entrypoint `wsgi.py`
- Render blueprint `render.yaml`
- container build `Dockerfile`
- health endpoint at `/healthz`

### Environment variables

- `PORT`: port provided by your host
- `APP_SECRET_KEY`: Flask session signing key
- `GOOGLE_CLIENT_ID`: Google OAuth client ID for site login
- `GOOGLE_CLIENT_SECRET`: Google OAuth client secret for site login
- `OUTPUTS_ROOT`: where generated NotebookLM files should be stored
- `NOTEBOOKLM_HOME`: where file-based NotebookLM state should live
- `NOTEBOOKLM_AUTH_JSON`: preferred for cloud deployment; set this to the full contents of your local `storage_state.json`

### Render setup

1. Create a new Blueprint deployment from this repo.
2. Keep the persistent disk mounted at `/var/data`.
3. Add a secret env var named `NOTEBOOKLM_AUTH_JSON`.
4. Redeploy.

The included `render.yaml` already points `OUTPUTS_ROOT` and `NOTEBOOKLM_HOME` at the mounted disk.

### Vercel note

Vercel can now build and serve the multi-page product shell and Google-gated workspace. The live NotebookLM pipeline is still limited by serverless constraints such as long-running subprocesses and non-persistent in-memory jobs, so Render or another persistent Python host remains the better production target for full use.

## Usage

1. Open `Overview` for the product intro.
2. Use `Workflow` to understand the research path.
3. Sign in with Google to unlock `Workspace`.
4. Search YouTube by topic, select the videos you want, then send them into NotebookLM when the backend status is ready.

Generated artifacts are saved under `outputs/notebooklm/<notebook-slug>/` locally, or under your configured `OUTPUTS_ROOT` in production.
