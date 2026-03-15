---
name: yt-research
description: Search YouTube with the workspace-local yt-dlp install and return structured video metadata including titles, views, author/channel, duration, upload date, and URLs. Use when Codex needs topic research from YouTube, a list of recent or high-signal videos on a subject, or a URL set to pass into another tool such as NotebookLM. If the user requests YouTube research without naming a topic or query, ask for the topic before proceeding.
---

# YT Research

## Overview

Use the Python script in `scripts/search_youtube.py` to gather consistent metadata from YouTube search results. Prefer this skill when the user wants recent videos on a topic, a structured export, or a ranked set of URLs for a downstream analysis workflow.

## Quick Start

Run the script with the workspace virtual environment:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\yt-research\scripts\search_youtube.py' `
  --query "artificial intelligence agents" `
  --count 25 `
  --search-mode latest `
  --sort views `
  --pool-size 75 `
  --output '.\outputs\yt\agents.json'
```

## Workflow

1. If the user did not provide a topic, ask for it before running the script.
2. Choose a search strategy:
   - For "latest trending on [topic]": use `--search-mode latest --sort views` and set `--pool-size` to at least `count * 3`.
   - For newest uploads only: use `--search-mode latest --sort latest`.
   - For the default YouTube relevance ranking: use `--search-mode relevance`.
3. Save the JSON output when another tool needs the URLs. The NotebookLM skill can read either the JSON file produced here or a plain text file of URLs.
4. Tell the user that topic-scoped "trending" is an approximation: the script searches recent videos for the topic and ranks them by view count when `--sort views` is used.

## Output Shape

The script prints JSON with:

- `query`
- `search_mode`
- `sort`
- `returned_count`
- `videos`

Each video object includes:

- `rank`
- `title`
- `author`
- `channel`
- `views`
- `duration`
- `duration_seconds`
- `upload_date`
- `url`
- `video_id`

## Decision Rules

- Use this skill before `notebooklm` when the user wants YouTube videos sent into NotebookLM.
- If the user wants only the URLs, still keep the structured output file because it preserves view counts and titles for later reporting.
- If YouTube returns sparse metadata for some entries, keep the entry and surface `null` values rather than inventing data.
- Read [query-patterns.md](./references/query-patterns.md) when you need examples of common search configurations.

## Resources

- `scripts/search_youtube.py`: Run the actual YouTube query and emit structured JSON.
- `references/query-patterns.md`: Reuse the recommended search patterns for "latest", "latest trending", and NotebookLM handoff workflows.
