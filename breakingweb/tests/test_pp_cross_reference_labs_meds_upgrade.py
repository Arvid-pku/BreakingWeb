"""Solvability + near-miss proof for the hardened (expert) pp_cross_reference_labs_meds.

The upgraded task requires the agent to:
  1. Re-derive the interacting medication pair and EVERY out-of-range resulted
     lab (flag in {abnormal, critical}) from the cabinet / lab panel.
  2. Book exactly ONE PCP appointment at the EARLIEST IN-PERSON slot (not the
     earliest slot overall, which could be telehealth) via the real
     POST /appointments/create route.
  3. CONFIRM that appointment (auto_confirm_specialties=[pcp] makes the new
     appointment land confirmation_state="pending") via the real
     POST /appointments/{id}/confirm route — a genuine two-step workflow.
  4. Use a reason that starts with the fixed prefix AND:
       - names both interacting medications verbatim (name + dosage),
       - for EVERY out-of-range resulted lab, quotes "<test_name> <value> <unit>"
         (unit omitted when the lab has no unit) — a re-derivation the agent
         must read off each lab result, not merely list test names, and
       - flags the single critical lab with the exact text
         "CRITICAL: <test_name>".
  5. Touch nothing else (prescriptions, messages, labs, claims, referrals,
     pre-existing appointments — including not confirming a pre-existing one).

The correct path is driven through the REAL backend endpoints
(starlette TestClient over breakingweb.app:app), which share the same
SessionManager used to mint the session/targets, so passing past the
auto-confirm + slot-availability gates is genuinely exercised.
"""

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_cross_reference_labs_meds"
_API = "/api/env/patient_portal"
_VARIANT = "pp_cross_reference_labs_meds__medication_shadow_v1.yaml"


