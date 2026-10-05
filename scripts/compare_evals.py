#!/usr/bin/env python3
"""Compare BreakingWeb evaluation results with statistical significance testing.

Supports two modes:

1. Single-run comparison (deterministic, temp=0):
   python scripts/compare_evals.py baseline.json trained.json

2. Multi-run comparison (statistical, temp>0):
   python scripts/compare_evals.py baseline_summary.json trained_summary.json

Also supports loading individual run files:
   python scripts/compare_evals.py --runs-a results_run*.json --runs-b trained_run*.json
"""

import argparse
import json
import statistics
import sys
from pathlib import Path


def load_single_result(path: str) -> dict[str, float]:
    """Load a single-run result file → {page_id: score}."""
    with open(path) as f:
        data = json.load(f)
    scores = {}
    for r in data.get("results", []):
        pid = r["page_id"]
        score = r["evaluation"].get("score", r["evaluation"].get("final_score", 0.0))
        scores[pid] = score
    return scores


def load_summary(path: str) -> dict[str, list[float]]:
    """Load a multi-run summary → {page_id: [scores across runs]}."""
    with open(path) as f:
        data = json.load(f)
    if "per_page" in data:
        return {pid: ps["scores"] for pid, ps in data["per_page"].items()}
    # Fall back to single-run format
    scores = load_single_result(path)
    return {pid: [s] for pid, s in scores.items()}


def load_runs(paths: list[str]) -> dict[str, list[float]]:
    """Load multiple individual run files → {page_id: [scores]}."""
    page_scores: dict[str, list[float]] = {}
    for p in paths:
        scores = load_single_result(p)
        for pid, s in scores.items():
            page_scores.setdefault(pid, []).append(s)
    return page_scores


def wilcoxon_signed_rank(x: list[float], y: list[float]) -> tuple[float, float]:
    """Wilcoxon signed-rank test (two-sided). Returns (statistic, p-value).

    Minimal implementation that doesn't require scipy.
    For N <= 25, uses exact distribution table. For N > 25, uses normal approximation.
    """
    diffs = [xi - yi for xi, yi in zip(x, y) if xi != yi]
    n = len(diffs)
    if n == 0:
        return 0.0, 1.0

    # Rank by absolute value
    abs_diffs = [(abs(d), i) for i, d in enumerate(diffs)]
    abs_diffs.sort()

    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs_diffs[j][0] == abs_diffs[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[abs_diffs[k][1]] = avg_rank
        i = j

    # Compute W+ and W-
    w_plus = sum(r for r, d in zip(ranks, diffs) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, diffs) if d < 0)
    w = min(w_plus, w_minus)

    # Normal approximation (valid for n >= 10, usable for n >= 5)
    mean_w = n * (n + 1) / 4
    std_w = (n * (n + 1) * (2 * n + 1) / 24) ** 0.5
    if std_w == 0:
        return w, 1.0
    z = (w - mean_w) / std_w
    # Two-sided p-value from z (using error function approximation)
    p = 2.0 * _norm_cdf(-abs(z))
    return w, p


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    import math
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    t = 1.0 / (1.0 + p * abs(x))
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x / 2)
    return y if x >= 0 else 1.0 - y


