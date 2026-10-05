#!/usr/bin/env python3
"""Clean-solve-gated degradation report for BreakingWeb sweeps.

Joins clean ↔ intervention runs by ``task_id`` across one or more model
``summary.json`` files, then reports per-primitive / per-layer / per-env
intervention pass rates **only** on variants whose base task was clean-solved
(by all models, by default). Prints side-by-side ungated columns so the
reader can see how much the gate moved each metric.

The motivation is that primitive deltas computed over the full sweep mix two
signals: how well a model handles the *base* task, and how robust it is to
*degradation*. With ~25-30%% of base tasks failing clean for one or more
models, ungated rollups conflate base-task difficulty with primitive
robustness, masking the actual degradation effect we're trying to measure.

Usage::

    python scripts/degradation_report.py opus.json sonnet.json
    python scripts/degradation_report.py --per-model-gate opus.json sonnet.json
    python scripts/degradation_report.py --variants-dir custom/path opus.json
    python scripts/degradation_report.py --emit-cross-table opus.json sonnet.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VARIANTS_DIR = REPO_ROOT / "breakingweb" / "injector" / "variants"


@dataclass(frozen=True)
class RunRow:
    """One row from a model's ``summary.json`` results array."""
    task_id: str
    cond: str  # "clean" or "intervention"
    variant_filename: str | None
    success: bool
    score: float
    env: str | None


@dataclass
class VariantMeta:
    """Decoded YAML metadata for an injector variant."""
    variant_id: str
    base_task_id: str
    target_primitive: str
    layers: tuple[str, ...]
    env: str | None  # not in YAML; derived from filename prefix


def _load_summary(path: Path) -> tuple[str, list[RunRow]]:
    """Parse a ``summary.json`` into a model name and a flat list of run rows."""
    data = json.loads(path.read_text())
    model = data.get("model") or path.stem
    rows: list[RunRow] = []
    for r in data.get("results", []):
        evaluation = r.get("evaluation") or {}
        pick = r.get("pick_metadata") or {}
        rows.append(RunRow(
            task_id=r["task_id"],
            cond=pick.get("cond") or ("clean" if not r.get("variant_filename") else "intervention"),
            variant_filename=r.get("variant_filename"),
            success=bool(evaluation.get("success", False)),
            score=float(evaluation.get("score", 0.0) or 0.0),
            env=pick.get("env"),
        ))
    return model, rows


def _load_variants(variants_dir: Path) -> dict[str, VariantMeta]:
    """Parse every variant YAML once, keyed by filename (with .yaml)."""
    variants: dict[str, VariantMeta] = {}
    for yaml_path in sorted(variants_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(yaml_path.read_text()) or {}
        except yaml.YAMLError as exc:
            print(f"warning: failed to parse {yaml_path.name}: {exc}", file=sys.stderr)
            continue
        layers = tuple(sorted({inj.get("layer", "?") for inj in doc.get("injections", []) or []}))
        # Filename convention: <env>_<task>__<variant>.yaml — env is the chunk
        # before the first underscore. Falls back to None for files that don't
        # match the convention.
        stem = yaml_path.stem
        env = stem.split("_", 1)[0] if "_" in stem else None
        variants[yaml_path.name] = VariantMeta(
            variant_id=doc.get("variant_id") or stem,
            base_task_id=doc.get("base_task_id") or "",
            target_primitive=doc.get("target_primitive") or "?",
            layers=layers,
            env=env,
        )
    return variants


def _split_clean_intervention(rows: Iterable[RunRow]) -> tuple[dict[str, RunRow], list[RunRow]]:
    """Partition one model's rows into ``{task_id: clean_row}`` and a list of intervention rows."""
    clean: dict[str, RunRow] = {}
    intervention: list[RunRow] = []
    for row in rows:
        if row.cond == "clean":
            # Last-write-wins on duplicates; sweeps shouldn't produce duplicate
            # clean runs per task_id, but if they do we keep the latest.
            clean[row.task_id] = row
        else:
            intervention.append(row)
    return clean, intervention


def _gated_task_ids(
    per_model_clean: dict[str, dict[str, RunRow]],
    *,
    per_model_gate: bool,
    model_name: str | None = None,
) -> set[str]:
    """Return base task_ids that pass the gate.

    With ``per_model_gate=False`` (default), a task_id is gated in only if
    EVERY model's clean run on it succeeded. With ``per_model_gate=True``,
    each model is reported against its own clean-solved set; in that mode the
    caller passes ``model_name`` to scope the result.
    """
    if per_model_gate:
        if model_name is None:
            raise ValueError("per_model_gate=True requires model_name")
        return {tid for tid, row in per_model_clean[model_name].items() if row.success}
    # All-models gate — intersect successful clean task_ids across every model.
    if not per_model_clean:
        return set()
    sets = [
        {tid for tid, row in clean_map.items() if row.success}
        for clean_map in per_model_clean.values()
    ]
    return set.intersection(*sets)


def _pct(num: int, denom: int) -> str:
    if denom == 0:
        return "  n/a"
    return f"{100.0 * num / denom:5.1f}%"


def _delta_pct(gated: int, gated_n: int, ungated: int, ungated_n: int) -> str:
    if gated_n == 0 or ungated_n == 0:
        return ""
    g = 100.0 * gated / gated_n
    u = 100.0 * ungated / ungated_n
    diff = g - u
    sign = "+" if diff >= 0 else ""
    return f"({sign}{diff:.1f}pp)"


def _rollup(
    intervention_rows: dict[str, list[RunRow]],
    variants: dict[str, VariantMeta],
    gated_task_ids_per_model: dict[str, set[str]],
    *,
    bucket_fn,
) -> dict[str, dict[str, dict[str, int]]]:
    """Group intervention pass/fail counts by an arbitrary bucket key.

    Returns ``{bucket: {model: {gated_pass, gated_n, ungated_pass, ungated_n}}}``.
    Variants whose YAML couldn't be loaded fall into the bucket ``"?"``.
    """
    out: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: dict(gated_pass=0, gated_n=0, ungated_pass=0, ungated_n=0))
    )
    for model, rows in intervention_rows.items():
        gated = gated_task_ids_per_model[model]
        for row in rows:
            meta = variants.get(row.variant_filename or "")
            buckets = bucket_fn(row, meta)
            for bucket in buckets:
                cell = out[bucket][model]
                cell["ungated_n"] += 1
                cell["ungated_pass"] += int(row.success)
                if row.task_id in gated:
                    cell["gated_n"] += 1
                    cell["gated_pass"] += int(row.success)
    return out


