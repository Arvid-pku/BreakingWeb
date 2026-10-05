"""
BreakingWeb — FastAPI application for advanced environments.

Serves:
- Advanced environment APIs under /api/env/*
- Built React SPAs under /env/*
- Public manifest at /manifest

Task definitions are loaded from YAML files via the unified task registry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess

import yaml
from copy import deepcopy
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import getenv
from .backend.routes import mount_environment_routes
from .backend.security import CONTROLLER_SECRET_ENV
from .backend.state import SessionManager
from .tasks._registry import get_task, tasks_by_env

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - not expected on local macOS/Linux dev
    fcntl = None

# Load environment metadata from manifest.json (no longer contains task defs)
with open(BASE_DIR / "manifest.json") as f:
    MANIFEST_TEMPLATE = json.load(f)

_ENV_TASK_GROUPS = tasks_by_env()


def _env_index_path(env_id: str) -> Path:
    return STATIC_DIR / "envs" / env_id / "index.html"


def _env_assets_path(env_id: str) -> Path:
    return STATIC_DIR / "envs" / env_id / "assets"


def _frontend_build_command() -> str:
    return "scripts/breakingweb.sh build"


def _auto_frontend_build_enabled() -> bool:
    raw = getenv("BREAKINGWEB_AUTO_BUILD_FRONTENDS", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _auto_frontend_build_clean() -> bool:
    raw = getenv("BREAKINGWEB_AUTO_BUILD_CLEAN", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _dev_frontend_overrides() -> dict[str, str]:
    raw = getenv("BREAKINGWEB_DEV_FRONTENDS", "").strip()
    if not raw:
        return {}

    overrides: dict[str, str] = {}
    for entry in raw.split(","):
        item = entry.strip()
        if not item:
            continue
        env_id, sep, url = item.partition("=")
        if not sep:
            continue
        env_id = env_id.strip()
        url = url.strip().rstrip("/")
        if env_id and url:
            overrides[env_id] = url
    return overrides


def _env_dev_base_url(env_id: str) -> str | None:
    return _dev_frontend_overrides().get(env_id)


def _join_public_base_url(base_url: str, path: str = "", query: str = "") -> str:
    normalized_base = base_url.rstrip("/")
    normalized_path = path.lstrip("/")
    joined = f"{normalized_base}/{normalized_path}" if normalized_path else f"{normalized_base}/"
    return f"{joined}?{query}" if query else joined


@lru_cache(maxsize=None)
def _env_source_inputs(env_id: str) -> tuple[Path, ...]:
    workspace_dir = BASE_DIR / "environments"
    env_dir = workspace_dir / env_id
    shared_dir = workspace_dir / "shared"
    candidates = [
        env_dir / "index.html",
        env_dir / "package.json",
        env_dir / "vite.config.ts",
        env_dir / "tsconfig.json",
        env_dir / "src",
        shared_dir / "package.json",
        shared_dir / "tsconfig.json",
        shared_dir / "src",
        workspace_dir / "package.json",
        workspace_dir / "pnpm-lock.yaml",
        workspace_dir / "pnpm-workspace.yaml",
        workspace_dir / "tsconfig.base.json",
    ]
    return tuple(path for path in candidates if path.exists())


def _latest_mtime_ns(paths: list[Path]) -> int | None:
    latest: int | None = None
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            mtime = path.stat().st_mtime_ns
            latest = mtime if latest is None else max(latest, mtime)
            continue
        for child in path.rglob("*"):
            if child.is_file():
                mtime = child.stat().st_mtime_ns
                latest = mtime if latest is None else max(latest, mtime)
    return latest


def _frontend_bundle_status(index_path: Path, assets_dir: Path, source_inputs: list[Path]) -> tuple[bool, str | None]:
    build_command = _frontend_build_command()
    if not index_path.exists() or not assets_dir.exists():
        return False, f"Environment backend exists but the frontend bundle has not been built. Run `{build_command}`."

    build_inputs = [index_path, assets_dir]
    latest_build = _latest_mtime_ns(build_inputs)
    latest_source = _latest_mtime_ns(source_inputs)

    if latest_build is None:
        return False, f"Environment backend exists but the frontend bundle has not been built. Run `{build_command}`."
    if latest_source is not None and latest_source > latest_build:
        return False, f"Environment backend exists but the frontend bundle is stale. Rebuild it with `{build_command}`."
    return True, None


def _env_frontend_status(env_id: str) -> tuple[bool, str | None]:
    dev_url = _env_dev_base_url(env_id)
    if dev_url:
        return True, None
    return _frontend_bundle_status(
        _env_index_path(env_id),
        _env_assets_path(env_id),
        list(_env_source_inputs(env_id)),
    )


def _env_public_base_url(env_id: str, fallback: str | None = None) -> str:
    return _env_dev_base_url(env_id) or fallback or f"/env/{env_id}"

def _serve_env_html(env_id: str) -> FileResponse:
    """Serve the built environment index.html without runtime mutation."""
    index_path = _env_index_path(env_id)
    available, reason = _env_frontend_status(env_id)
    if not available:
        raise HTTPException(status_code=503, detail=reason)
    return FileResponse(index_path)


def _env_is_available(env_id: str) -> bool:
    if env_id not in _ENV_TASK_GROUPS:
        return False
    available, _ = _env_frontend_status(env_id)
    return available


def _env_unavailable_reason(env_id: str) -> str | None:
    if env_id not in _ENV_TASK_GROUPS:
        return "Environment is listed in the manifest but has no backend implementation in this build."
    _, reason = _env_frontend_status(env_id)
    return reason


def _stale_frontend_env_ids() -> list[str]:
    stale: list[str] = []
    for env_id in sorted(_ENV_TASK_GROUPS):
        available, _ = _env_frontend_status(env_id)
        if not available:
            stale.append(env_id)
    return stale


@contextmanager
def _frontend_build_lock():
    lock_path = STATIC_DIR / ".frontend-build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _run_frontend_build(env_ids: list[str]) -> None:
    env_dir = BASE_DIR / "environments"

    if _auto_frontend_build_clean():
        shutil.rmtree(STATIC_DIR / "envs", ignore_errors=True)
        (STATIC_DIR / "envs").mkdir(parents=True, exist_ok=True)

    commands = [
        ["pnpm", "--filter", "@breakingweb/shared", "build"],
        *[["pnpm", "--filter", f"@breakingweb/{env_id}", "build"] for env_id in env_ids],
    ]
    for command in commands:
        subprocess.run(command, cwd=env_dir, check=True)


def _auto_build_frontends_if_needed() -> list[str]:
    if not _auto_frontend_build_enabled():
        return []
    if "PYTEST_CURRENT_TEST" in os.environ:
        return []

    stale_envs = _stale_frontend_env_ids()
    if not stale_envs:
        return []

    with _frontend_build_lock():
        stale_envs = _stale_frontend_env_ids()
        if not stale_envs:
            return []

        logger.info(
            "Auto-building stale frontend bundles before backend startup: %s",
            ", ".join(stale_envs),
        )
        try:
            _run_frontend_build(stale_envs)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Frontend auto-build requires `pnpm` on PATH. "
                "Install pnpm or disable auto-build with BREAKINGWEB_AUTO_BUILD_FRONTENDS=0."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Frontend auto-build failed while starting the backend. "
                "Run `./scripts/breakingweb.sh build --clean` to inspect the failing build."
            ) from exc

        remaining = _stale_frontend_env_ids()
        if remaining:
            raise RuntimeError(
                "Frontend auto-build completed, but these environments are still stale or unavailable: "
                + ", ".join(remaining)
            )
        return stale_envs


def _public_task_from_def(task) -> dict:
    """Return task metadata safe to expose through the public manifest."""
    return {
        "task_id": task.task_id,
        "env_id": task.env_id,
        "title": task.title,
        "instruction_template": task.instruction_template or task.instruction,
        "difficulty": task.difficulty,
        "primary_primitives": task.primary_primitives,
        "time_limit_seconds": task.time_limit_seconds,
        "expected_steps": task.expected_steps,
        "start_path": task.start_path or "/",
    }


def _build_env_manifest_entry(env_meta: dict, tasks: list) -> dict:
    entry = deepcopy(env_meta)
    entry.setdefault("env_id", env_meta.get("env_id"))
    entry.setdefault("title", entry["env_id"])
    entry["base_url"] = _env_public_base_url(
        entry["env_id"],
        env_meta.get("base_url", f"/env/{entry['env_id']}"),
    )
    entry["tasks"] = [_public_task_from_def(task) for task in tasks]
    entry["available"] = _env_is_available(entry["env_id"])
    entry["unavailable_reason"] = _env_unavailable_reason(entry["env_id"])
    return entry


def build_manifest() -> dict:
    """Build the public manifest from YAML registry + environment metadata."""
    manifest = {
        "version": MANIFEST_TEMPLATE.get("version", "2.0.0"),
        "benchmark": MANIFEST_TEMPLATE.get("benchmark", "BreakingWeb"),
        "description": MANIFEST_TEMPLATE.get("description", ""),
        "primitives": MANIFEST_TEMPLATE.get("primitives", []),
    }

    env_entries: list[dict] = []
    seen_env_ids: set[str] = set()

    for env in MANIFEST_TEMPLATE.get("environments", []):
        env_id = env["env_id"]
        env_entries.append(_build_env_manifest_entry(env, _ENV_TASK_GROUPS.get(env_id, [])))
        seen_env_ids.add(env_id)

    for env_id, env_task_list in _ENV_TASK_GROUPS.items():
        if env_id in seen_env_ids:
            continue
        env_entries.append(
            _build_env_manifest_entry(
                {"env_id": env_id, "title": env_id, "base_url": f"/env/{env_id}"},
                env_task_list,
            )
        )

    manifest["environments"] = env_entries
    return manifest


MANIFEST = build_manifest()
ENVIRONMENT_COUNT = len(MANIFEST.get("environments", []))
ENV_TASK_COUNT = sum(len(env.get("tasks", [])) for env in MANIFEST.get("environments", []))
MANIFEST_VERSION = MANIFEST.get("version", "1.0.0")
MANIFEST_FINGERPRINT = hashlib.sha256(
    json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()[:12]
KNOWN_ENV_IDS = {env["env_id"] for env in MANIFEST.get("environments", [])}

description = f"{ENV_TASK_COUNT} advanced environment tasks across {ENVIRONMENT_COUNT} simulated applications"


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    built_envs = _auto_build_frontends_if_needed()
    if built_envs:
        logger.info("Frontend bundles refreshed for: %s", ", ".join(built_envs))
    yield


app = FastAPI(
    title="BreakingWeb",
    description=description,
    version=MANIFEST_VERSION,
    lifespan=_app_lifespan,
)
app.state.session_manager = SessionManager()
app.state.controller_secret = getenv(CONTROLLER_SECRET_ENV)

# Server-side network degradation middleware — applies delays, errors, silent failures
# for both Playwright agents and human browsers
from .injector.middleware import DegradationMiddleware
app.add_middleware(DegradationMiddleware)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
mount_environment_routes(app)

for env_id in KNOWN_ENV_IDS:
    assets_dir = _env_assets_path(env_id)
    app.mount(
        f"/env/{env_id}/assets",
        StaticFiles(directory=str(assets_dir), check_dir=False),
        name=f"{env_id}-assets",
    )


@app.get("/control/{env_id}/{session_id}", response_class=HTMLResponse)
async def control_panel(env_id: str, session_id: str) -> HTMLResponse:
    """Human-facing control panel for a session: task description, record, evaluate, reset."""
    path = STATIC_DIR / "control.html"
    return HTMLResponse(content=path.read_text())


# cid → {session_id, env_id, start_path, created_at}. Used to bind the
# two tabs the public site opens (bench + control) to a single session.
# Whichever tab arrives first creates the session and stores its info
# here; the second tab reads from this cache and skips creation.
import asyncio as _asyncio_play
import time as _time_play
_PLAY_CID_CACHE: dict[str, dict] = {}
_PLAY_CID_LOCKS: dict[str, _asyncio_play.Lock] = {}
_PLAY_CID_TTL_SEC = 300


def _play_cache_evict_stale() -> None:
    cutoff = _time_play.time() - _PLAY_CID_TTL_SEC
    for k in [k for k, v in _PLAY_CID_CACHE.items() if v.get("created_at", 0) < cutoff]:
        _PLAY_CID_CACHE.pop(k, None)
        _PLAY_CID_LOCKS.pop(k, None)


async def _play_resolve_session(task: str, cond: str, seed: int, env_id: str) -> dict:
    """Create a session via the env's POST handler. Returns the cache entry."""
    payload: dict[str, object] = {"task_id": task, "seed": seed}
    if cond == "intervention":
        # Scan ALL variants — patient_portal uses pp_*.yaml and robinhood
        # uses rh_*.yaml, so an env_id-prefixed glob would miss them.
        # 519 files; the cost is dominated by yaml.safe_load, not the listing.
        variants_dir = BASE_DIR / "injector" / "variants"
        match: str | None = None
        for fp in sorted(variants_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(fp.read_text()) or {}
            except Exception:
                continue
            if data.get("base_task_id") == task:
                match = fp.name
                break
        if not match:
            raise HTTPException(status_code=404, detail=f"No intervention variant for: {task}")
        payload["variant_filename"] = match

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as client:
        resp = await client.post(f"/api/env/{env_id}/session", json=payload)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Session creation failed: {resp.text[:300]}",
        )
    data = resp.json()
    return {
        "session_id": data["session_id"],
        "env_id": env_id,
        "start_path": data.get("start_path") or "/",
        "created_at": _time_play.time(),
    }


