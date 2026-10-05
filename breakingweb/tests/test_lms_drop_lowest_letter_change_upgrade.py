"""Solvability proof for the v2 (expert) lms_drop_lowest_letter_change task.

The v2 base deterministically FORCES the demanding "submit" branch on every
seed (the v1 random distribution almost never produced it, so frontier models
trivially took the one-click "mark announcement" branch and the
recompute-and-verify weak point was never exercised). The ``grade_book`` builder
re-sculpts the TARGET course's homework grades into a fully re-derivable
configuration with three compounding, FAIR verification traps:

  X: 80/100 (ratio 0.80), late_penalty 0.15  -> the homework the engine drops
  P: 92/100 (ratio 0.92)
  A: 99/100 (ratio 0.99)
  Z:  9/10  (ratio 0.90)                      -> LOWEST raw EARNED points

Engine view (the Grades page the agent reads, which applies the (1 - penalty)
factor and re-derives drops):
  * WITH the drop applied  -> 93.67  -> A
  * WITHOUT the drop       -> 87.25  -> B
=> the coarse letter genuinely flips (B -> A) => drop_changes_letter_grounded
   == 'true' => branch 1 (submit ``letter_grade_report.pdf`` for X, the dropped
   homework = lowest score-to-points RATIO).

Three traps an agent can fall into, each of which FAILS:
  1. THRESHOLD/LATE-PENALTY: forget the late penalty on X and the WITHOUT-drop
     score reads as 90.25 (an A) -> no flip -> the agent wrongly marks the
     announcement (branch 2's action) -> trips the critical wrong-branch
     invariant.
  2. RATIO trap: submit the lowest raw EARNED-points homework (Z) instead of X
     (lowest ratio) -> wrong assignment.
  3. Wrong file name.

Drives the CORRECT solution through the REAL LMS backend submit endpoint via
Starlette TestClient, then evaluates via the unified evaluator. Also proves the
wrong / near-miss trajectories fail.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.runner import ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_drop_lowest_letter_change"
# Every seed now lands on the forced submit branch; sample a few to prove the
# forcing pass is seed-stable.
BRANCH1_SEEDS = [0, 7, 15, 42, 99]


@pytest.fixture()
def client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


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


def _submit(client: TestClient, sid: str, assignment_id: str, file_name: str) -> None:
    resp = client.post(
        f"/api/env/lms/assignments/{assignment_id}/submit",
        json={"session_id": sid, "file_name": file_name},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text


def _read_announcement(client: TestClient, sid: str, announcement_id: str) -> None:
    resp = client.post(
        f"/api/env/lms/announcements/{announcement_id}/read",
        json={"session_id": sid},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Seed preconditions: the v2 forcing pass must be seed-stable. Every seed lands
# on the submit branch, the flip is genuine (B without-drop -> A with-drop), the
# late penalty is live on the dropped homework, and the ratio trap is live
# (lowest-ratio dropped homework != lowest-raw-points homework).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", BRANCH1_SEEDS)
def test_seed_forces_hard_branch_and_traps(client: TestClient, seed: int):
    data = _create(client, seed)
    t = data["resolved_targets"]
    st = _state(data["session_id"])
    tcid = t["target_course_id"]

    assert t["drop_changes_letter_grounded"] == "true", t
    dropped = t["lowest_dropped_hw_id"]
    raw_lowest = t["lowest_hw_id"]
    assert dropped, "submit branch must have a dropped-homework target"
    assert raw_lowest and raw_lowest != dropped, (
        "ratio trap must be live: lowest-raw-points homework must differ from "
        "the dropped (lowest-ratio) homework"
    )

    # The flip is genuine and lives in the boundary band, with the late penalty
    # load-bearing (un-penalized without-drop reads as an A and kills the flip).
    assert str(st.weighted_score_for_course(tcid)) == "93.67"
    dropped_grade = next(
        g for g in st.grades if g.assignment_id == dropped and g.course_id == tcid
    )
    assert dropped_grade.late_penalty_applied > 0, "late penalty must be live on the dropped grade"

    # The dropped homework is submittable and a single submit reaches attempt 2.
    a = st.get_assignment(dropped)
    assert a.submission_status in ("not_submitted", "resubmit_requested", "graded", "late")
    assert a.attempt_count < a.max_attempts


# ---------------------------------------------------------------------------
# Correct trajectory: submit letter_grade_report.pdf for the dropped homework.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", BRANCH1_SEEDS)
def test_correct_submission_passes(client: TestClient, seed: int):
    session = _create(client, seed)
    sid = session["session_id"]
    targets = session["resolved_targets"]

    _submit(client, sid, targets["lowest_dropped_hw_id"], "letter_grade_report.pdf")

    result = _evaluate(sid)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # canonical_diff coverage is richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


# ---------------------------------------------------------------------------
# Trap 2 (ratio): submit the lowest RAW-EARNED-POINTS homework (Z) instead of
# the dropped lowest-ratio homework (X). Fails the positive op and trips the
# critical sibling-assignment invariant.
# ---------------------------------------------------------------------------

def test_wrong_homework_raw_lowest_points_fails(client: TestClient):
    session = _create(client, 15)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    dropped = targets["lowest_dropped_hw_id"]
    raw_lowest = targets["lowest_hw_id"]
    assert raw_lowest and raw_lowest != dropped

    _submit(client, sid, raw_lowest, "letter_grade_report.pdf")

    result = _evaluate(sid)
    assert result.get("success") is False, f"wrong-homework trajectory should fail: {result}"


# ---------------------------------------------------------------------------
# Trap 3 (file name).
# ---------------------------------------------------------------------------

def test_wrong_filename_fails(client: TestClient):
    session = _create(client, 15)
    sid = session["session_id"]
    targets = session["resolved_targets"]

    _submit(client, sid, targets["lowest_dropped_hw_id"], "wrong_file.pdf")

    result = _evaluate(sid)
    assert result.get("success") is False, f"wrong-filename trajectory should fail: {result}"


# ---------------------------------------------------------------------------
# Trap 1 (late penalty): an agent that forgets the late penalty concludes "no
# flip" and marks the latest announcement read (branch 2's action). Because the
# grounded discriminator is 'true', branch 2 never matches and the read trips
# the critical wrong-branch invariant.
# ---------------------------------------------------------------------------

def test_wrong_branch_marking_announcement_fails(client: TestClient):
    session = _create(client, 15)
    sid = session["session_id"]
    targets = session["resolved_targets"]

    _read_announcement(client, sid, targets["latest_announcement_id"])

    result = _evaluate(sid)
    assert result.get("success") is False, f"wrong-branch trajectory should fail: {result}"


def test_no_action_fails(client: TestClient):
    session = _create(client, 15)
    sid = session["session_id"]
    result = _evaluate(sid)
    assert result.get("success") is False, f"no-op trajectory should fail: {result}"


# ---------------------------------------------------------------------------
# Near-miss: a single submit that does NOT reach attempt_count >= 2 must fail
# the attempt predicate. (Forced X starts at attempt_count 1, max 2, so a
# single submit reaches exactly 2 and passes -- this proves the predicate bites
# when the agent submits to a freshly-created homework that is still at 0.)
# ---------------------------------------------------------------------------

def test_correct_homework_but_attempt_predicate_is_enforced(client: TestClient):
    """Sanity: the dropped homework starts at attempt_count==1 so ONE submit
    reaches the required attempt_count>=2; submitting the wrong file to it still
    fails (proves attempt count alone is not sufficient)."""
    session = _create(client, 42)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    st = _state(sid)
    a = st.get_assignment(targets["lowest_dropped_hw_id"])
    assert a.attempt_count == 1 and a.max_attempts >= 2

    _submit(client, sid, targets["lowest_dropped_hw_id"], "decoy_report.pdf")
    result = _evaluate(sid)
    assert result.get("success") is False, f"wrong-file even at attempt 2 should fail: {result}"
