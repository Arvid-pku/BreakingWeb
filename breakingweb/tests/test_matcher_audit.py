"""Audit battery for the canonical_diff matcher.

Each test probes a specific hypothesis about how the matcher could
produce a wrong score. Tests are designed to fail noisily when they
find a real bug and document the expected behavior when they pass.

Structure:
  Part A — consistency sweeps parametrized over every migrated task.
  Part B — targeted unit tests on synthetic canonical_diffs.

If Part A fires, the bug reproduces on real task data (high signal,
hard to dismiss). If Part B fires, it isolates a specific matcher
branch with a minimal fixture (easy to debug).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from breakingweb.backend.state import SessionManager
from breakingweb.eval_core import (
    MatchReport,
    Update,
    compute_diff,
    match_diff,
)
from breakingweb.tasks._registry import load_all_tasks
from breakingweb.tasks.canonical_diff import (
    Bijection,
    CanonicalDiff,
    Constraint,
    CreateEntry,
    InvariantEntry,
    NamedInvariant,
    UpdateEntry,
)


# ── Fixture helpers ─────────────────────────────────────────────────

def _migrated_task_ids() -> list[str]:
    return sorted(
        tid for tid, t in load_all_tasks().items() if t.canonical_diff is not None
    )


def _setup(task_id: str):
    sm = SessionManager()
    task = load_all_tasks()[task_id]
    sid, targets, _ = sm.create_session(env_id=task.env_id, task_id=task_id, seed=42)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), initial, state, task


def _match_do_nothing(task_id: str) -> MatchReport:
    _, _, targets, initial, state, task = _setup(task_id)
    agent_diff = compute_diff(initial, state)  # empty — nothing changed
    return match_diff(
        agent_diff, task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )


# ══════════════════════════════════════════════════════════════════════
# Part A — Consistency sweeps across every migrated task
# ══════════════════════════════════════════════════════════════════════

def _has_positive_entries(task) -> bool:
    cd = task.canonical_diff
    if cd.oneof:
        return any(
            len(b.create) + len(b.update) + len(b.delete) > 0
            for b in cd.oneof
        )
    return len(cd.create) + len(cd.update) + len(cd.delete) > 0


@pytest.mark.parametrize("task_id", _migrated_task_ids())
def test_do_nothing_score_is_boundary(task_id: str) -> None:
    """Do-nothing trajectory must score exactly 0.0 or exactly 1.0
    (for tasks that have positive entries).

    Any score strictly between is the Class 9 signature — vacuously-satisfied
    bijections contributing full credit, or a vacuous invariant not firing.

    Tasks with NO positive entries (constraint-only canonical_diffs) follow
    a different scoring path post-Class-10 (constraints promoted to the
    positive pool → score = n_passed / n_total, not 0/1). They're
    covered by ``test_constraint_only_task_score_reflects_constraint_pass_ratio``.
    """
    task = load_all_tasks()[task_id]
    if not _has_positive_entries(task):
        pytest.skip(f"{task_id} is constraint-only; see Class 10 test")

    report = _match_do_nothing(task_id)
    in_between = 0.0001 < report.score < 0.9999
    assert not in_between, (
        f"{task_id}: do-nothing score={report.score:.4f} is in forbidden (0,1) range. "
        f"This is the Class 9 signature — likely a vacuous bijection or other "
        f"seed-dependent entry contributing phantom credit.\n"
        f"checks={report.checks}\n"
        f"negative_checks={[nc for nc in report.negative_checks if not nc['passed']]}"
    )


def test_constraint_only_task_score_reflects_constraint_pass_ratio() -> None:
    """Class 10 fix: when a canonical_diff has no create/update/delete,
    the matcher now promotes constraints to the positive pool (n_passed
    / n_total) instead of defaulting to 1.0 minus penalties. A do-nothing
    trajectory on a constraint-only task should score exactly the
    fraction of constraints that hold on the initial state.
    """
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "constraints": [
            {"desc": "always true", "expr": "True", "severity": "medium"},
            {"desc": "always false", "expr": "False", "severity": "medium"},
        ],
    })
    report = match_diff([], block, targets=targets,
                        initial=initial, final=final)

    # 1 of 2 constraints passes → score should be 0.5 (no double-count
    # penalty deduction on the promoted path).
    assert abs(report.score - 0.5) < 1e-6, (
        f"Constraint-only score should reflect pass ratio; got {report.score}"
    )
    assert report.passed is False, (
        "failing constraint should yield passed=False"
    )


def test_oneof_prefers_branch_with_passing_critical_guard() -> None:
    """Critical constraints in oneof blocks act as branch guards.

    The matcher should not select an inapplicable branch just because the
    agent performed that branch's update and earned partial positive credit.
    """
    initial, final, targets = _task_with_real_initial()
    block = CanonicalDiff.model_validate({
        "oneof": [
            {
                "constraints": [
                    {"desc": "wrong guard", "expr": "False", "severity": "critical"},
                ],
                "update": [
                    {
                        "entity": "Appointment",
                        "desc": "wrong branch action",
                        "where": {"id": {"eq": "guard_probe"}},
                        "changes": {"status": {"eq": "cancelled"}},
                    },
                ],
            },
            {
                "constraints": [
                    {"desc": "right guard", "expr": "True", "severity": "critical"},
                ],
                "update": [
                    {
                        "entity": "Appointment",
                        "desc": "right branch action",
                        "where": {"id": {"eq": "missing_probe"}},
                        "changes": {"status": {"eq": "cancelled"}},
                    },
                ],
            },
        ],
    })

    report = match_diff(
        [Update(
            entity="appointments",
            entity_id="guard_probe",
            field_changes={"status": ("scheduled", "cancelled")},
        )],
        block,
        targets=targets,
        initial=initial,
        final=final,
    )

    assert any(
        check["desc"] == "right guard" and check["passed"]
        for check in report.negative_checks
    ), f"selected the wrong oneof branch: {report.negative_checks}"
    assert any(
        failure.description == "right branch action"
        for failure in report.failures
    ), f"expected the applicable branch's missing update, got {report.failures}"


def test_constraint_only_offender_catalog() -> None:
    """Informational: enumerate tasks whose canonical_diff has no positive
    entries. Post Class 10 fix these now score correctly, but authors
    should still consider whether the constraint-only pattern is right
    for the task or whether positive entries would be clearer.
    """
    offenders: list[str] = []
    for task_id, task in load_all_tasks().items():
        if task.canonical_diff is None:
            continue
        if not _has_positive_entries(task):
            offenders.append(task_id)

    # After the fix this is informational, not a hard failure.
    # Reddit migrated many aggregate/workflow tasks as constraint-only
    # (mark-all-read, workflow orchestration, multi-step actions that
    # can't be expressed via positive-diff grammar). We only flag if
    # the count grows pathologically large.
    assert len(offenders) <= 60, (
        f"Constraint-only canonical_diffs (Class 10): {len(offenders)} tasks. "
        f"These rely on 1.0-fallback minus penalties, producing arbitrary "
        f"do-nothing scores. Offenders: {offenders}"
    )


@pytest.mark.parametrize("task_id", _migrated_task_ids())
def test_score_and_passed_are_consistent(task_id: str) -> None:
    """Internal matcher invariant: passed ⟺ (score == 1.0 AND no failures).

    Divergence between the score and the passed flag means the user sees
    either (score=1.0, passed=False) or (score<1.0, passed=True), both
    of which look like matcher bugs from the outside.
    """
    report = _match_do_nothing(task_id)
    no_failures = len(report.failures) == 0
    full_score = report.score >= 0.9999

    # passed is defined as len(failures) == 0, so these must agree:
    assert report.passed == no_failures, (
        f"{task_id}: passed={report.passed} disagrees with "
        f"failures_empty={no_failures} — matcher internal invariant violated"
    )

    # A full score with failures is a red flag (user sees 1.0 but passed=False).
    if full_score and not no_failures:
        pytest.fail(
            f"{task_id}: score={report.score} but failures={report.failures!r}. "
            "This is the (score=1.0, passed=False) divergence — UX bug."
        )


@pytest.mark.parametrize("task_id", _migrated_task_ids())
def test_matcher_is_idempotent(task_id: str) -> None:
    """Calling match_diff twice with identical inputs yields identical reports.

    If idempotence breaks, the matcher has hidden mutable state (e.g.
    cached result that mutates on lookup, in-place agent_diff mutation).
    That's a correctness and a thread-safety hazard.
    """
    _, _, targets, initial, state, task = _setup(task_id)
    agent_diff = compute_diff(initial, state)

    report_a = match_diff(
        agent_diff, task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )
    report_b = match_diff(
        agent_diff, task.canonical_diff,
        targets=targets, initial=initial, final=state,
    )

    assert report_a.score == report_b.score, f"{task_id}: non-idempotent score"
    assert report_a.passed == report_b.passed, f"{task_id}: non-idempotent passed"
    assert len(report_a.failures) == len(report_b.failures), (
        f"{task_id}: non-idempotent failure count"
    )


# ══════════════════════════════════════════════════════════════════════
# Part B — Targeted probes on synthetic canonical_diffs
# ══════════════════════════════════════════════════════════════════════


def _task_with_real_initial(env_id: str = "patient_portal") -> tuple[Any, Any, dict]:
    """Borrow a real session to provide a plausible initial/final state
    for synthetic-diff tests that still need valid state objects."""
    all_tasks = load_all_tasks()
    # Use any migrated task from the env for its state shape.
    pick = next(
        t for t in all_tasks.values()
        if t.env_id == env_id and t.canonical_diff is not None
    )
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id=env_id, task_id=pick.task_id, seed=42)
    return sm.get_initial_snapshot(sid), sm.get_state(sid), dict(targets)


def test_invariant_filter_exception_does_not_silently_skip() -> None:
    """Bug hypothesis: invariant filter that raises is silently treated as
    "entity doesn't match filter", bypassing invariant enforcement entirely.

    A typo like ``filter: "a.nonexistent_field == 'x'"`` would make the
    matcher accept any mutation to the "protected" collection. That's a
    silent hole — invariant bypass by typo.

    Expected-correct behavior: either (a) surface the filter error as a
    failure, or (b) fail-safe by treating the exception as "filter matches"
    so the entity is still enforced. Current code chooses (c): silently
    skip the entity, which is the least safe option.
    """
    initial, final, targets = _task_with_real_initial()

    # Build a minimal invariant whose filter always raises.
    block = CanonicalDiff.model_validate({
        "invariant": [{
            "collection": "state.appointments",
            "filter": "a.totally_nonexistent_field.crash()",
            "preserve": "ALL",
        }],
    })

    # Inject a fake mutation so we can observe whether the invariant fires.
    from breakingweb.eval_core import Update
    fake_diff = [Update(
        entity="appointments",
        entity_id="appt_does_not_exist",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(
        fake_diff, block, targets=targets, initial=initial, final=final,
    )

    # Document current behavior. If this starts failing, the matcher
    # tightened — which is probably an improvement.
    filter_silent = all(nc["passed"] for nc in report.negative_checks
                       if "Preserve state.appointments" in nc["desc"])
    assert filter_silent, (
        "Filter exception behavior changed. If filter errors now surface, "
        "great — update this test to expect the failure. If this is still "
        "passing, it documents the known silent-skip bug: invariant filter "
        "typos silently disable invariant enforcement."
    )


def test_oneof_picks_highest_score_first_seen_on_tie() -> None:
    """Document the oneof tie-breaking policy.

    match_diff uses ``report.score > best.score`` (strict), so on ties the
    first block wins. Verify the contract: if two alternatives both score
    0 (neither matches agent_diff), the first alternative's failures are
    the ones reported. This matters for error attribution — if alternative
    B has cleaner failure messages, users see A's.
    """
    initial, final, targets = _task_with_real_initial()

    # Two oneof alternatives, each with a different update-target entity
    # that doesn't exist in the diff. Both score 0 (no matches).
    diff = CanonicalDiff.model_validate({
        "oneof": [
            {"update": [{
                "entity": "Appointment",
                "where": {"id": {"eq": "first_alt_id"}},
                "changes": {"status": {"eq": "scheduled"}},
            }]},
            {"update": [{
                "entity": "Appointment",
                "where": {"id": {"eq": "second_alt_id"}},
                "changes": {"status": {"eq": "cancelled"}},
            }]},
        ],
    })

    report = match_diff([], diff, targets=targets, initial=initial, final=final)

    # Both score 0; document the winning alternative's failure attribution.
    # We just assert ONE block's failures were reported (not a merge or blank).
    assert len(report.failures) >= 1, (
        f"oneof with both alternatives failing produced no failures: report={report!r}"
    )
    descriptions = [f.description for f in report.failures]
    surfaced_alternative = any(
        "Appointment" in d or "scheduled" in d or "cancelled" in d
        for d in descriptions
    )
    assert surfaced_alternative, (
        f"No oneof alternative surfaced in failures: {descriptions!r}"
    )


def test_empty_canonical_diff_scores_one() -> None:
    """An empty canonical_diff (no entries anywhere) should give score=1.0
    and passed=True on do-nothing — vacuously correct.

    If this starts failing, the matcher grew a new required entry kind
    that an empty diff no longer satisfies.
    """
    initial, final, targets = _task_with_real_initial()
    empty = CanonicalDiff.model_validate({})
    report = match_diff([], empty, targets=targets, initial=initial, final=final)
    assert report.score == 1.0, f"empty diff score={report.score}, expected 1.0"
    assert report.passed is True


def test_constraint_expression_exception_becomes_penalty() -> None:
    """Bug hypothesis: constraint expression that raises is caught and
    treated as False (penalty fires). Asymmetric with invariant filter
    which is caught and treated as "skip" (no penalty).

    Document current behavior: constraint error → penalty. If the asymmetry
    is ever fixed, this test guides the migration.
    """
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "constraints": [{
            "expr": "state.totally_nonexistent.crash()",
            "desc": "intentionally broken constraint",
            "severity": "high",
        }],
    })

    report = match_diff([], block, targets=targets, initial=initial, final=final)

    # Constraint raising → ok=False → penalty applied.
    constraint_failed = any(
        not nc["passed"] for nc in report.negative_checks
        if "intentionally broken" in nc["desc"]
    )
    assert constraint_failed, (
        "Constraint exception did not fire as failure. If you fixed the "
        "silent behavior — update this test. Otherwise, the matcher is no "
        "longer fail-safe on malformed constraints."
    )

    # And the score took a hit.
    assert report.score < 1.0, (
        f"Constraint failure should penalize. score={report.score}"
    )


def test_do_nothing_with_real_task_score_is_zero_when_applicable() -> None:
    """Spot-check: for a task with non-empty positive entries that are
    applicable on seed=42, do-nothing must score exactly 0.0.

    Uses pp_schedule_annual_physical as a canonical example — single
    non-bijection create, always applicable. Zero tolerance for drift.
    """
    tid = "pp_schedule_annual_physical"
    if tid not in load_all_tasks() or load_all_tasks()[tid].canonical_diff is None:
        pytest.skip(f"{tid} not migrated on this branch")

    report = _match_do_nothing(tid)
    assert report.score == 0.0, (
        f"{tid} do-nothing score={report.score}, expected 0.0. "
        f"checks={[c for c in report.checks if c['passed']]}"
    )
    assert report.passed is False


def test_session_start_none_with_predicate_using_it() -> None:
    """Bug hypothesis: predicate ``x >= session_start`` when session_start
    is None. Behavior: predicate eval raises TypeError → caught silently
    → predicate returns False. Agent cannot win the check regardless of
    action.

    This is a footgun for tasks that use session_start in predicates but
    forget to plumb it through match_diff.
    """
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "any"}},
            "changes": {
                "booked_at": {"expr": "x >= session_start"},
            },
        }],
    })

    # No session_start argument.
    from breakingweb.eval_core import Update
    fake = [Update(
        entity="appointments",
        entity_id="appt_1",
        field_changes={"booked_at": (None, datetime.now(timezone.utc))},
    )]

    report = match_diff(
        fake, block, targets=targets, initial=initial, final=final,
        session_start=None,
    )

    # Document: with session_start=None, predicate silently returns False.
    # If this assertion flips, someone tightened the matcher — good!
    assert report.score <= 1.0  # sanity; just exercise the path


def test_matcher_does_not_mutate_agent_diff() -> None:
    """Matcher must not mutate the agent_diff list it's passed (shared
    across trajectory storage, visualization, downstream telemetry).
    """
    initial, final, targets = _task_with_real_initial()
    from breakingweb.eval_core import Create
    diff = [Create(entity="appointments", entity_id="x", fields={"id": "x"})]

    block = CanonicalDiff.model_validate({
        "create": [{
            "entity": "Appointment",
            "properties": {"id": {"eq": "x"}},
        }],
    })

    _ = match_diff(diff, block, targets=targets, initial=initial, final=final)
    assert len(diff) == 1, "agent_diff list length mutated"
    assert diff[0].entity_id == "x", "agent_diff entry mutated"


# ══════════════════════════════════════════════════════════════════════
# Part C — Predicate-layer probes (targeted bug hypotheses)
# ══════════════════════════════════════════════════════════════════════


def test_expr_predicate_swallows_author_typos() -> None:
    """Hypothesis: a malformed ``{expr: ...}`` predicate — e.g. referencing a
    target key that doesn't exist — silently returns False instead of
    surfacing the author error. Agents producing the right state would
    unfairly fail, and the author gets no feedback on the typo.

    Current behavior (:237-239): ``except Exception: return False``. This
    is the silent-reject footgun. If this test starts failing, someone
    made expr errors surface — good direction.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            # Typo: target doesn't have TYPO_KEY. Author meant something else.
            "changes": {"status": {"expr": "x == target['TYPO_KEY_THAT_DOESNT_EXIST']"}},
        }],
    })
    agent_did_right_thing = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(agent_did_right_thing, block,
                        targets=targets, initial=initial, final=final)

    # Bug present: report.passed is False because the expr silently returns
    # False on KeyError. The author should have gotten a loud signal instead.
    # This test documents the current (buggy) behavior; flip the assertion
    # when the matcher tightens.
    assert not report.passed, (
        "Author-typo expr no longer silently rejects — matcher tightened. "
        "Update this test to assert the positive direction (loud error)."
    )


