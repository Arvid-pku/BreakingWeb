"""Generate a `picks` JSON array of BreakingWeb runs.

Each pick is a ``{"task_id", "variant_filename", "env", "diff", "cond"}`` entry
consumed by ``scripts/run_picks.py`` to drive a batch evaluation run.

Subsets
-------
  all        — **agent benchmark default**. Enumerate every task under
               ``breakingweb/tasks/<env>/*.yaml`` (519 base tasks) and every
               intervention variant under ``breakingweb/injector/variants/
               *.yaml`` (~530). Produces 519 clean + 530 intervention picks.
  primary    — 140 base-task subset used by the *human* annotator panel.
               Not the agent sweep; here only to reproduce the human-panel
               slice.
  duplicate  — 35 base-task cross-annotator reliability subset (humans only).
  both       — primary ∪ duplicate (humans only).

Filters (apply to any subset):
  --env ENV ...      only keep these environments
  --diff DIFF ...    only keep these difficulty tiers
  --cond {clean,intervention,both}   only keep this condition (default: both)

Sources of truth:
  --subset all:        breakingweb/tasks/<env>/*.yaml + injector/variants/*.yaml
  --subset primary/duplicate/both: breakingweb/human/assignments_v1.yaml
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSIGNMENTS = REPO_ROOT / "breakingweb" / "human" / "assignments_v1.yaml"
TASKS_DIR = REPO_ROOT / "breakingweb" / "tasks"
VARIANTS_DIR = REPO_ROOT / "breakingweb" / "injector" / "variants"


def _parse_flow_rows(section_text: str) -> list[dict]:
    """Parse the flow-style YAML rows the assignments file uses for entries.

    Each entry is one line like ``- {aid: "...", role: primary, ..., base: X, ...}``.
    We pull out the fields we care about with targeted regex rather than a full
    YAML parser, because the flow-style one-liners are narrow and the shape is
    stable.
    """
    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("- {"):
            continue
        base = re.search(r"\bbase:\s*([A-Za-z0-9_]+)", line)
        env = re.search(r"\benv:\s*([A-Za-z0-9_]+)", line)
        diff = re.search(r"\bdiff:\s*([a-z]+)", line)
        cond = re.search(r"\bcond:\s*([a-z]+)", line)
        variant_yaml = re.search(r"\bvariant:\s*\{[^}]*yaml:\s*([^\s,}]+)", line)
        if not (base and env and cond):
            continue
        rows.append({
            "base": base.group(1),
            "env": env.group(1),
            "diff": diff.group(1) if diff else None,
            "cond": cond.group(1),
            "variant_yaml": variant_yaml.group(1) if variant_yaml else None,
        })
    return rows


def load_rows(assignments_path: Path) -> tuple[list[dict], list[dict]]:
    src = assignments_path.read_text()
    prim_head = src.index("condition_assignments:")
    dup_head = src.index("duplicate_condition_assignments:")
    primary = _parse_flow_rows(src[prim_head:dup_head])
    duplicate = _parse_flow_rows(src[dup_head:])
    return primary, duplicate


def build_base_variant_map(primary: list[dict], duplicate: list[dict]) -> dict[str, str]:
    """Map base_task_id → variant YAML filename (for intervention condition)."""
    m: dict[str, str] = {}
    for row in primary + duplicate:
        if row["cond"] == "intervention" and row["variant_yaml"]:
            m.setdefault(row["base"], Path(row["variant_yaml"]).name)
    return m


def rows_to_picks(
    rows: list[dict],
    *,
    base_to_variant: dict[str, str],
    cond_filter: str,
    expand_both_conditions: bool,
) -> list[dict]:
    """Convert YAML rows into pick entries.

    If ``expand_both_conditions`` is True, every unique base task expands into
    (clean, intervention) regardless of the row's own cond field — this is
    the "35 base × 2" interpretation of duplicate_subset.

    If False, each row becomes exactly one pick matching its own cond.
    """
    picks: list[dict] = []
    if expand_both_conditions:
        seen = set()
        for row in rows:
            b = row["base"]
            if b in seen:
                continue
            seen.add(b)
            if cond_filter in ("clean", "both"):
                picks.append({
                    "task_id": b,
                    "variant_filename": None,
                    "env": row["env"],
                    "diff": row["diff"],
                    "cond": "clean",
                })
            if cond_filter in ("intervention", "both"):
                picks.append({
                    "task_id": b,
                    "variant_filename": base_to_variant.get(b),
                    "env": row["env"],
                    "diff": row["diff"],
                    "cond": "intervention",
                })
    else:
        for row in rows:
            if cond_filter != "both" and row["cond"] != cond_filter:
                continue
            picks.append({
                "task_id": row["base"],
                "variant_filename": Path(row["variant_yaml"]).name if row["variant_yaml"] else None,
                "env": row["env"],
                "diff": row["diff"],
                "cond": row["cond"],
            })
    return picks


def _read_yaml_field(yaml_path: Path, field: str) -> str | None:
    """Read a single top-level scalar field out of a YAML file.

    Avoids requiring PyYAML: task/variant YAMLs are authored so the target
    fields appear on their own line as ``field: value``. Good enough for
    the fields we need (``difficulty``, ``base_task_id``).
    """
    try:
        for line in yaml_path.read_text().splitlines():
            m = re.match(rf"^{re.escape(field)}:\s*(\S.*?)\s*$", line)
            if m:
                return m.group(1)
    except Exception:
        return None
    return None


def _enumerate_tasks_and_variants() -> list[dict]:
    """Enumerate every base task + every intervention variant in the repo.

    Returns a list of pick dicts with clean picks first, then intervention.

    For each ``breakingweb/tasks/<env>/<task_id>.yaml`` emit one clean pick.
    For each ``breakingweb/injector/variants/<variant>.yaml`` read its
    ``base_task_id`` field; look up the base task's env + difficulty and emit
    an intervention pick. Variants whose ``base_task_id`` has no matching
    base task YAML are skipped with a warning.
    """
    # Pass 1: base tasks. Build (env, diff) lookup by task_id.
    clean_picks: list[dict] = []
    base_index: dict[str, dict] = {}
    for task_yaml in sorted(TASKS_DIR.glob("*/*.yaml")):
        task_id = task_yaml.stem
        env = task_yaml.parent.name
        diff = _read_yaml_field(task_yaml, "difficulty")
        base_index[task_id] = {"env": env, "diff": diff}
        clean_picks.append({
            "task_id": task_id,
            "variant_filename": None,
            "env": env,
            "diff": diff,
            "cond": "clean",
        })

    # Pass 2: intervention variants. Emit one pick per variant YAML.
    intervention_picks: list[dict] = []
    unmatched: list[str] = []
    for variant_yaml in sorted(VARIANTS_DIR.glob("*.yaml")):
        base_id = _read_yaml_field(variant_yaml, "base_task_id")
        if not base_id:
            unmatched.append(f"{variant_yaml.name} (missing base_task_id)")
            continue
        base = base_index.get(base_id)
        if base is None:
            unmatched.append(f"{variant_yaml.name} (no base task for {base_id!r})")
            continue
        intervention_picks.append({
            "task_id": base_id,
            "variant_filename": variant_yaml.name,
            "env": base["env"],
            "diff": base["diff"],
            "cond": "intervention",
        })

    if unmatched:
        import sys
        print(f"[gen_picks] skipped {len(unmatched)} variant(s):", file=sys.stderr)
        for line in unmatched[:5]:
            print(f"  {line}", file=sys.stderr)
        if len(unmatched) > 5:
            print(f"  ... and {len(unmatched) - 5} more", file=sys.stderr)

    return clean_picks + intervention_picks


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--subset",
        choices=["all", "primary", "duplicate", "both"],
        required=True,
        help="all = full agent benchmark (519 clean + ~530 intervention ≈ 1049). "
             "primary/duplicate/both = human-annotator subsets, not the agent sweep.",
    )
    p.add_argument(
        "--cond",
        choices=["clean", "intervention", "both"],
        default="both",
        help="condition filter (default both)",
    )
    p.add_argument("--env", nargs="*", help="environment filter (amazon booking gmail ...)")
    p.add_argument(
        "--diff",
        nargs="*",
        choices=["easy", "medium", "hard", "expert", "frontier"],
        help="difficulty tier filter",
    )
    p.add_argument(
        "--assignments",
        type=Path,
        default=ASSIGNMENTS,
        help=f"path to assignments YAML (default {ASSIGNMENTS})",
    )
    p.add_argument("--output", "-o", type=Path, required=True, help="write picks JSON here")
    args = p.parse_args()

    if args.subset == "all":
        picks = _enumerate_tasks_and_variants()
        if args.cond == "clean":
            picks = [p for p in picks if p["cond"] == "clean"]
        elif args.cond == "intervention":
            picks = [p for p in picks if p["cond"] == "intervention"]
        # else (both) keep everything
        if args.env:
            picks = [p for p in picks if p["env"] in set(args.env)]
        if args.diff:
            picks = [p for p in picks if p["diff"] in set(args.diff)]
        _write_and_summarize(picks, args.output)
        return

    primary, duplicate = load_rows(args.assignments)
    base_to_variant = build_base_variant_map(primary, duplicate)

    if args.subset == "primary":
        picks = rows_to_picks(
            primary,
            base_to_variant=base_to_variant,
            cond_filter=args.cond,
            expand_both_conditions=False,
        )
    elif args.subset == "duplicate":
        picks = rows_to_picks(
            duplicate,
            base_to_variant=base_to_variant,
            cond_filter=args.cond,
            expand_both_conditions=True,
        )
    else:
        a = rows_to_picks(
            primary,
            base_to_variant=base_to_variant,
            cond_filter=args.cond,
            expand_both_conditions=False,
        )
        b = rows_to_picks(
            duplicate,
            base_to_variant=base_to_variant,
            cond_filter=args.cond,
            expand_both_conditions=True,
        )
        seen = set()
        picks = []
        for pk in a + b:
            key = (pk["task_id"], pk["variant_filename"])
            if key in seen:
                continue
            seen.add(key)
            picks.append(pk)

    if args.env:
        picks = [p for p in picks if p["env"] in set(args.env)]
    if args.diff:
        picks = [p for p in picks if p["diff"] in set(args.diff)]

    _write_and_summarize(picks, args.output)


def _write_and_summarize(picks: list[dict], output: Path) -> None:
    from collections import Counter

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(picks, indent=2))

    by_env = Counter(p["env"] for p in picks)
    by_diff = Counter(p["diff"] for p in picks)
    by_cond = Counter(p["cond"] for p in picks)
    print(f"wrote {len(picks)} picks → {output}")
    print(f"  by env:  {dict(by_env)}")
    print(f"  by diff: {dict(by_diff)}")
    print(f"  by cond: {dict(by_cond)}")


if __name__ == "__main__":
    main()
