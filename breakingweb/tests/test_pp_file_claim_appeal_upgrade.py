"""Solvability + difficulty proof for the upgraded pp_file_claim_appeal task.

The task was escalated from `hard` (single denied-claim appeal by earliest
deadline) to `expert`: the agent must now identify EVERY appealable denied
claim (denied + EOB available + appeal_deadline >= now), rank them by appeal
deadline (earliest first, claim-ID tie-break), and appeal EXACTLY the two
most-urgent — while leaving the OTHER appealable denied claims (the most
tempting siblings, including one with a far larger patient responsibility)
untouched, along with every approved/processing claim and all other records.

The v2 upgrade makes the eligibility FILTER load-bearing and the deadline
ranking ROBUST (the two weaknesses found in the empirical failure analysis):
  * the seed now plants INELIGIBLE denied decoys (no EOB, and past-deadline)
    so the agent must apply the full 3-clause filter (status==denied AND
    eob_available AND appeal_deadline>=now), not just "appeal every denied
    claim"; and
  * the eligible claims get DETERMINISTIC, monotonically-spaced deadlines so
    rank-1/rank-2 are each unambiguously earlier than rank-3 by a comfortable
    margin (no more RNG-clustered 0-day-gap coin-flips), with exactly ONE
    intentional same-deadline tie pair among the LATEST eligible claims to
    exercise the claim-id tiebreaker deliberately (and away from the answer).

This module proves:
  * the intended answer (`top_2_urgent_appealable_claim_ids`) is achievable by
    driving the REAL backend `/claims/{id}/appeal` endpoint past its gates
    (status==denied, eob_available, deadline>=now), and scores >= 0.99;
  * the ineligible denied decoys are genuinely excluded AND backend-rejected;
  * the deadline ranking is robust (rank-2 vs rank-3 gap is comfortable);
  * a near-miss (appealing by patient-responsibility rank instead of deadline,
    i.e. the pp_claim_audit heuristic) FAILS — confirming the new
    deadline-ranking discriminator genuinely bites.
"""

from __future__ import annotations

from datetime import datetime, timezone

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_file_claim_appeal"
API = "/api/env/patient_portal"


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _new_session() -> tuple[SessionManager, str, dict]:
    """Create a session on the app's shared SessionManager so TestClient and
    the test observe the same state."""
    sm: SessionManager = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id="patient_portal", task_id=TASK_ID, seed=42)
    return sm, sid, dict(targets)


def _appeal_via_backend(client: TestClient, sid: str, clm_id: str):
    return client.post(
        f"{API}/claims/{clm_id}/appeal",
        json={"session_id": sid, "reason": "Appeal supported by attached EOB and records."},
    )


def test_targets_are_well_formed_and_discriminating():
    """The urgency-ranked answer must be a strict 2-element subset of the
    appealable denied claims, and must DIFFER from a responsibility-based pick
    (otherwise the deadline discriminator would be vacuous)."""
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)

    top2 = targets["top_2_urgent_appealable_claim_ids"]
    by_deadline = targets["appealable_claim_ids_by_deadline"]
    denied = targets["denied_claim_ids"]

    assert len(top2) == 2, top2
    assert top2 == by_deadline[:2]
    # There must be appealable denied claims LEFT OVER (frozen siblings) so the
    # "appeal exactly two" constraint is non-trivial.
    assert len(by_deadline) >= 4, by_deadline
    assert set(top2).issubset(set(denied))

    claims = {c.id: c for c in state.claims}
    # Every appealable claim is genuinely appealable (denied + EOB). The
    # deadline gate is enforced/verified through the real backend in the
    # dedicated rejection test (it owns the authoritative request-time clock).
    for cid in by_deadline:
        c = claims[cid]
        assert c.status == "denied" and c.eob_available

    # v2: the eligibility FILTER is load-bearing — there are INELIGIBLE denied
    # decoys (no EOB, or past-deadline) among the denied claims that must be
    # EXCLUDED from the appealable set. An "appeal every denied claim" agent
    # would over-act on these and fail. The builder's appealable set is the
    # ground truth (it applies the same status+EOB+deadline gate the backend
    # does); membership exclusion is the structural proof, and the backend
    # 422-rejects each one in test_ineligible_denied_decoys_are_backend_rejected.
    ineligible_denied = [cid for cid in denied if cid not in set(by_deadline)]
    assert len(ineligible_denied) >= 2, (
        f"expected ineligible denied decoys; denied={denied} appealable={by_deadline}"
    )
    for cid in ineligible_denied:
        assert claims[cid].status == "denied"

    # The two urgent claims have the earliest deadlines among appealable claims.
    deadlines = [(cid, str(claims[cid].appeal_deadline)) for cid in by_deadline]
    assert deadlines[:2] == sorted(deadlines, key=lambda kv: (kv[1], kv[0]))[:2]

    # v2: the rank-2 vs rank-3 boundary is ROBUST — at least a few days of gap,
    # not a near-coin-flip on RNG-clustered dates. (Deterministic spacing puts
    # rank-2 a full 14 days ahead of rank-3 in this seed.)
    if len(by_deadline) >= 3:
        ordered = sorted(by_deadline, key=lambda cid: (str(claims[cid].appeal_deadline), cid))
        gap_days = (
            _as_dt(claims[ordered[2]].appeal_deadline)
            - _as_dt(claims[ordered[1]].appeal_deadline)
        ).total_seconds() / 86400.0
        assert gap_days >= 3.0, f"rank-2 vs rank-3 deadline gap too small: {gap_days}d"

    # Discriminator check: a responsibility-ranked top-2 (the pp_claim_audit
    # heuristic) selects a DIFFERENT set, so an agent cannot pass by sorting on
    # the wrong field.
    by_resp = sorted(
        by_deadline,
        key=lambda cid: (-float(claims[cid].patient_responsibility), cid),
    )[:2]
    assert set(by_resp) != set(top2), (
        "task is not discriminating: deadline-rank and responsibility-rank coincide"
    )


