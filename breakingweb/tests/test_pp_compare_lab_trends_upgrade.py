"""Solvability proof for the hardened pp_compare_lab_trends task.

The upgraded task (re-tiered easy -> hard) requires the agent to:
  1. RE-DERIVE the most-recent-pair HbA1c trend direction from lab history
     (NOT stated in the instruction). The seeded RESULTED HbA1c series sorted
     by collected_at is 8.4 -> 7.9 -> 7.5 -> 7.7 -> 7.8 (the 7.7 is an extra
     resulted point dated one day before the most-recent). Overall the series
     FALLS (an eyeballer reads "improving"), but the strict last-two RESULTED
     pair 7.7 -> 7.8 INCREASES, so the trend is WORSENING and only the
     endocrinology branch is satisfiable. A NON-resulted ("collected") HbA1c
     dated most-recently with a low value (6.4) is the visible tail of the
     /labs/trend view; an agent that skips the status=='resulted' filter would
     read 7.8 -> 6.4 as "improving" and flip to the wrong PCP branch.
  2. Book with an endocrinologist (gated on an APPROVED referral) at the
     GLOBAL earliest endocrinology slot across BOTH seeded endocrinologists,
     with reason exactly "HbA1c worsening review". Booking the other
     endocrinologist's (later) earliest slot fails the datetime predicate.
  3. Complete the two-step confirm workflow (endocrinology is in
     auto_confirm_specialties so the appointment lands pending and must be
     confirmed).
  4. Avoid touching prescriptions, messages, referrals (incl. the pending
     decoy referral), claims, etc.

The CORRECT path is driven through the REAL backend endpoints via the ASGI
app (TestClient): list labs/referrals/slots, create the endocrinology
appointment, then confirm it. Several near-misses are asserted to FAIL.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.backend.state import SessionManager
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.runner import ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_compare_lab_trends"
ENV = "patient_portal"


@pytest.fixture(autouse=True)
def _clean_degradation_state():
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {CONTROLLER_SECRET_HEADER: app.state.controller_secret}


def _create(client: TestClient, seed: int = 42) -> dict:
    resp = client.post(
        f"/api/env/{ENV}/session",
        json={"task_id": TASK_ID, "seed": seed},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "resolved_targets" in data, "controller create must expose resolved_targets"
    return data


def _earliest_slot(client: TestClient, sid: str, provider_id: str) -> str:
    resp = client.get(
        f"/api/env/{ENV}/appointments/available-slots",
        params={"session_id": sid, "provider_id": provider_id},
    )
    assert resp.status_code == 200, resp.text
    slots = resp.json()["items"]
    assert slots, f"provider {provider_id} has no available slots"
    return min(s["datetime"] for s in slots)


def _global_earliest_endo(client: TestClient, sid: str, endo_ids: list[str]) -> tuple[str, str]:
    """Return (provider_id, datetime) of the GLOBAL earliest slot across every
    seeded endocrinologist — this is what the canonical datetime expr computes."""
    best: tuple[str, str] | None = None
    for pid in endo_ids:
        resp = client.get(
            f"/api/env/{ENV}/appointments/available-slots",
            params={"session_id": sid, "provider_id": pid},
        )
        assert resp.status_code == 200, resp.text
        for s in resp.json()["items"]:
            if best is None or s["datetime"] < best[1]:
                best = (pid, s["datetime"])
    assert best is not None, "no endocrinology slots found"
    return best


# ---------------------------------------------------------------------------
# Correct solution — driven through the REAL backend endpoints.
# ---------------------------------------------------------------------------

def test_correct_trajectory_passes_via_real_endpoints(client: TestClient):
    session = _create(client)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    endo_ids = targets["endo_provider_ids"]
    assert len(endo_ids) >= 2, "task should seed multiple endocrinologists"

    # Confirm the seeded trend is worsening on the STRICT resulted last-two pair
    # (the discriminator), and that the status-blind tail would mislead.
    labs = client.get(
        f"/api/env/{ENV}/labs/trend/{targets['trend_test_name']}",
        params={"session_id": sid},
    ).json()["items"]
    resulted = [l for l in labs if l["status"] == "resulted"]
    resulted.sort(key=lambda l: l["collected_at"])
    assert float(resulted[-1]["value"]) > float(resulted[-2]["value"]), "seed must be worsening"
    # Overall series falls (eyeballing reads "improving") -> the most-recent
    # pair, not the overall direction, must decide.
    assert float(resulted[-1]["value"]) < float(resulted[0]["value"]), "overall series should fall"
    # Status-blind tail (no resulted filter) would read as improving -> trap.
    all_sorted = sorted(labs, key=lambda l: l["collected_at"])
    assert float(all_sorted[-1]["value"]) < float(all_sorted[-2]["value"]), (
        "status-blind tail should look improving (the fair trap)"
    )

    # An approved endocrinology referral must exist so the gate accepts the booking.
    refs = client.get(f"/api/env/{ENV}/referrals", params={"session_id": sid}).json()["items"]
    assert any(r["to_specialty"] == "endocrinology" and r["status"] == "approved" for r in refs)

    # GLOBAL earliest endo slot across BOTH endocrinologists.
    endo_id, earliest = _global_earliest_endo(client, sid, endo_ids)

    # Create the endocrinology follow-up at the earliest slot.
    create_resp = client.post(
        f"/api/env/{ENV}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": endo_id,
            "slot_datetime": earliest,
            "type": "in-person",
            "reason": "HbA1c worsening review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    apt = create_resp.json()
    # endocrinology is in auto_confirm_specialties -> lands pending.
    assert apt["requires_confirmation"] is True
    assert apt["confirmation_state"] == "pending"

    # Two-step confirm.
    confirm_resp = client.post(
        f"/api/env/{ENV}/appointments/{apt['id']}/confirm",
        json={"session_id": sid},
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["confirmation_state"] == "confirmed"

    # Evaluate via the unified evaluator over the SAME session state.
    sm: SessionManager = app.state.session_manager
    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"


# ---------------------------------------------------------------------------
# Near-miss A — booked the PCP (improving branch) instead of endo. The seed is
# worsening, so the improving branch's provider expr is unsatisfiable and the
# worsening branch's provider expr rejects the PCP -> FAIL.
# ---------------------------------------------------------------------------

def test_wrong_provider_pcp_improving_branch_fails(client: TestClient):
    session = _create(client)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    pcp_id = targets["pcp_id"]

    earliest = _earliest_slot(client, sid, pcp_id)
    create_resp = client.post(
        f"/api/env/{ENV}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": earliest,
            "type": "in-person",
            "reason": "HbA1c improving review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text

    sm: SessionManager = app.state.session_manager
    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"PCP/improving branch should fail: {result}"


# ---------------------------------------------------------------------------
# Near-miss B — booked endo at the earliest slot with the right reason but
# never confirmed (confirmation_state stays pending) -> FAIL.
# ---------------------------------------------------------------------------

def test_endo_not_confirmed_fails(client: TestClient):
    session = _create(client)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    endo_id = targets["endo_provider_ids"][0]

    earliest = _earliest_slot(client, sid, endo_id)
    create_resp = client.post(
        f"/api/env/{ENV}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": endo_id,
            "slot_datetime": earliest,
            "type": "in-person",
            "reason": "HbA1c worsening review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    assert create_resp.json()["confirmation_state"] == "pending"
    # Intentionally do NOT confirm.

    sm: SessionManager = app.state.session_manager
    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"unconfirmed endo appt should fail: {result}"


# ---------------------------------------------------------------------------
# Near-miss C — correct endo booking + confirm, but the agent also mutated the
# pending decoy referral path by requesting a NEW referral (collateral damage
# on the referrals collection, guarded critical) -> FAIL.
# ---------------------------------------------------------------------------

def test_correct_but_requested_extra_referral_fails(client: TestClient):
    session = _create(client)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    endo_id = targets["endo_provider_ids"][0]

    earliest = _earliest_slot(client, sid, endo_id)
    apt = client.post(
        f"/api/env/{ENV}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": endo_id,
            "slot_datetime": earliest,
            "type": "in-person",
            "reason": "HbA1c worsening review",
        },
    ).json()
    client.post(f"/api/env/{ENV}/appointments/{apt['id']}/confirm", json={"session_id": sid})

    # Collateral: request an unsolicited referral (forbidden by the instruction).
    ref_resp = client.post(
        f"/api/env/{ENV}/referrals/request",
        json={"session_id": sid, "to_specialty": "cardiology", "reason": "extra"},
    )
    assert ref_resp.status_code == 200, ref_resp.text

    sm: SessionManager = app.state.session_manager
    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"extra referral should fail: {result}"


# ---------------------------------------------------------------------------
# Freedom path (regression): the instruction scopes the slot to "the earliest
# available slot for the CHOSEN provider" and lets the agent pick EITHER
# endocrinologist. Booking the alternate endo's OWN earliest slot (which is NOT
# the global earliest across both endos) is therefore CORRECT and must PASS.
# Previously the datetime expr demanded the global minimum and mis-graded this.
# ---------------------------------------------------------------------------

def test_alt_endo_own_earliest_slot_passes(client: TestClient):
    session = _create(client)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    endo_ids = targets["endo_provider_ids"]
    assert len(endo_ids) >= 2, "need >=2 endos to exercise per-provider earliest"

    global_pid, global_dt = _global_earliest_endo(client, sid, endo_ids)
    # Pick the OTHER endocrinologist whose OWN earliest slot is strictly later.
    alt_pid = alt_dt = None
    for pid in endo_ids:
        if pid == global_pid:
            continue
        e = _earliest_slot(client, sid, pid)
        if e > global_dt:
            alt_pid, alt_dt = pid, e
            break
    assert alt_pid is not None, "expected a later-earliest endo to exist"

    apt = client.post(
        f"/api/env/{ENV}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": alt_pid,
            "slot_datetime": alt_dt,
            "type": "in-person",
            "reason": "HbA1c worsening review",
        },
    ).json()
    client.post(f"/api/env/{ENV}/appointments/{apt['id']}/confirm", json={"session_id": sid})

    sm: SessionManager = app.state.session_manager
    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )
    assert result.get("success") is True, (
        f"booking the chosen endo's OWN earliest slot is instruction-compliant: {result}"
    )


# ---------------------------------------------------------------------------
# Near-miss D — right specialty/branch, but booked a slot that is NOT the chosen
# provider's earliest available slot -> fails the per-provider datetime predicate.
# ---------------------------------------------------------------------------

def test_endo_non_earliest_slot_fails(client: TestClient):
    session = _create(client)
    sid = session["session_id"]
    targets = session["resolved_targets"]
    endo_ids = targets["endo_provider_ids"]

    # Find an endo with >=2 distinct slot datetimes; book its LATEST slot.
    pid = late_dt = None
    for cand in endo_ids:
        resp = client.get(
            f"/api/env/{ENV}/appointments/available-slots",
            params={"session_id": sid, "provider_id": cand},
        )
        dts = sorted({s["datetime"] for s in resp.json()["items"]})
        if len(dts) >= 2:
            pid, late_dt = cand, dts[-1]
            break
    assert pid is not None, "need an endo with >=2 distinct slots"

    apt = client.post(
        f"/api/env/{ENV}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pid,
            "slot_datetime": late_dt,
            "type": "in-person",
            "reason": "HbA1c worsening review",
        },
    ).json()
    client.post(f"/api/env/{ENV}/appointments/{apt['id']}/confirm", json={"session_id": sid})

    sm: SessionManager = app.state.session_manager
    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"booking a non-earliest slot of the chosen endo should fail: {result}"
    )


# ---------------------------------------------------------------------------
# Near-miss E — an agent that ignored the status=='resulted' filter would read
# the trend-view tail (most-recent point is a 'collected', non-resulted HbA1c
# with a low value) as IMPROVING and book the PCP. The seed is truly worsening,
# so the PCP/improving branch's provider expr is unsatisfiable -> FAIL.
# (This is the status-blind grounding trap the variant amplifies.)
# ---------------------------------------------------------------------------

def test_status_blind_improving_pcp_fails(client: TestClient):
    session = _create(client)
    sid = session["session_id"]
    targets = session["resolved_targets"]

    # Demonstrate the trap is live: status-blind tail looks improving.
    labs = client.get(
        f"/api/env/{ENV}/labs/trend/{targets['trend_test_name']}",
        params={"session_id": sid},
    ).json()["items"]
    all_sorted = sorted(labs, key=lambda l: l["collected_at"])
    assert float(all_sorted[-1]["value"]) < float(all_sorted[-2]["value"])
    assert all_sorted[-1]["status"] != "resulted", "tail trap must be non-resulted"

    pcp_id = targets["pcp_id"]
    earliest = _earliest_slot(client, sid, pcp_id)
    create_resp = client.post(
        f"/api/env/{ENV}/appointments/create",
        json={
            "session_id": sid,
            "provider_id": pcp_id,
            "slot_datetime": earliest,
            "type": "in-person",
            "reason": "HbA1c improving review",
        },
    )
    assert create_resp.status_code == 200, create_resp.text

    sm: SessionManager = app.state.session_manager
    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(state.resolved_targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"status-blind PCP/improving booking should fail: {result}"
    )