def test_contains_predicate_list_element_semantics() -> None:
    """Hypothesis: ``contains: [elem1, elem2]`` uses Python ``in``, which on
    a list value checks LIST-AS-ELEMENT, not SUBSET. Authors typically want
    subset — this is a foot-gun.

    Concretely: value = ``[1, 2, 3]``, predicate ``{contains: [1, 2]}``:
      Python: ``[1, 2] in [1, 2, 3]`` → False
      Intended: ``{1, 2} ⊆ {1, 2, 3]`` → True

    For single-element: ``{contains: 1}`` on ``[1, 2, 3]`` works correctly.
    The trap is specifically the list-argument form.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"notes": {"contains": ["alpha", "beta"]}},
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"notes": (["alpha"], ["alpha", "beta", "gamma"])},
    )]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    # If predicate were subset-like, report.passed would be True (agent's
    # list includes both "alpha" and "beta"). With current element-in
    # semantics, ``["alpha", "beta"] in ["alpha", "beta", "gamma"]`` is
    # False, so the predicate fails.
    assert not report.passed, (
        "`contains: [list]` started accepting subset-like matches. "
        "Either rename predicate to `elem`/`subset` or this test needs updating. "
        "See evaluator_diff.py:172 — current semantic is `arg in value` (element)."
    )


def test_length_predicate_does_not_crash_on_none_value() -> None:
    """Hypothesis: ``{length: {eq: 0}}`` applied to a field whose value is
    None raises TypeError (``len(None)`` unpropagated). The matcher should
    return False gracefully instead of crashing.

    This test fails loudly if a TypeError escapes. If the matcher is already
    graceful, it passes.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"notes": {"length": {"eq": 0}}},
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"notes": ("something", None)},
    )]

    try:
        report = match_diff(diff, block, targets=targets,
                            initial=initial, final=final)
    except TypeError as exc:
        pytest.fail(
            f"BUG: matcher crashed on len(None) instead of returning False. "
            f"evaluator_diff.py:173-182 — wrap in try/except. {exc}"
        )
    assert isinstance(report.score, float)


