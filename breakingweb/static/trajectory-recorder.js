/**
 * BreakingWeb — Human Trajectory Recorder
 *
 * Records human interactions (clicks, typing, navigation) as a replayable
 * trajectory. Works alongside the benchmark toolbar.
 *
 * Usage: Loaded by the in-app benchmark toolbar when recording is enabled.
 *
 * Recorded events:
 *   - click: element bid/selector, text, role
 *   - input: field bid/selector, value typed
 *   - navigation: URL change
 *   - scroll: direction, amount
 *   - submit: form submission
 */
(function () {
  "use strict";

  var WAB_RECORDER = {
    recording: false,
    events: [],
    startTime: null,
    sessionId: null,
    envId: null,

    start: function (sessionId, envId) {
      this.recording = true;
      this.events = [];
      this.startTime = Date.now();
      this.sessionId = sessionId;
      this.envId = envId;
      this._attachListeners();
      console.log("[WAB] Recording started for session:", sessionId);
    },

    stop: function () {
      this.recording = false;
      this._detachListeners();
      console.log("[WAB] Recording stopped.", this.events.length, "events captured.");
      return this.events;
    },

    _record: function (type, detail) {
      if (!this.recording) return;
      this.events.push({
        step: this.events.length + 1,
        type: type,
        timestamp_ms: Date.now() - this.startTime,
        url: window.location.pathname + window.location.search,
        detail: detail,
      });
    },

    // --- Element identification ---
    _describeElement: function (el) {
      if (!el || !el.tagName) return null;
      var desc = {
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || "",
        bid: el.getAttribute("bid") || el.getAttribute("data-bid") || "",
        text: (el.textContent || "").trim().slice(0, 80),
        ariaLabel: el.getAttribute("aria-label") || "",
      };
      // CSS selector for replay
      if (el.id) {
        desc.selector = "#" + el.id;
      } else {
        var cls = Array.from(el.classList || []).slice(0, 3).join(".");
        desc.selector = el.tagName.toLowerCase() + (cls ? "." + cls : "");
      }
      return desc;
    },

    // --- Event handlers ---
    _onClick: function (e) {
      var el = e.target;
      // Skip toolbar clicks
      if (el.closest && el.closest("#wab-toolbar")) return;
      WAB_RECORDER._record("click", {
        element: WAB_RECORDER._describeElement(el),
        x: e.clientX,
        y: e.clientY,
      });
    },

    _onInput: function (e) {
      var el = e.target;
      if (el.closest && el.closest("#wab-toolbar")) return;
      // Debounce: update last event if same element
      var events = WAB_RECORDER.events;
      var last = events.length > 0 ? events[events.length - 1] : null;
      if (
        last &&
        last.type === "input" &&
        last.detail.element &&
        last.detail.element.selector ===
          WAB_RECORDER._describeElement(el).selector
      ) {
        last.detail.value = el.value || el.textContent || "";
        last.timestamp_ms = Date.now() - WAB_RECORDER.startTime;
        return;
      }
      WAB_RECORDER._record("input", {
        element: WAB_RECORDER._describeElement(el),
        value: el.value || el.textContent || "",
      });
    },

    _onKeydown: function (e) {
      // Only record special keys (Enter, Escape, Tab, etc.)
      if (e.key.length > 1 || e.ctrlKey || e.metaKey) {
        var el = e.target;
        if (el.closest && el.closest("#wab-toolbar")) return;
        WAB_RECORDER._record("keypress", {
          key: e.key,
          ctrl: e.ctrlKey,
          meta: e.metaKey,
          shift: e.shiftKey,
          element: WAB_RECORDER._describeElement(el),
        });
      }
    },

    _onScroll: function () {
      // Throttle: only record every 500ms
      if (WAB_RECORDER._scrollTimer) return;
      WAB_RECORDER._scrollTimer = setTimeout(function () {
        WAB_RECORDER._scrollTimer = null;
        WAB_RECORDER._record("scroll", {
          scrollTop: document.documentElement.scrollTop || document.body.scrollTop,
          scrollHeight: document.documentElement.scrollHeight,
          viewportHeight: window.innerHeight,
        });
      }, 500);
    },
    _scrollTimer: null,

    _lastUrl: "",
    _onUrlChange: function () {
      var url = window.location.pathname + window.location.search;
      if (url !== WAB_RECORDER._lastUrl) {
        WAB_RECORDER._lastUrl = url;
        WAB_RECORDER._record("navigate", { url: url });
      }
    },
    _urlInterval: null,

    _attachListeners: function () {
      document.addEventListener("click", this._onClick, true);
      document.addEventListener("input", this._onInput, true);
      document.addEventListener("keydown", this._onKeydown, true);
      window.addEventListener("scroll", this._onScroll, true);
      this._lastUrl = window.location.pathname + window.location.search;
      this._urlInterval = setInterval(this._onUrlChange, 300);
    },

    _detachListeners: function () {
      document.removeEventListener("click", this._onClick, true);
      document.removeEventListener("input", this._onInput, true);
      document.removeEventListener("keydown", this._onKeydown, true);
      window.removeEventListener("scroll", this._onScroll, true);
      if (this._urlInterval) {
        clearInterval(this._urlInterval);
        this._urlInterval = null;
      }
    },
  };

  // Expose globally for the in-app benchmark toolbar
  window.__WAB_RECORDER = WAB_RECORDER;
})();
