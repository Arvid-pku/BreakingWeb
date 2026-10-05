"""
Visualize BreakingWeb agent trajectories alongside live pages.

Generates a self-contained HTML file that shows:
- The actual benchmark page in an iframe (left)
- Step-by-step trajectory timeline with actions and thoughts (right)
- Play/pause/step controls to walk through the agent's actions
- Summary dashboard with pass/fail, scores, primitives
- Prompt drawer showing the exact prompts fed to the agent

Requires the BreakingWeb server to be running for the iframe pages.

Usage:
    # Generate visualization (auto-starts server, opens browser)
    python -m breakingweb.visualize results/breakingweb/qwen3.5-35b-a3b-v5.json

    # Custom output path
    python -m breakingweb.visualize results/breakingweb/qwen3.5-35b-a3b-v5.json \
        --output viz.html

    # Don't auto-open browser
    python -m breakingweb.visualize results/breakingweb/qwen3.5-35b-a3b-v5.json --no-open

    # Use a different server URL (if already running)
    python -m breakingweb.visualize results/breakingweb/qwen3.5-35b-a3b-v5.json \
        --server-url http://localhost:8080
"""

import argparse
import html
import json
import sys
from pathlib import Path

from .result_utils import (
    build_manifest_task_meta,
    load_embedded_task_meta,
    summary_total_tasks,
)

# Maximum content length for observation messages embedded in the HTML.
# The first user message (initial instruction) and all system/assistant
# messages are kept in full; subsequent user messages (accessibility tree
# snapshots) are truncated to this limit.
_MAX_OBS_CONTENT = 500


def _truncate_messages(messages: list[dict]) -> list[dict]:
    """Return a copy of *messages* with large observation content trimmed."""
    out: list[dict] = []
    seen_first_user = False
    for msg in messages:
        msg = dict(msg)  # shallow copy
        if msg.get("role") == "user":
            if not seen_first_user:
                seen_first_user = True
            elif len(msg.get("content", "")) > _MAX_OBS_CONTENT:
                msg["content"] = (
                    msg["content"][:_MAX_OBS_CONTENT]
                    + "\n[... observation truncated ...]"
                )
        out.append(msg)
    return out


def _normalize_target_payload(target: object) -> dict:
    """Normalize a recorded target payload into the nested shape used by replay JS."""
    if isinstance(target, str):
        return {"bid": target}
    if not isinstance(target, dict):
        return {}

    payload: dict = {}
    for key in ("bid", "role", "name", "selector", "nth", "bbox"):
        value = target.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _normalize_step_targets(step: dict) -> dict:
    """Coerce flat or partially-shaped `targets` payloads into nested refs."""
    normalized_step = dict(step)
    raw_targets = step.get("targets") or {}
    if not isinstance(raw_targets, dict):
        normalized_step["targets"] = {}
        return normalized_step

    normalized_targets: dict[str, dict] = {}

    # Current agent output can be either flat:
    #   {"ref": "172", "role": "button", "name": "Save"}
    # or nested:
    #   {"ref": {"role": "button", "name": "Save"}}
    flat_target_keys = {"bid", "role", "name", "selector", "nth", "bbox"}
    has_flat_target = bool(flat_target_keys.intersection(raw_targets))
    ref_is_scalar = isinstance(raw_targets.get("ref"), str)
    if has_flat_target or ref_is_scalar:
        ref_payload = _normalize_target_payload(raw_targets.get("ref"))
        for key in flat_target_keys:
            value = raw_targets.get(key)
            if value is not None and key not in ref_payload:
                ref_payload[key] = value
        if ref_payload:
            normalized_targets["ref"] = ref_payload

    for key in ("ref", "from_ref", "to_ref"):
        payload = _normalize_target_payload(raw_targets.get(key))
        if payload:
            existing = normalized_targets.get(key, {})
            normalized_targets[key] = {**payload, **existing}

    normalized_step["targets"] = normalized_targets
    return normalized_step


def _build_replay_meta(result: dict) -> dict | None:
    """Synthesize replay metadata from task registry if not already present."""
    if result.get("replay", {}).get("kind") == "env":
        return None  # already set
    task_id = result.get("task_id", "")
    if not task_id:
        return None
    try:
        from .tasks._registry import tasks_by_env
        for env_id, tasks in tasks_by_env().items():
            for t in tasks:
                if t.task_id == task_id:
                    return {
                        "kind": "env",
                        "env_id": env_id,
                        "task_id": task_id,
                        "seed": result.get("seed"),
                        "base_url": f"/env/{env_id}",
                        "start_path": t.start_path or "/",
                    }
    except Exception:
        pass
    return None


def _inline_screenshot_if_relative(step: dict, base_dir: "Path | None") -> dict:
    """If a step's `screenshot` field is a relative path (new-style), read the
    PNG from disk and inline as a base64 data URI so the rendered HTML remains
    a self-contained artifact. Data URI strings are passed through unchanged.
    """
    shot = step.get("screenshot")
    if not isinstance(shot, str) or not shot:
        return step
    if shot.startswith("data:"):
        return step
    if base_dir is None:
        return step
    import base64 as _b64
    png_path = (base_dir / shot).resolve()
    try:
        if png_path.is_file():
            b = png_path.read_bytes()
            step["screenshot"] = f"data:image/png;base64,{_b64.b64encode(b).decode('ascii')}"
    except Exception:
        pass
    return step


def _prepare_result_for_js(result: dict, *, trajectory_base_dir: "Path | None" = None) -> dict:
    """Return a browser-safe copy of a result payload for the embedded viewer.

    If the result has a `trajectory_path` pointer (new summary.json schema)
    and `trajectory_base_dir` is given, load the per-task trajectory.json and
    splice its trajectory[] into this result before rendering. Relative
    screenshot paths are re-encoded to base64 so the final HTML is
    self-contained.
    """
    result_copy = dict(result)
    agent = dict(result_copy.get("agent", {}))
    raw_msgs = agent.get("messages", [])
    raw_traj = agent.get("trajectory", [])

    # If trajectory is empty but a pointer exists, follow it.
    traj_path = result_copy.get("trajectory_path")
    task_dir: "Path | None" = None
    if not raw_traj and traj_path and trajectory_base_dir is not None:
        full = (trajectory_base_dir / traj_path).resolve()
        if full.is_file():
            try:
                per_task = json.loads(full.read_text())
                raw_traj = per_task.get("agent", {}).get("trajectory", [])
                task_dir = full.parent
            except Exception:
                pass

    agent["messages"] = _truncate_messages(raw_msgs) if raw_msgs else []
    agent["trajectory"] = [
        _inline_screenshot_if_relative(_normalize_step_targets(step), task_dir)
        for step in raw_traj
        if isinstance(step, dict)
    ]
    result_copy["agent"] = agent
    replay = _build_replay_meta(result)
    if replay:
        result_copy["replay"] = replay
    return result_copy


def generate_html(data: dict, server_url: str, *, trajectory_base_dir: "Path | None" = None) -> str:
    """Generate the visualization HTML from result data."""
    # New schema (summary.json from stock harness) puts model at top level.
    # Legacy schema keeps it inside .agent.
    model = data.get("model") or data.get("agent", {}).get("model", "unknown")
    provider = data.get("provider") or data.get("agent", {}).get("provider", "unknown")
    summary = data.get("summary", {})
    results = data.get("results", [])
    task_meta = load_embedded_task_meta(data)
    total_tasks = summary_total_tasks(summary) or len(results)

    # Build a lightweight copy of results with truncated messages for embedding.
    # When a summary.json references per-task trajectory.json files, follow
    # those pointers + re-encode each step's PNG as base64 so the emitted
    # HTML remains a self-contained artifact.
    results_for_js = [
        _prepare_result_for_js(r, trajectory_base_dir=trajectory_base_dir)
        for r in results
    ]

    results_json = json.dumps(results_for_js)
    task_meta_json = json.dumps(task_meta)

    # NOTE: innerHTML usage below operates exclusively on trusted local data
    # (our own benchmark results) and all dynamic strings pass through
    # escapeHtml().  This is a self-contained visualization file, not a
    # web-facing application, so XSS is not a concern here.

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>BreakingWeb — {html.escape(model)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ height: 100%; overflow: clip; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    background: #f5f4f1;
    color: #1a1a1a;
    font-size: 13px;
    -webkit-font-smoothing: antialiased;
}}