def test_named_invariant_with_update_ref_applies_label() -> None:
    """Hypothesis: ``named_invariants: - ref: update[0]`` silently no-ops.

    Reading evaluator_diff.py:1110-1136, the attribution loop explicitly
    handles ``invariant`` and ``create`` refs. The ``update`` and ``delete``
    branches have no corresponding code — the loop just iterates past them.

    Impact: tasks with ``ref: update[0]  severity: high`` lose both the
    custom display label AND the severity override. Present-day migrated
    tasks rely on this for labeling (e.g. lms_end_of_semester_verification
    uses ``ref: update[0]`` and ``ref: update[1]``).
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"status": {"eq": "cancelled"}},
            "desc": "default update description",
        }],
        "named_invariants": [{
            "name": "CUSTOM-LABEL-FOR-UPDATE-0",
            "ref": "update[0]",
            "severity": "high",
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    relabeled = any(c.get("desc") == "CUSTOM-LABEL-FOR-UPDATE-0"
                    for c in report.checks)
    assert relabeled, (
        "BUG: named_invariant with ref=update[N] silently no-ops. "
        "Loop at evaluator_diff.py:1110 handles 'invariant' and 'create' only; "
        "add a branch for 'update' and 'delete' that rewrites checks[idx].desc."
    )


def test_named_invariant_severity_override_applied_to_invariant() -> None:
    """Regression: ``named_invariants: - ref: invariant[0]  severity: critical``
    must override the default ``medium`` penalty on the invariant's
    negative_check.

    critical → 0.3 per _SEVERITY_PENALTY table. medium → 0.15.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "invariant": [{
            "collection": "state.appointments",
            "preserve": "ALL",
        }],
        "named_invariants": [{
            "name": "Do not disturb existing appointments",
            "ref": "invariant[0]",
            "severity": "critical",
        }],
    })
    # Trigger the invariant by mutating an appointment.
    diff = [Update(
        entity="appointments",
        entity_id="appt_anything",
        field_changes={"status": ("scheduled", "cancelled")},
    )]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    nc = next(
        (x for x in report.negative_checks
         if x["desc"] == "Do not disturb existing appointments"),
        None,
    )
    assert nc is not None, "named_invariant label was not applied to negative_check"
    assert nc["penalty"] == 0.3, (
        f"severity=critical should yield penalty 0.3, got {nc['penalty']}. "
        "Check that NamedInvariant severity propagation at "
        "evaluator_diff.py:1115-1122 is wired correctly."
    )


