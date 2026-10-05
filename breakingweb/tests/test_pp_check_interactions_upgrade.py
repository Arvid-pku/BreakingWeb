"""Solvability proof for the hardened pp_check_interactions task.

The medium→hard upgrade requires the agent to:
  1. Identify the single ACTIVE↔ACTIVE interacting prescription pair (ignoring
     TWO tempting decoy interactions whose partner is EXPIRED).
  2. Schedule exactly one PCP follow-up at the EARLIEST available PCP slot.
  3. CONFIRM that appointment (auto_confirm_specialties=[pcp] → two-step
     workflow).
  4. Use a reason that begins with "Drug interaction review:" and names BOTH
     active interacting medications EXACTLY as listed (including strength).

The correct solution is driven through the REAL backend route handlers
(`create_appointment` + `confirm_appointment`), exercising the slot-consumption
and confirmation-state machinery, then graded through the canonical_diff
evaluator. Near-miss (unconfirmed), wrong (decoy meds in reason), wrong-slot,
and dosage-stripped-name trajectories are asserted to FAIL.
"""

from __future__ import annotations

from breakingweb.backend.routes.patient_portal import (
    CreateAppointmentRequest,
    SessionScopedRequest,
    create_appointment,
    confirm_appointment,
)
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _bootstrap(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_check_interactions",
        seed=seed,
    )
    state = sm.get_state(sid)
    return sm, sid, dict(targets), state


def _earliest_pcp_slot(state, pcp_id: str) -> str:
    pcp = next(p for p in state.providers if p.id == pcp_id)
    return min(s.datetime for s in pcp.available_slots).isoformat()


def _derive_active_pair_meds(state) -> list[str]:
    """Independently re-derive the active↔active interacting medication pair
    from raw state, exactly as a solving agent must (no peeking at targets).

    Asserts the pair is UNIQUE: with two expired-interaction decoys now wired
    into the cabinet, several active prescriptions carry a non-empty
    ``interactions`` list, but only ONE conflict has both members active. An
    agent (or grader) that requires mutual active↔active membership lands on a
    single answer.
    """
    active = {r.id: r for r in state.prescriptions if r.status == "active"}
    by_med = {r.medication: r for r in active.values()}
    found: set[tuple[str, str]] = set()
    for rx in active.values():
        for partner_med in rx.interactions:
            partner = by_med.get(partner_med)
            if partner is not None and rx.medication in partner.interactions:
                found.add(tuple(sorted([rx.medication, partner.medication])))
    assert len(found) == 1, f"expected exactly one active-active pair, got {found}"
    return sorted(found.pop())


