/** Voice-to-text: live preview, auto-stop on silence, browser speech API. */

const $stt = (s, r = document) => r.querySelector(s);

const STTService = {
  enabled: false,
  backendEnabled: false,

  _notify(msg, ms = 3000) {
    if (typeof toast === "function") toast(msg, ms);
  },
  _active: false,
  _recognition: null,
  _finalParts: [],
  _interim: "",
  _prefix: "",
  _silenceTimer: null,
  _maxTimer: null,
  _stopping: false,
  SILENCE_MS: 2200,
  MAX_LISTEN_MS: 45000,

  hasBrowserStt() {
    return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  },

  setBackendEnabled(on) {
    this.backendEnabled = !!on;
  },

  setEnabled(on) {
    this.enabled = !!on;
    const mic = $stt("#btn-mic");
    if (mic) {
      mic.disabled = !on;
      mic.title = on
        ? "Voice to text — click and speak"
        : "Voice input needs Chrome or Edge with microphone access";
    }
  },

  initUi() {
    $stt("#btn-voice-done")?.addEventListener("click", (e) => {
      e.preventDefault();
      this.stop({ reason: "done" });
    });
    $stt("#btn-voice-cancel")?.addEventListener("click", (e) => {
      e.preventDefault();
      this.cancel();
    });
    $stt("#btn-mic")?.addEventListener("click", (e) => {
      e.preventDefault();
      this.onMicClick();
    });
  },

  onMicClick() {
    if (!this.enabled) {
      this._notify(
        this.hasBrowserStt()
          ? "Allow microphone access when prompted, then try again."
          : "Voice input works best in Chrome or Edge. Type your question if needed.",
        5000,
      );
      return;
    }
    if (this._active) {
      this.stop({ reason: "done" });
      return;
    }
    this.start();
  },

  _getTranscript() {
    const body = [...this._finalParts, this._interim].join(" ").replace(/\s+/g, " ").trim();
    if (!body) return this._prefix.trim();
    if (!this._prefix.trim()) return body;
    return `${this._prefix.trim()} ${body}`;
  },

  _syncTextarea() {
    const ta = $stt("#chat-question");
    if (!ta) return;
    ta.value = this._getTranscript();
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  },

  _setStatus(text) {
    const el = $stt("#voice-input-status");
    if (el) el.textContent = text;
  },

  _showBar(show) {
    const bar = $stt("#voice-input-bar");
    const ta = $stt("#chat-question");
    if (bar) bar.classList.toggle("hidden", !show);
    if (ta) ta.classList.toggle("is-voice-active", show);
    const mic = $stt("#btn-mic");
    if (mic) {
      mic.classList.toggle("is-recording", show);
      mic.setAttribute("aria-pressed", show ? "true" : "false");
      mic.setAttribute("aria-label", show ? "Stop voice input" : "Voice to text");
    }
  },

  _resetSilenceTimer() {
    clearTimeout(this._silenceTimer);
    if (!this._active) return;
    this._silenceTimer = setTimeout(() => {
      if (this._active && (this._finalParts.length || this._interim)) {
        this.stop({ reason: "silence", silent: true });
      }
    }, this.SILENCE_MS);
  },

  _clearTimers() {
    clearTimeout(this._silenceTimer);
    clearTimeout(this._maxTimer);
    this._silenceTimer = null;
    this._maxTimer = null;
  },

  async start() {
    if (this._active) return;

    if (this.hasBrowserStt()) {
      await this._startBrowser();
      return;
    }

    if (this.backendEnabled && navigator.mediaDevices?.getUserMedia) {
      this._notify("Recording… speak, then click Done.", 3500);
      await this._startMediaFallback();
      return;
    }

    this._notify("Use Chrome or Edge for voice input, or type your question.", 5000);
  },

  async _startBrowser() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const ta = $stt("#chat-question");
    this._prefix = ta?.value?.trim() ? `${ta.value.trim()} ` : "";
    this._finalParts = [];
    this._interim = "";
    this._stopping = false;
    this._browserError = null;

    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = navigator.language || "en-US";
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      this._setStatus("Listening… speak now");
    };

    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0]?.transcript || "";
        if (!t) continue;
        if (e.results[i].isFinal) {
          this._finalParts.push(t.trim());
          this._interim = "";
        } else {
          this._interim = t.trim();
        }
      }
      this._syncTextarea();
      this._resetSilenceTimer();
      if (this._interim) {
        this._setStatus("Hearing you…");
      }
    };

    rec.onerror = (e) => {
      const code = e.error || "";
      if (code === "not-allowed") {
        this._browserError =
          "Microphone blocked. Click the lock icon in the address bar and allow the mic.";
        this.stop({ reason: "error", silent: true });
        this._notify(this._browserError, 6000);
      } else if (code === "network") {
        this._browserError = "Speech needs an internet connection in this browser.";
        this.stop({ reason: "error", silent: true });
        this._notify(this._browserError, 5000);
      } else if (code !== "aborted" && code !== "no-speech") {
        this._browserError = `Could not hear you (${code}). Try again.`;
      }
      if (code === "no-speech" && this._active && !this._stopping) {
        this._setStatus("Didn't catch that — keep speaking…");
      }
    };

    rec.onend = () => {
      if (this._stopping || !this._active) return;
      try {
        rec.start();
      } catch {
        this.stop({ reason: "ended" });
      }
    };

    this._recognition = rec;
    this._active = true;
    this._showBar(true);
    this._syncTextarea();
    ta?.focus();

    this._maxTimer = setTimeout(() => {
      if (this._active) this.stop({ reason: "limit", silent: true });
    }, this.MAX_LISTEN_MS);

    try {
      rec.start();
      this._resetSilenceTimer();
    } catch (err) {
      this._active = false;
      this._showBar(false);
      this._clearTimers();
      this._notify(err.message || "Could not start microphone.");
    }
  },

  async stop({ reason = "done", silent = false } = {}) {
    if (!this._active || this._stopping) return;

    if (this._mediaRecorder) {
      this._stopping = true;
      this._active = false;
      this._showBar(false);
      try {
        await this._finishMediaFallback();
      } catch (err) {
        this._notify(err.message || "Could not transcribe speech.", 5000);
      } finally {
        this._stopping = false;
      }
      return;
    }

    this._stopping = true;
    this._active = false;
    this._clearTimers();

    const rec = this._recognition;
    this._recognition = null;
    if (rec) {
      try {
        rec.onend = null;
        rec.stop();
      } catch {
        /* ignore */
      }
    }

    this._showBar(false);
    this._syncTextarea();

    const text = this._getTranscript().trim();
    const ta = $stt("#chat-question");
    if (ta) ta.value = text;

    this._stopping = false;
    this._finalParts = [];
    this._interim = "";
    this._prefix = "";

    if (!text && reason !== "cancel") {
      if (!silent) {
        this._notify("No speech heard. Check your mic and try again.", 4000);
      }
      return;
    }

    if (text && !silent && reason !== "cancel") {
      ta?.focus();
      if (reason === "silence" || reason === "done") {
        this._notify("Voice added — edit or press Send.", 2200);
      }
    }
  },

  cancel() {
    if (!this._active) return;
    const saved = this._prefix.trim();
    this._stopping = true;
    this._active = false;
    this._clearTimers();

    if (this._mediaRecorder) {
      try {
        if (this._mediaRecorder.state !== "inactive") this._mediaRecorder.stop();
      } catch {
        /* ignore */
      }
      this._mediaRecorder = null;
      this._chunks = [];
      if (this._stream) {
        this._stream.getTracks().forEach((t) => t.stop());
        this._stream = null;
      }
      this._showBar(false);
      const ta = $stt("#chat-question");
      if (ta) ta.value = saved;
      this._stopping = false;
      return;
    }

    const rec = this._recognition;
    this._recognition = null;
    if (rec) {
      try {
        rec.onend = null;
        rec.stop();
      } catch {
        /* ignore */
      }
    }
    this._showBar(false);
    this._finalParts = [];
    this._interim = "";
    const ta = $stt("#chat-question");
    if (ta) ta.value = saved;
    this._prefix = "";
    this._stopping = false;
  },

  /* Fallback: record audio and send to server (often blocked without HF Inference). */
  _mediaRecorder: null,
  _chunks: [],
  _stream: null,

  async _startMediaFallback() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this._stream = stream;
    this._chunks = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType: mime });
    recorder.ondataavailable = (e) => {
      if (e.data?.size) this._chunks.push(e.data);
    };
    recorder.start(250);
    this._mediaRecorder = recorder;
    this._active = true;
    this._showBar(true);
    this._setStatus("Recording… click Done when finished");
  },

  async _finishMediaFallback() {
    const recorder = this._mediaRecorder;
    if (!recorder) return;
    const blob = await new Promise((resolve, reject) => {
      recorder.onstop = () => {
        const b = new Blob(this._chunks, { type: recorder.mimeType || "audio/webm" });
        this._chunks = [];
        this._mediaRecorder = null;
        if (this._stream) {
          this._stream.getTracks().forEach((t) => t.stop());
          this._stream = null;
        }
        b.size ? resolve(b) : reject(new Error("No audio captured."));
      };
      try {
        if (recorder.state === "recording") recorder.requestData();
      } catch {
        /* ignore */
      }
      recorder.stop();
    });
    const text = await API.transcribeAudio(blob);
    const ta = $stt("#chat-question");
    if (ta) {
      const cur = ta.value.trim();
      ta.value = cur ? `${cur} ${text}` : text;
      ta.focus();
    }
    this._notify("Added — edit or press Send.", 2500);
  },
};