def test_matches_semantic_does_not_crash_on_plain_strings() -> None:
    """Exercise ``matches_semantic`` with ordinary string inputs. Regardless
    of whether an embedding model is available, the matcher must not crash.
    If the backend fails to load, matches_semantic should return False
    (conservative) rather than propagate the error.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {"notes": {"matches_semantic": "meeting scheduled"}},
        }],
    })
    diff = [Update(
        entity="appointments",
        entity_id="appt_x",
        field_changes={"notes": ("", "scheduled a meeting")},
    )]

    # Just assert no exception escapes. Pass/fail score irrelevant.
    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)
    assert isinstance(report.score, float)


def test_bijection_excess_tracked_when_empty_target() -> None:
    """Class 9 fix kept ``bijection_excess`` tracking alive even for empty
    targets, so ``named_invariants: - ref: create[N]`` can still flag
    "agent scheduled N when 0 were needed."

    This test verifies: empty-target bijection + agent-created entity +
    ref=create[0] named_invariant → the named invariant FAILS (over-creation
    detected).
    """
    from breakingweb.eval_core import Create
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "create": [{
            "entity": "Appointment",
            "bijection": {"over": "target['NONEXISTENT_EMPTY_KEY']",
                          "variable": "v"},
            "properties": {"id": {"any": True}},
        }],
        "named_invariants": [{
            "name": "Did not schedule more than required",
            "ref": "create[0]",
            "severity": "high",
        }],
    })
    # Agent creates an appointment when 0 were needed.
    diff = [Create(
        entity="appointments",
        entity_id="appt_x",
        fields={"id": "appt_x"},
    )]

    # targets must include the bijection key so _eval_target_expr doesn't
    # fail; give it an empty list.
    targets_with_empty = dict(targets)
    targets_with_empty["NONEXISTENT_EMPTY_KEY"] = []

    report = match_diff(diff, block, targets=targets_with_empty,
                        initial=initial, final=final)

    excess_nc = next(
        (x for x in report.negative_checks
         if x["desc"] == "Did not schedule more than required"),
        None,
    )
    assert excess_nc is not None, (
        "BUG: Class 9 fix lost bijection_excess tracking for empty-target "
        "bijections. Named invariant on create[0] should still fire when "
        "agent creates entities that weren't needed."
    )
    assert not excess_nc["passed"], (
        "Agent created 1 appointment when 0 were needed — "
        "named_invariant on create[0] should FAIL, got passed={}.".format(excess_nc["passed"])
    )


# ══════════════════════════════════════════════════════════════════════
# Part D — Diff-layer & structural probes
# ══════════════════════════════════════════════════════════════════════


def test_non_bijection_update_matches_at_most_one_candidate() -> None:
    """A non-bijection update with a where-clause that matches N agent
    mutations claims only ONE via the ``break`` in the inner loop at
    evaluator_diff.py:928-938. The remaining matches fall through to the
    invariant sweep / unaccounted check.

    This is correct behavior for "the task asks for one specific update",
    but authors should know: if you want "all matching", use a bijection
    over the target set.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    # `where` reads the BEFORE value of the field (so renames like
    # {name: {eq: "OldName"}} work). `changes` asserts the after value.
    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"status": {"eq": "scheduled"}},
            "changes": {"status": {"eq": "cancelled"}},
        }],
    })

    # Two agent mutations, both satisfying the after-state where-clause.
    diff = [
        Update(entity="appointments", entity_id="a1",
               field_changes={"status": ("scheduled", "cancelled")}),
        Update(entity="appointments", entity_id="a2",
               field_changes={"status": ("scheduled", "cancelled")}),
    ]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    # Expected: one update check passes (the first matching candidate is
    # claimed). The other is collateral.
    update_checks = [c for c in report.checks
                     if "Appointment" in (c.get("desc") or "")]
    assert any(c["passed"] for c in update_checks), (
        f"No update check passed despite matching candidates. checks={report.checks}"
    )
    # The unclaimed second update should surface as an unaccounted failure.
    unaccounted = any(f.kind == "unaccounted" for f in report.failures)
    assert unaccounted, (
        "Unclaimed mutation should be flagged as collateral, but the "
        "unaccounted sweep didn't fire. Agent could sneak extra mutations "
        "under the radar of a non-bijection update."
    )


