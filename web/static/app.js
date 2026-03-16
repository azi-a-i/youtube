"use strict";
const NOTEBOOK_SESSION_KEY = "llmnotetube.notebooklmSession";
const bootstrapWindow = window;
const bootstrap = bootstrapWindow.LLMNOTETUBE_BOOTSTRAP ?? {};
const state = {
    lastYtPayload: null,
    pollTimer: null,
    pulseTimer: null,
    pulseValue: 10,
    selectedVideoUrls: new Set(),
    system: null,
};
function byId(id) {
    const element = document.getElementById(id);
    if (!(element instanceof HTMLElement)) {
        throw new Error(`Missing expected element: ${id}`);
    }
    return element;
}
function maybeById(id) {
    const element = document.getElementById(id);
    return element instanceof HTMLElement ? element : null;
}
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
function readNotebookSession() {
    try {
        const rawValue = window.localStorage.getItem(NOTEBOOK_SESSION_KEY);
        if (!rawValue) {
            return null;
        }
        const parsed = JSON.parse(rawValue);
        if (typeof parsed.authJson !== "string" || !parsed.authJson.trim()) {
            return null;
        }
        return parsed;
    }
    catch {
        return null;
    }
}
function writeNotebookSession(payload) {
    window.localStorage.setItem(NOTEBOOK_SESSION_KEY, JSON.stringify(payload));
}
function clearNotebookSession() {
    window.localStorage.removeItem(NOTEBOOK_SESSION_KEY);
}
function syncNotebookSessionInputs() {
    const session = readNotebookSession();
    const value = session?.authJson ?? "";
    const inputIds = ["connect-auth-json", "workspace-connect-auth-json"];
    inputIds.forEach((id) => {
        const input = maybeById(id);
        if (input) {
            input.value = value;
        }
    });
}
function formatValidatedAt(value) {
    if (!value) {
        return "Not validated yet";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return "Connected in this browser";
    }
    return `Validated ${date.toLocaleString()}`;
}
async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const text = await response.text();
    let payload = null;
    try {
        payload = JSON.parse(text);
    }
    catch {
        const snippet = text.slice(0, 140).trim();
        throw new Error(snippet || "Unexpected non-JSON response from the server.");
    }
    if (!response.ok) {
        throw new Error(payload.error || "Request failed.");
    }
    return payload;
}
function getSelectedVideos() {
    const videos = state.lastYtPayload?.videos ?? [];
    return videos.filter((video) => {
        const url = video.url ?? "";
        return state.selectedVideoUrls.has(url);
    });
}
function updateSelectionRibbon() {
    const selectionCount = maybeById("selection-count");
    if (selectionCount) {
        selectionCount.textContent = `${getSelectedVideos().length} selected`;
    }
}
function updateConnectionPanels() {
    const session = readNotebookSession();
    const connected = Boolean(session);
    const cookieCount = session?.cookieCount ?? 0;
    const detail = connected
        ? `${formatValidatedAt(session?.validatedAt)}${cookieCount ? ` • ${cookieCount} cookies detected` : ""}`
        : "No NotebookLM session has been saved in this browser yet.";
    const connectSessionState = maybeById("connect-session-state");
    const connectSessionDetail = maybeById("connect-session-detail");
    const connectCookieCount = maybeById("connect-cookie-count");
    const workspaceSessionState = maybeById("workspace-session-state");
    const workspaceSessionDetail = maybeById("workspace-session-detail");
    if (connectSessionState) {
        connectSessionState.textContent = connected ? "Connected" : "Not connected";
    }
    if (connectSessionDetail) {
        connectSessionDetail.textContent = detail;
    }
    if (connectCookieCount) {
        connectCookieCount.textContent = String(cookieCount);
    }
    if (workspaceSessionState) {
        workspaceSessionState.textContent = connected ? "Connected" : "Not connected";
    }
    if (workspaceSessionDetail) {
        workspaceSessionDetail.textContent = connected
            ? detail
            : "Add a NotebookLM session to power synthesis in this browser.";
    }
}
function renderSystemStatus(payload) {
    state.system = payload;
    const session = readNotebookSession();
    const hasBrowserSession = Boolean(session);
    const hasSharedBackend = payload.notebooklm_ready;
    const notebookReady = hasBrowserSession || hasSharedBackend;
    const researchState = maybeById("research-state");
    const researchDetail = maybeById("research-detail");
    const notebookState = maybeById("notebook-state");
    const notebookDetail = maybeById("notebook-detail");
    const runtimeState = maybeById("runtime-state");
    const runtimeDetail = maybeById("runtime-detail");
    const workspaceState = maybeById("workspace-state");
    const workspaceDetail = maybeById("workspace-detail");
    const workspaceNote = maybeById("workspace-note");
    if (researchState) {
        researchState.textContent = payload.yt_research_ready ? "Ready" : "Offline";
    }
    if (researchDetail) {
        researchDetail.textContent = payload.yt_research_ready
            ? "YouTube topic search is available without any login."
            : "The Python backend is not ready for YouTube search.";
    }
    if (notebookState) {
        notebookState.textContent = notebookReady ? "Connected" : "Not connected";
    }
    if (notebookDetail) {
        if (hasBrowserSession) {
            notebookDetail.textContent = `Connected in this browser. ${formatValidatedAt(session?.validatedAt)}`;
        }
        else if (hasSharedBackend) {
            notebookDetail.textContent = `Shared backend auth source: ${payload.auth_source || "connected"}`;
        }
        else {
            notebookDetail.textContent =
                payload.deploy_auth_hint || "Connect NotebookLM to run synthesis and generate artifacts.";
        }
    }
    if (runtimeState) {
        runtimeState.textContent = payload.python_ready ? "Operational" : "Unavailable";
    }
    if (runtimeDetail) {
        runtimeDetail.textContent = payload.python_ready
            ? hasSharedBackend
                ? `Python is ready. Shared NotebookLM auth source: ${payload.auth_source || "connected"}`
                : "Python is ready. Shared NotebookLM auth is not configured on this deployment."
            : "Python runtime is unavailable, so searches and NotebookLM jobs cannot run.";
    }
    if (workspaceState) {
        if (!payload.python_ready) {
            workspaceState.textContent = "Offline";
        }
        else if (notebookReady) {
            workspaceState.textContent = "Synthesis ready";
        }
        else {
            workspaceState.textContent = "Research ready";
        }
    }
    if (workspaceDetail) {
        workspaceDetail.textContent = !payload.python_ready
            ? "The backend runtime is unavailable."
            : notebookReady
                ? "Search, synthesis, and artifact generation are available."
                : "You can research immediately. Connect NotebookLM to unlock synthesis.";
    }
    if (workspaceNote) {
        workspaceNote.className = notebookReady ? "message message-info" : "message message-warning";
        workspaceNote.textContent = notebookReady
            ? hasBrowserSession
                ? "NotebookLM is connected in this browser, so pipeline requests can use your session."
                : `NotebookLM is powered by shared backend auth in ${payload.pipeline_delivery_mode || "background"} mode.`
            : payload.deploy_auth_hint || "Connect NotebookLM to enable synthesis.";
    }
    updateConnectionPanels();
}
async function loadSystemStatus() {
    try {
        const payload = await fetchJson("/api/system/status");
        renderSystemStatus(payload);
    }
    catch (error) {
        const message = error instanceof Error ? error.message : "Status endpoint failed.";
        const elements = [
            maybeById("research-detail"),
            maybeById("notebook-detail"),
            maybeById("runtime-detail"),
            maybeById("workspace-detail"),
        ];
        elements.forEach((element) => {
            if (element) {
                element.textContent = message;
            }
        });
    }
}
function renderYtResults(payload, resetSelection) {
    const ytMeta = maybeById("yt-meta");
    const ytResults = maybeById("yt-results");
    const videoGrid = maybeById("video-grid");
    const nlTitle = maybeById("nl-title");
    if (!ytMeta || !ytResults || !videoGrid) {
        return;
    }
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
    if (nlTitle && !nlTitle.value.trim() && payload.query) {
        nlTitle.value = `LLMNoteTube Research: ${payload.query}`;
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
    const nlStatus = maybeById("nl-status");
    const nlUrls = maybeById("nl-urls");
    if (!nlUrls) {
        return;
    }
    const selectedVideos = getSelectedVideos();
    if (!selectedVideos.length) {
        if (nlStatus) {
            setMessage(nlStatus, "Select at least one video first.", "warning");
        }
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
    maybeById("pipeline-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}
function renderSummaryCards(result) {
    const resultSummary = maybeById("result-summary");
    if (!resultSummary) {
        return;
    }
    const notebook = result.notebook ?? {};
    const readySources = result.sources?.ready_sources ?? [];
    const artifactCount = result.artifacts?.length ?? 0;
    resultSummary.innerHTML = `
    <div class="summary-card">
      <span class="status-label">Notebook</span>
      <strong>${escapeHtml(notebook.title || "Untitled notebook")}</strong>
      <span>${escapeHtml(notebook.id || "No ID")}</span>
    </div>
    <div class="summary-card">
      <span class="status-label">Ready sources</span>
      <strong>${readySources.length}</strong>
      <span>Imported into NotebookLM</span>
    </div>
    <div class="summary-card">
      <span class="status-label">Artifacts</span>
      <strong>${artifactCount}</strong>
      <span>Generated files</span>
    </div>
  `;
}
function renderArtifacts(job) {
    const artifactDownloads = maybeById("nl-artifacts");
    if (!artifactDownloads) {
        return;
    }
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
      <span class="status-label">${escapeHtml(item.kind || "artifact")}</span>
      <strong>${escapeHtml(item.name || "Download")}</strong>
    `;
        artifactDownloads.appendChild(link);
    });
}
function showNotebookResult(job) {
    const resultPanel = maybeById("result-panel");
    const analysisAnswer = maybeById("analysis-answer");
    const citationCount = maybeById("citation-count");
    const rawJson = maybeById("raw-json");
    if (!resultPanel || !analysisAnswer || !citationCount || !rawJson) {
        return;
    }
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
    const jobProgressBar = maybeById("job-progress-bar");
    if (!jobProgressBar) {
        return;
    }
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
    const nlStatus = maybeById("nl-status");
    const nlProgress = maybeById("nl-job-progress");
    const jobStage = maybeById("job-stage");
    const jobHelper = maybeById("job-helper");
    const jobProgressBar = maybeById("job-progress-bar");
    if (!nlStatus || !nlProgress || !jobStage || !jobHelper || !jobProgressBar) {
        return;
    }
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
function attachNotebookConnectForm(formId, inputId, statusId, clearId) {
    const form = maybeById(formId);
    const input = maybeById(inputId);
    const status = maybeById(statusId);
    const clearButton = maybeById(clearId);
    if (!form || !input || !status) {
        return;
    }
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const authJson = input.value.trim();
        if (!authJson) {
            setMessage(status, "Paste your NotebookLM auth JSON first.", "warning");
            return;
        }
        setMessage(status, "Validating NotebookLM session...", "info");
        try {
            const payload = await fetchJson("/api/notebooklm/validate", {
                body: JSON.stringify({ auth_json: authJson }),
                headers: { "Content-Type": "application/json" },
                method: "POST",
            });
            writeNotebookSession({
                authJson,
                cookieCount: payload.cookie_count ?? 0,
                validatedAt: new Date().toISOString(),
            });
            syncNotebookSessionInputs();
            updateConnectionPanels();
            if (state.system) {
                renderSystemStatus(state.system);
            }
            else {
                await loadSystemStatus();
            }
            setMessage(status, payload.message || "NotebookLM is connected in this browser.", "success");
        }
        catch (error) {
            const message = error instanceof Error ? error.message : "Unable to validate NotebookLM auth JSON.";
            setMessage(status, message, "error");
        }
    });
    clearButton?.addEventListener("click", () => {
        clearNotebookSession();
        syncNotebookSessionInputs();
        updateConnectionPanels();
        if (state.system) {
            renderSystemStatus(state.system);
        }
        setMessage(status, "NotebookLM session cleared from this browser.", "info");
    });
}
function attachWorkspaceHandlers() {
    const ytForm = maybeById("yt-form");
    const nlForm = maybeById("nl-form");
    if (!ytForm || !nlForm) {
        return;
    }
    const ytStatus = byId("yt-status");
    const ytWarning = byId("yt-warning");
    const ytResults = byId("yt-results");
    const videoGrid = byId("video-grid");
    const nlStatus = byId("nl-status");
    const nlUrls = byId("nl-urls");
    const nlTitle = byId("nl-title");
    const nlAnalysis = byId("nl-analysis");
    const nlProgress = byId("nl-job-progress");
    const jobStage = byId("job-stage");
    const jobHelper = byId("job-helper");
    const resultPanel = byId("result-panel");
    maybeById("clear-results")?.addEventListener("click", () => {
        state.lastYtPayload = null;
        state.selectedVideoUrls.clear();
        ytResults.hidden = true;
        videoGrid.innerHTML = "";
        updateSelectionRibbon();
        clearMessage(ytStatus);
        clearMessage(ytWarning);
    });
    maybeById("select-all-videos")?.addEventListener("click", () => {
        (state.lastYtPayload?.videos ?? []).forEach((video) => {
            if (video.url) {
                state.selectedVideoUrls.add(video.url);
            }
        });
        renderYtResults(state.lastYtPayload ?? { videos: [] }, false);
    });
    maybeById("clear-selection")?.addEventListener("click", () => {
        state.selectedVideoUrls.clear();
        renderYtResults(state.lastYtPayload ?? { videos: [] }, false);
    });
    maybeById("copy-selected-urls")?.addEventListener("click", async () => {
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
    maybeById("use-in-notebooklm")?.addEventListener("click", fillNotebookTextareaFromSelection);
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
    maybeById("clear-pipeline")?.addEventListener("click", () => {
        nlForm.reset();
        clearMessage(nlStatus);
        nlProgress.hidden = true;
        resultPanel.hidden = true;
        stopPolling();
        stopProgressAnimation();
        if (state.lastYtPayload?.query) {
            nlTitle.value = `LLMNoteTube Research: ${state.lastYtPayload.query}`;
        }
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
        const notebookSession = readNotebookSession();
        if (!notebookSession && !state.system?.notebooklm_ready) {
            setMessage(nlStatus, "Connect NotebookLM first, or use a deployment with shared NotebookLM backend auth.", "warning");
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
            auth_json: notebookSession?.authJson,
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
            if (payload.mode === "direct") {
                submitButton.disabled = false;
                nlProgress.hidden = true;
                setMessage(nlStatus, "NotebookLM pipeline finished successfully.", "success");
                showNotebookResult({
                    artifacts: payload.artifacts,
                    result: payload.result,
                });
                return;
            }
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
syncNotebookSessionInputs();
updateConnectionPanels();
void loadSystemStatus();
attachNotebookConnectForm("connect-form", "connect-auth-json", "connect-status", "clear-connect");
attachNotebookConnectForm("workspace-connect-form", "workspace-connect-auth-json", "workspace-connect-status", "workspace-clear-connect");
attachWorkspaceHandlers();
