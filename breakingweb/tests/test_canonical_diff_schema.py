"""Tests for the CanonicalDiff pydantic schema.

Covers the canonical_diff grammar defined in
``docs/superpowers/specs/2026-04-16-correctness-diff-design.md`` §3.1–§3.7.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from breakingweb.tasks.canonical_diff import (
    Bijection,
    CanonicalDiff,
    Constraint,
    CreateEntry,
    DeleteEntry,
    InvariantEntry,
    NamedInvariant,
    UpdateEntry,
)


def test_minimal_diff_parses() -> None:
    diff = CanonicalDiff.model_validate(
        {"invariant": [{"collection": "state.emails", "preserve": "ALL"}]}
    )
    assert len(diff.invariant) == 1
    assert diff.invariant[0].collection == "state.emails"


def test_create_entry_requires_entity() -> None:
    with pytest.raises(ValidationError):
        CreateEntry.model_validate({"properties": {"foo": {"eq": "bar"}}})


def test_bijection_entry_parses() -> None:
    entry = CreateEntry.model_validate(
        {
            "entity": "Appointment",
            "bijection": {"over": "target.due_ids", "variable": "v"},
            "properties": {
                "provider_id": {"in": "target.admin_providers[v]"},
                "status": {"eq": "scheduled"},
            },
        }
    )
    assert entry.entity == "Appointment"
    assert entry.bijection is not None
    assert entry.bijection.variable == "v"
    assert entry.bijection.over == "target.due_ids"
    assert entry.properties["status"] == {"eq": "scheduled"}


def test_update_entry_requires_where() -> None:
    with pytest.raises(ValidationError):
        UpdateEntry.model_validate(
            {"entity": "Email", "changes": {"is_read": {"eq": True}}}
        )


def test_named_invariant_ref_grammar() -> None:
    # Valid refs
    for ref in ("invariant[0]", "create[2]", "update[0]", "delete[0]"):
        named = NamedInvariant.model_validate({"name": "X", "ref": ref})
        assert named.ref == ref

    # "invariant" without brackets is invalid
    with pytest.raises(ValidationError):
        NamedInvariant.model_validate({"name": "X", "ref": "invariant"})

    # Unknown kind
    with pytest.raises(ValidationError):
        NamedInvariant.model_validate({"name": "X", "ref": "foo[0]"})


def test_constraints_block() -> None:
    c = Constraint.model_validate(
        {
            "desc": "no overlapping appointments",
            "expr": "not any(a.start == b.start for a in ...)",
            "severity": "high",
        }
    )
    assert c.severity == "high"
    assert c.desc == "no overlapping appointments"


def test_unknown_predicate_key_rejected():
    """Unknown predicate kinds fail at load time."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CreateEntry.model_validate({
            "entity": "X",
            "properties": {"f": {"bogus": 1}},
        })


def test_multi_key_predicate_rejected():
    """Predicates with more than one key fail at load time."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CreateEntry.model_validate({
            "entity": "X",
            "properties": {"f": {"eq": 1, "in": [1]}},
        })


def test_nested_fields_predicate_recursively_validated():
    """A {fields: {...}} predicate recursively validates inner predicates."""
    from pydantic import ValidationError
    # Valid: nested eq
    CreateEntry.model_validate({
        "entity": "X",
        "properties": {"addr": {"fields": {"city": {"eq": "NY"}}}},
    })
    # Invalid: inner predicate has unknown key
    with pytest.raises(ValidationError):
        CreateEntry.model_validate({
            "entity": "X",
            "properties": {"addr": {"fields": {"city": {"bogus": "NY"}}}},
        })


def test_length_predicate_recursively_validated():
    """A {length: ...} predicate recursively validates its inner predicate."""
    from pydantic import ValidationError
    # Valid: length with scalar predicate
    CreateEntry.model_validate({
        "entity": "X",
        "properties": {"items": {"length": {"eq": 3}}},
    })
    # Invalid: inner predicate has unknown key
    with pytest.raises(ValidationError):
        CreateEntry.model_validate({
            "entity": "X",
            "properties": {"items": {"length": {"bogus": 3}}},
        })


def test_negative_weight_rejected():
    """Negative weight values are rejected."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CreateEntry.model_validate({
            "entity": "X",
            "weight": -1.0,
        })


def test_zero_count_rejected():
    """Count < 1 is nonsensical for a create entry."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CreateEntry.model_validate({
            "entity": "X",
            "count": 0,
        })