def _print_table(
    title: str,
    rollup: dict[str, dict[str, dict[str, int]]],
    models: Sequence[str],
    *,
    sort_by: str = "name",
) -> None:
    print()
    print(title)
    print("-" * len(title))
    if not rollup:
        print("  (no rows)")
        return

    keys = list(rollup.keys())
    if sort_by == "n":
        keys.sort(key=lambda k: -sum(rollup[k][m]["gated_n"] for m in models))
    else:
        keys.sort()

    name_w = max(10, max(len(k) for k in keys))
    short = [_short_model(m) for m in models]
    col_w = max(20, max(len(s) for s in short))
    header = f"  {'bucket':<{name_w}}  {'gated_n':>8}"
    for s in short:
        header += f"  {s:>{col_w}}"
    print(header)

    for k in keys:
        cells = [rollup[k][m] for m in models]
        gated_n = cells[0]["gated_n"] if cells else 0
        line = f"  {k:<{name_w}}  {gated_n:>8}"
        for cell in cells:
            pct = _pct(cell["gated_pass"], cell["gated_n"])
            delta = _delta_pct(cell["gated_pass"], cell["gated_n"],
                               cell["ungated_pass"], cell["ungated_n"])
            line += f"  {pct} {delta:>{col_w - 6}}"
        print(line)


def _short_model(model: str) -> str:
    """Strip provider prefix and truncate for table headers."""
    name = model.rsplit("/", 1)[-1]
    return name[:24]


def _break_table(
    intervention_rows: dict[str, list[RunRow]],
    variants: dict[str, VariantMeta],
    gated_task_ids_per_model: dict[str, set[str]],
    *,
    bucket_fn,
) -> dict[str, dict[str, int]]:
    """Compute per-bucket cross-model break rates.

    A "break" for a (model, variant) is intervention failure when the base
    task was in that model's clean-solved set. We then aggregate per variant:
      - any_break: at least one model broke
      - all_break: every model broke
    Variants where any model didn't have the base task gated-in are skipped
    (they're not apples-to-apples).
    """
    # Index intervention rows by variant_filename.
    by_var: dict[str, dict[str, RunRow]] = defaultdict(dict)
    for model, rows in intervention_rows.items():
        for row in rows:
            if row.variant_filename:
                by_var[row.variant_filename][model] = row

    models = list(intervention_rows.keys())
    out: dict[str, dict[str, int]] = defaultdict(
        lambda: dict(n=0, any_break=0, all_break=0)
    )
    for variant_filename, model_rows in by_var.items():
        if set(model_rows.keys()) != set(models):
            continue  # not all models ran this variant
        # Apples-to-apples requires all models clean-solved this base task.
        sample_row = next(iter(model_rows.values()))
        if not all(sample_row.task_id in gated_task_ids_per_model[m] for m in models):
            continue
        meta = variants.get(variant_filename)
        breaks = [not r.success for r in model_rows.values()]
        for bucket in bucket_fn(sample_row, meta):
            out[bucket]["n"] += 1
            if any(breaks):
                out[bucket]["any_break"] += 1
            if all(breaks):
                out[bucket]["all_break"] += 1
    return out


