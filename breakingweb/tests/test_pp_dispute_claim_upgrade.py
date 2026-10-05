"""Solvability proof for the hardened ``pp_dispute_claim`` task.

The upgraded task asks the agent to appeal the *3 most-recent eligible* denied
claims (denied + EOB available + appeal deadline not passed), ordered by service
date descending (claim-id descending tiebreak), and to leave every other claim
untouched. This module proves:

  1. The intended answer (seed target ``recent_appealable_claim_ids``) is
     achievable through the REAL backend appeal endpoint past its guards
     (status==denied, eob_available, deadline>=now), and that driving exactly
     that set makes the canonical_diff evaluator pass with score >= 0.99.
  2. Near-miss trajectories fail: (a) appealing only TWO of the three required
     claims (under-action breaks the bijection), (b) appealing an ineligible /
     lower-recency denied claim (over-action trips the critical out-of-scope
     invariant), (c) appealing the lower-numbered claim of a SERVICE-DATE TIE
     instead of the documented later-numbered one (the tiebreaker is
     load-bearing), and (d) appealing the NEWEST-of-all denied claim, which is a
     no-EOB sort-order trap (a recency-before-filter agent mis-fires).

Method: the correct solution is driven through the real HTTP endpoint
``POST /api/env/patient_portal/claims/{id}/appeal`` via starlette TestClient,
sharing the app's SessionManager so the post-appeal state is the one evaluated.
Near-miss cases mirror the same endpoint effect (status->appealed) to keep the
proof fast and deterministic.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _make_session() -> tuple[SessionManager, str, dict]:
    """Create a pp_dispute_claim session on a fresh SessionManager.

    The same manager is installed on the TestClient app so endpoint mutations
    and the evaluator read identical state.
    """
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_dispute_claim",
        seed=42,
    )
    return sm, sid, dict(targets)


def test_correct_trajectory_via_real_appeal_endpoint_passes() -> None:
    """Appealing exactly the 3 most-recent eligible denied claims passes."""
    sm, sid, targets = _make_session()
    recent = list(targets["recent_appealable_claim_ids"])
    assert len(recent) == 3, f"expected 3 recent appealable claims, got {recent}"

    # Sanity: the intended answer is a strict subset of denied claims and
    # excludes every ineligible denied claim (the decoys).
    assert set(recent).issubset(set(targets["denied_claim_ids"]))
    assert not set(recent) & set(targets["ineligible_denied_ids"])

    app.state.session_manager = sm
    client = TestClient(app)

    for clm_id in recent:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "Documentation submitted for reconsideration."},
        )
        assert resp.status_code == 200, f"appeal {clm_id} failed: {resp.text}"
        assert resp.json()["status"] == "appealed"

    state = sm.get_state(sid)
    appealed = {c.id for c in state.claims if c.status == "appealed"}
    assert appealed == set(recent), f"appealed set {appealed} != target {set(recent)}"

    result = evaluate(
        task=get_task("pp_dispute_claim"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # canonical_diff richness: bijection update + many invariants.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_partial_appeal_under_action_fails() -> None:
    """Appealing only two of the three required claims fails the bijection."""
    sm, sid, targets = _make_session()
    recent = list(targets["recent_appealable_claim_ids"])

    app.state.session_manager = sm
    client = TestClient(app)

    # Only appeal the first two of the three required claims.
    for clm_id in recent[:2]:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "Partial."},
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_dispute_claim"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"under-action should fail: {result}"


def test_over_action_on_ineligible_claim_fails() -> None:
    """Appealing the right 2 PLUS an out-of-scope denied claim trips invariants.

    The ineligible denied claims (past-deadline / no-EOB) cannot be appealed via
    the endpoint (the guards reject them with 422), so over-action is mirrored by
    directly flipping an out-of-scope denied claim's status to 'appealed' — the
    exact collateral damage the critical invariant must catch.
    """
    sm, sid, targets = _make_session()
    recent = list(targets["recent_appealable_claim_ids"])

    app.state.session_manager = sm
    client = TestClient(app)

    for clm_id in recent:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "Reconsideration."},
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)

    # The endpoint refuses ineligible claims (proving the guard is real)...
    ineligible_id = targets["ineligible_denied_ids"][0]
    bad = client.post(
        f"/api/env/patient_portal/claims/{ineligible_id}/appeal",
        json={"session_id": sid, "reason": "Should be rejected."},
    )
    assert bad.status_code == 422, f"ineligible appeal should 422: {bad.text}"

    # ...so mirror the collateral damage directly to exercise the invariant.
    extra = state.get_claim(ineligible_id)
    extra.status = "appealed"

    result = evaluate(
        task=get_task("pp_dispute_claim"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"over-action should fail: {result}"


def test_wrong_recency_set_fails() -> None:
    """Appealing three ELIGIBLE-but-not-most-recent claims fails the bijection.

    Every appealable claim is a valid appeal target at the endpoint, but only the
    three most recent are the correct answer. Appealing the older three must fail
    (wrong positive set + the right set left un-appealed).
    """
    sm, sid, targets = _make_session()
    recent = set(targets["recent_appealable_claim_ids"])
    older_eligible = [c for c in targets["appealable_claim_ids"] if c not in recent]
    assert len(older_eligible) >= 3, f"need >=3 older eligible, got {older_eligible}"

    app.state.session_manager = sm
    client = TestClient(app)

    for clm_id in older_eligible[:3]:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "Wrong recency."},
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_dispute_claim"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"wrong-recency set should fail: {result}"


def _claim_num(cid: str) -> int:
    return int(str(cid).rsplit("_", 1)[-1])


def test_tiebreaker_is_load_bearing() -> None:
    """Resolving the final rank by service_date alone (ignoring the claim-id
    tiebreak) lands on the WRONG claim and fails.

    The seed plants two fully-eligible denied claims sharing the same
    service_date at the recency boundary; only the later-numbered one belongs in
    the answer. Appealing the two leaders PLUS the *lower*-numbered tied claim
    (instead of the correct higher-numbered one) is a single-claim swap that the
    evaluator must reject.
    """
    sm, sid, targets = _make_session()
    recent = list(targets["recent_appealable_claim_ids"])
    state0 = sm.get_state(sid)

    # The boundary claim is the lowest-recency member of the answer; its tied
    # sibling shares its service_date but is NOT in the answer (lost the
    # tiebreak). Find that dropped, eligible, same-date sibling.
    by_id = {c.id: c for c in state0.claims}
    boundary = min(recent, key=_claim_num)  # later-numbered tie winner has higher id
    # Identify the answer claim that shares its service_date with a non-answer
    # eligible claim (the tie pair).
    answer_dates = {cid: str(by_id[cid].service_date) for cid in recent}
    tie_winner = None
    tie_loser = None
    for cid in recent:
        date_str = answer_dates[cid]
        for c in state0.claims:
            if (
                c.id not in recent
                and c.status == "denied"
                and c.eob_available
                and str(c.service_date) == date_str
                and c.id in targets["appealable_claim_ids"]
            ):
                tie_winner, tie_loser = cid, c.id
                break
        if tie_winner:
            break
    assert tie_winner is not None and tie_loser is not None, (
        f"expected a service_date tie at the boundary; recent={recent} "
        f"boundary={boundary}"
    )
    # The winner must be the LATER-numbered claim of the tied pair.
    assert _claim_num(tie_winner) > _claim_num(tie_loser), (
        f"tie winner {tie_winner} should out-number loser {tie_loser}"
    )

    app.state.session_manager = sm
    client = TestClient(app)

    # Appeal the two unambiguous leaders, then the WRONG (lower-numbered) tied
    # claim instead of the correct higher-numbered one.
    wrong_set = [c for c in recent if c != tie_winner] + [tie_loser]
    assert len(wrong_set) == 3
    for clm_id in wrong_set:
        resp = client.post(
            f"/api/env/patient_portal/claims/{clm_id}/appeal",
            json={"session_id": sid, "reason": "Tie misresolved."},
        )
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_dispute_claim"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"mis-resolved tiebreak should fail: appealed {wrong_set}, "
        f"correct {recent}: {result}"
    )


def test_newest_no_eob_trap_is_rejected_by_endpoint() -> None:
    """The newest-of-all denied claim is a no-EOB sort-order trap.

    An agent that sorts by recency BEFORE filtering would pick this claim first.
    The real appeal endpoint refuses it (no EOB → 422), proving the eligibility
    gate is genuine and the trap cannot silently enter the positive set.
    """
    sm, sid, targets = _make_session()
    state0 = sm.get_state(sid)

    denied = [c for c in state0.claims if c.status == "denied"]
    newest_all = max(denied, key=lambda c: (str(c.service_date), _claim_num(c.id)))
    # The newest denied claim must be an INELIGIBLE no-EOB trap, not the answer.
    assert newest_all.eob_available is False, (
        f"expected newest denied claim to be a no-EOB trap, got {newest_all.id}"
    )
    assert newest_all.id not in targets["recent_appealable_claim_ids"]
    assert newest_all.id in targets["ineligible_denied_ids"]

    app.state.session_manager = sm
    client = TestClient(app)
    resp = client.post(
        f"/api/env/patient_portal/claims/{newest_all.id}/appeal",
        json={"session_id": sid, "reason": "Should be rejected (no EOB)."},
    )
    assert resp.status_code == 422, f"no-EOB trap should 422: {resp.text}"