def compare_single(scores_a: dict[str, float], scores_b: dict[str, float],
                    name_a: str, name_b: str):
    """Compare two single-run results."""
    common = sorted(set(scores_a) & set(scores_b))
    if not common:
        print("ERROR: No common pages between the two results.", file=sys.stderr)
        sys.exit(1)

    vals_a = [scores_a[p] for p in common]
    vals_b = [scores_b[p] for p in common]

    avg_a = statistics.mean(vals_a)
    avg_b = statistics.mean(vals_b)
    passed_a = sum(1 for s in vals_a if s > 0)
    passed_b = sum(1 for s in vals_b if s > 0)

    print(f"\n{'='*70}")
    print(f"  SINGLE-RUN COMPARISON (deterministic, no statistics)")
    print(f"{'='*70}")
    print(f"  WARNING: Single runs have no error bars.")
    print(f"  Use --num-runs 3 --temperature 0.3 for statistical evaluation.\n")
    print(f"  {'':30s}  {name_a:>12s}  {name_b:>12s}  {'Delta':>8s}")
    print(f"  {'─'*30}  {'─'*12}  {'─'*12}  {'─'*8}")
    print(f"  {'Passed':30s}  {passed_a:>12d}  {passed_b:>12d}  {passed_b - passed_a:>+8d}")
    print(f"  {'Avg score':30s}  {avg_a:>+12.3f}  {avg_b:>+12.3f}  {avg_b - avg_a:>+8.3f}")
    print()
    print(f"  Per-page:")
    for p in common:
        sa, sb = scores_a[p], scores_b[p]
        delta = sb - sa
        marker = ""
        if delta >= 1.0:
            marker = " ++ "
        elif delta > 0:
            marker = " +  "
        elif delta <= -1.0:
            marker = " -- "
        elif delta < 0:
            marker = " -  "
        print(f"    {p:30s}  {sa:>+12.1f}  {sb:>+12.1f}  {delta:>+8.1f}{marker}")

    # Even for single runs, report whether the delta COULD be significant
    # given known variance (~5 pages can flip per run)
    print(f"\n  NOTE: Based on observed Qwen3.5 eval variance (±5 pages per run),")
    print(f"        a delta of {avg_b - avg_a:+.3f} is {'likely noise' if abs(avg_b - avg_a) < 0.3 else 'possibly real but unverified'}.")
    print(f"        Run with --num-runs 3 --temperature 0.3 for statistical evidence.")


def compare_multi(scores_a: dict[str, list[float]], scores_b: dict[str, list[float]],
                   name_a: str, name_b: str):
    """Compare two multi-run result sets with statistical testing."""
    common = sorted(set(scores_a) & set(scores_b))
    if not common:
        print("ERROR: No common pages.", file=sys.stderr)
        sys.exit(1)

    n_a = min(len(v) for v in scores_a.values())
    n_b = min(len(v) for v in scores_b.values())

    # Per-page means
    means_a = [statistics.mean(scores_a[p]) for p in common]
    means_b = [statistics.mean(scores_b[p]) for p in common]

    avg_a = statistics.mean(means_a)
    avg_b = statistics.mean(means_b)
    passed_a = sum(1 for m in means_a if m > 0)
    passed_b = sum(1 for m in means_b if m > 0)

    # Wilcoxon signed-rank test on per-page means
    w_stat, p_value = wilcoxon_signed_rank(means_a, means_b)

    # Effect size: matched-pairs rank-biserial correlation
    n_eff = sum(1 for a, b in zip(means_a, means_b) if a != b)
    if n_eff > 0:
        effect_size = 1 - (2 * w_stat) / (n_eff * (n_eff + 1) / 2)
    else:
        effect_size = 0.0

    print(f"\n{'='*70}")
    print(f"  MULTI-RUN COMPARISON ({n_a} runs × {n_b} runs)")
    print(f"{'='*70}")

    print(f"\n  {'':30s}  {name_a:>12s}  {name_b:>12s}  {'Delta':>8s}")
    print(f"  {'─'*30}  {'─'*12}  {'─'*12}  {'─'*8}")
    print(f"  {'Passed (by mean>0)':30s}  {passed_a:>12d}  {passed_b:>12d}  {passed_b - passed_a:>+8d}")
    print(f"  {'Avg score (mean of means)':30s}  {avg_a:>+12.3f}  {avg_b:>+12.3f}  {avg_b - avg_a:>+8.3f}")

    print(f"\n  Wilcoxon signed-rank test (two-sided, N={len(common)} pages):")
    print(f"    W = {w_stat:.1f},  p = {p_value:.4f},  effect size r = {effect_size:+.3f}")
    if p_value < 0.05:
        direction = "B > A" if avg_b > avg_a else "A > B"
        print(f"    → SIGNIFICANT at α=0.05 ({direction})")
    elif p_value < 0.10:
        print(f"    → Marginal (0.05 < p < 0.10). More runs needed.")
    else:
        print(f"    → NOT significant. Difference is within noise.")

    print(f"\n  Per-page (mean ± std):")
    print(f"    {'Page':30s}  {name_a:>14s}  {name_b:>14s}  {'Delta':>8s}  {'Sig':>4s}")
    print(f"    {'─'*30}  {'─'*14}  {'─'*14}  {'─'*8}  {'─'*4}")

    for p in common:
        sa = scores_a[p]
        sb = scores_b[p]
        ma, mb = statistics.mean(sa), statistics.mean(sb)
        sda = statistics.stdev(sa) if len(sa) > 1 else 0.0
        sdb = statistics.stdev(sb) if len(sb) > 1 else 0.0
        delta = mb - ma

        # Per-page significance (simple: non-overlapping means ± 1 std)
        sig = ""
        if len(sa) > 1 and len(sb) > 1:
            if ma + sda < mb - sdb:
                sig = "++"
            elif mb + sdb < ma - sda:
                sig = "--"
            elif abs(delta) > 0.5:
                sig = "?"

        a_str = f"{ma:+.2f}±{sda:.2f}"
        b_str = f"{mb:+.2f}±{sdb:.2f}"
        print(f"    {p:30s}  {a_str:>14s}  {b_str:>14s}  {delta:>+8.2f}  {sig:>4s}")

    print(f"\n  Legend: ++ = B significantly better, -- = B significantly worse, ? = large but noisy")


