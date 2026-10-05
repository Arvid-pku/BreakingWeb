"""Solvability + near-miss proof for the hardened pp_insurance_plan_change task.

The v2 base splits the patient's seven active prescriptions into a maintenance
subset (covered only via the plan mail service under the new plan) and a retail
subset (must stay at the default pharmacy). The formulary message no longer
spells out a "maintenance" keyword: each maintenance med carries a distinct
non-verbatim "fill via mail service" phrasing while every retail med carries a
DISTRACTOR line that dangles a 90-day supply / a future-quarter mail transition
but explicitly keeps the med at retail for now. The new member ID / group number
must still be DERIVED from the current values (exact 7-/5-digit rule).

The paired intervention variant stacks a backtracking stressor on the
insurance-write spine: a 409 concurrent-modification conflict (with a divergent
latest snapshot) on the first write, two silent-fails on the next two writes,
and a transient 401 re-auth challenge on the first pharmacy/medication mutation.

This module drives the correct solution through the real backend endpoints
(TestClient) to confirm the gates are passable on the harder base, asserts the
canonical evaluator scores it a pass, asserts near-misses fail, and proves the
variant is solvable end-to-end (and that a naive non-retrying trajectory under
the variant fails).
"""

from __future__ import annotations

import os

import yaml
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.injector.middleware import (
    clear_all_degradations,
    register_session_degradation,
)
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

API = "/api/env/patient_portal"

_VARIANT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "injector",
    "variants",
    "pp_insurance_plan_change__insurance_plan_transition_retry_v1.yaml",
)


def _bootstrap(register_variant: bool = False):
    """Create a session on a fresh SessionManager wired into the app.

    Returns ``(client, sid, targets, state)``. The app's session_manager is
    swapped for our instance so TestClient mutations operate on the very
    session whose targets we hold. When ``register_variant`` is True the
    paired intervention variant's network injections are registered for the
    session (mirroring the real route behaviour) so the stressor fires.
    """
    clear_all_degradations()
    sm = SessionManager()
    app.state.session_manager = sm
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_insurance_plan_change",
        seed=42,
    )
    if register_variant:
        with open(_VARIANT_PATH) as fh:
            injections = yaml.safe_load(fh)["injections"]
        register_session_degradation(sid, injections)
    client = TestClient(app)
    state = sm.get_state(sid)
    return client, sid, dict(targets), state


def _derived_insurance(state):
    ins = state.patient.insurance_plan
    member = "AET-" + ins.member_id.split("-")[1]
    group = "GRP-AET-" + ins.group_number.split("-")[1]
    return member, group


