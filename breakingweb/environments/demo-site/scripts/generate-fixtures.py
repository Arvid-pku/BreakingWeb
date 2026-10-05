#!/usr/bin/env python3
"""Generate static JSON fixtures for the demo site.

For each Gmail task, creates a fixture file containing the seeded state
and rendered instruction. Also produces a _manifest.json with task metadata.

Usage (from repo root):
    python breakingweb/environments/demo-site/scripts/generate-fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path so imports resolve.
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from breakingweb.backend.state import SessionManager
from breakingweb.task_rendering import render_template
from breakingweb.tasks._registry import load_all_tasks, tasks_by_env

# Fields to strip from serialised state — not needed for the demo.
STRIP_KEYS = {"audit_log", "benchmark_state", "created_at", "updated_at"}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "public" / "fixtures" / "gmail"


def generate_fixture(task, session_manager: SessionManager) -> dict:
    """Create a session, serialise state, render instruction, return fixture dict."""
    session_id, resolved_targets, seed = session_manager.create_session(
        task.env_id, task.task_id
    )
    state = session_manager.get(session_id)
    state_dict = state.model_dump(mode="json")

    # Strip unnecessary keys
    for key in STRIP_KEYS:
        state_dict.pop(key, None)

    instruction = render_template(
        task.instruction_template or task.instruction or "", resolved_targets
    )

    fixture = {
        "task_id": task.task_id,
        "env_id": task.env_id,
        "title": task.title,
        "difficulty": task.difficulty,
        "primary_primitives": task.primary_primitives,
        "secondary_primitives": task.secondary_primitives,
        "expected_steps": task.expected_steps,
        "time_limit_seconds": task.time_limit_seconds,
        "seed": seed,
        "start_path": task.start_path or "/inbox",
        "instruction": instruction,
        "resolved_targets": resolved_targets,
        "state": state_dict,
    }

    # Clean up session
    session_manager.destroy(session_id)
    return fixture


def build_manifest_entry(task) -> dict:
    """Build a metadata entry for _manifest.json."""
    return {
        "task_id": task.task_id,
        "title": task.title,
        "difficulty": task.difficulty,
        "primary_primitives": task.primary_primitives,
        "secondary_primitives": task.secondary_primitives,
        "expected_steps": task.expected_steps,
        "time_limit_seconds": task.time_limit_seconds,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    gmail_tasks = tasks_by_env().get("gmail", [])
    if not gmail_tasks:
        print("No Gmail tasks found.", file=sys.stderr)
        sys.exit(1)

    # Sort for deterministic output
    gmail_tasks.sort(key=lambda t: t.task_id)

    session_manager = SessionManager()
    manifest: list[dict] = []
    written = 0

    for task in gmail_tasks:
        try:
            fixture = generate_fixture(task, session_manager)
            out_path = OUTPUT_DIR / f"{task.task_id}.json"
            out_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
            manifest.append(build_manifest_entry(task))
            written += 1
            print(f"  OK  {task.task_id}")
        except Exception as exc:
            print(f"  FAIL  {task.task_id}: {exc}", file=sys.stderr)

    manifest_path = OUTPUT_DIR / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(f"\nGenerated {written}/{len(gmail_tasks)} fixtures -> {OUTPUT_DIR}")
    print(f"Manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
