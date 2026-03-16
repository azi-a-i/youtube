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
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

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
DEFAULT_SECRET_KEY = "llmnotetube-dev-secret-key"


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


def serialize_site_auth_status() -> dict[str, Any]:
    return {
        "authenticated": False,
        "provider": None,
        "mode": "none",
        "message": "LLMNoteTube does not require a site account.",
    }


def serialize_system_status() -> dict[str, Any]:
    python_command = get_python_command()
    python_ready = is_python_ready(python_command)
    auth_source = get_notebooklm_auth_source()
    notebooklm_ready = auth_source in {"env", "storage-file"} and python_ready
    site_auth = serialize_site_auth_status()
    workspace_ready = python_ready

    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "python_executable": python_command,
        "python_ready": python_ready,
        "server_mode": "production" if os.environ.get("PORT") else "local",
        "port": os.environ.get("PORT", "5000"),
        "pipeline_delivery_mode": "direct" if should_run_pipeline_inline() else "background",
        "site_auth": site_auth,
        "yt_research_ready": python_ready,
        "anonymous_research_ready": python_ready,
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
            "NotebookLM needs either backend auth or a browser-provided auth JSON session. "
            "YouTube research can run without any login."
        ),
        "workspace_ready": workspace_ready,
        "workspace_detail": (
            "Anonymous YouTube research is ready. Connect NotebookLM in your browser to run synthesis."
            if workspace_ready
            else "The Python backend is not ready."
        ),
        "browser_notebooklm_supported": True,
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
    return {
        "title": title,
        "page_name": page_name,
        "bootstrap": {
            "page": page_name,
            "browser_notebooklm_supported": True,
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


def build_pipeline_env(auth_json: str | None) -> tuple[dict[str, str], Path | None]:
    env = os.environ.copy()
    env.setdefault("NOTEBOOKLM_HOME", str(NOTEBOOKLM_HOME))

    if not auth_json:
        return env, None

    temp_home = Path(tempfile.mkdtemp(prefix="llmnotetube-auth-"))
    storage_path = temp_home / "storage_state.json"
    storage_path.write_text(auth_json, encoding="utf-8")
    env["NOTEBOOKLM_HOME"] = str(temp_home)
    env["NOTEBOOKLM_AUTH_JSON"] = auth_json
    return env, temp_home


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
    auth_json: str | None = None,
) -> dict[str, Any]:
    pipeline_env, temp_home = build_pipeline_env(auth_json)
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
            env=pipeline_env,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "Pipeline failed")
        return json.loads(result.stdout)
    finally:
        try:
            urls_path.unlink(missing_ok=True)
        except OSError:
            pass
        if temp_home is not None:
            shutil.rmtree(temp_home, ignore_errors=True)


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


@app.route("/connect")
def connect_page():
    return render_template("connect.html", **page_context("connect", "Connect"))


@app.route("/workflow")
def workflow_page():
    return render_template("workflow.html", **page_context("workflow", "Workflow"))


@app.route("/workspace")
def workspace_page():
    context = page_context("workspace", "Workspace")
    return render_template("workspace.html", **context)


@app.route("/healthz")
def healthcheck():
    return jsonify({"status": "ok", "time": now_iso()})


@app.route("/api/system/status")
def api_system_status():
    return jsonify(serialize_system_status())


@app.route("/api/auth/status")
def api_auth_status():
    return jsonify(serialize_site_auth_status())


@app.route("/api/notebooklm/validate", methods=["POST"])
def api_notebooklm_validate():
    data = request.get_json() or {}
    auth_json = (data.get("auth_json") or "").strip()
    if not auth_json:
        return jsonify({"error": "auth_json is required"}), 400

    try:
        from notebooklm.auth import extract_cookies_from_storage

        storage_state = json.loads(auth_json)
        cookies = extract_cookies_from_storage(storage_state)
    except Exception as exc:
        return jsonify({"error": f"Invalid NotebookLM auth payload: {exc}"}), 400

    return jsonify(
        {
            "valid": True,
            "cookie_count": len(cookies),
            "message": "NotebookLM auth JSON looks valid for this browser session.",
        }
    )


@app.route("/api/yt-research", methods=["POST"])
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

    provided_auth_json = (data.get("auth_json") or "").strip() or None
    auth_source = get_notebooklm_auth_source()
    if provided_auth_json is None and auth_source not in {"env", "storage-file"}:
        return (
            jsonify(
                {
                    "error": (
                        "NotebookLM is not connected yet. Add a browser session on the Connect page "
                        "or configure backend auth."
                    )
                }
            ),
            400,
        )

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
        "auth_json": provided_auth_json,
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
def api_jobs():
    with jobs_lock:
        payload = sorted(
            jobs.values(),
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )
    return jsonify({"jobs": payload[:10]})


@app.route("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/outputs/notebooklm/<path:subpath>")
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
