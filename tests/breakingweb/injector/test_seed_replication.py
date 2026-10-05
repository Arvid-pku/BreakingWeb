"""Tests for the multiplier/cap mechanic on seed-layer primitives.

The brief asks for ~2× decoy/notification/order/position counts. Rather
than force every variant author to copy-paste hand-typed entries, the
seed primitives now accept a `multiplier: N` knob and a `cap: M` knob so
a one-line yaml change can double the effective quantity. This test
confirms the helper behaves correctly.
"""

from __future__ import annotations

import pytest

from breakingweb.injector.seed import (
    _MULTIPLIER_CAP_DEFAULTS,
    _replicate_with_multiplier,
)


def test_multiplier_one_is_a_noop() -> None:
    items = [{"name": "a"}, {"name": "b"}]
    assert _replicate_with_multiplier(items, 1, cap=10) == items


def test_multiplier_two_doubles_with_distinguishable_replicas() -> None:
    items = [{"subject": "X"}, {"subject": "Y"}]
    out = _replicate_with_multiplier(items, 2, cap=10, suffix_field="subject")
    assert len(out) == 4
    # First copy is verbatim.
    assert out[0] == {"subject": "X"}
    assert out[1] == {"subject": "Y"}
    # Second copy is tagged so two seeded entries never share an exact subject.
    assert out[2]["subject"] != "X"
    assert "alt" in out[2]["subject"]
    assert out[3]["subject"] != "Y"


def test_cap_truncates_replicas() -> None:
    items = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    out = _replicate_with_multiplier(items, 3, cap=4, suffix_field="name")
    assert len(out) == 4


def test_string_decoys_replicate_as_is() -> None:
    """Some Gmail variants pass plain strings instead of dicts."""
    items = ["one", "two"]
    out = _replicate_with_multiplier(items, 2, cap=10, suffix_field="subject")
    assert len(out) == 4
    assert out[0] == "one"
    assert out[2] == "one"  # plain strings can't be tagged → repeated verbatim


def test_default_caps_match_audit_doc() -> None:
    """The cap table is referenced from the audit; sanity-check the values."""
    assert _MULTIPLIER_CAP_DEFAULTS["gmail_decoys"] == 12
    assert _MULTIPLIER_CAP_DEFAULTS["gmail_aliases"] == 8
    assert _MULTIPLIER_CAP_DEFAULTS["rh_decoys_notifications"] == 14
    assert _MULTIPLIER_CAP_DEFAULTS["rh_noise_orders"] == 8
    assert _MULTIPLIER_CAP_DEFAULTS["rh_confusing_positions"] == 6
    assert _MULTIPLIER_CAP_DEFAULTS["rh_confusing_stocks"] == 8


@pytest.mark.parametrize("multiplier", [0, -1])
def test_non_positive_multiplier_is_a_noop(multiplier: int) -> None:
    """multiplier ≤ 0 must not produce empty output (degrades gracefully)."""
    items = [{"name": "a"}]
    out = _replicate_with_multiplier(items, multiplier, cap=10)
    assert out == items
