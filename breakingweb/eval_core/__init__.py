"""Unified BreakingWeb evaluator.

Single evaluation path: every task's ``canonical_diff`` block is matched
against the computed state diff. Legacy ``eval.checks`` / ``negative_checks``
are no longer supported.

Public entry:
    from breakingweb.eval_core import evaluate
    result = evaluate(task, server_state, targets, trajectory)
"""

from .orchestrator import evaluate
from .diff import Create, Delete, DiffEntry, Update, compute_diff
from .matcher import MatchReport, match_diff
from .predicates import PredicateScope, eval_predicate
from .safe_eval import SafeEvalError, safe_eval
from .types import CheckResult, EvalResult, Failure

__all__ = [
    "CheckResult",
    "Create",
    "Delete",
    "DiffEntry",
    "EvalResult",
    "Failure",
    "MatchReport",
    "PredicateScope",
    "SafeEvalError",
    "Update",
    "compute_diff",
    "evaluate",
    "eval_predicate",
    "match_diff",
    "safe_eval",
]
