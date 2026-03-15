(function () {
  const API = "/api";

  function setStatus(el, message, type) {
    if (!el) return;
    el.textContent = message;
    el.className = "status " + (type || "info");
    el.hidden = false;
  }

  function clearStatus(el) {
    if (!el) return;
    el.textContent = "";
    el.className = "status";
    el.hidden = true;
  }

  // —— YouTube Research ——
  const ytForm = document.getElementById("yt-form");
  const ytStatus = document.getElementById("yt-status");
  const ytResults = document.getElementById("yt-results");
  const ytTableBody = ytResults?.querySelector(".results-table tbody");
  const ytMeta = ytResults?.querySelector(".results-meta");
  const useInNotebooklmBtn = document.getElementById("use-in-notebooklm");

  let lastYtPayload = null;

  if (ytForm) {
    ytForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById("yt-submit");
      submitBtn.disabled = true;
      clearStatus(ytStatus);
      setStatus(ytStatus, "Searching YouTube…", "info");

      const data = {
        query: document.getElementById("query").value.trim(),
        count: parseInt(document.getElementById("count").value, 10) || 25,
        search_mode: document.getElementById("search_mode").value,
        sort: document.getElementById("sort").value,
      };

      try {
        const res = await fetch(API + "/yt-research", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        });
        const json = await res.json();
        if (!res.ok) {
          setStatus(ytStatus, json.error || "Search failed", "error");
          return;
        }
        lastYtPayload = json;
        renderYtResults(json);
        ytResults.hidden = false;
        setStatus(ytStatus, `Found ${json.returned_count || json.videos?.length || 0} videos.`, "success");
      } catch (err) {
        setStatus(ytStatus, err.message || "Request failed", "error");
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  function renderYtResults(payload) {
    const videos = payload.videos || [];
    if (!ytTableBody || !ytMeta) return;
    ytMeta.textContent = `Query: "${payload.query}" · ${payload.returned_count ?? videos.length} videos`;
    ytTableBody.innerHTML = videos
      .map(
        (v) => `
        <tr>
          <td class="num">${v.rank ?? ""}</td>
          <td>${escapeHtml(v.title || "—")}</td>
          <td>${escapeHtml(v.channel || v.author || "—")}</td>
          <td class="num">${formatViews(v.views)}</td>
          <td class="num">${escapeHtml(v.duration || "—")}</td>
          <td>${v.url ? `<a href="${escapeAttr(v.url)}" target="_blank" rel="noopener">Watch</a>` : "—"}</td>
        </tr>
      `
      )
      .join("");
  }

  function formatViews(n) {
    if (n == null) return "—";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return String(n);
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function escapeAttr(s) {
    return s.replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }

  if (useInNotebooklmBtn) {
    useInNotebooklmBtn.addEventListener("click", () => {
      const nlUrls = document.getElementById("nl-urls");
      if (!nlUrls) return;
      if (lastYtPayload && lastYtPayload.videos?.length) {
        nlUrls.value = JSON.stringify(lastYtPayload, null, 2);
        nlUrls.placeholder = "JSON from YouTube Research (auto-filled). You can also paste URLs or edit.";
        document.getElementById("notebooklm-panel")?.scrollIntoView({ behavior: "smooth" });
      } else {
        setStatus(document.getElementById("nl-status"), "Run a YouTube search first, then click this button.", "info");
      }
    });
  }

  // —— NotebookLM Pipeline ——
  const nlForm = document.getElementById("nl-form");
  const nlStatus = document.getElementById("nl-status");
  const nlProgress = document.getElementById("nl-job-progress");
  const nlResult = document.getElementById("nl-result");
  const nlResultMeta = nlResult?.querySelector(".result-meta");
  const nlArtifacts = document.getElementById("nl-artifacts");

  if (nlForm) {
    nlForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const titleEl = document.getElementById("nl-title");
      const urlsEl = document.getElementById("nl-urls");
      const title = titleEl?.value?.trim();
      const urlsRaw = urlsEl?.value?.trim();
      if (!title) {
        setStatus(nlStatus, "Enter a notebook title.", "error");
        return;
      }
      if (!urlsRaw) {
        setStatus(nlStatus, "Paste URLs (one per line) or yt-research JSON.", "error");
        return;
      }

      let urlsPayload;
      try {
        const first = urlsRaw.trimStart();
        if (first.startsWith("{") || first.startsWith("[")) {
          urlsPayload = JSON.parse(urlsRaw);
          if (Array.isArray(urlsPayload) && urlsPayload.every((x) => typeof x === "string")) {
            urlsPayload = { urls: urlsPayload };
          }
        } else {
          const lines = urlsRaw.split(/\n/).map((s) => s.trim()).filter(Boolean);
          urlsPayload = { urls: lines };
        }
      } catch {
        setStatus(nlStatus, "Invalid JSON or URL list.", "error");
        return;
      }

      const artifacts = Array.from(nlForm.querySelectorAll('input[name="artifact"]:checked')).map((c) => c.value);
      if (artifacts.length === 0) {
        setStatus(nlStatus, "Select at least one artifact type.", "error");
        return;
      }

      const submitBtn = document.getElementById("nl-submit");
      submitBtn.disabled = true;
      nlResult.hidden = true;
      clearStatus(nlStatus);
      setStatus(nlStatus, "Starting pipeline…", "info");
      nlProgress.hidden = false;

      const body = {
        title,
        urls_data: urlsPayload,
        analysis_prompt: document.getElementById("nl-analysis")?.value?.trim() || undefined,
        artifacts,
        artifact_instructions: document.getElementById("nl-artifact-instructions")?.value?.trim() || undefined,
        infographic_style: document.getElementById("nl-infographic-style")?.value || "auto",
        infographic_orientation: "portrait",
        slide_deck_format: "detailed",
        slide_deck_output_format: document.getElementById("nl-slide-format")?.value || "pptx",
        flashcards_format: document.getElementById("nl-flashcards-format")?.value || "markdown",
      };

      try {
        const res = await fetch(API + "/notebooklm/pipeline", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const json = await res.json();
        if (!res.ok) {
          setStatus(nlStatus, json.error || "Failed to start pipeline", "error");
          nlProgress.hidden = true;
          submitBtn.disabled = false;
          return;
        }
        const jobId = json.job_id;
        pollJob(jobId, submitBtn);
      } catch (err) {
        setStatus(nlStatus, err.message || "Request failed", "error");
        nlProgress.hidden = true;
        submitBtn.disabled = false;
      }
    });
  }

  function pollJob(jobId, submitBtn) {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(API + "/jobs/" + jobId);
        const job = await res.json();
        if (job.status === "done") {
          clearInterval(interval);
          nlProgress.hidden = true;
          submitBtn.disabled = false;
          setStatus(nlStatus, "Pipeline finished.", "success");
          showNlResult(job);
          nlResult.hidden = false;
        } else if (job.status === "error") {
          clearInterval(interval);
          nlProgress.hidden = true;
          submitBtn.disabled = false;
          setStatus(nlStatus, job.error || "Pipeline failed", "error");
        }
      } catch (err) {
        clearInterval(interval);
        nlProgress.hidden = true;
        submitBtn.disabled = false;
        setStatus(nlStatus, err.message || "Polling failed", "error");
      }
    }, 2500);
  }

  function showNlResult(job) {
    const result = job.result || {};
    if (nlResultMeta) {
      const nb = result.notebook || {};
      nlResultMeta.textContent = nb.name ? `Notebook: ${nb.name}` : "Pipeline completed.";
    }
    if (nlArtifacts) {
      const list = job.artifacts || [];
      nlArtifacts.innerHTML = list
        .filter((a) => a.url)
        .map((a) => `<a href="${escapeAttr(a.url)}" download>${escapeHtml(a.name)}</a>`)
        .join("");
      if (nlArtifacts.innerHTML === "" && list.length > 0) {
        nlArtifacts.innerHTML = "<span class='status info'>Artifacts saved on server. Check the outputs folder.</span>";
      }
    }
  }
})();
