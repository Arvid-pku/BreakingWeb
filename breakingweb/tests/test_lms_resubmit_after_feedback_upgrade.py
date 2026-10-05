"""Solvability proof for the upgraded lms_resubmit_after_feedback task.

The upgraded task requires the agent to:
  * find every assignment whose status is "resubmit_requested" across all
    courses (multiple, scattered across a 5-course catalog),
  * determine, per course's late policy, which flagged assignments are still
    inside their resubmission window (window OPEN) and resubmit ONLY those —
    leaving the EXPIRED flagged decoys (status resubmit_requested but window
    closed) untouched, since resubmitting one mutates a frozen sibling and
    trips the critical freeze invariant,
  * name each revision file "revision_<weight_category>_attempt<n>.pdf" where
    <weight_category> is re-derived per-assignment and <n> is that assignment's
    NEXT attempt number (its live attempt_count + 1) — a per-row two-fact join.

The correct solution is driven through the REAL backend resubmit endpoint via
starlette TestClient, confirming achievability past the resubmit gate
(status == resubmit_requested, attempt_count < max_attempts). Several near-miss
trajectories (uniform filename, wrong attempt number, missing one, and
over-acting on an expired-window decoy) are asserted to fail.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.runner import ensure_controller_secret
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_resubmit_after_feedback"
SEEDS = [42, 1, 7, 100, 2024, 13, 77]


@pytest.fixture()
def client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {CONTROLLER_SECRET_HEADER: app.state.controller_secret}


def _create(client: TestClient, seed: int) -> tuple[str, dict]:
    resp = client.post(
        "/api/env/lms/session",
        json={"task_id": TASK_ID, "seed": seed},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["session_id"], data["resolved_targets"]


def _state(session_id: str):
    return app.state.session_manager.get(session_id)


def _flagged_ids(targets: dict) -> list[str]:
    raw = targets.get("resubmit_assignment_ids", "")
    return [x for x in raw.split(",") if x]


def _expired_ids(targets: dict) -> list[str]:
    raw = targets.get("expired_resubmit_assignment_ids", "")
    return [x for x in raw.split(",") if x]


def _expected_file(state, assignment_id: str) -> str:
    """revision_<category>_attempt<attempt_count+1>.pdf from the pre-action row."""
    a = state.get_assignment(assignment_id)
    return f"revision_{a.weight_category}_attempt{a.attempt_count + 1}.pdf"


@pytest.mark.parametrize("seed", SEEDS)
def test_correct_trajectory_passes(client: TestClient, seed: int) -> None:
    """Resubmitting every IN-WINDOW flagged assignment with the per-category,
    per-attempt file passes, while leaving expired-window decoys untouched."""
    sid, targets = _create(client, seed)
    ids = _flagged_ids(targets)
    expired = _expired_ids(targets)
    assert len(ids) >= 2, f"expected >=2 in-window flagged assignments, got {ids}"
    assert len(expired) >= 2, f"expected >=2 expired-window decoys, got {expired}"
    # The eligible set and the expired-decoy set must be disjoint.
    assert not (set(ids) & set(expired)), (ids, expired)

    # Read the seeded (pre-action) weight categories + attempt counts before mutating.
    pre_state = _state(sid)
    expected_files = {aid: _expected_file(pre_state, aid) for aid in ids}
    pre_attempts = {aid: pre_state.get_assignment(aid).attempt_count for aid in ids}

    for aid in ids:
        resp = client.post(
            f"/api/env/lms/assignments/{aid}/resubmit",
            json={"session_id": sid, "file_name": expected_files[aid]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["assignment"]
        assert body["submission_status"] in ("submitted", "late")
        assert body["file_name"] == expected_files[aid]
        # attempt_count is the prior count + 1 after a single resubmit.
        assert body["attempt_count"] == pre_attempts[aid] + 1

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"seed={seed} result={result}"
    assert result.get("score", 0.0) >= 0.99, f"seed={seed} result={result}"
    # The upgraded diff is richer than a single positive op.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_wrong_uniform_filename_fails(client: TestClient) -> None:
    """Resubmitting all flagged with a uniform (non-category) name fails."""
    sid, targets = _create(client, 42)
    ids = _flagged_ids(targets)
    assert len(ids) >= 2

    for aid in ids:
        resp = client.post(
            f"/api/env/lms/assignments/{aid}/resubmit",
            json={"session_id": sid, "file_name": "revision_v2.pdf"},
        )
        assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"unexpected pass: {result}"


def test_wrong_attempt_number_fails(client: TestClient) -> None:
    """Using a fixed attempt number (attempt2) for every flagged assignment
    fails the per-row attempt+1 two-fact join."""
    sid, targets = _create(client, 42)
    ids = _flagged_ids(targets)
    assert len(ids) >= 2
    pre_state = _state(sid)

    for aid in ids:
        cat = pre_state.get_assignment(aid).weight_category
        # Correct category, WRONG (fixed) attempt number.
        resp = client.post(
            f"/api/env/lms/assignments/{aid}/resubmit",
            json={"session_id": sid, "file_name": f"revision_{cat}_attempt2.pdf"},
        )
        assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"unexpected pass: {result}"


def test_resubmitting_expired_decoy_fails(client: TestClient) -> None:
    """Resubmitting an EXPIRED-window flagged decoy (the status-filter
    shortcut) on top of the correct work trips the critical freeze invariant."""
    sid, targets = _create(client, 42)
    ids = _flagged_ids(targets)
    expired = _expired_ids(targets)
    assert len(ids) >= 2 and len(expired) >= 1
    pre_state = _state(sid)

    for aid in ids:
        resp = client.post(
            f"/api/env/lms/assignments/{aid}/resubmit",
            json={"session_id": sid, "file_name": _expected_file(pre_state, aid)},
        )
        assert resp.status_code == 200, resp.text

    # Over-act on a closed-window decoy with an otherwise plausible name.
    e = expired[0]
    e_name = _expected_file(pre_state, e)
    resp = client.post(
        f"/api/env/lms/assignments/{e}/resubmit",
        json={"session_id": sid, "file_name": e_name},
    )
    # The endpoint accepts it (it only gates on status/attempts) — the window
    # rule is a planning obligation enforced by the evaluator, not the backend.
    assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"unexpected pass: {result}"


def test_missing_one_resubmission_fails(client: TestClient) -> None:
    """Leaving one in-window flagged assignment un-resubmitted fails the bijection."""
    sid, targets = _create(client, 42)
    ids = _flagged_ids(targets)
    assert len(ids) >= 2

    pre_state = _state(sid)
    # Resubmit all but the last one, each with the correct per-row name.
    for aid in ids[:-1]:
        resp = client.post(
            f"/api/env/lms/assignments/{aid}/resubmit",
            json={"session_id": sid, "file_name": _expected_file(pre_state, aid)},
        )
        assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"unexpected pass: {result}"


def test_extra_side_effect_message_fails(client: TestClient) -> None:
    """Correct resubmissions + an extra sent message trips the message guard."""
    sid, targets = _create(client, 42)
    ids = _flagged_ids(targets)
    pre_state = _state(sid)
    for aid in ids:
        resp = client.post(
            f"/api/env/lms/assignments/{aid}/resubmit",
            json={"session_id": sid, "file_name": _expected_file(pre_state, aid)},
        )
        assert resp.status_code == 200, resp.text

    # Side effect the instruction explicitly forbids.
    msg = client.post(
        "/api/env/lms/messages/send",
        json={"session_id": sid, "to": "advisor", "subject": "hi", "body": "done"},
    )
    assert msg.status_code == 200, msg.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"unexpected pass: {result}"
