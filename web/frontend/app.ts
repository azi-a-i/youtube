interface SystemStatus {
  auth_env_var?: string;
  auth_ready: boolean;
  auth_source?: string;
  deploy_auth_hint?: string;
  login_command?: string;
  outputs_root?: string;
  port?: string;
  python_executable?: string;
  python_ready: boolean;
  run_command?: string;
  server_mode?: string;
}

interface VideoResult {
  author?: string | null;
  channel?: string | null;
  duration?: string | null;
  rank?: number;
  title?: string | null;
  upload_date?: string | null;
  url?: string | null;
  views?: number | null;
}

interface YtResearchPayload {
  candidate_pool?: number;
  query?: string;
  returned_count?: number;
  search_mode?: string;
  sort?: string;
  videos?: VideoResult[];
  warnings?: string[];
}

interface AnalysisReference {
  citation_number?: number;
  source_id?: string;
}

interface NotebookAnalysis {
  answer?: string;
  references?: AnalysisReference[];
}

interface NotebookSourceResult {
  ready_sources?: Array<{ id?: string }>;
}

interface ArtifactLink {
  kind?: string | null;
  name?: string | null;
  url?: string | null;
}

interface NotebookPipelineResult {
  analysis?: NotebookAnalysis;
  artifacts?: ArtifactLink[];
  notebook?: {
    id?: string;
    title?: string;
  };
  sources?: NotebookSourceResult;
}

interface JobPayload {
  artifacts?: ArtifactLink[];
  error?: string | null;
  result?: NotebookPipelineResult | null;
  stage?: string;
  status?: string;
}

type MessageKind = "info" | "success" | "warning" | "error";

const state = {
  system: null as SystemStatus | null,
  lastYtPayload: null as YtResearchPayload | null,
  pulseTimer: null as number | null,
  pulseValue: 10,
  pollTimer: null as number | null,
  selectedVideoUrls: new Set<string>(),
};

