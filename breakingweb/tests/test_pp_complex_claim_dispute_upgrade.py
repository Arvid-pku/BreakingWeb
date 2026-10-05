"""Solvability + integrity proof for the hardened pp_complex_claim_dispute task.

The v2 task requires the agent to RE-DERIVE the genuinely-appealable denied-claim
subset (status=='denied' AND eob_available AND appeal_deadline not passed) and then
select, from that subset, ONLY the TWO claims with the EARLIEST appeal deadlines —
appealing exactly those two via the real backend appeal action, while leaving the
*other* appealable claims (later deadlines, which the backend WOULD let it appeal),
the non-appealable denied decoys (no-EOB / past-deadline), the approved claims, and
the processing claims untouched.

The key difficulty over v1: the discriminator is now an URGENCY SUBSET, not "appeal
every appealable claim". The backend no longer filters the answer for the agent —
it will happily appeal any appealable denied claim — so over-appealing the
later-deadline appealable claims is a genuine, server-unblocked hazard. The two
highest-balance appealable claims are deliberately NOT the two most urgent, so a
"rank by dollar amount" heuristic produces the wrong pair.

Correct trajectory is driven through the REAL backend endpoint
(POST /api/env/patient_portal/claims/{id}/appeal) via starlette TestClient so this
also confirms the intended answer set passes every backend appeal gate.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_complex_claim_dispute"


def _make_session():
    """Create a real session on the app's session manager and return helpers."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=42
    )
    return sm, sid, dict(targets)


def state_now(state):
    """The seeder anchor used for appeal-deadline gating (utc_now-based)."""
    from breakingweb.backend.routes.patient_portal import utc_now
    return utc_now()


def _as_list(value):
    """Targets are resolved to native lists for PP, but tolerate comma-joins."""
    if isinstance(value, str):
        return [v for v in value.split(",") if v]
    return list(value)


def test_seed_discriminator_is_nontrivial():
    """The urgent-two answer set must be a STRICT subset of the appealable set,
    which is itself a STRICT subset of all denied claims.

    If urgent-two == appealable, the task collapses to v1 ("appeal all
    appealable"); if appealable == denied, it collapses to "appeal all denied".
    The v2 version requires BOTH gates: filter to appealable, then rank by
    deadline and keep only the two soonest.
    """
    sm, sid, targets = _make_session()
    denied = set(targets["denied_claim_ids"])
    appealable = set(targets["appealable_denied_claim_ids"])
    urgent = _as_list(targets["top_2_urgent_appealable_claim_ids"])

    assert len(urgent) == 2, f"expected exactly two urgent claims, got {urgent}"
    assert set(urgent) < appealable, (
        "urgent-two must be a STRICT subset of the appealable set "
        f"(appealable={sorted(appealable)}, urgent={urgent})"
    )
    assert appealable < denied, (
        "appealable set must be a STRICT subset of denied claims "
        f"(denied={sorted(denied)}, appealable={sorted(appealable)})"
    )

    state = sm.get_state(sid)
    by_id = {c.id: c for c in state.claims}

    # The two urgent claims must indeed be the two earliest-deadline appealable.
    appealable_sorted = sorted(
        appealable, key=lambda cid: (by_id[cid].appeal_deadline, cid)
    )
    assert set(urgent) == set(appealable_sorted[:2]), (
        f"urgent set {urgent} is not the two earliest deadlines "
        f"{appealable_sorted[:2]}"
    )

    # Difficulty trap: the two HIGHEST-balance appealable claims must NOT be the
    # urgent pair (otherwise a 'rank by dollars' agent passes for free).
    by_balance = sorted(
        appealable, key=lambda cid: (-float(by_id[cid].patient_responsibility), cid)
    )
    assert set(by_balance[:2]) != set(urgent), (
        "the two highest-balance appealable claims coincide with the urgent two; "
        "the dollar-ranking trap is not engaged"
    )

    # The non-urgent appealable claims are SERVER-APPEALABLE lookalikes (the real
    # over-action hazard the backend will NOT block).
    excluded_appealable = appealable - set(urgent)
    assert excluded_appealable, "expected non-urgent appealable lookalikes"
    for cid in excluded_appealable:
        c = by_id[cid]
        assert c.eob_available and c.appeal_deadline >= state_now(state), (
            f"excluded appealable claim {cid} should pass all backend gates"
        )

    # There must also be genuinely non-appealable denied decoys (no-EOB / past).
    decoys = denied - appealable
    assert decoys, "expected non-appealable denied decoys"
    for cid in decoys:
        c = by_id[cid]
        fails_eob = not c.eob_available
        fails_deadline = c.appeal_deadline < state_now(state)
        assert fails_eob or fails_deadline, (
            f"decoy {cid} should fail a gate but looks appealable"
        )


