"""Evaluator result dataclasses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Failure:
    kind: str
    description: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    desc: str
    passed: bool
    error: str | None = None
    penalty: float | None = None
    skipped: bool = False

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"desc": self.desc, "passed": self.passed}
        if self.error is not None:
            out["error"] = self.error
        if self.penalty is not None:
            out["penalty"] = self.penalty
        if self.skipped:
            out["skipped"] = True
        return out


@dataclass
class EvalResult:
    score: float
    success: bool
    reasoning: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    negative_checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    collateral: Any = None
    bijection_graphs: list[dict[str, Any]] = field(default_factory=list)
    final_score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        final_score = self.score if self.final_score is None else self.final_score
        out: dict[str, Any] = {
            "score": self.score,
            "final_score": final_score,
            "success": self.success,
            "reasoning": self.reasoning,
            "checks": self.checks,
            "negative_checks": self.negative_checks,
        }
        if self.collateral is not None:
            out["collateral"] = self.collateral
        if self.bijection_graphs:
            out["bijection_graphs"] = self.bijection_graphs
        if self.failures:
            out["failures"] = [
                {"kind": f.kind, "description": f.description, "details": dict(f.details)}
                for f in self.failures
            ]
        return out


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def get_field(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a mapping, dataclass, Pydantic model, or plain object."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def get_list(obj: Any, name: str) -> list[Any]:
    value = get_field(obj, name, [])
    if value is None:
        return []
    return list(value)
