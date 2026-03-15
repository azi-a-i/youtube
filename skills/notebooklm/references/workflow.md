# Workflow Reference

## Authentication

Open a separate terminal in this workspace and run:

```powershell
.\notebooklm.cmd login
```

The wrapper keeps NotebookLM state in `.\.notebooklm` and uses the project virtual environment.

## Accepted URL inputs

`--urls-file` accepts:
- the JSON output from `yt-research`
- a JSON array of URLs
- a JSON object with a `urls` array
- a plain text file with one URL per line

## Core commands

Create a notebook:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' create --title "Research Title"
```

Add URLs:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' add-urls --notebook-id "<id>" --urls-file '.\outputs\yt\topic.json'
```

Ask for analysis:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' ask --notebook-id "<id>" --prompt "What are the top findings?"
```

Generate a single infographic:

```powershell
& '.\.venv\Scripts\python.exe' '.\skills\notebooklm\scripts\notebooklm_pipeline.py' `
  generate `
  --notebook-id "<id>" `
  --artifact infographic `
  --artifact-instructions "Handwritten chalkboard style." `
  --infographic-style sketch-note `
  --output '.\outputs\notebooklm\topic\infographic.png'
```

## Artifact options

Infographic styles:
- `auto`
- `sketch-note`
- `professional`
- `bento-grid`
- `editorial`
- `instructional`
- `bricks`
- `clay`
- `anime`
- `kawaii`
- `scientific`

Infographic orientation:
- `landscape`
- `portrait`
- `square`

Infographic detail:
- `concise`
- `standard`
- `detailed`

Slide deck formats:
- `detailed`
- `presenter`

Slide deck lengths:
- `default`
- `short`

Flashcard difficulty:
- `easy`
- `medium`
- `hard`

Flashcard quantity:
- `fewer`
- `standard`
