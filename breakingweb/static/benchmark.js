/**
 * BreakingWeb — Shared Benchmark State Harness
 *
 * Loaded by every benchmark page. Initializes window.__benchmarkState and
 * provides helpers for logging events, updating data, and marking completion.
 *
 * Dual-channel state exposure:
 *   1. window.__benchmarkState  (JS — primary)
 *   2. <div id="__benchmark_state"> (DOM — fallback for DOM-only agents)
 */
(function () {
  "use strict";

  // ── Initialise benchmark state ──────────────────────────────────────
  window.__benchmarkState = {
    pageId: "",
    completed: false,
    success: false,
    startTime: Date.now(),
    endTime: null,
    data: {},
    events: [],
  };

  // ── DOM sync ────────────────────────────────────────────────────────
  function syncToDOM() {
    var el = document.getElementById("__benchmark_state");
    if (!el) {
      el = document.createElement("div");
      el.id = "__benchmark_state";
      el.style.display = "none";
      el.setAttribute("aria-hidden", "true");
      document.body.appendChild(el);
    }
    el.textContent = JSON.stringify(window.__benchmarkState);
    el.dataset.completed = String(window.__benchmarkState.completed);
    el.dataset.success = String(window.__benchmarkState.success);
  }

  // ── Public helpers ──────────────────────────────────────────────────

  /** Log an interaction event (for debugging / trajectory analysis). */
  window.__benchmarkLog = function (eventType, detail) {
    window.__benchmarkState.events.push({
      type: eventType,
      detail: detail || {},
      timestamp: Date.now(),
    });
    syncToDOM();
  };

  /** Mark the task as completed (success or failure). */
  window.__benchmarkComplete = function (success, data) {
    window.__benchmarkState.completed = true;
    window.__benchmarkState.success = Boolean(success);
    window.__benchmarkState.endTime = Date.now();
    if (data) {
      Object.assign(window.__benchmarkState.data, data);
    }
    syncToDOM();
  };

  /** Update page-specific data without marking complete. */
  window.__benchmarkUpdate = function (data) {
    Object.assign(window.__benchmarkState.data, data);
    syncToDOM();
  };

  // ── Initial sync ───────────────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncToDOM);
  } else {
    syncToDOM();
  }
})();
