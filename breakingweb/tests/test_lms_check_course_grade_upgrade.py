"""Solvability proof for the upgraded (medium) lms_check_course_grade task.

Drives the CORRECT solution through the REAL LMS backend mutation endpoints
(submit / mark-announcement-read) via Starlette TestClient, then evaluates via
the unified evaluator. Also proves that wrong / near-miss trajectories fail.

Branch 1 (grade below 80%): submit the EARLIEST-due unsubmitted homework with
catch_up.pdf in the target course. Seed 42 lands here.
Branch 2 (grade >= 80%): mark EVERY unread announcement in the target course as
read (bijection). Seed 40 lands here with a real, non-vacuous weighted grade
computed from actual graded work (>=80).

V2 base hardening verified here:
  * unsubmitted_hw_id is the EARLIEST-due unsubmitted homework in the target
    course (== earliest_unsubmitted_hw_id), so a later-due unsubmitted homework
    or a non-homework unsubmitted item must NOT be accepted;
  * the catch-up positive op carries an exact ``type == homework`` predicate, so
    submitting an unsubmitted non-homework item in the target course fails;
  * the catch-up named invariant is critical, so a wrong target double-penalizes.

V2 intervention variant solvability is also exercised: the correct trajectory
still scores 1.0 under the catch_up_homework_contention_v2 variant (decoy
unsubmitted homeworks + contradictory weighting notice + erroring grades read),
while submitting a decoy homework fails.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.lms import SessionCreateRequest, create_session
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.runner import ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_check_course_grade"
# Seed 42 -> grade_below_80 == 'true' (branch 1). Seed 40 -> 'false' (branch 2,
# non-vacuous: target course has real graded work and a weighted grade >= 80).
BELOW_SEED = 42
ABOVE_SEED = 40
VARIANT_FILENAME = "lms_check_course_grade__catch_up_homework_contention_v2.yaml"


@pytest.fixture()
def client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


def _headers() -> dict[str, str]:
    return {CONTROLLER_SECRET_HEADER: app.state.controller_secret}


def _create(client: TestClient, seed: int) -> dict:
    resp = client.post(
        "/api/env/lms/session",
        json={"task_id": TASK_ID, "seed": seed},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "resolved_targets" in data, "controller header should expose resolved_targets"
    return data


def _state(session_id: str):
    return app.state.session_manager.get(session_id)


def _evaluate(session_id: str) -> dict:
    state = _state(session_id)
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )


# ---------------------------------------------------------------------------
# Branch 1: grade below 80% -> submit catch_up.pdf for the EARLIEST-due homework
# ---------------------------------------------------------------------------

def test_branch1_correct_submission_passes(client: TestClient):
    session = _create(client, BELOW_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    assert targets["grade_below_80"] == "true", "seed precondition: branch 1 is active"
    # The catch-up target must be the earliest-due unsubmitted homework in the
    # target course (the v2 fairness fix: deterministic, course-scoped target).
    assert targets["unsubmitted_hw_id"] == targets["earliest_unsubmitted_hw_id"], (
        f"unsubmitted_hw_id must equal earliest_unsubmitted_hw_id: {targets}"
    )

    hw_id = targets["unsubmitted_hw_id"]
    resp = client.post(
        f"/api/env/lms/assignments/{hw_id}/submit",
        json={"session_id": sid, "file_name": "catch_up.pdf"},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sid)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # canonical_diff coverage is richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_branch1_target_is_earliest_due_homework(client: TestClient):
    """The pinned target is genuinely the earliest-due unsubmitted homework."""
    session = _create(client, BELOW_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    tcid = targets["target_course_id"]
    hw_id = targets["unsubmitted_hw_id"]

    state = _state(sid)
    unsub_hw = [
        a for a in state.assignments
        if a.course_id == tcid and a.submission_status == "not_submitted" and a.type == "homework"
    ]
    assert unsub_hw, "expected at least one unsubmitted homework in the target course"
    earliest = sorted(
        unsub_hw,
        key=lambda a: (a.due_at, int(str(a.id).rsplit("_", 1)[-1])),
    )[0]
    assert hw_id == earliest.id, (
        f"target {hw_id} should be the earliest-due homework {earliest.id} in {tcid}"
    )


def test_branch1_wrong_assignment_fails(client: TestClient):
    """Submitting a DIFFERENT assignment trips the critical sibling invariant."""
    session = _create(client, BELOW_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    hw_id = targets["unsubmitted_hw_id"]

    # Find any other submittable assignment in the session and submit it instead.
    state = _state(sid)
    wrong = next(
        a for a in state.assignments
        if a.id != hw_id
        and a.submission_status in ("not_submitted", "resubmit_requested", "graded", "late")
        and a.attempt_count < a.max_attempts
    )
    resp = client.post(
        f"/api/env/lms/assignments/{wrong.id}/submit",
        json={"session_id": sid, "file_name": "catch_up.pdf"},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sid)
    assert result.get("success") is False, f"wrong-assignment trajectory should fail: {result}"


def test_branch1_non_homework_in_target_course_fails(client: TestClient):
    """Submitting an unsubmitted NON-homework in the target course fails the type guard."""
    session = _create(client, BELOW_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    tcid = targets["target_course_id"]
    hw_id = targets["unsubmitted_hw_id"]

    state = _state(sid)
    non_hw = next(
        (
            a for a in state.assignments
            if a.course_id == tcid
            and a.submission_status == "not_submitted"
            and a.type != "homework"
            and a.attempt_count < a.max_attempts
            and a.id != hw_id
        ),
        None,
    )
    assert non_hw is not None, "expected an unsubmitted non-homework in the target course"
    resp = client.post(
        f"/api/env/lms/assignments/{non_hw.id}/submit",
        json={"session_id": sid, "file_name": "catch_up.pdf"},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sid)
    assert result.get("success") is False, f"non-homework trajectory should fail: {result}"


def test_branch1_wrong_filename_fails(client: TestClient):
    """Submitting the right assignment with the wrong file fails the positive op."""
    session = _create(client, BELOW_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    hw_id = targets["unsubmitted_hw_id"]

    resp = client.post(
        f"/api/env/lms/assignments/{hw_id}/submit",
        json={"session_id": sid, "file_name": "wrong_file.pdf"},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sid)
    assert result.get("success") is False, f"wrong-filename trajectory should fail: {result}"


def test_branch1_no_action_fails(client: TestClient):
    """Doing nothing leaves the positive obligation unmet."""
    session = _create(client, BELOW_SEED)
    sid = session["session_id"]
    result = _evaluate(sid)
    assert result.get("success") is False, f"no-op trajectory should fail: {result}"


def test_branch1_wrong_branch_marking_announcement_fails(client: TestClient):
    """Taking branch 2's action (mark announcement read) when branch 1 is correct fails."""
    session = _create(client, BELOW_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    unread = [
        a for a in targets["target_course_unread_announcement_ids"].split(",")
        if a
    ]
    assert unread, "expected at least one unread announcement in target course"
    for ann_id in unread:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
            headers=_headers(),
        )
        assert resp.status_code == 200, resp.text

    result = _evaluate(sid)
    assert result.get("success") is False, f"wrong-branch trajectory should fail: {result}"


