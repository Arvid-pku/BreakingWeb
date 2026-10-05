"""Compute per-primitive Δ scores between standard and degraded evaluation runs.

Usage:
    python -m breakingweb.scripts.compute_delta \
        --standard results/standard.json \
        --degraded results/degraded_patience.json results/degraded_grounding.json \
        --output results/delta_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _extract_score(result: dict) -> float:
    ev = result.get("evaluation", {})
    return float(ev.get("score", ev.get("final_score", 0.0)))


def _extract_time(result: dict) -> float:
    return float(result.get("agent", {}).get("elapsed_seconds", 0))


def _extract_steps(result: dict) -> int:
    return int(result.get("agent", {}).get("steps", 0))


def compute_delta(
    standard_path: str | Path,
    degraded_paths: list[str | Path],
) -> dict[str, Any]:
    """Compare standard vs degraded runs and compute per-primitive Δ scores.

    Returns a report dict with per-primitive deltas and per-task breakdowns.
    """
    with open(standard_path) as f:
        standard_data = json.load(f)

    standard_scores: dict[str, float] = {}
    standard_times: dict[str, float] = {}
    standard_steps: dict[str, int] = {}
    for r in standard_data.get("results", []):
        tid = r.get("task_id") or r.get("page_id")
        if tid:
            standard_scores[tid] = _extract_score(r)
            standard_times[tid] = _extract_time(r)
            standard_steps[tid] = _extract_steps(r)

    primitives: dict[str, dict[str, Any]] = {}

    for deg_path in degraded_paths:
        with open(deg_path) as f:
            deg_data = json.load(f)

        for r in deg_data.get("results", []):
            tid = r.get("task_id") or r.get("page_id")
            if not tid:
                continue

            deg_info = r.get("degradation", {})
            primitive = deg_info.get("target_primitive", "unknown")
            variant_id = deg_info.get("variant_id", "")

            if primitive not in primitives:
                primitives[primitive] = {
                    "variant_id": variant_id,
                    "tasks": [],
                    "standard_scores": [],
                    "degraded_scores": [],
                }

            deg_score = _extract_score(r)
            deg_time = _extract_time(r)
            deg_steps = _extract_steps(r)
            std_score = standard_scores.get(tid)
            if std_score is None:
                continue
            std_time = standard_times.get(tid, 0)
            std_steps = standard_steps.get(tid, 0)
            time_ratio = round(deg_time / std_time, 2) if std_time > 0 else None

            primitives[primitive]["tasks"].append({
                "task_id": tid,
                "standard_score": std_score,
                "degraded_score": deg_score,
                "delta": std_score - deg_score,
                "standard_time": std_time,
                "degraded_time": deg_time,
                "time_ratio": time_ratio,
                "standard_steps": std_steps,
                "degraded_steps": deg_steps,
            })
            primitives[primitive]["standard_scores"].append(std_score)
            primitives[primitive]["degraded_scores"].append(deg_score)

    # Aggregate
    summary = {}
    for prim, data in sorted(primitives.items()):
        std_avg = sum(data["standard_scores"]) / len(data["standard_scores"]) if data["standard_scores"] else 0
        deg_avg = sum(data["degraded_scores"]) / len(data["degraded_scores"]) if data["degraded_scores"] else 0
        delta = std_avg - deg_avg
        data["avg_standard"] = round(std_avg, 4)
        data["avg_degraded"] = round(deg_avg, 4)
        data["delta"] = round(delta, 4)
        data["n_tasks"] = len(data["tasks"])
        # Clean up internal lists
        del data["standard_scores"]
        del data["degraded_scores"]
        summary[prim] = round(delta, 4)

    return {
        "standard_file": str(standard_path),
        "degraded_files": [str(p) for p in degraded_paths],
        "primitives": primitives,
        "summary": summary,
    }


def print_report(report: dict) -> None:
    """Print a formatted console report."""
    print(f"\n{'=' * 70}")
    print("BreakingWeb Δ-Primitive Diagnostic Report")
    print(f"{'=' * 70}")
    print(f"Standard: {report['standard_file']}")
    print(f"Degraded: {', '.join(report['degraded_files'])}")
    print()

    print(f"{'Primitive':<16s} {'Score Δ':>8s} {'Std':>7s} {'Deg':>7s} {'Time Ratio':>11s} {'Signal':>8s}")
    print(f"{'-' * 16} {'-' * 8} {'-' * 7} {'-' * 7} {'-' * 11} {'-' * 8}")

    for prim, data in sorted(report["primitives"].items()):
        delta = data["delta"]
        # Compute average time ratio
        time_ratios = [t["time_ratio"] for t in data["tasks"] if t.get("time_ratio")]
        avg_time_ratio = sum(time_ratios) / len(time_ratios) if time_ratios else None
        tr_str = f"{avg_time_ratio:.1f}x" if avg_time_ratio else "n/a"

        if delta > 0.1:
            signal = "WEAK"
        elif avg_time_ratio and avg_time_ratio > 1.3:
            signal = "ADAPT"
        else:
            signal = "-"
        print(
            f"{prim:<16s} {delta:>+8.3f} {data['avg_standard']:>7.2f} "
            f"{data['avg_degraded']:>7.2f} {tr_str:>11s} {signal:>8s}"
        )

    print()
    print("Signal:  WEAK = score dropped (agent lacks primitive)")
    print("         ADAPT = score held but time increased (agent has primitive, adapted)")
    print("         -    = no effect detected")

    # Per-task detail
    for prim, data in sorted(report["primitives"].items()):
        if data["tasks"]:
            print(f"\n  {prim}:")
            for t in data["tasks"]:
                tr = f"{t['time_ratio']:.1f}x" if t.get("time_ratio") else "n/a"
                print(
                    f"    {t['task_id']:<40s} "
                    f"score: {t['standard_score']:+.2f}→{t['degraded_score']:+.2f} "
                    f"Δ={t['delta']:+.2f}  "
                    f"time: {t['standard_time']:.0f}s→{t['degraded_time']:.0f}s ({tr})"
                )


def main():
    parser = argparse.ArgumentParser(
        description="Compute per-primitive Δ scores between standard and degraded runs"
    )
    parser.add_argument("--standard", required=True, help="Path to standard results JSON")
    parser.add_argument("--degraded", nargs="+", required=True, help="Path(s) to degraded results JSON")
    parser.add_argument("--output", default=None, help="Write JSON report to this path")
    args = parser.parse_args()

    report = compute_delta(args.standard, args.degraded)
    print_report(report)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
