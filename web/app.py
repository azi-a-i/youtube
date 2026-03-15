#!/usr/bin/env python
"""Flask app for YouTube Research + NotebookLM interactive web UI."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_ROOT = WORKSPACE_ROOT / "outputs" / "notebooklm"

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# In-memory job store: job_id -> { "status": "pending"|"running"|"done"|"error", "result"?, "error"?, "artifacts"? }
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def get_python_exe() -> Path:
    venv_python = WORKSPACE_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(os.environ.get("PYTHON", "python"))


def run_yt_research(
    query: str,
    count: int = 25,
    search_mode: str = "latest",
    sort: str = "views",
    pool_size: int | None = None,
) -> dict:
    pool = pool_size or max(count, count * 3)
    script = WORKSPACE_ROOT / "skills" / "yt-research" / "scripts" / "search_youtube.py"
    cmd = [
        str(get_python_exe()),
        str(script),
        "--query", query,
        "--count", str(count),
        "--search-mode", search_mode,
        "--sort", sort,
        "--pool-size", str(pool),
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
    return json.loads(result.stdout)


def run_notebooklm_pipeline(
    job_id: str,
    title: str,
    urls_data: dict | list[str],
    analysis_prompt: str,
    artifacts: list[str],
    artifact_instructions: str | None,
    infographic_style: str,
    infographic_orientation: str,
    slide_deck_format: str,
    slide_deck_output_format: str,
    flashcards_format: str,
) -> None:
    with jobs_lock:
        jobs[job_id]["status"] = "running"
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            if isinstance(urls_data, list) and urls_data and isinstance(urls_data[0], str):
                json.dump({"urls": urls_data}, f)
            else:
                json.dump(urls_data, f)
            urls_path = Path(f.name)

        script = WORKSPACE_ROOT / "skills" / "notebooklm" / "scripts" / "notebooklm_pipeline.py"
        output_dir = OUTPUTS_ROOT
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(get_python_exe()),
            str(script),
            "pipeline",
            "--title", title,
            "--urls-file", str(urls_path),
            "--analysis-prompt", analysis_prompt or "Summarize the top findings across these sources.",
            "--output-dir", str(output_dir),
            "--infographic-style", infographic_style,
            "--infographic-orientation", infographic_orientation,
            "--slide-deck-format", slide_deck_format,
            "--slide-deck-output-format", slide_deck_output_format,
            "--flashcards-format", flashcards_format,
        ]
        if artifact_instructions:
            cmd.extend(["--artifact-instructions", artifact_instructions])
        for a in artifacts:
            cmd.extend(["--artifact", a])

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

        with jobs_lock:
            if result.returncode != 0:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = result.stderr or result.stdout or "Pipeline failed"
                return
            out = json.loads(result.stdout)
            jobs[job_id]["status"] = "done"
            jobs[job_id]["result"] = out
            # Build artifact URLs from pipeline result (output_path in each artifact)
            artifacts_list = []
            for art in out.get("artifacts") or []:
                path_str = art.get("output_path")
                if path_str:
                    p = Path(path_str)
                    try:
                        rel = p.relative_to(OUTPUTS_ROOT)
                        artifacts_list.append({
                            "name": p.name,
                            "url": f"/outputs/notebooklm/{rel.as_posix()}",
                        })
                    except ValueError:
                        artifacts_list.append({"name": p.name, "url": None})
            jobs[job_id]["artifacts"] = artifacts_list
    except Exception as e:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


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
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/notebooklm/pipeline", methods=["POST"])
def api_notebooklm_pipeline():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    urls_data = data.get("urls_data")  # JSON from yt-research or { "urls": [...] }
    urls_list = data.get("urls_list")  # or plain list of URL strings
    if not title:
        return jsonify({"error": "title is required"}), 400
    urls_payload = urls_data if urls_data is not None else (urls_list if urls_list is not None else None)
    if not urls_payload:
        return jsonify({"error": "urls_data or urls_list is required"}), 400

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {"status": "pending", "result": None, "error": None, "artifacts": []}

    thread = threading.Thread(
        target=run_notebooklm_pipeline,
        kwargs={
            "job_id": job_id,
            "title": title,
            "urls_data": urls_payload,
            "analysis_prompt": data.get("analysis_prompt", "Summarize the top findings across these sources."),
            "artifacts": data.get("artifacts", ["infographic"]),
            "artifact_instructions": data.get("artifact_instructions") or None,
            "infographic_style": data.get("infographic_style", "auto"),
            "infographic_orientation": data.get("infographic_orientation", "portrait"),
            "slide_deck_format": data.get("slide_deck_format", "detailed"),
            "slide_deck_output_format": data.get("slide_deck_output_format", "pptx"),
            "flashcards_format": data.get("flashcards_format", "markdown"),
        },
    )
    thread.daemon = True
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>")
def api_job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/outputs/notebooklm/<path:subpath>")
def serve_artifact(subpath):
    """Serve generated NotebookLM artifacts (PDF, PNG, PPTX, etc.)."""
    safe_path = Path(subpath)
    if ".." in subpath or safe_path.is_absolute():
        return jsonify({"error": "Invalid path"}), 400
    file_path = OUTPUTS_ROOT / subpath
    if not file_path.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(file_path.parent, file_path.name, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
