"""Solvability proof for the hardened pp_claim_audit task (v2).

The hardened task seeds a MIX of denied claims: 12 eligible (denied + EOB +
future deadline) plus 8 denied-but-INELIGIBLE lookalikes (4 with no EOB, 4
with an already-expired appeal deadline). The 8 ineligible lookalikes ALL carry
a HIGHER patient_responsibility than every genuine eligible claim (their PR is
drawn from [1600, 2000] while the genuine eligible max is 1500), so the top-8
by raw patient_responsibility are ALL ineligible decoys. An agent that ranks
top-3-by-PR without first applying the full eligibility filter picks decoys the
appeal route rejects (422).

The 12 eligible claims also contain a DELIBERATE 3-way tie at PR 1300 spanning
the top-3 boundary: the genuine top-3 is {clm_4(1500), clm_5(1300), clm_6(1300)}
and clm_7(1300) is the EXCLUDED #4. Membership of the third slot is decided by
the ascending-claim-id tiebreaker, so a model that holds the ranked set but
skips the tiebreaker picks the wrong third claim and trips the exact-3
bijection.

The intended answer is target['top_3_appealable_claim_ids']. We drive the
correct solution through the REAL backend appeal endpoint via TestClient to
confirm the answer is achievable past the route's gates (denied + eob +
deadline), then assert the canonical_diff evaluator scores it as a pass.
"""

from decimal import Decimal

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

_PREFIX = "/api/env/patient_portal"


