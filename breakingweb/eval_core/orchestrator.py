"""Public evaluate() entry point — canonical_diff only."""

from __future__ import annotations

from typing import Any, Mapping

from .diff import compute_diff
from .matcher import match_diff
from .types import EvalResult, Failure, get_field


def _initial_state(final_state: Any) -> Any | None:
    for name in ("_initial_state_copy", "_initial_snapshot"):
        if hasattr(final_state, name):
            value = getattr(final_state, name)
            if value is not None:
                return value
    if isinstance(final_state, Mapping):
        return final_state.get("_initial_state_copy") or final_state.get("_initial_snapshot")
    return None


def _format_reasoning(report: Any) -> str:
    lines = [f"Score: {report.score:.3f}; success={report.passed}"]
    if report.checks:
        passed = sum(1 for c in report.checks if c.get("passed"))
        lines.append(f"Passed {passed}/{len(report.checks)} checks.")
        for check in report.checks:
            marker = "PASS" if check.get("passed") else "FAIL"
            suffix = f" (error: {check.get('error')})" if check.get("error") else ""
            lines.append(f"  [{marker}] {check.get('desc', '')}{suffix}")
    if report.negative_checks:
        failed = [nc for nc in report.negative_checks if not nc.get("passed")]
        if failed:
            total_penalty = sum(nc.get("penalty", 0.0) for nc in failed)
            lines.append(f"Negative check penalties: {len(failed)} triggered, total penalty {total_penalty:.2f}.")
            real_negatives = [nc for nc in failed if nc.get("_kind") != "constraint"]
            constraint_failures = [nc for nc in failed if nc.get("_kind") == "constraint"]
            if real_negatives:
                if constraint_failures:
                    lines.append("Negative checks failed:")
                for nc in real_negatives:
                    lines.append(f"  [PENALTY -{nc.get('penalty', 0.0):.2f}] {nc.get('desc', '')}")
            if constraint_failures:
                if real_negatives:
                    lines.append("Constraints failed:")
                for nc in constraint_failures:
                    lines.append(f"  [PENALTY -{nc.get('penalty', 0.0):.2f}] {nc.get('desc', '')}")
        else:
            lines.append("All negative checks passed (no penalties).")
    if report.failures:
        lines.append("Failures:")
        for failure in report.failures:
            lines.append(f"  - {failure.kind}: {failure.description}")
    lines.append(f"Final score: {report.score:.3f} | Success: {report.passed}")
    return "\n".join(lines)


def _collateral(final_state: Any, initial: Any) -> Any:
    compute = getattr(final_state, "compute_collateral", None)
    if callable(compute):
        try:
            return compute(initial)
        except (AttributeError, TypeError, KeyError):
            return None
    return None


def evaluate(
    task: Any,
    server_state: Any,
    targets: Mapping[str, Any] | None = None,
    trajectory: Any = None,
) -> dict[str, Any]:
    """Evaluate a BreakingWeb task via canonical_diff matching.

    The legacy ``eval.checks`` / ``negative_checks`` path has been removed.
    Every task must declare a ``canonical_diff`` block.
    """
    del trajectory
    targets = dict(targets or {})
    canonical = get_field(task, "canonical_diff")

    if canonical is None:
        result = EvalResult(
            score=0.0,
            final_score=0.0,
            success=False,
            reasoning="Task has no canonical_diff block. Legacy eval.checks are no longer supported.",
            failures=[Failure("missing_canonical_diff", "No canonical_diff block present", {})],
        )
        return result.as_dict()

    initial = _initial_state(server_state)
    if initial is not None:
        try:
            agent_diff = compute_diff(initial, server_state)
        except TypeError:
            agent_diff = []
    else:
        agent_diff = []

    session_start = (
        get_field(task, "session_start", None)
        or (targets.get("session_start") if targets else None)
        or getattr(server_state, "session_start", None)
    )
    if isinstance(session_start, str):
        from datetime import datetime
        try:
            session_start = datetime.fromisoformat(session_start)
        except ValueError:
            session_start = None

    report = match_diff(agent_diff, canonical, targets, initial, server_state, session_start=session_start)

    result = EvalResult(
        score=report.score,
        final_score=report.score,
        success=report.passed,
        reasoning=_format_reasoning(report),
        checks=report.checks,
        negative_checks=report.negative_checks,
        failures=report.failures,
        collateral=_collateral(server_state, initial),
        bijection_graphs=report.bijection_graphs,
    )
    return result.as_dict()
