"""Solvability proof for the hardened ``lms_submit_late`` task (v2).

Drives the CORRECT solution through the REAL LMS backend endpoints
(``/api/env/lms/session`` + ``/api/env/lms/assignments/{id}/submit``) using the
seed ``resolved_targets`` as the intended answer, then evaluates the live state
through the canonical-diff evaluator. Also exercises several near-miss
trajectories that must FAIL.

The hardened task no longer leaks the assignment id/title or the file name in
its instruction. The agent must:
  * filter to past-due, never-submitted assignments,
  * compute each one's days-late against its own course's late-submission
    window (``max_late_days``), and
  * identify the single assignment still inside its window.

v2 hardening (the load-bearing difficulty lever): the seed now plants a
SAME-DAYS-LATE LOOK-ALIKE — a past-due never-submitted assignment in a STRICTER
course that is the EXACT same number of days late as the sole recoverable target
but is already OUTSIDE its (smaller) window. "Sort by how many days late" no
longer separates the answer from the trap; the agent must read each course's
``max_late_days`` and do per-course window math. Submitting the look-alike trips
a high-severity look-alike constraint, a critical "out-of-window submission"
constraint, and the critical "only the target changed" constraint.

The seed builder guarantees exactly one recoverable past-due assignment (with
margin against the floating seed anchor), so ``target_assignment_id`` /
``required_file_name`` are the unambiguous intended answer.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.backend.state import SessionManager
from breakingweb.runner import ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_submit_late"
ENV_ID = "lms"
SEED = 42


@pytest.fixture()
def client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {CONTROLLER_SECRET_HEADER: app.state.controller_secret}


def _create(client: TestClient, seed: int = SEED) -> tuple[str, dict]:
    resp = client.post(
        f"/api/env/{ENV_ID}/session",
        json={"task_id": TASK_ID, "seed": seed},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "resolved_targets" in data, data
    return data["session_id"], data["resolved_targets"]


def _submit(client: TestClient, sid: str, assignment_id: str, file_name: str):
    return client.post(
        f"/api/env/{ENV_ID}/assignments/{assignment_id}/submit",
        json={"session_id": sid, "file_name": file_name},
        headers=_headers(),
    )


def _evaluate_live(sid: str, targets: dict) -> dict:
    state = app.state.session_manager.get(sid)
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )


# ---------------------------------------------------------------------------
# Seed-shape guarantees: exactly one recoverable past-due assignment, and the
# task target points at it. (Confirms the re-derivation rule is well-posed.)
# ---------------------------------------------------------------------------

def test_seed_has_exactly_one_recoverable_target():
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id=ENV_ID, task_id=TASK_ID, seed=SEED)
    state = sm.get_state(sid)
    now = datetime.now(timezone.utc)
    courses = {c.id: c for c in state.courses}

    recoverable: list[str] = []
    for a in state.assignments:
        if a.submission_status != "not_submitted":
            continue
        due = a.due_at if a.due_at.tzinfo else a.due_at.replace(tzinfo=timezone.utc)
        if due >= now:
            continue
        max_late = courses[a.course_id].syllabus.late_policy.max_late_days
        if (now - due).days <= max_late:
            recoverable.append(a.id)

    assert len(recoverable) == 1, f"expected exactly one recoverable, got {recoverable}"
    assert targets["target_assignment_id"] == recoverable[0]
    assert targets["sole_recoverable_missing_id"] == recoverable[0]
    # Required file name is the derived <COURSE_CODE>_late_submission.pdf.
    assert targets["required_file_name"] == f"{targets['course_code']}_late_submission.pdf"
    # Decoy lives in a different course (so the "left untouched" check is real).
    decoy = next(a for a in state.assignments if a.id == targets["decoy_assignment_id"])
    assert decoy.course_id != targets["target_course_id"]


def _days_late(a, now: datetime) -> int:
    due = a.due_at if a.due_at.tzinfo else a.due_at.replace(tzinfo=timezone.utc)
    return (now - due).days


def test_seed_has_same_days_late_lookalike_trap():
    """v2: a past-due look-alike in a STRICTER course is the EXACT same number of
    days late as the sole recoverable target, but is already OUT of its window.

    This is the load-bearing difficulty lever: days-late no longer separates the
    answer from the trap, so the agent MUST read each course's max_late_days.
    """
    for seed in (SEED, 1, 7, 100, 999, 2026):
        sm = SessionManager()
        sid, targets, _ = sm.create_session(env_id=ENV_ID, task_id=TASK_ID, seed=seed)
        state = sm.get_state(sid)
        now = datetime.now(timezone.utc)
        courses = {c.id: c for c in state.courses}

        look_id = targets["lookalike_assignment_id"]
        assert look_id, f"seed {seed}: expected a same-days-late look-alike"

        target = next(a for a in state.assignments if a.id == targets["target_assignment_id"])
        look = next(a for a in state.assignments if a.id == look_id)

        # Same number of days late as the target.
        assert _days_late(look, now) == _days_late(target, now), (
            f"seed {seed}: look-alike days-late must equal target days-late"
        )
        # Different (stricter) course.
        assert look.course_id != target.course_id
        look_max = courses[look.course_id].syllabus.late_policy.max_late_days
        target_max = courses[target.course_id].syllabus.late_policy.max_late_days
        assert look_max < target_max, f"seed {seed}: look-alike course must be stricter"
        # Target is INSIDE its window; look-alike is OUTSIDE its window.
        assert _days_late(target, now) <= target_max
        assert _days_late(look, now) > look_max
        # The look-alike is exposed as the canonical decoy.
        assert targets["decoy_assignment_id"] == look_id
        # The look-alike is in the authoritative out-of-window set.
        out_ids = [x for x in targets["out_of_window_assignment_ids"].split(",") if x]
        assert look_id in out_ids
        assert targets["target_assignment_id"] not in out_ids


# ---------------------------------------------------------------------------
# Correct solution through the REAL backend → evaluator passes.
# ---------------------------------------------------------------------------

def test_correct_submission_passes(client: TestClient):
    sid, targets = _create(client)

    resp = _submit(
        client, sid, targets["target_assignment_id"], targets["required_file_name"]
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["assignment"]
    # The sole recoverable assignment is past due → backend marks it 'late'.
    assert body["submission_status"] == "late"
    assert body["file_name"] == targets["required_file_name"]

    result = _evaluate_live(sid, targets)
    assert result["success"] is True, result
    assert result["score"] >= 0.99, result
    # canonical_diff is richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_correct_submission_passes_multiple_seeds(client: TestClient):
    for seed in (1, 7, 100, 999, 2026):
        sid, targets = _create(client, seed=seed)
        resp = _submit(
            client, sid, targets["target_assignment_id"], targets["required_file_name"]
        )
        assert resp.status_code == 200, resp.text
        result = _evaluate_live(sid, targets)
        assert result["success"] is True, f"seed {seed}: {result}"
        assert result["score"] >= 0.99, f"seed {seed}: {result}"


# ---------------------------------------------------------------------------
# Near-miss / wrong trajectories must FAIL.
# ---------------------------------------------------------------------------

def test_wrong_file_name_fails(client: TestClient):
    """Correct assignment, but the generic 'submission.pdf' (not the derived name)."""
    sid, targets = _create(client)
    resp = _submit(client, sid, targets["target_assignment_id"], "submission.pdf")
    assert resp.status_code == 200, resp.text
    result = _evaluate_live(sid, targets)
    assert result["success"] is False
    assert result["score"] < 0.99


def test_wrong_assignment_fails(client: TestClient):
    """Submitting a different past-due (but unrecoverable) assignment fails."""
    sid, targets = _create(client)
    state = app.state.session_manager.get(sid)
    now = datetime.now(timezone.utc)
    wrong_id = None
    for a in state.assignments:
        if a.submission_status != "not_submitted":
            continue
        if a.id == targets["target_assignment_id"]:
            continue
        due = a.due_at if a.due_at.tzinfo else a.due_at.replace(tzinfo=timezone.utc)
        if due < now:  # a past-due-but-unrecoverable distractor
            wrong_id = a.id
            break
    assert wrong_id is not None, "expected an unrecoverable past-due distractor in the seed"

    resp = _submit(client, sid, wrong_id, targets["required_file_name"])
    assert resp.status_code == 200, resp.text
    result = _evaluate_live(sid, targets)
    assert result["success"] is False
    assert result["score"] < 0.99


def test_same_days_late_lookalike_submission_fails(client: TestClient):
    """v2: submitting the SAME-DAYS-LATE look-alike (the days-late-sort trap)
    must fail and fire the look-alike + out-of-window + only-target constraints.

    An agent that shortcuts to "submit whichever past-due assignment is fewest
    days late" picks this look-alike (it ties the target on days-late) and fails.
    """
    sid, targets = _create(client)
    look_id = targets["lookalike_assignment_id"]
    assert look_id, "expected a same-days-late look-alike in the seed"

    resp = _submit(client, sid, look_id, targets["required_file_name"])
    assert resp.status_code == 200, resp.text
    result = _evaluate_live(sid, targets)
    assert result["success"] is False
    assert result["score"] < 0.99

    failed = {
        nc["desc"]
        for nc in result["negative_checks"]
        if not nc["passed"]
    }
    # The dedicated look-alike, out-of-window, and only-target constraints fire.
    assert any("look-alike" in d for d in failed), failed
    assert any("out-of-window" in d for d in failed), failed
    assert any("Only the targeted assignment" in d for d in failed), failed


def test_correct_plus_decoy_fails(client: TestClient):
    """Correct submission PLUS touching the decoy trips the critical invariant."""
    sid, targets = _create(client)
    assert (
        _submit(
            client, sid, targets["target_assignment_id"], targets["required_file_name"]
        ).status_code
        == 200
    )
    # Also submit the decoy in the other course (a tempting "catch everything" error).
    extra = _submit(client, sid, targets["decoy_assignment_id"], "extra.pdf")
    assert extra.status_code in (200, 422)  # decoy may or may not be submittable
    if extra.status_code == 200:
        result = _evaluate_live(sid, targets)
        assert result["success"] is False
        # Both the critical "other assignment" invariant and the decoy constraint fire.
        failed = [nc for nc in result["negative_checks"] if not nc["passed"]]
        assert failed, result


def test_no_action_fails(client: TestClient):
    sid, targets = _create(client)
    result = _evaluate_live(sid, targets)
    assert result["success"] is False
    assert result["score"] < 0.99