def _evaluate(sid, targets):
    state = app.state.session_manager.get_state(sid)
    return evaluate(
        task=get_task("pp_insurance_plan_change"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )


def test_correct_trajectory_evaluates_to_pass():
    client, sid, targets, state = _bootstrap()
    member_id, group_number = _derived_insurance(state)
    mail_order = targets["mail_order_pharmacy_id"]
    maintenance = targets["maintenance_rx_ids"]
    non_maintenance = targets["non_maintenance_rx_ids"]

    # Harder base: 7 active rxes, 3 maintenance, 4 retail distractors.
    assert len(targets["active_rx_ids"]) == 7
    assert len(maintenance) == 3 and len(non_maintenance) == 4
    assert set(maintenance).isdisjoint(set(non_maintenance))
    assert set(maintenance) | set(non_maintenance) == set(targets["active_rx_ids"])

    # 1) Update insurance to the DERIVED values via the real endpoint.
    r = client.post(
        f"{API}/profile/insurance",
        json={
            "session_id": sid,
            "plan_name": "Aetna PPO Silver",
            "member_id": member_id,
            "group_number": group_number,
        },
    )
    assert r.status_code == 200, r.text

    # 2) Set mail-order pharmacy as default.
    r = client.post(
        f"{API}/profile/pharmacy/{mail_order}/set-default",
        json={"session_id": sid},
    )
    assert r.status_code == 200, r.text

    # 3) Transfer ONLY the maintenance prescriptions to mail order.
    for rx_id in maintenance:
        r = client.post(
            f"{API}/medications/{rx_id}/transfer",
            json={"session_id": sid, "pharmacy_id": mail_order},
        )
        assert r.status_code == 200, r.text

    # 4) Leave non-maintenance prescriptions untouched (no calls).

    result = _evaluate(sid, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    # canonical_diff is richer than a 2-check legacy eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_over_transfer_all_rx_evaluates_to_fail():
    """Transferring EVERY active rx (including retail) to mail order must fail."""
    client, sid, targets, state = _bootstrap()
    member_id, group_number = _derived_insurance(state)
    mail_order = targets["mail_order_pharmacy_id"]

    client.post(
        f"{API}/profile/insurance",
        json={
            "session_id": sid,
            "plan_name": "Aetna PPO Silver",
            "member_id": member_id,
            "group_number": group_number,
        },
    )
    client.post(
        f"{API}/profile/pharmacy/{mail_order}/set-default",
        json={"session_id": sid},
    )
    # Wrong: move ALL active rxes, not just the maintenance subset (the
    # distractor "90-day supply available" retail lines tempt exactly this).
    for rx_id in targets["active_rx_ids"]:
        client.post(
            f"{API}/medications/{rx_id}/transfer",
            json={"session_id": sid, "pharmacy_id": mail_order},
        )

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"result: {result}"


def test_verbatim_member_id_evaluates_to_fail():
    """Using a non-derived (transcribed) member ID must fail the insurance check."""
    client, sid, targets, state = _bootstrap()
    mail_order = targets["mail_order_pharmacy_id"]
    maintenance = targets["maintenance_rx_ids"]

    # Wrong: a plausible-but-not-derived member ID / group number.
    client.post(
        f"{API}/profile/insurance",
        json={
            "session_id": sid,
            "plan_name": "Aetna PPO Silver",
            "member_id": "AET-5529103",
            "group_number": "GRP-88914",
        },
    )
    client.post(
        f"{API}/profile/pharmacy/{mail_order}/set-default",
        json={"session_id": sid},
    )
    for rx_id in maintenance:
        client.post(
            f"{API}/medications/{rx_id}/transfer",
            json={"session_id": sid, "pharmacy_id": mail_order},
        )

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"result: {result}"


def test_variant_is_solvable_with_backtracking_recovery():
    """Under the stacked stressor the FULL recovery trajectory still passes.

    The agent must: reconcile the 409 conflict and re-write insurance; keep
    verifying persistence and re-write past the two silent-fails; and re-auth
    (retry) past the transient 401 on the first pharmacy and first transfer
    calls. The correct, fully-recovered final state evaluates to success.
    """
    client, sid, targets, state = _bootstrap(register_variant=True)
    member_id, group_number = _derived_insurance(state)
    mail_order = targets["mail_order_pharmacy_id"]
    maintenance = targets["maintenance_rx_ids"]

    def _post_insurance():
        return client.post(
            f"{API}/profile/insurance",
            json={
                "session_id": sid,
                "plan_name": "Aetna PPO Silver",
                "member_id": member_id,
                "group_number": group_number,
            },
        )

    # (A) First write conflicts (409 + divergent latest snapshot).
    r = _post_insurance()
    assert r.status_code == 409, r.text
    assert "latest" in r.json(), r.text

    # (B) Verify-and-retry until the plan actually persists. The first two
    # post-conflict writes silently fail (200 echoing the OLD plan), so the
    # agent must keep verifying and retrying. Bound the loop to prove it is
    # solvable in a small number of retries (1 conflict + 2 silent-fails).
    persisted = False
    for _ in range(6):
        r = _post_insurance()
        assert r.status_code == 200, r.text
        live = app.state.session_manager.get_state(sid).patient.insurance_plan
        if live.plan_name == "Aetna PPO Silver" and live.member_id == member_id:
            persisted = True
            break
    assert persisted, "insurance write never persisted under the stressor"

    # (C) First pharmacy mutation returns a transient 401; retry succeeds.
    r = client.post(
        f"{API}/profile/pharmacy/{mail_order}/set-default",
        json={"session_id": sid},
    )
    if r.status_code != 200:
        assert r.status_code == 401, r.text
        r = client.post(
            f"{API}/profile/pharmacy/{mail_order}/set-default",
            json={"session_id": sid},
        )
    assert r.status_code == 200, r.text

    # First transfer also hits the transient 401; retry succeeds. Subsequent
    # transfers go through cleanly.
    for rx_id in maintenance:
        r = client.post(
            f"{API}/medications/{rx_id}/transfer",
            json={"session_id": sid, "pharmacy_id": mail_order},
        )
        if r.status_code != 200:
            assert r.status_code == 401, r.text
            r = client.post(
                f"{API}/medications/{rx_id}/transfer",
                json={"session_id": sid, "pharmacy_id": mail_order},
            )
        assert r.status_code == 200, r.text

    result = _evaluate(sid, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    clear_all_degradations()


def test_variant_naive_no_retry_trajectory_fails():
    """A naive agent that trusts the first 200 and never retries the 401s fails.

    This proves the stressor is load-bearing: writing insurance exactly once
    (the silent-fail 200 leaves the OLD BlueCross plan in place) and abandoning
    the 401-rejected pharmacy/transfer calls yields a wrong final state.
    """
    client, sid, targets, state = _bootstrap(register_variant=True)
    member_id, group_number = _derived_insurance(state)
    mail_order = targets["mail_order_pharmacy_id"]
    maintenance = targets["maintenance_rx_ids"]

    # First insurance write 409s; a naive agent retries once, gets a 200
    # (silent-fail echoing the OLD plan) and trusts it without verifying.
    client.post(
        f"{API}/profile/insurance",
        json={
            "session_id": sid,
            "plan_name": "Aetna PPO Silver",
            "member_id": member_id,
            "group_number": group_number,
        },
    )
    client.post(
        f"{API}/profile/insurance",
        json={
            "session_id": sid,
            "plan_name": "Aetna PPO Silver",
            "member_id": member_id,
            "group_number": group_number,
        },
    )
    # Pharmacy + transfers: naive agent fires once each and does NOT retry the
    # transient 401s, so the default pharmacy and at least one transfer never
    # land.
    client.post(
        f"{API}/profile/pharmacy/{mail_order}/set-default",
        json={"session_id": sid},
    )
    for rx_id in maintenance:
        client.post(
            f"{API}/medications/{rx_id}/transfer",
            json={"session_id": sid, "pharmacy_id": mail_order},
        )

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"naive trajectory unexpectedly passed: {result}"
    clear_all_degradations()