@app.get("/play")
async def play(
    task: str,
    cond: str = "clean",
    seed: int = 42,
    cid: str | None = None,
    mode: str | None = None,
):
    """One-click launch entry-point used by the public site.

    Two call patterns:

    * **Dual-tab (recommended).** The site click-handler synchronously
      opens two windows with the same ``cid`` and ``mode=bench`` /
      ``mode=control``. The first to arrive creates the session under
      ``cid``; the second reuses it. Each tab is 302-redirected to its
      respective URL (benchmark SPA or control panel). No "Launching…"
      screen, no popup-blocker issues — both windows are opened from
      the original user gesture.

    * **Single-tab fallback.** No ``cid`` provided. Returns a tiny
      HTML page that creates the session and tries to ``window.open``
      the bench tab while redirecting the current tab to the control
      panel — works when the user lands here from a bare URL (no
      site-side dual-open), but the popup blocker may block the
      second tab.
    """
    try:
        task_def = get_task(task)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown task: {task}")
    env_id = task_def.env_id

    # ── Dual-tab path ────────────────────────────────────────────────
    if cid and mode in {"bench", "control"}:
        _play_cache_evict_stale()
        lock = _PLAY_CID_LOCKS.setdefault(cid, _asyncio_play.Lock())
        async with lock:
            info = _PLAY_CID_CACHE.get(cid)
            if info is None:
                info = await _play_resolve_session(task, cond, seed, env_id)
                _PLAY_CID_CACHE[cid] = info

        sid = info["session_id"]
        start_path = info["start_path"]
        if mode == "bench":
            # Dual-tab mode: bench is pure SPA, the dedicated control panel
            # tab holds the Record/Evaluate buttons. We deliberately omit
            # &control=on, which would draw the in-bench floating toolbar —
            # redundant with the separate control tab and the UX the user
            # specifically asked us to drop.
            sep = "&" if "?" in start_path else "?"
            return RedirectResponse(
                f"/env/{env_id}{start_path}{sep}session={sid}",
                status_code=302,
            )
        # Control tab gets ?demo=1 so it shows the "recording is not saved"
        # banner. Local users hitting /control/... directly don't see it.
        return RedirectResponse(f"/control/{env_id}/{sid}?demo=1", status_code=302)

    # ── Single-tab fallback (HTML launching screen) ──────────────────
    info = await _play_resolve_session(task, cond, seed, env_id)
    session_id = info["session_id"]
    start_path = info["start_path"]
    sep = "&" if "?" in start_path else "?"
    bench_url = f"/env/{env_id}{start_path}{sep}session={session_id}&control=on"
    control_url = f"/control/{env_id}/{session_id}?demo=1"

    title_safe = (task_def.title or task).replace("<", "&lt;").replace(">", "&gt;")
    cond_label = "intervention" if cond == "intervention" else "clean"
    html = (PLAY_TEMPLATE
            .replace("__TITLE__", title_safe)
            .replace("__COND__", cond_label)
            .replace("__BENCH_URL__", json.dumps(bench_url))
            .replace("__CONTROL_URL__", json.dumps(control_url))
            .replace("__BENCH_HREF__", bench_url)
            .replace("__ENV_ID__", env_id))
    return HTMLResponse(content=html)


