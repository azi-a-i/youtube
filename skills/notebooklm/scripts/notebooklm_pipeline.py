#!/usr/bin/env python
"""NotebookLM workflow helpers for this workspace."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_NOTEBOOKLM_HOME = WORKSPACE_ROOT / ".notebooklm"
DEFAULT_OUTPUT_ROOT = WORKSPACE_ROOT / "outputs" / "notebooklm"

os.environ.setdefault("NOTEBOOKLM_HOME", str(DEFAULT_NOTEBOOKLM_HOME))

from notebooklm.client import NotebookLMClient
from notebooklm.types import (
    InfographicDetail,
    InfographicOrientation,
    InfographicStyle,
    QuizDifficulty,
    QuizQuantity,
    SlideDeckFormat,
    SlideDeckLength,
)

DEFAULT_ANALYSIS_PROMPT = (
    "Summarize the top findings across these sources. "
    "Highlight repeated themes, outliers, and concrete takeaways."
)

INFOGRAPHIC_STYLE_MAP = {
    "auto": InfographicStyle.AUTO_SELECT,
    "sketch-note": InfographicStyle.SKETCH_NOTE,
    "professional": InfographicStyle.PROFESSIONAL,
    "bento-grid": InfographicStyle.BENTO_GRID,
    "editorial": InfographicStyle.EDITORIAL,
    "instructional": InfographicStyle.INSTRUCTIONAL,
    "bricks": InfographicStyle.BRICKS,
    "clay": InfographicStyle.CLAY,
    "anime": InfographicStyle.ANIME,
    "kawaii": InfographicStyle.KAWAII,
    "scientific": InfographicStyle.SCIENTIFIC,
}
INFOGRAPHIC_ORIENTATION_MAP = {
    "landscape": InfographicOrientation.LANDSCAPE,
    "portrait": InfographicOrientation.PORTRAIT,
    "square": InfographicOrientation.SQUARE,
}
INFOGRAPHIC_DETAIL_MAP = {
    "concise": InfographicDetail.CONCISE,
    "standard": InfographicDetail.STANDARD,
    "detailed": InfographicDetail.DETAILED,
}
SLIDE_DECK_FORMAT_MAP = {
    "detailed": SlideDeckFormat.DETAILED_DECK,
    "presenter": SlideDeckFormat.PRESENTER_SLIDES,
}
SLIDE_DECK_LENGTH_MAP = {
    "default": SlideDeckLength.DEFAULT,
    "short": SlideDeckLength.SHORT,
}
FLASHCARD_DIFFICULTY_MAP = {
    "easy": QuizDifficulty.EASY,
    "medium": QuizDifficulty.MEDIUM,
    "hard": QuizDifficulty.HARD,
}
FLASHCARD_QUANTITY_MAP = {
    "fewer": QuizQuantity.FEWER,
    "standard": QuizQuantity.STANDARD,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create NotebookLM notebooks, add URLs, ask questions, and generate artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new notebook.")
    create.add_argument("--title", required=True, help="Notebook title.")

    add_urls = subparsers.add_parser("add-urls", help="Add URL sources to a notebook.")
    add_urls.add_argument("--notebook-id", required=True, help="Notebook ID.")
    add_urls.add_argument("--url", action="append", default=[], help="URL to add.")
    add_urls.add_argument(
        "--urls-file",
        type=Path,
        default=None,
        help="JSON or text file containing URLs.",
    )
    add_urls.add_argument(
        "--source-wait-timeout",
        type=float,
        default=300.0,
        help="Maximum seconds to wait for source processing.",
    )

    ask = subparsers.add_parser("ask", help="Ask NotebookLM for an analysis.")
    ask.add_argument("--notebook-id", required=True, help="Notebook ID.")
    ask.add_argument("--prompt", required=True, help="Question or analysis prompt.")
    ask.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Optional source IDs to target.",
    )

    generate = subparsers.add_parser("generate", help="Generate one artifact.")
    add_generation_arguments(generate)

    pipeline = subparsers.add_parser(
        "pipeline",
        help="Create a notebook, add URLs, ask for analysis, and generate artifacts.",
    )
    pipeline.add_argument("--title", required=True, help="Notebook title.")
    pipeline.add_argument("--url", action="append", default=[], help="URL to add.")
    pipeline.add_argument(
        "--urls-file",
        type=Path,
        default=None,
        help="JSON or text file containing URLs.",
    )
    pipeline.add_argument(
        "--analysis-prompt",
        default=DEFAULT_ANALYSIS_PROMPT,
        help="Analysis prompt to send after sources are ready.",
    )
    pipeline.add_argument(
        "--artifact",
        action="append",
        default=[],
        choices=("infographic", "slide-deck", "flashcards"),
        help="Artifact type to generate. Repeat for multiple outputs.",
    )
    pipeline.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for downloaded artifacts.",
    )
    pipeline.add_argument(
        "--source-wait-timeout",
        type=float,
        default=300.0,
        help="Maximum seconds to wait for source processing.",
    )
    add_generation_arguments(
        pipeline,
        include_notebook=False,
        include_output=False,
        include_artifact=False,
    )

    return parser.parse_args()


def add_generation_arguments(
    parser: argparse.ArgumentParser,
    include_notebook: bool = True,
    include_output: bool = True,
    include_artifact: bool = True,
) -> None:
    if include_notebook:
        parser.add_argument("--notebook-id", required=True, help="Notebook ID.")
    if include_artifact:
        parser.add_argument(
            "--artifact",
            required=True,
            choices=("infographic", "slide-deck", "flashcards"),
            help="Artifact type to generate.",
        )
    parser.add_argument(
        "--artifact-instructions",
        default=None,
        help="Optional custom instructions for the artifact.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Optional source IDs to target.",
    )
    if include_output:
        parser.add_argument(
            "--output",
            type=Path,
            default=None,
            help="Optional explicit output path for the downloaded artifact.",
        )
    parser.add_argument(
        "--artifact-wait-timeout",
        type=float,
        default=900.0,
        help="Maximum seconds to wait for artifact completion.",
    )
    parser.add_argument(
        "--infographic-style",
        default="auto",
        choices=sorted(INFOGRAPHIC_STYLE_MAP.keys()),
        help="Infographic style when generating infographics.",
    )
    parser.add_argument(
        "--infographic-orientation",
        default="portrait",
        choices=sorted(INFOGRAPHIC_ORIENTATION_MAP.keys()),
        help="Infographic orientation.",
    )
    parser.add_argument(
        "--infographic-detail",
        default="standard",
        choices=sorted(INFOGRAPHIC_DETAIL_MAP.keys()),
        help="Infographic detail level.",
    )
    parser.add_argument(
        "--slide-deck-format",
        default="detailed",
        choices=sorted(SLIDE_DECK_FORMAT_MAP.keys()),
        help="Slide deck format.",
    )
    parser.add_argument(
        "--slide-deck-length",
        default="default",
        choices=sorted(SLIDE_DECK_LENGTH_MAP.keys()),
        help="Slide deck length.",
    )
    parser.add_argument(
        "--slide-deck-output-format",
        default="pptx",
        choices=("pdf", "pptx"),
        help="Downloaded slide deck file format.",
    )
    parser.add_argument(
        "--flashcards-format",
        default="markdown",
        choices=("json", "markdown", "html"),
        help="Downloaded flashcards file format.",
    )
    parser.add_argument(
        "--flashcards-difficulty",
        default="medium",
        choices=sorted(FLASHCARD_DIFFICULTY_MAP.keys()),
        help="Flashcard difficulty.",
    )
    parser.add_argument(
        "--flashcards-quantity",
        default="standard",
        choices=sorted(FLASHCARD_QUANTITY_MAP.keys()),
        help="Flashcard quantity.",
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "notebooklm-output"


def load_urls(urls: list[str], urls_file: Path | None) -> list[str]:
    collected = list(urls)
    if urls_file is None:
        return dedupe_urls(collected)

    text = urls_file.read_text(encoding="utf-8").strip()
    if not text:
        return dedupe_urls(collected)

    if urls_file.suffix.lower() == ".json":
        data = json.loads(text)
        collected.extend(extract_urls_from_json(data))
        return dedupe_urls(collected)

    collected.extend(line.strip() for line in text.splitlines() if line.strip())
    return dedupe_urls(collected)


def extract_urls_from_json(data: Any) -> list[str]:
    if isinstance(data, dict):
        if isinstance(data.get("videos"), list):
            return [
                item.get("url")
                for item in data["videos"]
                if isinstance(item, dict) and item.get("url")
            ]
        if isinstance(data.get("urls"), list):
            return [item for item in data["urls"] if isinstance(item, str) and item]
    if isinstance(data, list):
        if all(isinstance(item, str) for item in data):
            return [item for item in data if item]
        return [item.get("url") for item in data if isinstance(item, dict) and item.get("url")]
    raise ValueError("Unsupported JSON format for URL import.")


def dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def ensure_auth_hint(exc: Exception) -> None:
    message = str(exc)
    if "storage file not found" in message.lower() or "login" in message.lower():
        raise RuntimeError(
            "NotebookLM authentication is not ready. Open a separate terminal and run '.\\notebooklm.cmd login', then retry."
        ) from exc
    raise RuntimeError(message) from exc


def serialize_notebook(notebook: Any) -> dict[str, Any]:
    return {
        "id": notebook.id,
        "title": notebook.title,
        "created_at": notebook.created_at.isoformat() if notebook.created_at else None,
        "is_owner": notebook.is_owner,
    }


def serialize_source(source: Any) -> dict[str, Any]:
    return {
        "id": source.id,
        "title": source.title,
        "url": source.url,
        "kind": source.kind.value,
        "status": source.status,
        "ready": source.is_ready,
    }


def serialize_reference(reference: Any) -> dict[str, Any]:
    return {
        "source_id": reference.source_id,
        "citation_number": reference.citation_number,
        "cited_text": reference.cited_text,
    }


def serialize_analysis(result: Any) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "conversation_id": result.conversation_id,
        "turn_number": result.turn_number,
        "is_follow_up": result.is_follow_up,
        "references": [serialize_reference(reference) for reference in result.references],
    }


async def create_notebook(title: str) -> dict[str, Any]:
    try:
        async with await NotebookLMClient.from_storage() as client:
            notebook = await client.notebooks.create(title)
    except Exception as exc:
        ensure_auth_hint(exc)
    return {"notebook": serialize_notebook(notebook)}


async def add_urls_to_notebook(
    notebook_id: str,
    urls: list[str],
    wait_timeout: float,
) -> dict[str, Any]:
    created_sources: list[Any] = []
    add_errors: list[dict[str, str]] = []

    try:
        async with await NotebookLMClient.from_storage() as client:
            for url in urls:
                try:
                    created_sources.append(
                        await client.sources.add_url(notebook_id, url, wait=False)
                    )
                except Exception as exc:
                    add_errors.append({"url": url, "error": str(exc)})

            ready_sources: list[Any] = []
            wait_errors: list[dict[str, str]] = []
            for source in created_sources:
                try:
                    ready_sources.append(
                        await client.sources.wait_until_ready(
                            notebook_id,
                            source.id,
                            timeout=wait_timeout,
                        )
                    )
                except Exception as exc:
                    wait_errors.append({"source_id": source.id, "error": str(exc)})
    except Exception as exc:
        ensure_auth_hint(exc)

    return {
        "requested_url_count": len(urls),
        "created_sources": [serialize_source(source) for source in created_sources],
        "ready_sources": [serialize_source(source) for source in ready_sources],
        "add_errors": add_errors,
        "wait_errors": wait_errors,
    }


async def ask_notebook(
    notebook_id: str,
    prompt: str,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    try:
        async with await NotebookLMClient.from_storage() as client:
            result = await client.chat.ask(
                notebook_id,
                prompt,
                source_ids=source_ids or None,
            )
    except Exception as exc:
        ensure_auth_hint(exc)
    return serialize_analysis(result)


def default_output_path(args: argparse.Namespace, notebook_id: str, artifact: str) -> Path:
    output_dir = DEFAULT_OUTPUT_ROOT / notebook_id
    output_dir.mkdir(parents=True, exist_ok=True)
    if artifact == "infographic":
        return output_dir / "infographic.png"
    if artifact == "slide-deck":
        return output_dir / f"slide-deck.{args.slide_deck_output_format}"
    return output_dir / {
        "json": "flashcards.json",
        "markdown": "flashcards.md",
        "html": "flashcards.html",
    }[args.flashcards_format]


async def generate_artifact(
    notebook_id: str,
    artifact: str,
    source_ids: list[str],
    args: argparse.Namespace,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resolved_output = output_path or getattr(args, "output", None) or default_output_path(
        args,
        notebook_id,
        artifact,
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with await NotebookLMClient.from_storage() as client:
            if artifact == "infographic":
                status = await client.artifacts.generate_infographic(
                    notebook_id,
                    source_ids=source_ids or None,
                    instructions=args.artifact_instructions,
                    orientation=INFOGRAPHIC_ORIENTATION_MAP[args.infographic_orientation],
                    detail_level=INFOGRAPHIC_DETAIL_MAP[args.infographic_detail],
                    style=INFOGRAPHIC_STYLE_MAP[args.infographic_style],
                )
                final_status = await client.artifacts.wait_for_completion(
                    notebook_id,
                    status.task_id,
                    timeout=args.artifact_wait_timeout,
                )
                if final_status.status != "completed":
                    raise RuntimeError(
                        f"Infographic generation did not complete successfully: {final_status.status}"
                    )
                downloaded = await client.artifacts.download_infographic(
                    notebook_id,
                    str(resolved_output),
                    artifact_id=final_status.task_id,
                )
            elif artifact == "slide-deck":
                status = await client.artifacts.generate_slide_deck(
                    notebook_id,
                    source_ids=source_ids or None,
                    instructions=args.artifact_instructions,
                    slide_format=SLIDE_DECK_FORMAT_MAP[args.slide_deck_format],
                    slide_length=SLIDE_DECK_LENGTH_MAP[args.slide_deck_length],
                )
                final_status = await client.artifacts.wait_for_completion(
                    notebook_id,
                    status.task_id,
                    timeout=args.artifact_wait_timeout,
                )
                if final_status.status != "completed":
                    raise RuntimeError(
                        f"Slide deck generation did not complete successfully: {final_status.status}"
                    )
                downloaded = await client.artifacts.download_slide_deck(
                    notebook_id,
                    str(resolved_output),
                    artifact_id=final_status.task_id,
                    output_format=args.slide_deck_output_format,
                )
            else:
                status = await client.artifacts.generate_flashcards(
                    notebook_id,
                    source_ids=source_ids or None,
                    instructions=args.artifact_instructions,
                    difficulty=FLASHCARD_DIFFICULTY_MAP[args.flashcards_difficulty],
                    quantity=FLASHCARD_QUANTITY_MAP[args.flashcards_quantity],
                )
                final_status = await client.artifacts.wait_for_completion(
                    notebook_id,
                    status.task_id,
                    timeout=args.artifact_wait_timeout,
                )
                if final_status.status != "completed":
                    raise RuntimeError(
                        f"Flashcard generation did not complete successfully: {final_status.status}"
                    )
                downloaded = await client.artifacts.download_flashcards(
                    notebook_id,
                    str(resolved_output),
                    artifact_id=final_status.task_id,
                    output_format=args.flashcards_format,
                )
    except Exception as exc:
        ensure_auth_hint(exc)

    return {
        "artifact": artifact,
        "task_id": final_status.task_id,
        "status": final_status.status,
        "output_path": downloaded,
    }


def build_pipeline_output_path(
    output_dir: Path,
    artifact: str,
    args: argparse.Namespace,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if artifact == "infographic":
        return output_dir / "infographic.png"
    if artifact == "slide-deck":
        return output_dir / f"slide-deck.{args.slide_deck_output_format}"
    return output_dir / {
        "json": "flashcards.json",
        "markdown": "flashcards.md",
        "html": "flashcards.html",
    }[args.flashcards_format]


async def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    urls = load_urls(args.url, args.urls_file)
    if not urls:
        raise RuntimeError("No URLs were provided for the NotebookLM pipeline.")

    created = await create_notebook(args.title)
    notebook_id = created["notebook"]["id"]
    source_results = await add_urls_to_notebook(
        notebook_id,
        urls,
        args.source_wait_timeout,
    )

    ready_sources = source_results["ready_sources"]
    if not ready_sources:
        raise RuntimeError("No NotebookLM sources were ready after import.")

    analysis = await ask_notebook(
        notebook_id,
        args.analysis_prompt,
        [source["id"] for source in ready_sources],
    )

    output_dir = args.output_dir / slugify(args.title)
    artifacts: list[dict[str, Any]] = []
    for artifact in args.artifact:
        artifact_args = argparse.Namespace(**vars(args))
        artifact_args.output = None
        artifacts.append(
            await generate_artifact(
                notebook_id,
                artifact,
                [source["id"] for source in ready_sources],
                artifact_args,
                output_path=build_pipeline_output_path(output_dir, artifact, artifact_args),
            )
        )

    return {
        "notebook": created["notebook"],
        "sources": source_results,
        "analysis": analysis,
        "artifacts": artifacts,
    }


async def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "create":
        return await create_notebook(args.title)

    if args.command == "add-urls":
        urls = load_urls(args.url, args.urls_file)
        if not urls:
            raise RuntimeError("No URLs were provided.")
        return await add_urls_to_notebook(
            args.notebook_id,
            urls,
            args.source_wait_timeout,
        )

    if args.command == "ask":
        return await ask_notebook(args.notebook_id, args.prompt, args.source_id)

    if args.command == "generate":
        return await generate_artifact(
            args.notebook_id,
            args.artifact,
            args.source_id,
            args,
        )

    if args.command == "pipeline":
        return await run_pipeline(args)

    raise RuntimeError(f"Unsupported command: {args.command}")


async def main() -> int:
    args = parse_args()
    result = await dispatch(args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(1)
