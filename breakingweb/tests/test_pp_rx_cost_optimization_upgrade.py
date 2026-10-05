"""Solvability proof for the hardened pp_rx_cost_optimization task.

The upgraded task asks the agent to:
  1. Identify the single mail-order pharmacy with the LOWEST 90-day supply cost
     (a computed discriminator — the destination is no longer named in the
     instruction; the agent must price-compare several mail-order options).
  2. Transfer EXACTLY the active prescriptions that are currently filled at a
     retail (non-mail-order) pharmacy AND still have >=1 refill remaining
     (a precomputed eligibility bijection) to that cheapest mail-order pharmacy.
  3. Leave every other prescription (zero-refill active, already-at-mail-order
     active, expired) frozen; not touch the default pharmacy; send no messages;
     request no renewal.

This drives the CORRECT solution through the real
``POST /api/env/patient_portal/medications/{rx_id}/transfer`` endpoint and
asserts the canonical_diff evaluator scores it as a pass, then drives several
near-miss trajectories and asserts each fails.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_rx_cost_optimization"


def _new_session(seed: int = 42):
    """Create a session on the app's shared SessionManager and return
    (client, session_manager, sid, targets)."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=seed
    )
    client = TestClient(app)
    return client, sm, sid, dict(targets)


def _transfer(client: TestClient, sid: str, rx_id: str, pharmacy_id: str):
    return client.post(
        f"/api/env/patient_portal/medications/{rx_id}/transfer",
        json={"session_id": sid, "pharmacy_id": pharmacy_id},
    )


def _evaluate(sm, sid: str, targets: dict):
    state = sm.get_state(sid)
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=targets,
        trajectory=[],
    )


# ---------------------------------------------------------------------------
# Sanity: the seed shape the proof depends on
# ---------------------------------------------------------------------------

def test_seed_shape_is_discriminating():
    """Every relevant seed exposes a non-empty eligible set, an excluded
    active set, >=2 distinct-cost mail-order pharmacies, and a cheapest that is
    truly the min cost with the documented id tie-break.

    The v2 hardening makes the partition DETERMINISTIC: a fixed eligible-set
    cardinality (5) across seeds, an excluded active set containing both an
    already-at-mail-order rx and >=1 zero-refill-at-retail rx (the conjunctive
    trap), an expired same-name decoy, and a NEAR-TIE cost discriminator (the
    runner-up mail-order is within $2 of the cheapest, so a naive eyeball /
    first-mail-order pick lands on the wrong one)."""
    for seed in (42, 1, 7, 100, 2026):
        _client, sm, sid, t = _new_session(seed)
        state = sm.get_state(sid)
        pharms = {p.id: p for p in state.pharmacies}
        rx_by_id = {rx.id: rx for rx in state.prescriptions}

        eligible = t["retail_refillable_active_rx_ids"]
        assert len(eligible) == 5, f"seed {seed}: eligible set not deterministic-5 ({len(eligible)})"
        excluded = [r for r in t["active_rx_ids"] if r not in eligible]
        assert len(excluded) >= 1, f"seed {seed}: nothing excluded (not discriminating)"

        mo_ids = t["mail_order_pharmacy_ids"]
        assert len(mo_ids) >= 2, f"seed {seed}: <2 mail-order pharmacies"

        costs = {pid: float(pharms[pid].cost_per_90day_supply) for pid in mo_ids}
        ordered = sorted(costs.values())
        # Strict unique minimum (so the canonical answer is well-defined) with a
        # genuine near-tie runner-up (so the discriminator is hard).
        assert ordered[0] < ordered[1], f"seed {seed}: cheapest is not a strict min ({costs})"
        assert ordered[1] - ordered[0] <= 2.0, f"seed {seed}: runner-up not a near-tie ({costs})"
        min_cost = min(costs.values())
        winners = sorted(pid for pid, c in costs.items() if c == min_cost)
        assert t["cheapest_mail_order_pharmacy_id"] == winners[0], (
            f"seed {seed}: cheapest target {t['cheapest_mail_order_pharmacy_id']} "
            f"!= min-cost id-tiebreak winner {winners[0]} (costs={costs})"
        )

        # Every eligible rx is genuinely active, at a retail pharmacy, with >=1
        # refill, and every excluded active rx fails at least one condition.
        for rid in eligible:
            rx = rx_by_id[rid]
            assert rx.status == "active"
            assert not pharms[rx.pharmacy_id].is_mail_order
            assert rx.refills_remaining >= 1
        for rid in excluded:
            rx = rx_by_id[rid]
            assert pharms[rx.pharmacy_id].is_mail_order or rx.refills_remaining == 0

        # The conjunctive trap is real: at least one EXCLUDED active rx is at a
        # RETAIL pharmacy with zero refills (looks eligible by pharmacy alone).
        retail_zero_refill = [
            rid for rid in excluded
            if not pharms[rx_by_id[rid].pharmacy_id].is_mail_order
            and rx_by_id[rid].refills_remaining == 0
        ]
        assert retail_zero_refill, f"seed {seed}: no zero-refill-at-retail trap"
        # At least one EXCLUDED active rx is already at a mail-order pharmacy.
        already_mail_order = [
            rid for rid in excluded
            if pharms[rx_by_id[rid].pharmacy_id].is_mail_order
        ]
        assert already_mail_order, f"seed {seed}: no already-at-mail-order exclude"
        # An expired rx shares the active target medication's name (same-name decoy).
        target_med = rx_by_id[t["target_rx_id"]].medication
        expired_same_name = [
            rx for rx in state.prescriptions
            if rx.status == "expired" and rx.medication == target_med
        ]
        assert expired_same_name, f"seed {seed}: no expired same-name decoy for {target_med}"