def test_ineligible_denied_decoys_are_backend_rejected():
    """v2 filter proof: every denied claim that is NOT in the appealable set is
    rejected by the real appeal endpoint (422) because it lacks an EOB or its
    deadline has passed. An agent that appeals 'every denied claim' both 422s
    and (if it forces the state) trips the critical frozen-sibling invariant."""
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)
    client = TestClient(app)

    appealable = set(targets["appealable_claim_ids_by_deadline"])
    ineligible_denied = [cid for cid in targets["denied_claim_ids"] if cid not in appealable]
    assert len(ineligible_denied) >= 2, ineligible_denied

    for cid in ineligible_denied:
        resp = _appeal_via_backend(client, sid, cid)
        assert resp.status_code == 422, f"{cid} should be ineligible: {resp.text}"


def test_correct_trajectory_via_backend_passes():
    """Appeal exactly the two most-urgent eligible claims through the real
    endpoint; evaluate() must pass with score >= 0.99."""
    sm, sid, targets = _new_session()
    client = TestClient(app)

    for clm_id in targets["top_2_urgent_appealable_claim_ids"]:
        resp = _appeal_via_backend(client, sid, clm_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "appealed"

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    # Richer than the legacy 2-check eval (bijection + many invariants).
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_backend_rejects_appealing_non_appealable_claim():
    """The backend gate itself enforces the eligibility filter: an approved
    claim cannot be appealed (proves the gate the agent must respect)."""
    sm, sid, targets = _new_session()
    client = TestClient(app)
    approved_ids = targets["approved_claim_ids"]
    assert approved_ids
    resp = _appeal_via_backend(client, sid, approved_ids[0])
    assert resp.status_code == 422, resp.text


def test_wrong_responsibility_rank_trajectory_fails():
    """Near-miss: appeal the two highest patient-responsibility eligible claims
    (the pp_claim_audit heuristic) instead of the two most-urgent. This both
    misses a required urgent claim AND touches a frozen sibling, so it must
    FAIL (critical invariant + bijection)."""
    sm, sid, targets = _new_session()
    state = sm.get_state(sid)
    client = TestClient(app)

    claims = {c.id: c for c in state.claims}
    by_resp = sorted(
        targets["appealable_claim_ids_by_deadline"],
        key=lambda cid: (-float(claims[cid].patient_responsibility), cid),
    )[:2]
    assert set(by_resp) != set(targets["top_2_urgent_appealable_claim_ids"])

    for clm_id in by_resp:
        resp = _appeal_via_backend(client, sid, clm_id)
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"near-miss should fail: {result}"


def test_extra_appeal_trajectory_fails():
    """Over-acting: appeal the two urgent claims PLUS a third eligible claim.
    The exact-cardinality bijection + frozen-sibling critical invariant must
    fail this."""
    sm, sid, targets = _new_session()
    client = TestClient(app)

    to_appeal = list(targets["top_2_urgent_appealable_claim_ids"])
    # Add the next eligible-by-deadline claim that is NOT in the urgent set.
    extra = [
        cid for cid in targets["appealable_claim_ids_by_deadline"]
        if cid not in to_appeal
    ][0]
    to_appeal.append(extra)

    for clm_id in to_appeal:
        resp = _appeal_via_backend(client, sid, clm_id)
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"over-acting should fail: {result}"


# ---------------------------------------------------------------------------
# Paired intervention variant (state_tracking stressor: split_information +
# contradictory_update). The variant plants boundary-case INELIGIBLE denied
# lookalikes right at the load-bearing rank-2 deadline cutoff + conflicting
# billing messages. It must (a) keep the task solvable (the true top-2 still
# passes), (b) NOT change the canonical answer (every decoy is ineligible and
# backend-rejected), and (c) demonstrably trap a deadline-only heuristic that
# skips the eligibility re-check.
# ---------------------------------------------------------------------------

VARIANT_FILENAME = "pp_file_claim_appeal__claim_shadow_v1.yaml"


def _new_variant_session() -> tuple[SessionManager, str, dict]:
    from breakingweb.backend.routes.patient_portal import SessionCreateRequest, create_session

    sm: SessionManager = app.state.session_manager
    payload = create_session(
        SessionCreateRequest(task_id=TASK_ID, variant_filename=VARIANT_FILENAME, seed=42),
        session_manager=sm,
    )
    sid = payload["session_id"]
    targets = sm.get_targets(sid)
    return sm, sid, dict(targets)


def test_variant_renders_with_no_unresolved_targets():
    """Every {target.X} placeholder in the variant resolves against base seed
    targets — there must be no literal '{target.' left in the injected state."""
    import json

    sm, sid, _ = _new_variant_session()
    state = sm.get(sid)
    blob = json.dumps(state.degradation)
    assert "{target." not in blob, f"unresolved target placeholder: {blob}"
    assert state.degradation["base_task_id"] == TASK_ID
    assert state.degradation["target_primitive"] == "state_tracking"


def test_variant_correct_trajectory_still_passes():
    """Solvability under the intervention: appealing the true top-2 still scores
    1.0 even with the boundary decoys + conflicting messages injected."""
    sm, sid, targets = _new_variant_session()
    client = TestClient(app)

    for clm_id in targets["top_2_urgent_appealable_claim_ids"]:
        resp = _appeal_via_backend(client, sid, clm_id)
        assert resp.status_code == 200, resp.text

    state = sm.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"variant should stay solvable: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"


def test_variant_decoys_are_ineligible_and_do_not_change_answer():
    """Every injected DENIED decoy is backend-ineligible (422), so the canonical
    answer set is unchanged — the decoys raise tracking load without creating a
    hidden alternative solution."""
    sm, sid, targets = _new_variant_session()
    state = sm.get(sid)
    client = TestClient(app)

    base_denied = set(targets["denied_claim_ids"])
    decoy_denied = [c for c in state.claims if c.status == "denied" and c.id not in base_denied]
    assert len(decoy_denied) >= 2, decoy_denied
    for c in decoy_denied:
        resp = _appeal_via_backend(client, sid, c.id)
        assert resp.status_code == 422, f"decoy {c.id} must be ineligible: {resp.text}"


def test_variant_deadline_only_heuristic_is_trapped():
    """An agent that ranks ALL denied claims by deadline WITHOUT re-applying the
    EOB/deadline eligibility filter (the exact state_tracking failure mode the
    variant stresses) selects a set that DIFFERS from the correct top-2 — so the
    intervention genuinely competes on the load-bearing predicate."""
    sm, sid, targets = _new_variant_session()
    state = sm.get(sid)

    denied_all = [c for c in state.claims if c.status == "denied"]
    naive_top2 = sorted(denied_all, key=lambda c: (str(c.appeal_deadline), c.id))[:2]
    correct = set(targets["top_2_urgent_appealable_claim_ids"])
    assert {c.id for c in naive_top2} != correct, (
        "variant does not trap the deadline-only heuristic; decoys not biting"
    )
    # And actually appealing the naive picks fails (they 422 or trip invariants).
    client = TestClient(app)
    appealable = set(targets["appealable_claim_ids_by_deadline"])
    for c in naive_top2:
        if c.id not in appealable:
            resp = _appeal_via_backend(client, sid, c.id)
            assert resp.status_code == 422, (c.id, resp.text)
