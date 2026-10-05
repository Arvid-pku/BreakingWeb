"""Solvability + correctness proof for the hardened pp_request_referral_preauth.

The hardened task requires the agent to:
  1. Identify the SINGLE schedulable approved referral (status approved AND, where
     pre-auth is required, pre-auth approved) — rejecting the approved-but-
     pre-auth-pending decoys, INCLUDING one in the SAME specialty (dermatology)
     as the eligible referral, so specialty-only pattern-matching links the wrong
     referral and fails.
  2. In that referral's specialty, pick a provider that is ACCEPTING new patients
     (rejecting the TWO closed-panel decoy providers, one of which holds a
     strictly-earlier slot).
  3. Book the EARLIEST slot offered by an accepting provider in that specialty.
  4. Link the new appointment to the schedulable referral.
  5. Confirm the appointment (the specialty is in auto_confirm_specialties, so the
     backend lands the create as confirmation_state='pending' and a second
     POST .../confirm is required). The instruction now explicitly states the
     confirmation step, so this is a discoverable, fair backtracking requirement.

The correct solution is driven through the REAL backend endpoints
(POST /appointments/create then POST /appointments/{id}/confirm) so the test also
proves the referral/pre-auth gate is passable with the seeded answer.
"""

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_request_referral_preauth"
ENV_PREFIX = "/api/env/patient_portal"


def _new_session():
    """Create a session via the app's own SessionManager (the one the endpoints
    use) and return (client, session_id, targets, session_manager)."""
    client = TestClient(app)
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=42
    )
    return client, sid, dict(targets), sm


def _correct_provider_id(targets, state):
    """The accepting provider in the eligible specialty offering the earliest slot."""
    pid = targets["earliest_slot_provider_ids"][0]
    prov = state.get_provider(pid)
    assert prov is not None
    assert prov.accepting_new is True
    assert prov.specialty == targets["eligible_specialty"]
    return pid


