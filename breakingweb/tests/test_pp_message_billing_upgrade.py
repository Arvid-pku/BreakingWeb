"""Solvability proof for the hardened pp_message_billing task.

Drives the CORRECT solution through the REAL patient-portal backend endpoints
(starlette TestClient over breakingweb.app:app), confirming the upgraded task is
achievable past its two-step confirmation workflow and computed-reason gate,
then asserts the canonical evaluator passes. A near-miss trajectory (wrong
provider / unconfirmed / wrong reason) must fail.

Levers exercised by the upgrade:
  1. Two billing providers — the agent must find the globally-earliest billing
     slot across BOTH providers (re-derived min-slot discriminator) and the
     canonical answer pins the exact owning provider.
  2. Two-step confirmation workflow (auto_confirm_specialties=[billing]) — the
     created appointment lands confirmation_state="pending"; the agent must
     POST /appointments/{id}/confirm to reach "confirmed".
  3. Claim-derived reason string — the agent must locate the most-recent
     approved claim, read its patient balance, and format an exact reason.
  4. Freshness (booked_at >= session_start) + narrowed appointment invariant
     (only the new billing appointment may appear) + critical claim/referral
     siblings.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

BASE = "/api/env/patient_portal"


def _new_session(seed: int = 42):
    """Create a session on the app's shared SessionManager and return
    (client, session_manager, session_id, targets)."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_message_billing",
        seed=seed,
    )
    client = TestClient(app)
    return client, sm, sid, dict(targets)


def _earliest_billing_slot(state, billing_provider_ids):
    """Independently recompute the (datetime_iso, provider_id, slot_type) of the
    single earliest available slot across all billing providers."""
    candidates = []
    for p in state.providers:
        if p.id in billing_provider_ids:
            for s in p.available_slots:
                candidates.append((s.datetime.isoformat(), p.id, s.type))
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0]


def _most_recent_approved_claim(state):
    """Independently recompute the canonical answer claim: the most-recent
    approved claim that still has a POSITIVE patient balance (latest service
    date, claim-id tiebreaker ascending). Fully-covered ($0) approved claims —
    which the upgrade pins to a LATER service date — are deliberately excluded,
    so a naive "latest approved claim" picks a wrong $0 decoy."""
    positive_approved = [
        c
        for c in state.claims
        if c.status == "approved" and float(c.patient_responsibility) > 0
    ]
    positive_approved.sort(key=lambda c: (c.service_date.isoformat(), c.id))
    return positive_approved[-1]


def _latest_zero_resp_approved_claim(state):
    """The later-dated fully-covered ($0 balance) approved decoy — the trap an
    agent falls into if it picks "the most recent approved claim" by date."""
    zero = [
        c
        for c in state.claims
        if c.status == "approved" and float(c.patient_responsibility) == 0
    ]
    zero.sort(key=lambda c: (c.service_date.isoformat(), c.id))
    return zero[-1] if zero else None