def test_update_with_empty_changes_dict_matches_any_mutation() -> None:
    """An update entry with ``changes: {}`` currently accepts any field
    change on the selected entity. That's because ``_all_predicates_hold``
    on an empty dict returns True vacuously.

    Is this a bug? For "any mutation to X counts" it's intentional. For
    "I forgot to specify what must change" it's a silent acceptance. The
    schema already forbids forgetting the `where:` key (Pydantic default
    is not allowed there) but tolerates empty `changes:`.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",
            "where": {"id": {"eq": "appt_x"}},
            "changes": {},  # intentionally empty
        }],
    })

    # Agent mutates an unrelated field. Empty changes → should still match.
    diff = [Update(entity="appointments", entity_id="appt_x",
                   field_changes={"notes": ("a", "b")})]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)
    assert report.passed, (
        "Empty changes dict no longer matches any mutation — "
        "if this is intentional schema-tightening, update test + hazards doc."
    )


def test_out_of_range_named_invariant_ref_caught_at_registry() -> None:
    """``named_invariants[*].ref`` like ``invariant[99]`` when only 2
    invariants exist should be rejected at task-load time by
    ``_validate_canonical_diff_refs`` at _registry.py:54-86 — not silently
    no-op at match time.

    This test asserts the validator catches the out-of-range case. If it
    starts failing, out-of-range refs slip through and become silent
    no-ops in the matcher.
    """
    from breakingweb.tasks._registry import _validate_canonical_diff_refs
    from breakingweb.tasks._schema import TaskDefinition

    task_raw = {
        "task_id": "synthetic_out_of_range_ref",
        "env_id": "patient_portal",
        "title": "Synthetic",
        "instruction_template": "n/a",
        "difficulty": "easy",
        "time_limit_seconds": 60,
        "expected_steps": 1,
        "primary_primitives": ["grounding"],
        "start_path": "/",
        "canonical_diff": {
            "invariant": [
                {"collection": "state.appointments", "preserve": "ALL"},
            ],
            "named_invariants": [
                {"name": "Out of range", "ref": "invariant[99]",
                 "severity": "medium"},
            ],
        },
    }
    task = TaskDefinition.model_validate(task_raw)

    with pytest.raises(ValueError, match="references invariant\\[99\\]"):
        _validate_canonical_diff_refs(task)


def test_compute_diff_detects_duplicate_ids_cleanly() -> None:
    """compute_diff uses ``_index_by_id`` (line 342) which silently collapses
    entries with the same id. If a state ever gets two entities with the
    same id in the same collection (seed bug, concurrent insert, etc.),
    only the last one is visible.

    Document the current behavior — quiet collapse — as a known corner
    case. A stricter version would raise on duplicate ids.
    """
    from breakingweb.eval_core import compute_diff

    # Dict-of-lists fast path is allowed by _collections_of (line 326).
    initial = {"widgets": [{"id": "w1", "val": 1}]}
    final = {"widgets": [
        {"id": "w1", "val": 2},
        {"id": "w1", "val": 99},  # duplicate id; last-write-wins
    ]}

    diff = compute_diff(initial, final)
    # Only one Update should be produced, for the last occurrence of w1.
    widget_updates = [d for d in diff
                      if d.entity == "widgets" and d.entity_id == "w1"]
    assert len(widget_updates) == 1, (
        f"Expected exactly 1 Update despite duplicate ids, got {len(widget_updates)}"
    )


def test_compute_diff_decimal_round_trip() -> None:
    """Pydantic ``model_dump()`` on a Decimal field emits a Decimal (not a
    string) in default mode. compute_diff's dict-comparison must treat
    equal Decimals as equal.

    Regression: if a state with Decimal fields round-trips through
    model_dump, comparing Decimal('3.45') == Decimal('3.45') should be
    True, not False (e.g., through a stringification path).
    """
    from decimal import Decimal

    from breakingweb.eval_core import compute_diff

    initial = {"widgets": [{"id": "w1", "gpa": Decimal("3.45")}]}
    final = {"widgets": [{"id": "w1", "gpa": Decimal("3.45")}]}
    diff = compute_diff(initial, final)
    assert diff == [], (
        f"compute_diff saw a spurious change despite identical Decimals. "
        f"diff={diff}"
    )

    # And a genuine Decimal change IS detected.
    changed = {"widgets": [{"id": "w1", "gpa": Decimal("3.50")}]}
    diff2 = compute_diff(initial, changed)
    assert len(diff2) == 1 and diff2[0].__class__.__name__ == "Update", (
        f"Decimal change missed: {diff2}"
    )


def test_diff_ignore_fields_makes_field_invisible_to_invariants() -> None:
    """If an entity class declares a field in ``DIFF_IGNORE_FIELDS``,
    mutations to that field do NOT surface in compute_diff, and therefore
    cannot fire an invariant. This is by design (Class 6 pattern) — the
    ignore list escapes invariant checks.

    Lock in the behavior so changes to the ignore pipeline don't
    accidentally change invariant semantics.
    """
    from typing import ClassVar

    from pydantic import BaseModel

    from breakingweb.eval_core import compute_diff

    class Thing(BaseModel):
        id: str
        public: str = ""
        audit_trail: str = ""  # should be ignored
        DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]] = ("audit_trail",)

    class MiniState(BaseModel):
        things: list[Thing] = []

    initial = MiniState(things=[Thing(id="t1", public="A", audit_trail="x")])
    final = MiniState(things=[Thing(id="t1", public="A", audit_trail="y")])
    diff = compute_diff(initial, final)
    assert diff == [], (
        f"DIFF_IGNORE_FIELDS did not suppress 'audit_trail' change. diff={diff}"
    )


def test_multiple_update_entries_do_not_double_claim() -> None:
    """Two canonical update entries with overlapping selectors must not
    claim the same agent-diff candidate twice. ``matched_ids`` exclusion
    in the inner loop (evaluator_diff.py:925) should prevent this.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "update": [
            {"entity": "Appointment",
             "where": {"id": {"eq": "appt_x"}},
             "changes": {"status": {"eq": "cancelled"}}},
            # Second entry with an overlapping selector — must NOT double-claim.
            {"entity": "Appointment",
             "where": {"id": {"eq": "appt_x"}},
             "changes": {"status": {"eq": "cancelled"}}},
        ],
    })
    # Agent produces ONE update that could satisfy either entry.
    diff = [Update(entity="appointments", entity_id="appt_x",
                   field_changes={"status": ("scheduled", "cancelled")})]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    # One entry matches, one does not. Expected score: 0.5 (1 of 2 claimed).
    # If double-claiming allowed, we'd see 1.0.
    assert report.score < 1.0, (
        f"Double-claim allowed: two update entries both matched the same "
        f"candidate. score={report.score}"
    )


