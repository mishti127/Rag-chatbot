/** Text-to-speech: Hugging Face via /api/tts, with browser speech fallback. */



const TTSService = {

  enabled: false,

  backendEnabled: false,

  _audio: null,

  _objectUrl: null,

  _utterance: null,

  _loading: false,



  hasBrowserTts() {

    return typeof window !== "undefined" && "speechSynthesis" in window;

  },



  setBackendEnabled(on) {

    this.backendEnabled = !!on;

  },



  setEnabled(on) {

    this.enabled = !!on;

  },



  stop() {

    if (this._audio) {

      this._audio.pause();

      this._audio.currentTime = 0;

      this._audio = null;

    }

    if (this._objectUrl) {

      URL.revokeObjectURL(this._objectUrl);

      this._objectUrl = null;

    }

    if (this._utterance) {

      this._utterance.onend = null;

      this._utterance.onerror = null;

      this._utterance = null;

    }

    if (this.hasBrowserTts()) {

      window.speechSynthesis.cancel();

    }

    this._loading = false;

    document.querySelectorAll(".tts-listen-btn.is-playing").forEach((b) => {

      b.classList.remove("is-playing");

      b.setAttribute("aria-label", "Listen");

    });

  },



  isPlaying() {

    return Boolean(

      (this._audio && !this._audio.paused) ||

        this._utterance ||

        (this.hasBrowserTts() && window.speechSynthesis.speaking),

    );

  },



  speakBrowser(text) {

    return new Promise((resolve, reject) => {

      if (!this.hasBrowserTts()) {

        reject(new Error("Text-to-speech is not supported in this browser."));

        return;

      }

      const utter = new SpeechSynthesisUtterance(text);

      utter.rate = 1;

      utter.pitch = 1;

      const voices = window.speechSynthesis.getVoices();

      const en =

        voices.find((v) => v.lang.startsWith("en") && v.localService) ||

        voices.find((v) => v.lang.startsWith("en")) ||

        voices[0];

      if (en) utter.voice = en;



      this._utterance = utter;

      utter.onend = () => {

        this.stop();

        resolve();

      };

      utter.onerror = (e) => {

        const msg = e?.error && e.error !== "canceled" ? String(e.error) : "Speech failed.";

        this.stop();

        reject(new Error(msg));

      };

      window.speechSynthesis.cancel();

      window.speechSynthesis.speak(utter);

    });

  },



  async speakBackend(text) {

    const blob = await API.ttsSpeak(text);

    this._objectUrl = URL.createObjectURL(blob);

    this._audio = new Audio(this._objectUrl);

    await new Promise((resolve, reject) => {

      this._audio.onended = () => {

        this.stop();

        resolve();

      };

      this._audio.onerror = () => {

        reject(new Error("Could not play audio."));

      };

      this._audio.play().catch(reject);

    });

  },



  async speak(text) {

    const raw = typeof text === "function" ? text() : text;

    const cleaned = (raw || "").trim();

    if (!cleaned) {

      if (typeof toast === "function") toast("Nothing to read aloud.");

      return;

    }

    if (!this.enabled) {

      if (typeof toast === "function") {

        toast("Text-to-speech is not available in this browser.");

      }

      return;

    }

    if (this._loading) return;



    this.stop();

    this._loading = true;

    const buttons = document.querySelectorAll(".tts-listen-btn");

    buttons.forEach((b) => {

      b.disabled = true;

    });



    try {

      if (this.backendEnabled) {

        try {

          await this.speakBackend(cleaned);

          return;

        } catch (err) {

          if (this.hasBrowserTts()) {

            if (typeof toast === "function") {

              toast("Cloud speech unavailable — using your browser voice.");

            }

            await this.speakBrowser(cleaned);

            return;

          }

          throw err;

        }

      }

      if (this.hasBrowserTts()) {

        await this.speakBrowser(cleaned);

        return;

      }

      throw new Error("Text-to-speech is not available.");

    } catch (err) {

      if (typeof toast === "function") toast(err.message || "Speech failed.");

      this.stop();

    } finally {

      this._loading = false;

      buttons.forEach((b) => {

        b.disabled = !this.enabled;

      });

    }

  },



  createListenButton(getText, label = "Listen") {

    const btn = document.createElement("button");

    btn.type = "button";

    btn.className = "btn btn-ghost btn-sm tts-listen-btn";

    btn.setAttribute("aria-label", label);

    btn.title = label;

    btn.disabled = !this.enabled;

    btn.innerHTML =

      '<span class="tts-listen-icon" aria-hidden="true">&#128266;</span><span class="tts-listen-label">Listen</span>';

    btn.addEventListener("click", (e) => {

      e.preventDefault();

      e.stopPropagation();

      if (this.isPlaying()) {

        this.stop();

        return;

      }

      btn.classList.add("is-playing");

      this.speak(getText).finally(() => btn.classList.remove("is-playing"));

    });

    return btn;

  },



  mountListenBar(container, getText, options = {}) {

    if (!container) return null;

    let bar = container.querySelector(":scope > .tts-toolbar");

    if (!bar) {

      bar = document.createElement("div");

      bar.className = "tts-toolbar";

      if (options.prepend) container.prepend(bar);

      else container.appendChild(bar);

    }

    bar.innerHTML = "";

    bar.appendChild(this.createListenButton(getText, options.label));

    return bar;

  },

  cleanText(raw) {
    return (raw || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s*\[[^\]]+\]\s*/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  },

  appendListenBar(parent, getText, className = "content-tts-bar") {
    if (!this.enabled || !parent) return null;
    const bar = document.createElement("div");
    bar.className = className;
    bar.appendChild(this.createListenButton(getText));
    parent.appendChild(bar);
    return bar;
  },

};



// Chrome loads voices asynchronously

if (typeof window !== "undefined" && window.speechSynthesis) {

  window.speechSynthesis.onvoiceschanged = () => {};

}

