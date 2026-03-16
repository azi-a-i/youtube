#!/usr/bin/env python
"""Flask app for the YouTube Research + NotebookLM interactive web UI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

APP_ROOT = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_ROOT = APP_ROOT.parents[0]
WORKSPACE_ROOT = Path(
    os.environ.get("WORKSPACE_ROOT", str(DEFAULT_WORKSPACE_ROOT))
).resolve()
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

app = Flask(__name__, static_folder=str(APP_ROOT / "static"), static_url_path="")
CORS(app)

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_truthy(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def serialize_system_status() -> dict[str, Any]:
    python_command = get_python_command()
    auth_source = get_notebooklm_auth_source()
    return {
        "workspace_root": str(WORKSPACE_ROOT),
        "python_executable": python_command,
        "python_ready": is_python_ready(python_command),
        "server_mode": "production" if os.environ.get("PORT") else "local",
        "port": os.environ.get("PORT", "5000"),
        "notebooklm_home": str(NOTEBOOKLM_HOME),
        "auth_ready": auth_source in {"env", "storage-file"},
        "auth_source": auth_source,
        "auth_env_var": "NOTEBOOKLM_AUTH_JSON",
        "storage_state_path": str(NOTEBOOKLM_STORAGE),
        "context_path": str(NOTEBOOKLM_CONTEXT),
        "outputs_root": str(OUTPUTS_ROOT),
        "login_command": r".\notebooklm.cmd login",
        "run_command": r".\run-web.cmd",
        "deploy_auth_hint": (
            "For hosted deployments, set NOTEBOOKLM_AUTH_JSON to the full contents "
            "of storage_state.json so the server can authenticate without an "
            "interactive browser login."
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


def run_notebooklm_pipeline(
    job_id: str,
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
) -> None:
    update_job(
        job_id,
        status="running",
        stage="Creating notebook and importing sources",
        started_at=now_iso(),
    )
    try:
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

        update_job(job_id, stage="NotebookLM analysis and artifact generation")
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=1800,
            encoding="utf-8",
        )
        try:
            urls_path.unlink(missing_ok=True)
        except OSError:
            pass

        if result.returncode != 0:
            update_job(
                job_id,
                status="error",
                stage="Pipeline failed",
                finished_at=now_iso(),
                error=result.stderr or result.stdout or "Pipeline failed",
            )
            return

        payload = json.loads(result.stdout)
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
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/healthz")
def healthcheck():
    return jsonify({"status": "ok", "time": now_iso()})


@app.route("/api/system/status")
def api_system_status():
    return jsonify(serialize_system_status())


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
        kwargs={
            "job_id": job_id,
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
        },
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id})


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
