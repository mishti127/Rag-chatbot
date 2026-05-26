/** Vectorless RAG SPA */

(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  let meta = { themes: [], tool_actions: [] };
  let currentThreadId = null;
  let selectedToolAction = "summarize";
  let noteFormat = "plain";
  let pendingFiles = [];
  const ACTIVE_SOURCE_KEY = "rag-active-source";
  const DOCUMENT_SELECTS = [
    { id: "chat-source", emptyLabel: "All documents" },
    { id: "tool-source", emptyLabel: "All documents" },
    { id: "notes-source", emptyLabel: "Select document…", noEmpty: true },
    { id: "km-source", emptyLabel: "All indexed documents" },
    { id: "tl-source", emptyLabel: "All indexed documents" },
    { id: "notebook-source", emptyLabel: "None" },
  ];
  let compareFileA = null;
  let compareFileB = null;
  let lastCompareReport = "";
  const compareMode = { a: "upload", b: "upload" };
  let selectedOutlineSource = null;
  /** @type {"all"|"summaries"|"topics"|"explanations"|"custom"} */
  let notebookFilter = "all";

  const TRASH_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a1 1 0 001 1h8a1 1 0 001-1l1-12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>`;

  const DEFAULT_TOOL_ACTIONS = [
    { id: "summarize", label: "Summarize document" },
    { id: "bullet_points", label: "Extract topics" },
    { id: "study_questions", label: "Question generator" },
    { id: "conclusion", label: "Document insights" },
    { id: "index", label: "Text extractor" },
    { id: "headings", label: "Citation finder" },
    { id: "keyword_focus", label: "Keyword finder" },
    { id: "custom", label: "Custom instruction" },
  ];

  const TOOL_CARD_GRADIENT_CLASSES = [
    "tool-card-purple",
    "tool-card-blue",
    "tool-card-teal",
    "tool-card-rose",
    "tool-card-slate",
    "tool-card-amber",
  ];

  /** @returns {string} */
  function displayFirstName(user) {
    const raw = (user?.display_name || user?.username || "there").trim();
    const token = raw.split(/\s+/)[0] || "there";
    return token.slice(0, 1).toUpperCase() + token.slice(1);
  }

  /** @returns {string} Good morning | afternoon | evening */
  function timeOfDayGreeting() {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  }

  /** @returns {string} Relative label like “2 mins ago”, or '' if missing */
  function relativeTime(iso) {
    if (!iso) return "";
    const t = Date.parse(String(iso));
    if (!Number.isFinite(t)) return "";
    let sec = Math.floor((Date.now() - t) / 1000);
    if (sec < 0) sec = 0;
    if (sec < 60) return "just now";
    const min = Math.floor(sec / 60);
    if (min < 60) return min === 1 ? "1 min ago" : `${min} mins ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return hr === 1 ? "1 hour ago" : `${hr} hours ago`;
    const day = Math.floor(hr / 24);
    if (day < 14) return day === 1 ? "Yesterday" : `${day} days ago`;
    const wk = Math.floor(day / 7);
    if (wk < 8) return wk === 1 ? "1 week ago" : `${wk} weeks ago`;
    return new Date(t).toLocaleDateString();
  }

  function buildChatWelcome() {
    const u = API.getUser();
    const name = displayFirstName(u);
    const lead = `${timeOfDayGreeting()}, ${escapeHtml(name)}`;
    return (
      '<div class="chat-welcome">' +
      '<div class="chat-welcome-icon" aria-hidden="true">' +
      '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/><path d="M5 19h14"/></svg>' +
      "</div>" +
      `<h2>${lead} 👋</h2>` +
      "<p>Ask anything about your library — citations, summaries, comparisons, maps, and timelines.</p>" +
      '<div class="chat-welcome-chips" aria-hidden="true">' +
      "<span>Summarize</span><span>Compare</span><span>Knowledge map</span><span>Timeline</span>" +
      "</div></div>"
    );
  }

  function updatePersonalizedGreetings() {
    const u = API.getUser();
    const name = displayFirstName(u);
    const greetingEl = $("#doc-hero-greeting");
    if (greetingEl) {
      greetingEl.textContent = `${timeOfDayGreeting()}, ${name} 👋`;
    }
    const sub = $(".ref-doc-hero-sub");
    if (sub && !sub.dataset.lockedCopy) {
      sub.textContent = "Upload your documents and start asking questions grounded in your files.";
    }
  }

  async function refreshDashboardStats() {
    const docEl = $("#dash-stat-docs");
    const chatEl = $("#dash-stat-chats");
    const pageEl = $("#dash-stat-pages");
    const diskEl = $("#dash-stat-disk");
    const docDelta = $("#dash-stat-docs-delta");
    const chatDelta = $("#dash-stat-chats-delta");
    const pageDelta = $("#dash-stat-pages-delta");
    const diskDelta = $("#dash-stat-disk-delta");
    if (!docEl && !chatEl) return;
    try {
      const [{ threads }, { sources }] = await Promise.all([API.listChats(), API.listDocuments()]);
      const nDoc = sources.length;
      const nChat = threads.length;
      if (docEl) docEl.textContent = String(nDoc);
      if (chatEl) chatEl.textContent = String(nChat);
      if (docDelta)
        docDelta.textContent =
          nDoc > 5 ? `${Math.min(nDoc + 4, nDoc + 24)} refs ready` : nDoc ? "Growing library" : "Upload to start";
      if (chatDelta) chatDelta.textContent = nChat ? `+${Math.min(nChat, 12)} active` : "+0 this week";
      if (pageEl) {
        pageEl.textContent =
          nDoc > 0 ? String(Math.round(nDoc * 32)) : "—";
      }
      if (pageDelta) pageDelta.textContent = nDoc ? `~${Math.round(nDoc * 32)} est. refs` : "No pages yet";

      let diskLbl = "—";
      let diskSub = "Balanced workspace";
      if (!nDoc) {
        diskLbl = "—";
        diskSub = "Balanced workspace";
      } else if (nDoc < 8) {
        diskLbl = "Light";
        diskSub = "~" + Math.round(nDoc * 12) + " MB est.";
      } else if (nDoc < 40) {
        diskLbl = "Active";
        diskSub = "Healthy indexing load";
      } else {
        diskLbl = "Dense";
        diskSub = "Heavy stack — prune if needed";
      }
      if (diskEl) diskEl.textContent = diskLbl;
      if (diskDelta) diskDelta.textContent = diskSub;
    } catch {
      /* ignore */
    }
  }

  /** Flatten backend history buckets into recent-activity rows (most recent first). */
  function collectActivityFlat(historyPayload) {
    const h = historyPayload || {};
    const flat = [];
    (h.documents || []).forEach((e) => {
      if (e.action === "removed") return;
      flat.push({
        kind: "doc",
        ts: e.ts,
        label: e.filename ? `${e.filename}` : "Document indexed",
        verb: "Upload",
      });
    });
    (h.chats || []).forEach((c) => {
      flat.push({
        kind: "chat",
        ts: c.updated,
        label: (c.title || "Chat").slice(0, 80),
        verb: "Chat",
      });
    });
    (h.tools || []).forEach((t) => {
      flat.push({
        kind: "tool",
        ts: t.ts,
        label: ((t.label || t.action || "Tool") + "").replace(/_/g, " "),
        verb: "Tool",
      });
    });
    flat.sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
    return flat;
  }

  function paintActivityUIs(flat) {
    const lucideKind = { doc: "file-plus", chat: "message-square", tool: "wand-2" };
    const top = flat.slice(0, 6);
    const topRail = flat.slice(0, 5);

    const wrap = $("#doc-activity-wrap");
    const inner = $("#doc-activity-inner");
    if (wrap && inner) {
      if (!top.length) {
        wrap.classList.add("hidden");
        inner.innerHTML = "";
      } else {
        inner.innerHTML = top
          .map(
            (x) =>
              `<div class="activity-chip ${x.kind}"><span class="activity-chip-icon ${x.kind}" aria-hidden="true"><i data-lucide="${lucideKind[x.kind] || "sparkles"}"></i></span><span>${escapeHtml(x.verb)}: ${escapeHtml(x.label.slice(0, 36))}${x.label.length > 36 ? "…" : ""}</span></div>`,
          )
          .join("");
        wrap.classList.remove("hidden");
      }
    }

    const rail = $("#rail-activity-inner");
    const empty = $("#rail-activity-empty");
    if (rail) {
      if (!topRail.length) {
        rail.innerHTML = "";
        empty?.classList.remove("hidden");
      } else {
        empty?.classList.add("hidden");
        rail.innerHTML = topRail
          .map(
            (x) =>
              `<div class="rail-activity-chip"><span class="rail-chip-dot" aria-hidden="true"></span><span><strong>${escapeHtml(x.verb)}</strong> · ${escapeHtml(x.label.slice(0, 64))}${x.label.length > 64 ? "…" : ""}</span></div>`,
          )
          .join("");
      }
    }
  }

  async function renderDocActivityStrip() {
    const wrap = $("#doc-activity-wrap");
    const inner = $("#doc-activity-inner");
    const rail = $("#rail-activity-inner");
    if (!inner && !rail) return;
    try {
      const h = await API.history();
      paintActivityUIs(collectActivityFlat(h));
      refreshLucideIcons();
    } catch {
      wrap?.classList.add("hidden");
      if (inner) inner.innerHTML = "";
      if (rail) rail.innerHTML = "";
      $("#rail-activity-empty")?.classList.remove("hidden");
    }
  }

  function updateDocsStatsStrip(sources) {
    const n = sources?.length ?? 0;
    const idx = $("#doc-stat-indexed");
    const seg = $("#doc-stat-segments");
    if (idx) idx.textContent = String(n);
    if (seg) seg.textContent = n ? String(Math.round(n * 32)) : "—";
  }

  function updateDocsQueueStrip() {
    const q = $("#doc-stat-queue");
    if (q) q.textContent = String(pendingFiles.length);
    const st = $("#doc-stat-processor");
    const busy = $("#upload-status")?.dataset?.busy === "1";
    if (st) st.textContent = busy ? "Indexing" : pendingFiles.length ? "Queued" : "Ready";
  }

  function toolActionLucideIcon(id) {
    const map = {
      summarize: "file-text",
      bullet_points: "layers",
      study_questions: "help-circle",
      conclusion: "lightbulb",
      index: "align-left",
      headings: "quote",
      keyword_focus: "hash",
      custom: "pencil-line",
    };
    return map[id] || "sparkles";
  }

  function toolActionBlurb(id, label) {
    const map = {
      summarize: "One-pass executive summary of the active document scope.",
      bullet_points: "Surface main themes as tight bullet topics.",
      study_questions: "Exam-style questions you can drill with.",
      conclusion: "Takeaways, risks, and opportunities in prose.",
      index: "Structured outline mirroring headings in the corpus.",
      headings: "Notable statements to trace back while writing.",
      keyword_focus: "High-signal terms for search and tagging.",
      custom: "Your own instruction — runs strictly on indexed text.",
    };
    return map[id] || `Run ${label} on your library.`;
  }

  function renderToolActionCards() {
    const host = $("#tools-cards");
    const sel = $("#tool-action");
    if (!host || !sel) return;
    const actions = meta.tool_actions?.length ? meta.tool_actions : DEFAULT_TOOL_ACTIONS;
    host.innerHTML = "";
    actions.forEach((a, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `tool-action-card ${TOOL_CARD_GRADIENT_CLASSES[i % TOOL_CARD_GRADIENT_CLASSES.length]}`;
      const icon = toolActionLucideIcon(a.id);
      btn.innerHTML =
        `<span class="tool-action-card-ico" aria-hidden="true"><i data-lucide="${icon}"></i></span>` +
        `<strong>${escapeHtml(a.label)}</strong>` +
        `<small>${escapeHtml(toolActionBlurb(a.id, a.label))}</small>`;
      btn.addEventListener("click", () => {
        sel.value = a.id;
        selectedToolAction = a.id;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        $("#btn-run-tool")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
      host.appendChild(btn);
    });
    refreshLucideIcons();
  }

  async function cycleHeaderTheme() {
    const themes = (meta.themes || []).map((t) => t.id).filter(Boolean);
    if (!themes.length) return;
    const cur =
      document.documentElement.getAttribute("data-theme") || API.getUser()?.theme || themes[0];
    let i = themes.indexOf(cur);
    if (i < 0) i = 0;
    const next = themes[(i + 1) % themes.length];
    applyTheme(next);
    const u = API.getUser();
    if (u) {
      u.theme = next;
      API.setUser(u);
      try {
        await API.setTheme(next);
      } catch {
        /* ignore */
      }
    }
    renderThemeGrid(next);
  }

  const THEME_SWATCHES = {
    midnight: ["#030014", "#c4b5fd"],
    ocean: ["#0b1220", "#38bdf8"],
    sunset: ["#1a0f14", "#fb923c"],
    forest: ["#0a1612", "#4ade80"],
    lavender: ["#13111c", "#c084fc"],
    ember: ["#140a08", "#f87171"],
    arctic: ["#f0f9ff", "#0891b2"],
    light: ["#f8fafc", "#4f46e5"],
  };

  function toast(msg, ms = 3000) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), ms);
  }
  window.toast = toast;

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function speechText(raw) {
    if (typeof TTSService !== "undefined" && TTSService.cleanText) {
      return TTSService.cleanText(raw);
    }
    return (raw || "").replace(/\s*\[[^\]]+\]\s*/g, " ").replace(/\s+/g, " ").trim();
  }

  function attachListen(parent, getText, className = "content-tts-bar") {
    if (typeof TTSService === "undefined" || !TTSService.enabled || !parent) return null;
    return TTSService.appendListenBar(parent, getText, className);
  }

  function explanationSpeechText(explanation) {
    if (!explanation) return "";
    const parts = [explanation.why_answer || ""];
    (explanation.pages || []).forEach((p) => {
      if (p.title) parts.push(p.title);
      if (p.traversal_logic) parts.push(p.traversal_logic);
    });
    return speechText(parts.filter(Boolean).join(". "));
  }

  function applyTheme(id) {
    document.documentElement.setAttribute("data-theme", id || "midnight");
    $$(".theme-swatch").forEach((sw) => {
      sw.classList.toggle("active", sw.dataset.theme === id);
    });
  }

  function showAuth() {
    API.setToken(null);
    API.setUser(null);
    currentThreadId = null;
    $("#auth-screen").classList.remove("hidden");
    $("#app-shell").classList.add("hidden");
  }

  function showApp(user) {
    $("#auth-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
    const name = user.display_name || user.username;
    const initial = (name && name[0] ? name[0] : "?").toUpperCase();
    $("#header-name").textContent = name;
    $("#header-avatar").textContent = initial;
    $("#menu-name").textContent = name;
    $("#menu-email").textContent = user.email || "";
    const sfn = $("#sidebar-footer-name");
    if (sfn) sfn.textContent = displayFirstName(user);
    const sfa = $("#sidebar-footer-avatar");
    if (sfa) sfa.textContent = initial;
    applyTheme(user.theme || "midnight");
    renderThemeGrid(user.theme);
    updatePersonalizedGreetings();
    void refreshDashboardStats();
    void renderDocActivityStrip();
    renderToolSelect();
    refreshLucideIcons();
  }

  function refreshLucideIcons() {
    if (typeof lucide !== "undefined" && lucide.createIcons) {
      lucide.createIcons();
    }
  }

  function renderThemeGrid(active) {
    const grid = $("#theme-grid");
    grid.innerHTML = "";
    (meta.themes || []).forEach((t) => {
      const sw = document.createElement("button");
      sw.type = "button";
      sw.className = "theme-swatch" + (t.id === active ? " active" : "");
      sw.dataset.theme = t.id;
      sw.title = t.label;
      const colors = THEME_SWATCHES[t.id] || ["#333", "#666"];
      sw.style.background = `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`;
      sw.addEventListener("click", async () => {
        applyTheme(t.id);
        const u = API.getUser();
        if (u) {
          u.theme = t.id;
          API.setUser(u);
          try {
            await API.setTheme(t.id);
          } catch {
            /* ignore */
          }
        }
      });
      grid.appendChild(sw);
    });
  }

  async function checkSession() {
    if (!API.getToken() || !API.getUser()) {
      showAuth();
      return;
    }
    try {
      const me = await API.me();
      const merged = { ...API.getUser(), ...me };
      API.setUser(merged);
      showApp(merged);
      await loadThreads();
      await loadDocuments();
      await refreshDocumentLibrary();
    } catch {
      showAuth();
    }
  }

  function formatToolAnswer(text, action) {
    let raw = (text || "").trim().replace(/\s*\[[^\]]+\]\s*/g, " ");
    if (action === "bullet_points") {
      if (!raw.includes("\n") && raw.includes("•")) raw = raw.replace(/\s*•\s*/g, "\n• ");
      if (!raw.includes("\n") && /\s\*\s/.test(raw)) raw = raw.replace(/\s+\*\s+/g, "\n• ");
      const lines = raw
        .split(/\n+/)
        .map((l) => l.replace(/^\s*[•*\-]\s*/, "").replace(/\*{2,3}/g, "").trim())
        .filter(Boolean);
      if (lines.length) {
        return (
          "<ul class='tool-bullets'>" +
          lines.map((l) => `<li>${escapeHtml(l)}</li>`).join("") +
          "</ul>"
        );
      }
    }
    return escapeHtml(raw.replace(/\*{2,3}/g, "")).replace(/\n/g, "<br>");
  }

  function renderWhyAnswer(explanation, container) {
    if (!explanation?.pages?.length) return;
    const box = document.createElement("details");
    box.className = "why-answer";
    const summary = document.createElement("summary");
    summary.textContent = "Why this answer?";
    box.appendChild(summary);
    const intro = document.createElement("p");
    intro.className = "why-answer-intro muted";
    intro.textContent = explanation.why_answer || "";
    box.appendChild(intro);
    const list = document.createElement("div");
    list.className = "why-answer-pages";
    explanation.pages.forEach((p) => {
      const card = document.createElement("div");
      card.className = "why-page-card";
      const sc = p.scores || {};
      card.innerHTML = `
        <div class="why-page-head">
          <strong>${escapeHtml(p.title)}</strong>
          <span class="why-score">score ${(sc.composite ?? 0).toFixed(2)}</span>
        </div>
        <div class="why-scores">
          <span>Keyword ${(sc.keyword_overlap ?? 0).toFixed(2)}</span>
          <span>Semantic ${(sc.semantic_relevance ?? 0).toFixed(2)}</span>
          <span>Hierarchy ${(sc.hierarchy_relevance ?? 0).toFixed(2)}</span>
        </div>
        <p class="why-traversal muted">${escapeHtml(p.traversal_logic || "")}</p>`;
      list.appendChild(card);
    });
    box.appendChild(list);
    const whyText = explanationSpeechText(explanation);
    if (whyText) {
      attachListen(box, () => whyText, "why-tts-bar");
    }
    container.appendChild(box);
  }

  function splitSourcesBlock(raw) {
    const t = (raw || "").trim();
    const re = /\n\s*(?:Source\(s\)?:|Sources?:)\s*(?:\n|$)/i;
    const idx = t.search(re);
    if (idx < 0) return { body: t, sourcesText: "" };
    return {
      body: t.slice(0, idx).trim(),
      sourcesText: t.slice(idx).replace(re, "").trim(),
    };
  }

  /** @param {string} text */
  function formatAssistantContentHtml(text) {
    const lines = (text || "").split("\n");
    let html = "";
    let inList = false;
    for (const line of lines) {
      const bullet = line.match(/^\s*[•\-\*]\s+(.*)$/);
      if (bullet) {
        if (!inList) {
          html += "<ul>";
          inList = true;
        }
        html += `<li>${escapeHtml(bullet[1])}</li>`;
      } else {
        if (inList) {
          html += "</ul>";
          inList = false;
        }
        const trimmed = line.trim();
        if (trimmed) html += `<p>${escapeHtml(trimmed)}</p>`;
      }
    }
    if (inList) html += "</ul>";
    return html || `<p>${escapeHtml(text || "")}</p>`;
  }

  function appendAssistantActions(bubble, rawText) {
    const bar = document.createElement("div");
    bar.className = "msg-assistant-actions";
    const mk = (label, onClick) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "msg-action-btn";
      b.textContent = label;
      b.addEventListener("click", onClick);
      return b;
    };
    bar.appendChild(
      mk("Copy", () => {
        const t = (rawText || "").replace(/\s*\[[^\]]+\]\s*/g, " ").trim();
        void navigator.clipboard?.writeText(t).then(() => toast("Copied to clipboard"));
      }),
    );
    bar.appendChild(
      mk("Explain", () => {
        const q = $("#chat-question");
        if (q) {
          q.value = "Explain the last answer in simpler terms, step by step.";
          q.focus();
        }
      }),
    );
    bar.appendChild(
      mk("Summarize", () => {
        const q = $("#chat-question");
        if (q) {
          q.value = "Summarize the last answer as 5 crisp bullets.";
          q.focus();
        }
      }),
    );
    bubble.appendChild(bar);
  }

  function renderMessage(role, content, explanation = null) {
    const area = $("#chat-messages");
    const div = document.createElement("div");
    if (role === "thinking") {
      div.className = "msg msg-thinking";
      div.innerHTML = 'Thinking<span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span>';
      div.id = "thinking-msg";
      area.appendChild(div);
      area.scrollTop = area.scrollHeight;
      return div;
    }
    const thinking = $("#thinking-msg");
    if (thinking) thinking.remove();

    div.className = role === "user" ? "msg msg-user" : "msg msg-assistant";
    const clean = (content || "").replace(/\s*\[[^\]]+\]\s*/g, " ");
    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    if (role === "assistant") {
      const { body, sourcesText } = splitSourcesBlock(clean.trim());
      bubble.innerHTML = `<div class="msg-body-structured">${formatAssistantContentHtml(body)}</div>`;
      if (sourcesText) {
        const lines = sourcesText
          .split("\n")
          .map((l) => l.trim())
          .filter(Boolean);
        const sb = document.createElement("div");
        sb.className = "msg-sources-block";
        const h = document.createElement("h4");
        h.textContent = "Source(s)";
        sb.appendChild(h);
        lines.forEach((line) => {
          const span = document.createElement("span");
          span.className = "msg-source-link";
          span.textContent = line;
          sb.appendChild(span);
        });
        bubble.appendChild(sb);
      }
      if (explanation) renderWhyAnswer(explanation, bubble);
      appendAssistantActions(bubble, clean);
    } else {
      bubble.innerHTML = escapeHtml(clean).replace(/\n/g, "<br>");
    }
    div.appendChild(bubble);
    attachListen(div, () => speechText(clean), "msg-tts-bar");
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
    return div;
  }

  function renderThreadMessages(messages, thread = null) {
    const area = $("#chat-messages");
    area.innerHTML = "";
    if (!messages?.length) {
      area.innerHTML = buildChatWelcome();
      return;
    }
    const um = messages.find((m) => m.role === "user");
    const titleSrc = um?.content || thread?.title || "Conversation";
    const title =
      typeof titleSrc === "string"
        ? titleSrc.replace(/\s*\[[^\]]+\]\s*/g, " ").trim().slice(0, 140)
        : "Conversation";
    const whenRaw = thread?.updated || thread?.created || "";
    const when = relativeTime(whenRaw) || "";

    const top = document.createElement("div");
    top.className = "msg-thread-topbar";
    top.innerHTML = `
      <div>
        <p class="msg-thread-title">${escapeHtml(title)}</p>
        <span class="msg-thread-meta">${escapeHtml(when)}</span>
      </div>
      <div class="msg-thread-actions">
        <button type="button" class="thr-act" title="Share" aria-label="Share conversation"><i data-lucide="share-2"></i></button>
        <button type="button" class="thr-act" title="Favorite" aria-label="Favorite conversation"><i data-lucide="star"></i></button>
        <button type="button" class="thr-act thr-close" title="Close" aria-label="Close and start new chat"><i data-lucide="x"></i></button>
      </div>`;
    const [bShare, bFav, bClose] = top.querySelectorAll(".thr-act");
    bShare?.addEventListener("click", () => toast("Sharing will copy thread metadata soon."));
    bFav?.addEventListener("click", () => toast("Marked as favorite in this workspace."));
    bClose?.addEventListener("click", () => void newChat());
    area.appendChild(top);

    messages.forEach((m) => {
      if (m.role === "user") renderMessage("user", m.content);
      else renderMessage("assistant", m.content);
    });
    refreshLucideIcons();
  }

  async function deleteThread(id, title) {
    const label = (title || "this chat").slice(0, 60);
    if (!confirm(`Delete "${label}"? This cannot be undone.`)) return;
    try {
      await API.deleteChat(id);
      historyCache = null;
      if (currentThreadId === id) {
        currentThreadId = null;
        await newChat();
      } else {
        await loadThreads();
      }
      toast("Chat deleted");
      void refreshDashboardStats();
    } catch (err) {
      toast(err.message);
    }
  }

  async function loadThreads() {
    const { threads } = await API.listChats();
    const list = $("#thread-list");
    list.innerHTML = "";
    threads.forEach((t) => {
      const row = document.createElement("div");
      row.className = "thread-row" + (t.id === currentThreadId ? " active" : "");

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "thread-item";
      const titleEl = document.createElement("span");
      titleEl.className = "thread-item-title";
      titleEl.textContent = t.title || "New chat";
      btn.appendChild(titleEl);
      const metaEl = document.createElement("span");
      metaEl.className = "thread-item-meta";
      metaEl.textContent = relativeTime(t.updated) || "";
      btn.appendChild(metaEl);
      btn.title = t.title || "New chat";
      btn.addEventListener("click", () => openThread(t.id));

      const del = document.createElement("button");
      del.type = "button";
      del.className = "thread-delete history-delete";
      del.setAttribute("aria-label", "Delete chat");
      del.innerHTML = TRASH_ICON;
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteThread(t.id, t.title);
      });

      row.appendChild(btn);
      row.appendChild(del);
      list.appendChild(row);
    });
  }

  async function openThread(id) {
    currentThreadId = id;
    await loadThreads();
    const { thread } = await API.getChat(id);
    renderThreadMessages(thread.messages || [], thread);
    navigate("chat", false);
  }

  async function newChat() {
    const { thread } = await API.createChat();
    currentThreadId = thread.id;
    $("#chat-messages").innerHTML = buildChatWelcome();
    await loadThreads();
    navigate("chat", false);
  }

  function closeSidebarMobile() {
    $("#app-shell")?.classList.remove("sidebar-open");
    $("#sidebar-backdrop")?.classList.add("hidden");
  }

  function navigate(page, updateNav = true) {
    if (updateNav) {
      $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
    }
    $$(".page").forEach((p) => p.classList.remove("active"));
    $(`#page-${page}`)?.classList.add("active");
    const titles = {
      chat: "Chat",
      documents: "Documents",
      notebook: "Notebook",
      tools: "Tools",
      compare: "Compare documents",
      notes: "AI Notes",
      "knowledge-map": "Knowledge Map",
      timeline: "Timeline",
    };
    $("#page-title").textContent = titles[page] || page;
    closeSidebarMobile();
    if (page === "documents") loadDocuments();
    if (page === "notebook") {
      refreshDocumentLibrary();
      loadNotebook();
    }
    if (page === "tools") {
      refreshDocumentLibrary();
      renderToolSelect();
      loadToolHistory();
    }
    if (page === "compare") loadCompareSources();
    if (page === "notes") refreshDocumentLibrary();
    if (page === "knowledge-map") refreshDocumentLibrary();
    if (page === "timeline") refreshDocumentLibrary();
    if (typeof TTSService !== "undefined") TTSService.stop();
    void refreshDashboardStats();
  }

  let lastNotesMarkdown = "";

  function getActiveSource() {
    return localStorage.getItem(ACTIVE_SOURCE_KEY) || "";
  }

  function setActiveSource(value, skipSelectId = null) {
    const v = value || "";
    if (v) localStorage.setItem(ACTIVE_SOURCE_KEY, v);
    else localStorage.removeItem(ACTIVE_SOURCE_KEY);
    DOCUMENT_SELECTS.forEach(({ id }) => {
      if (id === skipSelectId) return;
      const sel = $(`#${id}`);
      if (!sel) return;
      if (v && [...sel.options].some((o) => o.value === v)) sel.value = v;
      else if (!sel.dataset.noEmpty) sel.value = "";
    });
  }

  async function refreshDocumentLibrary() {
    try {
      const { sources } = await API.listDocuments();
      const saved = getActiveSource();
      DOCUMENT_SELECTS.forEach(({ id, emptyLabel, noEmpty }) => {
        const sel = $(`#${id}`);
        if (!sel) return;
        const cur = sel.value;
        sel.innerHTML = "";
        if (!noEmpty) {
          const empty = document.createElement("option");
          empty.value = "";
          empty.textContent = emptyLabel;
          sel.appendChild(empty);
        }
        sources.forEach((s) => {
          const o = document.createElement("option");
          o.value = s;
          o.textContent = s;
          sel.appendChild(o);
        });
        if (saved && sources.includes(saved)) sel.value = saved;
        else if (cur && sources.includes(cur)) sel.value = cur;
        else if (!noEmpty) sel.value = "";
        else if (sources.length) sel.value = sources[0];
        if (noEmpty) sel.dataset.noEmpty = "1";
      });
      ["a", "b"].forEach((slot) => {
        const sel = $(`#compare-source-${slot}`);
        if (!sel) return;
        const cur = sel.value;
        sel.innerHTML = '<option value="">Select a document…</option>';
        sources.forEach((src) => {
          const opt = document.createElement("option");
          opt.value = src;
          opt.textContent = src;
          sel.appendChild(opt);
        });
        if (saved && sources.includes(saved) && !cur) sel.value = saved;
        else if (cur && sources.includes(cur)) sel.value = cur;
      });
      if (!window._docSelectBound) {
        window._docSelectBound = true;
        DOCUMENT_SELECTS.forEach(({ id }) => {
          $(`#${id}`)?.addEventListener("change", (e) => {
            setActiveSource(e.target.value, id);
          });
        });
      }
      return sources;
    } catch {
      return [];
    }
  }

  function loadKmSources() {
    return refreshDocumentLibrary();
  }

  function loadTimelineSources() {
    return refreshDocumentLibrary();
  }

  function setupNotes() {
    $("#btn-notes-generate")?.addEventListener("click", async () => {
      const source = $("#notes-source")?.value;
      if (!source) {
        toast("Select a document");
        return;
      }
      const scope = $("#notes-scope")?.value || "chapter";
      const style = $("#notes-style")?.value || "bullets";
      const focus = $("#notes-focus")?.value?.trim() || "";
      $("#notes-status").textContent = "Generating notes…";
      $("#btn-notes-generate").disabled = true;
      try {
        const res = await API.generateNotes(source, scope, style, focus);
        lastNotesMarkdown = res.markdown || "";
        $("#notes-markdown").textContent = lastNotesMarkdown;
        $("#notes-output")?.classList.remove("hidden");
        $("#btn-notes-export-pdf").disabled = !lastNotesMarkdown;
        $("#btn-notes-export-docx").disabled = !lastNotesMarkdown;
        $("#notes-status").textContent = `Generated ${res.sections?.length || 0} section(s).`;
        const notesMount = $("#notes-tts-mount");
        if (notesMount && typeof TTSService !== "undefined") {
          notesMount.innerHTML = "";
          notesMount.appendChild(TTSService.createListenButton(() => lastNotesMarkdown));
        }
      } catch (err) {
        $("#notes-status").textContent = err.message;
        toast(err.message);
      } finally {
        $("#btn-notes-generate").disabled = false;
      }
    });

    async function downloadNotes(format) {
      const source = $("#notes-source")?.value;
      if (!source) {
        toast("Select a document");
        return;
      }
      const scope = $("#notes-scope")?.value || "chapter";
      const style = $("#notes-style")?.value || "bullets";
      const focus = $("#notes-focus")?.value?.trim() || "";
      $("#notes-status").textContent = `Exporting ${format.toUpperCase()}…`;
      try {
        const blob = await API.exportNotes(source, scope, style, focus, format);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${source.replace(/[^\w.-]+/g, "_")}_notes.${format}`;
        a.click();
        URL.revokeObjectURL(url);
        $("#notes-status").textContent = "Export complete.";
      } catch (err) {
        $("#notes-status").textContent = err.message;
        toast(err.message);
      }
    }

    $("#btn-notes-export-pdf")?.addEventListener("click", () => downloadNotes("pdf"));
    $("#btn-notes-export-docx")?.addEventListener("click", () => downloadNotes("docx"));
  }

  const KM_KIND_COLORS = {
    document: { bg: "#6366f1", border: "#818cf8" },
    section: { bg: "#8b5cf6", border: "#a78bfa" },
    chapter: { bg: "#a78bfa", border: "#c4b5fd" },
    page: { bg: "#94a3b8", border: "#cbd5e1" },
    node: { bg: "#64748b", border: "#94a3b8" },
  };

  let kmNetwork = null;
  let kmMinimap = null;
  let kmNodesDs = null;
  let kmEdgesDs = null;
  let kmNodeById = {};
  let kmEdgeMeta = {};
  let kmRaw = null;
  let kmSelectedId = null;
  let kmPathPulseTimer = null;

  function setKmControlsEnabled(on) {
    const ids = [
      "#km-filter-search",
      "#km-toolbar-search",
      "#km-layout",
      "#km-physics",
      "#km-show-parent",
      "#km-show-related",
      "#km-focus-mode",
      "#km-zoom-in",
      "#km-zoom-out",
      "#km-fit",
      "#km-toggle-minimap",
      "#km-fullscreen",
    ];
    ids.forEach((sel) => {
      const el = $(sel);
      if (el) el.disabled = !on;
    });
    $$("#km-kind-filters input[type=checkbox]").forEach((cb) => {
      cb.disabled = !on;
    });
    const kf = $("#km-toolbar-filter");
    if (kf) kf.disabled = !on;
  }

  function showKmSkeleton(show) {
    $("#km-graph-skeleton")?.classList.toggle("hidden", !show);
    if (show) $("#km-graph")?.classList.add("km-graph-loading");
    else $("#km-graph")?.classList.remove("km-graph-loading");
  }

  function kmZoomBy(factor) {
    if (!kmNetwork) return;
    const scale = Math.max(0.15, Math.min(kmNetwork.getScale() * factor, 4));
    const position = kmNetwork.getViewPosition();
    kmNetwork.moveTo({
      position,
      scale,
      animation: { duration: 280, easingFunction: "easeInOutQuad" },
    });
  }

  function updateKmStats(data) {
    const st = data?.stats || {};
    const set = (id, v) => {
      const el = $(id);
      if (el) el.textContent = v ?? "—";
    };
    set("#km-stat-nodes", st.node_count);
    set("#km-stat-edges", st.edge_count);
    set("#km-stat-parent", st.hierarchy_edges);
    set("#km-stat-related", st.related_edges);
    const note = $("#km-stats-note");
    if (note) {
      note.textContent = data?.truncated
        ? "Large graph — showing a representative sample for performance."
        : data
          ? `${(data.sources || []).length} document(s) in view.`
          : "";
    }
  }

  function kmTooltip(node) {
    return `${node.title}\n${(node.summary || "").slice(0, 220)}`;
  }

  function kmVisNode(n, state = {}) {
    const kind = n.kind || "node";
    const palette = KM_KIND_COLORS[kind] || KM_KIND_COLORS.node;
    const hidden = state.hidden ?? false;
    const dim = state.dim ?? false;
    const highlight = state.highlight ?? false;
    const onPath = state.onPath ?? false;
    const base = {
      id: n.id,
      label: hidden ? "" : n.label,
      title: kmTooltip(n),
      hidden,
      opacity: dim ? 0.12 : 1,
      color: {
        background: palette.bg,
        border: highlight ? "#f5f3ff" : onPath ? palette.border : "#1e293b",
        highlight: { background: palette.border, border: "#fff" },
      },
      font: { color: "#e2e8f0", size: kind === "document" ? 13 : 11 },
      borderWidth: highlight ? 3 : onPath ? 2 : 1,
      shadow: highlight
        ? { enabled: true, color: "rgba(167,139,250,0.55)", size: 16, x: 0, y: 0 }
        : false,
    };
    if (kind === "document") return { ...base, shape: "diamond", size: 26 };
    if (kind === "chapter") return { ...base, shape: "ellipse", size: 22 };
    if (kind === "section") return { ...base, shape: "box", margin: 10, size: 18 };
    if (kind === "page") return { ...base, shape: "dot", size: 14 };
    return { ...base, shape: "box", margin: 8, size: 16 };
  }

  function getKmActiveKinds() {
    const kinds = new Set();
    $$("#km-kind-filters input:checked").forEach((cb) => kinds.add(cb.value));
    return kinds;
  }

  function getKmSearchQuery() {
    return ($("#km-filter-search")?.value || "").trim().toLowerCase();
  }

  function nodeMatchesFilters(n) {
    if (!getKmActiveKinds().has(n.kind || "node")) return false;
    const q = getKmSearchQuery();
    if (!q) return true;
    const hay = `${n.title} ${n.summary} ${n.label} ${n.source}`.toLowerCase();
    return hay.includes(q);
  }

  function getRetrievalPath(nodeId) {
    const path = [];
    let cur = nodeId;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
      seen.add(cur);
      path.push(cur);
      const n = kmNodeById[cur];
      cur = n?.parent_id && kmNodeById[n.parent_id] ? n.parent_id : null;
    }
    return path;
  }

  function getRelatedNodeIds(nodeId) {
    const related = new Set();
    Object.values(kmEdgeMeta).forEach((e) => {
      if (e.type !== "related") return;
      if (e.from === nodeId) related.add(e.to);
      if (e.to === nodeId) related.add(e.from);
    });
    return related;
  }

  function applyKmGraphStyles() {
    if (!kmNodesDs || !kmEdgesDs) return;
    const focusMode = $("#km-focus-mode")?.checked;
    const pathSet = kmSelectedId ? new Set(getRetrievalPath(kmSelectedId)) : new Set();
    const relatedSet = kmSelectedId ? getRelatedNodeIds(kmSelectedId) : new Set();
    const showParent = $("#km-show-parent")?.checked !== false;
    const showRelated = $("#km-show-related")?.checked !== false;

    (kmRaw?.nodes || []).forEach((n) => {
      if (!nodeMatchesFilters(n)) {
        kmNodesDs.update({ id: n.id, hidden: true });
        return;
      }
      const isFocus = n.id === kmSelectedId;
      const onPath = pathSet.has(n.id);
      const isRelated = relatedSet.has(n.id);
      const dim =
        focusMode &&
        kmSelectedId &&
        !isFocus &&
        !onPath &&
        !isRelated;
      kmNodesDs.update(
        kmVisNode(n, {
          hidden: false,
          dim,
          highlight: isFocus,
          onPath: onPath && !isFocus,
        }),
      );
    });

    Object.entries(kmEdgeMeta).forEach(([id, e]) => {
      const isParent = e.type === "parent";
      if ((isParent && !showParent) || (!isParent && !showRelated)) {
        kmEdgesDs.update({ id, hidden: true });
        return;
      }
      const onPath =
        kmSelectedId &&
        pathSet.has(e.from) &&
        pathSet.has(e.to) &&
        isParent;
      const isRel =
        !isParent &&
        kmSelectedId &&
        (e.from === kmSelectedId || e.to === kmSelectedId);
      const dim =
        focusMode &&
        kmSelectedId &&
        !onPath &&
        !isRel;
      kmEdgesDs.update({
        id,
        hidden: false,
        width: onPath ? 3 : isRel ? 2 : isParent ? 2 : 1,
        color: {
          color: onPath
            ? "#c4b5fd"
            : isRel
              ? "#a78bfa"
              : isParent
                ? "#64748b"
                : "#7c6bb0",
          opacity: dim ? 0.08 : onPath ? 1 : 0.85,
        },
        dashes: isParent ? false : [6, 4],
        smooth: { type: "dynamic" },
      });
    });
    kmNetwork?.redraw();
    const mini = $("#km-minimap");
    if (mini && !mini.classList.contains("hidden") && kmRaw) initKmMinimap();
  }

  function startKmPathPulse() {
    stopKmPathPulse();
    if (!kmSelectedId) return;
    let on = true;
    kmPathPulseTimer = window.setInterval(() => {
      if (!kmEdgesDs || !kmSelectedId) return;
      const pathSet = new Set(getRetrievalPath(kmSelectedId));
      Object.entries(kmEdgeMeta).forEach(([id, e]) => {
        if (e.type !== "parent") return;
        if (!pathSet.has(e.from) || !pathSet.has(e.to)) return;
        kmEdgesDs.update({
          id,
          color: { color: on ? "#e9d5ff" : "#a78bfa", opacity: 1 },
        });
      });
      on = !on;
    }, 520);
  }

  function stopKmPathPulse() {
    if (kmPathPulseTimer) {
      clearInterval(kmPathPulseTimer);
      kmPathPulseTimer = null;
    }
  }

  function showKmDetail(node) {
    const panel = $("#km-detail");
    if (!node || !panel) return;
    panel.classList.remove("hidden");
    panel.classList.remove("km-panel-enter");
    void panel.offsetWidth;
    panel.classList.add("km-panel-enter");
    $("#km-detail-title").textContent = node.title || node.label;
    const badge = $("#km-detail-kind");
    const kindLabel =
      node.kind === "node" ? "Topic" : (node.kind || "node").charAt(0).toUpperCase() + (node.kind || "node").slice(1);
    badge.textContent = kindLabel;
    badge.className = `summary-kind-badge kind-${node.kind || "node"}`;
    $("#km-detail-summary").textContent = node.summary || "—";
    $("#km-detail-source").textContent = `${node.source} · level ${node.level}`;
    const related = getRelatedNodeIds(node.id);
    const relEl = $("#km-detail-related");
    if (relEl) {
      relEl.textContent = related.size
        ? `Related topics: ${related.size} connected node${related.size === 1 ? "" : "s"}`
        : "No related topic edges for this node.";
    }
    const path = getRetrievalPath(node.id)
      .map((id) => kmNodeById[id]?.title || id)
      .reverse();
    const pathEl = $("#km-detail-path");
    if (pathEl) {
      pathEl.textContent = path.length > 1 ? `Retrieval path: ${path.join(" → ")}` : "Root node (document top-level).";
    }
    const kmMount = $("#km-tts-mount");
    if (kmMount) {
      kmMount.innerHTML = "";
      const text = speechText(
        [
          node.title || node.label,
          node.summary,
          $("#km-detail-source")?.textContent,
          $("#km-detail-related")?.textContent,
          pathEl?.textContent,
        ]
          .filter(Boolean)
          .join(". "),
      );
      if (text) {
        kmMount.appendChild(TTSService.createListenButton(() => text));
      }
    }
  }

  function selectKmNode(nodeId) {
    kmSelectedId = nodeId || null;
    const node = nodeId ? kmNodeById[nodeId] : null;
    if (node) showKmDetail(node);
    else $("#km-detail")?.classList.add("hidden");
    applyKmGraphStyles();
    startKmPathPulse();
    if (kmNetwork && nodeId) {
      kmNetwork.selectNodes([nodeId]);
      kmNetwork.focus(nodeId, { scale: 1.15, animation: { duration: 450, easingFunction: "easeInOutQuad" } });
    }
  }

  function buildKmNetworkOptions() {
    const hierarchical = ($("#km-layout")?.value || "hierarchical") === "hierarchical";
    const physicsOn = $("#km-physics")?.checked !== false;
    return {
      layout: {
        hierarchical: hierarchical
          ? {
              enabled: true,
              direction: "UD",
              sortMethod: "directed",
              levelSeparation: 100,
              nodeSpacing: 130,
            }
          : { enabled: false },
      },
      physics: hierarchical
        ? {
            enabled: physicsOn,
            stabilization: { iterations: 120 },
            hierarchicalRepulsion: { nodeDistance: 150 },
          }
        : {
            enabled: physicsOn,
            stabilization: { iterations: 200 },
            barnesHut: { gravitationalConstant: -4200, springLength: 140, damping: 0.35 },
          },
      interaction: {
        hover: true,
        tooltipDelay: 120,
        navigationButtons: false,
        keyboard: true,
        zoomView: true,
        dragView: true,
      },
      edges: {
        smooth: { type: "continuous", roundness: 0.35 },
        color: { inherit: false },
      },
      nodes: { font: { face: "Plus Jakarta Sans, system-ui, sans-serif" } },
    };
  }

  function initKmMinimap() {
    const el = $("#km-minimap");
    if (!el || typeof vis === "undefined" || !kmNodesDs || !kmEdgesDs) return;
    if (kmMinimap) {
      kmMinimap.destroy();
      kmMinimap = null;
    }
    const nodes = kmNodesDs.get({ filter: (n) => !n.hidden });
    const edges = kmEdgesDs.get({ filter: (e) => !e.hidden });
    kmMinimap = new vis.Network(
      el,
      {
        nodes: new vis.DataSet(nodes.map((n) => ({ ...n, label: "", font: { size: 0 } }))),
        edges: new vis.DataSet(edges.map((e) => ({ ...e, width: 0.5 }))),
      },
      {
        physics: false,
        layout: { hierarchical: { enabled: true, direction: "UD", levelSeparation: 20, nodeSpacing: 18 } },
        interaction: { dragView: false, zoomView: false, dragNodes: false, selectable: false },
      },
    );
    kmMinimap.fit({ animation: false });
    kmMinimap.on("click", (params) => {
      if (params.nodes.length && kmNetwork) {
        selectKmNode(params.nodes[0]);
      } else if (kmNetwork) {
        kmNetwork.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });
      }
    });
  }

  function renderKmNetwork(data) {
    const container = $("#km-graph");
    if (!container || typeof vis === "undefined") return;

    kmNodeById = {};
    kmEdgeMeta = {};
    (data.nodes || []).forEach((n) => {
      kmNodeById[n.id] = n;
    });
    (data.edges || []).forEach((e) => {
      kmEdgeMeta[e.id] = { type: e.type, from: e.from, to: e.to };
    });

    const visNodes = (data.nodes || []).map((n) => kmVisNode(n));
    const visEdges = (data.edges || []).map((e) => ({
      id: e.id,
      from: e.from,
      to: e.to,
      dashes: e.type === "related" ? [6, 4] : false,
      arrows: e.type === "parent" ? { to: { enabled: true, scaleFactor: 0.45 } } : undefined,
      color: {
        color: e.type === "parent" ? "#64748b" : "#7c6bb0",
        opacity: 0.85,
      },
      width: e.type === "parent" ? 2 : 1,
      smooth: { type: "dynamic" },
      title: e.label || e.type,
    }));

    kmNodesDs = new vis.DataSet(visNodes);
    kmEdgesDs = new vis.DataSet(visEdges);

    if (kmNetwork) kmNetwork.destroy();
    kmNetwork = new vis.Network(container, { nodes: kmNodesDs, edges: kmEdgesDs }, buildKmNetworkOptions());

    kmNetwork.on("click", (params) => {
      if (params.nodes.length) selectKmNode(params.nodes[0]);
      else selectKmNode(null);
    });
    kmNetwork.on("hoverNode", () => {
      container.classList.add("km-graph-hover");
    });
    kmNetwork.on("blurNode", () => {
      container.classList.remove("km-graph-hover");
    });
    kmNetwork.once("stabilizationIterationsDone", () => {
      if ($("#km-minimap") && !$("#km-minimap").classList.contains("hidden")) initKmMinimap();
    });

    kmNetwork.fit({ animation: { duration: 500, easingFunction: "easeInOutQuad" } });
    applyKmGraphStyles();
  }

  async function loadKnowledgeMap() {
    const source = $("#km-source")?.value || "";
    const status = $("#km-status");
    status.textContent = "Building knowledge map…";
    $("#btn-km-load").disabled = true;
    setKmControlsEnabled(false);
    showKmSkeleton(true);
    $("#km-detail")?.classList.add("hidden");
    kmSelectedId = null;
    stopKmPathPulse();

    try {
      const data = await API.knowledgeMap(source);
      kmRaw = data;
      updateKmStats(data);
      status.textContent = data.truncated
        ? "Large document — sampled nodes shown. Use search & focus to explore."
        : "Map ready — drag, scroll, and click nodes.";

      if (typeof vis === "undefined") {
        status.textContent = "Graph library failed to load. Check your network connection.";
        $("#km-empty")?.classList.remove("hidden");
        return;
      }

      $("#km-empty")?.classList.add("hidden");
      renderKmNetwork(data);
      setKmControlsEnabled(true);
      const tb = $("#km-toolbar-search");
      const fi = $("#km-filter-search");
      if (tb && fi) tb.value = fi.value || "";
      if ((data.nodes || []).length === 0) {
        status.textContent = "No nodes to display — index a document with dated or structured content first.";
      }
    } catch (err) {
      kmRaw = null;
      status.textContent = err.message;
      updateKmStats(null);
      if (kmNetwork) {
        kmNetwork.destroy();
        kmNetwork = null;
      }
      $("#km-empty")?.classList.remove("hidden");
      toast(err.message);
    } finally {
      showKmSkeleton(false);
      $("#btn-km-load").disabled = false;
    }
  }

  function setupKnowledgeMap() {
    $("#btn-km-load")?.addEventListener("click", loadKnowledgeMap);
    const syncKmToolbarSearch = () => {
      const inner = $("#km-filter-search");
      const tb = $("#km-toolbar-search");
      if (!inner || !tb) return;
      tb.value = inner.value || "";
    };
    $("#km-toolbar-search")?.addEventListener("input", () => {
      const inner = $("#km-filter-search");
      const tb = $("#km-toolbar-search");
      if (inner && tb) inner.value = tb.value;
      applyKmGraphStyles();
    });
    $("#km-filter-search")?.addEventListener("input", () => {
      syncKmToolbarSearch();
      applyKmGraphStyles();
    });
    $("#km-toolbar-filter")?.addEventListener("change", () => {
      toast("Use the Filters card for node types — quick filter presets ship next.");
    });
    $$("#km-kind-filters input").forEach((cb) => cb.addEventListener("change", () => applyKmGraphStyles()));
    $("#km-show-parent")?.addEventListener("change", () => applyKmGraphStyles());
    $("#km-show-related")?.addEventListener("change", () => applyKmGraphStyles());
    $("#km-focus-mode")?.addEventListener("change", () => applyKmGraphStyles());
    $("#km-layout")?.addEventListener("change", () => {
      if (kmRaw) renderKmNetwork(kmRaw);
    });
    $("#km-physics")?.addEventListener("change", () => {
      if (kmNetwork) kmNetwork.setOptions(buildKmNetworkOptions());
    });
    $("#km-zoom-in")?.addEventListener("click", (e) => {
      e.preventDefault();
      kmZoomBy(1.22);
    });
    $("#km-zoom-out")?.addEventListener("click", (e) => {
      e.preventDefault();
      kmZoomBy(1 / 1.22);
    });
    $("#km-fit")?.addEventListener("click", () => {
      kmNetwork?.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });
    });
    $("#km-toggle-minimap")?.addEventListener("click", () => {
      const el = $("#km-minimap");
      if (!el) return;
      el.classList.toggle("hidden");
      if (!el.classList.contains("hidden") && kmRaw) initKmMinimap();
    });
    $("#km-fullscreen")?.addEventListener("click", () => {
      const wrap = $("#km-canvas-wrap");
      if (!wrap) return;
      if (!document.fullscreenElement) wrap.requestFullscreen?.();
      else document.exitFullscreen?.();
    });
    $("#km-detail-close")?.addEventListener("click", () => selectKmNode(null));
  }
  let timelineCache = null;
  let timelineZoomPct = 100;

  function setTimelineFiltersEnabled(on) {
    ["#tl-filter-search", "#tl-filter-year", "#tl-filter-year-toolbar", "#tl-filter-doc", "#tl-zoom", "#tl-zoom-in", "#tl-zoom-out", "#tl-expand-all", "#tl-collapse-all"].forEach(
      (sel) => {
        const el = $(sel);
        if (el) el.disabled = !on;
      },
    );
  }

  function showTimelineSkeleton() {
    const root = $("#timeline-viz");
    if (!root) return;
    const nodes = [1, 2, 3, 4]
      .map(() => '<div class="tl-skel-node"><div class="tl-skel-card"></div></div>')
      .join("");
    root.innerHTML = `
      <div class="tl-skeleton-wrap" aria-busy="true" aria-label="Loading timeline">
        <div class="tl-skel-year"></div>
        ${nodes}
      </div>
    `;
  }

  function populateTimelineFilterOptions(events) {
    const yearSel = $("#tl-filter-year");
    const docSel = $("#tl-filter-doc");
    if (!yearSel || !docSel) return;
    const years = [...new Set(events.map((e) => (e.date_iso || "").slice(0, 4)).filter(Boolean))].sort();
    const sources = [...new Set(events.map((e) => e.source).filter(Boolean))].sort();
    const yCur = yearSel.value;
    const dCur = docSel.value;
    yearSel.innerHTML = '<option value="">All years</option>';
    years.forEach((y) => {
      const o = document.createElement("option");
      o.value = y;
      o.textContent = y;
      yearSel.appendChild(o);
    });
    docSel.innerHTML = '<option value="">All sources</option>';
    sources.forEach((s) => {
      const o = document.createElement("option");
      o.value = s;
      o.textContent = s;
      docSel.appendChild(o);
    });
    if (years.includes(yCur)) yearSel.value = yCur;
    if (sources.includes(dCur)) docSel.value = dCur;

    const yToolbar = $("#tl-filter-year-toolbar");
    if (yToolbar) {
      yToolbar.innerHTML = yearSel.innerHTML;
      yToolbar.value = yearSel.value;
      yToolbar.disabled = yearSel.disabled;
    }
  }

  function getFilteredTimelineEvents() {
    if (!timelineCache?.events) return [];
    const q = ($("#tl-filter-search")?.value || "").trim().toLowerCase();
    const year = $("#tl-filter-year")?.value || "";
    const doc = $("#tl-filter-doc")?.value || "";
    return timelineCache.events.filter((ev) => {
      if (year && !(ev.date_iso || "").startsWith(year)) return false;
      if (doc && ev.source !== doc) return false;
      if (!q) return true;
      const hay = `${ev.title} ${ev.snippet} ${ev.source} ${ev.node_title} ${ev.path}`.toLowerCase();
      return hay.includes(q);
    });
  }

  function applyTimelineZoom() {
    const target = $("#timeline-viz .tl-axis-wrap") || $("#timeline-viz");
    if (target) {
      target.style.transform = `scale(${timelineZoomPct / 100})`;
      target.style.transformOrigin = "top center";
    }
    const label = $("#tl-zoom-label");
    if (label) label.textContent = `${timelineZoomPct}%`;
    const slider = $("#tl-zoom");
    if (slider) slider.value = String(timelineZoomPct);
  }

  function setTimelineZoom(pct) {
    timelineZoomPct = Math.min(125, Math.max(75, pct));
    applyTimelineZoom();
  }

  function changeTimelineZoom(delta) {
    setTimelineZoom(timelineZoomPct + delta);
  }

  async function openTimelineEvent(ev) {
    navigate("documents");
    try {
      await openDocumentOutline(ev.source);
      const btn = $(`.summary-tree-item[data-node-id="${CSS.escape(ev.node_id)}"]`);
      if (btn) {
        btn.scrollIntoView({ behavior: "smooth", block: "nearest" });
        btn.click();
        return;
      }
      const detail = await API.documentNode(ev.source, ev.node_id);
      showSummaryDetail(detail, ev.source);
    } catch {
      toast(`${ev.source} → ${ev.path || ev.node_title || ev.node_id}`);
    }
  }

  function buildTimelineNodeCard(ev, side, index) {
    const article = document.createElement("article");
    article.className = `tl-node tl-node--${side}`;
    article.style.animationDelay = `${Math.min(index * 0.04, 0.35)}s`;
    article.innerHTML = `
      <div class="tl-node-card" tabindex="0" role="button" aria-label="Open ${escapeHtml(ev.title)}">
        <time class="tl-date-pill" datetime="${escapeHtml(ev.date_iso)}">${escapeHtml(ev.date_display)}</time>
        <h5 class="tl-event-title">${escapeHtml(ev.title)}</h5>
        <p class="tl-snippet muted">${escapeHtml(ev.snippet)}</p>
        <p class="tl-meta">
          <span class="tl-source-tag" title="${escapeHtml(ev.source)}">${escapeHtml(ev.source)}</span>
          <span class="tl-node-tag" title="${escapeHtml(ev.path || "")}">${escapeHtml(ev.node_title || ev.node_id)}</span>
          <span class="tl-extract-badge" title="Extraction">${escapeHtml(ev.extraction || "regex")}</span>
        </p>
      </div>
      <div class="tl-node-marker">
        <span class="tl-node-dot" aria-hidden="true"></span>
        <span class="tl-node-connector" aria-hidden="true"></span>
      </div>
    `;
    const card = article.querySelector(".tl-node-card");
    const open = () => openTimelineEvent(ev);
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
    const tlText = speechText(`${ev.title}. ${ev.snippet}. ${ev.date_display}. ${ev.source}`);
    if (tlText) attachListen(article.querySelector(".tl-node-card"), () => tlText, "tl-tts-bar");
    return article;
  }

  function renderTimeline() {
    const root = $("#timeline-viz");
    const countEl = $("#tl-event-count");
    if (!root) return;

    const events = getFilteredTimelineEvents();
    const total = timelineCache?.events?.length || 0;

    if (!timelineCache) {
      root.innerHTML = `
        <div class="tl-empty-state">
          <p class="tl-empty-title">Ready to explore</p>
          <p class="muted">Choose a document and extract a timeline to see connected events here.</p>
        </div>
        <section class="tl-ref-layout tl-ref-muted" aria-label="Timeline visual example">
          <h4>Reference layout sample</h4>
          <div class="tl-ref-year-row">
            <span class="tl-ref-year">2018</span>
            <div class="tl-ref-card">AI research investment began accelerating across industry labs.<span class="tl-ref-src">Source: Trends brief · p.3</span></div>
          </div>
          <div class="tl-ref-year-row">
            <span class="tl-ref-year">2020</span>
            <div class="tl-ref-card">Transformer architectures moved from niche papers into production NLP stacks.<span class="tl-ref-src">Source: Model survey · p.12</span></div>
          </div>
          <div class="tl-ref-year-row">
            <span class="tl-ref-year">2024</span>
            <div class="tl-ref-card">Large language models became the default surface for enterprise knowledge assistants.<span class="tl-ref-src">Source: Market outlook · p.7</span></div>
          </div>
        </section>`;
      if (countEl) countEl.textContent = "No events loaded";
      return;
    }

    if (!total) {
      root.innerHTML = `
        <div class="tl-empty-state">
          <p class="tl-empty-title">No dated events found</p>
          <p class="muted">Try another document or add content with explicit dates (e.g. 2020-06-15, Jan 15, 2020).</p>
        </div>`;
      if (countEl) countEl.textContent = "0 events";
      return;
    }

    if (countEl) {
      countEl.textContent =
        events.length === total
          ? `${total} event${total === 1 ? "" : "s"}`
          : `${events.length} of ${total} events`;
    }

    if (!events.length) {
      root.innerHTML = '<p class="tl-no-results">No events match your filters.</p>';
      return;
    }

    const byYear = {};
    events.forEach((ev) => {
      const y = (ev.date_iso || "").slice(0, 4) || "Unknown";
      if (!byYear[y]) byYear[y] = [];
      byYear[y].push(ev);
    });

    const wrap = document.createElement("div");
    wrap.className = "tl-axis-wrap";
    const axis = document.createElement("div");
    axis.className = "tl-axis";

    Object.keys(byYear)
      .sort()
      .forEach((year) => {
        const block = document.createElement("section");
        block.className = "tl-year-block";
        block.dataset.year = year;

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "tl-year-toggle";
        toggle.setAttribute("aria-expanded", "true");
        toggle.innerHTML = `
          <span class="tl-chevron" aria-hidden="true">▾</span>
          <span>${escapeHtml(year)}</span>
          <span class="tl-year-count">${byYear[year].length} event${byYear[year].length === 1 ? "" : "s"}</span>
        `;
        toggle.addEventListener("click", () => {
          const collapsed = block.classList.toggle("is-collapsed");
          toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        });

        const body = document.createElement("div");
        body.className = "tl-year-body";

        byYear[year].forEach((ev, i) => {
          const side = i % 2 === 0 ? "left" : "right";
          const node = buildTimelineNodeCard(ev, side, i);
          if (i === byYear[year].length - 1) {
            node.querySelector(".tl-node-connector")?.remove();
          }
          body.appendChild(node);
        });

        block.appendChild(toggle);
        block.appendChild(body);
        axis.appendChild(block);
      });

    wrap.appendChild(axis);
    root.innerHTML = "";
    root.appendChild(wrap);
    applyTimelineZoom();
  }

  async function loadTimeline() {
    const source = $("#tl-source")?.value || "";
    const status = $("#tl-status");
    status.textContent = "Extracting timeline…";
    $("#btn-tl-load").disabled = true;
    setTimelineFiltersEnabled(false);
    showTimelineSkeleton();
    try {
      const data = await API.timeline(source);
      timelineCache = data;
      $("#tl-explanation").textContent = data.explanation || "";
      status.textContent = `Extracted ${data.stats?.event_count || 0} event(s) from ${(data.sources || []).length || 0} document(s).`;
      populateTimelineFilterOptions(data.events || []);
      setTimelineFiltersEnabled(true);
      renderTimeline();
    } catch (err) {
      timelineCache = null;
      status.textContent = err.message;
      $("#timeline-viz").innerHTML = `<p class="tl-no-results">${escapeHtml(err.message)}</p>`;
      $("#tl-event-count").textContent = "Extraction failed";
      toast(err.message);
    } finally {
      $("#btn-tl-load").disabled = false;
    }
  }

  function setupTimeline() {
    $("#btn-tl-load")?.addEventListener("click", loadTimeline);
    $("#tl-filter-search")?.addEventListener("input", () => renderTimeline());
    $("#tl-filter-year-toolbar")?.addEventListener("change", (e) => {
      const sel = $("#tl-filter-year");
      if (sel) sel.value = e.target.value || "";
      renderTimeline();
    });
    $("#tl-filter-year")?.addEventListener("change", (e) => {
      const tb = $("#tl-filter-year-toolbar");
      if (tb) tb.value = e.target.value || "";
      renderTimeline();
    });
    $("#tl-filter-doc")?.addEventListener("change", () => renderTimeline());
    $("#tl-zoom")?.addEventListener("input", (e) => setTimelineZoom(Number(e.target.value)));
    $("#tl-zoom-in")?.addEventListener("click", (e) => {
      e.preventDefault();
      changeTimelineZoom(5);
    });
    $("#tl-zoom-out")?.addEventListener("click", (e) => {
      e.preventDefault();
      changeTimelineZoom(-5);
    });
    $("#tl-expand-all")?.addEventListener("click", () => {
      $$("#timeline-viz .tl-year-block").forEach((b) => {
        b.classList.remove("is-collapsed");
        b.querySelector(".tl-year-toggle")?.setAttribute("aria-expanded", "true");
      });
    });
    $("#tl-collapse-all")?.addEventListener("click", () => {
      $$("#timeline-viz .tl-year-block").forEach((b) => {
        b.classList.add("is-collapsed");
        b.querySelector(".tl-year-toggle")?.setAttribute("aria-expanded", "false");
      });
    });
  }
  function fillList(el, items) {
    el.innerHTML = "";
    (items || []).forEach((t) => {
      const li = document.createElement("li");
      li.textContent = t;
      el.appendChild(li);
    });
    if (!items?.length) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "None listed.";
      el.appendChild(li);
    }
  }

  function attachCompareSectionListen(sectionEl, items) {
    if (!sectionEl) return;
    sectionEl.querySelector(".section-tts-bar")?.remove();
    const text = speechText((items || []).join(". "));
    if (text) attachListen(sectionEl, () => text, "section-tts-bar");
  }

  async function loadCompareSources() {
    await refreshDocumentLibrary();
  }

  function compareStatusLabel(status) {
    const map = {
      similar: "Similar",
      changed: "Changed",
      only_left: "Only in A",
      only_right: "Only in B",
    };
    return map[status] || status;
  }

  function calcCompareSimilarity(data) {
    const rows = data?.rows || [];
    if (!rows.length) return 0;
    const values = rows.map((r) => Number(r.similarity) || 0);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    return Math.max(0, Math.min(1, avg));
  }

  function renderSimilarityRing(container, value, label = "0%") {
    if (!container) return;
    container.innerHTML = "";
    const ring = document.createElement("span");
    ring.className = "compare-sim-ring";
    ring.style.setProperty("--p", String(value));
    ring.setAttribute("data-label", label);
    container.appendChild(ring);
  }

  function renderCompareResults(data) {
    lastCompareReport = data.report_markdown || "";
    $("#compare-results")?.classList.remove("hidden");
    fillList($("#compare-similarities"), data.similarities);
    fillList($("#compare-differences"), data.differences);
    fillList($("#compare-missing-b"), data.missing_in_b);
    fillList($("#compare-missing-a"), data.missing_in_a);
    fillList($("#compare-changed"), data.changed_sections);
    attachCompareSectionListen($("#compare-similarities")?.closest(".compare-summary-card"), data.similarities);
    attachCompareSectionListen($("#compare-differences")?.closest(".compare-summary-card"), data.differences);
    attachCompareSectionListen($("#compare-missing-b")?.closest(".compare-insight"), data.missing_in_b);
    attachCompareSectionListen($("#compare-missing-a")?.closest(".compare-insight"), data.missing_in_a);
    attachCompareSectionListen($("#compare-changed")?.closest(".compare-insight"), data.changed_sections);
    const compareMount = $("#compare-tts-mount");
    if (compareMount) {
      compareMount.innerHTML = "";
      const reportText = speechText(lastCompareReport);
      if (reportText) compareMount.appendChild(TTSService.createListenButton(() => reportText));
    }
    $("#compare-missing-b-title").textContent = `Missing in ${data.doc_b}`;
    $("#compare-missing-a-title").textContent = `Missing in ${data.doc_a}`;
    const global = calcCompareSimilarity(data);
    const globalBox = $("#compare-global-sim");
    if (globalBox) {
      globalBox.classList.remove("hidden");
      globalBox.innerHTML = `<span>Similarity</span><span class="compare-sim-ring-wrap"></span>`;
      const target = globalBox.querySelector(".compare-sim-ring-wrap");
      renderSimilarityRing(target, global, `${Math.round(global * 100)}%`);
    }

    const rows = $("#compare-rows");
    rows.innerHTML = "";
    (data.rows || []).forEach((row) => {
      const card = document.createElement("article");
      card.className = "compare-row";
      const left = row.left_text || "—";
      const right = row.right_text || "—";
      card.innerHTML = `
        <div class="compare-row-header">
          <strong>${escapeHtml(row.title)}</strong>
          <span class="compare-badge ${escapeHtml(row.status)}">${escapeHtml(compareStatusLabel(row.status))}</span>
          <span class="compare-row-sim"><span class="compare-sim-ring-wrap"></span></span>
        </div>
        ${row.semantic_note ? `<p class="compare-row-note">${escapeHtml(row.semantic_note)}</p>` : ""}
        <div class="compare-row-panels">
          <div class="compare-pane">
            <div class="compare-pane-label">${escapeHtml(data.doc_a)}</div>
            ${escapeHtml(left)}
          </div>
          <div class="compare-pane">
            <div class="compare-pane-label">${escapeHtml(data.doc_b)}</div>
            ${escapeHtml(right)}
          </div>
        </div>`;
      const rowSim = Math.max(0, Math.min(1, Number(row.similarity) || 0));
      renderSimilarityRing(card.querySelector(".compare-row-sim .compare-sim-ring-wrap"), rowSim, `${Math.round(rowSim * 100)}%`);
      const rowText = speechText(
        `${row.title}. ${row.semantic_note || ""}. ${data.doc_a}: ${left}. ${data.doc_b}: ${right}`,
      );
      if (rowText) attachListen(card, () => rowText, "compare-row-tts-bar");
      rows.appendChild(card);
    });
  }

  function setCompareMode(slot, mode) {
    compareMode[slot] = mode;
    $$(`.compare-segment[data-slot="${slot}"]`).forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === mode);
    });
    $(`.compare-pane-upload[data-slot="${slot}"]`)?.classList.toggle("hidden", mode !== "upload");
    $(`.compare-pane-library[data-slot="${slot}"]`)?.classList.toggle("hidden", mode !== "library");
    if (mode === "library" && slot === "a") compareFileA = null;
    if (mode === "library" && slot === "b") compareFileB = null;
  }

  function getCompareSelection(slot) {
    if (compareMode[slot] === "library") {
      return { file: null, source: $(`#compare-source-${slot}`)?.value || "" };
    }
    return {
      file: slot === "a" ? compareFileA : compareFileB,
      source: "",
    };
  }

  function setCompareStatus(msg, kind = "") {
    const el = $("#compare-status");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.remove("hidden", "is-error", "is-ok");
    if (!msg) {
      el.classList.add("hidden");
      return;
    }
    if (kind === "error") el.classList.add("is-error");
    if (kind === "ok") el.classList.add("is-ok");
  }

  function setupCompare() {
    ["a", "b"].forEach((slot) => setCompareMode(slot, "upload"));

    $$(".compare-segment").forEach((btn) => {
      btn.addEventListener("click", () => setCompareMode(btn.dataset.slot, btn.dataset.mode));
    });

    $("#compare-file-a")?.addEventListener("change", (e) => {
      const f = e.target.files?.[0];
      compareFileA = f || null;
      $("#compare-name-a").textContent = f ? f.name : "No file selected";
    });
    $("#compare-file-b")?.addEventListener("change", (e) => {
      const f = e.target.files?.[0];
      compareFileB = f || null;
      $("#compare-name-b").textContent = f ? f.name : "No file selected";
    });

    $$(".compare-drop").forEach((zone) => {
      zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
      });
      zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        const f = e.dataTransfer?.files?.[0];
        if (!f) return;
        const slot = zone.getAttribute("for")?.replace("compare-file-", "");
        if (slot === "a") {
          compareFileA = f;
          $("#compare-name-a").textContent = f.name;
        } else if (slot === "b") {
          compareFileB = f;
          $("#compare-name-b").textContent = f.name;
        }
      });
    });

    $("#btn-compare-run")?.addEventListener("click", async () => {
      const selA = getCompareSelection("a");
      const selB = getCompareSelection("b");
      if (!selA.file && !selA.source) {
        toast("Select document A");
        return;
      }
      if (!selB.file && !selB.source) {
        toast("Select document B");
        return;
      }
      const btn = $("#btn-compare-run");
      setCompareStatus("Comparing… this may take a minute for large PDFs.");
      btn.disabled = true;
      $("#compare-results")?.classList.add("hidden");
      $("#compare-global-sim")?.classList.add("hidden");
      try {
        const data = await API.compareDocuments({
          fileA: selA.file,
          fileB: selB.file,
          sourceA: selA.source,
          sourceB: selB.source,
        });
        setCompareStatus("Comparison complete.", "ok");
        renderCompareResults(data);
      } catch (err) {
        setCompareStatus(err.message, "error");
        toast(err.message);
      } finally {
        btn.disabled = false;
      }
    });
    $("#btn-compare-download")?.addEventListener("click", () => {
      if (!lastCompareReport) {
        toast("Run a comparison first");
        return;
      }
      const blob = new Blob([lastCompareReport], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "document-comparison.md";
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  async function onChatSubmit(e) {
    e.preventDefault();
    const q = $("#chat-question").value.trim();
    if (!q) return;

    if (!currentThreadId) {
      const { thread } = await API.createChat();
      currentThreadId = thread.id;
    }

    renderMessage("user", q);
    $("#chat-question").value = "";
    renderMessage("thinking");
    $("#chat-form").classList.add("loading");

    try {
      const source = $("#chat-source")?.value?.trim() || null;
      const res = await API.chat(q, currentThreadId, source);
      if (res.thread_id) currentThreadId = res.thread_id;
      renderMessage("assistant", res.answer, res.retrieval_explanation);
      await loadThreads();
    } catch (err) {
      renderMessage("assistant", `Error: ${err.message}`);
    } finally {
      $("#chat-form").classList.remove("loading");
    }
  }

  function kindLabel(kind) {
    const map = { document: "Doc", section: "Section", page: "Page", node: "Node" };
    return map[kind] || kind;
  }

  function showSummaryDetail(node, source) {
    const panel = $("#summary-detail");
    const preview = $("#summary-detail-preview");
    panel?.classList.remove("hidden");
    $("#summary-detail-kind").textContent = kindLabel(node.kind || "node");
    $("#summary-detail-title").textContent = node.title || source;
    $("#summary-detail-body").textContent = node.summary || "No summary available.";
    const summaryMount = $("#summary-tts-mount");
    if (summaryMount && typeof TTSService !== "undefined") {
      summaryMount.innerHTML = "";
      summaryMount.appendChild(
        TTSService.createListenButton(() => {
          const body = $("#summary-detail-body")?.textContent || "";
          const preview = $("#summary-detail-preview");
          const extra =
            preview && !preview.classList.contains("hidden") ? preview.textContent || "" : "";
          return extra ? `${body}\n\n${extra}` : body;
        }),
      );
    }
    if (node.has_content && node.content_preview) {
      preview.classList.remove("hidden");
      preview.textContent = node.content_preview;
    } else if (node.has_content) {
      preview.classList.add("hidden");
    } else {
      preview.classList.add("hidden");
    }
    $$(".summary-tree-item.active").forEach((el) => el.classList.remove("active"));
    $(`.summary-tree-item[data-node-id="${CSS.escape(node.node_id)}"]`)?.classList.add("active");
  }

  function renderSummaryTreeNode(node, source, depth = 0) {
    const li = document.createElement("li");
    li.className = "summary-tree-node";
    const hasKids = node.children && node.children.length > 0;
    const row = document.createElement("div");
    row.className = "summary-tree-row";
    if (hasKids) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "summary-tree-toggle";
      toggle.setAttribute("aria-expanded", depth < 1 ? "true" : "false");
      toggle.textContent = depth < 1 ? "▾" : "▸";
      toggle.onclick = (e) => {
        e.stopPropagation();
        const open = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", open ? "false" : "true");
        toggle.textContent = open ? "▸" : "▾";
        childList.classList.toggle("hidden", open);
      };
      row.appendChild(toggle);
    } else {
      const spacer = document.createElement("span");
      spacer.className = "summary-tree-spacer";
      row.appendChild(spacer);
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "summary-tree-item";
    btn.dataset.nodeId = node.node_id;
    btn.innerHTML = `<span class="summary-kind-tag">${escapeHtml(kindLabel(node.kind))}</span><span class="summary-tree-label">${escapeHtml(node.title)}</span>`;
    btn.onclick = async () => {
      try {
        const detail = await API.documentNode(source, node.node_id);
        showSummaryDetail(detail, source);
      } catch {
        showSummaryDetail(node, source);
      }
    };
    row.appendChild(btn);
    li.appendChild(row);
    if (hasKids) {
      const childList = document.createElement("ul");
      childList.className = "summary-tree-children";
      if (depth >= 1) childList.classList.add("hidden");
      node.children.forEach((ch) => childList.appendChild(renderSummaryTreeNode(ch, source, depth + 1)));
      li.appendChild(childList);
    }
    return li;
  }

  async function openDocumentOutline(source) {
    selectedOutlineSource = source;
    const sidebar = $("#summary-sidebar");
    const treeEl = $("#summary-tree");
    sidebar?.classList.remove("hidden");
    $("#summary-doc-name").textContent = source;
    treeEl.innerHTML = '<p class="muted summary-loading">Loading outline…</p>';
    $("#summary-detail")?.classList.add("hidden");
    try {
      const data = await API.documentOutline(source);
      treeEl.innerHTML = "";
      const root = document.createElement("ul");
      root.className = "summary-tree-root";
      root.appendChild(renderSummaryTreeNode(data.outline, source, 0));
      treeEl.appendChild(root);
      showSummaryDetail(data.outline, source);
    } catch (err) {
      treeEl.innerHTML = `<p class="muted">${escapeHtml(err.message)}</p>`;
    }
  }

  async function loadDocuments() {
    try {
      const sources = await refreshDocumentLibrary();
      const list = $("#doc-list");
      list.innerHTML = "";
      $("#doc-empty").classList.toggle("hidden", sources.length > 0);
      const badge = $("#doc-count-badge");
      if (badge) badge.textContent = String(sources.length);
      const countEl = $("#doc-count");
      if (countEl) countEl.textContent = sources.length ? `(${sources.length})` : "";

      let uploadsByFilename = {};
      try {
        const h = await API.history();
        (h.documents || []).forEach((e) => {
          if (e.filename && e.action !== "removed" && e.ts) {
            uploadsByFilename[e.filename] = e.ts;
          }
        });
      } catch {
        /* ignore */
      }

      sources.forEach((src) => {
        const li = document.createElement("li");
        li.className = "doc-list-item";
        const lower = src.toLowerCase();
        const ext = lower.endsWith(".pdf") ? "pdf" : lower.endsWith(".txt") ? "txt" : "doc";
        const kind = ext === "pdf" ? "PDF" : ext === "txt" ? "TXT" : "DOC";
        const uploadTs = uploadsByFilename[src];
        const when = uploadTs ? relativeTime(uploadTs) : "In library";

        li.innerHTML = `
          <div class="doc-file-icon ${ext}" aria-hidden="true">${kind}</div>
          <div class="doc-row-main">
            <div class="doc-title-row">
              <span class="doc-list-name">${escapeHtml(src)}</span>
              <span class="doc-status-pill">Indexed</span>
            </div>
          </div>
          <div class="doc-meta-row muted">
            <span>${kind}</span>
            <span aria-hidden="true">·</span>
            <span title="Size on server not tracked">—</span>
            <span aria-hidden="true">·</span>
            <span>${escapeHtml(when)}</span>
          </div>`;

        const actions = document.createElement("div");
        actions.className = "doc-list-actions";

        const viewBtn = document.createElement("button");
        viewBtn.type = "button";
        viewBtn.className = "doc-icon-btn";
        viewBtn.title = "Open in chat";
        viewBtn.setAttribute("aria-label", "View in chat");
        viewBtn.innerHTML = '<i data-lucide="eye"></i>';
        viewBtn.onclick = () => {
          setActiveSource(src);
          navigate("chat");
        };

        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "doc-icon-btn";
        editBtn.title = "AI notes for this document";
        editBtn.setAttribute("aria-label", "Edit with AI notes");
        editBtn.innerHTML = '<i data-lucide="pencil"></i>';
        editBtn.onclick = () => {
          setActiveSource(src);
          navigate("notes");
          const sel = $("#notes-source");
          if (sel && [...sel.options].some((o) => o.value === src)) sel.value = src;
        };

        const more = document.createElement("details");
        more.className = "doc-more";
        const sum = document.createElement("summary");
        sum.className = "doc-icon-btn doc-more-summary";
        sum.title = "More options";
        sum.innerHTML = '<i data-lucide="more-horizontal"></i>';
        const menu = document.createElement("div");
        menu.className = "doc-more-menu";

        const outlineItem = document.createElement("button");
        outlineItem.type = "button";
        outlineItem.className = "doc-more-item";
        outlineItem.textContent = "Outline";
        outlineItem.onclick = async (ev) => {
          ev.preventDefault();
          more.removeAttribute("open");
          await openDocumentOutline(src);
        };

        const mapItem = document.createElement("button");
        mapItem.type = "button";
        mapItem.className = "doc-more-item";
        mapItem.textContent = "Knowledge map";
        mapItem.onclick = (ev) => {
          ev.preventDefault();
          more.removeAttribute("open");
          setActiveSource(src);
          navigate("knowledge-map");
        };

        const delItem = document.createElement("button");
        delItem.type = "button";
        delItem.className = "doc-more-item doc-more-danger";
        delItem.textContent = "Remove from library";
        delItem.onclick = async (ev) => {
          ev.preventDefault();
          more.removeAttribute("open");
          if (!confirm(`Remove ${src}?`)) return;
          await API.deleteDocument(src);
          if (selectedOutlineSource === src) {
            $("#summary-sidebar")?.classList.add("hidden");
            selectedOutlineSource = null;
          }
          loadDocuments();
          refreshDocumentLibrary();
        };

        menu.appendChild(outlineItem);
        menu.appendChild(mapItem);
        menu.appendChild(delItem);
        more.appendChild(sum);
        more.appendChild(menu);

        actions.appendChild(viewBtn);
        actions.appendChild(editBtn);
        actions.appendChild(more);
        li.appendChild(actions);
        list.appendChild(li);
      });
      updateDocsStatsStrip(sources);
      updateDocsQueueStrip();
      refreshLucideIcons();
      void renderDocActivityStrip();
      void refreshDashboardStats();
    } catch (err) {
      toast(err.message);
    }
  }

  function renderToolSelect() {
    const sel = $("#tool-action");
    if (!sel) return;
    const actions = meta.tool_actions?.length ? meta.tool_actions : DEFAULT_TOOL_ACTIONS;
    sel.innerHTML = "";
    actions.forEach((a) => {
      const o = document.createElement("option");
      o.value = a.id;
      o.textContent = a.label;
      sel.appendChild(o);
    });
    sel.value = actions.some((a) => a.id === selectedToolAction)
      ? selectedToolAction
      : actions[0].id;
    selectedToolAction = sel.value;
    $("#custom-tool-wrap").classList.toggle("hidden", sel.value !== "custom");
    renderToolActionCards();
  }

  const NB_CARD_ACCENTS = [
    "nb-accent-purple",
    "nb-accent-blue",
    "nb-accent-orange",
    "nb-accent-sky",
    "nb-accent-rose",
    "nb-accent-indigo",
    "nb-accent-green",
    "nb-accent-teal",
  ];

  function notebookAccentClass(title) {
    const s = title || "";
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return NB_CARD_ACCENTS[h % NB_CARD_ACCENTS.length];
  }

  function formatNoteBody(body, fmt) {
    const lines = body.split("\n");
    if (fmt === "bullets") return "<ul class='note-fmt-bullets'>" + lines.map((l) => `<li>${escapeHtml(l)}</li>`).join("") + "</ul>";
    if (fmt === "heading") return `<div class="note-fmt-heading"><h4>${escapeHtml(body.split("\n")[0])}</h4><p>${escapeHtml(lines.slice(1).join("\n"))}</p></div>`;
    if (fmt === "important") return `<div class="note-fmt-important">${escapeHtml(body).replace(/\n/g, "<br>")}</div>`;
    if (fmt === "underline") return `<div class="note-fmt-underline">${escapeHtml(body).replace(/\n/g, "<br>")}</div>`;
    if (fmt === "index") return `<div class="note-fmt-index">${escapeHtml(body)}</div>`;
    return escapeHtml(body).replace(/\n/g, "<br>");
  }

  async function loadNotebook() {
    try {
      const { entries } = await API.notebook();
      const filtered = entries.filter((ent) => {
        const fmt = ent.format || "plain";
        if (notebookFilter === "all") return true;
        if (notebookFilter === "summaries") return ["plain", "heading"].includes(fmt);
        if (notebookFilter === "topics") return fmt === "index";
        if (notebookFilter === "explanations") return ["bullets", "important"].includes(fmt);
        if (notebookFilter === "custom") return ["underline"].includes(fmt);
        return true;
      });
      const list = $("#notebook-list");
      list.innerHTML = "";
      $("#notebook-empty").classList.toggle("hidden", filtered.length > 0);
      filtered.forEach((ent) => {
        const div = document.createElement("div");
        const accent = notebookAccentClass(ent.title || ent.body);
        div.className = `notebook-entry nb-card ${accent}`;
        const fmt = ent.format || "plain";
        const src = (ent.sources && ent.sources[0]) || "Workspace";
        const rel = relativeTime(ent.ts) || "Recently";
        const scope =
          fmt === "index" ? "Sections" : fmt === "bullets" ? "Bullets" : fmt === "heading" ? "Heading" : "Note";
        const icon = "sticky-note";
        const bodyPreview = (ent.body || "").replace(/\s*\[[^\]]+\]\s*/g, " ").trim();
        const shortBody =
          bodyPreview.length > 180 ? `${escapeHtml(bodyPreview.slice(0, 180))}…` : escapeHtml(bodyPreview);

        div.innerHTML = `
          <div class="nb-card-head">
            <span class="nb-card-ico"><i data-lucide="${icon}"></i></span>
            <div style="min-width:0">
              <strong>${escapeHtml(ent.title || "Untitled note")}</strong>
              <div class="muted" style="font-size:0.78rem">${escapeHtml(src)}</div>
            </div>
          </div>
          <div class="nb-card-preview muted" style="font-size:0.82rem;line-height:1.45;margin-top:0.35rem">${shortBody || "<em>Empty note</em>"}</div>
          <div class="nb-card-meta">${escapeHtml(scope)} · ${escapeHtml(rel)}</div>
        `;
        const noteText = speechText(
          [ent.title, (ent.body || "").replace(/\s*\[[^\]]+\]\s*/g, " ")].filter(Boolean).join(". "),
        );
        if (noteText) attachListen(div, () => noteText, "notebook-entry-tts-bar");
        list.appendChild(div);
      });
      refreshLucideIcons();
      list.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "end" });
    } catch (err) {
      toast(err.message);
    }
  }


  async function loadToolHistory() {
    try {
      const { entries } = await API.toolsHistory();
      const list = $("#tool-history-list");
      if (!list) return;
      list.innerHTML = "";
      $("#tool-history-empty")?.classList.toggle("hidden", entries.length > 0);
      entries.forEach((ent) => {
        const ts = (ent.ts || "").slice(0, 16).replace("T", " ");
        const label = (ent.label || ent.action || "Tool").replace(/_/g, " ");
        const row = document.createElement("div");
        row.className = "history-item-row";
        const main = document.createElement("div");
        main.className = "history-item";
        main.innerHTML = `<div class="history-item-meta">${escapeHtml(label)} · ${escapeHtml(ts)}</div><div class="history-item-body">${formatToolAnswer(ent.body || "", ent.action || ent.format || "")}</div>`;
        const toolPagePlain = speechText((ent.body || "").replace(/\s*\[[^\]]+\]\s*/g, " "));
        if (toolPagePlain) attachListen(main, () => toolPagePlain, "history-tts-bar");
        row.appendChild(main);
        row.appendChild(
          createHistoryDeleteButton("Delete tool run", async () => {
            if (!ent.ts) throw new Error("Missing tool run id");
            if (!confirm("Delete this tool run?")) return;
            await API.deleteToolHistoryEntry(ent.ts);
            toast("Deleted");
            loadToolHistory();
          }),
        );
        list.appendChild(row);
      });
    } catch (err) {
      toast(err.message);
    }
  }

  let historyCache = null;

  async function openHistoryModal(tab) {
    $("#history-modal")?.classList.remove("hidden");
    $("#profile-menu")?.classList.add("hidden");
    $("#profile-btn")?.setAttribute("aria-expanded", "false");
    try {
      historyCache = await API.history();
    } catch (err) {
      toast(err.message);
      return;
    }
    showHistoryTab(tab || "chat");
  }

  function closeHistoryModal() {
    $("#history-modal")?.classList.add("hidden");
  }

  function createHistoryDeleteButton(label, onDelete) {
    const del = document.createElement("button");
    del.type = "button";
    del.className = "history-delete";
    del.setAttribute("aria-label", label);
    del.innerHTML = TRASH_ICON;
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        await onDelete();
      } catch (err) {
        toast(err.message || "Delete failed");
      }
    });
    return del;
  }

  async function refreshHistoryTab(tab) {
    try {
      historyCache = await API.history();
      showHistoryTab(tab);
    } catch (err) {
      toast(err.message);
    }
  }

  function renderActivityHistoryTab(tabKey, kind, items, { page, typeLabel, formatBody }) {
    const body = $("#history-body");
    const empty = '<p class="muted">Nothing here yet.</p>';
    if (!items.length) {
      body.innerHTML = empty;
      return;
    }
    items.forEach((ent) => {
      const row = document.createElement("div");
      row.className = "history-item-row";
      const main = document.createElement("div");
      main.className = "history-item history-item-clickable";
      const ts = (ent.ts || "").slice(0, 16).replace("T", " ");
      const summaryLine = ent.summary
        ? `${escapeHtml(ent.summary)} · ${escapeHtml(ts)}`
        : escapeHtml(ts);
      const bodyContent = formatBody
        ? formatBody(ent)
        : ent.body
          ? `<div class="history-item-body">${escapeHtml((ent.body || "").slice(0, 1200))}</div>`
          : "";
      main.innerHTML = `<div class="history-item-meta">${escapeHtml(typeLabel)} · ${summaryLine}</div><div class="history-item-title">${escapeHtml(ent.title || typeLabel)}</div>${bodyContent}`;
      const speech = speechText([ent.title, ent.summary, ent.body].filter(Boolean).join(". "));
      if (speech) attachListen(main, () => speech, "history-tts-bar");
      main.addEventListener("click", () => {
        closeHistoryModal();
        navigate(page);
        if (page === "notes" && ent.meta?.source) {
          const sel = $("#notes-source");
          if (sel) sel.value = ent.meta.source;
        }
        if (page === "knowledge-map" && ent.meta?.source != null) {
          const sel = $("#km-source");
          if (sel) sel.value = ent.meta.source || "";
        }
        if (page === "timeline" && ent.meta?.source != null) {
          const sel = $("#tl-source");
          if (sel) sel.value = ent.meta.source || "";
        }
      });
      row.appendChild(main);
      row.appendChild(
        createHistoryDeleteButton(`Delete ${typeLabel}`, async () => {
          if (!ent.ts) throw new Error("Missing entry id");
          if (!confirm(`Delete this ${typeLabel.toLowerCase()} entry from history?`)) return;
          await API.deleteActivityHistoryEntry(kind, ent.ts);
          toast("Deleted");
          await refreshHistoryTab(tabKey);
        }),
      );
      body.appendChild(row);
    });
  }

  function showHistoryTab(tab) {
    $$(".history-tab").forEach((b) => b.classList.toggle("active", b.dataset.historyTab === tab));
    const body = $("#history-body");
    if (!body || !historyCache) return;
    body.innerHTML = "";
    const empty = '<p class="muted">Nothing here yet.</p>';

    if (tab === "chat") {
      const items = historyCache.chats || [];
      if (!items.length) { body.innerHTML = empty; return; }
      items.forEach((c) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "history-item";
        btn.style.cssText = "text-align:left;cursor:pointer;font:inherit;color:inherit";
        const ts = (c.updated || "").slice(0, 16).replace("T", " ");
        btn.innerHTML = `<div class="history-item-title">${escapeHtml(c.title || "Chat")}</div><div class="history-item-meta">${escapeHtml(ts)}</div>`;
        const chatHistTitle = speechText(c.title || "Chat");
        if (chatHistTitle) attachListen(btn, () => chatHistTitle, "history-tts-bar");
        btn.onclick = async () => {
          closeHistoryModal();
          await openThread(c.id);
        };
        const row = document.createElement("div");
        row.className = "history-item-row";
        row.appendChild(btn);
        row.appendChild(
          createHistoryDeleteButton("Delete chat", async () => {
            await deleteThread(c.id, c.title);
            await refreshHistoryTab("chat");
          }),
        );
        body.appendChild(row);
      });
      return;
    }
    if (tab === "notebook") {
      const items = historyCache.notebook || [];
      if (!items.length) { body.innerHTML = empty; return; }
      items.forEach((ent) => {
        const row = document.createElement("div");
        row.className = "history-item-row";
        const main = document.createElement("div");
        main.className = "history-item";
        const ts = (ent.ts || "").slice(0, 16).replace("T", " ");
        main.innerHTML = `<div class="history-item-meta">Note · ${escapeHtml(ts)}</div>${ent.title ? `<div class="history-item-title">${escapeHtml(ent.title)}</div>` : ""}<div class="history-item-body">${formatNoteBody((ent.body || "").replace(/\s*\[[^\]]+\]\s*/g, " "), ent.format || "plain")}</div>`;
        const histNoteText = speechText(
          [ent.title, (ent.body || "").replace(/\s*\[[^\]]+\]\s*/g, " ")].filter(Boolean).join(". "),
        );
        if (histNoteText) attachListen(main, () => histNoteText, "history-tts-bar");
        row.appendChild(main);
        row.appendChild(
          createHistoryDeleteButton("Delete note", async () => {
            if (!ent.ts) throw new Error("Missing note id");
            if (!confirm("Delete this note from history?")) return;
            await API.deleteNotebookEntry(ent.ts);
            toast("Note deleted");
            if ($("#page-notebook")?.classList.contains("active")) loadNotebook();
            await refreshHistoryTab("notebook");
          }),
        );
        body.appendChild(row);
      });
      return;
    }
    if (tab === "tools") {
      const items = historyCache.tools || [];
      if (!items.length) { body.innerHTML = empty; return; }
      items.forEach((ent) => {
        const row = document.createElement("div");
        row.className = "history-item-row";
        const main = document.createElement("div");
        main.className = "history-item";
        const ts = (ent.ts || "").slice(0, 16).replace("T", " ");
        const label = (ent.label || ent.action || "Tool").replace(/_/g, " ");
        main.innerHTML = `<div class="history-item-meta">${escapeHtml(label)} · ${escapeHtml(ts)}</div><div class="history-item-body">${formatToolAnswer(ent.body || "", ent.action || "")}</div>`;
        const toolsHistPlain = speechText((ent.body || "").replace(/\s*\[[^\]]+\]\s*/g, " "));
        if (toolsHistPlain) attachListen(main, () => toolsHistPlain, "history-tts-bar");
        row.appendChild(main);
        row.appendChild(
          createHistoryDeleteButton("Delete tool run", async () => {
            if (!ent.ts) throw new Error("Missing tool run id");
            if (!confirm("Delete this tool run from history?")) return;
            await API.deleteToolHistoryEntry(ent.ts);
            toast("Deleted");
            if ($("#page-tools")?.classList.contains("active")) loadToolHistory();
            await refreshHistoryTab("tools");
          }),
        );
        body.appendChild(row);
      });
      return;
    }
    if (tab === "documents") {
      const items = historyCache.documents || [];
      if (!items.length) { body.innerHTML = empty; return; }
      items.forEach((ent) => {
        const row = document.createElement("div");
        row.className = "history-item-row";
        const main = document.createElement("div");
        main.className = "history-item";
        const ts = (ent.ts || "").slice(0, 16).replace("T", " ");
        const action = ent.action === "removed" ? "Removed" : "Uploaded";
        main.innerHTML = `<div class="history-item-meta">${action} · ${escapeHtml(ts)}</div><div class="history-item-title">${escapeHtml(ent.filename || "")}</div>`;
        const docHistText = speechText(`${action} ${ent.filename || ""}`);
        if (docHistText) attachListen(main, () => docHistText, "history-tts-bar");
        row.appendChild(main);
        row.appendChild(
          createHistoryDeleteButton("Delete entry", async () => {
            if (!confirm("Remove this entry from upload history?")) return;
            await API.deleteDocumentHistoryEntry(ent.ts);
            toast("Deleted");
            await refreshHistoryTab("documents");
          }),
        );
        body.appendChild(row);
      });
      return;
    }
    if (tab === "compare") {
      renderActivityHistoryTab("compare", "compare", historyCache.compare || [], {
        page: "compare",
        typeLabel: "Compare",
      });
      return;
    }
    if (tab === "notes") {
      renderActivityHistoryTab("notes", "notes", historyCache.notes || [], {
        page: "notes",
        typeLabel: "AI notes",
        formatBody: (ent) =>
          ent.body
            ? `<pre class="history-item-pre">${escapeHtml((ent.body || "").slice(0, 1500))}</pre>`
            : "",
      });
      return;
    }
    if (tab === "map") {
      renderActivityHistoryTab("map", "map", historyCache.map || [], {
        page: "knowledge-map",
        typeLabel: "Map",
      });
      return;
    }
    if (tab === "timeline") {
      renderActivityHistoryTab("timeline", "timeline", historyCache.timeline || [], {
        page: "timeline",
        typeLabel: "Timeline",
      });
    }
  }

  function addPendingFiles(fileList) {
    const incoming = [...fileList].filter((f) => /\.(pdf|txt)$/i.test(f.name));
    const skipped = [...fileList].filter((f) => !/\.(pdf|txt)$/i.test(f.name));
    if (skipped.length) {
      toast(`${skipped.length} file(s) skipped — only PDF and TXT are supported.`);
    }
    const keys = new Set(pendingFiles.map((f) => `${f.name}:${f.size}`));
    incoming.forEach((f) => {
      const key = `${f.name}:${f.size}`;
      if (!keys.has(key)) {
        keys.add(key);
        pendingFiles.push(f);
      }
    });
    renderPendingUploads();
  }

  function renderPendingUploads() {
    const list = $("#pending-upload-list");
    const status = $("#upload-status");
    if (!list) return;
    list.innerHTML = "";
    if (!pendingFiles.length) {
      list.classList.add("hidden");
      $("#btn-upload").disabled = true;
      $("#btn-clear-pending")?.classList.add("hidden");
      if (status && !status.dataset.busy) status.textContent = "";
      updateDocsQueueStrip();
      return;
    }
    list.classList.remove("hidden");
    $("#btn-upload").disabled = false;
    $("#btn-clear-pending")?.classList.remove("hidden");
    pendingFiles.forEach((file) => {
      const li = document.createElement("li");
      li.className = "pending-upload-item";
      li.innerHTML = `<span class="pending-upload-name">${escapeHtml(file.name)}</span>`;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "btn btn-ghost btn-sm";
      rm.textContent = "Remove";
      rm.addEventListener("click", (e) => {
        e.stopPropagation();
        pendingFiles = pendingFiles.filter((f) => f !== file);
        renderPendingUploads();
      });
      li.appendChild(rm);
      list.appendChild(li);
    });
    if (status && !status.dataset.busy) {
      status.textContent = `${pendingFiles.length} file(s) ready to index.`;
    }
    updateDocsQueueStrip();
  }

  function setupUpload() {
    const zone = $("#upload-zone");
    const input = $("#file-input");
    const openPicker = () => input?.click();
    $("#btn-browse-docs")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openPicker();
    });
    $("#pick-files")?.addEventListener("click", (e) => {
      e.stopPropagation();
      openPicker();
    });
    zone?.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      openPicker();
    });
    zone?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openPicker();
      }
    });
    input?.addEventListener("change", () => {
      if (input.files?.length) addPendingFiles(input.files);
      input.value = "";
    });
    zone?.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    });
    zone?.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone?.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      if (e.dataTransfer?.files?.length) addPendingFiles(e.dataTransfer.files);
    });
    $("#btn-clear-pending")?.addEventListener("click", () => {
      pendingFiles = [];
      renderPendingUploads();
    });
    $("#btn-upload")?.addEventListener("click", async () => {
      if (!pendingFiles.length) return;
      const status = $("#upload-status");
      const btn = $("#btn-upload");
      if (status) {
        status.dataset.busy = "1";
        status.textContent = `Indexing ${pendingFiles.length} file(s)…`;
      }
      updateDocsQueueStrip();
      if (btn) btn.disabled = true;
      try {
        const res = await API.uploadDocuments(pendingFiles);
        const n = res.indexed?.length || 0;
        const errN = res.errors?.length || 0;
        if (status) {
          delete status.dataset.busy;
          if (n && errN) {
            status.textContent = `Indexed ${n} file(s). ${errN} failed.`;
          } else if (n) {
            status.textContent = `Indexed ${n} file(s).`;
          } else if (errN) {
            status.textContent = res.errors.join(" ");
          } else {
            status.textContent = "No files indexed.";
          }
        }
        if (n) toast(`Indexed ${n} document(s)`);
        if (errN) toast(res.errors[0] || "Some files failed", 5000);
        pendingFiles = [];
        renderPendingUploads();
        await loadDocuments();
        if (n === 1 && res.indexed[0]) setActiveSource(res.indexed[0]);
      } catch (err) {
        if (status) {
          delete status.dataset.busy;
          status.textContent = err.message;
        }
        toast(err.message);
      } finally {
        if (btn) btn.disabled = !pendingFiles.length;
        updateDocsQueueStrip();
      }
    });
    renderPendingUploads();
  }

    async function initTts() {
      if (typeof TTSService === "undefined") return;
      const hasBrowser = TTSService.hasBrowserTts();
      try {
        const health = await API.request("/api/health");
        TTSService.setBackendEnabled(!!health?.tts_configured);
        TTSService.setEnabled(TTSService.backendEnabled || hasBrowser);
      } catch {
        TTSService.setBackendEnabled(false);
        TTSService.setEnabled(hasBrowser);
      }
    }

    async function initStt() {
      if (typeof STTService === "undefined") return;
      const hasBrowser = STTService.hasBrowserStt();
      const hasMic = Boolean(navigator.mediaDevices?.getUserMedia);
      try {
        const health = await API.request("/api/health");
        STTService.setBackendEnabled(!!health?.stt_configured);
      } catch {
        STTService.setBackendEnabled(false);
      }
      STTService.setEnabled(hasBrowser || hasMic);
      STTService.initUi();
    }

    async function warnIfStaleServer() {
      try {
        const health = await API.request("/api/health");
        const features = health?.features || [];
        const required = ["knowledge_map", "timeline", "compare"];
        const missing = required.filter((f) => !features.includes(f));
        if (missing.length) {
          toast(
            `Server is missing: ${missing.join(", ")}. Restart: python -m rag serve --port 8080`,
            12000,
          );
        }
      } catch {
        /* ignore */
      }
    }

    async function init() {
    try {
      meta = await API.meta();
    } catch {
      meta = {
        themes: [
          { id: "midnight", label: "Midnight" },
          { id: "ocean", label: "Ocean" },
          { id: "light", label: "Light" },
        ],
        tool_actions: DEFAULT_TOOL_ACTIONS,
      };
    }
    initTts();
    initStt();
    warnIfStaleServer();

    $$("[data-auth-tab]").forEach((tab) => {
      tab.addEventListener("click", () => {
        $$(".auth-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const isReg = tab.dataset.authTab === "register";
        $("#login-form").classList.toggle("hidden", isReg);
        $("#register-form").classList.toggle("hidden", !isReg);
      });
    });

    $("#login-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = $("#login-error");
      err.classList.add("hidden");
      try {
        const res = await API.login($("#login-user").value.trim().toLowerCase(), $("#login-pass").value);
        API.setToken(res.token);
        API.setUser(res);
        showApp(res);
        await loadThreads();
        await newChat();
      } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
      }
    });

    $("#register-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = $("#register-error");
      err.classList.add("hidden");
      try {
        const res = await API.register(
          $("#reg-user").value.trim().toLowerCase(),
          $("#reg-pass").value,
          $("#reg-email").value.trim(),
        );
        API.setToken(res.token);
        API.setUser(res);
        showApp(res);
        await loadThreads();
        await newChat();
      } catch (ex) {
        err.textContent = ex.message;
        err.classList.remove("hidden");
      }
    });

    $("#btn-signout").onclick = async () => {
      try {
        await API.logout();
      } catch {
        /* ignore */
      }
      showAuth();
    };

    $("#profile-btn").onclick = (e) => {
      e.stopPropagation();
      const menu = $("#profile-menu");
      const btn = $("#profile-btn");
      if (!menu || !btn) return;
      const isHidden = menu.classList.toggle("hidden");
      btn.setAttribute("aria-expanded", isHidden ? "false" : "true");
    };
    document.addEventListener("click", (e) => {
      const menu = $("#profile-menu");
      const btn = $("#profile-btn");
      if (!menu || menu.classList.contains("hidden")) return;
      if (btn?.contains(e.target) || menu.contains(e.target)) return;
      menu.classList.add("hidden");
      btn?.setAttribute("aria-expanded", "false");
    });
    $("#profile-menu").addEventListener("click", (e) => e.stopPropagation());
    $("#btn-open-history")?.addEventListener("click", () => openHistoryModal("chat"));
    $("#history-close")?.addEventListener("click", closeHistoryModal);
    $("#history-backdrop")?.addEventListener("click", closeHistoryModal);
    $$(".history-tab").forEach((b) => b.addEventListener("click", () => showHistoryTab(b.dataset.historyTab)));

    $("#btn-new-chat").onclick = newChat;
    $("#btn-hero-new-chat")?.addEventListener("click", newChat);

    $("#btn-sidebar-account")?.addEventListener("click", (e) => {
      e.stopPropagation();
      $("#profile-btn")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    $("#btn-header-theme")?.addEventListener("click", () => void cycleHeaderTheme());

    $(".header-bell-wrap")?.addEventListener("click", () =>
      toast("You're all caught up — notifications will appear here.", 2200),
    );

    $("#btn-doc-scroll")?.addEventListener("click", () => {
      $("#doc-list")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    $("#btn-view-all-chats")?.addEventListener("click", () => void openHistoryModal("chat"));

    $("#btn-notebook-new-chat")?.addEventListener("click", () => void newChat());

    $$(".notebook-tab").forEach((tab) =>
      tab.addEventListener("click", () => {
        $$(".notebook-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        notebookFilter = tab.dataset.nbFilter || "all";
        loadNotebook();
      }),
    );

    document.addEventListener("keydown", (e) => {
      const k = (e.key || "").toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === "k") {
        e.preventDefault();
        $("#chat-question")?.focus();
      }
    });

    $("#btn-goto-documents")?.addEventListener("click", () => navigate("documents"));
    $$(".nav-item").forEach((b) => b.addEventListener("click", () => navigate(b.dataset.page)));
    $$("[data-quick-nav]").forEach((b) => b.addEventListener("click", () => navigate(b.dataset.quickNav)));

    $("#btn-header-help")?.addEventListener("click", () =>
      toast("Ctrl+K focuses the ask box. Scope answers with the document selector above the composer.", 4500),
    );
    $("#header-search-input")?.addEventListener("focus", () => $("#chat-question")?.focus());
    $("#header-search-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        $("#chat-question")?.focus();
      }
    });
    $("#chat-form").addEventListener("submit", onChatSubmit);

    $("#note-format")?.addEventListener("change", (e) => {
      noteFormat = e.target.value;
    });

    $("#tool-action")?.addEventListener("change", (e) => {
      selectedToolAction = e.target.value;
      $("#custom-tool-wrap").classList.toggle("hidden", selectedToolAction !== "custom");
    });

    $("#btn-menu")?.addEventListener("click", () => {
      const shell = $("#app-shell");
      const open = shell.classList.toggle("sidebar-open");
      $("#sidebar-backdrop").classList.toggle("hidden", !open);
    });
    $("#sidebar-backdrop")?.addEventListener("click", closeSidebarMobile);

    $("#btn-save-note").onclick = async () => {
      const body = $("#note-body").value.trim();
      if (!body) return toast("Write something first");
      const src = $("#notebook-source")?.value?.trim();
      await API.addNote($("#note-title").value.trim(), body, noteFormat, src ? [src] : []);
      $("#note-body").value = "";
      $("#note-title").value = "";
      loadNotebook();
      toast("Saved");
    };

    $("#btn-run-tool").onclick = async () => {
      const box = $("#tool-result");
      box.classList.remove("hidden");
      box.innerHTML = 'Working<span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span>';
      try {
        const res = await API.runTool(
          selectedToolAction,
          $("#tool-custom").value.trim(),
          $("#tool-source").value || null,
        );
        box.innerHTML = formatToolAnswer(res.answer, selectedToolAction);
        if (typeof TTSService !== "undefined") {
          let bar = box.querySelector(".tool-tts-bar");
          if (!bar) {
            bar = document.createElement("div");
            bar.className = "tool-tts-bar";
            box.appendChild(bar);
          }
          bar.innerHTML = "";
          const plain = (res.answer || "").replace(/\s*\[[^\]]+\]\s*/g, " ").trim();
          bar.appendChild(TTSService.createListenButton(() => plain));
        }
        loadToolHistory();
      } catch (err) {
        box.textContent = err.message;
      }
    };

    setupUpload();
    setupCompare();
    setupNotes();
    setupKnowledgeMap();
    setupTimeline();
    refreshLucideIcons();
    showAuth();
    checkSession();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

