"""Solvability proof for the v2 (expert-tier) lms_resubmit_flagged task.

The v2 base adds GENUINE backtracking + verification load on top of the v1
per-row filename arithmetic:

- 4 resubmittable flagged assignments, each with a distinct prior attempt_count,
  all resubmittable past the real backend gates (attempt_count < max_attempts).
- 1 BLOCKED flagged assignment (submission_status still "resubmit_requested" but
  attempt_count == max_attempts) so BOTH the /resubmit and /submit endpoints
  return 422. The agent must discover the 422 blocker mid-task, abandon that row,
  and NOT count it -- it is EXCLUDED from resubmit_assignment_ids.
- 1 GRADED look-alike sharing a flagged assignment's title in a different course
  (the /submit endpoint accepts "graded", so it looks resubmittable). The agent
  must match submission_status == "resubmit_requested" exactly, not the title.

Confirms:
- Driving the CORRECT solution (resubmit exactly the 4 resubmittable rows with the
  per-assignment derived filename revision_v{attempt_count+1}.pdf) via the REAL
  resubmit endpoint evaluates to success and score >= 0.99.
- The blocked row is genuinely un-resubmittable (422 on both endpoints) and leaving
  it untouched is correct; forcing a change on it fails the critical guard.
- Near-misses fail: uniform filename, skipping a flagged row, and touching the
  graded title look-alike.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from breakingweb.backend.routes.lms import (
    ResubmitAssignmentRequest,
    SubmitAssignmentRequest,
    resubmit_assignment,
    submit_assignment,
)
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "lms_resubmit_flagged"


def _new_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=seed)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), state


def _expected_filename(state, assignment_id: str) -> str:
    """Per-row filename: revision_v{current attempt_count + 1}.pdf."""
    a = state.get_assignment(assignment_id)
    return f"revision_v{a.attempt_count + 1}.pdf"


def _resubmit_all_correct(sm, sid, targets, state) -> None:
    for aid in targets["resubmit_assignment_ids"].split(","):
        resubmit_assignment(
            assignment_id=aid,
            body=ResubmitAssignmentRequest(session_id=sid, file_name=_expected_filename(state, aid)),
            session_manager=sm,
        )


def _evaluate(sm, sid, targets, state) -> dict:
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )


@pytest.mark.parametrize("seed", [42, 7, 123])
def test_seed_is_well_formed(seed):
    """4 distinct resubmittable flagged rows + 1 blocked row + 1 look-alike decoy."""
    sm, sid, targets, state = _new_session(seed)
    try:
        rs = targets["resubmit_assignment_ids"].split(",")
        assert len(rs) == 4, f"expected 4 resubmittable flagged assignments, got {rs}"

        attempts = set()
        for aid in rs:
            a = state.get_assignment(aid)
            assert a is not None
            assert a.submission_status == "resubmit_requested"
            assert a.attempt_count < a.max_attempts, "resubmittable row must have a remaining attempt"
            assert a.feedback, "flagged assignment must carry feedback to read"
            attempts.add(a.attempt_count)
        # Varied prior attempt counts force per-row filename re-derivation.
        assert len(attempts) >= 2, f"attempt counts not varied: {attempts}"

        # resubmit_filenames target agrees with per-row derivation.
        fns = dict(p.split(":") for p in targets["resubmit_filenames"].split(","))
        for aid in rs:
            assert fns[aid] == _expected_filename(state, aid)

        # Blocked row: flagged-looking but un-resubmittable, and EXCLUDED from rs.
        bid = targets["blocked_resubmit_assignment_id"]
        assert bid, "expected a blocked flagged assignment"
        assert bid not in rs, "blocked row must not be in the resubmittable set"
        blocked = state.get_assignment(bid)
        assert blocked.submission_status == "resubmit_requested"
        assert blocked.attempt_count == blocked.max_attempts, "blocked row must have no attempts left"

        # Look-alike decoy: graded, shares a flagged title, in a different course.
        lk = targets["lookalike_decoy_assignment_id"]
        assert lk, "expected a graded look-alike decoy"
        look = state.get_assignment(lk)
        assert look.submission_status == "graded"
        flagged_titles = {state.get_assignment(aid).title for aid in rs}
        assert look.title in flagged_titles, "look-alike must share a flagged assignment's title"
        assert look.course_id != state.get_assignment(rs[0]).course_id
    finally:
        sm.destroy(sid)


def test_correct_trajectory_via_real_endpoint_passes():
    """Resubmitting exactly the 4 resubmittable flagged rows via the real handler passes."""
    sm, sid, targets, state = _new_session()
    try:
        _resubmit_all_correct(sm, sid, targets, state)
        result = _evaluate(sm, sid, targets, state)
        assert result.get("success") is True, f"result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
        # Richer than a 2-check eval (bijection + many invariants + constraints).
        assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2
    finally:
        sm.destroy(sid)


def test_blocked_row_is_unresubmittable_and_leaving_it_untouched_is_correct():
    """The blocked flagged row 422s on BOTH endpoints; leaving it alone is correct."""
    sm, sid, targets, state = _new_session()
    try:
        bid = targets["blocked_resubmit_assignment_id"]

        # /resubmit on the blocked row must 422 (max attempts reached).
        with pytest.raises(HTTPException) as exc_resub:
            resubmit_assignment(
                assignment_id=bid,
                body=ResubmitAssignmentRequest(session_id=sid, file_name="revision_v3.pdf"),
                session_manager=sm,
            )
        assert exc_resub.value.status_code == 422

        # /submit on the blocked row must also 422 (same attempt guard).
        with pytest.raises(HTTPException) as exc_sub:
            submit_assignment(
                assignment_id=bid,
                body=SubmitAssignmentRequest(session_id=sid, file_name="revision_v3.pdf"),
                session_manager=sm,
            )
        assert exc_sub.value.status_code == 422

        # The fair completion (resubmit only the 4 resubmittable rows, leave the
        # blocked row untouched) passes.
        _resubmit_all_correct(sm, sid, targets, state)
        result = _evaluate(sm, sid, targets, state)
        assert result.get("success") is True, f"result: {result}"
        assert result.get("score", 0.0) >= 0.99
    finally:
        sm.destroy(sid)


def test_forcing_a_change_on_the_blocked_row_fails_the_critical_guard():
    """The blocked-row guard is non-vacuous: a forced mutation flips the eval to fail."""
    sm, sid, targets, state = _new_session()
    try:
        _resubmit_all_correct(sm, sid, targets, state)
        # Simulate an agent that ignored the 422 and forced the row "done".
        blocked = state.get_assignment(targets["blocked_resubmit_assignment_id"])
        blocked.submission_status = "submitted"
        blocked.attempt_count += 1
        result = _evaluate(sm, sid, targets, state)
        assert result.get("success") is False, f"should fail, got: {result}"
    finally:
        sm.destroy(sid)


def test_touching_the_graded_lookalike_fails():
    """Resubmitting the graded title look-alike (wrong row) fails the critical guard."""
    sm, sid, targets, state = _new_session()
    try:
        _resubmit_all_correct(sm, sid, targets, state)
        # The /submit endpoint accepts "graded" -> the agent that matched on title
        # rather than submission_status mutates the look-alike.
        submit_assignment(
            assignment_id=targets["lookalike_decoy_assignment_id"],
            body=SubmitAssignmentRequest(session_id=sid, file_name="revision_v2.pdf"),
            session_manager=sm,
        )
        result = _evaluate(sm, sid, targets, state)
        assert result.get("success") is False, f"should fail, got: {result}"
    finally:
        sm.destroy(sid)


def test_uniform_filename_near_miss_fails():
    """Using one literal filename for all (ignoring per-row attempt) fails."""
    sm, sid, targets, state = _new_session()
    try:
        for aid in targets["resubmit_assignment_ids"].split(","):
            # Naive agent reuses "revision_v2.pdf" for every assignment, which is
            # wrong for any assignment whose prior attempt_count != 1.
            resubmit_assignment(
                assignment_id=aid,
                body=ResubmitAssignmentRequest(session_id=sid, file_name="revision_v2.pdf"),
                session_manager=sm,
            )
        result = _evaluate(sm, sid, targets, state)
        assert result.get("success") is False, f"should fail, got: {result}"
    finally:
        sm.destroy(sid)


def test_skipping_one_flagged_assignment_fails():
    """Missing one resubmittable flagged assignment (incomplete saturation) fails."""
    sm, sid, targets, state = _new_session()
    try:
        rs = targets["resubmit_assignment_ids"].split(",")
        for aid in rs[:-1]:  # skip the last resubmittable flagged assignment
            resubmit_assignment(
                assignment_id=aid,
                body=ResubmitAssignmentRequest(session_id=sid, file_name=_expected_filename(state, aid)),
                session_manager=sm,
            )
        result = _evaluate(sm, sid, targets, state)
        assert result.get("success") is False, f"should fail, got: {result}"
    finally:
        sm.destroy(sid)
