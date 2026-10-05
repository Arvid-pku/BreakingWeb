"""Adversarial case generation from canonical_diff blocks.

For each authored predicate, synthesize a mutation that violates it — produces
{description, final} cases that should fail matching. These cases are used by
the adversarial regression test harness (Task 15) to confirm the matcher
actually rejects obviously-wrong trajectories.
"""

from __future__ import annotations

import copy
from typing import Any


_SKIP = object()


def synthesize_adversarial_cases(
    canonical: Any,  # CanonicalDiff
    *,
    initial: Any,
    targets: dict,
) -> list[dict]:
    """Return a list of {description, final} cases that should fail matching.

    If the canonical has a `oneof` block, synthesize against the first
    alternative — it's the simplest behaviour for Phase 0.
    """
    block = canonical.oneof[0] if canonical.oneof else canonical

    cases: list[dict] = []

    # Strategy 1: per-field predicate violation on create entries
    for i, entry in enumerate(block.create):
        for fname, pred in entry.properties.items():
            wrong_value = _negate_predicate(pred)
            if wrong_value is _SKIP:
                continue
            final = copy.deepcopy(initial)
            collection = _collection_name(entry.entity)
            if isinstance(final, dict):
                final.setdefault(collection, [])
                final[collection].append({
                    "id": f"adversarial_{i}_{fname}",
                    fname: wrong_value,
                })
            cases.append({
                "description": f"create[{i}].{fname} with violating value",
                "final": final,
            })

    # Strategy 2: per-invariant violation — mutate first entity in the collection.
    # Skip filtered (e.g. ``filter: "False"``) and comprehensive invariants —
    # those are tolerance-style invariants, not strict preservation. Also
    # skip non-list collections (singletons like ``state.settings``, primitive
    # scalars) — the diff layer surfaces those via ``DIFF_DIFFABLE_*`` opt-ins,
    # but the raw state dict still stores them as singletons/scalars and this
    # generator only knows how to mutate list-shaped collections.
    for i, inv in enumerate(block.invariant):
        if inv.filter or inv.comprehensive:
            continue
        collection = inv.collection.removeprefix("state.")
        final = copy.deepcopy(initial)
        if not isinstance(final, dict):
            continue
        col_value = final.get(collection)
        if not isinstance(col_value, list) or not col_value:
            continue
        entity = col_value[0]
        if isinstance(entity, dict) and entity:
            # Pick a non-id field to mutate; fall back to any field
            mutable_keys = [k for k in entity if k != "id"]
            if mutable_keys:
                k = mutable_keys[0]
                entity[k] = f"MUTATED_{entity[k]}"
                cases.append({
                    "description": f"invariant[{i}] violation on {collection}",
                    "final": final,
                })

    # Strategy 3: bijection unsaturation — drop all entities in the target collection
    for i, entry in enumerate(block.create):
        if entry.bijection is None:
            continue
        collection = _collection_name(entry.entity)
        final = copy.deepcopy(initial)
        if isinstance(final, dict):
            final[collection] = []
        cases.append({
            "description": f"bijection[{i}] unsaturated (no creations)",
            "final": final,
        })

    return cases


def _negate_predicate(pred: dict) -> Any:
    """Return a value that VIOLATES the predicate, or `_SKIP` if infeasible.

    The returned value can be assigned directly to a field and the predicate
    will evaluate False on it.
    """
    if not isinstance(pred, dict) or len(pred) != 1:
        return _SKIP
    key = next(iter(pred))
    arg = pred[key]

    if key == "eq":
        if isinstance(arg, str):
            return arg + "_WRONG"
        if isinstance(arg, bool):
            return not arg
        if isinstance(arg, (int, float)):
            return arg + 1
        return _SKIP
    if key == "in":
        return "__NOT_IN_SET__"
    if key == "between":
        lo, _ = arg
        if isinstance(lo, (int, float)):
            return lo - 1
        return _SKIP
    if key == "any":
        return _SKIP
    if key == "set_eq":
        # Wrong set: swap in a placeholder
        return ["__WRONG_SET_ELEMENT__"]
    if key == "subset":
        return ["__UNEXPECTED__"]
    if key == "superset":
        return []  # missing every required element
    if key == "contains":
        return []  # doesn't contain anything
    if key == "length":
        # Hard to synthesize without recursion; default to a length-0 list
        return []
    if key == "substring":
        return "WITHOUT_SUBSTRING"
    if key == "substring_all":
        return "MISSING"
    if key == "substring_any":
        return "NO_MATCH_AT_ALL"
    if key == "regex":
        return "no match"
    if key == "matches_semantic":
        return "completely_unrelated_text"
    if key == "fields":
        # Return an empty dict — nested predicates will fail
        return {}
    if key == "expr":
        # Cannot reliably negate an arbitrary expression
        return _SKIP
    return _SKIP


def _collection_name(entity_type: str) -> str:
    lower = entity_type.lower()
    return lower if lower.endswith("s") else lower + "s"