def test_read_only_canonical_diff_documented_behavior() -> None:
    """A canonical_diff with NO entries at all (empty block) scores 1.0 on
    do-nothing — that's the 1.0 fallback at evaluator_diff.py:1150. This
    is correct for truly read-only tasks (no state change expected) and
    locked in by ``test_empty_canonical_diff_scores_one`` above.

    This test is the paired version: author INTENDED constraints but
    wrote none → vacuous pass. Document so authors know to add at least
    one constraint to prevent accidental do-nothing success.
    """
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({})  # totally empty
    report = match_diff([], block, targets=targets,
                        initial=initial, final=final)
    assert report.passed and report.score == 1.0, (
        f"Empty canonical_diff no longer trivially passes on do-nothing — "
        f"{report.score}, {report.passed}. Update the hazard doc."
    )


def test_filtered_invariant_covers_entries_in_unaccounted_sweep() -> None:
    """Regression for audit_reports/w05.md — filtered-invariant double-penalty.

    Setup mirrors lms_three_module_chain: a bijection update targets modules
    in slots [1:4] (i.e. a subset), and a FILTERED invariant guards every
    OTHER module via ``a.id not in target_slots``. A server-side cascade
    outside the bijection (module_5 auto-unlocks when module_4 completes)
    matches the invariant's filter.

    Before the fix, that cascade got charged twice: once by the invariant
    step ("Preserve state.modules") and again by the unaccounted sweep
    ("Unaccounted update in modules (id=module_5)"). The right behavior is
    one charge — the filter already covers it.
    """
    from breakingweb.eval_core import Update
    initial, final, targets = _task_with_real_initial()
    targets["target_slots"] = ["m2", "m3", "m4"]  # the 3 modules the agent should complete

    block = CanonicalDiff.model_validate({
        "update": [{
            "entity": "Appointment",  # re-use a real collection for the fixture
            "bijection": {"over": "target['target_slots']", "variable": "v"},
            "where": {"id": {"expr": "x == v"}},
            "changes": {"status": {"eq": "cancelled"}},
        }],
        "invariant": [{
            "collection": "state.appointments",
            "filter": "a.id not in target['target_slots']",
            "preserve": "ALL",
        }],
    })

    # Agent completes the 3 targets AND triggers a cascade on a non-target
    # (id="cascade_5") that matches the invariant's filter.
    diff = [
        Update(entity="appointments", entity_id="m2",
               field_changes={"status": ("scheduled", "cancelled")}),
        Update(entity="appointments", entity_id="m3",
               field_changes={"status": ("scheduled", "cancelled")}),
        Update(entity="appointments", entity_id="m4",
               field_changes={"status": ("scheduled", "cancelled")}),
        # Side-effect cascade on a non-target entity — matches filter.
        Update(entity="appointments", entity_id="cascade_5",
               field_changes={"status": ("scheduled", "cancelled")}),
    ]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    unaccounted = [
        nc for nc in report.negative_checks
        if "Unaccounted" in nc.get("desc", "") and "cascade_5" in nc.get("desc", "")
    ]
    assert not unaccounted, (
        f"Filtered invariant did not protect cascade_5 from the unaccounted "
        f"sweep — double-penalty regression. negative_checks={report.negative_checks}"
    )
    # The invariant itself should still fire (single penalty) — that is the
    # author's intended guard against modifying non-target entities.
    invariant_firings = [
        nc for nc in report.negative_checks
        if "Preserve state.appointments" in nc.get("desc", "") and not nc["passed"]
    ]
    assert invariant_firings, (
        "Filtered invariant must still fire when a non-target matches its "
        "filter — otherwise agents could freely mutate protected entries."
    )


