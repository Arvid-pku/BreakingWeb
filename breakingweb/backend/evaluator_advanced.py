"""Stub for advanced environment evaluation.

Gmail environment evaluation is not yet implemented.  This module provides
the :class:`AdvancedEvaluator` interface so that the server can start and
serve legacy page benchmarks without errors.
"""

from __future__ import annotations

from typing import Any


class AdvancedEvaluator:
    """Placeholder evaluator for advanced (non-page) environments."""

    def __init__(self, session_manager: Any) -> None:
        self._session_manager = session_manager

    def evaluate(
        self,
        *,
        session_id: str,
        task_id: str | None = None,
        benchmark_state: dict[str, Any] | None = None,
        trajectory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return a stub evaluation result.

        A real implementation would inspect the session state and compare it
        against the task's success criteria.
        """
        return {
            "session_id": session_id,
            "task_id": task_id,
            "score": 0.0,
            "passed": False,
            "reason": "Advanced environment evaluation is not yet implemented.",
            "checks": [],
        }
