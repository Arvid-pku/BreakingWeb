#!/usr/bin/env python3
"""Generate demo-site data from browser-use sweep worker files.

Reads 8 worker JSON files (w0..w7), merges results (dedup by task_id,
keeping higher score), enriches with task YAML metadata, and writes:
  - summary.json  (aggregate stats + per-task summaries)
  - trajectories/<task_id>.json  (per-task trajectory files)

Usage:
    python scripts/generate_bu_demo_data.py
"""

import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

SWEEP_DIR = REPO_ROOT / "results" / "breakingweb" / "bu_sweep_20260405_012047"
TASK_YAML_DIR = REPO_ROOT / "breakingweb" / "tasks" / "gmail"
DEMO_RESULTS_DIR = (
    REPO_ROOT
    / "breakingweb"
    / "environments"
    / "demo-site"
    / "public"
    / "results"
    / "browser-use"
)
INDEX_PATH = (
    REPO_ROOT
    / "breakingweb"
    / "environments"
    / "demo-site"
    / "public"
    / "results"
    / "index.json"
)

WORKER_COUNT = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_task_metadata() -> dict[str, dict]:
    """Load metadata from all task YAML files. Returns {task_id: meta}."""
    metadata = {}
    for yaml_path in sorted(TASK_YAML_DIR.glob("*.yaml")):
        with open(yaml_path) as f:
            task = yaml.safe_load(f)
        tid = task["task_id"]
        metadata[tid] = {
            "title": task.get("title", tid),
            "env_id": task.get("env_id", "gmail"),
            "difficulty": task.get("difficulty", "medium"),
            "primitives": task.get("primary_primitives", []),
            "instruction": task.get("instruction_template", ""),
        }
    return metadata


def load_and_merge_workers() -> tuple[dict, list[dict]]:
    """Load all worker files, merge, dedup by task_id (keep higher score).

    Returns (agent_info, merged_results).
    """
    best: dict[str, dict] = {}
    agent_info = None

    for i in range(WORKER_COUNT):
        path = SWEEP_DIR / f"w{i}.json"
        with open(path) as f:
            data = json.load(f)

        if agent_info is None:
            agent_info = data.get("agent", {})

        for result in data["results"]:
            tid = result["task_id"]
            score = result["evaluation"]["score"]
            if tid not in best or score > best[tid]["evaluation"]["score"]:
                best[tid] = result

    return agent_info, sorted(best.values(), key=lambda r: r["task_id"])


def build_summary(
    agent_info: dict,
    results: list[dict],
    metadata: dict[str, dict],
) -> dict:
    """Build summary.json structure matching the gpt-5.4 format."""
    tasks = []
    by_difficulty: dict[str, list[float]] = defaultdict(list)

    for r in results:
        tid = r["task_id"]
        meta = metadata.get(tid, {})
        score = r["evaluation"]["score"]
        success = r["evaluation"]["success"]
        agent = r.get("agent", {})
        steps = agent.get("steps", len(agent.get("trajectory", [])))
        elapsed = agent.get("elapsed_seconds", 0)
        completed = agent.get("completed", True)
        reasoning = r["evaluation"].get("reasoning", "")

        difficulty = meta.get("difficulty", "medium")
        by_difficulty[difficulty].append(score)

        tasks.append(
            {
                "task_id": tid,
                "title": meta.get("title", tid),
                "env_id": meta.get("env_id", "gmail"),
                "difficulty": difficulty,
                "primitives": meta.get("primitives", []),
                "instruction": meta.get("instruction", ""),
                "score": score,
                "success": success,
                "steps": steps,
                "elapsed_seconds": round(elapsed, 1),
                "completed": completed,
                "reasoning": reasoning,
            }
        )

    total = len(tasks)
    success_count = sum(1 for t in tasks if t["success"])
    scores = [t["score"] for t in tasks]

    diff_breakdown = {}
    for diff, diff_scores in sorted(by_difficulty.items()):
        diff_breakdown[diff] = {
            "count": len(diff_scores),
            "avg_score": round(sum(diff_scores) / len(diff_scores), 4)
            if diff_scores
            else 0,
        }

    return {
        "source_file": "bu_sweep_20260405_012047",
        "agent": {
            "model": agent_info.get("model", "gpt-5.4"),
            "provider": agent_info.get("provider", "openai"),
        },
        "benchmark": "BreakingWeb",
        "version": "3.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aggregate": {
            "total_tasks": total,
            "success_count": success_count,
            "success_rate": round(success_count / total, 2) if total else 0,
            "avg_score": sum(scores) / total if total else 0,
        },
        "by_difficulty": diff_breakdown,
        "tasks": tasks,
    }


def build_trajectory(result: dict, metadata: dict[str, dict]) -> dict:
    """Build a per-task trajectory JSON matching the gpt-5.4 format."""
    tid = result["task_id"]
    meta = metadata.get(tid, {})
    agent = result.get("agent", {})
    trajectory = agent.get("trajectory", [])
    steps_count = agent.get("steps", len(trajectory))
    elapsed = agent.get("elapsed_seconds", 0)
    completed = agent.get("completed", True)

    return {
        "task_id": tid,
        "title": meta.get("title", tid),
        "instruction": meta.get("instruction", ""),
        "difficulty": meta.get("difficulty", "medium"),
        "model": agent.get("model", "gpt-5.4"),
        "total_steps": steps_count,
        "elapsed_seconds": round(elapsed, 1),
        "completed": completed,
        "start_path": "/inbox",
        "evaluation": result["evaluation"],
        "steps": trajectory,
    }


def update_index():
    """Update index.json: set browser-use tasks to 80."""
    with open(INDEX_PATH) as f:
        index = json.load(f)

    for model in index["models"]:
        if model["id"] == "browser-use":
            model["tasks"] = 80
            model["label"] = "GPT-5.4 (browser-use)"
            break
    else:
        # Entry doesn't exist; add it
        index["models"].append(
            {
                "id": "browser-use",
                "label": "GPT-5.4 (browser-use)",
                "provider": "openai",
                "tasks": 80,
            }
        )

    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
    print(f"  Updated {INDEX_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading task metadata from YAML files...")
    metadata = load_task_metadata()
    print(f"  Found {len(metadata)} task definitions")

    print("Loading and merging worker files...")
    agent_info, results = load_and_merge_workers()
    print(f"  Merged {len(results)} unique tasks from {WORKER_COUNT} workers")

    # Wipe old trajectory directory and recreate
    traj_dir = DEMO_RESULTS_DIR / "trajectories"
    if traj_dir.exists():
        shutil.rmtree(traj_dir)
        print(f"  Deleted old trajectories at {traj_dir}")
    traj_dir.mkdir(parents=True, exist_ok=True)

    print("Building summary.json...")
    summary = build_summary(agent_info, results, metadata)
    summary_path = DEMO_RESULTS_DIR / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(f"  Wrote {summary_path}")
    print(
        f"  Aggregate: {summary['aggregate']['total_tasks']} tasks, "
        f"{summary['aggregate']['success_rate']:.0%} success, "
        f"avg_score={summary['aggregate']['avg_score']:.4f}"
    )

    print("Writing trajectory files...")
    for r in results:
        tid = r["task_id"]
        traj = build_trajectory(r, metadata)
        traj_path = traj_dir / f"{tid}.json"
        with open(traj_path, "w") as f:
            json.dump(traj, f, indent=2)
            f.write("\n")
    print(f"  Wrote {len(results)} trajectory files to {traj_dir}")

    print("Updating index.json...")
    update_index()

    print("Done.")


if __name__ == "__main__":
    main()
