(function () {
  const API = "/api";
  const state = {
    system: null,
    lastYtPayload: null,
    selectedVideoUrls: new Set(),
    pollTimer: null,
    pulseTimer: null,
    pulseValue: 10,
  };

  const ytForm = document.getElementById("yt-form");
  const ytStatus = document.getElementById("yt-status");
  const ytWarning = document.getElementById("yt-warning");
  const ytResults = document.getElementById("yt-results");
  const ytMeta = document.getElementById("yt-meta");
  const videoGrid = document.getElementById("video-grid");
  const selectionCount = document.getElementById("selection-count");

  const nlForm = document.getElementById("nl-form");
  const nlStatus = document.getElementById("nl-status");
  const nlUrls = document.getElementById("nl-urls");
  const nlTitle = document.getElementById("nl-title");
  const nlAnalysis = document.getElementById("nl-analysis");
  const nlProgress = document.getElementById("nl-job-progress");
  const jobStage = document.getElementById("job-stage");
  const jobHelper = document.getElementById("job-helper");
  const jobProgressBar = document.getElementById("job-progress-bar");

  const resultPanel = document.getElementById("result-panel");
  const resultSummary = document.getElementById("result-summary");
  const analysisAnswer = document.getElementById("analysis-answer");
  const citationCount = document.getElementById("citation-count");
  const artifactDownloads = document.getElementById("nl-artifacts");
  const rawJson = document.getElementById("raw-json");

  const systemDot = document.getElementById("system-dot");
  const authState = document.getElementById("auth-state");
  const pythonState = document.getElementById("python-state");
  const outputRoot = document.getElementById("output-root");
  const loginCommand = document.getElementById("login-command");
  const loginCommandLarge = document.getElementById("login-command-large");

  function setMessage(element, message, type) {
    if (!element) return;
    element.textContent = message;
    element.className = `message ${type ? `message-${type}` : ""}`.trim();
    element.hidden = false;
  }

  function clearMessage(element) {
    if (!element) return;
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
    if (value == null) return "Unknown";
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
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
    const videos = state.lastYtPayload?.videos || [];
    return videos.filter((video) => state.selectedVideoUrls.has(video.url));
  }

  function updateSelectionRibbon() {
    const selectedCount = getSelectedVideos().length;
    selectionCount.textContent = `${selectedCount} selected`;
  }

  function renderSystemStatus(payload) {
    state.system = payload;
    const authReady = Boolean(payload.auth_ready);
    const pythonReady = Boolean(payload.python_ready);

    authState.textContent = authReady ? "Ready" : "Login required";
    pythonState.textContent = pythonReady ? "Environment found" : "Python missing";
    outputRoot.textContent = payload.outputs_root || "Unavailable";
    loginCommand.textContent = payload.login_command || ".\\notebooklm.cmd login";
    loginCommandLarge.textContent = payload.login_command || ".\\notebooklm.cmd login";

    systemDot.classList.toggle("is-ready", authReady && pythonReady);
    systemDot.classList.toggle("is-warning", !authReady && pythonReady);
    systemDot.classList.toggle("is-error", !pythonReady);
  }

  async function loadSystemStatus() {
    try {
      const response = await fetch(`${API}/system/status`);
      const payload = await response.json();
      renderSystemStatus(payload);
    } catch (error) {
      authState.textContent = "Unavailable";
      pythonState.textContent = "Unavailable";
      outputRoot.textContent = "Status endpoint failed";
      systemDot.classList.add("is-error");
    }
  }

  function renderYtResults(payload, resetSelection) {
    const videos = payload.videos || [];
    state.lastYtPayload = payload;
    if (resetSelection) {
      state.selectedVideoUrls = new Set(videos.map((video) => video.url).filter(Boolean));
    }

    ytMeta.textContent = `${payload.returned_count || videos.length} videos for "${payload.query}"`;
    videoGrid.innerHTML = videos
      .map((video) => {
        const checked = state.selectedVideoUrls.has(video.url) ? "checked" : "";
        return `
          <article class="video-card" data-url="${escapeHtml(video.url || "")}">
            <label class="video-check">
              <input type="checkbox" class="video-toggle" data-url="${escapeHtml(video.url || "")}" ${checked} />
              <span>Use in pipeline</span>
            </label>
            <div class="video-card-body">
              <p class="video-rank">#${video.rank || "?"}</p>
              <h3>${escapeHtml(video.title || "Untitled video")}</h3>
              <p class="video-channel">${escapeHtml(video.channel || video.author || "Unknown channel")}</p>
            </div>
            <div class="video-metrics">
              <span>${formatViews(video.views)} views</span>
              <span>${escapeHtml(video.duration || "Unknown duration")}</span>
              <span>${escapeHtml(video.upload_date || "Unknown date")}</span>
            </div>
            <a class="video-link" href="${escapeHtml(video.url || "#")}" target="_blank" rel="noopener">Open video</a>
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
      search_mode: state.lastYtPayload?.search_mode,
      sort: state.lastYtPayload?.sort,
      returned_count: selectedVideos.length,
      videos: selectedVideos,
    };
    nlUrls.value = JSON.stringify(payload, null, 2);
    document.getElementById("pipeline-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderSummaryCards(result) {
    const notebook = result.notebook || {};
    const sources = result.sources || {};
    const readySources = sources.ready_sources || [];
    const artifactCount = (result.artifacts || []).length;

    resultSummary.innerHTML = `
      <div class="summary-card">
        <span class="mini-label">Notebook</span>
        <strong>${escapeHtml(notebook.title || "Untitled notebook")}</strong>
        <span class="summary-detail">${escapeHtml(notebook.id || "No ID")}</span>
      </div>
      <div class="summary-card">
        <span class="mini-label">Ready sources</span>
        <strong>${readySources.length}</strong>
        <span class="summary-detail">Imported into NotebookLM</span>
      </div>
      <div class="summary-card">
        <span class="mini-label">Artifacts</span>
        <strong>${artifactCount}</strong>
        <span class="summary-detail">Generated files</span>
      </div>
    `;
  }

  function renderArtifacts(job) {
    const items = job.artifacts || [];
    artifactDownloads.innerHTML = "";
    if (!items.length) {
      artifactDownloads.innerHTML = "<p class='empty-state'>No downloadable artifacts were returned.</p>";
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
        <span class="download-kind">${escapeHtml(item.kind || "artifact")}</span>
        <strong>${escapeHtml(item.name || "Download")}</strong>
      `;
      artifactDownloads.appendChild(link);
    });
  }

  function showNotebookResult(job) {
    const result = job.result || {};
    const analysis = result.analysis || {};
    renderSummaryCards(result);
    citationCount.textContent = `${(analysis.references || []).length} references`;
    analysisAnswer.innerHTML = formatParagraphs(analysis.answer);
    renderArtifacts(job);
    rawJson.textContent = JSON.stringify(result, null, 2);
    resultPanel.hidden = false;
    resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function stopProgressAnimation() {
    if (state.pulseTimer) {
      clearInterval(state.pulseTimer);
      state.pulseTimer = null;
    }
  }

  function startProgressAnimation() {
    stopProgressAnimation();
    state.pulseValue = 18;
    jobProgressBar.style.width = `${state.pulseValue}%`;
    state.pulseTimer = setInterval(() => {
      state.pulseValue = Math.min(88, state.pulseValue + 6);
      jobProgressBar.style.width = `${state.pulseValue}%`;
      if (state.pulseValue >= 88) {
        state.pulseValue = 46;
      }
    }, 1000);
  }

  async function pollJob(jobId, submitButton) {
    stopPolling();
    startProgressAnimation();
    state.pollTimer = setInterval(async () => {
      try {
        const response = await fetch(`${API}/jobs/${jobId}`);
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Unable to read job status.");
        }

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
        setMessage(nlStatus, error.message || "Polling failed.", "error");
      }
    }, 2500);
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function attachEventHandlers() {
    document.getElementById("scroll-to-search")?.addEventListener("click", () => {
      document.getElementById("search-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    document.getElementById("scroll-to-pipeline")?.addEventListener("click", () => {
      document.getElementById("pipeline-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    document.getElementById("clear-results")?.addEventListener("click", () => {
      state.lastYtPayload = null;
      state.selectedVideoUrls.clear();
      ytResults.hidden = true;
      videoGrid.innerHTML = "";
      updateSelectionRibbon();
      clearMessage(ytStatus);
      clearMessage(ytWarning);
    });

    document.getElementById("select-all-videos")?.addEventListener("click", () => {
      (state.lastYtPayload?.videos || []).forEach((video) => {
        if (video.url) state.selectedVideoUrls.add(video.url);
      });
      renderYtResults(state.lastYtPayload || { videos: [] }, false);
    });

    document.getElementById("clear-selection")?.addEventListener("click", () => {
      state.selectedVideoUrls.clear();
      renderYtResults(state.lastYtPayload || { videos: [] }, false);
    });

    document.getElementById("copy-selected-urls")?.addEventListener("click", async () => {
      const urls = getSelectedVideos().map((video) => video.url).filter(Boolean);
      if (!urls.length) {
        setMessage(ytStatus, "No selected URLs to copy yet.", "warning");
        return;
      }
      try {
        await navigator.clipboard.writeText(urls.join("\n"));
        setMessage(ytStatus, "Selected URLs copied to your clipboard.", "success");
      } catch (error) {
        setMessage(ytStatus, "Clipboard access failed. Copy from the NotebookLM field instead.", "warning");
      }
    });

    document.getElementById("use-in-notebooklm")?.addEventListener("click", fillNotebookTextareaFromSelection);

    videoGrid?.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || !target.classList.contains("video-toggle")) {
        return;
      }
      const url = target.dataset.url;
      if (!url) return;
      if (target.checked) {
        state.selectedVideoUrls.add(url);
      } else {
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

    document.getElementById("clear-pipeline")?.addEventListener("click", () => {
      nlForm.reset();
      clearMessage(nlStatus);
      nlProgress.hidden = true;
      resultPanel.hidden = true;
      stopPolling();
      stopProgressAnimation();
    });

    ytForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = document.getElementById("yt-submit");
      submitButton.disabled = true;
      clearMessage(ytStatus);
      clearMessage(ytWarning);
      setMessage(ytStatus, "Searching YouTube and ranking results...", "info");

      const body = {
        query: document.getElementById("query").value.trim(),
        count: parseInt(document.getElementById("count").value, 10) || 25,
        search_mode: document.getElementById("search_mode").value,
        sort: document.getElementById("sort").value,
      };

      try {
        const response = await fetch(`${API}/yt-research`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Search failed.");
        }
        renderYtResults(payload, true);
        setMessage(ytStatus, `Loaded ${payload.returned_count || 0} videos.`, "success");
        if (payload.warnings?.length) {
          setMessage(ytWarning, payload.warnings.join(" | "), "warning");
        }
      } catch (error) {
        setMessage(ytStatus, error.message || "Search failed.", "error");
      } finally {
        submitButton.disabled = false;
      }
    });

    nlForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = document.getElementById("nl-submit");
      clearMessage(nlStatus);
      resultPanel.hidden = true;

      if (!state.system?.auth_ready) {
        setMessage(
          nlStatus,
          `NotebookLM login is still required. Open a separate terminal and run ${state.system?.login_command || ".\\notebooklm.cmd login"}.`,
          "warning"
        );
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
      } catch (error) {
        setMessage(nlStatus, error.message, "error");
        return;
      }

      submitButton.disabled = true;
      nlProgress.hidden = false;
      jobStage.textContent = "Queued";
      jobHelper.textContent = "Submitting the request to the backend.";
      setMessage(nlStatus, "Starting NotebookLM pipeline...", "info");

      const body = {
        title: nlTitle.value.trim(),
        urls_data: urlsPayload,
        analysis_prompt: nlAnalysis.value.trim() || undefined,
        artifacts,
        artifact_instructions:
          document.getElementById("nl-artifact-instructions").value.trim() || undefined,
        infographic_style: document.getElementById("nl-infographic-style").value,
        infographic_orientation: "portrait",
        slide_deck_format: "detailed",
        slide_deck_output_format: document.getElementById("nl-slide-format").value,
        flashcards_format: document.getElementById("nl-flashcards-format").value,
      };

      try {
        const response = await fetch(`${API}/notebooklm/pipeline`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Unable to start the pipeline.");
        }
        pollJob(payload.job_id, submitButton);
      } catch (error) {
        submitButton.disabled = false;
        nlProgress.hidden = true;
        setMessage(nlStatus, error.message || "Unable to start the pipeline.", "error");
      }
    });
  }

  loadSystemStatus();
  attachEventHandlers();
})();
