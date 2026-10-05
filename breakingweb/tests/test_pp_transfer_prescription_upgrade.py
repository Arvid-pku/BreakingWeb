"""Solvability proof + adversarial checks for the hardened pp_transfer_prescription.

The task (hard tier, primary_primitive = state_tracking) requires the agent to:
  * reconstruct the SUBSET of active prescriptions currently filled at the
    discontinuing mail-order pharmacy (a computed set the agent must re-derive
    from each rx's ``pharmacy_id``), and
  * transfer EXACTLY that subset to the specific Walgreens retail pharmacy,
  * touching nothing else (no default change, no refill/renewal, no message).

A seeded "pharmacy closing" message lists "affected" medications BY NAME, but
that list DISAGREES with the structured per-rx truth: it omits one real
mail-order medication and names one medication that is NOT at the mail-order
pharmacy. An agent that transfers per the prose instead of reconciling against
each prescription's pharmacy fails — that is the state_tracking load.

The correct solution is driven through the REAL backend transfer endpoint
(POST /api/env/patient_portal/medications/{rx_id}/transfer) via a Starlette
TestClient bound to the app's shared SessionManager, then graded through the
canonical_diff evaluator. Several near-miss trajectories are asserted to FAIL.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_transfer_prescription"
PREFIX = "/api/env/patient_portal"


def _new_session():
    """Create a session on the app's shared SessionManager.

    Returns (client, session_id, targets, state). Driving mutations through the
    TestClient hits the same SessionManager instance, so the post-mutation
    state is the exact object the evaluator reads.
    """
    client = TestClient(app)
    sm = app.state.session_manager
    session_id, targets, _seed = sm.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=42
    )
    state = sm.get_state(session_id)
    return client, session_id, dict(targets), state


def _transfer(client: TestClient, session_id: str, rx_id: str, pharmacy_id: str):
    return client.post(
        f"{PREFIX}/medications/{rx_id}/transfer",
        json={"session_id": session_id, "pharmacy_id": pharmacy_id},
    )


def test_seed_shape_is_unambiguous_in_structured_state():
    """The transfer set must equal exactly the ACTIVE rxes at the mail-order pharmacy."""
    _client, _sid, targets, state = _new_session()

    source = targets["source_pharmacy_id"]
    dest = targets["target_pharmacy_id"]
    transfer_set = set(targets["rxes_at_source_pharmacy"])

    assert targets["source_pharmacy_id"] == targets["mail_order_pharmacy_id"]
    assert source != dest and dest != targets["default_pharmacy_id"]
    # Hard tier: a genuine multi-element bijection, larger than the v1 set.
    assert len(transfer_set) >= 4

    active_at_source = {
        r.id for r in state.prescriptions
        if r.status == "active" and r.pharmacy_id == source
    }
    # Every active rx at the mail-order pharmacy is in the transfer set and
    # vice versa — fully disambiguated in STRUCTURED state for a careful agent.
    assert active_at_source == transfer_set, (active_at_source, transfer_set)

    # No non-source active rx is pre-positioned at the destination (each
    # transfer is a real move that produces a diff Update).
    for r in state.prescriptions:
        if r.status == "active" and r.id in transfer_set:
            assert r.pharmacy_id == source


def test_message_notice_is_a_misleading_decoy():
    """The seeded closure notice disagrees with the structured transfer set.

    It must (a) name at least one medication that is NOT at the mail-order
    pharmacy and (b) omit at least one medication that IS — so the prose is a
    genuine state_tracking trap, not a paraphrase of the truth.
    """
    _client, _sid, targets, state = _new_session()

    notice = next(
        (m for m in state.messages if "Pharmacy Service Notice" in (m.body or "")),
        None,
    )
    assert notice is not None, "expected a seeded pharmacy_closure_notice message"

    true_source_meds = set(targets["source_medication_names"])
    non_source_meds = set(targets["non_source_active_medication_names"])

    named_in_notice = {m for m in (true_source_meds | non_source_meds) if m in notice.body}

    # Names a non-source medication (a decoy the agent must NOT move).
    assert named_in_notice & non_source_meds, (named_in_notice, non_source_meds)
    # Omits at least one genuinely-affected source medication.
    assert true_source_meds - named_in_notice, (true_source_meds, named_in_notice)


def test_correct_trajectory_passes():
    """Transferring exactly the mail-order subset to Walgreens passes via evaluate()."""
    client, session_id, targets, state = _new_session()
    dest = targets["target_pharmacy_id"]

    for rx_id in targets["rxes_at_source_pharmacy"]:
        resp = _transfer(client, session_id, rx_id, dest)
        assert resp.status_code == 200, resp.text
        assert resp.json()["pharmacy_id"] == dest

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    # Hard task: richer than the legacy 2-check eval (bijection + constraints
    # + standing invariant wall).
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 5


def test_following_the_message_text_fails():
    """Transferring the medications named in the misleading notice fails.

    The notice omits one real mail-order rx and names one non-mail-order rx. An
    agent that maps medication-name -> rx purely from the prose ends up moving a
    decoy AND leaving a genuine mail-order rx behind — failing both the critical
    decoy constraint and the bijection.
    """
    client, session_id, targets, state = _new_session()
    dest = targets["target_pharmacy_id"]

    notice = next(
        (m for m in state.messages if "Pharmacy Service Notice" in (m.body or "")),
        None,
    )
    assert notice is not None
    body = notice.body

    # Resolve the rxes whose medication the notice lists (the trap trajectory).
    named_rx_ids = [
        rx.id for rx in state.prescriptions
        if rx.status == "active" and rx.medication in body
    ]
    # Sanity: the trap set differs from the true source set.
    assert set(named_rx_ids) != set(targets["rxes_at_source_pharmacy"])

    for rx_id in named_rx_ids:
        # Only active rxes can transfer; all named ones here are active.
        assert _transfer(client, session_id, rx_id, dest).status_code == 200

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_extra_transfer_fails():
    """Transferring an EXTRA non-mail-order active rx trips the filtered invariant."""
    client, session_id, targets, state = _new_session()
    dest = targets["target_pharmacy_id"]

    for rx_id in targets["rxes_at_source_pharmacy"]:
        assert _transfer(client, session_id, rx_id, dest).status_code == 200

    # Move one decoy (a non-source active rx) as well — over-acting.
    extra = targets["non_source_active_rx_ids"][0]
    assert _transfer(client, session_id, extra, dest).status_code == 200

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_incomplete_transfer_fails():
    """Transferring only part of the mail-order subset fails the bijection."""
    client, session_id, targets, state = _new_session()
    dest = targets["target_pharmacy_id"]

    subset = list(targets["rxes_at_source_pharmacy"])
    assert len(subset) >= 4
    for rx_id in subset[:-1]:  # leave one mail-order rx behind
        assert _transfer(client, session_id, rx_id, dest).status_code == 200

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_wrong_destination_fails():
    """Transferring the mail-order subset to a NON-Walgreens pharmacy fails."""
    client, session_id, targets, state = _new_session()
    wrong_dest = targets["default_pharmacy_id"]  # CVS, not the required Walgreens
    assert wrong_dest != targets["target_pharmacy_id"]

    for rx_id in targets["rxes_at_source_pharmacy"]:
        assert _transfer(client, session_id, rx_id, wrong_dest).status_code == 200

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"