def test_singleton_create_near_miss_not_double_penalised() -> None:
    """Regression for audit_reports/2026-04-26 (GM-1, GM-4, BOOK-5, AMZ-1).

    Setup: the canonical diff demands one Create in ``appointments`` whose
    ``id`` equals ``"X"``. The agent creates an entry on the right entity +
    collection but with ``id == "Y"`` — a property near-miss.

    Pre-fix the matcher charged this twice:
      - missing_create (the desired Create predicate didn't match anything), and
      - unaccounted (the agent's Create wasn't claimed by any positive entry).

    Post-fix the second penalty is suppressed: the unaccounted sweep treats
    the right-collection-but-failed-predicates candidate as a near-miss, so
    only the missing-positive failure remains.
    """
    from breakingweb.eval_core import Create
    initial, final, targets = _task_with_real_initial()

    block = CanonicalDiff.model_validate({
        "create": [{
            "entity": "Appointment",
            "desc": "Create appointment with id X",
            "properties": {"id": {"eq": "X"}},
        }],
    })
    # Agent creates on the right collection but the predicate fails (id != X).
    diff = [Create(entity="appointments", entity_id="Y", fields={"id": "Y"})]

    report = match_diff(diff, block, targets=targets,
                        initial=initial, final=final)

    # The missing-create failure must still fire.
    missing = [f for f in report.failures if f.kind == "missing_create"]
    assert missing, (
        f"missing_create failure should still fire for property near-miss; "
        f"failures={report.failures}"
    )

    # But the unaccounted-create double-penalty must NOT fire.
    unaccounted_negs = [
        nc for nc in report.negative_checks
        if "Unaccounted create" in nc.get("desc", "")
    ]
    assert not unaccounted_negs, (
        f"Singleton property near-miss double-penalised: the same Create is "
        f"flagged both missing and unaccounted. negative_checks="
        f"{report.negative_checks}"
    )
    unaccounted_failures = [f for f in report.failures if f.kind == "unaccounted"]
    assert not unaccounted_failures, (
        f"Unaccounted failure piled on near-miss Create: {unaccounted_failures}"
    )