def test_correct_trajectory_via_endpoints_passes():
    client, sid, targets, sm = _new_session()
    state = sm.get_state(sid)

    provider_id = _correct_provider_id(targets, state)
    slot_dt = targets["earliest_slot_dt"]
    eligible_ref = targets["eligible_ref_id"]

    # Sanity: the eligible referral is dermatology, approved, pre-auth approved.
    ref = next(r for r in state.referrals if r.id == eligible_ref)
    assert ref.status == "approved"
    assert ref.to_specialty == targets["eligible_specialty"]
    assert (not ref.prior_auth_required) or ref.prior_auth_status == "approved"
    # The decoys are approved but pre-auth pending.
    for did in targets["preauth_pending_ref_ids"]:
        d = next(r for r in state.referrals if r.id == did)
        assert d.status == "approved" and d.prior_auth_status == "pending"
    # There is a SAME-SPECIALTY (dermatology) approved-but-pre-auth-pending decoy
    # in the ineligible set — the new backtracking trap. It must NOT be the
    # eligible referral, and it must share the eligible specialty.
    same_spec_decoys = [
        r
        for r in state.referrals
        if r.id in targets["ineligible_approved_ref_ids"]
        and r.to_specialty == targets["eligible_specialty"]
    ]
    assert same_spec_decoys, "expected a same-specialty pre-auth-pending decoy referral"
    for d in same_spec_decoys:
        assert d.id != eligible_ref
        assert d.status == "approved"
        assert d.prior_auth_required and d.prior_auth_status == "pending"

    # Step 1: create the appointment through the gated endpoint.
    create_resp = client.post(
        f"{ENV_PREFIX}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": provider_id,
            "slot_datetime": slot_dt,
            "type": "in-person",
            "reason": "Dermatology specialist consultation",
            "linked_referral_id": eligible_ref,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    apt = create_resp.json()
    new_apt_id = apt["id"]
    # auto_confirm_specialties includes dermatology -> create lands pending.
    assert apt["requires_confirmation"] is True
    assert apt["confirmation_state"] == "pending"

    # Step 2: confirm the appointment (two-step workflow).
    confirm_resp = client.post(
        f"{ENV_PREFIX}/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["confirmation_state"] == "confirmed"

    # Evaluate via the real evaluator entry point.
    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"


def test_closed_panel_provider_with_earlier_slot_fails():
    """Near-miss: book the closed-panel (not-accepting) dermatology provider's
    strictly-earlier slot. The backend gate accepts it (it does not check
    accepting_new), but the canonical_diff must reject it."""
    client, sid, targets, sm = _new_session()
    state = sm.get_state(sid)

    # Find the non-accepting dermatology provider and its earliest slot.
    closed_providers = [
        p for p in state.providers
        if p.specialty == targets["eligible_specialty"] and not p.accepting_new
    ]
    # The upgrade widens the closed-panel haystack to TWO non-accepting derm providers.
    assert len(closed_providers) >= 2, "expected >=2 closed-panel dermatology providers"
    closed = closed_providers[0]
    closed_slot = min(s.datetime.isoformat() for s in closed.available_slots)
    # It must be strictly earlier than the correct earliest accepting slot.
    assert closed_slot < targets["earliest_slot_dt"]

    create_resp = client.post(
        f"{ENV_PREFIX}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": closed.id,
            "slot_datetime": closed_slot,
            "type": "in-person",
            "reason": "Dermatology specialist consultation",
            "linked_referral_id": targets["eligible_ref_id"],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    new_apt_id = create_resp.json()["id"]
    client.post(
        f"{ENV_PREFIX}/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result should fail: {result}"


def test_unconfirmed_appointment_fails():
    """Near-miss: correct provider/slot/referral but the agent forgets the
    second-step confirmation. confirmation_state stays 'pending' -> fail."""
    client, sid, targets, sm = _new_session()
    state = sm.get_state(sid)

    provider_id = _correct_provider_id(targets, state)
    create_resp = client.post(
        f"{ENV_PREFIX}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": provider_id,
            "slot_datetime": targets["earliest_slot_dt"],
            "type": "in-person",
            "reason": "Dermatology specialist consultation",
            "linked_referral_id": targets["eligible_ref_id"],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    # Deliberately do NOT confirm.

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result should fail: {result}"


def test_same_specialty_preauth_pending_decoy_link_fails():
    """Near-miss: book the correct accepting provider + earliest slot + confirm,
    but link the SAME-SPECIALTY approved-but-pre-auth-pending decoy referral
    instead of the eligible one. The backend create gate still accepts the
    booking (it resolves the FIRST approved dermatology referral — the eligible
    one — independent of linked_referral_id), but the canonical_diff pins the
    exact eligible_ref_id and excludes the ineligible set, so it must fail."""
    client, sid, targets, sm = _new_session()
    state = sm.get_state(sid)

    # The same-specialty decoy: approved, dermatology, pre-auth pending, != eligible.
    decoy = next(
        r
        for r in state.referrals
        if r.id in targets["ineligible_approved_ref_ids"]
        and r.to_specialty == targets["eligible_specialty"]
        and r.id != targets["eligible_ref_id"]
    )

    provider_id = _correct_provider_id(targets, state)
    create_resp = client.post(
        f"{ENV_PREFIX}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": provider_id,
            "slot_datetime": targets["earliest_slot_dt"],
            "type": "in-person",
            "reason": "Dermatology specialist consultation",
            "linked_referral_id": decoy.id,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    new_apt_id = create_resp.json()["id"]
    client.post(
        f"{ENV_PREFIX}/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result should fail: {result}"


def test_preauth_pending_referral_specialty_is_gate_blocked():
    """The approved-but-pre-auth-pending decoy referral cannot be scheduled at
    all: the backend create gate rejects it with 422. This proves the decoys are
    genuine traps, not just diff-level losers."""
    client, sid, targets, sm = _new_session()
    state = sm.get_state(sid)

    decoy_ref_id = targets["preauth_pending_ref_ids"][0]
    decoy = next(r for r in state.referrals if r.id == decoy_ref_id)
    # Find an accepting provider in the decoy's specialty with a slot.
    prov = next(
        (
            p for p in state.providers
            if p.specialty == decoy.to_specialty and p.accepting_new and p.available_slots
        ),
        None,
    )
    assert prov is not None, "expected a bookable provider in the decoy specialty"
    slot = min(s.datetime.isoformat() for s in prov.available_slots)

    create_resp = client.post(
        f"{ENV_PREFIX}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": prov.id,
            "slot_datetime": slot,
            "type": "in-person",
            "reason": f"{decoy.to_specialty} consultation",
            "linked_referral_id": decoy_ref_id,
        },
    )
    # Gate rejects: approved referral exists but pre-auth is pending.
    assert create_resp.status_code == 422, create_resp.text
    assert "pre-auth" in create_resp.text.lower() or "authorization" in create_resp.text.lower()
