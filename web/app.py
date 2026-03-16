#!/usr/bin/env python
"""Flask app for the LLMNoteTube interactive web UI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:  # pragma: no cover - dependency added at runtime
    OAuth = None

APP_ROOT = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_ROOT = APP_ROOT.parents[0]
WORKSPACE_ROOT = Path(
    os.environ.get("WORKSPACE_ROOT", str(DEFAULT_WORKSPACE_ROOT))
).resolve()
PUBLIC_ROOT = (WORKSPACE_ROOT / "public").resolve()
OUTPUTS_ROOT = Path(
    os.environ.get("OUTPUTS_ROOT", str(WORKSPACE_ROOT / "outputs" / "notebooklm"))
).resolve()
NOTEBOOKLM_HOME = Path(
    os.environ.get("NOTEBOOKLM_HOME", str(WORKSPACE_ROOT / ".notebooklm"))
).resolve()
NOTEBOOKLM_STORAGE = Path(
    os.environ.get("NOTEBOOKLM_STORAGE", str(NOTEBOOKLM_HOME / "storage_state.json"))
).resolve()
NOTEBOOKLM_CONTEXT = Path(
    os.environ.get("NOTEBOOKLM_CONTEXT", str(NOTEBOOKLM_HOME / "context.json"))
).resolve()
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
DEFAULT_SECRET_KEY = "llmnotetube-dev-secret-key"

F = TypeVar("F", bound=Callable[..., Any])


def env_truthy(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_serverless_runtime() -> bool:
    return bool(os.environ.get("VERCEL")) or env_truthy("SERVERLESS_MODE")


def should_run_pipeline_inline() -> bool:
    return is_serverless_runtime() or env_truthy("NOTEBOOKLM_INLINE_MODE")


def get_static_root() -> Path:
    if os.environ.get("VERCEL") and PUBLIC_ROOT.exists():
        return PUBLIC_ROOT
    return APP_ROOT / "static"


app = Flask(
    __name__,
    static_folder=str(get_static_root()),
    static_url_path="",
    template_folder=str(APP_ROOT / "templates"),
)
app.config.update(
    SECRET_KEY=os.environ.get("APP_SECRET_KEY", DEFAULT_SECRET_KEY),
    SESSION_COOKIE_NAME="llmnotetube_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=env_truthy("SESSION_COOKIE_SECURE") or bool(os.environ.get("VERCEL")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
CORS(app, supports_credentials=True)

oauth = OAuth(app) if OAuth else None
if oauth and os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": "openid email profile"},
    )

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()


def get_python_command() -> str:
    candidates = [
        WORKSPACE_ROOT / ".venv" / "Scripts" / "python.exe",
        WORKSPACE_ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    if sys.executable:
        return sys.executable

    env_python = os.environ.get("PYTHON")
    if env_python:
        resolved = shutil.which(env_python)
        return resolved or env_python

    return shutil.which("python") or shutil.which("python3") or "python"


def is_python_ready(command: str) -> bool:
    return Path(command).exists() or shutil.which(command) is not None


def get_notebooklm_auth_source() -> str:
    auth_json = os.environ.get("NOTEBOOKLM_AUTH_JSON")
    if auth_json is not None and auth_json.strip():
        return "env"
    if NOTEBOOKLM_STORAGE.exists():
        return "storage-file"
    if auth_json is not None:
        return "env-invalid"
    return "missing"


def google_oauth_configured() -> bool:
    return (
        OAuth is not None
        and bool(os.environ.get("GOOGLE_CLIENT_ID"))
        and bool(os.environ.get("GOOGLE_CLIENT_SECRET"))
    )


def get_current_user() -> dict[str, Any] | None:
    payload = session.get("user")
    if isinstance(payload, dict) and payload.get("email"):
        return payload
    return None


def api_login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if get_current_user() is None:
            return (
                jsonify(
                    {
                        "error": "Google login required before using the workspace.",
                        "login_url": url_for("auth_login", next=request.path),
                    }
                ),
                401,
            )
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def serialize_site_auth_status() -> dict[str, Any]:
    user = get_current_user()
    return {
        "authenticated": user is not None,
        "google_oauth_configured": google_oauth_configured(),
        "login_url": url_for("auth_login", next=url_for("workspace_page")),
        "logout_url": url_for("auth_logout"),
        "user": user,
    }


def serialize_system_status() -> dict[str, Any]:
    python_command = get_python_command()
    python_ready = is_python_ready(python_command)
    auth_source = get_notebooklm_auth_source()
    notebooklm_ready = auth_source in {"env", "storage-file"} and python_ready
    site_auth = serialize_site_auth_status()
    workspace_ready = site_auth["authenticated"] and python_ready and notebooklm_ready

    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "python_executable": python_command,
        "python_ready": python_ready,
        "server_mode": "production" if os.environ.get("PORT") else "local",
        "port": os.environ.get("PORT", "5000"),
        "pipeline_delivery_mode": "direct" if should_run_pipeline_inline() else "background",
        "site_auth": site_auth,
        "yt_research_ready": python_ready,
        "notebooklm_home": str(NOTEBOOKLM_HOME),
        "notebooklm_ready": notebooklm_ready,
        "auth_ready": notebooklm_ready,
        "auth_source": auth_source,
        "auth_env_var": "NOTEBOOKLM_AUTH_JSON",
        "storage_state_path": str(NOTEBOOKLM_STORAGE),
        "context_path": str(NOTEBOOKLM_CONTEXT),
        "outputs_root": str(OUTPUTS_ROOT),
        "login_command": r".\notebooklm.cmd login",
        "run_command": r".\run-web.cmd",
        "deploy_auth_hint": (
            "NotebookLM uses backend session storage or NOTEBOOKLM_AUTH_JSON. "
            "Google site login unlocks the workspace, but NotebookLM still needs "
            "its own backend auth connection."
        ),
        "workspace_ready": workspace_ready,
        "workspace_detail": (
            "Ready for signed-in research and NotebookLM synthesis."
            if workspace_ready
            else "Sign in with Google and make sure the NotebookLM backend is connected."
        ),
        "skills": {
            "yt_research": str(
                WORKSPACE_ROOT / "skills" / "yt-research" / "scripts" / "search_youtube.py"
            ),
            "notebooklm": str(
                WORKSPACE_ROOT / "skills" / "notebooklm" / "scripts" / "notebooklm_pipeline.py"
            ),
        },
    }


def page_context(page_name: str, title: str) -> dict[str, Any]:
    user = get_current_user()
    return {
        "title": title,
        "page_name": page_name,
        "current_user": user,
        "google_oauth_configured": google_oauth_configured(),
        "bootstrap": {
            "page": page_name,
            "user": user,
            "google_oauth_configured": google_oauth_configured(),
        },
    }


def set_job(job_id: str, payload: dict[str, Any]) -> None:
    with jobs_lock:
        jobs[job_id] = payload


def update_job(job_id: str, **changes: Any) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job.update(changes)
        job["updated_at"] = now_iso()


def list_artifact_links(result_payload: dict[str, Any]) -> list[dict[str, str | None]]:
    artifacts_list: list[dict[str, str | None]] = []
    for artifact in result_payload.get("artifacts") or []:
        path_str = artifact.get("output_path")
        if not path_str:
            continue
        output_path = Path(path_str)
        try:
            rel = output_path.relative_to(OUTPUTS_ROOT)
            url = f"/outputs/notebooklm/{rel.as_posix()}"
        except ValueError:
            url = None
        artifacts_list.append(
            {
                "name": output_path.name,
                "kind": artifact.get("artifact"),
                "url": url,
            }
        )
    return artifacts_list


def run_yt_research(
    query: str,
    count: int = 25,
    search_mode: str = "latest",
    sort: str = "views",
    pool_size: int | None = None,
) -> dict[str, Any]:
    pool = pool_size or max(count, count * 3)
    script = WORKSPACE_ROOT / "skills" / "yt-research" / "scripts" / "search_youtube.py"
    cmd = [
        get_python_command(),
        str(script),
        "--query",
        query,
        "--count",
        str(count),
        "--search-mode",
        search_mode,
        "--sort",
        sort,
        "--pool-size",
        str(pool),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "yt-research failed")
    payload = json.loads(result.stdout)
    warnings = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    payload["warnings"] = warnings
    return payload


def execute_notebooklm_pipeline(
    *,
    title: str,
    urls_data: dict[str, Any] | list[str],
    analysis_prompt: str,
    artifacts: list[str],
    artifact_instructions: str | None,
    infographic_style: str,
    infographic_orientation: str,
    slide_deck_format: str,
    slide_deck_output_format: str,
    flashcards_format: str,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as handle:
        if isinstance(urls_data, list):
            json.dump({"urls": urls_data}, handle)
        else:
            json.dump(urls_data, handle)
        urls_path = Path(handle.name)

    try:
        script = WORKSPACE_ROOT / "skills" / "notebooklm" / "scripts" / "notebooklm_pipeline.py"
        OUTPUTS_ROOT.mkdir(parents=True, exist_ok=True)

        cmd = [
            get_python_command(),
            str(script),
            "pipeline",
            "--title",
            title,
            "--urls-file",
            str(urls_path),
            "--analysis-prompt",
            analysis_prompt or "Summarize the top findings across these sources.",
            "--output-dir",
            str(OUTPUTS_ROOT),
            "--infographic-style",
            infographic_style,
            "--infographic-orientation",
            infographic_orientation,
            "--slide-deck-format",
            slide_deck_format,
            "--slide-deck-output-format",
            slide_deck_output_format,
            "--flashcards-format",
            flashcards_format,
        ]
        if artifact_instructions:
            cmd.extend(["--artifact-instructions", artifact_instructions])
        for artifact in artifacts:
            cmd.extend(["--artifact", artifact])

        timeout_seconds = 240 if should_run_pipeline_inline() else 1800
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "Pipeline failed")
        return json.loads(result.stdout)
    finally:
        try:
            urls_path.unlink(missing_ok=True)
        except OSError:
            pass


def run_notebooklm_pipeline(job_id: str, **kwargs: Any) -> None:
    update_job(
        job_id,
        status="running",
        stage="Creating notebook and importing sources",
        started_at=now_iso(),
    )
    try:
        payload = execute_notebooklm_pipeline(**kwargs)
        update_job(
            job_id,
            status="done",
            stage="Completed",
            finished_at=now_iso(),
            result=payload,
            artifacts=list_artifact_links(payload),
        )
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            stage="Pipeline failed",
            finished_at=now_iso(),
            error=str(exc),
        )


@app.route("/")
@app.route("/overview")
def overview_page():
    return render_template("overview.html", **page_context("overview", "Overview"))


@app.route("/workflow")
def workflow_page():
    return render_template("workflow.html", **page_context("workflow", "Workflow"))


@app.route("/workspace")
def workspace_page():
    context = page_context("workspace", "Workspace")
    context["workspace_access"] = get_current_user() is not None
    return render_template("workspace.html", **context)


@app.route("/auth/login")
def auth_login():
    if not google_oauth_configured() or oauth is None:
        return redirect(url_for("workspace_page"))

    session["post_login_redirect"] = request.args.get("next") or url_for("workspace_page")
    redirect_uri = url_for("auth_callback", _external=True)
    return oauth.google.authorize_redirect(
        redirect_uri,
        prompt="select_account",
    )


@app.route("/auth/callback")
def auth_callback():
    if not google_oauth_configured() or oauth is None:
        return redirect(url_for("overview_page"))

    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = oauth.google.get("userinfo").json()
        session["user"] = {
            "email": userinfo.get("email"),
            "name": userinfo.get("name") or userinfo.get("given_name") or "Google User",
            "picture": userinfo.get("picture"),
        }
        session.permanent = True
    except Exception:
        session.pop("user", None)
    return redirect(session.pop("post_login_redirect", url_for("workspace_page")))


@app.route("/auth/logout")
def auth_logout():
    session.pop("user", None)
    session.pop("post_login_redirect", None)
    return redirect(url_for("overview_page"))


@app.route("/healthz")
def healthcheck():
    return jsonify({"status": "ok", "time": now_iso()})


@app.route("/api/system/status")
def api_system_status():
    return jsonify(serialize_system_status())


@app.route("/api/auth/status")
def api_auth_status():
    return jsonify(serialize_site_auth_status())


@app.route("/api/yt-research", methods=["POST"])
@api_login_required
def api_yt_research():
    data = request.get_json() or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    try:
        payload = run_yt_research(
            query=query,
            count=int(data.get("count", 25)),
            search_mode=data.get("search_mode", "latest"),
            sort=data.get("sort", "views"),
            pool_size=data.get("pool_size"),
        )
        return jsonify(payload)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "YouTube search timed out"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/notebooklm/pipeline", methods=["POST"])
@api_login_required
def api_notebooklm_pipeline():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    urls_data = data.get("urls_data")
    urls_list = data.get("urls_list")

    if not title:
        return jsonify({"error": "title is required"}), 400

    urls_payload = urls_data if urls_data is not None else urls_list
    if not urls_payload:
        return jsonify({"error": "urls_data or urls_list is required"}), 400

    pipeline_kwargs = {
        "title": title,
        "urls_data": urls_payload,
        "analysis_prompt": data.get(
            "analysis_prompt",
            "Summarize the top findings across these sources.",
        ),
        "artifacts": data.get("artifacts", ["infographic"]),
        "artifact_instructions": data.get("artifact_instructions") or None,
        "infographic_style": data.get("infographic_style", "auto"),
        "infographic_orientation": data.get("infographic_orientation", "portrait"),
        "slide_deck_format": data.get("slide_deck_format", "detailed"),
        "slide_deck_output_format": data.get("slide_deck_output_format", "pptx"),
        "flashcards_format": data.get("flashcards_format", "markdown"),
    }

    if should_run_pipeline_inline():
        try:
            payload = execute_notebooklm_pipeline(**pipeline_kwargs)
            return jsonify(
                {
                    "mode": "direct",
                    "result": payload,
                    "artifacts": list_artifact_links(payload),
                }
            )
        except subprocess.TimeoutExpired:
            return jsonify({"error": "NotebookLM pipeline timed out in direct mode"}), 504
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    job_id = str(uuid.uuid4())
    set_job(
        job_id,
        {
            "id": job_id,
            "status": "pending",
            "stage": "Queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "started_at": None,
            "finished_at": None,
            "request": {
                "title": title,
                "artifact_count": len(data.get("artifacts") or []),
            },
            "result": None,
            "error": None,
            "artifacts": [],
        },
    )

    thread = threading.Thread(
        target=run_notebooklm_pipeline,
        kwargs={"job_id": job_id, **pipeline_kwargs},
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id, "mode": "background"})


@app.route("/api/jobs")
@api_login_required
def api_jobs():
    with jobs_lock:
        payload = sorted(
            jobs.values(),
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )
    return jsonify({"jobs": payload[:10]})


@app.route("/api/jobs/<job_id>")
@api_login_required
def api_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/outputs/notebooklm/<path:subpath>")
@api_login_required
def serve_artifact(subpath: str):
    safe_path = Path(subpath)
    if ".." in subpath or safe_path.is_absolute():
        return jsonify({"error": "Invalid path"}), 400
    file_path = OUTPUTS_ROOT / subpath
    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(file_path.parent, file_path.name, as_attachment=True)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=env_truthy("FLASK_DEBUG"),
    )