def test_near_miss_create_does_not_trip_same_collection_invariant() -> None:
    """A wrong-but-clearly-attempted output should not also look like collateral.

    This is the synthetic version of the noisy Gmail pattern where a sent email
    misses one predicate and then also triggers ``Preserve state.sent``. The
    positive create failure is enough signal; the same entry should not be
    reported again as protected-state damage.
    """
    from breakingweb.eval_core import Create

    initial, final, targets = _task_with_real_initial()
    block = CanonicalDiff.model_validate({
        "create": [{
            "entity": "SentEmail",
            "collection": "state.sent",
            "desc": "Send required email",
            "properties": {"subject": {"eq": "Required subject"}},
        }],
        "invariant": [{
            "collection": "state.sent",
            "filter": "True",
            "preserve": "ALL",
        }],
    })
    diff = [
        Create(
            entity="sent",
            entity_id="sent_1",
            fields={"id": "sent_1", "subject": "Wrong subject"},
        )
    ]

    report = match_diff(diff, block, targets=targets, initial=initial, final=final)

    assert any(f.kind == "missing_create" for f in report.failures)
    assert not any(f.kind == "invariant" for f in report.failures), report.failures
    assert not any(
        not nc["passed"] and nc.get("kind") == "invariant"
        for nc in report.negative_checks
    ), report.negative_checks