# ---------------------------------------------------------------------------
# Branch 2: grade >= 80% -> mark EVERY unread announcement in target course read
# ---------------------------------------------------------------------------

def test_branch2_correct_mark_all_unread_passes(client: TestClient):
    session = _create(client, ABOVE_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    assert targets["grade_below_80"] == "false", "seed precondition: branch 2 is active"

    # Branch 2 is non-vacuous on this seed: the target course has real graded
    # work and a computed weighted grade >= 80.
    state = _state(sid)
    tcid = targets["target_course_id"]
    assert any(g.course_id == tcid for g in state.grades), (
        "branch 2 fixture must have real graded work in the target course"
    )
    assert state.weighted_score_for_course(tcid) is not None

    unread = [a for a in targets["target_course_unread_announcement_ids"].split(",") if a]
    assert len(unread) >= 2, f"branch 2 should require a multi-element bijection: {unread}"
    for ann_id in unread:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
            headers=_headers(),
        )
        assert resp.status_code == 200, resp.text

    result = _evaluate(sid)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"


def test_branch2_partial_mark_fails(client: TestClient):
    """Marking only ONE of the unread announcements fails the bijection saturation."""
    session = _create(client, ABOVE_SEED)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    unread = [a for a in targets["target_course_unread_announcement_ids"].split(",") if a]
    assert len(unread) >= 2

    resp = client.post(
        f"/api/env/lms/announcements/{unread[0]}/read",
        json={"session_id": sid},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sid)
    assert result.get("success") is False, f"partial-mark trajectory should fail: {result}"


# ---------------------------------------------------------------------------
# Intervention variant (catch_up_homework_contention_v2) solvability + bite
# ---------------------------------------------------------------------------

def _create_variant(seed: int) -> str:
    session = create_session(
        SessionCreateRequest(task_id=TASK_ID, seed=seed, variant_filename=VARIANT_FILENAME),
        session_manager=app.state.session_manager,
    )
    assert session["degradation_active"] is True
    return session["session_id"]


def test_variant_correct_submission_still_passes():
    """The correct earliest-due catch-up submission still scores 1.0 under the variant."""
    from datetime import datetime, timezone

    sid = _create_variant(BELOW_SEED)
    try:
        state = _state(sid)
        targets = state.resolved_targets
        hw_id = targets["unsubmitted_hw_id"]
        a = state.get_assignment(hw_id)
        # Drive the same mutation the submit endpoint performs.
        now = datetime.now(timezone.utc)
        a.submitted_at = now
        a.attempt_count += 1
        a.file_name = "catch_up.pdf"
        a.submission_status = "late" if now > a.due_at else "submitted"
        state.touch()
        result = _evaluate(sid)
        assert result.get("success") is True, f"variant correct trajectory should pass: {result}"
        assert result.get("score", 0.0) >= 0.99, f"variant score too low: {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_variant_decoy_homework_fails():
    """Submitting an injected decoy unsubmitted homework (later due) fails under the variant."""
    from datetime import datetime, timezone

    sid = _create_variant(BELOW_SEED)
    try:
        state = _state(sid)
        targets = state.resolved_targets
        tcid = targets["target_course_id"]
        hw_id = targets["unsubmitted_hw_id"]
        decoy = next(
            a for a in state.assignments
            if a.course_id == tcid
            and a.submission_status == "not_submitted"
            and a.type == "homework"
            and a.id != hw_id
        )
        now = datetime.now(timezone.utc)
        decoy.submitted_at = now
        decoy.attempt_count += 1
        decoy.file_name = "catch_up.pdf"
        decoy.submission_status = "late" if now > decoy.due_at else "submitted"
        state.touch()
        result = _evaluate(sid)
        assert result.get("success") is False, f"variant decoy-homework trajectory should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)
