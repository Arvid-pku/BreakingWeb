"""Pydantic v2 schema for the ``canonical_diff`` block of a task YAML.

Encodes the canonical-diff grammar described in
``docs/superpowers/specs/2026-04-16-correctness-diff-design.md`` §3.1–§3.7.

The canonical_diff block specifies how a task's expected state transformation
should be verified. It consists of four operation kinds (``create``, ``update``,
``delete``, ``invariant``), plus free-form ``constraints`` expressions and
``named_invariants`` that reference operations by index.

All models use ``ConfigDict(extra="forbid")`` so unknown YAML keys raise
``ValidationError`` at load time. Predicate maps (``properties``, ``where``,
``changes``) are validated against an allowlist of predicate keys.

The trust model for the ``{expr: "..."}`` predicate is implemented in
``breakingweb/eval_core/safe_eval.py`` (AST validation + restricted builtins
+ forbidden name/dunder checks) — no new security surface is introduced here.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "Bijection",
    "CanonicalDiff",
    "CanonicalDiffBlock",
    "Constraint",
    "CreateEntry",
    "DeleteEntry",
    "InvariantEntry",
    "NamedInvariant",
    "UpdateEntry",
]


# ------------------------------------------------------------------
# Predicate-key allowlist
# ------------------------------------------------------------------

# Scalar predicates.
_SCALAR_PREDICATES = frozenset({"eq", "in", "between", "expr", "any"})

# Collection predicates.
_COLLECTION_PREDICATES = frozenset({"set_eq", "subset", "superset", "contains", "length"})

# Text predicates.
_TEXT_PREDICATES = frozenset(
    {"substring", "substring_all", "substring_any", "regex", "matches_semantic"}
)

# Nested predicates.
_NESTED_PREDICATES = frozenset({"fields"})

_ALLOWED_PREDICATE_KEYS: frozenset[str] = (
    _SCALAR_PREDICATES
    | _COLLECTION_PREDICATES
    | _TEXT_PREDICATES
    | _NESTED_PREDICATES
)


def _validate_predicate(p: Any) -> dict[str, Any]:
    """Validate a single predicate value.

    A predicate must be a dict with exactly one key, and that key must appear in
    the allowlist. Returns the predicate unchanged on success.

    For nested predicates (``fields`` and ``length``), the inner predicate(s)
    are recursively validated so typos inside a nested block (e.g.
    ``{fields: {city: {bogus: 1}}}``) are rejected at load time.
    """
    if not isinstance(p, dict):
        raise ValueError(
            f"predicate must be a dict, got {type(p).__name__}: {p!r}"
        )
    if len(p) != 1:
        raise ValueError(
            f"predicate must have exactly one key, got {len(p)}: {list(p)!r}"
        )
    key = next(iter(p))
    if key not in _ALLOWED_PREDICATE_KEYS:
        raise ValueError(
            f"predicate key {key!r} is not in the allowlist "
            f"{sorted(_ALLOWED_PREDICATE_KEYS)!r}"
        )
    arg = p[key]
    # Recurse into nested predicate forms.
    if key == "fields":
        if not isinstance(arg, dict):
            raise ValueError(
                f"'fields' predicate expects a dict of field -> predicate, "
                f"got {type(arg).__name__}"
            )
        for sub_field, sub_predicate in arg.items():
            if not isinstance(sub_field, str):
                raise ValueError(
                    f"'fields' predicate keys must be strings, "
                    f"got {type(sub_field).__name__}"
                )
            _validate_predicate(sub_predicate)
    elif key == "length":
        _validate_predicate(arg)
    return p


def _validate_predicate_map(value: Any) -> dict[str, dict[str, Any]]:
    """Validate a mapping of field-name -> predicate."""
    if not isinstance(value, dict):
        raise ValueError(
            f"predicate map must be a dict, got {type(value).__name__}"
        )
    for field_name, predicate in value.items():
        if not isinstance(field_name, str):
            raise ValueError(
                f"predicate map keys must be strings, got {type(field_name).__name__}"
            )
        _validate_predicate(predicate)
    return value


# ------------------------------------------------------------------
# Sub-models
# ------------------------------------------------------------------

class Bijection(BaseModel):
    """One-to-one binding between a target collection and a loop variable.

    ``over`` names the target collection (e.g. ``target.due_ids``) and
    ``variable`` names the loop variable referenced inside the ``properties``
    predicates (e.g. ``target.admin_providers[v]``).
    """

    over: str
    variable: str

    model_config = ConfigDict(extra="forbid")


class CreateEntry(BaseModel):
    """One entry in ``canonical_diff.create``."""

    entity: str
    collection: str | None = None
    bijection: Bijection | None = None
    count: int = Field(default=1, ge=1)
    weight: float = Field(default=1.0, ge=0.0)
    desc: str | None = None  # optional human-readable check label
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator("properties")
    @classmethod
    def _check_properties(cls, value: Any) -> dict[str, dict[str, Any]]:
        return _validate_predicate_map(value)


class UpdateEntry(BaseModel):
    """One entry in ``canonical_diff.update``.

    ``where`` is required (a task cannot update records without selecting them).

    ``collection`` optionally overrides the entity→collection mapping. Useful
    on envs where multiple state collections hold the same entity type
    (e.g. Reddit's ``messages`` and ``sent_messages`` both hold ``Message``);
    without the override, the matcher's ``collection_map`` last-one-wins
    can route an update at the wrong collection.
    """

    entity: str
    collection: str | None = None
    where: dict[str, dict[str, Any]]
    changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    bijection: Bijection | None = None
    weight: float = Field(default=1.0, ge=0.0)
    desc: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("where")
    @classmethod
    def _check_where(cls, value: Any) -> dict[str, dict[str, Any]]:
        return _validate_predicate_map(value)

    @field_validator("changes")
    @classmethod
    def _check_changes(cls, value: Any) -> dict[str, dict[str, Any]]:
        return _validate_predicate_map(value)


class DeleteEntry(BaseModel):
    """One entry in ``canonical_diff.delete``."""

    entity: str
    collection: str | None = None
    where: dict[str, dict[str, Any]]
    bijection: Bijection | None = None
    weight: float = Field(default=1.0, ge=0.0)
    desc: str | None = None  # optional human-readable check label

    model_config = ConfigDict(extra="forbid")

    @field_validator("where")
    @classmethod
    def _check_where(cls, value: Any) -> dict[str, dict[str, Any]]:
        return _validate_predicate_map(value)


class InvariantEntry(BaseModel):
    """One entry in ``canonical_diff.invariant``.

    An invariant asserts that a collection is preserved — nothing in the target
    region (optionally narrowed by ``filter``) should have been mutated.

    When ``filter`` is set and ``comprehensive`` is True, the filter is treated
    as the author's complete opinion on the collection — entries NOT matching
    the filter are considered explicitly allowed to change (server-side
    cascades, allowed over-production) and are skipped by the collateral
    sweep. Without ``comprehensive``, the sweep still flags non-matching
    entries as "unaccounted," forcing the author to list every allowed
    side-effect as a positive update.
    """

    collection: str
    filter: str | None = None
    preserve: Literal["ALL"] = "ALL"
    weight: float = Field(default=1.0, ge=0.0)
    comprehensive: bool = False

    model_config = ConfigDict(extra="forbid")


class Constraint(BaseModel):
    """Free-form constraint expression evaluated against the post-state."""

    desc: str
    expr: str
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    weight: float = Field(default=1.0, ge=0.0)

    model_config = ConfigDict(extra="forbid")


_REF_PATTERN = re.compile(r"^(invariant|create|update|delete)\[\d+\]$")


class NamedInvariant(BaseModel):
    """A named reference to one of the canonical_diff entries.

    ``ref`` must match the grammar ``(invariant|create|update|delete)[N]``
    (e.g. ``"invariant[0]"``, ``"create[2]"``).
    """

    name: str
    ref: str
    severity: Literal["critical", "high", "medium", "low"] = "medium"

    model_config = ConfigDict(extra="forbid")

    @field_validator("ref")
    @classmethod
    def _check_ref(cls, value: str) -> str:
        if not isinstance(value, str) or not _REF_PATTERN.match(value):
            raise ValueError(
                f"NamedInvariant.ref must match "
                f"'(invariant|create|update|delete)[N]', got {value!r}"
            )
        return value


# ------------------------------------------------------------------
# Top-level containers
# ------------------------------------------------------------------

class CanonicalDiffBlock(BaseModel):
    """Container for a single canonical_diff alternative (no ``oneof`` nesting)."""

    create: list[CreateEntry] = Field(default_factory=list)
    update: list[UpdateEntry] = Field(default_factory=list)
    delete: list[DeleteEntry] = Field(default_factory=list)
    invariant: list[InvariantEntry] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    named_invariants: list[NamedInvariant] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CanonicalDiff(CanonicalDiffBlock):
    """Top-level canonical_diff block.

    Extends :class:`CanonicalDiffBlock` with an optional ``oneof`` list of
    alternative blocks — any one of which, if satisfied, is accepted as correct.
    """

    oneof: list[CanonicalDiffBlock] | None = None

    model_config = ConfigDict(extra="forbid")