def test_correct_trajectory_via_backend_passes():
    """Appeal exactly the two most-urgent appealable claims through the real
    endpoint and confirm the harder eval scores success / >= 0.99."""
    sm, sid, targets = _make_session()
    client = TestClient(app)

    urgent = _as_list(targets["top_2_urgent_appealable_claim_ids"])
    appealed_ids = []
    for clm_id in urgent:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "Filing the most time-critical appeal with EOB on file."},
        )
        assert resp.status_code == 200, (
            f"appeal of {clm_id} should succeed past backend gates: "
            f"{resp.status_code} {resp.text}"
        )
        appealed_ids.append(clm_id)

    state = sm.get_state(sid)
    appealed_now = {c.id for c in state.claims if c.status == "appealed"}
    assert appealed_now == set(appealed_ids)

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"


def test_backend_rejects_non_appealable_decoys():
    """The backend itself must reject appealing no-EOB / past-deadline claims."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    denied = set(targets["denied_claim_ids"])
    appealable = set(targets["appealable_denied_claim_ids"])
    decoys = sorted(denied - appealable)
    assert decoys
    for clm_id in decoys:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "trying to appeal a decoy"},
        )
        assert resp.status_code == 422, (
            f"decoy {clm_id} must be rejected by a backend gate, got {resp.status_code}"
        )


def test_over_appeal_non_urgent_appealable_fails():
    """Appealing the two urgent claims PLUS a later-deadline appealable claim
    (which the backend HAPPILY accepts) must fail.

    This is the central v2 hazard: the server does NOT filter the answer, so an
    agent that appeals every appealable claim over-acts. The cardinality
    constraint (==2), the urgency-set constraint, the comprehensive invariant,
    and the bijection 'no excess' must all catch the third real appeal.
    """
    sm, sid, targets = _make_session()
    client = TestClient(app)
    appealable = _as_list(targets["appealable_denied_claim_ids"])
    urgent = set(_as_list(targets["top_2_urgent_appealable_claim_ids"]))
    extra = next(cid for cid in appealable if cid not in urgent)

    for clm_id in list(urgent) + [extra]:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "appeal"},
        )
        # The backend accepts ALL three — that is the whole point.
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"over-appealing a non-urgent appealable claim must fail, got: {result}"
    )


def test_wrong_pair_by_balance_fails():
    """Appealing the two HIGHEST-BALANCE appealable claims (instead of the two
    most urgent) must fail the urgency discriminator even though both are
    server-appealable and the cardinality is exactly two."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    state = sm.get_state(sid)
    by_id = {c.id: c for c in state.claims}
    appealable = _as_list(targets["appealable_denied_claim_ids"])
    urgent = set(_as_list(targets["top_2_urgent_appealable_claim_ids"]))

    by_balance = sorted(
        appealable, key=lambda cid: (-float(by_id[cid].patient_responsibility), cid)
    )
    wrong_pair = by_balance[:2]
    assert set(wrong_pair) != urgent, "balance pair must differ from urgent pair"
    for clm_id in wrong_pair:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "appeal"},
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"appealing the wrong (highest-balance) pair must fail, got: {result}"
    )


def test_under_appeal_fails():
    """Filing only one of the two urgent appeals must fail (cardinality + set)."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    urgent = _as_list(targets["top_2_urgent_appealable_claim_ids"])
    assert len(urgent) == 2
    resp = client.post(
        f"/api/env/patient_portal/claims/{urgent[0]}/appeal",
        json={"session_id": sid, "reason": "appeal"},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"under-appeal must fail, got: {result}"
    )


def test_paying_urgent_claim_fails():
    """Paying (instead of appealing) one urgent target must fail the diff."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    urgent = _as_list(targets["top_2_urgent_appealable_claim_ids"])
    # Appeal the second urgent claim, then PAY the first (wrong action). pay
    # requires patient_responsibility>0; denied claims carry a positive balance.
    resp = client.post(
        f"/api/env/patient_portal/claims/{urgent[1]}/appeal",
        json={"session_id": sid, "reason": "appeal"},
    )
    assert resp.status_code == 200, resp.text
    pay = client.post(
        f"/api/env/patient_portal/claims/{urgent[0]}/pay",
        json={"session_id": sid},
    )
    assert pay.status_code == 200, pay.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"paying a target instead of appealing must fail, got: {result}"
    )
