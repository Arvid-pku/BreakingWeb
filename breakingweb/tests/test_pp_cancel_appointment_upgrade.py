"""Solvability proof for the hardened pp_cancel_appointment task.

The task was re-tiered easy -> medium. The patient accidentally booked the same
visit with the SAME PCP at the SAME datetime THREE times (a same-provider,
same-datetime duplicate CLUSTER). The instruction no longer names the
discriminating field: the agent must infer that the ORIGINAL booking is the
earliest-booked member of the cluster (minimum ``booked_at``) and cancel EVERY
other member (the accidental re-books) with a cancellation reason that contains
the word "duplicate", while keeping the original and every other collection
untouched.

The correct trajectory is driven through the REAL backend cancel endpoint
(POST /appointments/{id}/cancel) via a Starlette TestClient so the proof also
confirms the action is reachable past the endpoint's gates (scheduled-only) and
that the cancel BIJECTION over the re-book set saturates.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.runner import controller_headers, ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_cancel_appointment"
SEED = 42


def _client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _new_session() -> tuple[str, dict]:
    """Create a session on the app's shared SessionManager and return (sid, targets)."""
    sm: SessionManager = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id="patient_portal", task_id=TASK_ID, seed=SEED)
    return sid, dict(targets)


def _state(sid: str):
    return app.state.session_manager.get_state(sid)


def _cancel(client: TestClient, sid: str, apt_id: str, reason: str):
    return client.post(
        f"/api/env/patient_portal/appointments/{apt_id}/cancel",
        json={"session_id": sid, "reason": reason},
        headers=controller_headers(),
    )


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        return [v for v in value.split(",") if v]
    return list(value)


def _cluster_ids(targets: dict) -> list[str]:
    return _as_list(targets["conflict_apt_ids"])


def _cancel_ids(targets: dict) -> list[str]:
    return _as_list(targets["conflict_cancel_apt_ids"])


def _keep_id(targets: dict) -> str:
    return targets["conflict_keep_apt_id"]


def _earliest_booked_id(targets: dict, state) -> str:
    """Re-derive the ORIGINAL (earliest-booked) the way a correct agent would."""
    by_id = {a.id: a for a in state.appointments}
    return min(_cluster_ids(targets), key=lambda aid: (by_id[aid].booked_at, aid))


def test_seed_shape_is_a_same_provider_duplicate_cluster():
    """Three conflict appointments share provider + datetime; booked_at orders them."""
    sid, targets = _new_session()
    state = _state(sid)
    ids = _cluster_ids(targets)
    assert len(ids) == 3
    appts = {a.id: a for a in state.appointments if a.id in ids}
    # Same provider (the PCP) and same datetime -> only booked_at disambiguates.
    provider_ids = {appts[i].provider_id for i in ids}
    datetimes = {appts[i].datetime for i in ids}
    assert provider_ids == {state.patient.pcp_id}
    assert len(datetimes) == 1
    booked = {appts[i].booked_at for i in ids}
    assert len(booked) == 3  # all distinct -> total order
    # The KEEP target must be the earliest-booked; the CANCEL set is the rest.
    assert _keep_id(targets) == _earliest_booked_id(targets, state)
    assert set(_cancel_ids(targets)) == set(ids) - {_keep_id(targets)}
    assert _keep_id(targets) not in _cancel_ids(targets)


def test_correct_trajectory_passes_via_real_endpoint():
    """Cancelling EVERY re-book with a 'duplicate' reason (keeping the original) passes."""
    client = _client()
    sid, targets = _new_session()
    state = _state(sid)
    keep = _earliest_booked_id(targets, state)
    assert keep == _keep_id(targets)

    for apt_id in _cancel_ids(targets):
        resp = _cancel(client, sid, apt_id, "Duplicate booking created in error")
        assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    # Confirm the kept original is still scheduled.
    kept = next(a for a in state.appointments if a.id == keep)
    assert kept.status == "scheduled"


def test_cancelling_only_one_rebook_fails():
    """Cancelling just ONE of the two re-books (bijection not saturated) fails."""
    client = _client()
    sid, targets = _new_session()

    one = _cancel_ids(targets)[0]
    resp = _cancel(client, sid, one, "Duplicate booking created in error")
    assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_cancelling_the_original_fails():
    """Cancelling the earliest-booked ORIGINAL (which must be kept) fails."""
    client = _client()
    sid, targets = _new_session()
    state = _state(sid)
    keep = _earliest_booked_id(targets, state)

    # Agent who took global-min wrong / cancelled the original instead of a re-book.
    resp = _cancel(client, sid, keep, "Duplicate booking created in error")
    assert resp.status_code == 200, resp.text
    # Also cancel one real re-book, leaving the other re-book live -> still wrong set.
    resp = _cancel(client, sid, _cancel_ids(targets)[0], "Duplicate booking created in error")
    assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_missing_duplicate_reason_fails():
    """Cancelling the right re-books but without 'duplicate' in the reason fails."""
    client = _client()
    sid, targets = _new_session()

    for apt_id in _cancel_ids(targets):
        resp = _cancel(client, sid, apt_id, "Patient requested cancellation")
        assert resp.status_code == 200, resp.text

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_extra_side_effect_cancelling_whole_cluster_fails():
    """Cancelling ALL cluster members (incl. the original) trips the keep invariant."""
    client = _client()
    sid, targets = _new_session()

    for apt_id in _cluster_ids(targets):
        assert _cancel(client, sid, apt_id, "Duplicate booking").status_code == 200

    state = _state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"