/* ── Topbar ─────────────────────────────────────────────────── */
.topbar {{
    height: 44px; padding: 0 20px;
    display: flex; align-items: center; gap: 16px;
    border-bottom: 1px solid #e0ddd8;
    background: #faf9f7;
}}
.topbar h1 {{
    font-size: 13px; font-weight: 700; color: #1a1a1a;
    letter-spacing: -0.01em; white-space: nowrap;
}}
.topbar .model {{
    font-size: 11px; color: #6b6560;
    font-weight: 500;
}}
.topbar .summary {{
    font-size: 12px; color: #6b6560; margin-left: auto; font-weight: 500;
    font-variant-numeric: tabular-nums;
}}
.topbar .mode-toggle {{ display: flex; gap: 0; margin-left: 12px; }}
.topbar .mode-toggle button {{
    background: transparent; border: 1px solid #d4d0ca;
    color: #6b6560; padding: 4px 12px; cursor: pointer; font-size: 11px;
    font-weight: 500; transition: background 0.15s, color 0.15s;
}}
.topbar .mode-toggle button:first-child {{ border-radius: 4px 0 0 4px; }}
.topbar .mode-toggle button:last-child {{ border-radius: 0 4px 4px 0; border-left: none; }}
.topbar .mode-toggle button.active {{
    background: #1a1a1a; border-color: #1a1a1a; color: #faf9f7;
}}
.topbar .mode-toggle button:hover:not(.active) {{ background: #eceae5; }}

/* ── Layout ─────────────────────────────────────────────────── */
.main {{ display: flex; height: calc(100vh - 44px); }}

/* ── Sidebar ────────────────────────────────────────────────── */
.sidebar {{
    width: 232px; min-width: 232px;
    background: #faf9f7;
    border-right: 1px solid #e0ddd8;
    overflow-y: auto; padding: 6px;
}}
.sidebar::-webkit-scrollbar {{ width: 3px; }}
.sidebar::-webkit-scrollbar-track {{ background: transparent; }}
.sidebar::-webkit-scrollbar-thumb {{ background: #d4d0ca; border-radius: 2px; }}

.page-item {{
    padding: 8px 10px; cursor: pointer; font-size: 12px;
    border-radius: 5px; margin-bottom: 1px;
    transition: background 0.12s;
}}
.page-item:hover {{ background: #eceae5; }}
.page-item.active {{ background: #e4e1db; }}
.page-item .page-title {{
    font-weight: 600; color: #1a1a1a; margin-bottom: 2px;
    line-height: 1.3;
}}
.page-item .page-meta {{
    color: #918b83; font-size: 11px;
    display: flex; align-items: center; gap: 6px;
}}

.badge {{
    display: inline-block; padding: 1px 5px; border-radius: 3px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.03em;
}}
.badge.pass {{ background: #dff5e3; color: #1a7a34; }}
.badge.fail {{ background: #fde4e4; color: #b52828; }}

/* ── Center panel ───────────────────────────────────────────── */
.page-view {{ flex: 1; display: flex; flex-direction: column; min-width: 0; }}
.page-toolbar {{
    padding: 8px 16px;
    display: flex; align-items: flex-start; gap: 12px; font-size: 12px;
    background: #faf9f7;
    border-bottom: 1px solid #e0ddd8;
}}
.page-toolbar .instruction {{
    color: #4a4540; flex: 1;
    line-height: 1.5; max-height: 54px; overflow-y: auto;
}}
.page-toolbar .instruction::-webkit-scrollbar {{ width: 3px; }}
.page-toolbar .instruction::-webkit-scrollbar-thumb {{ background: #d4d0ca; border-radius: 2px; }}
.page-toolbar .score {{
    font-weight: 700; font-size: 12px;
    white-space: nowrap; flex-shrink: 0;
    font-variant-numeric: tabular-nums;
}}
.page-toolbar .score.pass {{ color: #1a7a34; }}
.page-toolbar .score.fail {{ color: #b52828; }}

.page-frame {{ flex: 1; position: relative; background: #f5f4f1; }}
.page-frame iframe {{
    width: 100%; height: 100%; border: none;
    background: #fff;
}}
.replay-status {{
    position: absolute; top: 10px; right: 10px;
    background: #1a1a1a; color: #faf9f7;
    padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: 500;
    display: none; z-index: 999;
}}

/* ── Trajectory panel ───────────────────────────────────────── */
.trajectory-panel {{
    width: 380px; min-width: 380px;
    background: #faf9f7;
    border-left: 1px solid #e0ddd8;
    display: flex; flex-direction: column;
}}
.traj-header {{
    padding: 10px 14px;
    border-bottom: 1px solid #e0ddd8;
    font-size: 12px; font-weight: 600;
    display: flex; align-items: center; gap: 8px;
    color: #1a1a1a;
}}
.traj-header .step-counter {{ color: #918b83; font-weight: 400; }}
.traj-controls {{ display: flex; gap: 3px; margin-left: auto; }}
.traj-controls button {{
    background: transparent; border: 1px solid #d4d0ca;
    color: #4a4540; padding: 3px 9px; cursor: pointer;
    border-radius: 4px; font-size: 12px; transition: background 0.12s;
}}
.traj-controls button:hover {{ background: #eceae5; }}
.traj-controls button.active {{
    background: #1a1a1a; border-color: #1a1a1a; color: #faf9f7;
}}

/* ── Prompt drawer ──────────────────────────────────────────── */
.prompt-drawer {{ border-bottom: 1px solid #e0ddd8; }}
.prompt-drawer-toggle {{
    padding: 7px 14px; cursor: pointer;
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600; color: #918b83;
    transition: color 0.12s;
    user-select: none;
}}
.prompt-drawer-toggle:hover {{ color: #4a4540; }}
.prompt-drawer-toggle .chevron {{
    transition: transform 0.15s; font-size: 9px; display: inline-block;
}}
.prompt-drawer-toggle .chevron.open {{ transform: rotate(90deg); }}
.prompt-drawer-toggle .verbose-toggle {{
    margin-left: auto; display: flex; align-items: center; gap: 5px;
    font-weight: 400; font-size: 10px; color: #918b83;
}}
.prompt-drawer-toggle .verbose-toggle label {{ cursor: pointer; }}
.verbose-switch {{
    appearance: none; -webkit-appearance: none;
    width: 24px; height: 12px; border-radius: 6px;
    background: #d4d0ca; cursor: pointer;
    position: relative; transition: background 0.15s;
    vertical-align: middle;
}}
.verbose-switch:checked {{ background: #1a1a1a; }}
.verbose-switch::after {{
    content: ''; position: absolute; top: 1.5px; left: 1.5px;
    width: 9px; height: 9px; border-radius: 50%;
    background: #faf9f7; transition: transform 0.15s;
}}
.verbose-switch:checked::after {{ transform: translateX(12px); }}

.prompt-drawer-content {{
    max-height: 0; overflow: hidden;
    transition: max-height 0.25s ease-out;
}}
.prompt-drawer-content.open {{ max-height: 400px; overflow-y: auto; }}
.prompt-drawer-content::-webkit-scrollbar {{ width: 3px; }}
.prompt-drawer-content::-webkit-scrollbar-thumb {{ background: #d4d0ca; border-radius: 2px; }}

.prompt-section {{ padding: 6px 14px 10px; }}
.prompt-section-label {{
    font-size: 10px; font-weight: 600; color: #918b83;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;
}}
.prompt-section-body {{
    font-family: "SF Mono", ui-monospace, "Cascadia Mono", "Segoe UI Mono", monospace;
    font-size: 11px; line-height: 1.55;
    color: #4a4540;
    background: #f0eeea; border-radius: 4px;
    padding: 10px 12px; white-space: pre-wrap; word-break: break-word;
    max-height: 180px; overflow-y: auto;
}}
.prompt-section-body::-webkit-scrollbar {{ width: 3px; }}
.prompt-section-body::-webkit-scrollbar-thumb {{ background: #d4d0ca; border-radius: 2px; }}

.msg-card {{
    padding: 8px 10px; margin: 3px 0; border-radius: 4px;
    font-size: 11px;
    border-left: 3px solid transparent;
}}
.msg-card.msg-system {{ background: #f0eeea; border-left-color: #918b83; }}
.msg-card.msg-user {{ background: #faf9f7; border-left-color: #c4a35a; }}
.msg-card.msg-assistant {{ background: #f0eeea; border-left-color: #1a7a34; }}
.msg-role {{
    display: inline-block; font-size: 9px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 3px;
}}
.msg-role.role-system {{ color: #918b83; }}
.msg-role.role-user {{ color: #c4a35a; }}
.msg-role.role-assistant {{ color: #1a7a34; }}
.msg-body {{
    font-family: "SF Mono", ui-monospace, "Cascadia Mono", "Segoe UI Mono", monospace;
    font-size: 10px; line-height: 1.45;
    color: #4a4540;
    white-space: pre-wrap; word-break: break-word;
    max-height: 120px; overflow-y: auto;
}}
.msg-body::-webkit-scrollbar {{ width: 3px; }}
.msg-body::-webkit-scrollbar-thumb {{ background: #d4d0ca; border-radius: 2px; }}

.no-prompt {{ padding: 16px 14px; text-align: center; color: #918b83; font-size: 11px; }}

/* ── Trajectory steps ───────────────────────────────────────── */
.traj-steps {{ flex: 1; overflow-y: auto; padding: 6px; }}
.traj-steps::-webkit-scrollbar {{ width: 3px; }}
.traj-steps::-webkit-scrollbar-track {{ background: transparent; }}
.traj-steps::-webkit-scrollbar-thumb {{ background: #d4d0ca; border-radius: 2px; }}

.step {{
    padding: 7px 10px; margin-bottom: 2px; border-radius: 4px;
    font-size: 12px; cursor: pointer;
    transition: background 0.12s;
    border-left: 3px solid transparent;
}}
.step:hover {{ background: #eceae5; }}
.step.current {{ background: #e4e1db; border-left-color: #1a1a1a; }}
.step.executed {{ border-left-color: #1a7a34; }}
.step.exec-error {{ border-left-color: #b52828; }}
.step .step-num {{ color: #918b83; font-weight: 600; margin-right: 4px; font-size: 11px; }}
.step .action-name {{ color: #1a1a1a; font-weight: 600; }}
.step .action-target {{ color: #6b6560; }}
.step .action-value {{ color: #5a7a3a; }}
.step .status {{ color: #918b83; font-size: 11px; margin-top: 2px; }}
.step .elapsed {{ color: #b8b2a8; font-size: 10px; float: right; font-variant-numeric: tabular-nums; }}
.step-thought {{ margin-top: 4px; }}
.step-thought summary {{
    cursor: pointer; color: #6b6560; font-size: 11px;
    list-style: none; font-weight: 500;
}}
.step-thought summary::-webkit-details-marker {{ display: none; }}
.step-thought summary:hover {{ color: #1a1a1a; }}
.step-thought .thought-body {{
    color: #6b6560; font-size: 11px;
    margin-top: 4px; white-space: pre-wrap; line-height: 1.5;
    padding: 6px 8px; border-radius: 3px;
    background: #f0eeea;
}}

.step-screenshot {{ margin-top: 4px; }}
.step-screenshot summary {{
    cursor: pointer; color: #6b6560; font-size: 11px;
    list-style: none; font-weight: 500;
}}
.step-screenshot summary::-webkit-details-marker {{ display: none; }}
.step-screenshot summary:hover {{ color: #1a1a1a; }}
.step-screenshot .step-screenshot-img {{
    display: block; margin-top: 4px;
    max-width: 100%; border: 1px solid #d4d0ca; border-radius: 3px;
    background: #fff;
}}

/* ── Eval panel ─────────────────────────────────────────────── */
.eval-panel {{
    padding: 10px 14px;
    border-top: 1px solid #e0ddd8;
    font-size: 11px; max-height: 260px; overflow-y: auto;
}}
.eval-panel::-webkit-scrollbar {{ width: 3px; }}
.eval-panel::-webkit-scrollbar-thumb {{ background: #d4d0ca; border-radius: 2px; }}
.eval-panel .criteria {{ margin-top: 4px; }}
.eval-panel .criterion {{ padding: 2px 0; }}
.criterion.passed {{ color: #1a7a34; }}
.criterion.failed {{ color: #b52828; }}
.eval-panel .section {{ margin-top: 8px; }}
.eval-panel .label {{ color: #1a1a1a; font-weight: 600; font-size: 11px; }}
.eval-panel .kv {{ display: grid; grid-template-columns: auto 1fr; gap: 3px 10px; margin-top: 3px; }}
.eval-panel .kv div:nth-child(odd) {{ color: #918b83; }}
.eval-panel .kv div:nth-child(even) {{ color: #1a1a1a; }}
.eval-panel .pill {{
    display: inline-block; padding: 1px 6px; border-radius: 3px;
    font-size: 10px; background: #eceae5; color: #4a4540;
    margin-right: 4px;
}}

.no-traj {{ padding: 40px 20px; text-align: center; color: #918b83; font-size: 12px; }}
</style>
</head>
<body>

<div class="topbar">
    <h1>BreakingWeb</h1>
    <span class="model">{html.escape(model)} &middot; {html.escape(provider)}</span>
    <div class="mode-toggle">
        <button id="modeView" class="active" onclick="setMode('view')">View</button>
        <button id="modeInteractive" onclick="setMode('interactive')">Interactive</button>
    </div>
    <span class="summary">{summary.get('passed', 0)}/{total_tasks} passed &nbsp; avg: {summary.get('average_score', 0):+.3f}</span>
</div>

<div class="main">
    <div class="sidebar" id="sidebar"></div>
    <div class="page-view">
        <div class="page-toolbar" id="toolbar">
            <span class="instruction" id="instruction">Select a task from the sidebar</span>
            <span class="score" id="score"></span>
        </div>
        <div class="page-frame">
            <iframe id="pageFrame" src="about:blank"></iframe>
            <div class="replay-status" id="replayStatus"></div>
        </div>
    </div>
    <div class="trajectory-panel">
        <div class="traj-header">
            <span>Trajectory</span>
            <span class="step-counter" id="stepCounter"></span>
            <div class="traj-controls">
                <button onclick="resetPage()" title="Reset">&#8634;</button>
                <button onclick="prevStep()" title="Previous">&laquo;</button>
                <button onclick="nextStep()" title="Next">&raquo;</button>
                <button id="playBtn" onclick="togglePlay()" title="Auto-play">&#9654;</button>
            </div>
        </div>
        <div class="prompt-drawer">
            <div class="prompt-drawer-toggle" onclick="togglePromptDrawer()">
                <span class="chevron" id="promptChevron">&#9656;</span>
                <span>Prompt</span>
                <div class="verbose-toggle" onclick="event.stopPropagation()">
                    <label for="verboseSwitch">Verbose</label>
                    <input type="checkbox" class="verbose-switch" id="verboseSwitch" onchange="renderPromptDrawer()">
                </div>
            </div>
            <div class="prompt-drawer-content" id="promptContent"></div>
        </div>
        <div class="traj-steps" id="trajSteps">
            <div class="no-traj">Select a task to view its trajectory</div>
        </div>
        <div class="eval-panel" id="evalPanel"></div>
    </div>
</div>

<script>
const SERVER_URL = window.location.origin;
const RESULTS = {results_json};
const TASK_META = {task_meta_json};

let currentPageIdx = -1;
let currentStepIdx = -1;
let lastExecutedIdx = -1;
let playTimer = null;
let mode = 'view';

function getResultTaskId(result) {{
    return result?.task_id || result?.page_id || '';
}}

// ═══════════════════════════════════════════════════════════════
// Prompt drawer
// ═══════════════════════════════════════════════════════════════

function togglePromptDrawer() {{
    const content = document.getElementById('promptContent');
    const chevron = document.getElementById('promptChevron');
    const isOpen = content.classList.toggle('open');
    chevron.classList.toggle('open', isOpen);
    if (isOpen && content.textContent.trim() === '') renderPromptDrawer();
}}

function renderPromptDrawer() {{
    const container = document.getElementById('promptContent');
    container.textContent = '';
    if (currentPageIdx < 0) {{
        const p = document.createElement('div');
        p.className = 'no-prompt';
        p.textContent = 'No task selected';
        container.appendChild(p);
        return;
    }}
    const r = RESULTS[currentPageIdx];
    const msgs = r?.agent?.messages || [];
    if (msgs.length === 0) {{
        const p = document.createElement('div');
        p.className = 'no-prompt';
        p.textContent = 'No prompt data available';
        container.appendChild(p);
        return;
    }}
    const verbose = document.getElementById('verboseSwitch').checked;
    if (verbose) {{
        const wrap = document.createElement('div');
        wrap.style.padding = '8px 14px';
        msgs.forEach((m, i) => {{
            const role = m.role || 'unknown';
            const card = document.createElement('div');
            card.className = 'msg-card msg-' + role;
            const badge = document.createElement('span');
            badge.className = 'msg-role role-' + role;
            badge.textContent = role + ' #' + i;
            card.appendChild(badge);
            const body = document.createElement('div');
            body.className = 'msg-body';
            body.textContent = m.content || '';
            card.appendChild(body);
            wrap.appendChild(card);
        }});
        container.appendChild(wrap);
    }} else {{
        const sysMsg = msgs.find(m => m.role === 'system');
        const firstUser = msgs.find(m => m.role === 'user');
        if (sysMsg) {{
            const sec = document.createElement('div');
            sec.className = 'prompt-section';
            const lbl = document.createElement('div');
            lbl.className = 'prompt-section-label';
            lbl.textContent = 'System Prompt';
            sec.appendChild(lbl);
            const body = document.createElement('div');
            body.className = 'prompt-section-body';
            body.textContent = sysMsg.content || '';
            sec.appendChild(body);
            container.appendChild(sec);
        }}
        if (firstUser) {{
            const sec = document.createElement('div');
            sec.className = 'prompt-section';
            const lbl = document.createElement('div');
            lbl.className = 'prompt-section-label';
            lbl.textContent = 'Initial Instruction';
            sec.appendChild(lbl);
            const body = document.createElement('div');
            body.className = 'prompt-section-body';
            body.textContent = firstUser.content || '';
            sec.appendChild(body);
            container.appendChild(sec);
        }}
        if (!sysMsg && !firstUser) {{
            const p = document.createElement('div');
            p.className = 'no-prompt';
            p.textContent = 'No prompt data available';
            container.appendChild(p);
        }}
    }}
}}

// ═══════════════════════════════════════════════════════════════
// DOM element finder — mirrors Playwright's getByRole logic
// ═══════════════════════════════════════════════════════════════

const ROLE_SELECTORS = {{
    button:    'button, [role="button"], input[type="button"], input[type="submit"], input[type="reset"], summary',
    textbox:   'input:not([type]), input[type="text"], input[type="email"], input[type="password"], input[type="search"], input[type="tel"], input[type="url"], input[type="number"], textarea, [role="textbox"]',
    checkbox:  'input[type="checkbox"], [role="checkbox"]',
    radio:     'input[type="radio"], [role="radio"]',
    combobox:  'select, [role="combobox"], [role="listbox"]',
    link:      'a[href], [role="link"]',
    heading:   'h1, h2, h3, h4, h5, h6, [role="heading"]',
    img:       'img[alt], [role="img"]',
    tab:       '[role="tab"]',
    tabpanel:  '[role="tabpanel"]',
    dialog:    'dialog, [role="dialog"], [role="alertdialog"]',
    option:    'option, [role="option"]',
    listitem:  'li, [role="listitem"]',
    menuitem:  '[role="menuitem"]',
    navigation:'nav, [role="navigation"]',
    region:    'section[aria-label], [role="region"]',
    searchbox: 'input[type="search"], [role="searchbox"]',
    spinbutton:'input[type="number"], [role="spinbutton"]',
    slider:    'input[type="range"], [role="slider"]',
    switch:    '[role="switch"]',
    row:       'article, [role="row"], li, tr',
    article:   'article, [role="article"]',
    cell:      'td, th, [role="cell"], [role="gridcell"]',
    sectionheader: 'h1, h2, h3, h4, h5, h6, header, [role="heading"]',
    colorwell: 'input[type="color"], button, [role="button"]',
    labeltext: 'label, span, [aria-label]',
    strong:    'strong, b, [role="strong"]',
    paragraph: 'p, [role="paragraph"], div',
}};

function normalizeText(value) {{
    return String(value || '')
        .replace(/\\s+/g, ' ')
        .replace(/[“”]/g, '"')
        .replace(/[’]/g, "'")
        .trim()
        .toLowerCase();
}}

function tokenizeText(value) {{
    return normalizeText(value)
        .replace(/[^a-z0-9$%]+/g, ' ')
        .split(/\\s+/)
        .filter(Boolean);
}}

function candidateTargetNames(name) {{
    const variants = new Set();
    const push = (value) => {{
        const normalized = normalizeText(value);
        if (normalized) variants.add(normalized);
    }};

    const raw = String(name || '');
    push(raw);
    push(
        raw
            .replace(/^open (?:unread |read )?thread /i, '')
            .replace(/^read thread from /i, '')
            .replace(/^reply all to /i, '')
            .replace(/^reply to /i, '')
            .replace(/^star contact /i, '')
            .replace(/^unstar contact /i, '')
            .replace(/^star /i, '')
            .replace(/^unstar /i, '')
            .replace(/^archive /i, '')
            .replace(/^move to inbox /i, '')
            .replace(/^delete permanently /i, '')
            .replace(/^delete contact /i, '')
            .replace(/^delete filter /i, '')
            .replace(/^delete label /i, '')
            .replace(/^delete /i, '')
            .replace(/^apply label /i, '')
            .replace(/^remove label /i, '')
    );
    return Array.from(variants);
}}

function getAccessibleName(el) {{
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel;
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {{
        const text = labelledBy
            .split(/\\s+/)
            .map((id) => el.ownerDocument.getElementById(id))
            .filter(Boolean)
            .map((labelEl) => labelEl.textContent.trim())
            .filter(Boolean)
            .join(' ');
        if (text) return text;
    }}
    if (el.id) {{
        const label = el.ownerDocument.querySelector('label[for="' + el.id + '"]');
        if (label) return label.textContent.trim();
    }}
    if (el.placeholder) return el.placeholder;
    if (typeof el.value === 'string' && el.value) return el.value;
    if (el.title) return el.title;
    if (el.alt) return el.alt;
    return el.textContent?.trim() || '';
}}

function buildSelectorCandidates(selector) {{
    if (!selector) return [];
    const stripped = selector.replace(/:nth-of-type\\(\\d+\\)/g, '').trim();
    const parts = stripped.split('>').map((part) => part.trim()).filter(Boolean);
    const selectors = new Set([selector, stripped]);
    for (let i = 0; i < parts.length; i += 1) {{
        selectors.add(parts.slice(i).join(' > '));
    }}
    if (parts.length > 0) {{
        selectors.add(parts[parts.length - 1]);
    }}
    return Array.from(selectors).filter(Boolean);
}}

function isElementNode(el) {{
    return Boolean(el) && el.nodeType === 1 && typeof el.getBoundingClientRect === 'function';
}}

function isVisibleElement(el) {{
    if (!isElementNode(el)) return false;
    const style = el.ownerDocument.defaultView?.getComputedStyle(el);
    if (style && (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0)) {{
        return false;
    }}
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
}}

function roleSelector(role) {{
    const normalizedRole = normalizeText(role);
    if (normalizedRole && ROLE_SELECTORS[normalizedRole]) {{
        return ROLE_SELECTORS[normalizedRole];
    }}
    if (normalizedRole) {{
        return '[role="' + normalizedRole + '"], button, a, input, textarea, select, article, [aria-label], [title]';
    }}
    return 'button, a, input, textarea, select, article, [role], [aria-label], [title], label, span, li, td, th, p, strong';
}}

function roleMatches(el, role) {{
    const normalizedRole = normalizeText(role);
    if (!normalizedRole) return false;

    const tag = el.tagName.toLowerCase();
    const ariaRole = normalizeText(el.getAttribute('role'));
    if (ariaRole === normalizedRole) return true;

    switch (normalizedRole) {{
        case 'button':
            return tag === 'button' || tag === 'summary' || ['button', 'submit', 'reset'].includes((el.type || '').toLowerCase());
        case 'textbox':
            return tag === 'textarea' || tag === 'input' || ariaRole === 'textbox' || el.isContentEditable;
        case 'searchbox':
            return (tag === 'input' && (el.type || '').toLowerCase() === 'search') || ariaRole === 'searchbox';
        case 'checkbox':
            return (tag === 'input' && (el.type || '').toLowerCase() === 'checkbox') || ariaRole === 'checkbox';
        case 'radio':
            return (tag === 'input' && (el.type || '').toLowerCase() === 'radio') || ariaRole === 'radio';
        case 'combobox':
            return tag === 'select' || ariaRole === 'combobox' || ariaRole === 'listbox';
        case 'link':
            return tag === 'a' || ariaRole === 'link';
        case 'tab':
            return tag === 'button' || ariaRole === 'tab';
        case 'menuitem':
            return tag === 'button' || ariaRole === 'menuitem';
        case 'row':
            return tag === 'article' || tag === 'tr' || tag === 'li' || ariaRole === 'row';
        case 'article':
            return tag === 'article' || ariaRole === 'article';
        case 'cell':
            return tag === 'td' || tag === 'th' || ariaRole === 'cell' || ariaRole === 'gridcell';
        case 'sectionheader':
            return /^h[1-6]$/.test(tag) || tag === 'header' || ariaRole === 'heading';
        case 'colorwell':
            return (tag === 'input' && (el.type || '').toLowerCase() === 'color') || tag === 'button';
        case 'labeltext':
            return tag === 'label' || tag === 'span';
        case 'strong':
            return tag === 'strong' || tag === 'b';
        case 'paragraph':
            return tag === 'p' || tag === 'div';
        default:
            return false;
    }}
}}

function scoreElement(el, target, bonus = 0) {{
    let score = bonus;
    const targetNames = candidateTargetNames(target?.name);
    const descriptors = [
        getAccessibleName(el),
        el.getAttribute('title'),
        el.getAttribute('placeholder'),
        el.getAttribute('value'),
        el.textContent,
    ].map(normalizeText).filter(Boolean);

    for (const targetName of targetNames) {{
        if (!targetName) continue;
        if (descriptors.some((value) => value === targetName)) {{
            score += 140;
            break;
        }}
        if (descriptors.some((value) => value.includes(targetName) || targetName.includes(value))) {{
            score += 90;
            break;
        }}

        const targetTokens = tokenizeText(targetName);
        const matchedTokens = targetTokens.filter((token) =>
            descriptors.some((value) => value.includes(token))
        );
        score += matchedTokens.length * 12;
    }}

    if (roleMatches(el, target?.role)) {{
        score += 35;
    }}
    if (isVisibleElement(el)) {{
        score += 12;
    }}
    if (['button', 'a', 'input', 'textarea', 'select'].includes(el.tagName.toLowerCase())) {{
        score += 5;
    }}

    return score;
}}

function queryElements(doc, selector) {{
    if (!selector) return [];
    try {{
        return Array.from(doc.querySelectorAll(selector)).filter(isElementNode);
    }} catch (e) {{
        return [];
    }}
}}

function pickBestMatch(elements, target, bonus = 0) {{
    let best = null;
    let bestScore = -1;

    for (const el of elements) {{
        const score = scoreElement(el, target, bonus);
        if (score > bestScore) {{
            best = el;
            bestScore = score;
        }}
    }}

    return bestScore >= 20 ? {{ el: best, score: bestScore }} : null;
}}

function findBySelector(doc, target) {{
    let best = null;
    for (const selector of buildSelectorCandidates(target?.selector)) {{
        const match = pickBestMatch(queryElements(doc, selector), target, 40);
        if (match && (!best || match.score > best.score)) {{
            best = match;
        }}
    }}
    return best;
}}

function findByRole(doc, role, name, nth) {{
    const target = {{ role, name }};
    const candidates = queryElements(doc, roleSelector(role))
        .map((el) => ({{ el, score: scoreElement(el, target, 24) }}))
        .filter((item) => item.score >= 20)
        .sort((a, b) => b.score - a.score);

    if (!candidates.length) return null;
    if (typeof nth === 'number') {{
        return candidates[nth]?.el || (nth > 0 ? candidates[nth - 1]?.el : null) || candidates[0].el;
    }}
    return candidates[0].el;
}}

function findByText(doc, text) {{
    const wanted = normalizeText(text);
    if (!wanted || !doc.body) return null;

    const NodeFilterRef = doc.defaultView?.NodeFilter || window.NodeFilter;
    const walker = doc.createTreeWalker(doc.body, NodeFilterRef.SHOW_TEXT);
    while (walker.nextNode()) {{
        const nodeText = normalizeText(walker.currentNode.textContent);
        if (!nodeText || !nodeText.includes(wanted)) continue;
        const parent = walker.currentNode.parentElement;
        if (parent) return parent;
    }}
    return null;
}}

function resolveTargetElement(doc, target) {{
    if (!target) return null;

    let best = findBySelector(doc, target);

    const roleMatch = findByRole(doc, target.role, target.name, target.nth);
    if (roleMatch) {{
        const roleScore = scoreElement(roleMatch, target, 24);
        if (!best || roleScore > best.score) {{
            best = {{ el: roleMatch, score: roleScore }};
        }}
    }}

    const textMatch = findByText(doc, candidateTargetNames(target.name)[0] || target.name);
    if (textMatch) {{
        const textScore = scoreElement(textMatch, target, 10);
        if (!best || textScore > best.score) {{
            best = {{ el: textMatch, score: textScore }};
        }}
    }}

    return best?.el || null;
}}

// ═══════════════════════════════════════════════════════════════
// Action execution in iframe
// ═══════════════════════════════════════════════════════════════

function executeAction(trajStep) {{
    const iframe = document.getElementById('pageFrame');
    const doc = iframe.contentDocument || iframe.contentWindow.document;
    if (!doc || !doc.body) return 'iframe not ready';

    const action = trajStep.action || {{}};
    const targets = trajStep.targets || {{}};
    const actionName = action.action || 'wait';

    if (actionName === 'finish' || actionName === 'wait' || actionName === 'noop') return actionName;

    if (actionName === 'scroll') {{
        const dir = action.direction || 'down';
        const isHorizontal = dir === 'left' || dir === 'right';
        const delta = (dir === 'up' || dir === 'left') ? -300 : 300;
        const dx = isHorizontal ? delta : 0;
        const dy = isHorizontal ? 0 : delta;
        if (targets.ref) {{
            const el = resolveTargetElement(doc, targets.ref);
            if (el) el.scrollBy(dx, dy);
            else iframe.contentWindow.scrollBy(dx, dy);
        }} else {{
            iframe.contentWindow.scrollBy(dx, dy);
        }}
        return 'scrolled ' + dir;
    }}

    if (actionName === 'press') {{
        const key = action.key || '';
        let target = doc.activeElement || doc.body;
        if (targets.ref) {{
            const el = resolveTargetElement(doc, targets.ref);
            if (el) target = el;
        }}
        target.dispatchEvent(new KeyboardEvent('keydown', {{ key, bubbles: true }}));
        target.dispatchEvent(new KeyboardEvent('keyup', {{ key, bubbles: true }}));
        if (key === 'Enter') target.dispatchEvent(new KeyboardEvent('keypress', {{ key, bubbles: true }}));
        return 'pressed ' + key;
    }}

    if (actionName === 'drag_and_drop') {{
        [targets.from_ref, targets.to_ref].forEach(t => {{
            if (t) {{
                const el = resolveTargetElement(doc, t);
                if (el) highlightEl(el);
            }}
        }});
        return 'drag_and_drop (highlight only)';
    }}

    const t = (
        targets.ref && typeof targets.ref === 'object'
            ? targets.ref
            : (typeof targets === 'object' && targets && !targets.ref && (targets.role || targets.name || targets.selector || targets.bid)
                ? targets
                : null)
    );
    if (!t) return 'no target info';
    const el = resolveTargetElement(doc, t);
    if (!el) return 'element not found: ' + t.role + ' "' + t.name + '"';

    highlightEl(el);
    el.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});

    switch (actionName) {{
        case 'click':
            el.click();
            return 'clicked';
        case 'dblclick':
            el.dispatchEvent(new MouseEvent('dblclick', {{ bubbles: true }}));
            return 'dblclicked';
        case 'fill':
            el.focus();
            if ('value' in el) {{
                el.value = action.value || '';
            }} else if (el.isContentEditable) {{
                el.textContent = action.value || '';
            }}
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return 'filled "' + (action.value || '').substring(0, 30) + '"';
        case 'select':
            if (el.tagName === 'SELECT') {{
                const opt = Array.from(el.options).find(o =>
                    o.text.includes(action.value) || o.value === action.value
                );
                if (opt) {{
                    el.value = opt.value;
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'selected "' + opt.text + '"';
                }}
                return 'option not found: ' + action.value;
            }}
            el.click();
            return 'clicked (select fallback)';
        case 'check':
            if (!el.checked) el.click();
            return 'checked';
        case 'uncheck':
            if (el.checked) el.click();
            return 'unchecked';
        case 'hover':
            el.dispatchEvent(new MouseEvent('mouseenter', {{ bubbles: true }}));
            el.dispatchEvent(new MouseEvent('mouseover', {{ bubbles: true }}));
            return 'hovered';
        default:
            return 'unknown action: ' + actionName;
    }}
}}

function highlightEl(el) {{
    const prev = el.style.outline;
    const prevBg = el.style.backgroundColor;
    el.style.outline = '2px solid #1a1a1a';
    el.style.backgroundColor = 'rgba(26,26,26,0.06)';
    setTimeout(() => {{
        el.style.outline = prev;
        el.style.backgroundColor = prevBg;
    }}, 1500);
}}

function showReplayStatus(text) {{
    const el = document.getElementById('replayStatus');
    el.textContent = text;
    el.style.display = 'block';
    setTimeout(() => {{ el.style.display = 'none'; }}, 2000);
}}

let activeReplaySession = null;

function getStoredInstruction(result) {{
    const meta = TASK_META[getResultTaskId(result)] || {{}};
    return meta.instruction || result.instruction || '';
}}

function getDisplayedInstruction(result) {{
    const replay = result?.replay || {{}};
    if (
        replay.kind === 'env' &&
        activeReplaySession &&
        activeReplaySession.envId === replay.env_id &&
        activeReplaySession.taskId === (replay.task_id || result.task_id) &&
        activeReplaySession.instruction
    ) {{
        return activeReplaySession.instruction;
    }}
    return getStoredInstruction(result);
}}

function getResultScore(result) {{
    return Number(result?.evaluation?.score ?? result?.evaluation?.final_score ?? -1);
}}

async function destroyActiveReplaySession() {{
    if (!activeReplaySession) return;
    const session = activeReplaySession;
    activeReplaySession = null;
    try {{
        await fetch(
            `${{SERVER_URL}}/api/env/${{session.envId}}/session/${{encodeURIComponent(session.sessionId)}}`,
            {{ method: 'DELETE' }}
        );
    }} catch (e) {{
        console.warn('Failed to destroy replay session', e);
    }}
}}

function joinReplayPath(baseUrl, startPath) {{
    const base = String(baseUrl || '').replace(/\\/+$/, '');
    const path = String(startPath || '');
    if (!path) {{
        return base || '/';
    }}
    return base + (path.startsWith('/') ? path : '/' + path);
}}

function buildReplayRequestPayload(result, replay) {{
    const payload = {{ task_id: replay.task_id || result.task_id }};
    if (replay.seed !== undefined && replay.seed !== null) {{
        payload.seed = replay.seed;
    }}

    const degradation =
        replay.degradation && typeof replay.degradation === 'object'
            ? replay.degradation
            : (result.degradation && typeof result.degradation === 'object' ? result.degradation : null);

    const variantFilename = replay.variant_filename || degradation?.variant_filename;
    if (variantFilename) {{
        payload.variant_filename = variantFilename;
    }}

    if (degradation) {{
        const replayDegradation = {{ ...degradation }};
        delete replayDegradation.variant_filename;
        if (Object.keys(replayDegradation).length > 0) {{
            payload.degradation = replayDegradation;
        }}
    }}

    return payload;
}}

function buildReplayPageUrl(baseUrl, startPath, sessionId) {{
    const joinedPath = joinReplayPath(baseUrl, startPath);
    const replayUrl = new URL(joinedPath || '/', SERVER_URL || window.location.origin);
    replayUrl.searchParams.set('session', sessionId);
    if (!replayUrl.searchParams.has('agent_mode')) {{
        replayUrl.searchParams.set('agent_mode', '1');
    }}
    return replayUrl.toString();
}}

async function buildReplayUrl(result, resetSession = false) {{
    const replay = result?.replay || {{}};
    if (replay.kind !== 'env') {{
        if (resetSession) await destroyActiveReplaySession();
        return null;
    }}

    if (
        resetSession ||
        !activeReplaySession ||
        activeReplaySession.envId !== replay.env_id ||
        activeReplaySession.taskId !== (replay.task_id || result.task_id)
    ) {{
        await destroyActiveReplaySession();
        const payload = buildReplayRequestPayload(result, replay);
        const response = await fetch(`${{SERVER_URL}}/api/env/${{replay.env_id}}/session`, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload),
        }});
        if (!response.ok) {{
            throw new Error(`Failed to create replay session (${{response.status}})`);
        }}
        const data = await response.json();
        activeReplaySession = {{
            envId: replay.env_id,
            sessionId: data.session_id,
            taskId: payload.task_id,
            title: data.title || null,
            instruction: data.instruction || null,
        }};
    }}

    const baseUrl = replay.base_url || result.base_url;
    const startPath = replay.start_path || "";
    return buildReplayPageUrl(baseUrl, startPath, activeReplaySession.sessionId);
}}

async function loadResultFrame(result, resetSession = false) {{
    const iframe = document.getElementById('pageFrame');
    const replayStatus = document.getElementById('replayStatus');
    const src = await buildReplayUrl(result, resetSession);
    if (!src) {{
        iframe.src = 'about:blank';
        replayStatus.style.display = 'flex';
        replayStatus.textContent = 'No live replay — screenshots not available for stored results';
        return;
    }}
    replayStatus.style.display = 'none';
    await new Promise((resolve) => {{
        iframe.onload = () => resolve();
        iframe.src = src;
    }});
}}

window.addEventListener('beforeunload', () => {{
    void destroyActiveReplaySession();
}});

// ═══════════════════════════════════════════════════════════════
// Mode toggle
// ═══════════════════════════════════════════════════════════════

function setMode(m) {{
    mode = m;
    document.getElementById('modeView').classList.toggle('active', m === 'view');
    document.getElementById('modeInteractive').classList.toggle('active', m === 'interactive');
    lastExecutedIdx = -1;
    document.querySelectorAll('#trajSteps .step').forEach(el => {{
        el.classList.remove('executed', 'exec-error');
    }});
    if (m === 'interactive' && currentPageIdx >= 0) {{
        const r = RESULTS[currentPageIdx];
        void loadResultFrame(r, true);
        currentStepIdx = -1;
        showReplayStatus('Interactive mode — actions will replay on page');
    }}
}}

// ═══════════════════════════════════════════════════════════════
// Navigation
// ═══════════════════════════════════════════════════════════════

const sidebar = document.getElementById('sidebar');
RESULTS.forEach((r, idx) => {{
    const item = document.createElement('div');
    item.className = 'page-item';
    item.dataset.idx = idx;
    const success = r.evaluation && r.evaluation.success;
    const score = getResultScore(r);
    const badgeClass = success ? 'pass' : 'fail';
    const badgeText = success ? 'PASS' : 'FAIL';
    const steps = r.agent ? r.agent.steps : 0;

    const titleEl = document.createElement('div');
    titleEl.className = 'page-title';
    titleEl.textContent = r.title || getResultTaskId(r);

    const metaEl = document.createElement('div');
    metaEl.className = 'page-meta';

    const badge = document.createElement('span');
    badge.className = 'badge ' + badgeClass;
    badge.textContent = badgeText;
    metaEl.appendChild(badge);

    const info = document.createTextNode(
        ' ' + score.toFixed(2) + ' \u00b7 ' + steps + ' steps \u00b7 ' + (r.difficulty || '?')
    );
    metaEl.appendChild(info);

    item.appendChild(titleEl);
    item.appendChild(metaEl);
    item.onclick = () => {{ void selectPage(idx); }};
    sidebar.appendChild(item);
}});

async function selectPage(idx) {{
    currentPageIdx = idx;
    currentStepIdx = -1;
    lastExecutedIdx = -1;
    stopPlay();

    document.querySelectorAll('.page-item').forEach((el, i) => {{
        el.classList.toggle('active', i === idx);
    }});

    const r = RESULTS[idx];
    const success = r.evaluation && r.evaluation.success;
    const title = r.title || getResultTaskId(r) || 'Untitled';
    document.getElementById('instruction').textContent = getDisplayedInstruction(r) || title;
    const scoreEl = document.getElementById('score');
    const scoreVal = getResultScore(r);
    scoreEl.textContent = (success ? 'PASS' : 'FAIL') + ' ' + scoreVal.toFixed(2);
    scoreEl.className = 'score ' + (success ? 'pass' : 'fail');

    try {{
        await loadResultFrame(r, true);
        document.getElementById('instruction').textContent = getDisplayedInstruction(r) || title;
    }} catch (e) {{
        console.error(e);
        showReplayStatus('Failed to load replay target');
    }}

    // Re-render prompt drawer if open
    const promptContent = document.getElementById('promptContent');
    if (promptContent.classList.contains('open')) {{
        renderPromptDrawer();
    }} else {{
        promptContent.textContent = '';
    }}

    const trajEl = document.getElementById('trajSteps');
    const traj = r.agent?.trajectory || [];
    if (traj.length === 0) {{
        trajEl.textContent = '';
        const noTraj = document.createElement('div');
        noTraj.className = 'no-traj';
        noTraj.textContent = 'No trajectory recorded';
        trajEl.appendChild(noTraj);
    }} else {{
        trajEl.textContent = '';
        traj.forEach((t, stepIdx) => {{
            const step = document.createElement('div');
            step.className = 'step';
            step.dataset.step = stepIdx;

            const action = t.action || {{}};
            const actionBatch = Array.isArray(t.actions) && t.actions.length ? t.actions : [action];
            const name = actionBatch.map((a) => a.action || '?').join(' → ');
            let targetStr = '';
            if (action.ref !== undefined) targetStr = ' [' + action.ref + ']';
            if (action.from_ref !== undefined) targetStr = ' [' + action.from_ref + ' \u2192 ' + action.to_ref + ']';
            let valueStr = '';
            if (action.value) valueStr = ' "' + String(action.value).substring(0, 50) + '"';
            if (action.key) valueStr = ' ' + action.key;
            if (action.direction) valueStr = ' ' + action.direction;
            if (action.answer) valueStr = ' "' + String(action.answer).substring(0, 50) + '"';

            // elapsed
            const elapsed = document.createElement('span');
            elapsed.className = 'elapsed';
            elapsed.textContent = t.elapsed_seconds + 's';
            step.appendChild(elapsed);

            // step number
            const num = document.createElement('span');
            num.className = 'step-num';
            num.textContent = '#' + t.step;
            step.appendChild(num);

            // action
            const actionEl = document.createElement('span');
            actionEl.className = 'action-name';
            actionEl.textContent = name;
            step.appendChild(actionEl);

            if (targetStr) {{
                const tgt = document.createElement('span');
                tgt.className = 'action-target';
                tgt.textContent = targetStr;
                step.appendChild(tgt);
            }}

            if (valueStr) {{
                const val = document.createElement('span');
                val.className = 'action-value';
                val.textContent = valueStr;
                step.appendChild(val);
            }}

            // status
            if (t.status) {{
                const st = document.createElement('div');
                st.className = 'status';
                st.textContent = t.status;
                step.appendChild(st);
            }}

            // thought
            if (t.thought) {{
                const details = document.createElement('details');
                details.className = 'step-thought';
                const summary = document.createElement('summary');
                summary.textContent = 'Thought';
                details.appendChild(summary);
                const body = document.createElement('div');
                body.className = 'thought-body';
                body.textContent = t.thought;
                details.appendChild(body);
                step.appendChild(details);
            }}

            // screenshot (stock-harness-only; recorded by _history_to_trajectory)
            if (t.screenshot) {{
                const shotDetails = document.createElement('details');
                shotDetails.className = 'step-screenshot';
                const shotSummary = document.createElement('summary');
                shotSummary.textContent = 'Screenshot';
                shotDetails.appendChild(shotSummary);
                const img = document.createElement('img');
                img.src = t.screenshot;
                img.className = 'step-screenshot-img';
                img.alt = 'Step ' + t.step + ' screenshot';
                shotDetails.appendChild(img);
                step.appendChild(shotDetails);
            }}

            step.onclick = () => goToStep(stepIdx);
            trajEl.appendChild(step);
        }});
    }}
    document.getElementById('stepCounter').textContent = traj.length + ' steps';

    // Evaluation panel
    renderEvalPanel(r);
}}

function renderEvalPanel(r) {{
    const evalEl = document.getElementById('evalPanel');
    evalEl.textContent = '';
    const ev = r.evaluation || {{}};

    function addSection(title) {{
        const sec = document.createElement('div');
        sec.className = 'section';
        const lbl = document.createElement('span');
        lbl.className = 'label';
        lbl.textContent = title;
        sec.appendChild(lbl);
        evalEl.appendChild(sec);
    }}

    function addKv(pairs) {{
        const kv = document.createElement('div');
        kv.className = 'kv';
        pairs.forEach(([k, v]) => {{
            const kEl = document.createElement('div');
            kEl.textContent = k;
            kv.appendChild(kEl);
            const vEl = document.createElement('div');
            vEl.textContent = String(v);
            kv.appendChild(vEl);
        }});
        evalEl.appendChild(kv);
    }}

    function addCriteria(items) {{
        const wrap = document.createElement('div');
        wrap.className = 'criteria';
        items.forEach(c => {{
            const el = document.createElement('div');
            el.className = 'criterion ' + (c.passed ? 'passed' : 'failed');
            const label = c.expression || c.check || c.desc || c.selector || JSON.stringify(c);
            el.textContent = (c.passed ? '\u2713 ' : '\u2717 ') + label;
            wrap.appendChild(el);
        }});
        evalEl.appendChild(wrap);
    }}

    addSection('Analysis');
    const kvPairs = [
        ['Score', Number(ev.score ?? -1).toFixed(2)],
        ['Success', ev.success ? 'true' : 'false'],
    ];
    if (ev.completed !== undefined) kvPairs.push(['Completed', ev.completed ? 'true' : 'false']);
    if (r.agent?.steps !== undefined) kvPairs.push(['Steps', r.agent.steps]);
    if (r.agent?.elapsed_seconds !== undefined) kvPairs.push(['Elapsed', r.agent.elapsed_seconds + 's']);
    addKv(kvPairs);

    if (ev.reasoning) {{
        addSection('Reasoning');
        const p = document.createElement('div');
        p.style.color = 'rgba(255,255,255,0.6)';
        p.textContent = ev.reasoning;
        evalEl.appendChild(p);
    }}

    const criteria = ev.criteria_results || [];
    if (criteria.length > 0) {{
        addSection('Criteria');
        addCriteria(criteria);
    }}

    const negativeResults = ev.negative_results || [];
    if (negativeResults.length > 0) {{
        addSection('Negative Checks');
        addCriteria(negativeResults);
    }}

    const domResults = ev.dom_results || [];
    if (domResults.length > 0) {{
        addSection('DOM Checks');
        domResults.forEach(d => {{
            const el = document.createElement('div');
            el.className = 'criterion ' + (d.passed ? 'passed' : 'failed');
            const cond = [d.selector, d.condition].filter(Boolean).join(' \u00b7 ');
            el.textContent = (d.passed ? '\u2713 ' : '\u2717 ') + cond;
            evalEl.appendChild(el);
        }});
    }}

    const details = ev.details || {{}};
    const detailKeys = Object.keys(details);
    if (detailKeys.length > 0) {{
        addSection('Details');
        addKv(detailKeys.map(k => {{
            const v = details[k];
            return [k, (v && typeof v === 'object') ? JSON.stringify(v) : String(v)];
        }}));
    }}
}}

async function goToStep(stepIdx) {{
    const steps = document.querySelectorAll('#trajSteps .step');
    currentStepIdx = stepIdx;
    steps.forEach((el, i) => el.classList.toggle('current', i === stepIdx));
    if (steps[stepIdx]) steps[stepIdx].scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    document.getElementById('stepCounter').textContent = (stepIdx + 1) + ' / ' + steps.length + ' steps';

    if (mode === 'interactive') {{
        const r = RESULTS[currentPageIdx];
        const traj = r?.agent?.trajectory || [];
        for (let i = lastExecutedIdx + 1; i <= stepIdx; i++) {{
            const t = traj[i];
            if (!t) continue;
            const result = executeAction(t);
            const stepEl = steps[i];
            if (result && !result.includes('not found') && !result.includes('not ready')) {{
                stepEl.classList.add('executed');
                stepEl.classList.remove('exec-error');
            }} else {{
                stepEl.classList.add('exec-error');
                stepEl.classList.remove('executed');
            }}
            showReplayStatus('#' + (i + 1) + ': ' + result);
        }}
        if (stepIdx > lastExecutedIdx) lastExecutedIdx = stepIdx;
    }}
}}

function nextStep() {{
    const steps = document.querySelectorAll('#trajSteps .step');
    if (steps.length === 0) return;
    void goToStep(Math.min(currentStepIdx + 1, steps.length - 1));
}}

function prevStep() {{
    if (currentStepIdx <= 0) return;
    if (mode === 'interactive') {{
        showReplayStatus('Use reset (\u21ba) then step forward');
        return;
    }}
    void goToStep(currentStepIdx - 1);
}}

async function resetPage() {{
    if (currentPageIdx < 0) return;
    const r = RESULTS[currentPageIdx];
    try {{
        await loadResultFrame(r, true);
    }} catch (e) {{
        console.error(e);
        showReplayStatus('Failed to reset replay target');
    }}
    currentStepIdx = -1;
    lastExecutedIdx = -1;
    document.querySelectorAll('#trajSteps .step').forEach(el => {{
        el.classList.remove('current', 'executed', 'exec-error');
    }});
    document.getElementById('stepCounter').textContent =
        (r.agent?.trajectory?.length || 0) + ' steps';
    showReplayStatus('Page reset');
}}

function togglePlay() {{
    if (playTimer) {{
        stopPlay();
    }} else {{
        document.getElementById('playBtn').classList.add('active');
        document.getElementById('playBtn').textContent = '\u25a0';
        const delay = mode === 'interactive' ? 1500 : 800;
        playTimer = setInterval(() => {{
            const steps = document.querySelectorAll('#trajSteps .step');
            if (currentStepIdx >= steps.length - 1) {{
                stopPlay();
                return;
            }}
            nextStep();
        }}, delay);
    }}
}}

function stopPlay() {{
    if (playTimer) {{ clearInterval(playTimer); playTimer = null; }}
    document.getElementById('playBtn').classList.remove('active');
    document.getElementById('playBtn').textContent = '\u25b6';
}}

function escapeHtml(str) {{
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}}

if (RESULTS.length > 0) void selectPage(0);
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description="Visualize BreakingWeb agent trajectories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", help="Result JSON file to visualize")
    parser.add_argument("--output", "-o", help="Output HTML path (default: <input>_viz.html)")
    parser.add_argument("--server-url", default="http://127.0.0.1:8080",
                        help="BreakingWeb server URL (default: http://127.0.0.1:8080)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--no-server", action="store_true",
                        help="Don't auto-start the BreakingWeb server")
    args = parser.parse_args()

    # Load results
    with open(args.file) as f:
        data = json.load(f)

    # Attach manifest metadata without discarding result-supplied env task metadata.
    task_meta = load_embedded_task_meta(data)
    try:
        manifest_path = Path(__file__).parent / "manifest.json"
        with open(manifest_path) as mf:
            manifest = json.load(mf)
        data["task_meta"] = {
            **build_manifest_task_meta(manifest),
            **task_meta,
        }
    except Exception:
        data["task_meta"] = task_meta

    # Determine output path
    if args.output:
        out_path = args.output
    else:
        p = Path(args.file)
        out_path = str(p.with_suffix("")) + "_viz.html"

    # Start server if needed
    server_proc = None
    server_ok = False

    def server_is_healthy(url: str) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/health", timeout=2)
            return True
        except Exception:
            return False

    if not args.no_server:
        from .runner import start_server, wait_for_server
        import urllib.parse
        parsed = urllib.parse.urlparse(args.server_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8080

        # Check if server is already running
        if server_is_healthy(args.server_url):
            print(f"Server already running at {args.server_url}")
            server_ok = True
        else:
            print(f"Starting BreakingWeb server on {args.server_url}...")
            server_proc = start_server(host, port)
            if not wait_for_server(host, port):
                print("ERROR: Server failed to start", file=sys.stderr)
                if server_proc:
                    server_proc.terminate()
                sys.exit(1)
            print("Server ready.")
            server_ok = True
    else:
        server_ok = server_is_healthy(args.server_url)

    # Generate HTML
    # If the input file is a summary.json whose results point at per-task
    # trajectory.json files, load/inline them relative to the summary's dir.
    html_content = generate_html(
        data, args.server_url,
        trajectory_base_dir=Path(args.file).resolve().parent,
    )
    with open(out_path, "w") as f:
        f.write(html_content)

    # Always write a copy into /static for same-origin playback (if server is running)
    static_out = None
    if server_ok:
        static_dir = Path(__file__).parent / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        static_out = static_dir / Path(out_path).name
        if static_out.resolve() != Path(out_path).resolve():
            with open(static_out, "w") as f:
                f.write(html_content)

    print(f"Visualization written to {out_path}")
    if static_out:
        print(f"Visualization served at {args.server_url.rstrip('/')}/static/{static_out.name}")

    # Open in browser
    if not args.no_open:
        import webbrowser
        if static_out:
            webbrowser.open(f"{args.server_url.rstrip('/')}/static/{static_out.name}")
        else:
            webbrowser.open(f"file://{Path(out_path).resolve()}")
        if server_proc:
            print("Server running in background. Press Ctrl+C to stop.")
            try:
                server_proc.wait()
            except KeyboardInterrupt:
                server_proc.terminate()
                server_proc.wait()
    elif server_proc:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
            server_proc.wait()
        print("Temporary visualization server stopped.")
    elif args.no_open and static_out:
        print("Visualization generated without opening a browser.")
    elif args.no_open:
        print("Visualization generated without opening a browser.")


if __name__ == "__main__":
    main()
