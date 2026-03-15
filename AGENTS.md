## Skills

### Available skills

- `yt-research`: Search YouTube with the workspace-local `yt-dlp` setup and return structured metadata, including titles, views, author/channel, duration, upload date, and URLs. Use when the user wants YouTube topic research, recent or high-signal video discovery, or a URL set to pass into NotebookLM. If the user asks for YouTube research without a topic, ask for the topic first. (file: C:/Users/Azibaola Arikekpar/Documents/youtube/skills/yt-research/SKILL.md)
- `notebooklm`: Use the workspace-local `notebooklm-py` integration to create notebooks, add YouTube or web URLs as sources, ask NotebookLM for analysis, and generate/download artifacts such as infographics, slide decks, and flashcards. Use after `yt-research` when the workflow continues into NotebookLM. If NotebookLM authentication is not set up yet, ask the user to open a separate terminal and run `.\notebooklm.cmd login` before continuing. (file: C:/Users/Azibaola Arikekpar/Documents/youtube/skills/notebooklm/SKILL.md)

### How to use skills

- Use `yt-research` first for YouTube discovery and metadata collection.
- Use `notebooklm` second when the URLs need to be imported into NotebookLM for synthesis or artifact generation.
- Keep the `yt-research` JSON output when handing results to `notebooklm`; the NotebookLM script can read that file directly.