PLAY_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Launching __TITLE__</title>
  <style>
    body { background:#0d1117; color:#fafaf7; font-family:system-ui,-apple-system,sans-serif;
           display:grid; place-items:center; height:100vh; margin:0; }
    .panel { text-align:center; padding:2rem; max-width:32rem; }
    h1 { font-weight:300; font-size:1.4rem; margin:0 0 .25rem; }
    .badge { display:inline-block; background:#1f2937; color:#9aa4b2; font-size:.7rem;
             text-transform:uppercase; letter-spacing:.1em; padding:.2rem .6rem;
             border-radius:999px; margin-bottom:1rem; }
    p { color:#9aa4b2; font-size:.9rem; margin:.25rem 0; line-height:1.5; }
    a { color:#d9684a; text-decoration:none; }
    a:hover { text-decoration:underline; }
    .dots { margin:1rem 0; }
    .dot { display:inline-block; width:7px; height:7px; border-radius:50%;
           background:#d9684a; margin:0 3px; animation: bounce 1.4s infinite; }
    .dot:nth-child(2) { animation-delay:.2s }
    .dot:nth-child(3) { animation-delay:.4s }
    @keyframes bounce {
      0%, 80%, 100% { transform:scale(.5); opacity:.4 }
      40% { transform:scale(1); opacity:1 }
    }
  </style>
</head>
<body>
  <div class="panel">
    <span class="badge">__COND__ condition</span>
    <h1>Launching __TITLE__</h1>
    <div class="dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
    <p>Opening the benchmark SPA in a new tab. This tab will become the control panel where you can see the task instruction and score your attempt.</p>
    <p style="margin-top:1.25rem">Browser blocked the popup?
       <a href="__BENCH_HREF__" target="_blank" rel="noreferrer">Open benchmark manually</a>.</p>
  </div>
  <script>
    var benchUrl = __BENCH_URL__;
    var controlUrl = __CONTROL_URL__;
    var envId = "__ENV_ID__";
    window.open(benchUrl, 'wab-bench-' + envId);
    setTimeout(function() { window.location.replace(controlUrl); }, 400);
  </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
@app.get("/launch", response_class=HTMLResponse)
async def index():
    """Home page: environment overview + task launcher."""
    current_manifest = build_manifest()
    env_base_urls = {
        env["env_id"]: env.get("base_url", f"/env/{env['env_id']}")
        for env in current_manifest.get("environments", [])
    }

    env_base_url_json = json.dumps(env_base_urls, sort_keys=True)

    # Build per-env task data for the table view
    _DIFF_ORDER = {"easy": 0, "medium": 1, "hard": 2, "expert": 3, "frontier": 4}
    env_task_data_json = json.dumps([
        {
            "env_id": env["env_id"],
            "title": env["title"],
            "available": bool(env.get("available", False)),
            "description": env.get("description", ""),
            "unavailable_reason": env.get("unavailable_reason", ""),
            "tasks": [
                {
                    "task_id": t["task_id"],
                    "title": t.get("title", t["task_id"]),
                    "difficulty": t.get("difficulty", ""),
                    "primitives": t.get("primary_primitives", []),
                    "steps": t.get("expected_steps", ""),
                    "time": t.get("time_limit_seconds", ""),
                }
                for t in sorted(env.get("tasks", []), key=lambda x: (
                    _DIFF_ORDER.get(x.get("difficulty", ""), 9),
                    x.get("title", ""),
                ))
            ],
        }
        for env in current_manifest.get("environments", [])
    ], sort_keys=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BreakingWeb</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               color: #1f2328; background: #f6f8fa; }}

        .header {{ background: #24292f; color: #fff; padding: 20px 0; }}
        .header-inner {{ max-width: 1100px; margin: 0 auto; padding: 0 24px;
                        display: flex; justify-content: space-between; align-items: center; }}
        .header h1 {{ font-size: 1.4rem; font-weight: 700; letter-spacing: -0.3px; }}
        .header-stats {{ display: flex; gap: 20px; font-size: 0.82rem; color: #8b949e; }}
        .header-stats span {{ color: #fff; font-weight: 600; }}

        .main {{ max-width: 1100px; margin: 0 auto; padding: 20px 24px; }}

        /* ── Environment tabs ── */
        .env-tabs {{ display: flex; gap: 6px; margin-bottom: 20px; flex-wrap: wrap; }}
        .env-tab {{ padding: 8px 18px; border: 1px solid #d0d7de; border-radius: 20px;
                    background: #fff; font-size: 13px; font-weight: 500; cursor: pointer;
                    display: flex; align-items: center; gap: 8px; transition: all .15s; }}
        .env-tab:hover {{ border-color: #24292f; color: #24292f; }}
        .env-tab.active {{ background: #24292f; color: #fff; border-color: #24292f; }}
        .env-tab.unavailable {{ opacity: 0.5; cursor: default; }}
        .env-tab .count {{ font-size: 11px; padding: 1px 7px; border-radius: 10px;
                          background: rgba(0,0,0,.08); font-weight: 600; }}
        .env-tab.active .count {{ background: rgba(255,255,255,.25); }}

        /* ── Task table ── */
        .task-table-wrap {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden; }}
        .task-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        .task-table th {{ text-align: left; padding: 10px 14px; background: #f6f8fa;
                         font-weight: 600; font-size: 12px; color: #656d76;
                         text-transform: uppercase; letter-spacing: 0.3px;
                         border-bottom: 1px solid #d0d7de; position: sticky; top: 0; }}
        .task-table td {{ padding: 8px 14px; border-bottom: 1px solid #eee; vertical-align: middle; }}
        .task-table tr {{ cursor: pointer; transition: background .1s; }}
        .task-table tr:hover {{ background: #f6f8fa; }}
        .task-table tr.selected {{ background: #eef0f2; }}

        .diff-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                       font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }}
        .diff-easy {{ background: #dafbe1; color: #1a7f37; }}
        .diff-medium {{ background: #fff8c5; color: #9a6700; }}
        .diff-hard {{ background: #ffebe9; color: #cf222e; }}
        .diff-expert {{ background: #f0e6ff; color: #7c3aed; }}
        .diff-frontier {{ background: #1f2328; color: #fff; }}

        .prim-tag {{ display: inline-block; padding: 1px 6px; border-radius: 3px;
                     font-size: 11px; background: #eff1f3; color: #656d76; margin-right: 3px; }}

        /* ── Sticky launch bar ── */
        .launch-bar {{ position: sticky; top: 0; z-index: 50;
                       background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
                       padding: 8px 14px; margin-bottom: 14px;
                       display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
                       box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
        .launch-bar__selected {{ font-weight: 600; font-size: 13px; color: #8b949e;
                                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px; }}
        .launch-bar__selected.active {{ color: #1f2328; }}
        .launch-bar__meta {{ font-size: 11px; color: #8b949e; white-space: nowrap; }}
        .launch-bar__sep {{ width: 1px; height: 24px; background: #d0d7de; flex-shrink: 0; }}
        .launch-bar__select {{ padding: 5px 8px; font-size: 12px; border: 1px solid #d0d7de;
                              border-radius: 5px; background: #fff; max-width: 180px; }}
        .launch-bar__seed {{ padding: 5px 8px; font-size: 12px; border: 1px solid #d0d7de;
                            border-radius: 5px; width: 70px; }}
        .launch-bar__select:focus, .launch-bar__seed:focus {{ outline: 2px solid #24292f; border-color: transparent; }}
        .launch-bar__status {{ font-size: 12px; color: #656d76; }}

        .btn-launch {{ padding: 9px 24px; background: #24292f; color: #fff; border: none;
                       border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;
                       white-space: nowrap; }}
        .btn-launch:hover {{ background: #1b1f23; }}
        .btn-launch:disabled {{ background: #8b949e; cursor: wait; }}

        .mode-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
                       font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }}
        .mode-standard {{ background: #dafbe1; color: #1a7f37; }}
        .mode-stress {{ background: #ffebe9; color: #cf222e; }}
        #variant-info {{ margin-top: 6px; padding: 6px 10px; background: #fff8c5;
                         border: 1px solid #ebd98b; border-radius: 6px; font-size: 12px; display: none; }}
        #status {{ font-size: 13px; color: #656d76; margin-top: 8px; }}

        /* ── Search / filter bar ── */
        .filter-bar {{ display: flex; gap: 8px; margin-bottom: 14px; align-items: center; flex-wrap: wrap; }}
        .filter-bar input {{ padding: 7px 12px; font-size: 13px; border: 1px solid #d0d7de;
                            border-radius: 6px; width: 240px; }}
        .filter-bar select {{ padding: 7px 10px; font-size: 13px; border: 1px solid #d0d7de; border-radius: 6px; }}
        .task-count {{ font-size: 12px; color: #656d76; margin-left: auto; }}

        .empty-state {{ padding: 40px 20px; text-align: center; color: #656d76; }}

        /* ── Footer ── */
        .footer {{ max-width: 1100px; margin: 30px auto 20px; padding: 0 24px;
                   font-size: 12px; color: #8b949e; display: flex; gap: 16px; }}
        .footer code {{ background: #eff1f3; padding: 1px 5px; border-radius: 3px; font-size: 11px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-inner">
            <h1>BreakingWeb</h1>
            <div class="header-stats">
                <div><span>{ENVIRONMENT_COUNT}</span> environments</div>
                <div><span>{ENV_TASK_COUNT}</span> tasks</div>
                <div>v{MANIFEST_VERSION}</div>
                <a href="/trajectories" style="color:#8b949e;text-decoration:none;border:1px solid #444;padding:3px 10px;border-radius:4px;font-size:12px">Trajectories</a>
                <a href="/static/docs.html" style="color:#8b949e;text-decoration:none;border:1px solid #444;padding:3px 10px;border-radius:4px;font-size:12px">Docs</a>
            </div>
        </div>
    </div>

    <div class="main">
        <!-- Environment tabs -->
        <div class="env-tabs" id="env-tabs"></div>

        <!-- Filter bar -->
        <div class="filter-bar">
            <input type="text" id="search" placeholder="Search tasks..." />
            <select id="diff-filter">
                <option value="">All difficulties</option>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
                <option value="expert">Expert</option>
                <option value="frontier">Frontier</option>
            </select>
            <select id="prim-filter">
                <option value="">All primitives</option>
                <option value="grounding">Grounding</option>
                <option value="planning">Planning</option>
                <option value="state_tracking">State Tracking</option>
                <option value="backtracking">Backtracking</option>
                <option value="patience">Patience</option>
                <option value="exploration">Exploration</option>
                <option value="verification">Verification</option>
            </select>
            <div class="task-count" id="task-count"></div>
        </div>

        <!-- Sticky launch bar -->
        <div class="launch-bar" id="launch-bar">
            <div class="launch-bar__selected" id="lp-title">Click a task to select</div>
            <div class="launch-bar__meta" id="lp-meta"></div>
            <div class="launch-bar__sep"></div>
            <select id="variant" class="launch-bar__select" title="Intervention">
                <option value="">No intervention</option>
            </select>
            <span class="mode-badge mode-standard" id="mode-badge" style="font-size:10px">STD</span>
            <div id="variant-info" style="display:none"></div>
            <input id="seed" type="number" class="launch-bar__seed" placeholder="Seed" title="Random seed" value="42" />
            <button class="btn-launch" id="btn-launch" onclick="launch()" disabled>Launch</button>
            <div id="status" class="launch-bar__status"></div>
        </div>

        <!-- Task table -->
        <div class="task-table-wrap">
            <table class="task-table">
                <thead>
                    <tr>
                        <th style="width:40%">Task</th>
                        <th style="width:10%">Difficulty</th>
                        <th style="width:30%">Primitives</th>
                        <th style="width:10%">Steps</th>
                        <th style="width:10%">Time</th>
                    </tr>
                </thead>
                <tbody id="task-body"></tbody>
            </table>
            <div class="empty-state" id="empty-state" style="display:none">No tasks match your filters.</div>
        </div>
    </div>

    <div class="footer">
        <div><code>GET /manifest</code> &mdash; manifest</div>
        <div><code>GET /health</code> &mdash; health</div>
        <div><code>/api/env/&lt;id&gt;/*</code> &mdash; environment API</div>
        <div><a href="/static/docs.html" style="color:#8b949e">Documentation</a></div>
    </div>

    <script>
    var ENV_DATA = {env_task_data_json};
    var envBaseUrls = {env_base_url_json};
    var allVariants = [];
    var selectedEnv = '';
    var selectedTaskId = '';

    // ── Restore saved filter state from localStorage ──
    var _stored = {{}};
    try {{ _stored = JSON.parse(localStorage.getItem('wab_filters') || '{{}}'); }} catch(e) {{}}
    if (_stored.env) selectedEnv = _stored.env;
    if (_stored.diff) document.getElementById('diff-filter').value = _stored.diff;
    if (_stored.prim) document.getElementById('prim-filter').value = _stored.prim;
    if (_stored.search) document.getElementById('search').value = _stored.search;
    if (_stored.seed) document.getElementById('seed').value = _stored.seed;

    // URL ?env=<id> overrides localStorage so deep links land on the right tab.
    var _urlParams = new URLSearchParams(window.location.search);
    var _envFromUrl = _urlParams.get('env');
    if (_envFromUrl) selectedEnv = _envFromUrl;

    function saveFilters() {{
        try {{
            localStorage.setItem('wab_filters', JSON.stringify({{
                env: selectedEnv,
                diff: document.getElementById('diff-filter').value,
                prim: document.getElementById('prim-filter').value,
                search: document.getElementById('search').value,
                seed: document.getElementById('seed').value,
            }}));
        }} catch(e) {{}}
    }}

    // ── Render env tabs ──
    var tabsEl = document.getElementById('env-tabs');
    // "All" tab
    var allTab = document.createElement('div');
    allTab.className = 'env-tab' + (selectedEnv === '' ? ' active' : '');
    allTab.dataset.env = '';
    var total = ENV_DATA.reduce(function(s,e){{ return s + e.tasks.length; }}, 0);
    allTab.innerHTML = 'All <span class="count">' + total + '</span>';
    allTab.onclick = function() {{ selectEnv(''); }};
    tabsEl.appendChild(allTab);

    ENV_DATA.forEach(function(env) {{
        var tab = document.createElement('div');
        tab.className = 'env-tab' + (env.available ? '' : ' unavailable') + (env.env_id === selectedEnv ? ' active' : '');
        tab.dataset.env = env.env_id;
        tab.innerHTML = env.title + ' <span class="count">' + env.tasks.length + '</span>';
        tab.onclick = function() {{ if (env.available) selectEnv(env.env_id); }};
        tab.title = env.available ? env.description : (env.unavailable_reason || 'Unavailable');
        tabsEl.appendChild(tab);
    }});

    function selectEnv(envId) {{
        selectedEnv = envId;
        document.querySelectorAll('.env-tab').forEach(function(t) {{
            t.classList.toggle('active', t.dataset.env === envId);
        }});
        saveFilters();
        renderTasks();
    }}

    // ── Render task rows ──
    function renderTasks() {{
        var body = document.getElementById('task-body');
        var search = document.getElementById('search').value.toLowerCase();
        var diff = document.getElementById('diff-filter').value;
        var prim = document.getElementById('prim-filter').value;
        body.innerHTML = '';
        var count = 0;

        ENV_DATA.forEach(function(env) {{
            if (selectedEnv && env.env_id !== selectedEnv) return;
            if (!env.available) return;

            env.tasks.forEach(function(task) {{
                if (diff && task.difficulty !== diff) return;
                if (prim && task.primitives.indexOf(prim) < 0) return;
                if (search && task.title.toLowerCase().indexOf(search) < 0 &&
                    task.task_id.toLowerCase().indexOf(search) < 0 &&
                    task.primitives.join(' ').toLowerCase().indexOf(search) < 0) return;

                count++;
                var tr = document.createElement('tr');
                tr.dataset.taskId = task.task_id;
                tr.dataset.env = env.env_id;
                if (task.task_id === selectedTaskId) tr.className = 'selected';
                tr.onclick = function() {{ selectTask(task.task_id, env.env_id, task); }};

                var primsHtml = task.primitives.map(function(p) {{
                    return '<span class="prim-tag">' + p + '</span>';
                }}).join('');
                var timeMin = task.time ? Math.round(task.time / 60) + 'm' : '';

                tr.innerHTML =
                    '<td><strong>' + task.title + '</strong>' +
                    '<div style="font-size:11px;color:#8b949e;margin-top:1px">' + env.env_id + ' / ' + task.task_id + '</div></td>' +
                    '<td><span class="diff-badge diff-' + task.difficulty + '">' + task.difficulty + '</span></td>' +
                    '<td>' + primsHtml + '</td>' +
                    '<td style="text-align:center;color:#656d76">' + (task.steps || '') + '</td>' +
                    '<td style="text-align:center;color:#656d76">' + timeMin + '</td>';
                body.appendChild(tr);
            }});
        }});

        document.getElementById('task-count').textContent = count + ' task' + (count !== 1 ? 's' : '');
        document.getElementById('empty-state').style.display = count === 0 ? '' : 'none';
    }}

    document.getElementById('search').addEventListener('input', function() {{ saveFilters(); renderTasks(); }});
    document.getElementById('diff-filter').addEventListener('change', function() {{ saveFilters(); renderTasks(); }});
    document.getElementById('prim-filter').addEventListener('change', function() {{ saveFilters(); renderTasks(); }});
    document.getElementById('seed').addEventListener('change', saveFilters);

    // ── Select task → show launch panel ──
    function selectTask(taskId, envId, task) {{
        selectedTaskId = taskId;
        document.querySelectorAll('.task-table tr').forEach(function(r) {{
            r.classList.toggle('selected', r.dataset.taskId === taskId);
        }});
        document.getElementById('btn-launch').disabled = false;
        var titleEl = document.getElementById('lp-title');
        titleEl.textContent = task.title;
        titleEl.classList.add('active');
        document.getElementById('lp-meta').textContent = envId + ' / ' + task.difficulty;

        // Update variants
        var sel = document.getElementById('variant');
        while (sel.options.length > 1) sel.remove(1);
        var matching = allVariants.filter(function(v) {{ return v.base_task_id === taskId; }});
        matching.forEach(function(v) {{
            var opt = document.createElement('option');
            opt.value = v.filename;
            opt.textContent = '[' + v.target_primitive + '] ' + v.description.slice(0, 70);
            opt.dataset.desc = v.description;
            opt.dataset.primitive = v.target_primitive;
            sel.appendChild(opt);
        }});
        sel.value = '';
        document.getElementById('variant-info').style.display = 'none';
        document.getElementById('mode-badge').textContent = 'Standard';
        document.getElementById('mode-badge').className = 'mode-badge mode-standard';

    }}

    // ── Variant change ──
    document.getElementById('variant').addEventListener('change', function() {{
        var sel = this;
        var info = document.getElementById('variant-info');
        var badge = document.getElementById('mode-badge');
        var opt = sel.options[sel.selectedIndex];
        if (sel.value) {{
            info.style.display = 'block';
            info.textContent = (opt.dataset.primitive || '') + ' — ' + (opt.dataset.desc || '');
            badge.textContent = 'Stress';
            badge.className = 'mode-badge mode-stress';
        }} else {{
            info.style.display = 'none';
            badge.textContent = 'Standard';
            badge.className = 'mode-badge mode-standard';
        }}
    }});

    // ── Launch ──
    async function launch() {{
        if (!selectedTaskId) return;
        var btn = document.getElementById('btn-launch');
        var status = document.getElementById('status');
        btn.disabled = true;
        status.textContent = 'Creating session...';

        var variant = document.getElementById('variant').value;
        var seedVal = document.getElementById('seed').value;
        var envId = '';
        ENV_DATA.forEach(function(e) {{ e.tasks.forEach(function(t) {{ if (t.task_id === selectedTaskId) envId = e.env_id; }}); }});

        var payload = {{ task_id: selectedTaskId }};
        if (seedVal) payload.seed = parseInt(seedVal);
        if (variant) payload.variant_filename = variant;

        try {{
            var resp = await fetch('/api/env/' + envId + '/session', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload),
            }});
            if (!resp.ok) {{
                var err = await resp.json();
                status.textContent = 'Error: ' + (err.detail || resp.statusText);
                btn.disabled = false;
                return;
            }}
            var data = await resp.json();
            var baseUrl = envBaseUrls[envId] || ('/env/' + envId);
            var startPath = data.start_path || '/';
            var sep = startPath.indexOf('?') >= 0 ? '&' : '?';
            var benchUrl = baseUrl.replace(/\\/+$/, '') + startPath + sep + 'session=' + encodeURIComponent(data.session_id) + '&control=on';
            var controlUrl = '/control/' + envId + '/' + encodeURIComponent(data.session_id);
            // Open the benchmark tab first (user-gesture) then the control tab
            // Env-scoped window names so reset navigates the same tabs instead of orphaning them.
            var benchTab = window.open(benchUrl, 'wab-bench-' + envId);
            var controlTab = window.open(controlUrl, 'wab-control-' + envId);
            if (!benchTab || !controlTab) {{
                status.innerHTML = 'Popups blocked. <a href="' + controlUrl + '" target="_blank">Open control</a> &middot; <a href="' + benchUrl + '" target="_blank">Open benchmark</a>';
                btn.disabled = false;
                return;
            }}
            status.textContent = 'Launched. Use the control tab to record and evaluate.';
            btn.disabled = false;
        }} catch(e) {{
            status.textContent = 'Error: ' + e.message;
            btn.disabled = false;
        }}
    }}

    // ── Load variants ──
    var envIds = ENV_DATA.map(function(e) {{ return e.env_id; }});
    Promise.all(envIds.map(function(eid) {{
        return fetch('/api/env/' + eid + '/variants')
            .then(function(r) {{ return r.ok ? r.json() : []; }})
            .catch(function() {{ return []; }});
    }})).then(function(results) {{
        for (var i = 0; i < results.length; i++) allVariants = allVariants.concat(results[i]);

        // ── Deep-link from URL: ?task=<task_id>&cond=clean|intervention&seed=<n> ──
        // Pre-select a task (and optionally pick the first intervention variant)
        // so the site can hand a visitor straight onto the launch panel.
        var taskFromUrl = _urlParams.get('task');
        var seedFromUrl = _urlParams.get('seed');
        if (seedFromUrl && /^\d+$/.test(seedFromUrl)) {{
            document.getElementById('seed').value = seedFromUrl;
            saveFilters();
        }}
        if (taskFromUrl) {{
            var matchEnv = null, matchTask = null;
            ENV_DATA.forEach(function(e) {{
                e.tasks.forEach(function(t) {{
                    if (t.task_id === taskFromUrl) {{ matchEnv = e; matchTask = t; }}
                }});
            }});
            if (matchEnv && matchTask) {{
                selectEnv(matchEnv.env_id);
                selectTask(matchTask.task_id, matchEnv.env_id, matchTask);
                if (_urlParams.get('cond') === 'intervention') {{
                    var v = allVariants.find(function(x) {{ return x.base_task_id === taskFromUrl; }});
                    if (v) {{
                        var variantSel = document.getElementById('variant');
                        variantSel.value = v.filename;
                        variantSel.dispatchEvent(new Event('change'));
                    }}
                }}
                var selRow = document.querySelector('.task-table tr.selected');
                if (selRow) selRow.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }}
    }});

    // ── Initial render ──
    renderTasks();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/trajectories", response_class=HTMLResponse)
async def list_trajectories():
    """Directory page of trajectory visualisations shipped in /static/*_viz.html."""
    import os as _os
    from datetime import datetime as _dt
    entries: list[dict] = []
    for path in sorted(STATIC_DIR.glob("*_viz.html")):
        stat = path.stat()
        entries.append({
            "name": path.stem,
            "href": f"/static/{path.name}",
            "size_kb": round(stat.st_size / 1024, 1),
            "mtime": _dt.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })

    rows = "".join(
        f'<tr><td><a href="{e["href"]}">{e["name"]}</a></td>'
        f'<td style="text-align:right;color:#656d76">{e["size_kb"]} KB</td>'
        f'<td style="color:#656d76">{e["mtime"]}</td></tr>'
        for e in entries
    ) or '<tr><td colspan="3" style="padding:30px;color:#656d76;text-align:center">No trajectories yet. Generate one with <code>python -m breakingweb.scripts.run_bedrock_subset</code> or <code>python -m breakingweb.visualize &lt;results.json&gt;</code>.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang=\"en\"><head><meta charset=\"UTF-8\"><title>Trajectories — BreakingWeb</title>
<style>
  body {{ font-family:-apple-system,sans-serif; max-width:900px; margin:0 auto; padding:2rem; color:#1f2328; }}
  a {{ color:#0969da; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
  table {{ width:100%; border-collapse:collapse; margin-top:1rem; font-size:0.9rem; }}
  th {{ text-align:left; padding:8px 10px; border-bottom:2px solid #d0d7de; background:#f6f8fa; font-size:0.78rem; text-transform:uppercase; color:#656d76; }}
  td {{ padding:8px 10px; border-bottom:1px solid #eaecef; }}
  tr:hover td {{ background:#f9fbfd; }}
  code {{ background:#f6f8fa; border:1px solid #d0d7de; padding:1px 5px; border-radius:4px; font-size:0.84em; }}
</style></head><body>
<a href=\"/launch\" style=\"font-size:0.85rem\">&larr; Back to launcher</a>
<h1 style=\"margin-top:0.5rem\">Trajectory Visualisations</h1>
<p style=\"color:#656d76\">Self-contained viz HTMLs produced by <code>visualize.py</code> (or <code>run_bedrock_subset.py</code>), served from <code>{STATIC_DIR.name}/*_viz.html</code>.</p>
<table><thead><tr><th>Name</th><th style=\"text-align:right\">Size</th><th>Modified</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/manifest")
async def get_manifest():
    """Return the merged benchmark manifest."""
    return build_manifest()


_SAFE_ID = re.compile(r"^[A-Za-z0-9_]+$")
_TASKS_DIR = BASE_DIR / "tasks"
_VARIANTS_DIR = BASE_DIR / "injector" / "variants"


def _load_yaml_safe(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text())
    return raw if isinstance(raw, dict) else {}


@app.get("/task/{task_id}")
def get_task_yaml(task_id: str) -> dict:
    """Return the parsed task YAML so browser-only workers can audit without
    filesystem access. task_id is an alphanumeric/underscore identifier; no
    path traversal is possible.
    """
    if not _SAFE_ID.match(task_id):
        raise HTTPException(status_code=400, detail="invalid task_id")
    for env_dir in _TASKS_DIR.iterdir():
        if not env_dir.is_dir() or env_dir.name.startswith("_"):
            continue
        candidate = env_dir / f"{task_id}.yaml"
        if candidate.is_file():
            return _load_yaml_safe(candidate)
    raise HTTPException(status_code=404, detail=f"task {task_id} not found")


@app.get("/variant/{variant_id}")
def get_variant_yaml(variant_id: str) -> dict:
    """Return the parsed intervention-variant YAML."""
    if not _SAFE_ID.match(variant_id):
        raise HTTPException(status_code=400, detail="invalid variant_id")
    candidate = _VARIANTS_DIR / f"{variant_id}.yaml"
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"variant {variant_id} not found")
    return _load_yaml_safe(candidate)


async def _proxy_to_dev_frontend(dev_url: str, path: str, request: Request) -> Response:
    """Proxy a request to the Vite dev server, so browsers behind NAT (e.g. WSL2) never need direct access."""
    target = _join_public_base_url(dev_url, path=path, query=str(request.url.query))
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.request(
            method=request.method,
            url=target,
            headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "connection")},
            content=await request.body(),
        )
    excluded = {"transfer-encoding", "connection", "keep-alive"}
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
    return Response(content=resp.content, status_code=resp.status_code, headers=headers)


@app.get("/env/{env_id}")
async def redirect_env_root(env_id: str, request: Request):
    """Redirect bare /env/<id> to the home-page launcher (which has variant support)."""
    if env_id not in KNOWN_ENV_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown environment: {env_id}")
    dev_url = _env_dev_base_url(env_id)
    if dev_url:
        if request.query_params.get("session"):
            return await _proxy_to_dev_frontend(dev_url, "", request)
        return RedirectResponse(url="/", status_code=302)
    if request.query_params.get("session"):
        return _serve_env_html(env_id)
    return RedirectResponse(url="/", status_code=302)


@app.get("/env/{env_id}/{path:path}")
async def serve_environment_spa(env_id: str, request: Request, path: str = ""):
    """Serve a built React SPA for an advanced environment."""
    if env_id not in KNOWN_ENV_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown environment: {env_id}")
    dev_url = _env_dev_base_url(env_id)
    if dev_url:
        return await _proxy_to_dev_frontend(dev_url, path, request)
    if not path:
        if request.query_params.get("session"):
            return _serve_env_html(env_id)
        return RedirectResponse(url="/", status_code=302)
    return _serve_env_html(env_id)


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "environments": ENVIRONMENT_COUNT,
        "environment_tasks": ENV_TASK_COUNT,
        "manifest_fingerprint": MANIFEST_FINGERPRINT,
    }


@app.post("/api/env/{env_id}/session/{session_id}/chat")
async def append_chat(env_id: str, session_id: str, body: dict, request: Request):
    """Record an agent chat message into state.chat.

    Called by the BrowserGym harness each time the agent emits a
    ``send_msg_to_user`` / ``report_infeasible`` message. Best-effort: silently
    no-ops if the session is unknown so chat forwarding never aborts a task.
    """
    session_manager: SessionManager = request.app.state.session_manager
    role = body.get("role", "assistant")
    content = body.get("content", "")
    session_manager.append_chat_message(session_id, role=role, content=content)
    return {"ok": True}


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="BreakingWeb server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--reload", action="store_true", default=True, help="Enable autoreload (default: on)")
    parser.add_argument("--no-reload", action="store_false", dest="reload", help="Disable autoreload")
    args = parser.parse_args()

    uvicorn.run("breakingweb.app:app", host=args.host, port=args.port, reload=args.reload)