# ---------------------------------------------------------------------------
# CORRECT solution through the real transfer endpoint passes
# ---------------------------------------------------------------------------

def test_correct_transfer_passes_via_real_endpoint():
    """Transfer exactly the eligible rxes to the cheapest mail-order pharmacy
    through the real endpoint; the evaluator must score it as a pass."""
    for seed in (42, 1, 7, 100, 2026):
        client, sm, sid, t = _new_session(seed)
        dest = t["cheapest_mail_order_pharmacy_id"]
        for rx_id in t["retail_refillable_active_rx_ids"]:
            resp = _transfer(client, sid, rx_id, dest)
            assert resp.status_code == 200, f"seed {seed} rx {rx_id}: {resp.text}"
            assert resp.json()["pharmacy_id"] == dest

        result = _evaluate(sm, sid, t)
        assert result.get("success") is True, f"seed {seed}: {result}"
        assert result.get("score", 0.0) >= 0.99, f"seed {seed}: {result}"
        # canonical_diff is richer than a 2-check eval (1 bijection + 8 invariants).
        assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


# ---------------------------------------------------------------------------
# WRONG / near-miss trajectories fail
# ---------------------------------------------------------------------------

def test_wrong_destination_fails():
    """Transferring eligible rxes to a NON-cheapest mail-order pharmacy fails."""
    client, sm, sid, t = _new_session(42)
    wrong = next(
        pid for pid in t["mail_order_pharmacy_ids"]
        if pid != t["cheapest_mail_order_pharmacy_id"]
    )
    for rx_id in t["retail_refillable_active_rx_ids"]:
        assert _transfer(client, sid, rx_id, wrong).status_code == 200
    result = _evaluate(sm, sid, t)
    assert result.get("success") is False, result


def test_naive_first_mail_order_destination_fails():
    """The near-tie trap: transferring to the FIRST/most-obvious mail-order
    pharmacy (Express Scripts, the legacy single-mail-order entry) instead of
    the genuinely cheapest one fails — its cost is only ~$1 above the true
    cheapest, so an agent that does not compare every option lands here."""
    client, sm, sid, t = _new_session(42)
    state = sm.get_state(sid)
    pharms = {p.id: p for p in state.pharmacies}
    cheapest = t["cheapest_mail_order_pharmacy_id"]
    # The legacy first mail-order entry (mail_order_pharmacy_id) is the obvious
    # but NON-cheapest pick; assert it is genuinely close yet wrong.
    naive = t["mail_order_pharmacy_id"]
    assert naive != cheapest, "expected the first mail-order entry to NOT be cheapest"
    gap = float(pharms[naive].cost_per_90day_supply) - float(
        pharms[cheapest].cost_per_90day_supply
    )
    assert 0 < gap <= 2.0, f"near-tie gap unexpected: {gap}"
    for rx_id in t["retail_refillable_active_rx_ids"]:
        assert _transfer(client, sid, rx_id, naive).status_code == 200
    result = _evaluate(sm, sid, t)
    assert result.get("success") is False, result


