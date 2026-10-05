"""Solvability proof for the v2-upgraded lms_review_rubric_submit task.

The v2 hardening DECOUPLES the decision from the displayed points column:
every unsubmitted assignment in the target course shows the SAME
points_possible, but their rubrics sum to DIFFERENT totals and have
DIFFERENT criteria counts. The agent must open and SUM each rubric to find
the winner (highest rubric total), break a 3-way total tie by earliest due
then alphabetical title, and name the file with the winner's rubric-criteria
count. This proves:

  * the correct trajectory (submit the rubric-total argmax winner with the
    winner's rubric-criteria-count file) still scores 1.0 / success;
  * a wrong file_name count fails (the count is load-bearing);
  * submitting the same-course equal-points look-alike (lower rubric total)
    fails — points are NOT a usable discriminator;
  * submitting the runner-up that ties on rubric total but loses the
    tie-break fails (and its different criteria count is the wrong N);
  * the cross-course decoy submission fails.
"""

from __future__ import annotations

from decimal import Decimal

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "lms_review_rubric_submit"


def _make_session(seed: int = 42):
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=seed)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), state


def _correct_file_name(targets: dict) -> str:
    return f"rubric_review_{targets['highest_points_rubric_count']}.pdf"


def _rubric_total(assignment) -> Decimal:
    return sum(
        (Decimal(str(r.max_points)) for r in assignment.rubric),
        Decimal("0"),
    )


def _target_course_id(state, targets) -> str:
    for c in state.courses:
        if c.course_code == targets["course_code"]:
            return c.id
    raise AssertionError("target course not found")


def _evaluate(state, targets):
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )


def test_decision_is_decoupled_from_points_column():
    """Sanity: every unsubmitted target-course assignment shows the SAME
    points, but rubric totals differ — so the points column cannot pick the
    winner, and the winner is the rubric-total argmax (with tie-break)."""
    sm, sid, targets, state = _make_session(seed=42)
    tcid = _target_course_id(state, targets)
    unsubmitted = [
        a for a in state.assignments
        if a.course_id == tcid and a.submission_status == "not_submitted"
    ]
    assert len(unsubmitted) >= 3, "expected a multi-assignment selection problem"

    # The displayed points column is uninformative (a single distinct value).
    distinct_points = {str(a.points_possible) for a in unsubmitted}
    assert len(distinct_points) == 1, f"points should tie, got {distinct_points}"

    # Rubric totals genuinely differ (so summing rubrics is load-bearing).
    totals = sorted({_rubric_total(a) for a in unsubmitted})
    assert len(totals) >= 2, f"rubric totals should differ, got {totals}"

    # The winner is the argmax-by-rubric-total, tie-broken earliest-due then title.
    winner = state.get_assignment(targets["highest_points_unsubmitted_id"])
    assert winner is not None and winner.submission_status == "not_submitted"
    max_total = max(_rubric_total(a) for a in unsubmitted)
    assert _rubric_total(winner) == max_total, "winner must hold the max rubric total"
    tied_top = sorted(
        (a for a in unsubmitted if _rubric_total(a) == max_total),
        key=lambda a: (str(a.due_at), a.title),
    )
    assert tied_top[0].id == winner.id, "winner must survive the due/alpha tie-break"
    # At least one OTHER assignment ties on rubric total → tie-break really fires.
    assert len(tied_top) >= 2, "expected a real rubric-total tie at the top"

    # The encoded N equals the winner's actual criteria count.
    assert str(len(winner.rubric)) == targets["highest_points_rubric_count"]
    # And the runner-up's criteria count differs (wrong winner ⇒ wrong N).
    assert len(tied_top[1].rubric) != len(winner.rubric)


