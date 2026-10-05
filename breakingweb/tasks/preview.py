"""CLI: apply a task's canonical_diff to its seeded initial state to produce
the canonical final state (for author visual review).

Phase 0 ships ``--text-only`` mode (JSON dump of the final state). Phase 1
will wire up the SPA launch.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import sys
from typing import Any


# ── Predicate → representative concrete value ────────────────────────

def represent_predicate(pred: dict) -> Any:
    """Pick a representative concrete value for a predicate.

    Used by the preview tool to concretize canonical final states for
    author review. ``{expr:}`` has no inherent representative — authors
    must provide an ``example:`` value alongside the predicate for preview
    to work (not supported in Phase 0; raises).
    """
    if not isinstance(pred, dict) or len(pred) != 1:
        raise ValueError(f"predicate must be single-key dict, got {pred!r}")
    key = next(iter(pred))
    val = pred[key]

    if key == "eq":
        return val
    if key == "in":
        return val[0] if val else None
    if key == "between":
        lo, hi = val
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            return (lo + hi) / 2
        return lo  # strings / dates: lo as the "earliest" representative
    if key == "any":
        return None
    if key == "expr":
        raise ValueError(
            "{expr:} predicate has no inherent representative value; "
            "preview requires an explicit `example:` value (Phase 1 feature)"
        )
    if key == "set_eq":
        return list(val)
    if key == "subset":
        return list(val)[:1]
    if key == "superset":
        return list(val)
    if key == "contains":
        return [val]
    if key == "length":
        # Best effort: a list of the requested length if predicate is {eq: N}
        if isinstance(val, dict) and "eq" in val and isinstance(val["eq"], int):
            return [None] * val["eq"]
        return []
    if key == "substring":
        return f"<...{val}...>"
    if key == "substring_all":
        return " ".join(f"<...{s}...>" for s in val)
    if key == "substring_any":
        return f"<...{val[0] if val else ''}...>"
    if key == "regex":
        return f"<regex:{val}>"
    if key == "matches_semantic":
        target = val.get("value", val.get("s", val)) if isinstance(val, dict) else val
        return f"<semantic:{target}>"
    if key == "fields":
        return {
            sub: represent_predicate(subpred) for sub, subpred in val.items()
        }
    raise ValueError(f"unknown predicate key: {key!r}")


# ── Apply canonical_diff to an initial state ─────────────────────────

def _substitute_variable(value: Any, var_name: str, var_value: Any, targets: dict) -> Any:
    """Substitute a bijection variable reference inside a predicate arg.

    Author expressions may reference either the loop variable alone
    (``"v"``) or a target-table lookup (``"target['admin_providers'][v]"``).
    We share the ``eval_core.safe_eval`` allowlist for the latter so the
    restricted-eval trust model stays in one place.
    """
    if not isinstance(value, str):
        return value
    if value.strip() == var_name:
        return var_value
    # Target-reference expression — reuse the matcher's helper so we share
    # the safe-globals allowlist (avoids duplicating restricted eval logic).
    try:
        from breakingweb.eval_core.safe_eval import SAFE_BUILTINS as _SAFE_BUILTINS  # noqa: PLC0415
        # _eval_target_expr only binds `target`; we need v bound too.
        # Inline the same pattern with the extra binding.
        return eval(  # noqa: S307 — mirrors evaluator_diff trust model (author-controlled)
            value,
            {"__builtins__": _SAFE_BUILTINS},
            {var_name: var_value, "target": targets},
        )
    except Exception:
        return value


def _substitute_in_predicate(pred: dict, var_name: str, var_value: Any, targets: dict) -> dict:
    out = {}
    for k, v in pred.items():
        if isinstance(v, str):
            out[k] = _substitute_variable(v, var_name, var_value, targets)
        elif isinstance(v, list):
            out[k] = [_substitute_variable(item, var_name, var_value, targets) for item in v]
        elif isinstance(v, dict):
            out[k] = _substitute_in_predicate(v, var_name, var_value, targets)
        else:
            out[k] = v
    return out


_MODEL_SEARCH_PATHS = (
    "breakingweb.backend.models.patient_portal",
    "breakingweb.backend.models.gmail",
    "breakingweb.backend.models.robinhood",
    "breakingweb.backend.models.amazon",
    "breakingweb.backend.models.booking",
    "breakingweb.backend.models.lms",
    "breakingweb.backend.models.reddit",
)


def _find_entity_class(entity_type: str):
    """Locate the pydantic model class by name across env model modules."""
    for module_name in _MODEL_SEARCH_PATHS:
        try:
            mod = importlib.import_module(module_name)
            cls = getattr(mod, entity_type, None)
            if cls is not None:
                return cls
        except Exception:
            continue
    return None


def _collection_name(entity_type: str) -> str:
    lower = entity_type.lower()
    return lower if lower.endswith("s") else lower + "s"


def apply_canonical_diff(
    initial_state: Any,
    task_id: str,
    targets: dict,
) -> Any:
    """Apply a task's canonical_diff to an initial state, producing the
    canonical final state. Pure function — doesn't mutate input.

    Phase 0: handles ``create`` entries (including bijection). ``update``
    and ``delete`` are no-ops in preview (a comment is printed); full
    support lands in a Phase 1 follow-up.
    """
    from breakingweb.tasks._registry import get_task
    from breakingweb.eval_core.safe_eval import safe_eval

    task = get_task(task_id)
    cd = getattr(task, "canonical_diff", None)
    if cd is None:
        raise ValueError(f"Task {task_id} has no canonical_diff")

    block = cd.oneof[0] if cd.oneof else cd

    final = copy.deepcopy(initial_state)

    for entry in block.create:
        collection_name = _collection_name(entry.entity)
        collection = getattr(final, collection_name, None)
        if collection is None:
            continue

        cls = _find_entity_class(entry.entity)

        if entry.bijection is not None:
            try:
                left = safe_eval(entry.bijection.over, {"target": targets, "initial": None, "state": None})
            except Exception:
                continue

            for lv in left:
                new_fields: dict[str, Any] = {}
                for fname, pred in entry.properties.items():
                    pred_subst = _substitute_in_predicate(
                        pred, entry.bijection.variable, lv, targets,
                    )
                    try:
                        new_fields[fname] = represent_predicate(pred_subst)
                    except ValueError:
                        # Skip predicates we can't concretize (e.g. {expr:})
                        continue
                new_fields.setdefault("id", f"appt_new_{lv}")
                if cls is not None:
                    try:
                        collection.append(cls(**new_fields))
                    except Exception:
                        # Model constructor rejected our representative values;
                        # fall back to appending the raw dict for text preview.
                        collection.append(new_fields)
                else:
                    collection.append(new_fields)
        else:
            new_fields = {"id": f"{entry.entity.lower()}_new_0"}
            for fname, pred in entry.properties.items():
                try:
                    new_fields[fname] = represent_predicate(pred)
                except ValueError:
                    continue
            if cls is not None:
                try:
                    collection.append(cls(**new_fields))
                except Exception:
                    collection.append(new_fields)
            else:
                collection.append(new_fields)

    # Phase 0: update/delete are no-ops in preview.
    if block.update or block.delete:
        print(
            "# preview: update/delete entries not applied (Phase 1 feature)",
            file=sys.stderr,
        )

    return final


# ── CLI ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview the canonical final state of a task (author review tool).",
    )
    parser.add_argument("task_id")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--text-only", action="store_true",
                        help="Print canonical state as JSON text (Phase 0 mode).")
    args = parser.parse_args()

    from breakingweb.backend.state import SessionManager
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id=_infer_env_from_task(args.task_id),
        task_id=args.task_id,
        seed=args.seed,
    )
    initial = sm.get_state(sid)
    final = apply_canonical_diff(initial, args.task_id, dict(targets))

    # Text-only mode is the only mode in Phase 0
    print(final.model_dump_json(indent=2))
    return 0


def _infer_env_from_task(task_id: str) -> str:
    """Map task_id prefix to env_id."""
    from breakingweb.tasks._registry import get_task
    return get_task(task_id).env_id


if __name__ == "__main__":
    sys.exit(main())
