"""Solvability + near-miss proof for the upgraded pp_cancel_duplicate_appointments.

The upgraded task is HARD: three appointments share the exact same datetime,
each booked at a different time. The agent must KEEP only the earliest-booked
one and CANCEL the other two, each with an exact cancellation_reason. The
keep/cancel partition is a seed-computed discriminator (the agent cannot infer
it from id order — booked_at ordering is permuted per seed, so the
earliest-booked member is NOT the lowest-id / first-listed appointment).

v2 hardening verified here:
  * booked_at is decoupled from id/creation order (conflict_shuffle_booked_at),
    so an agent that just keeps the first/lowest-id same-time appointment fails;
  * a SECOND same-time group of legitimately-distinct visits must be left
    untouched (cancelling one fails the frozen-sibling invariant);
  * a critical `constraints` predicate independently pins the kept member as the
    earliest-BOOKED one, so mis-ordering the timestamps fails even before the
    invariant fires.

The CORRECT solution is driven through the REAL backend cancel endpoint via
starlette TestClient, using the seed `targets` as the intended answer; this
confirms the answer is achievable past every backend guard. WRONG / near-miss
trajectories must fail.
"""

from __future__ import annotations

import json

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_cancel_duplicate_appointments"
REASON = "Duplicate booking - keeping earliest"
PREFIX = "/api/env/patient_portal"
VARIANT_FILE = "pp_cancel_duplicate_appointments__appointment_cancel_retry_v1.yaml"


def _create_session(client: TestClient, seed: int = 42):
    # Create the session directly on the manager the app uses (so the
    # TestClient routes operate on the same session) and read back the
    # seed-resolved targets — the intended canonical answer.
    sid, targets, _ = app.state.session_manager.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=seed,
    )
    return sid, dict(targets)


def _cancel(client: TestClient, sid: str, apt_id: str, reason: str = REASON):
    return client.post(
        f"{PREFIX}/appointments/{apt_id}/cancel",
        json={"session_id": sid, "reason": reason},
    )


def _state(sid: str):
    return app.state.session_manager.get_state(sid)


def test_correct_trajectory_passes_via_real_backend():
    """Cancelling exactly the non-earliest cluster members (with the exact
    reason) through the real cancel endpoint evaluates to a pass."""
    with TestClient(app) as client:
        sid, targets = _create_session(client, seed=42)

        cancel_ids = targets["conflict_cancel_apt_ids"]
        keep_id = targets["conflict_keep_apt_id"]
        assert isinstance(cancel_ids, list) and len(cancel_ids) == 2
        assert keep_id not in cancel_ids

        # Drive the CORRECT solution through the real backend route.
        for apt_id in cancel_ids:
            r = _cancel(client, sid, apt_id)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "cancelled"

        state = _state(sid)
        # Backend persisted the cancellations + the exact reason.
        for apt_id in cancel_ids:
            apt = state.get_appointment(apt_id)
            assert apt.status == "cancelled"
            assert apt.cancellation_reason == REASON
        # The kept (earliest-booked) appointment is untouched.
        assert state.get_appointment(keep_id).status == "scheduled"

        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is True, f"result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"result: {result}"


def test_wrong_member_cancelled_fails():
    """Cancelling the WRONG cluster member (the earliest-booked one that must
    be KEPT) and leaving a to-cancel member scheduled must fail — both the
    bijection (wrong slot) and the critical preserve invariant on the kept
    appointment are violated."""
    with TestClient(app) as client:
        sid, targets = _create_session(client, seed=42)

        cancel_ids = list(targets["conflict_cancel_apt_ids"])
        keep_id = targets["conflict_keep_apt_id"]

        # Cancel only ONE correct member, plus the appointment that should be
        # kept — a plausible near-miss for an agent that mis-orders booked_at.
        _cancel(client, sid, cancel_ids[0])
        _cancel(client, sid, keep_id)

        state = _state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result: {result}"


def test_wrong_reason_fails():
    """Cancelling exactly the right two appointments but with the WRONG
    cancellation reason must fail the changes.cancellation_reason predicate."""
    with TestClient(app) as client:
        sid, targets = _create_session(client, seed=42)
        cancel_ids = list(targets["conflict_cancel_apt_ids"])

        for apt_id in cancel_ids:
            _cancel(client, sid, apt_id, reason="cancelled it")

        state = _state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result: {result}"


def test_under_cancel_fails():
    """Cancelling only ONE of the two required members (under-acting) must
    fail the exact-cardinality bijection ('no fewer')."""
    with TestClient(app) as client:
        sid, targets = _create_session(client, seed=7)
        cancel_ids = list(targets["conflict_cancel_apt_ids"])

        _cancel(client, sid, cancel_ids[0])

        state = _state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result: {result}"


def _suffix(apt_id: str) -> int:
    part = apt_id.split("_", 1)[1]
    return int(part) if part.isdigit() else -1