def main():
    parser = argparse.ArgumentParser(
        description="Compare BreakingWeb evaluation results with statistical testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("result_a", nargs="?", help="Baseline result (single .json or _summary.json)")
    parser.add_argument("result_b", nargs="?", help="Trained result (single .json or _summary.json)")
    parser.add_argument("--runs-a", nargs="+", help="Multiple run files for model A")
    parser.add_argument("--runs-b", nargs="+", help="Multiple run files for model B")
    parser.add_argument("--name-a", default="Baseline", help="Name for model A")
    parser.add_argument("--name-b", default="Trained", help="Name for model B")

    args = parser.parse_args()

    # Determine mode
    if args.runs_a and args.runs_b:
        scores_a = load_runs(args.runs_a)
        scores_b = load_runs(args.runs_b)
        compare_multi(scores_a, scores_b, args.name_a, args.name_b)
    elif args.result_a and args.result_b:
        # Check if summary files (multi-run) or single-run
        with open(args.result_a) as f:
            data_a = json.load(f)
        with open(args.result_b) as f:
            data_b = json.load(f)

        is_multi_a = "per_page" in data_a
        is_multi_b = "per_page" in data_b

        if is_multi_a and is_multi_b:
            scores_a = {pid: ps["scores"] for pid, ps in data_a["per_page"].items()}
            scores_b = {pid: ps["scores"] for pid, ps in data_b["per_page"].items()}
            compare_multi(scores_a, scores_b, args.name_a, args.name_b)
        elif not is_multi_a and not is_multi_b:
            scores_a = load_single_result(args.result_a)
            scores_b = load_single_result(args.result_b)
            compare_single(scores_a, scores_b, args.name_a, args.name_b)
        else:
            # Mixed: wrap single in list
            if is_multi_a:
                scores_a = {pid: ps["scores"] for pid, ps in data_a["per_page"].items()}
            else:
                s = load_single_result(args.result_a)
                scores_a = {pid: [v] for pid, v in s.items()}
            if is_multi_b:
                scores_b = {pid: ps["scores"] for pid, ps in data_b["per_page"].items()}
            else:
                s = load_single_result(args.result_b)
                scores_b = {pid: [v] for pid, v in s.items()}
            compare_multi(scores_a, scores_b, args.name_a, args.name_b)
    else:
        parser.error("Provide either two result files or --runs-a and --runs-b")


if __name__ == "__main__":
    main()
