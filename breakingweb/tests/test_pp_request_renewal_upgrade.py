"""Solvability + difficulty proof for the v2-upgraded ``pp_request_renewal`` task.

The task was hardened into a dual-action, three-category renewal task with a
real backtracking gate (the declared primary primitive):

* renew **every** prescription that has 0 refills remaining — the renewal set is
  a bijection over ``target['renewable_rx_ids']`` which now spans THREE seed
  sub-categories:
    - the dedicated active zero-refill rx (``zero_refill_rx_ids``),
    - the expiring-AND-zero-refill rxes (``expiring_zero_refill_rx_ids``), and
    - the already-**expired** rx (``expired_renewable_rx_ids``) — the
      backtracking gate: a refill on it 422s (refill requires status==active),
      so the agent must discover the blocker and re-route to the renewal
      endpoint (which accepts status in {active, expired});
* refill **exactly** the named refillable prescription
  (``target['refill_rx_id']`` / ``target['refill_medication']``), whose
  ``refills_remaining`` must be decremented by one and ``last_filled`` refreshed
  **this session** (``x > session_start``), while staying ``active``;
* leave the expiring-**with-refills** decoys (``expiring_with_refills_rx_ids``)
  untouched — they are refill-eligible, not renewal-eligible;
* touch nothing else (every sibling collection is pinned ``preserve: ALL`` and
  the most-tempting prescription sibling invariant is ``severity: critical``).

The correct solution is driven through the REAL backend endpoints
(``POST /medications/{rx_id}/renewal`` and ``POST /medications/{rx_id}/refill``)
so the proof also confirms the canonical answer survives the server's status
gates (renewal requires status in {active, expired}; refill requires
status == active and refills_remaining > 0).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

API = "/api/env/patient_portal"
TASK_ID = "pp_request_renewal"


def _fresh_session(seed: int = 42):
    """Create a session on a manager wired into the app so TestClient calls hit
    the same state we later hand to ``evaluate``.

    Returns ``(session_manager, session_id, targets_dict, client)``.
    """
    sm = SessionManager()
    app.state.session_manager = sm
    sid, targets, _ = sm.create_session(env_id="patient_portal", task_id=TASK_ID, seed=seed)
    return sm, sid, dict(targets), TestClient(app)


def _renew(client: TestClient, sid: str, rx_id: str):
    return client.post(f"{API}/medications/{rx_id}/renewal", json={"session_id": sid})


def _refill(client: TestClient, sid: str, rx_id: str):
    return client.post(f"{API}/medications/{rx_id}/refill", json={"session_id": sid})


def _evaluate(sm: SessionManager, sid: str, targets: dict):
    return evaluate(
        task=get_task(TASK_ID),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )


# ---------------------------------------------------------------------------
# Seed sanity — the discriminator targets are well-formed and distinct.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [42, 7, 123, 2026])
def test_seed_targets_are_well_formed(seed: int):
    sm, sid, t, _ = _fresh_session(seed)
    state = sm.get_state(sid)
    rxes = {r.id: r for r in state.prescriptions}

    # The renewal set spans three sub-categories and is a strict union.
    renewable = t["renewable_rx_ids"]
    assert len(renewable) == len(set(renewable)) == 4
    assert set(t["zero_refill_rx_ids"]).issubset(set(renewable))
    assert set(t["expiring_zero_refill_rx_ids"]).issubset(set(renewable))
    assert set(t["expired_renewable_rx_ids"]).issubset(set(renewable))
    assert len(t["zero_refill_rx_ids"]) == 1
    assert len(t["expiring_zero_refill_rx_ids"]) == 2
    assert len(t["expired_renewable_rx_ids"]) == 1

    # Every renewal target has 0 refills and is renewal-eligible.
    for rid in renewable:
        assert rxes[rid].refills_remaining == 0
        assert rxes[rid].status in ("active", "expired")

    # Exactly one renewal target is EXPIRED — the backtracking gate.
    expired_in_set = [rid for rid in renewable if rxes[rid].status == "expired"]
    assert expired_in_set == t["expired_renewable_rx_ids"]
    assert len(expired_in_set) == 1

    # The refill target is a DIFFERENT, active, refillable prescription.
    refill_id = t["refill_rx_id"]
    assert refill_id not in renewable
    assert rxes[refill_id].refills_remaining > 0
    assert rxes[refill_id].status == "active"
    assert t["refill_medication"].lower() in rxes[refill_id].medication.lower()

    # The expiring-with-refills decoys are NOT in the renewal set and have refills.
    assert len(t["expiring_with_refills_rx_ids"]) >= 1
    for rid in t["expiring_with_refills_rx_ids"]:
        assert rid not in renewable
        assert rxes[rid].refills_remaining > 0


# ---------------------------------------------------------------------------
# Backtracking gate — a refill on the expired rx is rejected (422), proving the
# agent genuinely has to re-route to renewal.
# ---------------------------------------------------------------------------

def test_refill_on_expired_renewal_target_is_rejected():
    sm, sid, t, client = _fresh_session(seed=42)
    expired_id = t["expired_renewable_rx_id"]
    resp = _refill(client, sid, expired_id)
    assert resp.status_code == 422, resp.text
    # Renewal on the same expired rx succeeds (the correct re-route).
    resp = _renew(client, sid, expired_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending_renewal"


# ---------------------------------------------------------------------------
# Correct solution — driven through the real endpoints — passes.
# ---------------------------------------------------------------------------

def test_correct_trajectory_via_real_endpoints_passes():
    sm, sid, t, client = _fresh_session(seed=42)

    # Method: the canonical solution is driven entirely through the real
    # POST /medications/{rx_id}/renewal and /refill backend routes so the
    # proof confirms the intended answer survives the server status gates,
    # INCLUDING the expired-rx backtracking gate (renewal accepts expired).
    for rid in t["renewable_rx_ids"]:
        resp = _renew(client, sid, rid)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "pending_renewal"

    before = next(r for r in sm.get_state(sid).prescriptions if r.id == t["refill_rx_id"])
    before_refills = before.refills_remaining
    resp = _refill(client, sid, t["refill_rx_id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["refills_remaining"] == before_refills - 1
    assert resp.json()["status"] == "active"

    result = _evaluate(sm, sid, t)
    assert result["success"] is True, f"result: {result}"
    assert result["score"] >= 0.99
    # canonical_diff checks are richer than a single positive op.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


# ---------------------------------------------------------------------------
# Wrong / near-miss trajectories — fail.
# ---------------------------------------------------------------------------

def test_missing_the_expired_renewal_fails():
    """The naive 'renew the active/expiring zero-refill rxes' agent that never
    backtracks to renew the EXPIRED prescription leaves the bijection
    unsaturated, so the task fails even though the refill is correct."""
    sm, sid, t, client = _fresh_session(seed=42)
    expired_id = t["expired_renewable_rx_id"]
    for rid in t["renewable_rx_ids"]:
        if rid == expired_id:
            continue  # forget the backtracking target
        _renew(client, sid, rid)
    _refill(client, sid, t["refill_rx_id"])

    result = _evaluate(sm, sid, t)
    assert result["success"] is False


def test_missing_an_expiring_zero_refill_renewal_fails():
    """Only some of the renewal set renewed (an expiring-zero-refill slot
    skipped) — bijection not saturated."""
    sm, sid, t, client = _fresh_session(seed=42)
    skip = t["expiring_zero_refill_rx_ids"][0]
    for rid in t["renewable_rx_ids"]:
        if rid == skip:
            continue
        _renew(client, sid, rid)
    _refill(client, sid, t["refill_rx_id"])

    result = _evaluate(sm, sid, t)
    assert result["success"] is False


def test_skipping_the_refill_fails():
    """Every renewal done but the required refill skipped."""
    sm, sid, t, client = _fresh_session(seed=42)
    for rid in t["renewable_rx_ids"]:
        _renew(client, sid, rid)

    result = _evaluate(sm, sid, t)
    assert result["success"] is False


def test_renewing_the_refill_target_instead_of_refilling_fails():
    """Refill-vs-renewal confusion: the agent renews the medication that should
    have been refilled. refills_remaining and last_filled are then unchanged, so
    the update[1] predicate fails."""
    sm, sid, t, client = _fresh_session(seed=42)
    for rid in t["renewable_rx_ids"]:
        _renew(client, sid, rid)
    _renew(client, sid, t["refill_rx_id"])  # WRONG: renewal, not refill

    result = _evaluate(sm, sid, t)
    assert result["success"] is False


def test_renewing_an_expiring_with_refills_decoy_fails():
    """Everything correct, plus a stray renewal on an expiring-but-refillable
    prescription that should have been left untouched — trips the critical
    prescription-preservation invariant."""
    sm, sid, t, client = _fresh_session(seed=42)
    for rid in t["renewable_rx_ids"]:
        _renew(client, sid, rid)
    _refill(client, sid, t["refill_rx_id"])

    decoy = t["expiring_with_refills_rx_ids"][0]
    _renew(client, sid, decoy)

    result = _evaluate(sm, sid, t)
    assert result["success"] is False