function byId<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing expected element: ${id}`);
  }
  return element as T;
}

const ytForm = byId<HTMLFormElement>("yt-form");
const ytStatus = byId<HTMLElement>("yt-status");
const ytWarning = byId<HTMLElement>("yt-warning");
const ytResults = byId<HTMLElement>("yt-results");
const ytMeta = byId<HTMLElement>("yt-meta");
const videoGrid = byId<HTMLElement>("video-grid");
const selectionCount = byId<HTMLElement>("selection-count");

const nlForm = byId<HTMLFormElement>("nl-form");
const nlStatus = byId<HTMLElement>("nl-status");
const nlUrls = byId<HTMLTextAreaElement>("nl-urls");
const nlTitle = byId<HTMLInputElement>("nl-title");
const nlAnalysis = byId<HTMLTextAreaElement>("nl-analysis");
const nlProgress = byId<HTMLElement>("nl-job-progress");
const jobStage = byId<HTMLElement>("job-stage");
const jobHelper = byId<HTMLElement>("job-helper");
const jobProgressBar = byId<HTMLElement>("job-progress-bar");

const resultPanel = byId<HTMLElement>("result-panel");
const resultSummary = byId<HTMLElement>("result-summary");
const analysisAnswer = byId<HTMLElement>("analysis-answer");
const citationCount = byId<HTMLElement>("citation-count");
const artifactDownloads = byId<HTMLElement>("nl-artifacts");
const rawJson = byId<HTMLElement>("raw-json");

const systemModePill = byId<HTMLElement>("system-mode-pill");
const systemDot = byId<HTMLElement>("system-dot");
const authState = byId<HTMLElement>("auth-state");
const authSource = byId<HTMLElement>("auth-source");
const pythonState = byId<HTMLElement>("python-state");
const pythonPath = byId<HTMLElement>("python-path");
const serverMode = byId<HTMLElement>("server-mode");
const outputRoot = byId<HTMLElement>("output-root");
const loginCommand = byId<HTMLElement>("login-command");
const deployHint = byId<HTMLElement>("deploy-hint");

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

function formatViews(value: number | null | undefined): string {
  if (value == null) {
    return "Unknown";
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return String(value);
}

function formatParagraphs(text: string | null | undefined): string {
  if (!text) {
    return "<p>No NotebookLM answer was returned.</p>";
  }
  return text
    .split(/\n{2,}/)
    .filter(Boolean)
    .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
    .join("");
}

function getSelectedVideos(): VideoResult[] {
  const videos = state.lastYtPayload?.videos ?? [];
  return videos.filter((video) => {
    const url = video.url ?? "";
    return state.selectedVideoUrls.has(url);
  });
}

function updateSelectionRibbon(): void {
  selectionCount.textContent = `${getSelectedVideos().length} selected`;
}

function renderSystemStatus(payload: SystemStatus): void {
  state.system = payload;

  const authReady = Boolean(payload.auth_ready);
  const pythonReady = Boolean(payload.python_ready);
  const resolvedMode = payload.server_mode === "production" ? "Production mode" : "Local mode";
  const resolvedAuthSource =
    payload.auth_source === "env"
      ? "Authenticated from environment secret"
      : payload.auth_source === "storage-file"
        ? "Authenticated from local storage file"
        : payload.auth_source === "env-invalid"
          ? "Inline auth is present but invalid"
          : "Login still required";

  authState.textContent = authReady ? "Ready" : "Needs login";
  authSource.textContent = resolvedAuthSource;
  pythonState.textContent = pythonReady ? "Environment found" : "Python missing";
  pythonPath.textContent = payload.python_executable || "Unavailable";
  serverMode.textContent = resolvedMode;
  outputRoot.textContent = payload.outputs_root || "Unavailable";
  loginCommand.textContent = payload.login_command || ".\\notebooklm.cmd login";
  deployHint.textContent = payload.deploy_auth_hint || "Run NotebookLM login before the first pipeline.";
  systemModePill.textContent = `${resolvedMode} · ${authReady ? "auth ready" : "auth pending"}`;

  systemDot.classList.toggle("is-ready", authReady && pythonReady);
  systemDot.classList.toggle("is-warning", !authReady && pythonReady);
  systemDot.classList.toggle("is-error", !pythonReady);
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = (await response.json()) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

async function loadSystemStatus(): Promise<void> {
  try {
    const payload = await fetchJson<SystemStatus>("/api/system/status");
    renderSystemStatus(payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Status endpoint failed.";
    authState.textContent = "Unavailable";
    authSource.textContent = message;
    pythonState.textContent = "Unavailable";
    pythonPath.textContent = "Unavailable";
    serverMode.textContent = "Unavailable";
    outputRoot.textContent = "Unavailable";
    deployHint.textContent = message;
    systemModePill.textContent = "Status unavailable";
    systemDot.classList.add("is-error");
  }
}

function renderYtResults(payload: YtResearchPayload, resetSelection: boolean): void {
  const videos = payload.videos ?? [];
  state.lastYtPayload = payload;

  if (resetSelection) {
    state.selectedVideoUrls = new Set(
      videos
        .map((video) => video.url ?? "")
        .filter(Boolean),
    );
  }

  ytMeta.textContent = `${payload.returned_count ?? videos.length} videos for "${payload.query ?? "your topic"}"`;
  videoGrid.innerHTML = videos
    .map((video) => {
      const url = video.url ?? "";
      const checked = state.selectedVideoUrls.has(url) ? "checked" : "";
      return `
        <article class="video-card" data-url="${escapeHtml(url)}">
          <label class="video-check">
            <input type="checkbox" class="video-toggle" data-url="${escapeHtml(url)}" ${checked} />
            <span>Use in pipeline</span>
          </label>
          <div class="video-card-body">
            <p class="video-rank">#${video.rank ?? "?"}</p>
            <h4>${escapeHtml(video.title || "Untitled video")}</h4>
            <p class="video-channel">${escapeHtml(video.channel || video.author || "Unknown channel")}</p>
          </div>
          <div class="video-metrics">
            <span>${formatViews(video.views)} views</span>
            <span>${escapeHtml(video.duration || "Unknown duration")}</span>
            <span>${escapeHtml(video.upload_date || "Unknown date")}</span>
          </div>
          <a class="video-link" href="${escapeHtml(url || "#")}" target="_blank" rel="noopener">Open video</a>
        </article>
      `;
    })
    .join("");

  updateSelectionRibbon();
  ytResults.hidden = false;

  if (!nlTitle.value.trim() && payload.query) {
    nlTitle.value = `YouTube Research: ${payload.query}`;
  }
}

function parseNotebookPayload(rawValue: string): { urls?: string[] } | Record<string, unknown> {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    throw new Error("Paste URLs or yt-research JSON first.");
  }

  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    const parsed = JSON.parse(trimmed) as unknown;
    if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
      return { urls: parsed };
    }
    return parsed as Record<string, unknown>;
  }

  const urls = trimmed
    .split(/\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  return { urls };
}

function fillNotebookTextareaFromSelection(): void {
  const selectedVideos = getSelectedVideos();
  if (!selectedVideos.length) {
    setMessage(nlStatus, "Select at least one video first.", "warning");
    return;
  }

  const payload: YtResearchPayload = {
    query: state.lastYtPayload?.query,
    returned_count: selectedVideos.length,
    search_mode: state.lastYtPayload?.search_mode,
    sort: state.lastYtPayload?.sort,
    videos: selectedVideos,
  };

  nlUrls.value = JSON.stringify(payload, null, 2);
  byId<HTMLElement>("pipeline-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummaryCards(result: NotebookPipelineResult): void {
  const notebook = result.notebook ?? {};
  const readySources = result.sources?.ready_sources ?? [];
  const artifactCount = result.artifacts?.length ?? 0;

  resultSummary.innerHTML = `
    <div class="summary-card">
      <span class="card-label">Notebook</span>
      <strong>${escapeHtml(notebook.title || "Untitled notebook")}</strong>
      <span>${escapeHtml(notebook.id || "No ID")}</span>
    </div>
    <div class="summary-card">
      <span class="card-label">Ready sources</span>
      <strong>${readySources.length}</strong>
      <span>Imported into NotebookLM</span>
    </div>
    <div class="summary-card">
      <span class="card-label">Artifacts</span>
      <strong>${artifactCount}</strong>
      <span>Generated files</span>
    </div>
  `;
}

function renderArtifacts(job: JobPayload): void {
  const items = job.artifacts ?? [];
  artifactDownloads.innerHTML = "";

  if (!items.length) {
    artifactDownloads.innerHTML = "<p class='message message-warning'>No downloadable artifacts were returned.</p>";
    return;
  }

  items.forEach((item) => {
    const link = document.createElement("a");
    link.className = "download-card";
    link.href = item.url || "#";
    link.target = "_blank";
    link.rel = "noopener";
    if (item.url) {
      link.setAttribute("download", "");
    } else {
      link.classList.add("is-disabled");
    }
    link.innerHTML = `
      <span class="card-label">${escapeHtml(item.kind || "artifact")}</span>
      <strong>${escapeHtml(item.name || "Download")}</strong>
    `;
    artifactDownloads.appendChild(link);
  });
}

function showNotebookResult(job: JobPayload): void {
  const result = job.result ?? {};
  const analysis = result.analysis ?? {};
  renderSummaryCards(result);
  citationCount.textContent = `${analysis.references?.length ?? 0} references`;
  analysisAnswer.innerHTML = formatParagraphs(analysis.answer);
  renderArtifacts(job);
  rawJson.textContent = JSON.stringify(result, null, 2);
  resultPanel.hidden = false;
  resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function stopProgressAnimation(): void {
  if (state.pulseTimer != null) {
    window.clearInterval(state.pulseTimer);
    state.pulseTimer = null;
  }
}

function startProgressAnimation(): void {
  stopProgressAnimation();
  state.pulseValue = 18;
  jobProgressBar.style.width = `${state.pulseValue}%`;
  state.pulseTimer = window.setInterval(() => {
    state.pulseValue = Math.min(88, state.pulseValue + 6);
    jobProgressBar.style.width = `${state.pulseValue}%`;
    if (state.pulseValue >= 88) {
      state.pulseValue = 46;
    }
  }, 1000);
}

function stopPolling(): void {
  if (state.pollTimer != null) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function pollJob(jobId: string, submitButton: HTMLButtonElement): void {
  stopPolling();
  startProgressAnimation();

  state.pollTimer = window.setInterval(async () => {
    try {
      const payload = await fetchJson<JobPayload>(`/api/jobs/${jobId}`);
      jobStage.textContent = payload.stage || "Working";
      jobHelper.textContent =
        payload.status === "running"
          ? "NotebookLM can take a few minutes for analysis and artifact generation."
          : "Job state updated.";

      if (payload.status === "done") {
        stopPolling();
        stopProgressAnimation();
        jobProgressBar.style.width = "100%";
        submitButton.disabled = false;
        nlProgress.hidden = true;
        setMessage(nlStatus, "NotebookLM pipeline finished successfully.", "success");
        showNotebookResult(payload);
      } else if (payload.status === "error") {
        stopPolling();
        stopProgressAnimation();
        submitButton.disabled = false;
        nlProgress.hidden = true;
        setMessage(nlStatus, payload.error || "Pipeline failed.", "error");
      }
    } catch (error) {
      stopPolling();
      stopProgressAnimation();
      submitButton.disabled = false;
      nlProgress.hidden = true;
      const message = error instanceof Error ? error.message : "Polling failed.";
      setMessage(nlStatus, message, "error");
    }
  }, 2500);
}

function attachEventHandlers(): void {
  const scrollSearch = byId<HTMLButtonElement>("scroll-to-search");
  const scrollPipeline = byId<HTMLButtonElement>("scroll-to-pipeline");
  const scrollWorkspace = byId<HTMLButtonElement>("scroll-to-workspace");

  scrollSearch.addEventListener("click", () => {
    byId<HTMLElement>("search-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  scrollPipeline.addEventListener("click", () => {
    byId<HTMLElement>("pipeline-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  scrollWorkspace.addEventListener("click", () => {
    byId<HTMLElement>("workspace").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  byId<HTMLButtonElement>("clear-results").addEventListener("click", () => {
    state.lastYtPayload = null;
    state.selectedVideoUrls.clear();
    ytResults.hidden = true;
    videoGrid.innerHTML = "";
    updateSelectionRibbon();
    clearMessage(ytStatus);
    clearMessage(ytWarning);
  });

  byId<HTMLButtonElement>("select-all-videos").addEventListener("click", () => {
    (state.lastYtPayload?.videos ?? []).forEach((video) => {
      if (video.url) {
        state.selectedVideoUrls.add(video.url);
      }
    });
    renderYtResults(state.lastYtPayload ?? { videos: [] }, false);
  });

  byId<HTMLButtonElement>("clear-selection").addEventListener("click", () => {
    state.selectedVideoUrls.clear();
    renderYtResults(state.lastYtPayload ?? { videos: [] }, false);
  });

  byId<HTMLButtonElement>("copy-selected-urls").addEventListener("click", async () => {
    const urls = getSelectedVideos()
      .map((video) => video.url ?? "")
      .filter(Boolean);

    if (!urls.length) {
      setMessage(ytStatus, "No selected URLs to copy yet.", "warning");
      return;
    }

    try {
      await navigator.clipboard.writeText(urls.join("\n"));
      setMessage(ytStatus, "Selected URLs copied to your clipboard.", "success");
    } catch {
      setMessage(ytStatus, "Clipboard access failed. Copy from the NotebookLM field instead.", "warning");
    }
  });

  byId<HTMLButtonElement>("use-in-notebooklm").addEventListener("click", fillNotebookTextareaFromSelection);

  videoGrid.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || !target.classList.contains("video-toggle")) {
      return;
    }

    const url = target.dataset.url ?? "";
    if (!url) {
      return;
    }

    if (target.checked) {
      state.selectedVideoUrls.add(url);
    } else {
      state.selectedVideoUrls.delete(url);
    }
    updateSelectionRibbon();
  });

  document.querySelectorAll<HTMLElement>(".chip-button").forEach((button) => {
    button.addEventListener("click", () => {
      const prompt = button.getAttribute("data-prompt");
      if (prompt) {
        nlAnalysis.value = prompt;
      }
    });
  });

  byId<HTMLButtonElement>("clear-pipeline").addEventListener("click", () => {
    nlForm.reset();
    clearMessage(nlStatus);
    nlProgress.hidden = true;
    resultPanel.hidden = true;
    stopPolling();
    stopProgressAnimation();
  });

  ytForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = byId<HTMLButtonElement>("yt-submit");
    submitButton.disabled = true;
    clearMessage(ytStatus);
    clearMessage(ytWarning);
    setMessage(ytStatus, "Searching YouTube and ranking results...", "info");

    const body = {
      count: Number.parseInt(byId<HTMLInputElement>("count").value, 10) || 25,
      query: byId<HTMLInputElement>("query").value.trim(),
      search_mode: byId<HTMLSelectElement>("search_mode").value,
      sort: byId<HTMLSelectElement>("sort").value,
    };

    try {
      const payload = await fetchJson<YtResearchPayload>("/api/yt-research", {
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      renderYtResults(payload, true);
      setMessage(ytStatus, `Loaded ${payload.returned_count ?? 0} videos.`, "success");
      if (payload.warnings?.length) {
        setMessage(ytWarning, payload.warnings.join(" | "), "warning");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Search failed.";
      setMessage(ytStatus, message, "error");
    } finally {
      submitButton.disabled = false;
    }
  });

  nlForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = byId<HTMLButtonElement>("nl-submit");
    clearMessage(nlStatus);
    resultPanel.hidden = true;

    if (!state.system?.auth_ready) {
      setMessage(
        nlStatus,
        `NotebookLM login is still required. Open a separate terminal and run ${state.system?.login_command || ".\\notebooklm.cmd login"}.`,
        "warning",
      );
      return;
    }

    const artifacts = Array.from(
      document.querySelectorAll<HTMLInputElement>('input[name="artifact"]:checked'),
    ).map((input) => input.value);

    if (!artifacts.length) {
      setMessage(nlStatus, "Choose at least one artifact to generate.", "warning");
      return;
    }

    let urlsPayload: { urls?: string[] } | Record<string, unknown>;
    try {
      urlsPayload = parseNotebookPayload(nlUrls.value);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Invalid URLs payload.";
      setMessage(nlStatus, message, "error");
      return;
    }

    submitButton.disabled = true;
    nlProgress.hidden = false;
    jobStage.textContent = "Queued";
    jobHelper.textContent = "Submitting the request to the backend.";
    setMessage(nlStatus, "Starting NotebookLM pipeline...", "info");

    const body = {
      analysis_prompt: nlAnalysis.value.trim() || undefined,
      artifact_instructions: byId<HTMLInputElement>("nl-artifact-instructions").value.trim() || undefined,
      artifacts,
      flashcards_format: byId<HTMLSelectElement>("nl-flashcards-format").value,
      infographic_orientation: "portrait",
      infographic_style: byId<HTMLSelectElement>("nl-infographic-style").value,
      slide_deck_format: "detailed",
      slide_deck_output_format: byId<HTMLSelectElement>("nl-slide-format").value,
      title: nlTitle.value.trim(),
      urls_data: urlsPayload,
    };

    try {
      const payload = await fetchJson<{ job_id: string }>("/api/notebooklm/pipeline", {
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      pollJob(payload.job_id, submitButton);
    } catch (error) {
      submitButton.disabled = false;
      nlProgress.hidden = true;
      const message = error instanceof Error ? error.message : "Unable to start the pipeline.";
      setMessage(nlStatus, message, "error");
    }
  });
}

void loadSystemStatus();
attachEventHandlers();
