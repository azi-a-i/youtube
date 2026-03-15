#!/usr/bin/env python
"""Search YouTube with yt-dlp and emit structured metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search YouTube and return structured metadata for each video.",
    )
    parser.add_argument("--query", required=True, help="Search query or topic.")
    parser.add_argument(
        "--count",
        type=int,
        default=25,
        help="Number of videos to return after ranking.",
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        default=None,
        help="Number of candidate videos to fetch before ranking.",
    )
    parser.add_argument(
        "--search-mode",
        choices=("latest", "relevance"),
        default="latest",
        help="Use recent uploads or YouTube's default relevance search.",
    )
    parser.add_argument(
        "--sort",
        choices=("latest", "views"),
        default="views",
        help="Sort the candidate pool by upload date or by view count.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON payload.",
    )
    return parser.parse_args()


def format_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def normalize_video(entry: dict[str, Any]) -> dict[str, Any]:
    uploader = entry.get("uploader") or entry.get("channel")
    duration_seconds = entry.get("duration")
    return {
        "rank": 0,
        "video_id": entry.get("id"),
        "title": entry.get("title"),
        "author": uploader,
        "channel": entry.get("channel") or uploader,
        "views": entry.get("view_count"),
        "duration_seconds": duration_seconds,
        "duration": format_duration(duration_seconds),
        "upload_date": entry.get("upload_date"),
        "url": entry.get("webpage_url"),
    }


def search_videos(query: str, search_mode: str, pool_size: int) -> list[dict[str, Any]]:
    _ = search_mode
    search_term = f"ytsearch{pool_size}:{query}"
    options = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "extract_flat": False,
    }
    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(search_term, download=False)
    entries = result.get("entries", []) if isinstance(result, dict) else []
    return [normalize_video(entry) for entry in entries if isinstance(entry, dict)]


def sort_videos(videos: list[dict[str, Any]], sort_mode: str) -> list[dict[str, Any]]:
    if sort_mode == "latest":
        videos.sort(
            key=lambda item: (
                item.get("upload_date") is not None,
                item.get("upload_date") or "",
                item.get("views") or -1,
            ),
            reverse=True,
        )
        return videos

    videos.sort(
        key=lambda item: (
            item.get("views") is not None,
            item.get("views") or -1,
            item.get("upload_date") or "",
        ),
        reverse=True,
    )
    return videos


def main() -> int:
    args = parse_args()
    pool_size = args.pool_size or max(args.count, args.count * 3)
    videos = sort_videos(
        search_videos(args.query, args.search_mode, pool_size),
        args.sort,
    )[: args.count]

    for index, video in enumerate(videos, start=1):
        video["rank"] = index

    payload = {
        "query": args.query,
        "search_mode": args.search_mode,
        "sort": args.sort,
        "requested_count": args.count,
        "candidate_pool": pool_size,
        "returned_count": len(videos),
        "videos": videos,
    }

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