def test_correct_trajectory_via_backend_passes():
    sm, sid, targets, state = _bootstrap()

    # Agent re-derives the active pair from raw state and confirms it matches
    # the seeded answer (the decoy interaction has an expired partner so is
    # excluded).
    derived = _derive_active_pair_meds(state)
    assert derived == sorted(targets["interacting_medications"])

    pcp_id = targets["pcp_id"]
    slot = _earliest_pcp_slot(state, pcp_id)
    meds = targets["interacting_medications"]
    reason = f"Drug interaction review: {meds[0]} and {meds[1]}"

    # Step 1: schedule the PCP follow-up through the real route. The PCP
    # specialty bypasses the referral gate; auto_confirm_specialties=[pcp]
    # lands it in confirmation_state="pending".
    created = create_appointment(
        CreateAppointmentRequest(
            session_id=sid,
            provider_id=pcp_id,
            slot_datetime=slot,
            type="in-person",
            reason=reason,
        ),
        session_manager=sm,
    )
    assert created["confirmation_state"] == "pending"
    apt_id = created["id"]

    # Step 2: confirm it (the required second step).
    confirmed = confirm_appointment(
        apt_id,
        SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )
    assert confirmed["confirmation_state"] == "confirmed"

    result = evaluate(
        task=get_task("pp_check_interactions"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"


def test_unconfirmed_appointment_fails():
    """Skipping the CONFIRM step is a near-miss: confirmation_state stays
    'pending', so create[0] (which pins confirmed) does not match."""
    sm, sid, targets, state = _bootstrap()
    pcp_id = targets["pcp_id"]
    slot = _earliest_pcp_slot(state, pcp_id)
    meds = targets["interacting_medications"]
    reason = f"Drug interaction review: {meds[0]} and {meds[1]}"

    create_appointment(
        CreateAppointmentRequest(
            session_id=sid,
            provider_id=pcp_id,
            slot_datetime=slot,
            type="in-person",
            reason=reason,
        ),
        session_manager=sm,
    )
    # Intentionally do NOT confirm.

    result = evaluate(
        task=get_task("pp_check_interactions"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False


def test_wrong_decoy_meds_in_reason_fails():
    """Naming the DECOY interaction's medications (one expired) instead of the
    genuine active pair fails the reason discriminator."""
    sm, sid, targets, state = _bootstrap()
    pcp_id = targets["pcp_id"]
    slot = _earliest_pcp_slot(state, pcp_id)

    rxmap = {r.id: r for r in state.prescriptions}
    decoy_meds = [rxmap[rid].medication for rid in targets["decoy_interaction_rx_ids"]]
    # Ensure the decoy meds are genuinely different from the active pair.
    assert set(decoy_meds) != set(targets["interacting_medications"])
    reason = f"Drug interaction review: {decoy_meds[0]} and {decoy_meds[1]}"

    created = create_appointment(
        CreateAppointmentRequest(
            session_id=sid,
            provider_id=pcp_id,
            slot_datetime=slot,
            type="in-person",
            reason=reason,
        ),
        session_manager=sm,
    )
    confirm_appointment(
        created["id"],
        SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )

    result = evaluate(
        task=get_task("pp_check_interactions"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False


def test_second_decoy_distinct_and_in_reason_fails():
    """The hardened cabinet wires a SECOND expired-interaction decoy. It must be
    distinct from the genuine pair and the first decoy, and naming its
    medications in the reason must fail the discriminator."""
    sm, sid, targets, state = _bootstrap()

    first = targets["decoy_interaction_rx_ids"]
    second = targets["second_decoy_interaction_rx_ids"]
    # Two distinct decoy traps were seeded.
    assert second, "second_decoy_interaction_rx_ids should be populated"
    assert set(first) != set(second)
    assert set(first).isdisjoint(set(second))
    assert set(targets["interacting_rx_ids"]).isdisjoint(set(first) | set(second))

    pcp_id = targets["pcp_id"]
    slot = _earliest_pcp_slot(state, pcp_id)
    rxmap = {r.id: r for r in state.prescriptions}
    second_meds = [rxmap[rid].medication for rid in second]
    assert set(second_meds) != set(targets["interacting_medications"])
    reason = f"Drug interaction review: {second_meds[0]} and {second_meds[1]}"

    created = create_appointment(
        CreateAppointmentRequest(
            session_id=sid,
            provider_id=pcp_id,
            slot_datetime=slot,
            type="in-person",
            reason=reason,
        ),
        session_manager=sm,
    )
    confirm_appointment(
        created["id"],
        SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )

    result = evaluate(
        task=get_task("pp_check_interactions"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False


def test_dosage_stripped_names_fail():
    """The reason discriminator requires the medication strings EXACTLY as
    listed (with strength). The instruction discloses this requirement, so a
    reason that names the bare drug (no dosage) is a legitimate near-miss that
    must FAIL — this keeps the reason field a strict proof of identification."""
    sm, sid, targets, state = _bootstrap()
    pcp_id = targets["pcp_id"]
    slot = _earliest_pcp_slot(state, pcp_id)
    meds = targets["interacting_medications"]
    # Strip the strength suffix (everything after the first space).
    bare = [m.split(" ")[0] for m in meds]
    assert bare != meds, "test fixture expects dosage-bearing medication names"
    reason = f"Drug interaction review: {bare[0]} and {bare[1]}"

    created = create_appointment(
        CreateAppointmentRequest(
            session_id=sid,
            provider_id=pcp_id,
            slot_datetime=slot,
            type="in-person",
            reason=reason,
        ),
        session_manager=sm,
    )
    confirm_appointment(
        created["id"],
        SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )

    result = evaluate(
        task=get_task("pp_check_interactions"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False


def test_wrong_slot_fails():
    """Booking a later PCP slot (not the earliest) fails the datetime expr."""
    sm, sid, targets, state = _bootstrap()
    pcp_id = targets["pcp_id"]
    pcp = next(p for p in state.providers if p.id == pcp_id)
    later = sorted(s.datetime for s in pcp.available_slots)[1].isoformat()
    meds = targets["interacting_medications"]
    reason = f"Drug interaction review: {meds[0]} and {meds[1]}"

    created = create_appointment(
        CreateAppointmentRequest(
            session_id=sid,
            provider_id=pcp_id,
            slot_datetime=later,
            type="in-person",
            reason=reason,
        ),
        session_manager=sm,
    )
    confirm_appointment(
        created["id"],
        SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )

    result = evaluate(
        task=get_task("pp_check_interactions"),
        server_state=sm.get_state(sid),
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False