def test_transfer_zero_refill_retail_rx_fails():
    """The conjunctive trap: also moving an EXCLUDED active rx that is at a
    retail pharmacy but has zero refills (looks eligible by pharmacy alone)
    trips the prescriptions invariant and fails."""
    client, sm, sid, t = _new_session(42)
    state = sm.get_state(sid)
    pharms = {p.id: p for p in state.pharmacies}
    rx_by_id = {rx.id: rx for rx in state.prescriptions}
    dest = t["cheapest_mail_order_pharmacy_id"]
    eligible = list(t["retail_refillable_active_rx_ids"])
    excluded = [r for r in t["active_rx_ids"] if r not in eligible]
    retail_zero = next(
        rid for rid in excluded
        if not pharms[rx_by_id[rid].pharmacy_id].is_mail_order
        and rx_by_id[rid].refills_remaining == 0
    )
    for rx_id in eligible:
        assert _transfer(client, sid, rx_id, dest).status_code == 200
    # Over-act on the zero-refill-at-retail decoy.
    assert _transfer(client, sid, retail_zero, dest).status_code == 200
    result = _evaluate(sm, sid, t)
    assert result.get("success") is False, result


def test_partial_transfer_fails():
    """Transferring only SOME eligible rxes (missing one) fails the bijection."""
    client, sm, sid, t = _new_session(42)
    dest = t["cheapest_mail_order_pharmacy_id"]
    eligible = list(t["retail_refillable_active_rx_ids"])
    assert len(eligible) >= 2
    for rx_id in eligible[:-1]:  # skip the last eligible rx
        assert _transfer(client, sid, rx_id, dest).status_code == 200
    result = _evaluate(sm, sid, t)
    assert result.get("success") is False, result


def test_over_transfer_excluded_rx_fails():
    """Also transferring an EXCLUDED active rx (zero-refill or already
    mail-order) trips the prescriptions invariant and fails."""
    client, sm, sid, t = _new_session(42)
    dest = t["cheapest_mail_order_pharmacy_id"]
    eligible = list(t["retail_refillable_active_rx_ids"])
    excluded = [r for r in t["active_rx_ids"] if r not in eligible]
    assert excluded, "seed 42 expected to have excluded active rxes"
    for rx_id in eligible:
        assert _transfer(client, sid, rx_id, dest).status_code == 200
    # Over-act: move an excluded active rx to the cheapest pharmacy too.
    # (Excluded rxes are still 'active' so the transfer endpoint accepts them.)
    extra = excluded[0]
    resp = _transfer(client, sid, extra, dest)
    if resp.status_code == 200:
        result = _evaluate(sm, sid, t)
        assert result.get("success") is False, result
    else:
        # If the endpoint refused (e.g. expired status), the over-act could not
        # happen — pick a different excluded rx that is active.
        active_ids = set(t["active_rx_ids"])
        extra2 = next((r for r in excluded if r in active_ids), None)
        assert extra2 is not None
        assert _transfer(client, sid, extra2, dest).status_code == 200
        result = _evaluate(sm, sid, t)
        assert result.get("success") is False, result


def test_default_pharmacy_change_fails():
    """Doing the correct transfers but also flipping the default pharmacy
    trips the pharmacies invariant and fails."""
    client, sm, sid, t = _new_session(42)
    dest = t["cheapest_mail_order_pharmacy_id"]
    for rx_id in t["retail_refillable_active_rx_ids"]:
        assert _transfer(client, sid, rx_id, dest).status_code == 200
    # Mirror a "set default pharmacy" side effect directly on state (there is
    # no dedicated default-change route; this models an over-eager agent that
    # marks the new pharmacy as default). method: direct state mutation.
    state = sm.get_state(sid)
    for p in state.pharmacies:
        if p.id == t["default_pharmacy_id"]:
            p.is_default = False
        if p.id == dest:
            p.is_default = True
    result = _evaluate(sm, sid, t)
    assert result.get("success") is False, result


def test_no_action_fails():
    """Doing nothing fails (the positive bijection is unsatisfied)."""
    _client, sm, sid, t = _new_session(42)
    result = _evaluate(sm, sid, t)
    assert result.get("success") is False, result
