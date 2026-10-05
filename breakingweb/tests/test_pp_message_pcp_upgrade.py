"""Solvability + difficulty proof for the v2-upgraded pp_message_pcp task.

The upgraded task (medium tier) requires the agent to:
  1. Schedule exactly one appointment with the ASSIGNED PCP (target.pcp_id),
     at that PCP's OWN earliest available slot, with an exact reason. A SECOND
     PCP (a sibling provider in the directory) advertises a strictly-EARLIER
     slot (target.global_earliest_decoy_slot_dt on
     target.global_earliest_decoy_provider_id) — booking the globally-earliest
     PCP slot is the wrong answer; only the assigned PCP's own earliest slot
     scores.
  2. Complete the two-step confirmation workflow (auto_confirm_specialties=[pcp]
     lands the new appointment in confirmation_state="pending"; the agent must
     then POST /appointments/{id}/confirm to reach "confirmed").
  3. Touch nothing else — in particular, one PRE-EXISTING PCP appointment
     (target.pcp_apt_id) is itself seeded requires_confirmation=True /
     confirmation_state="pending". The naive "find the pending PCP appointment
     and confirm it" heuristic confirms the WRONG (pre-existing) row, which is
     a critical, comprehensive appointments-invariant violation. The agent must
     confirm ONLY its own newly-created appointment.

The correct path is driven entirely through the REAL backend mutation
endpoints via TestClient so the proof also confirms every gate is passable.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _create_session():
    # Reuse the app's own SessionManager so the real routes (which read it from
    # request.app.state) and the evaluator operate on the same state object.
    sm: SessionManager = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_message_pcp",
        seed=42,
    )
    state = sm.get_state(sid)
    return sm, sid, dict(targets), state


def _earliest_pcp_slot_iso(state, pcp_id: str) -> str:
    pcp = next(p for p in state.providers if p.id == pcp_id)
    return min(s.datetime for s in pcp.available_slots).isoformat()


def test_difficulty_preconditions_hold():
    """The two v2 discriminators must actually exist for this seed."""
    sm, sid, targets, state = _create_session()
    pcp_id = targets["pcp_id"]

    # Two PCP providers exist; the confirmation workflow is opted in.
    assert state.auto_confirm_specialties == ["pcp"], state.auto_confirm_specialties
    pcps = [p for p in state.providers if p.specialty == "pcp"]
    assert len(pcps) >= 2

    # Trap 1 (grounding): a sibling PCP advertises a strictly-EARLIER slot than
    # the assigned PCP's own earliest slot.
    assigned_earliest = _earliest_pcp_slot_iso(state, pcp_id)
    decoy_dt = targets["global_earliest_decoy_slot_dt"]
    decoy_pid = targets["global_earliest_decoy_provider_id"]
    assert decoy_pid and decoy_pid != pcp_id, (decoy_pid, pcp_id)
    assert decoy_dt < assigned_earliest, (decoy_dt, assigned_earliest)

    # Trap 2 (backtracking/state-tracking): the pre-existing PCP appointment is
    # itself awaiting confirmation — a confirm-the-wrong-one lure.
    pre = next(a for a in state.appointments if a.id == targets["pcp_apt_id"])
    assert pre.requires_confirmation is True
    assert pre.confirmation_state == "pending"
    assert pre.status == "scheduled"
    assert pre.provider_id == pcp_id


def test_correct_trajectory_through_real_endpoints_passes():
    """Schedule the assigned PCP's OWN earliest slot + confirm only the new
    appointment via real endpoints -> pass."""
    sm, sid, targets, state = _create_session()
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_pcp_slot_iso(state, pcp_id)

    client = TestClient(app)

    # Step 1: schedule with the assigned PCP at that PCP's earliest slot.
    create_resp = client.post(
        "/api/env/patient_portal/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": slot_iso,
            "type": "in-person",
            "reason": "Medication side effect review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    new_apt = create_resp.json()
    # auto_confirm_specialties=[pcp] -> the new appointment must land pending.
    assert new_apt["confirmation_state"] == "pending", new_apt
    new_apt_id = new_apt["id"]

    # Step 2: complete the confirmation workflow on the NEW appointment only.
    confirm_resp = client.post(
        f"/api/env/patient_portal/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["confirmation_state"] == "confirmed"

    # Evaluate against the canonical_diff.
    result = evaluate(
        task=get_task("pp_message_pcp"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, result
    # canonical_diff is richer than a 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_booking_globally_earliest_decoy_pcp_slot_fails():
    """Booking the sibling PCP's strictly-earlier slot (the globally-earliest
    PCP slot) instead of the assigned PCP's own earliest slot must fail."""
    sm, sid, targets, state = _create_session()
    decoy_pid = targets["global_earliest_decoy_provider_id"]
    decoy_dt = targets["global_earliest_decoy_slot_dt"]

    client = TestClient(app)
    create_resp = client.post(
        "/api/env/patient_portal/appointments/create",
        json={
            "session_id": sid,
            "provider_id": decoy_pid,
            "slot_datetime": decoy_dt,
            "type": "in-person",
            "reason": "Medication side effect review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    new_apt_id = create_resp.json()["id"]
    client.post(
        f"/api/env/patient_portal/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )

    result = evaluate(
        task=get_task("pp_message_pcp"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"globally-earliest decoy PCP slot should fail: {result}"
    )


def test_confirming_preexisting_pending_pcp_appointment_fails():
    """Correct create+confirm, but ALSO confirming the pre-existing pending PCP
    appointment violates the critical comprehensive appointments invariant."""
    sm, sid, targets, state = _create_session()
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_pcp_slot_iso(state, pcp_id)

    client = TestClient(app)
    create_resp = client.post(
        "/api/env/patient_portal/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": slot_iso,
            "type": "in-person",
            "reason": "Medication side effect review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    new_apt_id = create_resp.json()["id"]
    client.post(
        f"/api/env/patient_portal/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )

    # The confirm-the-wrong-one trap: confirm the PRE-EXISTING pending PCP appt.
    wrong_confirm = client.post(
        f"/api/env/patient_portal/appointments/{targets['pcp_apt_id']}/confirm",
        json={"session_id": sid},
    )
    assert wrong_confirm.status_code == 200, wrong_confirm.text

    result = evaluate(
        task=get_task("pp_message_pcp"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"confirming a pre-existing appointment should fail: {result}"
    )


def test_only_confirming_preexisting_without_creating_own_fails():
    """Confirming the seeded pending PCP appointment and never creating one's
    own appointment must fail (no positive create, plus an invariant hit)."""
    sm, sid, targets, state = _create_session()

    client = TestClient(app)
    wrong_confirm = client.post(
        f"/api/env/patient_portal/appointments/{targets['pcp_apt_id']}/confirm",
        json={"session_id": sid},
    )
    assert wrong_confirm.status_code == 200, wrong_confirm.text

    result = evaluate(
        task=get_task("pp_message_pcp"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"confirming only the pre-existing appointment should fail: {result}"
    )


def test_scheduled_but_not_confirmed_fails():
    """Skipping the confirmation step must fail (confirmation_state != confirmed)."""
    sm, sid, targets, state = _create_session()
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_pcp_slot_iso(state, pcp_id)

    client = TestClient(app)

    create_resp = client.post(
        "/api/env/patient_portal/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": slot_iso,
            "type": "in-person",
            "reason": "Medication side effect review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    assert create_resp.json()["confirmation_state"] == "pending"
    # Deliberately DO NOT confirm.

    result = evaluate(
        task=get_task("pp_message_pcp"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"should fail without confirm: {result}"


def test_wrong_pcp_fails():
    """Booking with the OTHER PCP (not the assigned one) must fail."""
    sm, sid, targets, state = _create_session()
    pcp_id = targets["pcp_id"]
    other_pcp = next(
        p for p in state.providers if p.specialty == "pcp" and p.id != pcp_id
    )
    slot_iso = min(s.datetime for s in other_pcp.available_slots).isoformat()

    client = TestClient(app)

    create_resp = client.post(
        "/api/env/patient_portal/appointments/create",
        json={
            "session_id": sid,
            "provider_id": other_pcp.id,
            "slot_datetime": slot_iso,
            "type": "in-person",
            "reason": "Medication side effect review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    new_apt_id = create_resp.json()["id"]
    client.post(
        f"/api/env/patient_portal/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )

    result = evaluate(
        task=get_task("pp_message_pcp"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"wrong PCP should fail: {result}"


def test_cancelling_existing_appointment_fails():
    """Correct booking + confirm, but ALSO cancelling a pre-existing appointment
    must fail the critical, comprehensive appointments invariant."""
    sm, sid, targets, state = _create_session()
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_pcp_slot_iso(state, pcp_id)
    existing_scheduled = next(
        a.id for a in state.appointments if a.status == "scheduled"
    )

    client = TestClient(app)

    create_resp = client.post(
        "/api/env/patient_portal/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": slot_iso,
            "type": "in-person",
            "reason": "Medication side effect review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    new_apt_id = create_resp.json()["id"]
    client.post(
        f"/api/env/patient_portal/appointments/{new_apt_id}/confirm",
        json={"session_id": sid},
    )

    # Side-effect: cancel a pre-existing appointment.
    cancel_resp = client.post(
        f"/api/env/patient_portal/appointments/{existing_scheduled}/cancel",
        json={"session_id": sid},
    )
    assert cancel_resp.status_code == 200, cancel_resp.text

    result = evaluate(
        task=get_task("pp_message_pcp"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"cancelling existing apt should fail: {result}"