def test_correct_trajectory_via_backend_passes():
    """Submitting the rubric-total winner via the real endpoint with the
    rubric-count-named file passes evaluate()."""
    sm, sid, targets, state = _make_session(seed=42)
    client = TestClient(app)

    target_id = targets["highest_points_unsubmitted_id"]
    assert target_id, "seed did not produce a target assignment"
    file_name = _correct_file_name(targets)

    before = state.get_assignment(target_id)
    assert before is not None and before.submission_status == "not_submitted"
    course = state.get_course(before.course_id)
    assert course is not None and course.course_code == targets["course_code"]

    resp = client.post(
        f"/api/env/lms/assignments/{target_id}/submit",
        json={"session_id": sid, "file_name": file_name},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = _evaluate(state, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_wrong_file_name_count_fails():
    """Submitting the right assignment but with the wrong rubric-count file fails."""
    sm, sid, targets, state = _make_session(seed=42)
    client = TestClient(app)

    target_id = targets["highest_points_unsubmitted_id"]
    correct = int(targets["highest_points_rubric_count"])
    wrong_file = f"rubric_review_{correct + 1}.pdf"

    resp = client.post(
        f"/api/env/lms/assignments/{target_id}/submit",
        json={"session_id": sid, "file_name": wrong_file},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = _evaluate(state, targets)
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_same_course_lower_rubric_total_lookalike_fails():
    """Submitting the same-course equal-points look-alike (lower rubric total)
    fails: the true winner stays unsubmitted (update unsatisfied) and the
    same-course decoy critical constraint is violated. Points alone do not
    discriminate it from the winner."""
    sm, sid, targets, state = _make_session(seed=42)
    client = TestClient(app)

    decoy_id = targets["rubric_review_same_course_decoy_id"]
    assert decoy_id, "seed did not produce a same-course decoy at seed=42"
    winner = state.get_assignment(targets["highest_points_unsubmitted_id"])
    decoy = state.get_assignment(decoy_id)
    # Same displayed points, strictly lower rubric total — the trap.
    assert decoy.points_possible == winner.points_possible
    assert _rubric_total(decoy) < _rubric_total(winner)

    resp = client.post(
        f"/api/env/lms/assignments/{decoy_id}/submit",
        json={"session_id": sid, "file_name": _correct_file_name(targets)},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = _evaluate(state, targets)
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_tie_break_loser_fails():
    """Submitting the runner-up that ties on rubric total but loses the
    earliest-due/alphabetical tie-break fails (wrong assignment AND wrong N)."""
    sm, sid, targets, state = _make_session(seed=42)
    client = TestClient(app)

    tcid = _target_course_id(state, targets)
    unsubmitted = [
        a for a in state.assignments
        if a.course_id == tcid and a.submission_status == "not_submitted"
    ]
    max_total = max(_rubric_total(a) for a in unsubmitted)
    tied_top = sorted(
        (a for a in unsubmitted if _rubric_total(a) == max_total),
        key=lambda a: (str(a.due_at), a.title),
    )
    loser = tied_top[1]
    assert loser.id != targets["highest_points_unsubmitted_id"]

    # Submit the loser with ITS OWN criteria count (a plausible wrong path).
    resp = client.post(
        f"/api/env/lms/assignments/{loser.id}/submit",
        json={"session_id": sid, "file_name": f"rubric_review_{len(loser.rubric)}.pdf"},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = _evaluate(state, targets)
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_wrong_cross_course_assignment_fails():
    """Submitting a different (cross-course) decoy assignment fails."""
    sm, sid, targets, state = _make_session(seed=42)
    client = TestClient(app)

    decoy_id = targets["rubric_review_decoy_id"]
    assert decoy_id, "seed did not produce a cross-course decoy"

    resp = client.post(
        f"/api/env/lms/assignments/{decoy_id}/submit",
        json={"session_id": sid, "file_name": _correct_file_name(targets)},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = _evaluate(state, targets)
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_correct_trajectory_multiple_seeds():
    """The correct strategy passes across several seeds (robustness)."""
    for seed in (7, 123, 999, 2024, 17, 88, 1001, 5, 9):
        sm, sid, targets, state = _make_session(seed=seed)
        client = TestClient(app)
        target_id = targets["highest_points_unsubmitted_id"]
        file_name = _correct_file_name(targets)
        resp = client.post(
            f"/api/env/lms/assignments/{target_id}/submit",
            json={"session_id": sid, "file_name": file_name},
        )
        assert resp.status_code == 200, resp.text
        state = sm.get_state(sid)
        result = _evaluate(state, targets)
        assert result.get("success") is True, f"seed={seed} result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"seed={seed} score: {result}"
