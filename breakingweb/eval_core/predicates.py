"""Predicate grammar implementation."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .access import EntityView, get_value
from .safe_eval import SafeEvalError, safe_eval


ALLOWED_PREDICATE_KEYS = frozenset({
    "eq", "in", "between", "expr", "any",
    "set_eq", "subset", "superset", "contains", "length",
    "substring", "substring_all", "substring_any", "regex", "matches_semantic",
    "fields",
    "not", "all_of", "any_of",
})


@dataclass
class PredicateScope:
    value: Any
    target: Mapping[str, Any]
    initial: Any = None
    state: Any = None
    bijection_var: Any = None
    session_start: datetime | None = None

    def child(self, value: Any, *, bijection_var: Any | None = None) -> "PredicateScope":
        return PredicateScope(
            value=value,
            target=self.target,
            initial=self.initial,
            state=self.state,
            bijection_var=self.bijection_var if bijection_var is None else bijection_var,
            session_start=self.session_start,
        )


def validate_predicate_shape(predicate: Any) -> tuple[str, Any]:
    if not isinstance(predicate, Mapping) or len(predicate) != 1:
        raise ValueError(f"predicate must be a single-key mapping, got {predicate!r}")
    key = next(iter(predicate))
    if key not in ALLOWED_PREDICATE_KEYS:
        raise ValueError(f"unknown predicate key {key!r}")
    return key, predicate[key]


def _as_set(value: Any) -> set[Any]:
    if value is None:
        return set()
    return set(value)


def _semantic_match(a: Any, b: Any, threshold: float = 0.8) -> bool:
    if a == b:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.01
    return difflib.SequenceMatcher(None, str(a), str(b)).ratio() >= threshold


def _expr_bindings(scope: PredicateScope) -> dict[str, Any]:
    x = scope.value
    if isinstance(x, Mapping):
        x = EntityView(x)
    return {
        "x": x,
        "v": scope.bijection_var,
        "target": scope.target,
        "initial": scope.initial,
        "state": scope.state,
        "session_start": scope.session_start,
    }


def _fuzzy_eq(a: Any, b: Any) -> bool:
    if a == b:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.01
    try:
        if isinstance(a, str) and isinstance(b, (int, float)):
            return _fuzzy_eq(float(a), b)
        if isinstance(b, str) and isinstance(a, (int, float)):
            return _fuzzy_eq(a, float(b))
    except ValueError:
        return False
    return False


def eval_predicate(predicate: Mapping[str, Any], scope: PredicateScope) -> bool:
    """Evaluate a single predicate against the current scope value."""
    key, arg = validate_predicate_shape(predicate)
    value = scope.value

    if key == "any":
        return True
    if key == "eq":
        return _fuzzy_eq(value, arg)
    if key == "in":
        return value in arg
    if key == "between":
        lo, hi = arg
        return lo <= value <= hi

    if key == "set_eq":
        return _as_set(value) == _as_set(arg)
    if key == "subset":
        return _as_set(value).issubset(_as_set(arg))
    if key == "superset":
        return _as_set(value).issuperset(_as_set(arg))
    if key == "contains":
        return arg in (value or [])
    if key == "length":
        try:
            length = len(value)
        except TypeError:
            return False
        return eval_predicate(arg, scope.child(length))

    if key == "substring":
        return str(arg) in str(value or "")
    if key == "substring_all":
        haystack = str(value or "")
        return all(str(part) in haystack for part in arg)
    if key == "substring_any":
        haystack = str(value or "")
        return any(str(part) in haystack for part in arg)
    if key == "regex":
        return re.search(str(arg), str(value or "")) is not None
    if key == "matches_semantic":
        if isinstance(arg, Mapping):
            target_text = arg.get("value", arg.get("s"))
            threshold = float(arg.get("threshold", 0.8))
        else:
            target_text = arg
            threshold = 0.8
        return _semantic_match(value, target_text, threshold)

    if key == "fields":
        if value is None:
            return False
        return all(
            eval_predicate(sub_pred, scope.child(get_value(value, field)))
            for field, sub_pred in arg.items()
        )

    if key == "expr":
        try:
            return bool(safe_eval(str(arg), _expr_bindings(scope)))
        except SafeEvalError:
            return False

    if key == "not":
        return not eval_predicate(arg, scope)
    if key == "all_of":
        return all(eval_predicate(p, scope) for p in arg)
    if key == "any_of":
        return any(eval_predicate(p, scope) for p in arg)

    raise AssertionError(f"unreachable predicate key {key!r}")


def all_field_predicates_hold(
    predicates: Mapping[str, Mapping[str, Any]],
    fields: Mapping[str, Any],
    scope: PredicateScope,
) -> bool:
    return all(eval_predicate(pred, scope.child(fields.get(name))) for name, pred in predicates.items())
