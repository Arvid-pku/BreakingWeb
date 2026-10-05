"""Solvability proof for the hardened (v2) lms_course_load_analysis task.

The upgraded task no longer spells out the closed-form projection formula or the
2.0 grade-point mapping. The agent must DERIVE the credit-weighted GPA rule and,
critically, sum credit hours over ONLY the actively-enrolled courses. The seed now
plants a WAITLISTED decoy course (status != enrolled) with real credit hours: an
agent that counts it inflates the current credit total and flips the safe/not-safe
branch. The authoritative ``can_add_course`` / ``lowest_performing_course_id`` are
computed enrolled-scoped in grade_book (enrolled_scoped_decision=true), so:

  * projected GPA >= 3.0 (enrolled credits)  -> mark every unread announcement read
  * projected GPA <  3.0 (enrolled credits)  -> drop the lowest-weighted enrolled
                                                course

With the current seed config (must_include MATH201+PHYS201+CS101, count=5,
include_waitlisted), the enrolled credit total is pinned near the 3.0 boundary:

  * seed=0 -> 14 enrolled credits -> projected 2.99 (< 3.0) -> Branch 2 (drop). The
    NAIVE all-courses total (incl. the waitlisted decoy) is 17, which would project
    >= 3.0 and wrongly choose Branch 1 -- this is the load-bearing trap.
  * seed=1 -> 15 enrolled credits -> projected 3.00 (>= 3.0) -> Branch 1 (mark read).

Both branches are driven through the REAL LMS backend endpoints
(POST /courses/{id}/drop and POST /announcements/mark_all_read) to confirm the
intended answer is reachable past the server gates.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.models.lms import Enrollment
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

DROP_SEED = 0  # enrolled credits 14 -> projected 2.99 -> Branch 2 (drop)
SAFE_SEED = 1  # enrolled credits 15 -> projected 3.00 -> Branch 1 (mark read)


def _session(seed: int):
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="lms", task_id="lms_course_load_analysis", seed=seed,
    )
    return sm, sid, dict(targets)


def _evaluate(sm, sid, targets):
    task = get_task("lms_course_load_analysis")
    return evaluate(
        task=task,
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )


def test_seed_invariants_hold():
    """The seed reliably produces the credit-scope trap on the drop branch."""
    sm, sid, targets = _session(DROP_SEED)
    state = sm.get_state(sid)
    enrolled = [e for e in state.enrollments if e.status == "enrolled"]
    waitlisted = [e for e in state.enrollments if e.status == "waitlisted"]
    # 4 enrolled + exactly one waitlisted decoy course.
    assert len(enrolled) == 4, [e.status for e in state.enrollments]
    assert len(waitlisted) == 1
    # Enrolled credit total < all-courses total: counting the decoy flips the branch.
    assert int(targets["current_total_credits"]) < int(targets["all_courses_total_credits"])
    assert targets["can_add_course"] == "false"
    # The lowest-performing course is an enrolled course, never the waitlisted decoy.
    waitlisted_cids = {e.course_id for e in waitlisted}
    assert targets["lowest_performing_course_id"] not in waitlisted_cids


def test_drop_branch_correct_solution_passes():
    """seed=0 -> projected GPA < 3.0 (enrolled-scoped) -> drop lowest enrolled course."""
    sm, sid, targets = _session(DROP_SEED)
    assert targets["can_add_course"] == "false"

    client = TestClient(app)
    cid = targets["lowest_performing_course_id"]
    resp = client.post(f"/api/env/lms/courses/{cid}/drop", json={"session_id": sid})
    assert resp.status_code == 200, resp.text
    assert resp.json().get("dropped") is True

    result = _evaluate(sm, sid, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99
    # Hardened task has a thick wall of negative coverage.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_mark_read_branch_correct_solution_passes():
    """seed=1 -> projected GPA >= 3.0 (enrolled-scoped) -> mark all unread read."""
    sm, sid, targets = _session(SAFE_SEED)
    assert targets["can_add_course"] == "true"

    client = TestClient(app)
    resp = client.post(
        "/api/env/lms/announcements/mark_all_read", json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sm, sid, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99


def test_credit_scope_trap_wrong_branch_fails():
    """The load-bearing trap: counting the waitlisted decoy in the credit total makes
    an agent project GPA >= 3.0 and take the SAFE branch on a drop seed. Marking
    announcements read (the safe action) must fail."""
    sm, sid, targets = _session(DROP_SEED)
    client = TestClient(app)
    resp = client.post(
        "/api/env/lms/announcements/mark_all_read", json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sm, sid, targets)
    assert result.get("success") is False, f"result: {result}"


def test_wrong_drop_target_fails():
    """Dropping an enrolled course other than the lowest-weighted-grade course fails."""
    sm, sid, targets = _session(DROP_SEED)
    client = TestClient(app)
    state = sm.get_state(sid)
    target_cid = targets["lowest_performing_course_id"]
    wrong_cid = next(
        e.course_id
        for e in state.enrollments
        if e.course_id != target_cid and e.status == "enrolled"
    )
    resp = client.post(
        f"/api/env/lms/courses/{wrong_cid}/drop", json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sm, sid, targets)
    assert result.get("success") is False, f"result: {result}"


def test_dropping_waitlisted_decoy_fails():
    """An agent confused about which courses 'count' might drop the waitlisted decoy.
    The drop endpoint 422s on a non-enrolled course, so simulate the bad post-state
    directly: a dropped waitlisted enrollment must fail (it is not the answer and the
    real drop target was never touched)."""
    sm, sid, targets = _session(DROP_SEED)
    state = sm.get_state(sid)
    decoy = next(e for e in state.enrollments if e.status == "waitlisted")
    decoy.status = "dropped"

    result = _evaluate(sm, sid, targets)
    assert result.get("success") is False, f"result: {result}"


def test_collateral_new_enrollment_fails():
    """Correct drop plus a stray new enrollment trips the critical no-new-course constraint."""
    sm, sid, targets = _session(DROP_SEED)
    client = TestClient(app)
    client.post(
        f"/api/env/lms/courses/{targets['lowest_performing_course_id']}/drop",
        json={"session_id": sid},
    )
    state = sm.get_state(sid)
    # Mirror the create_enrollment route (a tempting wrong action) by appending a
    # brand-new enrollment row. The no-new-course constraint must reject this.
    state.enrollments.append(
        Enrollment(
            id="enrollment_collateral",
            student_id=state.student.id,
            course_id="course_2",
            role="student",
            status="enrolled",
        )
    )

    result = _evaluate(sm, sid, targets)
    assert result.get("success") is False, f"result: {result}"


def test_noop_fails():
    """Doing nothing fails both branches."""
    sm, sid, targets = _session(DROP_SEED)
    result = _evaluate(sm, sid, targets)
    assert result.get("success") is False, f"result: {result}"