def _print_break_table(title: str, table: dict[str, dict[str, int]]) -> None:
    print()
    print(title)
    print("-" * len(title))
    if not table:
        print("  (no rows — gate excluded all variants)")
        return
    keys = sorted(table.keys(), key=lambda k: -table[k]["n"])
    name_w = max(10, max(len(k) for k in keys))
    print(f"  {'bucket':<{name_w}}  {'n':>5}  {'any_break':>11}  {'all_break':>11}")
    for k in keys:
        cell = table[k]
        any_pct = _pct(cell["any_break"], cell["n"])
        all_pct = _pct(cell["all_break"], cell["n"])
        print(f"  {k:<{name_w}}  {cell['n']:>5}  {any_pct:>11}  {all_pct:>11}")


# ── Bucket functions ──────────────────────────────────────────────────────

def _bucket_primitive(row: RunRow, meta: VariantMeta | None) -> tuple[str, ...]:
    return (meta.target_primitive,) if meta else ("?",)


def _bucket_layer(row: RunRow, meta: VariantMeta | None) -> tuple[str, ...]:
    if not meta or not meta.layers:
        return ("?",)
    return meta.layers


def _bucket_env(row: RunRow, meta: VariantMeta | None) -> tuple[str, ...]:
    return (row.env or (meta.env if meta else None) or "?",)


def _bucket_primitive_x_layer(row: RunRow, meta: VariantMeta | None) -> tuple[str, ...]:
    if not meta:
        return ("?",)
    primitive = meta.target_primitive
    layers = meta.layers or ("?",)
    return tuple(f"{primitive} × {layer}" for layer in layers)


