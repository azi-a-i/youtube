# Query Patterns

Use these patterns with `scripts/search_youtube.py`.

## Latest trending approximation

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\yt-research\scripts\search_youtube.py' `
  --query "TOPIC" `
  --count 25 `
  --search-mode latest `
  --sort views `
  --pool-size 75 `
  --output '.\outputs\yt\topic.json'
```

This is the best available approximation for "latest trending videos on TOPIC":
- search recent uploads
- collect a larger candidate pool
- rank the recent pool by views

## Newest uploads

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\yt-research\scripts\search_youtube.py' `
  --query "TOPIC" `
  --count 25 `
  --search-mode latest `
  --sort latest
```

## Relevance-first discovery

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\yt-research\scripts\search_youtube.py' `
  --query "TOPIC" `
  --count 25 `
  --search-mode relevance `
  --sort views
```

## NotebookLM handoff

Point the NotebookLM skill at the JSON file produced here:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' `
  pipeline `
  --title "YouTube Research: TOPIC" `
  --urls-file '.\outputs\yt\topic.json' `
  --analysis-prompt "Summarize the top findings." `
  --artifact infographic
```
