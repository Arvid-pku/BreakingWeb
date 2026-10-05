"""Solvability + difficulty proof for the hardened pp_coordinate_rx_transfer.

The task was escalated in-place (still ``hard``) by turning the destination
pick into a genuine multi-constraint filtered-min:

* The patient now has THREE non-default in-list retail pharmacies with fees
  ``[8, 6, 6]`` (the default itself charges ``9``). The cheapest is a TIE at
  fee 6, so the agent must apply the stated id-suffix tie-break rather than
  eyeball a unique minimum.
* TWO out-of-list retail decoy pharmacies (fees ``4`` and ``5``) are visible on
  ``GET /pharmacies`` but are NOT in the patient's pharmacy list. An agent that
  sorts every visible pharmacy by ``dispensing_fee`` is lured to the cheaper
  decoy and fails — the correct answer is scoped to ``profile.pharmacy_ids``.
* The mail-order pharmacy (fee ``0``, the absolute lowest) remains an explicit
  trap.
* The bijection now saturates over NINE active prescriptions (6 normal +
  1 zero-refill + 2 expiring-soon). The zero-refill / expiring-soon rxes stay
  active and MUST be transferred; only the lone expired rx must be left alone.

The correct solution is driven through the REAL backend endpoints
(``POST /medications/{id}/transfer`` and
``POST /profile/pharmacy/{id}/set-default``) to confirm it is achievable past
server guards. The session is created on the TestClient app's own
SessionManager so HTTP calls and the evaluator observe the same state.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

_PREFIX = "/api/env/patient_portal"


def _make_session(seed: int = 42):
    """Create a session on the TestClient app's SessionManager.

    Returns (client, sid, targets, state). Driving the real endpoints through
    `client` mutates exactly the `state` the evaluator will read.
    """
    client = TestClient(app)
    sm = client.app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_coordinate_rx_transfer",
        seed=seed,
    )
    return client, sid, dict(targets), sm.get_state(sid)


def _evaluate(state, targets):
    return evaluate(
        task=get_task("pp_coordinate_rx_transfer"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )


def _transfer_all(client, sid, rx_ids, pharmacy_id):
    for rx_id in rx_ids:
        resp = client.post(
            f"{_PREFIX}/medications/{rx_id}/transfer",
            json={"session_id": sid, "pharmacy_id": pharmacy_id},
        )
        assert resp.status_code == 200, resp.text


def test_seed_distinguishes_every_trap():
    """The four tempting-but-wrong destinations must each diverge from the
    correct, list-scoped, tie-broken cheapest pharmacy on seed 42."""
    _client, _sid, targets, state = _make_session()
    dest = targets["cheapest_retail_pharmacy_id"]
    pmap = {p.id: p for p in state.pharmacies}

    # Correct destination is a real, in-list, non-default, non-mail-order retail.
    assert dest in pmap
    assert pmap[dest].is_mail_order is False
    assert pmap[dest].is_default is False
    assert dest in state.patient.pharmacy_ids

    # Naive "first non-default retail" (fee 8) is NOT the cheapest (fee 6).
    assert targets["new_default_pharmacy_id"] != dest
    # Mail-order (fee 0, absolute lowest) is forbidden and different.
    assert targets["mail_order_pharmacy_id"] != dest
    # Out-of-list decoy (cheapest considering ALL visible retail) is different
    # AND is genuinely outside the patient's pharmacy list.
    overall = targets["cheapest_overall_retail_pharmacy_id"]
    assert overall != dest
    assert overall not in state.patient.pharmacy_ids
    assert overall in pmap and pmap[overall].is_mail_order is False
    # There is a genuine fee tie at the cheapest in-list fee: the chosen
    # destination's fee equals at least one OTHER in-list retail's fee.
    dest_fee = pmap[dest].dispensing_fee
    tie_siblings = [
        p for p in state.pharmacies
        if p.id != dest
        and p.id in state.patient.pharmacy_ids
        and not p.is_mail_order
        and not p.is_default
        and p.dispensing_fee == dest_fee
    ]
    assert tie_siblings, "expected a fee tie that forces the id-suffix tie-break"


def test_correct_trajectory_via_real_endpoints_passes():
    """Transfer all active rxes to the cheapest in-list retail pharmacy + set
    default. The bijection now saturates over all (>=9) active prescriptions."""
    client, sid, targets, state = _make_session()
    dest = targets["cheapest_retail_pharmacy_id"]

    active_ids = list(targets["active_rx_ids"])
    assert len(active_ids) >= 9, f"expected a saturated active set, got {len(active_ids)}"

    # 1. Transfer every active prescription via the real transfer endpoint.
    for rx_id in active_ids:
        resp = client.post(
            f"{_PREFIX}/medications/{rx_id}/transfer",
            json={"session_id": sid, "pharmacy_id": dest},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["pharmacy_id"] == dest

    # 2. Set the cheapest retail pharmacy as the new default via the real endpoint.
    resp = client.post(
        f"{_PREFIX}/profile/pharmacy/{dest}/set-default",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is True

    result = _evaluate(state, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    # canonical_diff is richer than a 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_naive_first_retail_destination_fails():
    """Picking the *first* non-default retail pharmacy (fee 8) instead of the
    cheapest one (fee 6) fails — they genuinely differ on seed 42."""
    client, sid, targets, state = _make_session()
    naive = targets["new_default_pharmacy_id"]
    cheapest = targets["cheapest_retail_pharmacy_id"]
    assert naive != cheapest, "seed 42 must distinguish naive vs cheapest"

    _transfer_all(client, sid, targets["active_rx_ids"], naive)
    resp = client.post(
        f"{_PREFIX}/profile/pharmacy/{naive}/set-default",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"result: {result}"


def test_out_of_list_decoy_destination_fails():
    """Transferring to the cheapest-overall retail pharmacy (an out-of-list
    decoy charging a LOWER fee than any in-list pharmacy) fails: the destination
    must be a member of the patient's pharmacy list."""
    client, sid, targets, state = _make_session()
    decoy = targets["cheapest_overall_retail_pharmacy_id"]
    assert decoy not in state.patient.pharmacy_ids, "decoy must be out-of-list"
    assert decoy != targets["cheapest_retail_pharmacy_id"]

    _transfer_all(client, sid, targets["active_rx_ids"], decoy)
    resp = client.post(
        f"{_PREFIX}/profile/pharmacy/{decoy}/set-default",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"result: {result}"


def test_mail_order_destination_trap_fails():
    """Transferring to the mail-order pharmacy (fee 0, the lowest overall, but
    explicitly forbidden) fails."""
    client, sid, targets, state = _make_session()
    mail = targets["mail_order_pharmacy_id"]

    _transfer_all(client, sid, targets["active_rx_ids"], mail)
    resp = client.post(
        f"{_PREFIX}/profile/pharmacy/{mail}/set-default",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"result: {result}"


def test_partial_transfer_leaves_default_unchanged_fails():
    """Transferring only some active rxes (and not setting the new default)
    fails the saturating bijection + default-flip obligations."""
    client, sid, targets, state = _make_session()
    dest = targets["cheapest_retail_pharmacy_id"]

    # Move only the first three active rxes; leave the rest + default alone.
    _transfer_all(client, sid, list(targets["active_rx_ids"])[:3], dest)

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"result: {result}"


def test_tie_break_loser_as_default_fails():
    """Choosing the OTHER in-list retail pharmacy that ties on the lowest fee
    (the tie-break loser) instead of the id-suffix winner fails."""
    client, sid, targets, state = _make_session()
    dest = targets["cheapest_retail_pharmacy_id"]
    pmap = {p.id: p for p in state.pharmacies}
    dest_fee = pmap[dest].dispensing_fee
    loser = next(
        p.id for p in state.pharmacies
        if p.id != dest
        and p.id in state.patient.pharmacy_ids
        and not p.is_mail_order
        and not p.is_default
        and p.dispensing_fee == dest_fee
    )

    _transfer_all(client, sid, targets["active_rx_ids"], loser)
    resp = client.post(
        f"{_PREFIX}/profile/pharmacy/{loser}/set-default",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(state, targets)
    assert result.get("success") is False, f"result: {result}"


def test_strengthened_variant_naive_pass_fails_disciplined_recovers():
    """The strengthened backtracking variant must (a) defeat a single-pass agent
    and (b) remain solvable by a disciplined detect-recover-reverify agent.

    Driven over HTTP so the network middleware actually intercepts.
    """
    from breakingweb.injector.middleware import clear_all_degradations

    variant = "pp_coordinate_rx_transfer__medication_transfer_retry_v1.yaml"

    def run(disciplined: bool):
        clear_all_degradations()
        client = TestClient(app)
        sm = client.app.state.session_manager
        resp = client.post(
            f"{_PREFIX}/session",
            json={
                "task_id": "pp_coordinate_rx_transfer",
                "variant_filename": variant,
                "seed": 42,
            },
        )
        assert resp.status_code == 200, resp.text
        sid = resp.json()["session_id"]
        targets = sm.get_targets(sid)
        dest = targets["cheapest_retail_pharmacy_id"]
        actives = list(targets["active_rx_ids"])

        # Single optimistic pass: transfer all, set default once.
        for rx_id in actives:
            client.post(
                f"{_PREFIX}/medications/{rx_id}/transfer",
                json={"session_id": sid, "pharmacy_id": dest},
            )
        client.post(
            f"{_PREFIX}/profile/pharmacy/{dest}/set-default",
            json={"session_id": sid},
        )

        if disciplined:
            # Reconcile transfers against the real /medications view.
            for _ in range(6):
                items = client.get(
                    f"{_PREFIX}/medications", params={"session_id": sid}
                ).json()["items"]
                reverted = [
                    m["id"] for m in items
                    if m["id"] in actives and m["pharmacy_id"] != dest
                ]
                if not reverted:
                    break
                for rx_id in reverted:
                    client.post(
                        f"{_PREFIX}/medications/{rx_id}/transfer",
                        json={"session_id": sid, "pharmacy_id": dest},
                    )
            # Verify the default actually stuck; retry until persisted.
            for _ in range(6):
                phs = client.get(
                    f"{_PREFIX}/pharmacies", params={"session_id": sid}
                ).json()["items"]
                if [p["id"] for p in phs if p["is_default"]] == [dest]:
                    break
                client.post(
                    f"{_PREFIX}/profile/pharmacy/{dest}/set-default",
                    json={"session_id": sid},
                )

        result = _evaluate(sm.get_state(sid), targets)
        clear_all_degradations()
        return result

    naive_result = run(disciplined=False)
    assert naive_result.get("success") is False, f"naive should fail: {naive_result}"

    disciplined_result = run(disciplined=True)
    assert disciplined_result.get("success") is True, (
        f"disciplined recovery should pass: {disciplined_result}"
    )
    assert disciplined_result.get("score", 0.0) >= 0.99
