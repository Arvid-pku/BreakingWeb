#!/usr/bin/env python
"""Preview what an annotator will see before they start recording.

Shows two sections per assignment:
  A. Human-facing preview — title + instruction + env name + cold/warm flow
     (NO primitive label, NO intervention label, NO expected_steps, NO seed,
      NO evaluator checks, NO YAML metadata).
  B. Debug/admin preview — full metadata, variant info, expected trace paths,
     launch payload, dry-run launchability check (optional with --launch-probe).

Usage:
    python breakingweb/human/preview_assignment.py \\
        --annotator P1 --role primary --index 0
    python breakingweb/human/preview_assignment.py \\
        --annotator D1 --role duplicate --index 0
    python breakingweb/human/preview_assignment.py \\
        --annotator P4 --role primary --index 5 --launch-probe \\
        --backend-url http://127.0.0.1:8080

`--launch-probe` POSTs `/api/env/{env}/session` to verify the task-condition
launches cleanly, then deletes the session — does NOT actually record. Requires
the WAB backend running and `BREAKINGWEB_CONTROLLER_SECRET` exported.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO / "breakingweb/human/assignments_v1.yaml"
TRACES_ROOT = REPO / "breakingweb/human/traces"


def load_assignments() -> tuple[list[dict], list[dict]]:
    plan = yaml.safe_load(PLAN_PATH.read_text())
    return plan["condition_assignments"], plan.get("duplicate_condition_assignments", [])


def filter_assignments(role: str, annotator: str) -> list[dict]:
    primary, duplicate = load_assignments()
    pool = primary if role == "primary" else duplicate
    name = annotator.strip().lower()
    matched = [a for a in pool if a["annotator"].lower() == name]
    if not matched:
        valid = sorted({a["annotator"] for a in pool})
        raise SystemExit(
            f"No {role} assignments for {annotator!r}. "
            f"Valid {role} annotators: {', '.join(valid)}"
        )
    return matched


def render_instruction_template(
    base_task_id: str, env: str,
    backend_url: str, controller_secret: str,
    variant_filename: str | None = None,
) -> str | None:
    """Live-render the instruction by creating a session at seed 42 then deleting.

    Returns the resolved instruction text, or None if the backend is unreachable.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Controller-Secret": controller_secret,
    }
    payload = {"task_id": base_task_id, "seed": 42}
    if variant_filename:
        payload["variant_filename"] = variant_filename
    url = f"{backend_url.rstrip('/')}/api/env/{env}/session"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return None
    sid = body.get("session_id")
    instruction = (body.get("instruction") or "").strip() or None
    # Cleanup
    if sid:
        del_req = urllib.request.Request(
            f"{backend_url.rstrip('/')}/api/env/{env}/session/"
            f"{urllib.parse.quote(sid)}",
            headers=headers, method="DELETE")
        try:
            urllib.request.urlopen(del_req, timeout=10)
        except Exception:
            pass
    return instruction


def render_preview(
    entry: dict, role: str, *,
    backend_url: str | None = None,
    controller_secret: str | None = None,
    launch_probe: bool = False,
) -> dict:
    """Build both human-facing and debug/admin preview sections for one assignment."""
    aid = entry["aid"]
    base = entry["base"]
    env = entry["env"]
    cond = entry["cond"]
    title = entry.get("title", "")
    annotator = entry["annotator"]
    diff = entry["diff"]
    prim = entry["prim"]
    steps = entry["steps"]
    variant = entry.get("variant", {}) or {}
    variant_id = variant.get("id")
    variant_yaml = variant.get("yaml")

    # Resolve instruction (live render preferred; fall back to YAML template)
    rendered_instruction = None
    launchable = None
    if launch_probe and backend_url and controller_secret:
        variant_filename = Path(variant_yaml).name if variant_yaml else None
        rendered_instruction = render_instruction_template(
            base, env, backend_url, controller_secret,
            variant_filename=variant_filename if cond == "intervention" else None,
        )
        launchable = rendered_instruction is not None

    # Storage paths (cold + warm) per README §3
    base_dir = TRACES_ROOT / annotator / role / env / base / cond
    cold_dir = base_dir / "cold"
    warm_dir = base_dir / "warm"

    # Human-facing — what the annotator sees on the dashboard + control tab
    human_view = {
        "task_title": title or f"(see resolved instruction at recording time)",
        "website": env,
        "recording_flow": [
            "1. Click Start on the dashboard card.",
            "2. Read the resolved instruction in the Control tab. A 10-s "
            "countdown auto-starts the recorder; click Start now to begin earlier.",
            "3. Cold attempt: switch to the env tab, perform the task. "
            "Click Evaluate when done. Trace saves under .../cold/.",
            "4. Click Start warm attempt → ; env resets at the same seed.",
            "5. Warm attempt: redo the task using what you learned in cold. "
            "Click Evaluate. Trace saves under .../warm/.",
            "6. Click Done — close windows, or Leave optional feedback.",
        ],
    }
    if rendered_instruction:
        human_view["resolved_instruction"] = rendered_instruction

    # Debug/admin — everything the annotator must NOT see
    admin_view = {
        "assignment_id": aid,
        "assignment_role": role,
        "annotator": annotator,
        "base_task_id": base,
        "env": env,
        "difficulty": diff,
        "primary_primitive": prim,
        "condition": cond,
        "seed": 42,
        "expected_steps": steps,
        "task_yaml": entry.get("yaml"),
        "intervention_variant_id": variant_id,
        "intervention_variant_yaml": variant_yaml,
        "expected_cold_trace_dir": str(cold_dir),
        "expected_warm_trace_dir": str(warm_dir),
        "launch_payload": {
            "method": "POST",
            "endpoint": f"/api/env/{env}/session",
            "json": (
                {"task_id": base, "seed": 42}
                if cond == "clean"
                else {"task_id": base, "seed": 42,
                      "variant_filename":
                          Path(variant_yaml).name if variant_yaml else None}
            ),
        },
    }
    if role == "duplicate":
        admin_view["original_primary_annotator"] = entry.get("original_primary_annotator")
    if launchable is not None:
        admin_view["dry_run_launchable"] = launchable

    return {"human_view": human_view, "admin_view": admin_view}


