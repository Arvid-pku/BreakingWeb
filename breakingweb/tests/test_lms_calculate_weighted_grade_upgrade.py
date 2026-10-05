"""Solvability proof for the hardened (v2) lms_calculate_weighted_grade task.

Drives the CORRECT solution through the REAL LMS backend endpoints (Starlette
TestClient over the full ASGI app) and confirms the canonical_diff evaluator
passes; then drives wrong / near-miss trajectories and confirms they fail.

The hardened task is a 2-branch oneof gated on `has_discrepancy`:
  * Branch 1 (a course has a >1pt discrepancy): resubmit the single most
    recently graded assignment (`most_recent_graded_id`, the globally latest-due
    graded assignment) with grade_dispute.pdf.
  * Branch 2 (no discrepancy): mark the latest announcement in the target
    course as read.

v2 levers exercised here:
  * 5 courses x 12 assignments (60-row haystack) with vary_late_policies and
    late_within_grace so the displayed weighted grade diverges from a naive
    raw recompute (LMS-8). The branch flag must be re-derived correctly.
  * The branch-1 positive update re-derives the globally latest-due graded
    assignment inside the where-clause, so resubmitting a plausible look-alike
    (a graded assignment that is NOT the global max-due) fails.
  * Critical-severity invariants: exactly-one-resubmit, the resubmit is the
    latest-due one, no announcement touched on branch 1, no grade tampering.

seed=0 / seed=42 exercise Branch 1; seed=8 / seed=27 exercise Branch 2.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.backend.state import SessionManager
from breakingweb.runner import ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_calculate_weighted_grade"

# Seeds that deterministically exercise each oneof branch under the v2 seed
# config (5 courses x 12 assignments, vary_late_policies, late_count=2).
BRANCH1_SEED = 0   # has_discrepancy == 'true'
BRANCH2_SEED = 8   # has_discrepancy == 'false'


def _client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {CONTROLLER_SECRET_HEADER: app.state.controller_secret}


def _create(client: TestClient, seed: int) -> tuple[str, dict]:
    resp = client.post(
        f"/api/env/lms/session",
        json={"task_id": TASK_ID, "seed": seed},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["session_id"], body["resolved_targets"]


def _evaluate_endpoint(client: TestClient, session_id: str) -> dict:
    resp = client.post(
        "/api/env/lms/evaluate",
        json={"session_id": session_id, "task_id": TASK_ID, "trajectory": []},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Branch 1 (has_discrepancy == 'true') — resubmit the latest-due graded one
# ---------------------------------------------------------------------------

def test_branch1_correct_resubmit_passes_via_real_endpoint():
    """seed=0 has a discrepancy; resubmitting most_recent_graded_id passes.

    Method: REAL backend endpoint POST /assignments/{id}/submit (the submit
    route accepts a 'graded'/'late' assignment with remaining attempts and bumps
    attempt_count, setting submission_status to submitted/late and file_name).
    """
    client = _client()
    sid, targets = _create(client, seed=BRANCH1_SEED)
    assert targets["has_discrepancy"] == "true"

    mr_id = targets["most_recent_graded_id"]
    resp = client.post(
        f"/api/env/lms/assignments/{mr_id}/submit",
        json={"session_id": sid, "file_name": "grade_dispute.pdf"},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["assignment"]["file_name"] == "grade_dispute.pdf"

    result = _evaluate_endpoint(client, sid)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    # richer than legacy 2-check eval
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_branch1_correct_passes_via_evaluate_function():
    """Same Branch-1 outcome (seed=42), asserted through the unified evaluate()."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=42)
    state = sm.get_state(sid)
    assert dict(targets)["has_discrepancy"] == "true"

    mr_id = dict(targets)["most_recent_graded_id"]
    a = state.get_assignment(mr_id)
    # Mirror the submit endpoint's effect on the assignment record.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    a.attempt_count += 1
    a.file_name = "grade_dispute.pdf"
    a.submitted_at = now
    a.submission_status = "late" if now > a.due_at else "submitted"

    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99


def test_branch1_due_date_tie_resolves_to_lowest_id():
    """Regression: when two graded assignments tie on the (globally latest) due
    date, the instruction's tie-break ("the one with the lowest assignment id")
    must equal the seed's pinned most_recent_graded_id, and resubmitting it passes.

    Without the tie-break a correct agent could resubmit the other equally-valid
    tied assignment and be mis-graded. ~2.3% of branch-1 seeds carry such a tie
    (e.g. 90, 163, 172)."""
    from datetime import datetime, timezone

    for seed in (90, 163, 172):
        sm = SessionManager()
        sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=seed)
        state = sm.get_state(sid)
        t = dict(targets)
        assert t["has_discrepancy"] == "true", f"seed {seed} expected branch 1"

        assignments = {a.id: a for a in state.assignments}
        graded: list[tuple[str, object]] = []
        for g in state.grades:
            if getattr(g, "score", None) is None:
                continue
            a = assignments.get(g.assignment_id)
            if a is not None:
                graded.append((a.id, a.due_at))
        assert graded, f"seed {seed} has no graded assignments"

        max_due = max(d for _, d in graded)
        tied = sorted(
            (aid for aid, d in graded if d == max_due),
            key=lambda i: int(i.rsplit("_", 1)[-1]),
        )
        assert len(tied) >= 2, f"seed {seed} expected a due-date tie, got {tied}"
        # The instruction's lowest-id tie-break must match the seed's pinned answer.
        assert t["most_recent_graded_id"] == tied[0], (
            f"seed {seed}: pinned {t['most_recent_graded_id']} != lowest tied id {tied[0]}"
        )

        # Resubmitting the pinned (lowest-id) tied assignment grades as correct.
        a = state.get_assignment(t["most_recent_graded_id"])
        now = datetime.now(timezone.utc)
        a.attempt_count += 1
        a.file_name = "grade_dispute.pdf"
        a.submitted_at = now
        a.submission_status = "late" if now > a.due_at else "submitted"
        result = evaluate(task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[])
        assert result.get("success") is True, f"seed {seed}: {result}"
        assert result.get("score", 0.0) >= 0.99, f"seed {seed}: {result.get('score')}"

