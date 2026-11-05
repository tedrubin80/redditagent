(() => {
  const $ = (sel) => document.querySelector(sel);
  const matchesEl = $("#matches");
  const banner = $("#banner");
  const filterStatus = $("#filter-status");
  let busy = false;
  let refreshTimer = null;

  function showBanner(message, kind = "ok") {
    banner.textContent = message;
    banner.className = `banner ${kind}`;
  }

  function hideBanner() {
    banner.className = "banner hidden";
    banner.textContent = "";
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
      ...options,
    });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { ok: false, error: text || res.statusText };
    }
    if (!res.ok) {
      const err = new Error((data && (data.error || data.message)) || res.statusText || "Request failed");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function fmtTime(value) {
    if (!value) return "never";
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return value;
      return d.toLocaleString();
    } catch {
      return value;
    }
  }

  function csv(list) {
    return (list || []).join(", ");
  }

  function splitCsv(value) {
    return String(value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function setBusy(on) {
    busy = on;
    ["#btn-poll", "#btn-pause", "#btn-check", "#btn-refresh"].forEach((sel) => {
      const el = $(sel);
      if (el) el.disabled = on;
    });
  }

  function renderStatus(status) {
    const open = (status.counts?.new || 0) + (status.counts?.reviewing || 0);
    $("#stat-paused").textContent = status.paused ? "paused" : "active";
    $("#stat-project").textContent = status.settings?.project_name || "(settings missing)";
    $("#stat-open").textContent = String(open);
    $("#stat-last-run").textContent = fmtTime(status.last_run_at);
    $("#stat-message").textContent =
      status.last_error || status.last_message || status.error || "No poll yet. Use Run poll.";
    if (status.last_error) $("#stat-message").style.color = "var(--warn)";
    else $("#stat-message").style.color = "";

    const provider = status.provider || "reddit-oauth";
    const providerEl = $("#stat-provider");
    if (providerEl) {
      providerEl.textContent = provider === "treg" ? "treg.to" : "Reddit OAuth";
      providerEl.title = provider === "treg"
        ? "Powered by treg.to (Crawl4AI + TikHub)"
        : "Reddit app-only OAuth";
    }
    // Show/hide search panel based on whether treg is available.
    const searchSection = $("#search-section");
    if (searchSection) {
      searchSection.style.display = provider === "treg" ? "" : "none";
    }

    const pauseBtn = $("#btn-pause");
    pauseBtn.textContent = status.paused ? "Resume" : "Pause";
    pauseBtn.dataset.paused = status.paused ? "1" : "0";

    $("#phase").textContent = status.phase || "phase3-dashboard";

    const counts = status.counts || {};
    $("#counts").innerHTML = ["new", "reviewing", "completed", "ignored", "deleted"]
      .map((k) => `<span>${k}: <strong>${counts[k] || 0}</strong></span>`)
      .join("");

    if (status.settings) fillSettings(status.settings);
  }

  function fillSettings(settings) {
    const form = $("#settings-form");
    form.project_name.value = settings.project_name || "";
    form.subreddits.value = csv(settings.subreddits);
    form.keywords.value = csv(settings.keywords);
    form.exclude_terms.value = csv(settings.exclude_terms);
    form.poll_limit.value = settings.poll_limit || 25;
    form.community_notes.value = JSON.stringify(settings.community_notes || {}, null, 2);
  }

  function matchCard(match) {
    const keywords = (match.matched_keywords || [])
      .map((k) => `<span class="chip">${escapeHtml(k)}</span>`)
      .join("");
    const note = match.community_note
      ? `<p class="note">${escapeHtml(match.community_note)}</p>`
      : "";
    const actions = [];
    if (match.status === "new") {
      actions.push(`<button type="button" class="btn compact" data-action="reviewing" data-id="${match.id}">Reviewing</button>`);
    }
    if (match.status === "new" || match.status === "reviewing") {
      actions.push(`<button type="button" class="btn compact" data-action="completed" data-id="${match.id}">Done</button>`);
      actions.push(`<button type="button" class="btn compact danger" data-action="ignored" data-id="${match.id}">Ignore</button>`);
    }
    if (match.status === "ignored" || match.status === "completed") {
      actions.push(`<button type="button" class="btn compact" data-action="new" data-id="${match.id}">Reopen</button>`);
    }
    actions.push(`<button type="button" class="btn compact ghost" data-comments-id="${match.id}">Comments</button>`);
    return `<article class="match" data-id="${match.id}">
      <h3 class="match-title"><a href="${escapeAttr(match.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(match.title)}</a></h3>
      <p class="meta">r/${escapeHtml(match.subreddit)} · u/${escapeHtml(match.author)}</p>
      <div class="chips">
        <span class="chip status-${escapeAttr(match.status)}">${escapeHtml(match.status)}</span>
        ${keywords}
      </div>
      ${note}
      <div class="match-actions">${actions.join("")}</div>
    </article>`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll("'", "&#39;");
  }

  async function loadMatches() {
    const filter = filterStatus.value;
    let path = "/api/matches?limit=100";
    if (filter === "all") path += "&include_ignored=1";
    else if (filter === "open") path += "";
    else if (filter === "ignored") path += "&status=ignored&include_ignored=1";
    else path += `&status=${encodeURIComponent(filter)}&include_ignored=1`;

    const data = await api(path);
    let matches = data.matches || [];
    if (filter === "open") {
      matches = matches.filter((m) => m.status === "new" || m.status === "reviewing");
    }
    if (!matches.length) {
      matchesEl.innerHTML = `<div class="empty">No matches in this view. Run a poll or widen the filter.</div>`;
      return;
    }
    matchesEl.innerHTML = matches.map(matchCard).join("");
  }

  async function refresh() {
    const status = await api("/api/status");
    renderStatus(status);
    await loadMatches();
  }

  async function withBusy(fn, okMessage) {
    if (busy) return;
    setBusy(true);
    hideBanner();
    try {
      const result = await fn();
      if (okMessage) showBanner(typeof okMessage === "function" ? okMessage(result) : okMessage, "ok");
      await refresh();
    } catch (err) {
      showBanner(err.message || String(err), "err");
      try { await refresh(); } catch { /* ignore */ }
    } finally {
      setBusy(false);
    }
  }

  $("#btn-poll").addEventListener("click", () =>
    withBusy(
      () => api("/api/poll", { method: "POST", body: "{}" }),
      (r) => r.message || `Poll complete · ${r.found ?? 0} new`
    )
  );

  $("#btn-pause").addEventListener("click", () => {
    const currentlyPaused = $("#btn-pause").dataset.paused === "1";
    withBusy(
      () =>
        api("/api/pause", {
          method: "POST",
          body: JSON.stringify({ paused: !currentlyPaused }),
        }),
      currentlyPaused ? "Monitoring resumed." : "Monitoring paused."
    );
  });

  $("#btn-check").addEventListener("click", () =>
    withBusy(
      () => api("/api/check", { method: "POST", body: "{}" }),
      (r) => r.message || "Connection OK"
    )
  );

  $("#btn-refresh").addEventListener("click", () => withBusy(refresh));
  filterStatus.addEventListener("change", () => withBusy(loadMatches));

  matchesEl.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (btn) {
      const id = btn.dataset.id;
      const status = btn.dataset.action;
      withBusy(
        () =>
          api(`/api/matches/${id}/status`, {
            method: "POST",
            body: JSON.stringify({ status }),
          }),
        `Marked as ${status}.`
      );
      return;
    }
    const commentsBtn = event.target.closest("button[data-comments-id]");
    if (commentsBtn) {
      openComments(commentsBtn.dataset.commentsId);
    }
  });

  $("#settings-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    let notes = {};
    try {
      notes = JSON.parse(form.community_notes.value || "{}");
      if (notes === null || typeof notes !== "object" || Array.isArray(notes)) {
        throw new Error("community notes must be a JSON object");
      }
    } catch (err) {
      showBanner(`Community notes JSON: ${err.message}`, "err");
      return;
    }
    const payload = {
      project_name: form.project_name.value.trim(),
      subreddits: splitCsv(form.subreddits.value),
      keywords: splitCsv(form.keywords.value),
      exclude_terms: splitCsv(form.exclude_terms.value),
      poll_limit: Number(form.poll_limit.value || 25),
      community_notes: notes,
    };
    withBusy(
      () => api("/api/settings", { method: "PUT", body: JSON.stringify(payload) }),
      "Settings saved."
    );
  });

  // ---- Search ----
  const searchForm = $("#search-form");
  const searchResults = $("#search-results");
  const searchBtn = $("#btn-search");

  function renderSearchResult(post) {
    const created = post.created_utc ? fmtTime(new Date(post.created_utc * 1000).toISOString()) : "";
    const excerpt = post.selftext
      ? `<p class="search-excerpt">${escapeHtml(post.selftext.slice(0, 220))}${post.selftext.length > 220 ? "…" : ""}</p>`
      : "";
    return `<article class="search-result">
      <h4 class="match-title"><a href="${escapeAttr(post.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(post.title)}</a></h4>
      <p class="meta">r/${escapeHtml(post.subreddit)} · u/${escapeHtml(post.author)}${created ? " · " + created : ""}</p>
      ${excerpt}
    </article>`;
  }

  if (searchForm) {
    searchForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const q = searchForm.q.value.trim();
      if (!q) return;
      const sub = searchForm.subreddit.value.trim().replace(/^r\//, "");
      const sort = searchForm.sort.value;
      const t = searchForm.t.value;
      searchBtn.disabled = true;
      searchResults.innerHTML = `<div class="empty">Searching…</div>`;
      searchResults.classList.remove("hidden");
      try {
        let path = `/api/search?q=${encodeURIComponent(q)}&sort=${encodeURIComponent(sort)}&t=${encodeURIComponent(t)}`;
        if (sub) path += `&subreddit=${encodeURIComponent(sub)}`;
        const data = await api(path);
        const posts = data.results || [];
        if (!posts.length) {
          searchResults.innerHTML = `<div class="empty">No results for "${escapeHtml(q)}".</div>`;
        } else {
          searchResults.innerHTML = `<p class="muted search-count">${posts.length} result${posts.length !== 1 ? "s" : ""}</p>` +
            posts.map(renderSearchResult).join("");
        }
      } catch (err) {
        searchResults.innerHTML = `<div class="empty" style="color:var(--warn)">${escapeHtml(err.message || String(err))}</div>`;
      } finally {
        searchBtn.disabled = false;
      }
    });
  }

  // ---- Comments modal ----
  const commentsModal = $("#comments-modal");
  const commentsList = $("#comments-list");
  const commentsTitle = $("#comments-modal-title");

  function renderComment(c) {
    const indent = Math.min(c.depth || 0, 6);
    const score = c.score !== null && c.score !== undefined ? `<span class="comment-score">${c.score > 0 ? "+" : ""}${c.score}</span>` : "";
    const created = c.created ? `<span class="comment-time">${fmtTime(c.created)}</span>` : "";
    return `<div class="comment" style="--depth:${indent}">
      <p class="comment-meta">
        <strong>${escapeHtml(c.author)}</strong>${score}${created}
        ${c.url ? `<a class="comment-link" href="${escapeAttr(c.url)}" target="_blank" rel="noopener noreferrer">↗</a>` : ""}
      </p>
      <p class="comment-text">${escapeHtml(c.text || "(no text)")}</p>
    </div>`;
  }

  async function openComments(matchId) {
    commentsModal.classList.remove("hidden");
    commentsTitle.textContent = "Loading comments…";
    commentsList.innerHTML = `<div class="empty">Fetching from treg…</div>`;
    try {
      const data = await api(`/api/matches/${matchId}/comments`);
      const comments = data.comments || [];
      commentsTitle.textContent = `${comments.length} comment${comments.length !== 1 ? "s" : ""}`;
      if (!comments.length) {
        commentsList.innerHTML = `<div class="empty">No comments returned.</div>`;
      } else {
        commentsList.innerHTML = comments.map(renderComment).join("");
      }
    } catch (err) {
      commentsTitle.textContent = "Comments";
      commentsList.innerHTML = `<div class="empty" style="color:var(--warn)">${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  function closeComments() {
    commentsModal.classList.add("hidden");
    commentsList.innerHTML = "";
  }

  if ($("#btn-close-comments")) {
    $("#btn-close-comments").addEventListener("click", closeComments);
  }
  if (commentsModal) {
    commentsModal.addEventListener("click", (e) => {
      if (e.target.classList.contains("modal-backdrop")) closeComments();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !commentsModal.classList.contains("hidden")) closeComments();
    });
  }

  refresh()
    .then(() => {
      refreshTimer = setInterval(() => {
        if (!busy) refresh().catch(() => {});
      }, 15000);
    })
    .catch((err) => showBanner(err.message || String(err), "err"));

  window.addEventListener("beforeunload", () => {
    if (refreshTimer) clearInterval(refreshTimer);
  });
})();
