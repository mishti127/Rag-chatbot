/** API client */

const API = {
  base: "",

  getToken() {
    return localStorage.getItem("rag_token");
  },

  setToken(token) {
    if (token) localStorage.setItem("rag_token", token);
    else localStorage.removeItem("rag_token");
  },

  getUser() {
    const raw = localStorage.getItem("rag_user");
    return raw ? JSON.parse(raw) : null;
  },

  setUser(user) {
    if (user) localStorage.setItem("rag_user", JSON.stringify(user));
    else localStorage.removeItem("rag_user");
  },

  async request(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    const token = this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    let body = options.body;
    if (body && !(body instanceof FormData) && typeof body === "object") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }

    const res = await fetch(`${this.base}${path}`, { ...options, headers, body });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text || res.statusText };
    }

    if (!res.ok) {
      let msg = data?.detail || res.statusText;
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      if (res.status === 404 && (data?.detail === "Not Found" || !data?.detail)) {
        msg =
          `API route not found: ${path} at ${origin || "this URL"}. ` +
          "Stop any old server and restart from the project folder: " +
          "python -m rag serve --port 8080 — then open http://127.0.0.1:8080/ and hard-refresh (Ctrl+Shift+R).";
      } else if (res.status === 401) {
        msg = typeof msg === "string" ? msg : "Not authenticated — sign in again.";
      }
      const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = res.status;
      throw err;
    }
    return data;
  },

  meta() {
    return this.request("/api/meta");
  },

  register(username, password, email) {
    return this.request("/api/auth/register", {
      method: "POST",
      body: { username, password, email },
    });
  },

  login(username, password) {
    return this.request("/api/auth/login", {
      method: "POST",
      body: { username, password },
    });
  },

  logout() {
    return this.request("/api/auth/logout", { method: "POST" });
  },

  me() {
    return this.request("/api/auth/me");
  },

  setTheme(theme) {
    return this.request("/api/auth/theme", { method: "PATCH", body: { theme } });
  },

  listChats() {
    return this.request("/api/chats");
  },

  createChat() {
    return this.request("/api/chats", { method: "POST" });
  },

  getChat(id) {
    return this.request(`/api/chats/${id}`);
  },

  deleteChat(id) {
    return this.request(`/api/chats/${id}`, { method: "DELETE" });
  },

  chat(question, threadId, source = null) {
    const body = { question, thread_id: threadId };
    if (source) body.source = source;
    return this.request("/api/chat", {
      method: "POST",
      body,
    });
  },

  runTool(action, customPrompt, source) {
    return this.request("/api/tools/run", {
      method: "POST",
      body: {
        action,
        custom_prompt: customPrompt || "",
        source: source || null,
      },
    });
  },

  toolsHistory() {
    return this.request("/api/tools/history");
  },

  history() {
    return this.request("/api/history");
  },

  deleteNotebookEntry(ts) {
    const id = encodeURIComponent(ts || "");
    return this.request(`/api/notebook/entries/${id}`, { method: "DELETE" });
  },

  deleteToolHistoryEntry(ts) {
    const id = encodeURIComponent(ts || "");
    return this.request(`/api/tools/history/entries/${id}`, { method: "DELETE" });
  },

  deleteDocumentHistoryEntry(ts) {
    const id = encodeURIComponent(ts || "");
    return this.request(`/api/history/documents/entries/${id}`, { method: "DELETE" });
  },

  deleteActivityHistoryEntry(kind, ts) {
    const k = encodeURIComponent(kind || "");
    const id = encodeURIComponent(ts || "");
    return this.request(`/api/history/activity/${k}/entries/${id}`, { method: "DELETE" });
  },

  listDocuments() {
    return this.request("/api/documents");
  },

  uploadDocuments(files) {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return this.request("/api/documents/upload", { method: "POST", body: fd });
  },

  deleteDocument(source) {
    return this.request(`/api/documents/${encodeURIComponent(source)}`, {
      method: "DELETE",
    });
  },

  documentOutline(source) {
    return this.request(`/api/documents/${encodeURIComponent(source)}/outline`);
  },

  documentNode(source, nodeId) {
    return this.request(
      `/api/documents/${encodeURIComponent(source)}/nodes/${encodeURIComponent(nodeId)}`,
    );
  },

  notebook() {
    return this.request("/api/notebook");
  },

  addNote(title, body, format, sources) {
    return this.request("/api/notebook", {
      method: "POST",
      body: { title, body, format, sources },
    });
  },

  clearNotebook() {
    return this.request("/api/notebook", { method: "DELETE" });
  },

  generateNotes(source, scope, style, focus) {
    return this.request("/api/notes/generate", {
      method: "POST",
      body: { source, scope, style, focus: focus || "" },
    });
  },

  async exportNotes(source, scope, style, focus, format) {
    const res = await fetch(`${this.base}/api/notes/export`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.getToken()}`,
      },
      body: JSON.stringify({
        source,
        scope,
        style,
        focus: focus || "",
        format,
      }),
    });
    if (!res.ok) {
      const text = await res.text();
      let msg = text;
      try {
        msg = JSON.parse(text).detail || msg;
      } catch {
        /* ignore */
      }
      throw new Error(msg);
    }
    return res.blob();
  },

  compareDocuments({ fileA, fileB, sourceA, sourceB }) {
    const fd = new FormData();
    if (fileA) fd.append("file_a", fileA);
    if (fileB) fd.append("file_b", fileB);
    if (sourceA) fd.append("source_a", sourceA);
    if (sourceB) fd.append("source_b", sourceB);
    return this.request("/api/compare", { method: "POST", body: fd });
  },

  knowledgeMap(source = "") {
    const q = source ? `?source=${encodeURIComponent(source)}` : "";
    return this.request(`/api/knowledge-map${q}`);
  },

  timeline(source = "") {
    const q = source ? `?source=${encodeURIComponent(source)}` : "";
    return this.request(`/api/timeline${q}`);
  },

  async transcribeAudio(blob, filename = "recording.webm") {
    const fd = new FormData();
    fd.append("file", blob, filename);
    const token = this.getToken();
    const headers = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${this.base}/api/stt`, {
      method: "POST",
      headers,
      body: fd,
    });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!res.ok) {
      const msg = data?.detail || text || "Speech recognition failed.";
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data?.text || "";
  },

  async ttsSpeak(text, model = null) {
    const body = { text: text || "" };
    if (model) body.model = model;
    const res = await fetch(`${this.base}/api/tts`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.getToken()}`,
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const errText = await res.text();
      let msg = errText;
      try {
        msg = JSON.parse(errText).detail || msg;
      } catch {
        /* ignore */
      }
      throw new Error(typeof msg === "string" ? msg : "Speech synthesis failed.");
    }
    return res.blob();
  },
};
