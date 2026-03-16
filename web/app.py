#!/usr/bin/env python
"""Flask app for the simplified LLMNoteTube workspace."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar
from xml.sax.saxutils import escape as xml_escape

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
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
DEFAULT_SECRET_KEY = "llmnotetube-dev-secret-key"
DEFAULT_LOGIN_EMAIL = "demo@llmnotetube.app"
DEFAULT_LOGIN_PASSWORD = "llmnotetube"
URL_RE = re.compile(r"https?://[^\s<>\"]+")
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
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
CORS(app, supports_credentials=True)

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()


def configured_login_email() -> str:
    return os.environ.get("WORKSPACE_LOGIN_EMAIL", DEFAULT_LOGIN_EMAIL)


def configured_login_password() -> str:
    return os.environ.get("WORKSPACE_LOGIN_PASSWORD", DEFAULT_LOGIN_PASSWORD)


def using_demo_credentials() -> bool:
    return (
        configured_login_email() == DEFAULT_LOGIN_EMAIL
        and configured_login_password() == DEFAULT_LOGIN_PASSWORD
    )


def get_current_user() -> str | None:
    user_email = session.get("user_email")
    return user_email if isinstance(user_email, str) and user_email else None


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if not get_current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required."}), 401
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)

    return wrapped  # type: ignore[return-value]


def page_context(page_name: str, title: str) -> dict[str, Any]:
    return {
        "title": title,
        "page_name": page_name,
        "current_user": get_current_user(),
        "bootstrap": {
            "page": page_name,
        },
    }


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


def get_notebooklm_auth_source() -> str:
    auth_json = os.environ.get("NOTEBOOKLM_AUTH_JSON")
    if auth_json is not None and auth_json.strip():
        return "env"
    if NOTEBOOKLM_STORAGE.exists():
        return "storage-file"
    if auth_json is not None:
        return "env-invalid"
    return "missing"


def notebooklm_backend_ready() -> bool:
    return get_notebooklm_auth_source() in {"env", "storage-file"}


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


def run_yt_research(query: str, count: int = 12) -> dict[str, Any]:
    script = WORKSPACE_ROOT / "skills" / "yt-research" / "scripts" / "search_youtube.py"
    cmd = [
        get_python_command(),
        str(script),
        "--query",
        query,
        "--count",
        str(count),
        "--search-mode",
        "relevance",
        "--sort",
        "views",
        "--pool-size",
        str(max(count * 2, count)),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "yt-research failed")

    payload = json.loads(result.stdout)
    videos = payload.get("videos") or []
    simplified = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
        }
        for item in videos
        if item.get("title") and item.get("url")
    ]
    return {"query": query, "videos": simplified[:count]}


def execute_notebooklm_analysis(
    *,
    title: str,
    urls_data: dict[str, Any] | list[str],
    analysis_prompt: str,
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
        ]
        timeout_seconds = 240 if should_run_pipeline_inline() else 1800
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "NotebookLM analysis failed")
        return json.loads(result.stdout)
    finally:
        try:
            urls_path.unlink(missing_ok=True)
        except OSError:
            pass


def run_notebooklm_job(job_id: str, **kwargs: Any) -> None:
    update_job(
        job_id,
        status="running",
        stage="NotebookLM is analyzing sources",
        started_at=now_iso(),
    )
    try:
        payload = execute_notebooklm_analysis(**kwargs)
        answer = (
            ((payload.get("analysis") or {}).get("answer"))
            or "NotebookLM returned no answer."
        )
        update_job(
            job_id,
            status="done",
            stage="Completed",
            finished_at=now_iso(),
            result={
                "title": (payload.get("notebook") or {}).get("title") or kwargs.get("title"),
                "answer": answer,
                "raw": payload,
            },
        )
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            stage="NotebookLM failed",
            finished_at=now_iso(),
            error=str(exc),
        )


def extract_urls_from_text(raw_text: str) -> list[str]:
    urls = []
    seen: set[str] = set()
    for match in URL_RE.findall(raw_text):
        cleaned = match.rstrip(".,);]")
        if cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls


def build_txt_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def build_pdf_bytes(content: str, title: str) -> bytes:
    lines = [title, ""] + content.splitlines()
    normalized = [line[:100] for line in lines[:45]]

    def pdf_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    y = 760
    commands = ["BT", "/F1 12 Tf", "50 790 Td"]
    for index, line in enumerate(normalized):
        if index == 0:
            commands.append(f"({pdf_escape(line)}) Tj")
            y -= 24
            continue
        commands.append(f"1 0 0 1 50 {y} Tm ({pdf_escape(line or ' ')}) Tj")
        y -= 16
        if y < 60:
            break
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")

    objects: list[bytes] = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1")
        + stream
        + b"\nendstream endobj\n"
    )

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(output.tell())
        output.write(obj)
    xref_start = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.write(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF"
        ).encode("latin-1")
    )
    return output.getvalue()


def build_docx_bytes(content: str, title: str) -> bytes:
    paragraphs = [title, ""] + content.splitlines()
    paragraph_xml = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{xml_escape(line or ' ')}</w:t></w:r></w:p>"
        for line in paragraphs
    )
    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
        "mc:Ignorable=\"w14 wp14\">"
        f"<w:body>{paragraph_xml}<w:sectPr>"
        "<w:pgSz w:w=\"12240\" w:h=\"15840\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" "
        "w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/>"
        "</w:sectPr></w:body></w:document>"
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
            "<Override PartName=\"/word/document.xml\" "
            "ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
            "<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>"
            "<Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>"
            "</Types>",
        )
        docx.writestr(
            "_rels/.rels",
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/>"
            "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>"
            "<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>"
            "</Relationships>",
        )
        docx.writestr(
            "docProps/core.xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" "
            "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" "
            "xmlns:dcterms=\"http://purl.org/dc/terms/\" "
            "xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" "
            "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
            f"<dc:title>{xml_escape(title)}</dc:title>"
            "<dc:creator>LLMNoteTube</dc:creator>"
            f"<cp:lastModifiedBy>LLMNoteTube</cp:lastModifiedBy>"
            f"<dcterms:created xsi:type=\"dcterms:W3CDTF\">{xml_escape(now_iso())}</dcterms:created>"
            f"<dcterms:modified xsi:type=\"dcterms:W3CDTF\">{xml_escape(now_iso())}</dcterms:modified>"
            "</cp:coreProperties>",
        )
        docx.writestr(
            "docProps/app.xml",
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" "
            "xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
            "<Application>LLMNoteTube</Application>"
            "</Properties>",
        )
        docx.writestr(
            "word/_rels/document.xml.rels",
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"></Relationships>",
        )
        docx.writestr("word/document.xml", document_xml)
    return output.getvalue()


def build_export_file(content: str, title: str, file_format: str) -> tuple[io.BytesIO, str, str]:
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.strip()).strip("-") or "llmnotetube-output"
    if file_format == "txt":
        return io.BytesIO(build_txt_bytes(content)), "text/plain", f"{safe_title}.txt"
    if file_format == "pdf":
        return io.BytesIO(build_pdf_bytes(content, title)), "application/pdf", f"{safe_title}.pdf"
    if file_format == "docx":
        return (
            io.BytesIO(build_docx_bytes(content, title)),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"{safe_title}.docx",
        )
    raise ValueError("Unsupported format.")


def render_login(error: str | None = None) -> str:
    return render_template(
        "login.html",
        title="Login",
        page_name="login",
        current_user=get_current_user(),
        login_error=error,
        show_demo_credentials=using_demo_credentials(),
        demo_email=configured_login_email(),
        demo_password=configured_login_password(),
        bootstrap={"page": "login"},
    )


@app.route("/")
def root_page():
    if get_current_user():
        return redirect(url_for("workspace_page"))
    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        if get_current_user():
            return redirect(url_for("workspace_page"))
        return render_login()

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""

    if email == configured_login_email() and password == configured_login_password():
        session.permanent = True
        session["user_email"] = email
        return redirect(url_for("workspace_page"))

    return render_login("Invalid email or password.")


@app.route("/logout", methods=["POST"])
@login_required
def logout_page():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/workspace")
@login_required
def workspace_page():
    return render_template("workspace.html", **page_context("workspace", "Workspace"))


@app.route("/healthz")
def healthcheck():
    return jsonify({"status": "ok", "time": now_iso()})


@app.route("/api/yt-research", methods=["POST"])
@login_required
def api_yt_research():
    data = request.get_json() or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    try:
        payload = run_yt_research(query=query, count=int(data.get("count", 12)))
        return jsonify(payload)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "YouTube search timed out."}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/notebooklm/connect", methods=["POST"])
@login_required
def api_notebooklm_connect():
    if notebooklm_backend_ready():
        return jsonify({"connected": True, "message": "NotebookLM backend is ready."})
    return (
        jsonify(
            {
                "connected": False,
                "error": (
                    "NotebookLM backend is not connected yet. Run .\\notebooklm.cmd login "
                    "on the server or local workspace first."
                ),
            }
        ),
        400,
    )


@app.route("/api/notebooklm/run", methods=["POST"])
@login_required
def api_notebooklm_run():
    if not notebooklm_backend_ready():
        return (
            jsonify(
                {
                    "error": (
                        "NotebookLM backend is not connected. Run .\\notebooklm.cmd login "
                        "before using this feature."
                    )
                }
            ),
            400,
        )

    data = request.get_json() or {}
    title = (data.get("title") or "").strip() or "LLMNoteTube Research"
    prompt = (data.get("prompt") or "").strip() or "Summarize the top findings across these sources."
    sources_text = (data.get("sources_text") or "").strip()
    urls = extract_urls_from_text(sources_text)

    if not urls:
        return jsonify({"error": "Paste at least one YouTube URL."}), 400

    kwargs = {
        "title": title,
        "urls_data": {"urls": urls},
        "analysis_prompt": prompt,
    }

    if should_run_pipeline_inline():
        try:
            payload = execute_notebooklm_analysis(**kwargs)
            answer = ((payload.get("analysis") or {}).get("answer")) or "NotebookLM returned no answer."
            return jsonify(
                {
                    "mode": "direct",
                    "result": {
                        "title": (payload.get("notebook") or {}).get("title") or title,
                        "answer": answer,
                        "raw": payload,
                    },
                }
            )
        except subprocess.TimeoutExpired:
            return jsonify({"error": "NotebookLM timed out."}), 504
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
            "result": None,
            "error": None,
        },
    )
    thread = threading.Thread(
        target=run_notebooklm_job,
        kwargs={"job_id": job_id, **kwargs},
        daemon=True,
    )
    thread.start()
    return jsonify({"mode": "background", "job_id": job_id})


@app.route("/api/jobs/<job_id>")
@login_required
def api_job_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(job)


@app.route("/api/download-analysis", methods=["POST"])
@login_required
def api_download_analysis():
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()
    title = (data.get("title") or "").strip() or "LLMNoteTube Output"
    file_format = (data.get("format") or "").strip().lower()

    if not content:
        return jsonify({"error": "content is required"}), 400
    if file_format not in {"txt", "pdf", "docx"}:
        return jsonify({"error": "format must be txt, pdf, or docx"}), 400

    try:
        file_handle, mime_type, filename = build_export_file(content, title, file_format)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    file_handle.seek(0)
    return send_file(
        file_handle,
        mimetype=mime_type,
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=env_truthy("FLASK_DEBUG"),
    )
