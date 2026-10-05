#!/usr/bin/env python3
"""
BreakingWeb task debugger — observe, act, verify.

Works with any environment (Gmail, Robinhood, etc.) by auto-detecting
from the task_id prefix or an explicit --env flag.

Observe (browser):  screenshot + a11y tree of any page
Act (API):          call environment API endpoints
Verify (API):       run eval checks, dump server state

Usage:
  python debug.py start <task_id> [--seed N]         Create session, screenshot home
  python debug.py see [path]                          Screenshot + a11y tree
  python debug.py act <endpoint> <json> [--method M]  Call API endpoint
  python debug.py state                               Dump all server state
  python debug.py check                               Run eval checks
  python debug.py batch [task_id ...] [-w N]          Parallel quick-test

Parallel agents (each gets its own isolated session automatically):
  python debug.py start gmail_compose_new             # writes scripts/.debug_gmail_compose_new.json
  python debug.py -s scripts/.debug_gmail_compose_new.json see /inbox
  python debug.py -s scripts/.debug_gmail_compose_new.json check

Or use the env var:
  DEBUG_SESSION_FILE=/tmp/agent_1.json python debug.py start ...
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BASE = os.environ.get("WAB_URL", "http://127.0.0.1:8080")
DIR = Path("scripts/debug_screenshots")


# ── environment configs ─────────────────────────────────────────────────

@dataclass
class EnvConfig:
    name: str
    api_prefix: str          # e.g. "/api/env/gmail"
    frontend_base: str       # e.g. "/env/gmail"
    task_dir: str            # e.g. "breakingweb/tasks/gmail"
    variant_glob: str        # e.g. "gmail_*.yaml"
    task_prefix: str         # e.g. "gmail_"
    session_file: str        # e.g. "scripts/.gmail_session.json"
    state_sections: list = field(default_factory=list)
    display_keys: list = field(default_factory=list)


GMAIL = EnvConfig(
    name="gmail",
    api_prefix="/api/env/gmail",
    frontend_base="/env/gmail",
    task_dir="breakingweb/tasks/gmail",
    variant_glob="gmail_*.yaml",
    task_prefix="gmail_",
    session_file="scripts/.gmail_session.json",
    state_sections=[
        ("Emails",    "emails"),
        ("Labels",    "labels"),
        ("Filters",   "filters"),
        ("Contacts",  "contacts"),
        ("Settings",  "settings"),
        ("Search",    "search"),
    ],
    display_keys=[
        "id", "subject", "from_addr", "to", "is_read", "is_starred",
        "label", "name", "email", "color", "criteria", "action",
        "from_name", "snippet",
    ],
)

ROBINHOOD = EnvConfig(
    name="robinhood",
    api_prefix="/api/env/robinhood",
    frontend_base="/env/robinhood",
    task_dir="breakingweb/tasks/robinhood",
    variant_glob="rh_*.yaml",
    task_prefix="rh_",
    session_file="scripts/.rh_session.json",
    state_sections=[
        ("Account",       "account"),
        ("Positions",     "positions"),
        ("Orders",        "orders"),
        ("Options",       "options/orders"),
        ("Alerts",        "alerts"),
        ("Watchlists",    "watchlists"),
        ("Recurring",     "recurring"),
        ("Notifications", "notifications"),
        ("Transfers",     "transfers"),
        ("Settings",      "settings"),
    ],
    display_keys=[
        "symbol", "underlying_symbol", "name", "side", "order_type", "quantity",
        "status", "amount", "frequency", "condition", "target_price", "direction",
        "type", "is_read", "strike", "expiration", "option_type", "strategy",
        "two_factor_method", "id",
    ],
)

LMS = EnvConfig(
    name="lms",
    api_prefix="/api/env/lms",
    frontend_base="/env/lms",
    task_dir="breakingweb/tasks/lms",
    variant_glob="lms_*.yaml",
    task_prefix="lms_",
    session_file="scripts/.lms_session.json",
    state_sections=[
        ("Profile",       "profile"),
        ("Courses",       "courses"),
        ("Enrollments",   "enrollments"),
        ("Assignments",   "courses/{cid}/assignments"),
        ("Modules",       "courses/{cid}/modules"),
        ("Announcements", "announcements"),
        ("Calendar",      "calendar"),
        ("Messages",      "messages"),
    ],
    display_keys=[
        "id", "course_code", "title", "name", "status", "submission_status",
        "score", "file_name", "is_read", "priority", "type", "due_at",
        "weight_category", "position", "to", "subject",
    ],
)

PATIENT_PORTAL = EnvConfig(
    name="patient_portal",
    api_prefix="/api/env/patient_portal",
    frontend_base="/env/patient_portal",
    task_dir="breakingweb/tasks/patient_portal",
    variant_glob="pp_*.yaml",
    task_prefix="pp_",
    session_file="scripts/.pp_session.json",
    state_sections=[
        ("Profile",        "profile"),
        ("Providers",      "providers"),
        ("Appointments",   "appointments"),
        ("Messages",       "messages"),
        ("Medications",    "medications"),
        ("Labs",           "labs"),
        ("Referrals",      "referrals"),
        ("Claims",         "claims"),
        ("Immunizations",  "immunizations"),
        ("Pharmacies",     "pharmacies"),
    ],
    display_keys=[
        "id", "name", "specialty", "status", "medication", "test_name",
        "value", "flag", "subject", "category", "from_type", "provider_id",
        "is_read", "vaccine_name", "amount", "type", "reason",
    ],
)

ENVS = {"gmail": GMAIL, "robinhood": ROBINHOOD, "rh": ROBINHOOD,
        "lms": LMS, "patient_portal": PATIENT_PORTAL, "pp": PATIENT_PORTAL}

# Set by --session / -s CLI flag or DEBUG_SESSION_FILE env var.
# When set, ALL commands use this file instead of the env-default.
_SESSION_OVERRIDE: str | None = os.environ.get("DEBUG_SESSION_FILE")


def _detect_env(task_id: str | None) -> EnvConfig:
    """Auto-detect environment from task_id prefix."""
    if task_id:
        for cfg in (GMAIL, ROBINHOOD, LMS, PATIENT_PORTAL):
            if task_id.startswith(cfg.task_prefix):
                return cfg
    return GMAIL  # default


# ── session helpers ─────────────────────────────────────────────────────

def _sf(env: EnvConfig) -> Path:
    if _SESSION_OVERRIDE:
        return Path(_SESSION_OVERRIDE)
    return Path(env.session_file)


def _sf_for_task(task_id: str) -> Path:
    """Generate a unique, collision-free session file path from task_id."""
    return Path(f"scripts/.debug_{task_id}.json")


def _save(env: EnvConfig, d: dict):
    sf = _sf(env)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(d, indent=2))


def _load(env: EnvConfig) -> dict:
    sf = _sf(env)
    return json.loads(sf.read_text()) if sf.exists() else {}


def _load_any() -> tuple[dict, EnvConfig]:
    """Load session from override path or most-recent env default, or fail."""
    if _SESSION_OVERRIDE:
        p = Path(_SESSION_OVERRIDE)
        if p.exists():
            data = json.loads(p.read_text())
            env_name = data.get("env", "gmail")
            return data, ENVS.get(env_name, GMAIL)
        sys.exit(f"Session file not found: {p}\nRun: debug.py start <task_id>")

    # No override — find the most recently modified session file
    candidates = []
    for cfg in (GMAIL, ROBINHOOD, LMS, PATIENT_PORTAL):
        sf = Path(cfg.session_file)
        if sf.exists():
            candidates.append((sf.stat().st_mtime, sf, cfg))
    # Also check task-scoped session files (scripts/.debug_<task_id>.json)
    for sf in Path("scripts").glob(".debug_*.json"):
        data = json.loads(sf.read_text())
        env_name = data.get("env", "gmail")
        cfg = ENVS.get(env_name, GMAIL)
        candidates.append((sf.stat().st_mtime, sf, cfg))

    if candidates:
        candidates.sort(reverse=True)  # most recent first
        _, sf, cfg = candidates[0]
        data = json.loads(sf.read_text())
        return data, cfg

    sys.exit("No session. Run: debug.py start <task_id>")


def _sid_and_env() -> tuple[str, EnvConfig]:
    data, env = _load_any()
    if "session_id" not in data:
        sys.exit("No session. Run: debug.py start <task_id>")
    return data["session_id"], env


def _artifact_stem(env: EnvConfig, task_id: str | None = None) -> str:
    """Unique stem for screenshots/trees. Uses task_id when available."""
    if task_id:
        return task_id
    sf = _sf(env)
    stem = sf.stem.lstrip(".").removeprefix("debug_")
    return stem or "session"


def _api(env: EnvConfig) -> str:
    return f"{BASE}{env.api_prefix}"


def _request(env, method, path, payload=None, sid=None, client=None, include_session=True):
    c = client or httpx.Client(base_url=_api(env), timeout=30)
    method = method.upper()
    if method in {"GET", "DELETE"}:
        params = {"session_id": sid}
        if payload:
            params.update(payload)
        r = c.request(method, f"/{path}", params=params)
    else:
        body = dict(payload or {})
        if include_session:
            body.setdefault("session_id", sid)
        r = c.request(method, f"/{path}", json=body)
    r.raise_for_status()
    if not client:
        c.close()
    return r.json()


def _unwrap(data):
    return data["items"] if isinstance(data, dict) and "items" in data else data


# ── observe ─────────────────────────────────────────────────────────────

def see(path=None):
    """Screenshot + a11y tree of a page."""
    from playwright.sync_api import sync_playwright

    st, env = _load_any()
    if not st:
        sys.exit("No session.")

    sid = st["session_id"]
    p = path or st.get("current_path", "/")
    if not p.startswith("/"):
        p = f"/{p}"

    query_sep = "&" if "?" in p else "?"
    url = f"{BASE}{env.frontend_base}{p}{query_sep}session={sid}&agent_mode=1"
    DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=15000)
        time.sleep(1)

        stem = _artifact_stem(env, st.get("task_id"))
        ss = DIR / f"{stem}_current.png"
        page.screenshot(path=str(ss), full_page=True)

        try:
            tree = page.locator("body").aria_snapshot()
        except Exception:
            tree = "(unavailable)"

        (DIR / f"{stem}_current_tree.txt").write_text(tree)
        browser.close()

    st["current_path"] = p
    _save(env, st)

    print(f"PAGE: {p}")
    print(f"SCREENSHOT: {ss}")
    print(f"\nTREE:\n{tree}")
    return tree


# ── act ─────────────────────────────────────────────────────────────────

def act(endpoint, payload_json="{}", method="POST"):
    """Call an API endpoint with the current session_id injected."""
    sid, env = _sid_and_env()
    payload = json.loads(payload_json)
    result = _request(env, method, endpoint, payload=payload, sid=sid)
    print(json.dumps(result, indent=2, default=str))
    return result


# ── state ───────────────────────────────────────────────────────────────

def state():
    """Compact dump of all server state (parallel API calls)."""
    sid, env = _sid_and_env()

    sections = list(env.state_sections) + [("Degradation", f"degradation/{sid}")]

    fetched = {}
    with httpx.Client(base_url=_api(env), timeout=30) as client:
        with ThreadPoolExecutor(max_workers=len(sections)) as pool:
            futures = {}
            for label, ep in sections:
                def fetch(ep=ep):
                    if ep.startswith("degradation/"):
                        r = client.get(f"/{ep}")
                    else:
                        r = client.get(f"/{ep}", params={"session_id": sid})
                    r.raise_for_status()
                    return r.json()
                futures[pool.submit(fetch)] = label
            for fut in as_completed(futures):
                label = futures[fut]
                try:
                    fetched[label] = fut.result()
                except Exception:
                    pass

    for label, _ in sections:
        data = fetched.get(label)
        if data is None:
            continue
        data = _unwrap(data)
        if isinstance(data, list):
            if not data:
                continue
            print(f"\n{label} ({len(data)})")
            for item in data[:20]:
                parts = [f"{k}={item[k]}" for k in env.display_keys if k in item and item[k] is not None]
                print(f"  {' | '.join(parts)}")
        elif isinstance(data, dict):
            if label == "Degradation":
                injections = data.get("client_injections", [])
                print(f"\n{label}")
                print(f"  session_id: {data.get('session_id')}")
                print(f"  client_injections: {len(injections)}")
                continue
            vals = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool)) and v not in (None, "", False)}
            if vals:
                print(f"\n{label}")
                for k, v in vals.items():
                    print(f"  {k}: {v}")


# ── check ───────────────────────────────────────────────────────────────

def check():
    """Run eval checks. Returns (score, passed, total, details)."""
    st, env = _load_any()
    sid, tid = st["session_id"], st["task_id"]

    result = _request(env, "POST", "evaluate", {"session_id": sid, "task_id": tid}, sid=sid)
    score = result.get("score", 0)
    checks = result.get("check_results", result.get("checks", []))

    passed = sum(1 for c in checks if c.get("passed"))
    total = len(checks)

    print(f"\n{'PASS' if result.get('success') else 'FAIL'}  score={score:.3f}  ({passed}/{total} checks)")
    for c in checks:
        ok = c.get("passed", False)
        print(f"  {'>' if ok else 'X'} {c.get('desc', '?')}")

    return score, passed, total, checks


# ── start ───────────────────────────────────────────────────────────────

def start(task_id, seed=42, variant_filename=None, env_override=None):
    """Create a session and take initial screenshot.

    When no --session / DEBUG_SESSION_FILE is set, auto-generates a
    task-scoped session file (scripts/.debug_<task_id>.json) so that
    parallel starts never collide.
    """
    global _SESSION_OVERRIDE
    env = ENVS.get(env_override, _detect_env(task_id)) if env_override else _detect_env(task_id)

    # Auto-generate a collision-free session file when no override is set
    if not _SESSION_OVERRIDE:
        auto_path = _sf_for_task(task_id)
        _SESSION_OVERRIDE = str(auto_path)

    body = {"task_id": task_id, "seed": seed}
    if variant_filename:
        body["variant_filename"] = variant_filename

    resp = _request(env, "POST", "session", body, sid=None, include_session=False)
    sid = resp["session_id"]

    _save(env, {
        "session_id": sid,
        "task_id": task_id,
        "env": env.name,
        "variant_filename": variant_filename,
        "instruction": resp["instruction"],
        "start_path": resp.get("start_path", "/"),
        "current_path": resp.get("start_path", "/"),
        "seed": seed,
    })

    sf = _sf(env)
    print(f"ENV: {env.name}")
    print(f"SESSION: {sid}")
    print(f"SESSION_FILE: {sf}")
    print(f"TASK: {resp['instruction']}")
    print(f"\nFor subsequent commands, use:")
    print(f"  python scripts/debug.py -s {sf} see /inbox")
    print(f"  python scripts/debug.py -s {sf} check")

    see()
    return sid


# ── batch ───────────────────────────────────────────────────────────────

def _test_one_task(job: dict, env: EnvConfig, seed: int = 42) -> dict:
    """Test a single task or variant: create session + evaluate. Thread-safe."""
    tid = job["task_id"]
    variant_filename = job.get("variant_filename")
    with httpx.Client(base_url=_api(env), timeout=30) as client:
        try:
            body = {"task_id": tid, "seed": seed}
            if variant_filename:
                body["variant_filename"] = variant_filename
            resp = client.post("/session", json=body).json()
            if "session_id" not in resp:
                return {"task_id": tid, "variant_filename": variant_filename, "status": "crash", "error": str(resp)}
            sid = resp["session_id"]

            ev = client.post("/evaluate", json={"session_id": sid, "task_id": tid}).json()
            checks = ev.get("check_results", ev.get("checks", []))
            errored = [c for c in checks if c.get("error")]
            score = ev.get("score", 0)

            if errored:
                status = "ERROR"
            elif score >= 1.0:
                status = "VACUOUS"
            else:
                status = "ok"

            return {
                "task_id": tid,
                "variant_filename": variant_filename,
                "status": status,
                "score": score,
                "errors": [c.get("error") for c in errored],
            }
        except Exception as e:
            return {"task_id": tid, "variant_filename": variant_filename, "status": "crash", "error": str(e)}


def batch(task_ids, workers=8, include_variants=False, variants_only=False, env_override=None):
    """Parallel quick-test: create session + run checks for each task or variant."""
    import yaml

    # Determine which environments to test
    if env_override:
        envs_to_test = [ENVS[env_override]]
    elif task_ids:
        envs_to_test = list({_detect_env(tid) for tid in task_ids})
    else:
        # Auto-discover: test all envs that have task directories
        envs_to_test = [cfg for cfg in (GMAIL, ROBINHOOD, LMS, PATIENT_PORTAL) if Path(cfg.task_dir).is_dir()]

    jobs: list[tuple[dict, EnvConfig]] = []

    for env in envs_to_test:
        task_dir = Path(env.task_dir)
        if not task_dir.is_dir():
            continue

        if not task_ids or not variants_only:
            discovered = []
            for f in sorted(task_dir.glob("*.yaml")):
                if f.name.startswith("_"):
                    continue
                data = yaml.safe_load(f.read_text())
                discovered.append(data["task_id"])
            base_ids = [t for t in (task_ids or discovered) if t.startswith(env.task_prefix)]
            if not variants_only:
                jobs.extend(({"task_id": tid, "variant_filename": None}, env) for tid in base_ids)

        if include_variants or variants_only:
            variant_dir = Path("breakingweb/injector/variants")
            for f in sorted(variant_dir.glob(env.variant_glob)):
                data = yaml.safe_load(f.read_text()) or {}
                jobs.append((
                    {"task_id": data.get("base_task_id"), "variant_filename": f.name},
                    env,
                ))

    DIR.mkdir(parents=True, exist_ok=True)
    results = []
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_test_one_task, job, env): (job, env) for job, env in jobs}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            done += 1
            label = r["variant_filename"] or r["task_id"]

            if r["status"] != "ok":
                print(f"  [{done}/{len(jobs)}] {label}: {r['status']} score={r.get('score', '?')}")
                for err in r.get("errors", []):
                    if err:
                        print(f"    ERR: {err}")
                if r["status"] == "VACUOUS":
                    print(f"    VACUOUS PASS — task passes without any agent action")

    # Sort results to match input order
    order = {
        (job["task_id"], job.get("variant_filename")): i
        for i, (job, _) in enumerate(jobs)
    }
    results.sort(key=lambda r: order.get((r["task_id"], r.get("variant_filename")), 999))

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] in ("ERROR", "crash"))
    vac = sum(1 for r in results if r["status"] == "VACUOUS")
    print(f"\n{'='*50}")
    print(f"BATCH: {len(results)} runs | {ok} ok | {err} errors | {vac} vacuous  [{workers} workers]")
    if err + vac > 0:
        print("\nIssues:")
        for r in results:
            if r["status"] != "ok":
                print(f"  {r.get('variant_filename') or r['task_id']}: {r['status']}")

    (DIR / "_batch_results.json").write_text(json.dumps(results, indent=2))
    return results


# ── main ────────────────────────────────────────────────────────────────

def main():
    global _SESSION_OVERRIDE

    p = argparse.ArgumentParser(description="BreakingWeb task debugger")
    p.add_argument("--env", choices=["gmail", "robinhood", "rh", "lms", "patient_portal", "pp"],
                   help="Force environment (auto-detected from task_id if omitted)")
    p.add_argument("-s", "--session", help="Session file path (isolates parallel agents)")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("start");  s.add_argument("task_id"); s.add_argument("--seed", type=int, default=42); s.add_argument("--variant")
    s = sub.add_parser("see");    s.add_argument("path", nargs="?")
    s = sub.add_parser("act");    s.add_argument("endpoint"); s.add_argument("payload", nargs="?", default="{}"); s.add_argument("--method", default="POST")
    sub.add_parser("state")
    sub.add_parser("check")
    s = sub.add_parser("batch");  s.add_argument("task_ids", nargs="*"); s.add_argument("-w", "--workers", type=int, default=8); s.add_argument("--include-variants", action="store_true"); s.add_argument("--variants-only", action="store_true")

    args = p.parse_args()

    # CLI flag takes precedence over env var
    if args.session:
        _SESSION_OVERRIDE = args.session

    env_flag = getattr(args, "env", None)

    if args.cmd == "start":   start(args.task_id, args.seed, args.variant, env_override=env_flag)
    elif args.cmd == "see":   see(args.path)
    elif args.cmd == "act":   act(args.endpoint, args.payload, args.method)
    elif args.cmd == "state": state()
    elif args.cmd == "check": check()
    elif args.cmd == "batch": batch(args.task_ids, args.workers, args.include_variants, args.variants_only, env_override=env_flag)
    else: p.print_help()

if __name__ == "__main__":
    main()