def test_correct_trajectory_passes_via_real_backend():
    client, sm, sid, targets = _new_session(seed=42)
    state = sm.get_state(sid)

    billing_ids = targets["billing_provider_ids"]
    assert len(billing_ids) == 2, "upgrade must seed exactly two billing providers"

    # --- Re-derive the discriminators the way an agent would ---
    earliest_dt, earliest_pid, earliest_type = _earliest_billing_slot(
        state, billing_ids
    )
    assert earliest_dt == targets["billing_earliest_slot_datetime"]
    assert earliest_pid == targets["billing_earliest_slot_provider_id"]

    # The cross-provider trap must be live: the globally-earliest slot belongs
    # to the SECOND-listed billing provider and is strictly earlier (by minutes)
    # than the first billing provider's earliest slot — so an agent that stops
    # at the first provider books the wrong (later) slot / wrong provider.
    assert earliest_pid == billing_ids[1], (
        "global earliest billing slot must belong to the second billing provider"
    )
    first_prov = next(p for p in state.providers if p.id == billing_ids[0])
    first_earliest = min(s.datetime for s in first_prov.available_slots)
    second_prov = next(p for p in state.providers if p.id == billing_ids[1])
    second_earliest = min(s.datetime for s in second_prov.available_slots)
    assert second_earliest < first_earliest, (
        "second billing provider must hold the strictly-earliest slot"
    )

    mra = _most_recent_approved_claim(state)
    assert mra.id == targets["most_recent_approved_claim_id"]
    assert float(mra.patient_responsibility) > 0, (
        "answer claim must have a positive balance, not a $0 fully-covered decoy"
    )
    # The trap must exist: a later-dated fully-covered ($0) approved decoy that a
    # naive "latest approved claim by date" would wrongly select.
    zero_decoy = _latest_zero_resp_approved_claim(state)
    assert zero_decoy is not None
    assert zero_decoy.service_date > mra.service_date, (
        "the $0 approved decoy must be MORE RECENT than the answer claim"
    )
    assert float(zero_decoy.patient_responsibility) == 0
    balance = mra.model_dump(mode="json")["patient_responsibility"]
    reason = (
        f"Incorrect charge review for claim {mra.id} "
        f"(patient balance ${balance})"
    )
    assert reason == targets["billing_followup_reason"]

    # --- Step 1: schedule the billing follow-up via the real endpoint ---
    resp = client.post(
        f"{BASE}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": earliest_pid,
            "slot_datetime": earliest_dt,
            "type": earliest_type,
            "reason": reason,
        },
    )
    assert resp.status_code == 200, resp.text
    apt = resp.json()
    apt_id = apt["id"]
    # auto_confirm_specialties=[billing] -> lands pending, not yet confirmed.
    assert apt["confirmation_state"] == "pending"
    assert apt["requires_confirmation"] is True

    # --- Step 2: confirm the appointment (two-step workflow) ---
    resp = client.post(
        f"{BASE}/appointments/{apt_id}/confirm",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["confirmation_state"] == "confirmed"

    # --- Evaluate the canonical diff against the live state ---
    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_message_billing"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    # canonical_diff is richer than a legacy 2-check eval.
    assert (
        len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2
    )


def test_unconfirmed_appointment_fails():
    """Scheduling without the mandatory confirm step must fail (lever 2)."""
    client, sm, sid, targets = _new_session(seed=42)
    state = sm.get_state(sid)
    earliest_dt, earliest_pid, earliest_type = _earliest_billing_slot(
        state, targets["billing_provider_ids"]
    )
    reason = targets["billing_followup_reason"]

    resp = client.post(
        f"{BASE}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": earliest_pid,
            "slot_datetime": earliest_dt,
            "type": earliest_type,
            "reason": reason,
        },
    )
    assert resp.status_code == 200, resp.text
    # Deliberately skip the confirm step.

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_message_billing"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_wrong_billing_provider_fails():
    """Booking the OTHER billing provider's (later) earliest slot must fail —
    the answer pins the globally-earliest slot's owning provider (lever 1)."""
    client, sm, sid, targets = _new_session(seed=42)
    state = sm.get_state(sid)

    billing_ids = targets["billing_provider_ids"]
    correct_pid = targets["billing_earliest_slot_provider_id"]
    wrong_pid = next(pid for pid in billing_ids if pid != correct_pid)
    wrong_prov = next(p for p in state.providers if p.id == wrong_pid)
    wrong_slots = sorted(wrong_prov.available_slots, key=lambda s: s.datetime)
    wrong_slot = wrong_slots[0].datetime.isoformat()
    wrong_type = wrong_slots[0].type
    reason = targets["billing_followup_reason"]

    resp = client.post(
        f"{BASE}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": wrong_pid,
            "slot_datetime": wrong_slot,
            "type": wrong_type,
            "reason": reason,
        },
    )
    assert resp.status_code == 200, resp.text
    apt_id = resp.json()["id"]
    client.post(f"{BASE}/appointments/{apt_id}/confirm", json={"session_id": sid})

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_message_billing"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_wrong_reason_fails():
    """A generic reason that ignores the claim discriminator must fail (lever 3)."""
    client, sm, sid, targets = _new_session(seed=42)
    state = sm.get_state(sid)
    earliest_dt, earliest_pid, earliest_type = _earliest_billing_slot(
        state, targets["billing_provider_ids"]
    )

    resp = client.post(
        f"{BASE}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": earliest_pid,
            "slot_datetime": earliest_dt,
            "type": earliest_type,
            "reason": "Incorrect charge review",  # generic — claim not re-derived
        },
    )
    assert resp.status_code == 200, resp.text
    apt_id = resp.json()["id"]
    client.post(f"{BASE}/appointments/{apt_id}/confirm", json={"session_id": sid})

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_message_billing"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_later_dated_zero_balance_decoy_claim_fails():
    """Picking the MOST-RECENT approved claim by date — which the upgrade makes
    a later-dated, fully-covered ($0 balance) decoy — must fail. The agent must
    instead track the latest approved claim with an actual positive balance."""
    client, sm, sid, targets = _new_session(seed=42)
    state = sm.get_state(sid)
    earliest_dt, earliest_pid, earliest_type = _earliest_billing_slot(
        state, targets["billing_provider_ids"]
    )

    decoy = _latest_zero_resp_approved_claim(state)
    assert decoy is not None
    decoy_balance = decoy.model_dump(mode="json")["patient_responsibility"]
    # The reason a naive "latest approved claim by date" agent would build.
    decoy_reason = (
        f"Incorrect charge review for claim {decoy.id} "
        f"(patient balance ${decoy_balance})"
    )
    assert decoy_reason != targets["billing_followup_reason"]

    resp = client.post(
        f"{BASE}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": earliest_pid,
            "slot_datetime": earliest_dt,
            "type": earliest_type,
            "reason": decoy_reason,
        },
    )
    assert resp.status_code == 200, resp.text
    apt_id = resp.json()["id"]
    client.post(f"{BASE}/appointments/{apt_id}/confirm", json={"session_id": sid})

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_message_billing"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"