def format_human_section(p: dict) -> str:
    h = p["human_view"]
    lines = [
        "## A. Human-facing preview (what the annotator sees)",
        "",
        f"**Task title:** {h['task_title']}",
        f"**Website:** {h['website']}",
    ]
    if "resolved_instruction" in h:
        lines += ["", "**Resolved instruction (rendered at seed 42):**", "",
                  "> " + h["resolved_instruction"].replace("\n", "\n> ")]
    lines += ["", "**Recording flow:**"]
    lines += h["recording_flow"]
    return "\n".join(lines)


def format_admin_section(p: dict) -> str:
    a = p["admin_view"]
    lines = [
        "",
        "## B. Debug / admin preview (NOT shown to annotator)",
        "",
        f"- **assignment_id:** `{a['assignment_id']}`",
        f"- **assignment_role:** {a['assignment_role']}",
        f"- **annotator:** {a['annotator']}",
        f"- **base_task_id:** `{a['base_task_id']}`",
        f"- **env:** {a['env']}",
        f"- **difficulty:** {a['difficulty']}",
        f"- **primary_primitive:** {a['primary_primitive']}",
        f"- **condition:** {a['condition']}",
        f"- **seed:** {a['seed']}",
        f"- **expected_steps:** {a['expected_steps']}",
        f"- **task_yaml:** `{a['task_yaml']}`",
    ]
    if a.get("intervention_variant_id"):
        lines.append(f"- **intervention_variant_id:** `{a['intervention_variant_id']}`")
        lines.append(f"- **intervention_variant_yaml:** `{a['intervention_variant_yaml']}`")
    if "original_primary_annotator" in a:
        lines.append(f"- **original_primary_annotator:** {a['original_primary_annotator']}")
    lines += [
        f"- **expected cold trace dir:** `{a['expected_cold_trace_dir']}/{{metadata.json,trace.json}}`",
        f"- **expected warm trace dir:** `{a['expected_warm_trace_dir']}/{{metadata.json,trace.json}}`",
        "",
        "**Launch payload:**",
        "```json",
        json.dumps(a["launch_payload"], indent=2),
        "```",
    ]
    if "dry_run_launchable" in a:
        ok = a["dry_run_launchable"]
        lines.append(f"\n**Dry-run launchable:** {'✓ yes' if ok else '✗ no — backend rejected'}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Preview a human recording assignment.",
        epilog="Use --launch-probe to verify the task-condition launches "
               "cleanly against a running backend (no actual recording).",
    )
    p.add_argument("--annotator", required=True,
                   help="Annotator name (case-insensitive). e.g. P1, D1.")
    p.add_argument("--role", choices=["primary", "duplicate"], default="primary",
                   help="Assignment role to filter by.")
    p.add_argument("--index", type=int, default=0,
                   help="Zero-based index into the filtered list.")
    p.add_argument("--launch-probe", action="store_true",
                   help="Probe the backend (POST then DELETE /session) to "
                        "verify launchability + render the instruction.")
    p.add_argument("--backend-url", default="http://127.0.0.1:8080",
                   help="Backend URL for --launch-probe.")
    p.add_argument("--controller-secret",
                   default=os.environ.get("BREAKINGWEB_CONTROLLER_SECRET", os.environ.get("WEBSTRESS_CONTROLLER_SECRET", "")),
                   help="Controller secret. Defaults to "
                        "BREAKINGWEB_CONTROLLER_SECRET env var.")
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable JSON instead of markdown.")
    args = p.parse_args()

    matched = filter_assignments(args.role, args.annotator)
    if args.index < 0 or args.index >= len(matched):
        raise SystemExit(
            f"--index {args.index} out of range; "
            f"{args.annotator} has {len(matched)} {args.role} assignments "
            f"(valid: 0..{len(matched)-1}).")

    entry = matched[args.index]
    secret = args.controller_secret or None
    if args.launch_probe and not secret:
        print("WARNING: --launch-probe requested but no controller secret set; "
              "skipping live probe.", file=sys.stderr)

    preview = render_preview(
        entry, args.role,
        backend_url=args.backend_url if args.launch_probe else None,
        controller_secret=secret if args.launch_probe else None,
        launch_probe=args.launch_probe and bool(secret),
    )

    if args.json:
        print(json.dumps(preview, indent=2))
        return

    print(f"# Assignment preview — {args.annotator} ({args.role}, index {args.index} "
          f"of {len(matched)-1})")
    print()
    print(format_human_section(preview))
    print(format_admin_section(preview))


if __name__ == "__main__":
    main()