def test_branch2_correct_mark_read_passes_via_real_endpoint():
    """seed=8 has no discrepancy; marking the latest announcement read passes."""
    client = _client()
    sid, targets = _create(client, seed=BRANCH2_SEED)
    assert targets["has_discrepancy"] == "false"

    ann_id = targets["latest_announcement_id"]
    resp = client.post(
        f"/api/env/lms/announcements/{ann_id}/read",
        json={"session_id": sid},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["announcement"]["is_read"] is True

    result = _evaluate_endpoint(client, sid)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99


# ---------------------------------------------------------------------------
# Wrong / near-miss trajectories — must FAIL
# ---------------------------------------------------------------------------

def test_wrong_branch_on_discrepancy_fails():
    """seed=0 HAS a discrepancy, but agent takes the no-discrepancy action
    (marks announcement read instead of resubmitting). Neither branch matches:
    branch 1's positive update is unsatisfied, branch 2's where-clause requires
    has_discrepancy == 'false'. Must fail."""
    client = _client()
    sid, targets = _create(client, seed=BRANCH1_SEED)
    assert targets["has_discrepancy"] == "true"

    ann_id = targets["latest_announcement_id"]
    resp = client.post(
        f"/api/env/lms/announcements/{ann_id}/read",
        json={"session_id": sid},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate_endpoint(client, sid)
    assert result.get("success") is False, f"result: {result}"


def test_wrong_assignment_resubmit_fails():
    """seed=0: resubmit a DIFFERENT graded assignment (not most_recent_graded_id).
    Branch 1's positive update is unsatisfied (where-clause re-derives the global
    latest-due target), the latest-due constraint fires, and the collateral
    invariant on other assignments fires. Must fail."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=BRANCH1_SEED)
    state = sm.get_state(sid)
    t = dict(targets)
    assert t["has_discrepancy"] == "true"
    mr_id = t["most_recent_graded_id"]

    # Find a graded, resubmittable assignment that is NOT the most_recent one.
    wrong = next(
        a for a in state.assignments
        if a.id != mr_id and a.submission_status == "graded"
        and a.attempt_count < a.max_attempts
    )
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    wrong.attempt_count += 1
    wrong.file_name = "grade_dispute.pdf"
    wrong.submitted_at = now
    wrong.submission_status = "late" if now > wrong.due_at else "submitted"

    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"


def test_resubmit_correct_plus_lookalike_fails():
    """seed=0: agent resubmits the correct latest-due assignment BUT also
    resubmits a second graded look-alike (over-action). The exactly-one-resubmit
    and latest-due-only critical constraints fire. Must fail."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=BRANCH1_SEED)
    state = sm.get_state(sid)
    t = dict(targets)
    mr_id = t["most_recent_graded_id"]

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    a = state.get_assignment(mr_id)
    a.attempt_count += 1
    a.file_name = "grade_dispute.pdf"
    a.submitted_at = now
    a.submission_status = "late" if now > a.due_at else "submitted"

    # Over-action: also resubmit a second graded assignment.
    extra = next(
        x for x in state.assignments
        if x.id != mr_id and x.submission_status == "graded"
        and x.attempt_count < x.max_attempts
    )
    extra.attempt_count += 1
    extra.file_name = "grade_dispute.pdf"
    extra.submitted_at = now
    extra.submission_status = "late" if now > extra.due_at else "submitted"

    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"


def test_grade_tampering_fails_even_with_correct_resubmit():
    """seed=0: agent resubmits the correct assignment BUT also mutates a grade
    record (critical-severity invariant on state.grades). Must fail."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=BRANCH1_SEED)
    state = sm.get_state(sid)
    t = dict(targets)
    mr_id = t["most_recent_graded_id"]

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    a = state.get_assignment(mr_id)
    a.attempt_count += 1
    a.file_name = "grade_dispute.pdf"
    a.submitted_at = now
    a.submission_status = "late" if now > a.due_at else "submitted"

    # Tamper with a grade record (forbidden, critical invariant).
    from decimal import Decimal
    assert state.grades, "expected seeded grades"
    state.grades[0].score = (Decimal(str(state.grades[0].score)) + Decimal("5"))

    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"


def test_branch2_wrong_resubmit_fails():
    """seed=8 has NO discrepancy; agent wrongly resubmits an assignment instead
    of marking the announcement read. Branch 2's no-resubmit critical constraint
    fires and branch 1's where-clause requires has_discrepancy=='true'. Fail."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=BRANCH2_SEED)
    state = sm.get_state(sid)
    t = dict(targets)
    assert t["has_discrepancy"] == "false"
    mr_id = t["most_recent_graded_id"]

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    a = state.get_assignment(mr_id)
    a.attempt_count += 1
    a.file_name = "grade_dispute.pdf"
    a.submitted_at = now
    a.submission_status = "late" if now > a.due_at else "submitted"

    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"