def test_keep_is_not_the_lowest_id_member():
    """v2 grounding guard: the booked_at permutation must decouple the
    keep/cancel partition from id order, so an agent cannot pass by 'keep the
    first/lowest-id same-time appointment'. Across many seeds the kept member
    is the earliest-BOOKED one and NOT systematically the lowest-id member."""
    keep_is_lowest = 0
    seeds = list(range(0, 30))
    with TestClient(app) as client:
        for seed in seeds:
            sid, targets = _create_session(client, seed=seed)
            cluster = list(targets["conflict_apt_ids"])
            keep_id = targets["conflict_keep_apt_id"]
            state = _state(sid)
            # Kept member is the strict minimum by booked_at over the cluster.
            booked = {aid: state.get_appointment(aid).booked_at for aid in cluster}
            assert keep_id == min(cluster, key=lambda a: (booked[a], a)), (
                f"seed {seed}: keep {keep_id} is not the earliest-booked"
            )
            lowest_id_member = min(cluster, key=_suffix)
            if keep_id == lowest_id_member:
                keep_is_lowest += 1
    # If the shuffle were broken, keep would ALWAYS be the lowest id. Require
    # that the lowest-id shortcut fails on a strong majority of seeds.
    assert keep_is_lowest <= len(seeds) // 3, (
        f"keep == lowest-id member on {keep_is_lowest}/{len(seeds)} seeds — "
        "the booked_at shuffle is not decoupling id order from booking order"
    )


def test_keep_lowest_id_member_fails():
    """Near-miss for an agent that shortcuts on id order: keep the lowest-id
    same-time member and cancel the rest (including the true earliest-booked
    keep). On a seed where the earliest-booked is NOT the lowest id, this both
    cancels the member that must be kept (critical invariant + critical
    earliest-booked constraint) and fails the bijection — it must NOT pass."""
    with TestClient(app) as client:
        # Find a seed where the lowest-id member is NOT the keep member.
        chosen = None
        for seed in range(0, 30):
            _, targets = _create_session(client, seed=seed)
            cluster = list(targets["conflict_apt_ids"])
            keep_id = targets["conflict_keep_apt_id"]
            if min(cluster, key=_suffix) != keep_id:
                chosen = (seed, targets, cluster, keep_id)
                break
        assert chosen is not None, "no seed where lowest-id != keep"
        seed, targets, cluster, keep_id = chosen

        sid, targets = _create_session(client, seed=seed)
        lowest_id_member = min(cluster, key=_suffix)
        # Naive 'keep the first/lowest-id' strategy: cancel everyone else.
        for apt_id in cluster:
            if apt_id != lowest_id_member:
                _cancel(client, sid, apt_id)

        state = _state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result: {result}"


def test_cancel_decoy_same_time_member_fails():
    """v2 grounding guard: a second, legitimately-distinct same-time group must
    be left untouched. Cancelling the correct duplicate set BUT also cancelling
    a member of the decoy same-time group must fail the frozen-sibling
    invariant (the decoy is not in conflict_cancel_apt_ids)."""
    with TestClient(app) as client:
        sid, targets = _create_session(client, seed=42)
        cancel_ids = list(targets["conflict_cancel_apt_ids"])
        cluster = set(targets["conflict_apt_ids"])

        state = _state(sid)
        keep_dt = state.get_appointment(targets["conflict_keep_apt_id"]).datetime
        # Locate a scheduled same-time decoy group: >=2 scheduled appointments
        # sharing a datetime that is NOT the live cluster's datetime and whose
        # members are not in the cluster.
        from collections import Counter

        sched = [a for a in state.appointments if a.status == "scheduled"]
        dt_counts = Counter(a.datetime for a in sched)
        decoy_member = None
        for a in sched:
            if (
                a.id not in cluster
                and dt_counts[a.datetime] >= 2
                and a.datetime != keep_dt
            ):
                decoy_member = a.id
                break
        assert decoy_member is not None, "no decoy same-time member found"

        # Correctly cancel the duplicate set...
        for apt_id in cancel_ids:
            r = _cancel(client, sid, apt_id)
            assert r.status_code == 200, r.text
        # ...but ALSO touch the decoy group (over-action).
        r = _cancel(client, sid, decoy_member)
        assert r.status_code == 200, r.text

        state = _state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result: {result}"


def test_variant_creates_session_without_unresolved_targets():
    """Variant integrity: the strengthened backtracking variant must bind to
    this task, target the backtracking primitive, register its stacked
    network injections, and leave NO unresolved {target.*} placeholder in the
    rendered injection params."""
    from breakingweb.backend.routes.patient_portal import (
        SessionCreateRequest,
        create_session,
    )
    from breakingweb.backend.state import SessionManager
    from breakingweb.injector.middleware import clear_all_degradations

    clear_all_degradations()
    try:
        sm = SessionManager()
        payload = create_session(
            SessionCreateRequest(
                task_id=TASK_ID, variant_filename=VARIANT_FILE
            ),
            session_manager=sm,
        )
        st = sm.get(payload["session_id"])
        deg = st.degradation
        assert deg["base_task_id"] == TASK_ID, deg
        assert deg["target_primitive"] == "backtracking", deg
        injs = deg["injections"]
        assert len(injs) == 2, injs
        blob = json.dumps(injs)
        assert "{target." not in blob, f"unresolved target placeholder: {blob}"
        actions = {inj["params"].get("action") for inj in injs}
        assert actions == {"silent_fail", "stale_data"}, actions
        # The silent_fail must fake >= the two required cancellations.
        sf = next(i["params"] for i in injs if i["params"]["action"] == "silent_fail")
        assert int(sf.get("fail_count", 1)) >= 2, sf
        # The misleading body must advertise the exact graded post-state.
        assert sf["response_body"]["status"] == "cancelled", sf
        assert sf["response_body"]["cancellation_reason"] == REASON, sf
    finally:
        clear_all_degradations()

