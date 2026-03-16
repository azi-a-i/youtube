"use strict";
const state = {
    system: null,
    lastYtPayload: null,
    pulseTimer: null,
    pulseValue: 10,
    pollTimer: null,
    selectedVideoUrls: new Set(),
};
function byId(id) {
    const element = document.getElementById(id);
    if (!(element instanceof HTMLElement)) {
        throw new Error(`Missing expected element: ${id}`);
    }
    return element;
}
const ytForm = byId("yt-form");
const ytStatus = byId("yt-status");
const ytWarning = byId("yt-warning");
const ytResults = byId("yt-results");
const ytMeta = byId("yt-meta");
const videoGrid = byId("video-grid");
const selectionCount = byId("selection-count");
const nlForm = byId("nl-form");
const nlStatus = byId("nl-status");
const nlUrls = byId("nl-urls");
const nlTitle = byId("nl-title");
const nlAnalysis = byId("nl-analysis");
const nlProgress = byId("nl-job-progress");
const jobStage = byId("job-stage");
const jobHelper = byId("job-helper");
const jobProgressBar = byId("job-progress-bar");
const resultPanel = byId("result-panel");
const resultSummary = byId("result-summary");
const analysisAnswer = byId("analysis-answer");
const citationCount = byId("citation-count");
const artifactDownloads = byId("nl-artifacts");
const rawJson = byId("raw-json");
const systemModePill = byId("system-mode-pill");
const systemDot = byId("system-dot");
const authState = byId("auth-state");
const authSource = byId("auth-source");
const pythonState = byId("python-state");
const pythonPath = byId("python-path");
const serverMode = byId("server-mode");
const outputRoot = byId("output-root");
const loginCommand = byId("login-command");
const deployHint = byId("deploy-hint");
function setMessage(element, message, type) {
    element.textContent = message;
    element.className = `message message-${type}`;
    element.hidden = false;
}
function clearMessage(element) {
    element.textContent = "";
    element.className = "message";
    element.hidden = true;
}
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
function formatViews(value) {
    if (value == null) {
        return "Unknown";
    }
    if (value >= 1000000) {
        return `${(value / 1000000).toFixed(1)}M`;
    }
    if (value >= 1000) {
        return `${(value / 1000).toFixed(1)}K`;
    }
    return String(value);
}
function formatParagraphs(text) {
    if (!text) {
        return "<p>No NotebookLM answer was returned.</p>";
    }
    return text
        .split(/\n{2,}/)
        .filter(Boolean)
        .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
        .join("");
}
function getSelectedVideos() {
    const videos = state.lastYtPayload?.videos ?? [];
    return videos.filter((video) => {
        const url = video.url ?? "";
        return state.selectedVideoUrls.has(url);
    });
}
function updateSelectionRibbon() {
    selectionCount.textContent = `${getSelectedVideos().length} selected`;
}
function renderSystemStatus(payload) {
    state.system = payload;
    const authReady = Boolean(payload.auth_ready);
    const pythonReady = Boolean(payload.python_ready);
    const resolvedMode = payload.server_mode === "production" ? "Production mode" : "Local mode";
    const resolvedAuthSource = payload.auth_source === "env"
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
async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const payload = (await response.json());
    if (!response.ok) {
        throw new Error(payload.error || "Request failed.");
    }
    return payload;
}
async function loadSystemStatus() {
    try {
        const payload = await fetchJson("/api/system/status");
        renderSystemStatus(payload);
    }
    catch (error) {
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
function renderYtResults(payload, resetSelection) {
    const videos = payload.videos ?? [];
    state.lastYtPayload = payload;
    if (resetSelection) {
        state.selectedVideoUrls = new Set(videos
            .map((video) => video.url ?? "")
            .filter(Boolean));
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
function parseNotebookPayload(rawValue) {
    const trimmed = rawValue.trim();
    if (!trimmed) {
        throw new Error("Paste URLs or yt-research JSON first.");
    }
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
            return { urls: parsed };
        }
        return parsed;
    }
    const urls = trimmed
        .split(/\n/)
        .map((item) => item.trim())
        .filter(Boolean);
    return { urls };
}
function fillNotebookTextareaFromSelection() {
    const selectedVideos = getSelectedVideos();
    if (!selectedVideos.length) {
        setMessage(nlStatus, "Select at least one video first.", "warning");
        return;
    }
    const payload = {
        query: state.lastYtPayload?.query,
        returned_count: selectedVideos.length,
        search_mode: state.lastYtPayload?.search_mode,
        sort: state.lastYtPayload?.sort,
        videos: selectedVideos,
    };
    nlUrls.value = JSON.stringify(payload, null, 2);
    byId("pipeline-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}
function renderSummaryCards(result) {
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
function renderArtifacts(job) {
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
        }
        else {
            link.classList.add("is-disabled");
        }
        link.innerHTML = `
      <span class="card-label">${escapeHtml(item.kind || "artifact")}</span>
      <strong>${escapeHtml(item.name || "Download")}</strong>
    `;
        artifactDownloads.appendChild(link);
    });
}
function showNotebookResult(job) {
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
function stopProgressAnimation() {
    if (state.pulseTimer != null) {
        window.clearInterval(state.pulseTimer);
        state.pulseTimer = null;
    }
}
function startProgressAnimation() {
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
function stopPolling() {
    if (state.pollTimer != null) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}
function pollJob(jobId, submitButton) {
    stopPolling();
    startProgressAnimation();
    state.pollTimer = window.setInterval(async () => {
        try {
            const payload = await fetchJson(`/api/jobs/${jobId}`);
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
            }
            else if (payload.status === "error") {
                stopPolling();
                stopProgressAnimation();
                submitButton.disabled = false;
                nlProgress.hidden = true;
                setMessage(nlStatus, payload.error || "Pipeline failed.", "error");
            }
        }
        catch (error) {
            stopPolling();
            stopProgressAnimation();
            submitButton.disabled = false;
            nlProgress.hidden = true;
            const message = error instanceof Error ? error.message : "Polling failed.";
            setMessage(nlStatus, message, "error");
        }
    }, 2500);
}
function attachEventHandlers() {
    const scrollSearch = byId("scroll-to-search");
    const scrollPipeline = byId("scroll-to-pipeline");
    const scrollWorkspace = byId("scroll-to-workspace");
    scrollSearch.addEventListener("click", () => {
        byId("search-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    scrollPipeline.addEventListener("click", () => {
        byId("pipeline-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    scrollWorkspace.addEventListener("click", () => {
        byId("workspace").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    byId("clear-results").addEventListener("click", () => {
        state.lastYtPayload = null;
        state.selectedVideoUrls.clear();
        ytResults.hidden = true;
        videoGrid.innerHTML = "";
        updateSelectionRibbon();
        clearMessage(ytStatus);
        clearMessage(ytWarning);
    });
    byId("select-all-videos").addEventListener("click", () => {
        (state.lastYtPayload?.videos ?? []).forEach((video) => {
            if (video.url) {
                state.selectedVideoUrls.add(video.url);
            }
        });
        renderYtResults(state.lastYtPayload ?? { videos: [] }, false);
    });
    byId("clear-selection").addEventListener("click", () => {
        state.selectedVideoUrls.clear();
        renderYtResults(state.lastYtPayload ?? { videos: [] }, false);
    });
    byId("copy-selected-urls").addEventListener("click", async () => {
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
        }
        catch {
            setMessage(ytStatus, "Clipboard access failed. Copy from the NotebookLM field instead.", "warning");
        }
    });
    byId("use-in-notebooklm").addEventListener("click", fillNotebookTextareaFromSelection);
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
        }
        else {
            state.selectedVideoUrls.delete(url);
        }
        updateSelectionRibbon();
    });
    document.querySelectorAll(".chip-button").forEach((button) => {
        button.addEventListener("click", () => {
            const prompt = button.getAttribute("data-prompt");
            if (prompt) {
                nlAnalysis.value = prompt;
            }
        });
    });
    byId("clear-pipeline").addEventListener("click", () => {
        nlForm.reset();
        clearMessage(nlStatus);
        nlProgress.hidden = true;
        resultPanel.hidden = true;
        stopPolling();
        stopProgressAnimation();
    });
    ytForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const submitButton = byId("yt-submit");
        submitButton.disabled = true;
        clearMessage(ytStatus);
        clearMessage(ytWarning);
        setMessage(ytStatus, "Searching YouTube and ranking results...", "info");
        const body = {
            count: Number.parseInt(byId("count").value, 10) || 25,
            query: byId("query").value.trim(),
            search_mode: byId("search_mode").value,
            sort: byId("sort").value,
        };
        try {
            const payload = await fetchJson("/api/yt-research", {
                body: JSON.stringify(body),
                headers: { "Content-Type": "application/json" },
                method: "POST",
            });
            renderYtResults(payload, true);
            setMessage(ytStatus, `Loaded ${payload.returned_count ?? 0} videos.`, "success");
            if (payload.warnings?.length) {
                setMessage(ytWarning, payload.warnings.join(" | "), "warning");
            }
        }
        catch (error) {
            const message = error instanceof Error ? error.message : "Search failed.";
            setMessage(ytStatus, message, "error");
        }
        finally {
            submitButton.disabled = false;
        }
    });
    nlForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const submitButton = byId("nl-submit");
        clearMessage(nlStatus);
        resultPanel.hidden = true;
        if (!state.system?.auth_ready) {
            setMessage(nlStatus, `NotebookLM login is still required. Open a separate terminal and run ${state.system?.login_command || ".\\notebooklm.cmd login"}.`, "warning");
            return;
        }
        const artifacts = Array.from(document.querySelectorAll('input[name="artifact"]:checked')).map((input) => input.value);
        if (!artifacts.length) {
            setMessage(nlStatus, "Choose at least one artifact to generate.", "warning");
            return;
        }
        let urlsPayload;
        try {
            urlsPayload = parseNotebookPayload(nlUrls.value);
        }
        catch (error) {
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
            artifact_instructions: byId("nl-artifact-instructions").value.trim() || undefined,
            artifacts,
            flashcards_format: byId("nl-flashcards-format").value,
            infographic_orientation: "portrait",
            infographic_style: byId("nl-infographic-style").value,
            slide_deck_format: "detailed",
            slide_deck_output_format: byId("nl-slide-format").value,
            title: nlTitle.value.trim(),
            urls_data: urlsPayload,
        };
        try {
            const payload = await fetchJson("/api/notebooklm/pipeline", {
                body: JSON.stringify(body),
                headers: { "Content-Type": "application/json" },
                method: "POST",
            });
            pollJob(payload.job_id, submitButton);
        }
        catch (error) {
            submitButton.disabled = false;
            nlProgress.hidden = true;
            const message = error instanceof Error ? error.message : "Unable to start the pipeline.";
            setMessage(nlStatus, message, "error");
        }
    });
}
void loadSystemStatus();
attachEventHandlers();