def _new_session():
    """Create a session on the app's shared SessionManager (so HTTP routes and
    the evaluator operate on the SAME state object)."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id="pp_claim_audit", seed=42
    )
    return sm, sid, dict(targets)


def _appeal(client: TestClient, sid: str, clm_id: str):
    return client.post(
        f"{_PREFIX}/claims/{clm_id}/appeal",
        json={"session_id": sid, "reason": "Documentation submitted for reconsideration."},
    )


def test_correct_trajectory_evaluates_to_pass():
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)
    top3 = targets["top_3_appealable_claim_ids"]

    # Sanity: the intended set must be a strict subset of the eligible set,
    # which itself must be a strict subset of all denied claims — i.e. the
    # eligibility filter actually removes lookalikes.
    assert len(top3) == 3
    eligible = set(targets["appealable_claim_ids"])
    denied = set(targets["denied_claim_ids"])
    assert set(top3).issubset(eligible)
    assert eligible.issubset(denied)
    assert len(eligible) < len(denied), "eligibility filter must remove some denied lookalikes"
    # The eligible ranking pool is large (state_tracking load): the agent must
    # hold/compare ~12 patient_responsibility values, not a handful.
    assert len(eligible) >= 12, "eligible set should be large enough to load working memory"

    claims_by_id = {c.id: c for c in state.claims}

    # The TOP claims by RAW patient_responsibility must ALL be ineligible decoys
    # (PR engineered above the genuine eligible set), so an agent that ranks
    # before applying the full eligibility filter is reliably wrong — not lucky.
    denied_sorted = sorted(
        denied, key=lambda cid: float(claims_by_id[cid].patient_responsibility), reverse=True
    )
    eligible_max_pr = max(float(claims_by_id[cid].patient_responsibility) for cid in eligible)
    top_raw = [cid for cid in denied_sorted if float(claims_by_id[cid].patient_responsibility) > eligible_max_pr]
    assert len(top_raw) >= 4, "the top denied-by-PR claims must be ineligible decoys"
    assert all(cid not in eligible for cid in top_raw), "high-PR decoys must be ineligible"

    # The third top-3 slot must be decided by the ascending-claim-id TIEBREAKER:
    # the genuine #3 and the excluded #4 (next eligible by PR) tie on PR and the
    # lower claim id wins. A model that skips the tiebreaker picks the wrong #3.
    eligible_by_pr = sorted(
        eligible,
        key=lambda cid: (-float(claims_by_id[cid].patient_responsibility), cid),
    )
    third, fourth = eligible_by_pr[2], eligible_by_pr[3]
    assert (
        float(claims_by_id[third].patient_responsibility)
        == float(claims_by_id[fourth].patient_responsibility)
    ), "the top-3 boundary must be a patient-responsibility TIE so the id tiebreaker binds"
    assert third in top3 and fourth not in top3
    assert third < fourth, "tiebreaker must pick the lower claim id for the third slot"

    with TestClient(app) as client:
        for clm_id in top3:
            resp = _appeal(client, sid, clm_id)
            assert resp.status_code == 200, f"appeal {clm_id} failed: {resp.status_code} {resp.text}"
            assert resp.json()["status"] == "appealed"

    state = sm.get_state(sid)
    appealed = [c.id for c in state.claims if c.status == "appealed"]
    assert sorted(appealed) == sorted(top3)

    result = evaluate(
        task=get_task("pp_claim_audit"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_ineligible_decoy_is_gated_by_the_appeal_endpoint():
    """The real appeal route must REJECT the ineligible high-PR decoys, proving
    the eligibility distinction is enforced server-side (no EOB / expired)."""
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)
    claims_by_id = {c.id: c for c in state.claims}

    denied = set(targets["denied_claim_ids"])
    eligible = set(targets["appealable_claim_ids"])
    ineligible = denied - eligible
    assert ineligible, "there must be denied-but-ineligible decoys"

    with TestClient(app) as client:
        for clm_id in ineligible:
            resp = _appeal(client, sid, clm_id)
            assert resp.status_code == 422, (
                f"ineligible {clm_id} should be rejected, got {resp.status_code}"
            )

    # Nothing was appealed, so the evaluator must NOT pass (no positive op).
    state = sm.get_state(sid)
    assert all(c.status != "appealed" for c in state.claims)
    result = evaluate(
        task=get_task("pp_claim_audit"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False


def test_overappeal_near_miss_evaluates_to_fail():
    """Appealing the correct 3 PLUS one extra eligible (but not top-3) claim is
    a near miss: the endpoint allows it (it is eligible) but the exact-3
    bijection + cardinality constraint must reject it."""
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)
    top3 = targets["top_3_appealable_claim_ids"]
    eligible = targets["appealable_claim_ids"]

    extra = next(cid for cid in eligible if cid not in top3)

    with TestClient(app) as client:
        for clm_id in list(top3) + [extra]:
            resp = _appeal(client, sid, clm_id)
            assert resp.status_code == 200, f"appeal {clm_id} failed: {resp.text}"

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_claim_audit"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"over-appeal must fail: {result}"


def test_tiebreaker_near_miss_evaluates_to_fail():
    """The third top-3 slot is decided by the ascending-claim-id tiebreaker over
    a patient-responsibility tie. An agent that holds the ranked set but skips
    the tiebreaker appeals the correct #1/#2 plus the EXCLUDED #4 (the tied
    eligible claim with the higher id) instead of the genuine #3. Both are
    eligible (the endpoint accepts the appeal), but the set is wrong, so the
    exact-3 bijection over top_3_appealable_claim_ids must reject it."""
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)
    top3 = list(targets["top_3_appealable_claim_ids"])
    eligible = targets["appealable_claim_ids"]
    claims_by_id = {c.id: c for c in state.claims}

    eligible_by_pr = sorted(
        eligible,
        key=lambda cid: (-float(claims_by_id[cid].patient_responsibility), cid),
    )
    genuine_third, excluded_fourth = eligible_by_pr[2], eligible_by_pr[3]
    # Confirm the boundary really is a tie decided only by the id tiebreaker.
    assert (
        float(claims_by_id[genuine_third].patient_responsibility)
        == float(claims_by_id[excluded_fourth].patient_responsibility)
    )
    wrong_set = [top3[0], top3[1], excluded_fourth]
    assert genuine_third not in wrong_set and excluded_fourth not in top3

    with TestClient(app) as client:
        for clm_id in wrong_set:
            resp = _appeal(client, sid, clm_id)
            assert resp.status_code == 200, f"appeal {clm_id} failed: {resp.text}"

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_claim_audit"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"tiebreaker near-miss must fail: {result}"


def test_paying_a_claim_violates_forbidden_action():
    """Appealing the correct 3 but ALSO paying a claim (zeroing patient
    responsibility) must trip the critical 'do not pay any claim' constraint."""
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)
    top3 = targets["top_3_appealable_claim_ids"]

    # Pay an approved claim with positive responsibility (real pay endpoint).
    approved = targets["approved_claim_ids"]
    claims_by_id = {c.id: c for c in state.claims}
    payable = next(
        cid for cid in approved if Decimal(str(claims_by_id[cid].patient_responsibility)) > 0
    )

    with TestClient(app) as client:
        for clm_id in top3:
            assert _appeal(client, sid, clm_id).status_code == 200
        pay = client.post(f"{_PREFIX}/claims/{payable}/pay", json={"session_id": sid})
        assert pay.status_code == 200, pay.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_claim_audit"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"paying a claim must fail: {result}"
