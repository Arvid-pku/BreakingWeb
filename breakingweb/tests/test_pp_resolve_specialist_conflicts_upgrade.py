"""Solvability proof for the HARDENED pp_resolve_specialist_conflicts task.

Upgrade levers exercised here (v2):
  * THREE overlapping conflict appointments — the most-recently-booked must be
    re-derived from booked_at across >2 candidates (target['later_booked_apt_id']).
  * Destination is the earliest SAME-VISIT-TYPE slot (target['type_matched_slot']).
    In v2 this is GUARANTEED to differ from the provider's bare-earliest slot in
    EVERY seed: the builder injects a strictly-earlier telehealth decoy one hour
    before the earliest in-person slot (conflict_guarantee_type_trap), so the
    bare-earliest slot is ALWAYS the wrong visit type and the agent MUST filter
    slots by visit type before taking min().
  * datetime freshness gate (>= session_start).
  * Branch B's replacement must be CONFIRMED (auto_confirm specialty) — a single
    create call is insufficient; the agent must also call /confirm.
  * A provider-grounding decoy (4th upcoming appointment sharing the later-booked
    conflict's provider at a distinct datetime, conflict_provider_grounding_decoy)
    is frozen by the critical sibling invariant — an agent that grounds on
    "the appointment with provider X" touches the wrong row.
  * The one mutated collection is filtered so both earlier-booked conflicts, the
    provider-grounding decoy, and every other upcoming appointment are frozen;
    sibling invariant escalated to severity:critical.

Both `oneof` branches are driven through the REAL backend REST endpoints via
TestClient (reschedule for Branch A; cancel + create + confirm for Branch B),
confirming achievability past the slot/referral/confirmation gates. WRONG
near-misses (bare-earliest wrong-type slot; unconfirmed rebook; moved the
earliest-booked conflict; moved the provider-grounding decoy) are asserted to
FAIL.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

ENV = "patient_portal"
TASK = "pp_resolve_specialist_conflicts"
BASE = f"/api/env/{ENV}"


def _create_session(client: TestClient, seed: int = 42):
    """Create a session via the app's own SessionManager so TestClient drives it."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id=ENV, task_id=TASK, seed=seed)
    targets = dict(targets)
    return sm, sid, targets


def _later_apt(state, targets):
    return next(a for a in state.appointments if a.id == targets["later_booked_apt_id"])


def test_seed_targets_are_well_formed():
    sm, sid, targets = _create_session(TestClient(app))
    state = sm.get_state(sid)
    cluster = targets["conflict_apt_ids"]
    assert len(cluster) == 3, f"expected a 3-appointment conflict cluster, got {cluster}"
    apts = {a.id: a for a in state.appointments}
    # later_booked_apt_id is the most-recently-booked of the cluster (booked_at, id).
    true_max = max(cluster, key=lambda c: (apts[c].booked_at, c))
    assert targets["later_booked_apt_id"] == true_max
    # type_matched_slot must exist and match the appointment's visit type.
    la = apts[targets["later_booked_apt_id"]]
    assert targets["later_booked_type"] == la.type
    assert targets["type_matched_slot"] is not None
    prov = next(p for p in state.providers if p.id == la.provider_id)
    same_type = sorted(s.datetime.isoformat() for s in prov.available_slots if s.type == la.type)
    assert targets["type_matched_slot"] == same_type[0]
    # v2: the provider-grounding decoy is a distinct upcoming appt with the
    # SAME provider as the later-booked conflict but is NOT a cluster member.
    decoy_id = targets["provider_decoy_apt_id"]
    assert decoy_id is not None
    assert decoy_id not in cluster
    assert decoy_id != targets["later_booked_apt_id"]
    assert apts[decoy_id].provider_id == la.provider_id
    assert apts[decoy_id].status == "scheduled"


def test_type_matched_trap_is_guaranteed_every_seed():
    """v2 guarantee: the bare-earliest slot is ALWAYS a wrong-type telehealth
    decoy strictly distinct from the type-matched destination, so the trap can
    never collapse to a no-op (the v1 'didn't bite' root cause)."""
    sm = app.state.session_manager
    for seed in (1, 7, 13, 23, 42, 55, 71):
        sid, targets, _ = sm.create_session(env_id=ENV, task_id=TASK, seed=seed)
        targets = dict(targets)
        state = sm.get_state(sid)
        apts = {a.id: a for a in state.appointments}
        la = apts[targets["later_booked_apt_id"]]
        prov = next(p for p in state.providers if p.id == la.provider_id)
        bare = min(s.datetime.isoformat() for s in prov.available_slots)
        bare_slot = next(s for s in prov.available_slots if s.datetime.isoformat() == bare)
        assert bare != targets["type_matched_slot"], (
            f"seed={seed}: trap collapsed (bare-earliest == type-matched)"
        )
        assert bare_slot.type != la.type, (
            f"seed={seed}: bare-earliest slot type {bare_slot.type} is not the trap type"
        )
        assert bare == targets["bare_earliest_slot"]


