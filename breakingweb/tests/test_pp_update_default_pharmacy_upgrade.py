"""Solvability proof for the upgraded (medium-tier) pp_update_default_pharmacy.

Drives the CORRECT solution through the REAL backend mutation endpoints
(set-default + transfer) via Starlette TestClient so the proof also confirms
the actions are achievable past all gates, then evaluates the net state diff
through the canonical_diff evaluator. A deliberately-wrong/near-miss
trajectory is also evaluated and must fail.

Method: real endpoints via TestClient(app), sharing app.state.session_manager
so the mutated state is exactly what evaluate() grades.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "pp_update_default_pharmacy"


def _new_session():
    """Create a session on the APP's session manager and return its primitives.

    Returns (client, session_id, targets, state). The client drives mutations
    against the same SessionManager the state is read from, so evaluate() sees
    exactly the endpoint-mutated state.
    """
    client = TestClient(app)
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=42
    )
    state = sm.get_state(sid)
    return client, sid, dict(targets), state


def _set_default(client: TestClient, sid: str, pharm_id: str):
    return client.post(
        f"/api/env/patient_portal/profile/pharmacy/{pharm_id}/set-default",
        json={"session_id": sid},
    )


def _transfer(client: TestClient, sid: str, rx_id: str, pharm_id: str):
    return client.post(
        f"/api/env/patient_portal/medications/{rx_id}/transfer",
        json={"session_id": sid, "pharmacy_id": pharm_id},
    )


def test_targets_have_expected_shape():
    """The seed exposes the discriminator + transfer-set targets the task needs."""
    _, _, targets, state = _new_session()
    # New discriminator target: cheapest non-default retail pharmacy.
    assert targets["new_default_pharmacy_id"], targets
    # The cheapest retail must NOT be the original default and must NOT be mail-order.
    assert targets["new_default_pharmacy_id"] != targets["original_default_id"]
    assert targets["new_default_pharmacy_id"] != targets["mail_order_pharmacy_id"]
    # Transfer set is the active rxes currently at the old default.
    assert isinstance(targets["transfer_rx_ids"], list)
    assert len(targets["transfer_rx_ids"]) >= 1
    # Transfer set must be a strict subset of all active rxes (there are
    # distractor active rxes filled elsewhere that must NOT move).
    assert set(targets["transfer_rx_ids"]).issubset(set(targets["active_rx_ids"]))
    assert len(targets["transfer_rx_ids"]) < len(targets["active_rx_ids"])
    # Existing keys preserved for variant safety.
    assert "target_pharmacy_id" in targets
    assert "pharmacy_name" in targets
    assert "original_default_id" in targets

    # --- v2 hardening invariants on the seeded fixture ---------------------
    # There is a NON-DEFAULT retail pharmacy tied at the lowest dispensing fee
    # with the canonical answer but with a HIGHER id — the tie-break trap.
    new_default = next(
        p for p in state.pharmacies if p.id == targets["new_default_pharmacy_id"]
    )
    from decimal import Decimal

    tied_siblings = [
        p for p in state.pharmacies
        if not p.is_default and not p.is_mail_order
        and p.id != targets["new_default_pharmacy_id"]
        and Decimal(str(p.dispensing_fee)) == Decimal(str(new_default.dispensing_fee))
    ]
    assert tied_siblings, "expected a tied-lowest-fee sibling (tie-break trap)"
    # Every tied sibling must have a STRICTLY HIGHER id suffix than the answer
    # (so the lower-id tie-break is the only correct selection).
    def _suffix(pid: str) -> int:
        return int(pid.rsplit("_", 1)[-1])

    assert all(_suffix(p.id) > _suffix(new_default.id) for p in tied_siblings)
    # There is a near-miss retail strictly above the minimum (kills "obvious
    # cheapest" eyeballing) and a mail-order with the lowest dispensing fee of
    # all (the forbidden naive-cheapest bait).
    retail_fees = sorted(
        Decimal(str(p.dispensing_fee))
        for p in state.pharmacies if not p.is_mail_order
    )
    assert any(
        Decimal(str(p.dispensing_fee)) > Decimal(str(new_default.dispensing_fee))
        and not p.is_default and not p.is_mail_order
        for p in state.pharmacies
    ), "expected a near-miss retail above the minimum"
    assert any(p.is_mail_order for p in state.pharmacies)
    assert min(
        Decimal(str(p.dispensing_fee)) for p in state.pharmacies if p.is_mail_order
    ) < min(
        Decimal(str(p.dispensing_fee))
        for p in state.pharmacies if not p.is_mail_order and not p.is_default
    ), "mail-order dispensing fee should undercut retail (forbidden bait)"
    # One active rx is ALREADY at the new default (must not be re-pointed), and
    # one expired rx sits at the OLD default (a status decoy that must stay).
    assert targets["active_at_new_default_rx_ids"], targets
    assert set(targets["active_at_new_default_rx_ids"]).isdisjoint(
        set(targets["transfer_rx_ids"])
    )
    assert targets["expired_at_default_rx_ids"], targets
    assert set(targets["expired_at_default_rx_ids"]).isdisjoint(
        set(targets["active_rx_ids"])
    )


def test_correct_trajectory_evaluates_to_pass():
    """Correct solution via real endpoints passes via evaluate()."""
    client, sid, targets, state = _new_session()
    new_default = targets["new_default_pharmacy_id"]

    # 1) Set the lowest-fee retail pharmacy as the new default.
    r = _set_default(client, sid, new_default)
    assert r.status_code == 200, r.text

    # 2) Transfer every active rx at the previous default to the new default.
    for rx_id in targets["transfer_rx_ids"]:
        r = _transfer(client, sid, rx_id, new_default)
        assert r.status_code == 200, r.text

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    # Richer than a 2-check eval (bijection + 2 pharmacy updates + invariants).
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_wrong_destination_fails():
    """Setting the WRONG (more-expensive) retail pharmacy as default fails."""
    client, sid, targets, state = _new_session()
    correct = targets["new_default_pharmacy_id"]
    # Find a non-default, non-mail-order retail pharmacy that is NOT the cheapest.
    wrong = next(
        (
            p.id for p in state.pharmacies
            if not p.is_default and not p.is_mail_order and p.id != correct
        ),
        None,
    )
    assert wrong is not None, "expected a more-expensive retail decoy"

    r = _set_default(client, sid, wrong)
    assert r.status_code == 200, r.text
    for rx_id in targets["transfer_rx_ids"]:
        r = _transfer(client, sid, rx_id, wrong)
        assert r.status_code == 200, r.text

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"


def test_tied_higher_id_sibling_fails():
    """Picking the tied-lowest-fee sibling with the HIGHER id fails the tie-break.

    Two non-default retail pharmacies share the minimum dispensing fee; only the
    lower-id one is the canonical answer. Selecting the higher-id sibling
    satisfies the bare "lowest fee" reading but violates the tie-break
    constraint, so a strong model that skips the lower-id rule still fails.
    """
    from decimal import Decimal

    client, sid, targets, state = _new_session()
    correct = targets["new_default_pharmacy_id"]
    correct_pharm = next(p for p in state.pharmacies if p.id == correct)
    tied = next(
        (
            p.id for p in state.pharmacies
            if not p.is_default and not p.is_mail_order and p.id != correct
            and Decimal(str(p.dispensing_fee)) == Decimal(str(correct_pharm.dispensing_fee))
        ),
        None,
    )
    assert tied is not None, "expected a tied-fee sibling"
    assert tied != correct

    r = _set_default(client, sid, tied)
    assert r.status_code == 200, r.text
    for rx_id in targets["transfer_rx_ids"]:
        r = _transfer(client, sid, rx_id, tied)
        assert r.status_code == 200, r.text

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"


def test_mail_order_destination_fails():
    """Picking the (cheaper, fee-0) mail-order pharmacy as default fails.

    The mail-order pharmacy has the lowest dispensing fee of all (0), so a naive
    "cheapest dispensing fee" reading lands on it — but the instruction forbids
    mail-order, and the critical constraint requires a retail default.
    """
    client, sid, targets, state = _new_session()
    mail = targets["mail_order_pharmacy_id"]
    assert mail
    r = _set_default(client, sid, mail)
    # Endpoint may accept the mutation; the evaluator enforces the retail rule.
    if r.status_code == 200:
        task = get_task(TASK_ID)
        result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
        assert result.get("success") is False, f"result: {result}"


def test_extra_side_effect_fails():
    """Correct default + transfer, but ALSO moving a frozen distractor rx fails."""
    client, sid, targets, state = _new_session()
    new_default = targets["new_default_pharmacy_id"]

    _set_default(client, sid, new_default)
    for rx_id in targets["transfer_rx_ids"]:
        _transfer(client, sid, rx_id, new_default)

    # Now move an active rx that is NOT in the transfer set and is currently at
    # a TRAP pharmacy (i.e. not already at the new default) so the move is a
    # real, gradeable side-effect rather than a no-op.
    extra = next(
        (
            rid for rid in targets["active_rx_ids"]
            if rid not in targets["transfer_rx_ids"]
            and rid not in targets.get("active_at_new_default_rx_ids", [])
        ),
        None,
    )
    assert extra is not None, "expected a distractor active rx at a trap pharmacy"
    r = _transfer(client, sid, extra, new_default)
    assert r.status_code == 200, r.text

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"


def test_partial_transfer_fails():
    """Setting default correctly but transferring only SOME of the set fails the bijection."""
    client, sid, targets, state = _new_session()
    new_default = targets["new_default_pharmacy_id"]

    _set_default(client, sid, new_default)
    # Transfer all but the last one — bijection must not saturate.
    for rx_id in targets["transfer_rx_ids"][:-1]:
        _transfer(client, sid, rx_id, new_default)

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"result: {result}"
