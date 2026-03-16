interface BootstrapPayload {
  page?: string;
}

interface VideoResult {
  title?: string | null;
  url?: string | null;
}

interface YtResearchPayload {
  query?: string;
  videos?: VideoResult[];
}

interface NotebookRunResult {
  answer?: string;
  raw?: Record<string, unknown>;
  title?: string;
}

interface JobPayload {
  error?: string | null;
  result?: NotebookRunResult | null;
  stage?: string;
  status?: string;
}

type NotebookRunResponse =
  | { job_id: string; mode: "background" }
  | { mode: "direct"; result: NotebookRunResult };

type MessageKind = "info" | "success" | "warning" | "error";

const bootstrapWindow = window as Window & {
  LLMNOTETUBE_BOOTSTRAP?: BootstrapPayload;
};

const bootstrap = bootstrapWindow.LLMNOTETUBE_BOOTSTRAP ?? {};

const state = {
  lastSearch: null as YtResearchPayload | null,
  notebookConnected: false,
  pollTimer: null as number | null,
  progressTimer: null as number | null,
  progressValue: 18,
  result: null as NotebookRunResult | null,
  selectedUrls: new Set<string>(),
};

function byId<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing expected element: ${id}`);
  }
  return element as T;
}

function maybeById<T extends HTMLElement>(id: string): T | null {
  const element = document.getElementById(id);
  return element instanceof HTMLElement ? (element as T) : null;
}

function setMessage(element: HTMLElement, message: string, type: MessageKind): void {
  element.textContent = message;
  element.className = `message message-${type}`;
  element.hidden = false;
}

function clearMessage(element: HTMLElement): void {
  element.textContent = "";
  element.className = "message";
  element.hidden = true;
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatParagraphs(text: string | undefined): string {
  if (!text) {
    return "<p>No NotebookLM answer was returned.</p>";
  }
  return text
    .split(/\n{2,}/)
    .filter(Boolean)
    .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
    .join("");
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const text = await response.text();

  let payload: (T & { error?: string }) | null = null;
  try {
    payload = JSON.parse(text) as T & { error?: string };
  } catch {
    throw new Error(text.slice(0, 160).trim() || "Unexpected response from the server.");
  }

  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

async function fetchBlob(url: string, options?: RequestInit): Promise<Blob> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    let payload: { error?: string } | null = null;
    try {
      payload = JSON.parse(text) as { error?: string };
    } catch {
      payload = null;
    }
    throw new Error(payload?.error || text || "Download failed.");
  }
  return response.blob();
}

function renderVideoResults(payload: YtResearchPayload): void {
  const resultsShell = maybeById<HTMLElement>("yt-results");
  const meta = maybeById<HTMLElement>("yt-meta");
  const list = maybeById<HTMLElement>("video-list");
  if (!resultsShell || !meta || !list) {
    return;
  }

  const videos = payload.videos ?? [];
  state.lastSearch = payload;
  state.selectedUrls = new Set(videos.map((item) => item.url ?? "").filter(Boolean));

  meta.textContent = `${videos.length} results for "${payload.query ?? ""}"`;
  list.innerHTML = videos
    .map((video) => {
      const url = video.url ?? "";
      return `
        <label class="video-row">
          <input type="checkbox" class="video-toggle" data-url="${escapeHtml(url)}" checked />
          <div class="video-copy">
            <strong>${escapeHtml(video.title || "Untitled video")}</strong>
            <a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>
          </div>
        </label>
      `;
    })
    .join("");
  resultsShell.hidden = false;
}

function stopPolling(): void {
  if (state.pollTimer != null) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function stopProgress(): void {
  if (state.progressTimer != null) {
    window.clearInterval(state.progressTimer);
    state.progressTimer = null;
  }
}

function startProgress(): void {
  const bar = maybeById<HTMLElement>("job-progress-bar");
  if (!bar) {
    return;
  }

  stopProgress();
  state.progressValue = 18;
  bar.style.width = `${state.progressValue}%`;
  state.progressTimer = window.setInterval(() => {
    state.progressValue = Math.min(90, state.progressValue + 7);
    bar.style.width = `${state.progressValue}%`;
    if (state.progressValue >= 90) {
      state.progressValue = 48;
    }
  }, 900);
}

function renderNotebookResult(result: NotebookRunResult): void {
  const panel = maybeById<HTMLElement>("result-panel");
  const title = maybeById<HTMLElement>("result-title");
  const answer = maybeById<HTMLElement>("analysis-answer");
  const rawJson = maybeById<HTMLElement>("raw-json");
  if (!panel || !title || !answer || !rawJson) {
    return;
  }

  state.result = result;
  title.textContent = result.title || "Generated response";
  answer.innerHTML = formatParagraphs(result.answer);
  rawJson.textContent = JSON.stringify(result.raw ?? {}, null, 2);
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function pollJob(jobId: string, submitButton: HTMLButtonElement): void {
  const status = byId<HTMLElement>("nl-status");
  const progress = byId<HTMLElement>("nl-job-progress");
  const stage = byId<HTMLElement>("job-stage");
  const helper = byId<HTMLElement>("job-helper");
  const bar = byId<HTMLElement>("job-progress-bar");

  stopPolling();
  startProgress();

  state.pollTimer = window.setInterval(async () => {
    try {
      const payload = await fetchJson<JobPayload>(`/api/jobs/${jobId}`);
      stage.textContent = payload.stage || "Working";
      helper.textContent = "NotebookLM is processing the selected sources.";

      if (payload.status === "done") {
        stopPolling();
        stopProgress();
        bar.style.width = "100%";
        progress.hidden = true;
        submitButton.disabled = false;
        setMessage(status, "NotebookLM finished successfully.", "success");
        renderNotebookResult(payload.result ?? {});
      } else if (payload.status === "error") {
        stopPolling();
        stopProgress();
        progress.hidden = true;
        submitButton.disabled = false;
        setMessage(status, payload.error || "NotebookLM failed.", "error");
      }
    } catch (error) {
      stopPolling();
      stopProgress();
      progress.hidden = true;
      submitButton.disabled = false;
      setMessage(status, error instanceof Error ? error.message : "Polling failed.", "error");
    }
  }, 2500);
}

function addSelectedUrlsToSources(): void {
  const sources = maybeById<HTMLTextAreaElement>("nl-sources");
  if (!sources) {
    return;
  }

  const urls = Array.from(state.selectedUrls);
  if (!urls.length) {
    return;
  }

  const existing = sources.value.trim();
  const existingLines = existing ? existing.split(/\n/).map((item) => item.trim()) : [];
  const merged = Array.from(new Set([...existingLines.filter(Boolean), ...urls]));
  sources.value = `${merged.join("\n")}\n`;
}

function attachWorkspaceHandlers(): void {
  if (bootstrap.page !== "workspace") {
    return;
  }

  const ytForm = byId<HTMLFormElement>("yt-form");
  const nlForm = byId<HTMLFormElement>("nl-form");
  const ytStatus = byId<HTMLElement>("yt-status");
  const nlStatus = byId<HTMLElement>("nl-status");
  const connectStatus = byId<HTMLElement>("notebooklm-connect-status");
  const progress = byId<HTMLElement>("nl-job-progress");
  const stage = byId<HTMLElement>("job-stage");
  const helper = byId<HTMLElement>("job-helper");
  const resultPanel = byId<HTMLElement>("result-panel");
  const videoList = byId<HTMLElement>("video-list");

  maybeById<HTMLButtonElement>("connect-notebooklm")?.addEventListener("click", async () => {
    connectStatus.textContent = "Connecting...";
    connectStatus.className = "message-inline";
    try {
      const payload = await fetchJson<{ connected: boolean; message?: string }>("/api/notebooklm/connect", {
        method: "POST",
      });
      state.notebookConnected = payload.connected;
      connectStatus.textContent = payload.message || "NotebookLM backend is ready.";
      connectStatus.className = "message-inline is-success";
    } catch (error) {
      state.notebookConnected = false;
      connectStatus.textContent = error instanceof Error ? error.message : "Unable to connect NotebookLM.";
      connectStatus.className = "message-inline is-error";
    }
  });

  maybeById<HTMLButtonElement>("clear-results")?.addEventListener("click", () => {
    state.lastSearch = null;
    state.selectedUrls.clear();
    byId<HTMLElement>("yt-results").hidden = true;
    videoList.innerHTML = "";
    clearMessage(ytStatus);
  });

  maybeById<HTMLButtonElement>("add-selected-sources")?.addEventListener("click", addSelectedUrlsToSources);

  videoList.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || !target.classList.contains("video-toggle")) {
      return;
    }

    const url = target.dataset.url ?? "";
    if (!url) {
      return;
    }

    if (target.checked) {
      state.selectedUrls.add(url);
    } else {
      state.selectedUrls.delete(url);
    }
  });

  ytForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = byId<HTMLButtonElement>("yt-submit");
    submitButton.disabled = true;
    clearMessage(ytStatus);
    setMessage(ytStatus, "Searching YouTube...", "info");

    try {
      const payload = await fetchJson<YtResearchPayload>("/api/yt-research", {
        body: JSON.stringify({
          count: Number.parseInt(byId<HTMLInputElement>("count").value, 10) || 12,
          query: byId<HTMLInputElement>("query").value.trim(),
        }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      renderVideoResults(payload);
      setMessage(ytStatus, `Loaded ${payload.videos?.length ?? 0} YouTube results.`, "success");
    } catch (error) {
      setMessage(ytStatus, error instanceof Error ? error.message : "Search failed.", "error");
    } finally {
      submitButton.disabled = false;
    }
  });

  nlForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = byId<HTMLButtonElement>("nl-submit");
    const title = byId<HTMLInputElement>("nl-title").value.trim();
    const sourcesText = byId<HTMLTextAreaElement>("nl-sources").value.trim();
    const prompt = byId<HTMLTextAreaElement>("nl-prompt").value.trim();

    if (!state.notebookConnected) {
      setMessage(nlStatus, "Click Connect NotebookLM before running the workspace.", "warning");
      return;
    }

    if (!sourcesText) {
      setMessage(nlStatus, "Paste at least one YouTube URL.", "warning");
      return;
    }

    clearMessage(nlStatus);
    resultPanel.hidden = true;
    progress.hidden = false;
    stage.textContent = "Queued";
    helper.textContent = "Submitting the request to NotebookLM.";
    submitButton.disabled = true;
    setMessage(nlStatus, "Running NotebookLM...", "info");

    try {
      const payload = await fetchJson<NotebookRunResponse>("/api/notebooklm/run", {
        body: JSON.stringify({
          prompt,
          sources_text: sourcesText,
          title,
        }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });

      if (payload.mode === "direct") {
        progress.hidden = true;
        submitButton.disabled = false;
        setMessage(nlStatus, "NotebookLM finished successfully.", "success");
        renderNotebookResult(payload.result);
        return;
      }

      pollJob(payload.job_id, submitButton);
    } catch (error) {
      progress.hidden = true;
      submitButton.disabled = false;
      setMessage(nlStatus, error instanceof Error ? error.message : "NotebookLM failed.", "error");
    }
  });

  maybeById<HTMLButtonElement>("download-output")?.addEventListener("click", async () => {
    if (!state.result?.answer) {
      return;
    }

    const format = byId<HTMLSelectElement>("download-format").value;
    const safeTitle = (state.result.title || "llmnotetube-output")
      .replace(/[^a-zA-Z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "llmnotetube-output";
    try {
      const blob = await fetchBlob("/api/download-analysis", {
        body: JSON.stringify({
          content: state.result.answer,
          format,
          title: state.result.title || "LLMNoteTube Output",
        }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${safeTitle}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(nlStatus, error instanceof Error ? error.message : "Download failed.", "error");
    }
  });
}

attachWorkspaceHandlers();
