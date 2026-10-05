#!/usr/bin/env python3
"""Prepare evaluation results as static JSON for the demo site.

Reads a BreakingWeb result JSON and produces:
  - public/results/summary.json     — model metadata, aggregate stats, per-task scores
  - public/results/trajectories/<task_id>.json — simplified per-task trajectories

Usage (from repo root):
    python breakingweb/environments/demo-site/scripts/prepare-results.py \
        results/breakingweb/gmail_qwen3max_merged.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode


DEMO_PUBLIC = Path(__file__).resolve().parent.parent / "public"
RESULTS_DIR = DEMO_PUBLIC / "results"
TRAJECTORIES_DIR = RESULTS_DIR / "trajectories"


def simplify_step(step: dict) -> dict:
    """Extract the fields we need from a trajectory step."""
    targets_raw = step.get("targets") or {}

    def simplify_target(target: dict | None) -> dict:
        target = target or {}
        return {
            "role": target.get("role", ""),
            "name": target.get("name", ""),
            "nth": target.get("nth"),
            "selector": target.get("selector"),
            "bbox": target.get("bbox"),
        }

    if isinstance(targets_raw, dict) and (
        "role" in targets_raw or "name" in targets_raw or "selector" in targets_raw
    ):
        targets = {"ref": simplify_target(targets_raw)}
    else:
        targets = {
            key: simplify_target(targets_raw.get(key))
            for key in ("ref", "from_ref", "to_ref")
            if isinstance(targets_raw, dict) and targets_raw.get(key)
        }

    simplified = {
        "step": step.get("step"),
        "thought": step.get("thought", ""),
        "action": step.get("action"),
        "actions": step.get("actions") or [],
        "raw_actions": step.get("raw_actions") or [],
        "targets": targets,
        "action_targets": [
            simplify_target(target)
            for target in (step.get("action_targets") or [])
        ],
        "action_results": step.get("action_results") or [],
        "status": step.get("status", ""),
        "elapsed_seconds": step.get("elapsed_seconds", 0),
    }
    if step.get("replay_path"):
        simplified["replay_path"] = step["replay_path"]
    if step.get("result_path"):
        simplified["result_path"] = step["result_path"]
    return simplified


def normalize_route(pathname: str | None, query: str | None) -> str:
    pathname = pathname or "/inbox"
    query = query or ""
    pairs = [
        (key, value)
        for key, value in parse_qsl(query.lstrip("?"), keep_blank_values=True)
        if key not in {"session", "session_id"}
    ]
    encoded = urlencode(pairs)
    return f"{pathname}?{encoded}" if encoded else pathname


def derive_replay_paths(
    result: dict,
    simplified_steps: list[dict],
    total_elapsed_seconds: float,
) -> tuple[str, list[dict]]:
    replay = result.get("replay") or {}
    benchmark_state = result.get("benchmark_state") or {}
    start_time = benchmark_state.get("startTime")
    start_path = normalize_route(
        replay.get("start_path"),
        None,
    )

    route_events = sorted(
        (
            event
            for event in benchmark_state.get("events", []) or []
            if event.get("type") == "route_change"
        ),
        key=lambda event: event.get("timestamp", 0),
    )

    current_path = start_path
    event_idx = 0
    if simplified_steps:
        simplified_steps[0].setdefault("replay_path", start_path)

    for idx, step in enumerate(simplified_steps):
        if idx == 0:
            continue

        if start_time is not None:
            step_elapsed = step.get("elapsed_seconds", total_elapsed_seconds)
            step_ts = start_time + int(float(step_elapsed) * 1000)
            while (
                event_idx < len(route_events)
                and route_events[event_idx].get("timestamp", 0) <= step_ts
            ):
                detail = route_events[event_idx].get("detail") or {}
                current_path = normalize_route(
                    detail.get("pathname"),
                    detail.get("query"),
                )
                event_idx += 1

        step.setdefault("replay_path", current_path)

    final_path = current_path
    if start_time is not None:
        final_ts = start_time + int(float(total_elapsed_seconds) * 1000)
        while (
            event_idx < len(route_events)
            and route_events[event_idx].get("timestamp", 0) <= final_ts
        ):
            detail = route_events[event_idx].get("detail") or {}
            final_path = normalize_route(
                detail.get("pathname"),
                detail.get("query"),
            )
            event_idx += 1

    for idx, step in enumerate(simplified_steps):
        if idx + 1 < len(simplified_steps):
            step.setdefault("result_path", simplified_steps[idx + 1]["replay_path"])
        else:
            step.setdefault("result_path", final_path)

    return start_path, simplified_steps


def simplify_evaluation(evaluation: dict) -> dict:
    """Extract the evaluation fields needed by the replay page."""
    # Support both old field names (criteria_results/negative_results) and
    # current evaluator output (checks/negative_checks).
    positive_items = (
        evaluation.get("criteria_results")
        or evaluation.get("checks")
        or []
    )
    negative_items = (
        evaluation.get("negative_results")
        or evaluation.get("negative_checks")
        or []
    )
    criteria = [
        {
            "desc": item.get("check", "") or item.get("desc", ""),
            "passed": item.get("passed", False),
            "kind": "criterion",
        }
        for item in positive_items
    ]
    criteria.extend(
        {
            "desc": item.get("check", "") or item.get("desc", ""),
            "passed": item.get("passed", False),
            "kind": "penalty",
            "penalty": item.get("penalty", 0),
        }
        for item in negative_items
    )

    return {
        "score": evaluation.get("final_score", evaluation.get("score", 0)),
        "success": evaluation.get("success", False),
        "reasoning": evaluation.get("reasoning", ""),
        "criteria_results": criteria,
    }


def build_negative_checks(results_dir: Path) -> None:
    """Scan all trajectory files and emit negative-checks.json."""
    trajectories_dir = results_dir / "trajectories"
    if not trajectories_dir.exists():
        return

    checks: list[dict] = []
    for traj_path in sorted(trajectories_dir.glob("*.json")):
        with open(traj_path) as f:
            traj = json.load(f)
        task_id = traj.get("task_id", traj_path.stem)
        title = traj.get("title", task_id)
        difficulty = traj.get("difficulty", "")
        for cr in traj.get("evaluation", {}).get("criteria_results", []):
            if cr.get("penalty") is not None:
                checks.append({
                    "task_id": task_id,
                    "task_title": title,
                    "difficulty": difficulty,
                    "desc": cr.get("desc", ""),
                    "penalty": cr["penalty"],
                    "triggered": cr.get("passed") is False,
                })

    triggered_count = sum(1 for c in checks if c["triggered"])
    tasks_with_negatives = len({c["task_id"] for c in checks})

    payload = {
        "total_tasks_with_negatives": tasks_with_negatives,
        "total_negative_checks": len(checks),
        "triggered_count": triggered_count,
        "checks": checks,
    }

    out_path = results_dir / "negative-checks.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"  Negative checks -> {out_path} ({len(checks)} checks, {triggered_count} triggered)")


def process_result(result: dict) -> tuple[dict, dict]:
    """Process a single task result into a summary entry and simplified trajectory."""
    evaluation = result.get("evaluation") or {}
    agent = result.get("agent") or {}
    trajectory_raw = agent.get("trajectory") or []
    simplified_steps = [simplify_step(s) for s in trajectory_raw]
    total_elapsed_seconds = float(agent.get("elapsed_seconds", 0) or 0)
    default_start_path = normalize_route(
        (result.get("replay") or {}).get("start_path"),
        None,
    )
    start_path, simplified_steps = derive_replay_paths(
        result,
        simplified_steps,
        total_elapsed_seconds,
    )
    if not start_path:
        start_path = default_start_path

    summary_entry = {
        "task_id": result.get("task_id", ""),
        "title": result.get("title", ""),
        "env_id": result.get("env_id", ""),
        "difficulty": result.get("difficulty", ""),
        "primitives": result.get("primitives", []),
        "instruction": result.get("instruction", ""),
        "score": evaluation.get("final_score", evaluation.get("score", 0)),
        "success": evaluation.get("success", False),
        "steps": agent.get("steps", 0),
        "elapsed_seconds": agent.get("elapsed_seconds", 0),
        "completed": agent.get("completed", False),
        "reasoning": evaluation.get("reasoning", ""),
    }

    trajectory_payload = {
        "task_id": result.get("task_id", ""),
        "title": result.get("title", ""),
        "instruction": result.get("instruction", ""),
        "difficulty": result.get("difficulty", ""),
        "model": agent.get("model", ""),
        "total_steps": agent.get("steps", len(trajectory_raw)),
        "elapsed_seconds": agent.get("elapsed_seconds", 0),
        "completed": agent.get("completed", False),
        "start_path": start_path,
        "evaluation": simplify_evaluation(evaluation),
        "steps": simplified_steps,
    }
    return summary_entry, trajectory_payload


def main():
    if len(sys.argv) < 2:
        print("Usage: prepare-results.py <result_json_path>", file=sys.stderr)
        sys.exit(1)

    result_path = Path(sys.argv[1])
    if not result_path.exists():
        print(f"File not found: {result_path}", file=sys.stderr)
        sys.exit(1)

    with open(result_path) as f:
        data = json.load(f)

    results = data.get("results", [])
    if not results:
        print("No results found in input file.", file=sys.stderr)
        sys.exit(1)

    # Ensure output directories exist
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TRAJECTORIES_DIR.mkdir(parents=True, exist_ok=True)

    task_summaries: list[dict] = []
    total_score = 0.0
    success_count = 0

    for result in results:
        task_id = result.get("task_id", "unknown")
        try:
            summary_entry, trajectory = process_result(result)
            task_summaries.append(summary_entry)
            total_score += summary_entry["score"]
            if summary_entry["success"]:
                success_count += 1

            # Write per-task trajectory
            traj_path = TRAJECTORIES_DIR / f"{task_id}.json"
            traj_path.write_text(
                json.dumps(trajectory, indent=2, ensure_ascii=False) + "\n"
            )
            print(f"  OK  {task_id} (score={summary_entry['score']:.2f})")
        except Exception as exc:
            print(f"  FAIL  {task_id}: {exc}", file=sys.stderr)

    n = len(task_summaries)
    avg_score = total_score / n if n else 0.0

    # Aggregate stats by difficulty
    by_difficulty: dict[str, list[float]] = {}
    for entry in task_summaries:
        by_difficulty.setdefault(entry["difficulty"], []).append(entry["score"])
    difficulty_stats = {
        k: {"count": len(v), "avg_score": round(sum(v) / len(v), 4)}
        for k, v in sorted(by_difficulty.items())
    }

    summary = {
        "source_file": result_path.name,
        "agent": data.get("agent", {}),
        "benchmark": data.get("benchmark", "BreakingWeb"),
        "version": data.get("version", ""),
        "timestamp": data.get("timestamp", ""),
        "aggregate": {
            "total_tasks": n,
            "success_count": success_count,
            "success_rate": round(success_count / n, 4) if n else 0,
            "avg_score": round(avg_score, 4),
        },
        "by_difficulty": difficulty_stats,
        "tasks": task_summaries,
    }

    summary_path = RESULTS_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    print(f"\nProcessed {n} results from {result_path.name}")
    print(f"  Avg score: {avg_score:.4f}  Success: {success_count}/{n}")
    print(f"  Summary  -> {summary_path}")
    print(f"  Trajectories -> {TRAJECTORIES_DIR}/")
    build_negative_checks(RESULTS_DIR)


if __name__ == "__main__":
    main()
