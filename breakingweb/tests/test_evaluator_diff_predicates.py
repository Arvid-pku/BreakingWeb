"""Unit tests for ``breakingweb.evaluator_diff.eval_predicate``.

Covers every predicate kind defined in the canonical-diff spec §3.2. Each test
builds a ``PredicateScope`` and asserts the boolean result of
``eval_predicate``. These tests are the source-of-truth for predicate semantics
before downstream compute_diff / match_diff are wired up (Tasks 3-6).
"""

from __future__ import annotations

import pytest

from breakingweb.eval_core import PredicateScope, eval_predicate


def _scope(x, **kw):
    """Build a PredicateScope with ``value=x`` and optional overrides."""
    defaults = dict(target={}, initial=None, state=None, bijection_var=None)
    defaults.update(kw)
    return PredicateScope(value=x, **defaults)


# ------------------------------------------------------------------
# Scalar predicates
# ------------------------------------------------------------------

def test_eq_passes_on_equal():
    assert eval_predicate({"eq": "scheduled"}, _scope("scheduled")) is True


def test_eq_fails_on_unequal():
    assert eval_predicate({"eq": "scheduled"}, _scope("cancelled")) is False


def test_in_passes():
    assert eval_predicate({"in": ["a", "b", "c"]}, _scope("b")) is True


def test_in_fails():
    assert eval_predicate({"in": ["a", "b", "c"]}, _scope("z")) is False


def test_between_inclusive():
    pred = {"between": [10, 20]}
    assert eval_predicate(pred, _scope(10)) is True
    assert eval_predicate(pred, _scope(20)) is True
    assert eval_predicate(pred, _scope(15)) is True
    assert eval_predicate(pred, _scope(9)) is False
    assert eval_predicate(pred, _scope(21)) is False


def test_any_always_true():
    pred = {"any": True}
    assert eval_predicate(pred, _scope("anything")) is True
    assert eval_predicate(pred, _scope(None)) is True
    assert eval_predicate(pred, _scope([])) is True


# ------------------------------------------------------------------
# Collection predicates
# ------------------------------------------------------------------

def test_set_eq_order_insensitive():
    pred = {"set_eq": ["inbox", "starred"]}
    assert eval_predicate(pred, _scope(["starred", "inbox"])) is True
    assert eval_predicate(pred, _scope(["inbox", "starred"])) is True
    assert eval_predicate(pred, _scope(["inbox"])) is False


def test_subset():
    pred = {"subset": ["a", "b", "c"]}
    assert eval_predicate(pred, _scope(["a", "b"])) is True
    assert eval_predicate(pred, _scope(["a", "z"])) is False


def test_superset():
    pred = {"superset": ["starred"]}
    assert eval_predicate(pred, _scope(["inbox", "starred"])) is True
    assert eval_predicate(pred, _scope(["inbox"])) is False


def test_contains():
    pred = {"contains": "x"}
    assert eval_predicate(pred, _scope(["w", "x", "y"])) is True
    assert eval_predicate(pred, _scope(["w", "y"])) is False


def test_length():
    pred = {"length": {"eq": 3}}
    assert eval_predicate(pred, _scope([1, 2, 3])) is True
    assert eval_predicate(pred, _scope([1, 2])) is False


# ------------------------------------------------------------------
# Text predicates
# ------------------------------------------------------------------

def test_substring():
    assert eval_predicate({"substring": "hello"}, _scope("say hello world")) is True
    assert eval_predicate({"substring": "hello"}, _scope("goodbye")) is False


def test_substring_all():
    assert eval_predicate({"substring_all": ["a", "b"]}, _scope("abc def")) is True
    assert eval_predicate({"substring_all": ["a", "z"]}, _scope("abc def")) is False


def test_substring_any():
    assert eval_predicate({"substring_any": ["x", "b"]}, _scope("abc")) is True
    assert eval_predicate({"substring_any": ["x", "y"]}, _scope("abc")) is False


def test_regex():
    assert eval_predicate({"regex": r"\d+"}, _scope("abc123")) is True
    assert eval_predicate({"regex": r"^\d+$"}, _scope("abc123")) is False


# ------------------------------------------------------------------
# Expr predicate (restricted-eval)
# ------------------------------------------------------------------

def test_expr_with_x_in_scope():
    pred = {"expr": "x > 10"}
    assert eval_predicate(pred, _scope(15)) is True
    assert eval_predicate(pred, _scope(5)) is False


def test_expr_with_target_in_scope():
    scope = _scope(42, target={"threshold": 40})
    assert eval_predicate({"expr": "x > target['threshold']"}, scope) is True
    scope2 = _scope(20, target={"threshold": 40})
    assert eval_predicate({"expr": "x > target['threshold']"}, scope2) is False


# ------------------------------------------------------------------
# Nested / composite predicates
# ------------------------------------------------------------------

def test_fields_selective():
    value = {"zip": "94107", "city": "SF", "street": "1 Main St"}
    assert (
        eval_predicate({"fields": {"zip": {"eq": "94107"}}}, _scope(value)) is True
    )
    assert (
        eval_predicate({"fields": {"zip": {"eq": "10001"}}}, _scope(value)) is False
    )


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------

def test_unknown_predicate_raises():
    with pytest.raises(ValueError, match="unknown"):
        eval_predicate({"bogus": 1}, _scope("x"))