def test_branch_a_reschedule_in_place_passes():
    """Correct Branch A: in-place reschedule to the earliest same-type slot."""
    client = TestClient(app)
    sm, sid, targets = _create_session(client)
    state = sm.get_state(sid)
    later_id = targets["later_booked_apt_id"]

    resp = client.post(
        f"{BASE}/appointments/{later_id}/reschedule",
        json={"session_id": sid, "new_slot_datetime": targets["type_matched_slot"]},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(task=get_task(TASK), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"


def test_branch_b_cancel_rebook_and_confirm_passes():
    """Correct Branch B: cancel the later-booked, create a same-type replacement, confirm it."""
    client = TestClient(app)
    sm, sid, targets = _create_session(client)
    state = sm.get_state(sid)
    later = _later_apt(state, targets)

    # Cancel the most-recently-booked conflict.
    cancel = client.post(
        f"{BASE}/appointments/{later.id}/cancel",
        json={"session_id": sid, "reason": "Resolving overlapping schedule"},
    )
    assert cancel.status_code == 200, cancel.text

    # Re-book with the same provider at the earliest same-visit-type slot.
    create = client.post(
        f"{BASE}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": targets["later_booked_provider_id"],
            "slot_datetime": targets["type_matched_slot"],
            "type": targets["later_booked_type"],
            "reason": "Follow-up",
        },
    )
    assert create.status_code == 200, create.text
    new_apt = create.json()
    assert new_apt["confirmation_state"] == "pending", new_apt

    # The specialty is in auto_confirm_specialties, so a confirm step is required.
    confirm = client.post(
        f"{BASE}/appointments/{new_apt['id']}/confirm",
        json={"session_id": sid},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["confirmation_state"] == "confirmed"

    state = sm.get_state(sid)
    result = evaluate(task=get_task(TASK), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"


def test_branch_b_without_confirm_fails():
    """Near-miss: cancel + rebook the right slot but SKIP the confirm step -> fail."""
    client = TestClient(app)
    sm, sid, targets = _create_session(client)
    state = sm.get_state(sid)
    later = _later_apt(state, targets)

    client.post(
        f"{BASE}/appointments/{later.id}/cancel",
        json={"session_id": sid, "reason": "Resolving overlap"},
    )
    create = client.post(
        f"{BASE}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": targets["later_booked_provider_id"],
            "slot_datetime": targets["type_matched_slot"],
            "type": targets["later_booked_type"],
            "reason": "Follow-up",
        },
    )
    assert create.status_code == 200, create.text
    # Deliberately do NOT confirm.

    state = sm.get_state(sid)
    result = evaluate(task=get_task(TASK), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"unconfirmed rebook should fail: {result}"


def test_wrong_slot_bare_earliest_fails():
    """Near-miss: reschedule to the provider's bare-earliest slot (wrong visit type) -> fail.

    Only meaningful when the seed's bare-earliest slot diverges from the
    type-matched slot; for the canonical seed=42 it does (telehealth earlier
    than the earliest in-person slot).
    """
    client = TestClient(app)
    sm, sid, targets = _create_session(client)
    state = sm.get_state(sid)
    later = _later_apt(state, targets)
    prov = next(p for p in state.providers if p.id == later.provider_id)
    bare_earliest = min(s.datetime.isoformat() for s in prov.available_slots)
    assert bare_earliest != targets["type_matched_slot"], (
        "seed must have a diverging bare-earliest trap for this assertion"
    )

    resp = client.post(
        f"{BASE}/appointments/{later.id}/reschedule",
        json={"session_id": sid, "new_slot_datetime": bare_earliest},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(task=get_task(TASK), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"wrong-type slot should fail: {result}"


def test_wrong_appointment_moved_fails():
    """Near-miss: reschedule the EARLIEST-booked conflict instead of the latest -> fail."""
    client = TestClient(app)
    sm, sid, targets = _create_session(client)
    state = sm.get_state(sid)
    apts = {a.id: a for a in state.appointments}
    cluster = targets["conflict_apt_ids"]
    earliest_booked = min(cluster, key=lambda c: (apts[c].booked_at, c))
    assert earliest_booked != targets["later_booked_apt_id"]
    wrong = apts[earliest_booked]
    prov = next(p for p in state.providers if p.id == wrong.provider_id)
    same_type = sorted(s.datetime.isoformat() for s in prov.available_slots if s.type == wrong.type)
    assert same_type, "wrong-conflict provider needs a same-type slot to attempt the move"

    resp = client.post(
        f"{BASE}/appointments/{wrong.id}/reschedule",
        json={"session_id": sid, "new_slot_datetime": same_type[0]},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(task=get_task(TASK), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"moving the wrong conflict should fail: {result}"


def test_wrong_provider_grounding_decoy_moved_fails():
    """Near-miss (v2): an agent that grounds on 'the appointment with provider X'
    moves the 4th non-cluster appointment that merely shares the later-booked
    conflict's provider -> fail (and it trips the critical sibling invariant)."""
    client = TestClient(app)
    sm, sid, targets = _create_session(client)
    state = sm.get_state(sid)
    decoy_id = targets["provider_decoy_apt_id"]
    decoy = next(a for a in state.appointments if a.id == decoy_id)
    assert decoy_id != targets["later_booked_apt_id"]
    prov = next(p for p in state.providers if p.id == decoy.provider_id)
    # Move it to the type-matched destination (the otherwise-correct slot) so
    # the only error is operating on the WRONG appointment row.
    resp = client.post(
        f"{BASE}/appointments/{decoy_id}/reschedule",
        json={"session_id": sid, "new_slot_datetime": targets["type_matched_slot"]},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(task=get_task(TASK), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"moving the provider decoy should fail: {result}"