# ── Main ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("summaries", nargs="+", type=Path,
                        help="One or more model summary.json files.")
    parser.add_argument("--variants-dir", type=Path, default=DEFAULT_VARIANTS_DIR,
                        help=f"Variant YAML directory (default: {DEFAULT_VARIANTS_DIR}).")
    parser.add_argument("--per-model-gate", action="store_true",
                        help="Gate each model by its own clean-solved set rather than the "
                             "intersection across all models. Loses cross-model apples-to-apples "
                             "comparison but answers 'given this model could solve baseline, "
                             "how often did degradation break it?'.")
    parser.add_argument("--emit-cross-table", action="store_true",
                        help="Also emit the (primitive × layer) cross-table. Sparse but useful "
                             "for spotting variant types that do or don't discriminate.")
    parser.add_argument("--list-excluded", action="store_true",
                        help="List the base task_ids excluded by the gate.")
    args = parser.parse_args(argv)

    if not args.variants_dir.is_dir():
        parser.error(f"variants dir not found: {args.variants_dir}")

    variants = _load_variants(args.variants_dir)
    print(f"loaded {len(variants)} variant YAMLs from {args.variants_dir}", file=sys.stderr)

    per_model_clean: dict[str, dict[str, RunRow]] = {}
    per_model_intervention: dict[str, list[RunRow]] = {}
    model_order: list[str] = []
    for path in args.summaries:
        if not path.is_file():
            parser.error(f"summary not found: {path}")
        model, rows = _load_summary(path)
        if model in per_model_clean:
            print(f"warning: duplicate model name '{model}' from {path} — skipping", file=sys.stderr)
            continue
        clean_map, inter_rows = _split_clean_intervention(rows)
        per_model_clean[model] = clean_map
        per_model_intervention[model] = inter_rows
        model_order.append(model)

    if not model_order:
        parser.error("no models loaded")

    # Gate computation -----------------------------------------------------
    gate_mode = "per-model" if args.per_model_gate else "all-models"
    gated_per_model = {
        m: _gated_task_ids(per_model_clean, per_model_gate=args.per_model_gate, model_name=m)
        for m in model_order
    }
    union_clean_task_ids = set().union(*[set(c.keys()) for c in per_model_clean.values()])

    # ── Header ────────────────────────────────────────────────────────────
    print("=" * 72)
    print("DEGRADATION REPORT — clean-solve gated")
    print("=" * 72)
    print(f"Models:         {', '.join(model_order)}")
    print(f"Gate mode:      {gate_mode}")
    print(f"Variants index: {args.variants_dir}")
    print(f"Base task ids:  {len(union_clean_task_ids)}")
    print()

    # ── Clean pass rates ──────────────────────────────────────────────────
    print("Clean pass rates (ungated)")
    print("--------------------------")
    for m in model_order:
        clean = per_model_clean[m]
        passed = sum(1 for r in clean.values() if r.success)
        print(f"  {m:<24}  {_pct(passed, len(clean))}  ({passed}/{len(clean)})")

    # ── Gate stats ────────────────────────────────────────────────────────
    print()
    print("Gate")
    print("----")
    if args.per_model_gate:
        for m in model_order:
            print(f"  {m:<24}  gated task ids: {len(gated_per_model[m])}")
    else:
        common = gated_per_model[model_order[0]]
        excluded_ids = sorted(union_clean_task_ids - common)
        print(f"  All-models clean-pass:  {len(common)} task ids "
              f"({_pct(len(common), len(union_clean_task_ids))})")
        print(f"  Excluded:               {len(excluded_ids)} task ids")

    # ── Intervention top-line ─────────────────────────────────────────────
    print()
    print("Intervention pass rates")
    print("-----------------------")
    for m in model_order:
        inter = per_model_intervention[m]
        gate = gated_per_model[m]
        ungated_pass = sum(1 for r in inter if r.success)
        gated_rows = [r for r in inter if r.task_id in gate]
        gated_pass = sum(1 for r in gated_rows if r.success)
        print(f"  {m:<24}  ungated {_pct(ungated_pass, len(inter))} ({ungated_pass}/{len(inter)})  "
              f"|  gated {_pct(gated_pass, len(gated_rows))} ({gated_pass}/{len(gated_rows)})  "
              f"{_delta_pct(gated_pass, len(gated_rows), ungated_pass, len(inter))}")

    # ── Roll-ups ──────────────────────────────────────────────────────────
    primitive_pass = _rollup(per_model_intervention, variants, gated_per_model,
                             bucket_fn=_bucket_primitive)
    layer_pass = _rollup(per_model_intervention, variants, gated_per_model,
                         bucket_fn=_bucket_layer)
    env_pass = _rollup(per_model_intervention, variants, gated_per_model,
                       bucket_fn=_bucket_env)

    primitive_breaks = _break_table(per_model_intervention, variants, gated_per_model,
                                    bucket_fn=_bucket_primitive)
    layer_breaks = _break_table(per_model_intervention, variants, gated_per_model,
                                bucket_fn=_bucket_layer)
    env_breaks = _break_table(per_model_intervention, variants, gated_per_model,
                              bucket_fn=_bucket_env)

    _print_table("Per primitive — pass rate (gated, with delta vs ungated)",
                 primitive_pass, model_order, sort_by="n")
    _print_break_table("Per primitive — break rate (cross-model, gated only)",
                       primitive_breaks)

    _print_table("Per layer — pass rate (gated, with delta vs ungated)",
                 layer_pass, model_order, sort_by="n")
    print("  note: variants with multi-layer injections count once per layer,")
    print("        so per-layer counts can exceed the total gated variant count.")
    _print_break_table("Per layer — break rate (cross-model, gated only)", layer_breaks)

    _print_table("Per environment — pass rate (gated, with delta vs ungated)",
                 env_pass, model_order, sort_by="n")
    _print_break_table("Per environment — break rate (cross-model, gated only)", env_breaks)

    if args.emit_cross_table:
        cross_pass = _rollup(per_model_intervention, variants, gated_per_model,
                             bucket_fn=_bucket_primitive_x_layer)
        cross_breaks = _break_table(per_model_intervention, variants, gated_per_model,
                                    bucket_fn=_bucket_primitive_x_layer)
        _print_table("Per primitive × layer — pass rate (gated)", cross_pass,
                     model_order, sort_by="n")
        _print_break_table("Per primitive × layer — break rate (cross-model, gated)",
                           cross_breaks)

    if args.list_excluded and not args.per_model_gate:
        common = gated_per_model[model_order[0]]
        excluded_ids = sorted(union_clean_task_ids - common)
        print()
        print(f"Excluded base task ids ({len(excluded_ids)}) — failed clean by 1+ models")
        print("-" * 72)
        for tid in excluded_ids:
            failers = [m for m in model_order
                       if not (tid in per_model_clean[m] and per_model_clean[m][tid].success)]
            print(f"  {tid}  [{', '.join(failers)}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