def _make_session():
    """Mint a session on the APP's SessionManager so the TestClient routes and
    the evaluator both operate on the same state object."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id="patient_portal", task_id=TASK_ID, seed=42)
    return sm, sid, dict(targets)


def _make_variant_session(client):
    """Mint a variant-bound session via the real /session route so the network
    degradation (confirm misleading_success + create error_then_success) is
    registered in the middleware for that session_id. Targets are read back
    off the shared app SessionManager state."""
    clear_all_degradations()
    resp = client.post(
        f"{_API}/session",
        json={"task_id": TASK_ID, "seed": 42, "variant_filename": _VARIANT},
    )
    assert resp.status_code == 200, resp.text
    sid = resp.json()["session_id"]
    sm = app.state.session_manager
    targets = dict(sm.get_targets(sid))
    return sm, sid, targets


def _earliest_in_person_slot(state, pcp_id: str) -> str:
    pcp = next(p for p in state.providers if p.id == pcp_id)
    in_person = [s.datetime for s in pcp.available_slots if s.type == "in-person"]
    return min(in_person).isoformat()


def _build_reason(targets: dict, *, include_values=True, include_critical=True,
                  drop_last_value=False) -> str:
    """Construct a reason satisfying the hardened predicate.

    The canonical_diff requires the prefix, both medications, every
    "<test_name> <value> <unit>" value label, and "CRITICAL: <critical_name>".
    Flags let near-miss tests strip individual requirements.
    """
    meds = ", ".join(targets["interacting_medications"])
    value_labels = list(targets["abnormal_lab_value_labels"])
    if drop_last_value:
        value_labels = value_labels[:-1]
    if include_values:
        labs_part = "; out-of-range labs: " + ", ".join(value_labels)
    else:
        # Names only, no values — should NOT satisfy the value-label predicate.
        labs_part = "; out-of-range labs: " + ", ".join(targets["abnormal_lab_test_names"])
    crit_part = (
        f"; CRITICAL: {targets['critical_lab_test_name']}"
        if include_critical
        else ""
    )
    return (
        "Drug interaction and abnormal lab review: "
        f"interacting pair {meds}{labs_part}{crit_part}"
    )


def _create_and_confirm(client, sm, sid, pcp_id, slot_iso, reason, *, type_="in-person"):
    create_resp = client.post(
        f"{_API}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": slot_iso,
            "type": type_,
            "reason": reason,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    apt_id = create_resp.json()["id"]
    client.post(f"{_API}/appointments/{apt_id}/confirm", json={"session_id": sid})
    return apt_id


def test_correct_trajectory_via_real_endpoints_passes():
    sm, sid, targets = _make_session()
    state = sm.get_state(sid)
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_in_person_slot(state, pcp_id)
    reason = _build_reason(targets)

    # Hardened base: abnormal_count=4 + critical_count=1 => the agent must
    # re-derive and quote FIVE distinct "<test_name> <value> <unit>" labels
    # (one of which is the single critical lab), lengthening the state the
    # agent has to track relative to the v1 (4-label) bar.
    assert len(targets["abnormal_lab_value_labels"]) == 5, targets["abnormal_lab_value_labels"]
    assert targets["critical_lab_test_name"], "expected exactly one critical lab"
    assert targets["critical_lab_test_name"] in targets["abnormal_lab_test_names"]

    client = TestClient(app)

    # Step 1: create the PCP appointment at the earliest in-person slot.
    create_resp = client.post(
        f"{_API}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": slot_iso,
            "type": "in-person",
            "reason": reason,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    apt_id = create_resp.json()["id"]

    # The auto_confirm_specialties=[pcp] opt-in means the new appointment is
    # NOT confirmed yet — proving the two-step workflow is real.
    pre_confirm = sm.get_state(sid).get_appointment(apt_id)
    assert pre_confirm.requires_confirmation is True
    assert pre_confirm.confirmation_state == "pending"

    # Step 2: confirm the appointment via the real confirm route.
    confirm_resp = client.post(
        f"{_API}/appointments/{apt_id}/confirm",
        json={"session_id": sid},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    state = sm.get_state(sid)
    apt = state.get_appointment(apt_id)
    assert apt.confirmation_state == "confirmed"
    assert apt.type == "in-person"

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # Richer than legacy: create checks + invariant/constraint negatives.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_unconfirmed_appointment_fails():
    """Near-miss: correct slot + reason but the agent forgot the confirm step.

    confirmation_state stays 'pending', so the confirmation constraint fails.
    """
    sm, sid, targets = _make_session()
    state = sm.get_state(sid)
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_in_person_slot(state, pcp_id)
    reason = _build_reason(targets)

    client = TestClient(app)
    create_resp = client.post(
        f"{_API}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": slot_iso,
            "type": "in-person",
            "reason": reason,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    # Intentionally DO NOT confirm.

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False


def test_reason_with_names_only_no_values_fails():
    """Near-miss: agent books+confirms the correct in-person slot but only lists
    the lab TEST NAMES without each lab's resulted value+unit. The hardened
    value-label predicate is not satisfied, so the task fails."""
    sm, sid, targets = _make_session()
    state = sm.get_state(sid)
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_in_person_slot(state, pcp_id)
    reason = _build_reason(targets, include_values=False)

    client = TestClient(app)
    _create_and_confirm(client, sm, sid, pcp_id, slot_iso, reason)

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False


def test_reason_missing_critical_flag_fails():
    """Near-miss: agent quotes every value label but never flags the critical
    lab with 'CRITICAL: <name>'. The critical-flag predicate fails."""
    sm, sid, targets = _make_session()
    state = sm.get_state(sid)
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_in_person_slot(state, pcp_id)
    reason = _build_reason(targets, include_critical=False)

    client = TestClient(app)
    _create_and_confirm(client, sm, sid, pcp_id, slot_iso, reason)

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False


def test_telehealth_slot_and_partial_reason_fails():
    """Near-miss: agent books the earliest slot but as telehealth and drops one
    value label. Both the in-person/telehealth constraints and the value-label
    predicate fail, so the task fails even after confirming."""
    sm, sid, targets = _make_session()
    state = sm.get_state(sid)
    pcp_id = targets["pcp_id"]
    pcp = next(p for p in state.providers if p.id == pcp_id)
    tele_slots = [s.datetime for s in pcp.available_slots if s.type == "telehealth"]
    assert tele_slots, "seed should contain at least one telehealth slot"
    tele_iso = min(tele_slots).isoformat()

    partial_reason = _build_reason(targets, drop_last_value=True)

    client = TestClient(app)
    _create_and_confirm(client, sm, sid, pcp_id, tele_iso, partial_reason, type_="telehealth")

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False


# ---------------------------------------------------------------------------
# INTERVENTION VARIANT (medication_shadow_v1) proofs.
#
# The variant stacks three layers on the task's load-bearing predicates:
#   * SEED add_confusing_decoys: dosage-shifted name-stem prescription
#     lookalikes (e.g. "Metformin 1000mg" vs the real "Metformin 500mg") that
#     are ACTIVE + non-interacting, plus boundary-case decoy labs flagged
#     NORMAL/pending so they never pollute the out-of-range value-label set.
#   * NETWORK misleading_success on POST /appointments/{id}/confirm: the FIRST
#     confirm returns a loud success body but leaves confirmation_state
#     "pending"; the agent must re-read and re-confirm.
#   * NETWORK error_then_success on POST /appointments/create: one 503 before
#     the real create succeeds (a naive retry-without-verify can double-book).
#
# These prove the variant is still SOLVABLE (re-read + re-confirm scores 1.0)
# and that the single most likely failure under the variant — trusting the
# fake confirm success — fails on exactly the confirmation_state constraint
# that already broke the strong model on the clean task.
# ---------------------------------------------------------------------------


def test_variant_decoys_do_not_pollute_targets():
    """Seed-layer decoys must not change the canonical out-of-range set nor the
    interacting pair: targets are computed by the builder BEFORE injection, and
    every decoy lab is flagged normal/pending while every decoy rx is
    non-interacting. The dosage-shifted lookalikes ARE present in active state
    so the agent must track the exact dosage."""
    client = TestClient(app)
    sm, sid, targets = _make_variant_session(client)
    state = sm.get_state(sid)

    # The dosage-shifted lookalikes are live, ACTIVE, and non-interacting.
    active_meds = {rx.medication for rx in state.prescriptions if rx.status == "active"}
    assert {"Metformin 1000mg", "Gabapentin 600mg"} <= active_meds
    for rx in state.prescriptions:
        if rx.medication in {"Metformin 1000mg", "Gabapentin 600mg",
                             "Warfarin 2mg", "Atorvastatin 40mg"}:
            assert list(rx.interactions) == [], rx.medication

    # The genuine interacting pair (exact name+dosage) is unchanged and is NOT
    # any of the dosage-shifted decoys.
    assert len(targets["interacting_medications"]) == 2
    for med in targets["interacting_medications"]:
        assert med in active_meds

    # No decoy lab leaked into the out-of-range value-label set.
    assert len(targets["abnormal_lab_value_labels"]) == 5
    out_of_range_resulted = [
        l for l in state.lab_results
        if l.status == "resulted" and l.flag in ("abnormal", "critical")
    ]
    # Exactly the 5 builder-seeded out-of-range labs — no normal-flagged decoy.
    assert len(out_of_range_resulted) == 5


def test_variant_solvable_with_reconfirm_and_create_retry():
    """Under the variant, the correct trajectory is: tolerate the one 503 on
    create, then DETECT the fake confirm success (state still pending) and
    confirm AGAIN. That re-confirm path scores 1.0."""
    client = TestClient(app)
    sm, sid, targets = _make_variant_session(client)
    state = sm.get_state(sid)
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_in_person_slot(state, pcp_id)
    reason = _build_reason(targets)

    # Create #1 is faked-failed (503); retry succeeds. A verifying agent reads
    # the appointment list and issues exactly ONE more create.
    c1 = client.post(
        f"{_API}/appointments/create",
        json={"session_id": sid, "provider_id": pcp_id,
              "slot_datetime": slot_iso, "type": "in-person", "reason": reason},
    )
    assert c1.status_code == 503, c1.text
    c2 = client.post(
        f"{_API}/appointments/create",
        json={"session_id": sid, "provider_id": pcp_id,
              "slot_datetime": slot_iso, "type": "in-person", "reason": reason},
    )
    assert c2.status_code == 200, c2.text
    apt_id = c2.json()["id"]

    # Confirm #1 returns a loud (lying) success; the REAL state stays pending.
    cf1 = client.post(f"{_API}/appointments/{apt_id}/confirm", json={"session_id": sid})
    assert cf1.status_code == 200
    assert cf1.json().get("confirmation_state") == "confirmed"  # the lie
    assert sm.get_state(sid).get_appointment(apt_id).confirmation_state == "pending"

    # A verifying agent re-reads, sees pending, and confirms again — this one
    # passes through to the real handler.
    cf2 = client.post(f"{_API}/appointments/{apt_id}/confirm", json={"session_id": sid})
    assert cf2.status_code == 200
    state = sm.get_state(sid)
    assert state.get_appointment(apt_id).confirmation_state == "confirmed"

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"


def test_variant_trusting_fake_confirm_fails():
    """The most likely failure under the variant: the agent trusts the loud
    fake confirm success and never re-confirms. confirmation_state stays
    'pending', so the confirmation constraint fails — the exact predicate that
    broke the strong model on the clean task, now doubled by the drift."""
    client = TestClient(app)
    sm, sid, targets = _make_variant_session(client)
    state = sm.get_state(sid)
    pcp_id = targets["pcp_id"]
    slot_iso = _earliest_in_person_slot(state, pcp_id)
    reason = _build_reason(targets)

    # Create with a single retry past the 503.
    assert client.post(
        f"{_API}/appointments/create",
        json={"session_id": sid, "provider_id": pcp_id,
              "slot_datetime": slot_iso, "type": "in-person", "reason": reason},
    ).status_code == 503
    c2 = client.post(
        f"{_API}/appointments/create",
        json={"session_id": sid, "provider_id": pcp_id,
              "slot_datetime": slot_iso, "type": "in-person", "reason": reason},
    )
    assert c2.status_code == 200, c2.text
    apt_id = c2.json()["id"]

    # ONE confirm call — the agent trusts the fake success and stops.
    cf1 = client.post(f"{_API}/appointments/{apt_id}/confirm", json={"session_id": sid})
    assert cf1.status_code == 200
    state = sm.get_state(sid)
    assert state.get_appointment(apt_id).confirmation_state == "pending"

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False
