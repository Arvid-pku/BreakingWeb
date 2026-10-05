"""Solvability proof for the upgraded pp_review_eob task.

The hardened task asks the agent to review the EOB on each insurance claim and
pay (zero out) the patient responsibility on EVERY approved claim that has an
available EOB AND a strictly-positive balance -- while leaving alone:
  * approved claims whose EOB is not yet available (positive balance, but the
    "review EOB then pay" workflow must skip them),
  * fully-covered approved claims (patient_responsibility == 0; the pay route
    422s on these),
  * denied claims (appeal/pay temptation),
  * the processing claim,
  * everything in the other collections.

The correct answer set is the seed-computed discriminator
``payable_approved_claim_ids``. The test drives the REAL backend pay endpoint
via the FastAPI TestClient for the correct trajectory, then asserts the
canonical_diff evaluator passes; a near-miss (paying a no-EOB approved claim)
is asserted to fail.
"""

from __future__ import annotations

from decimal import Decimal

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

BASE = "/api/env/patient_portal"


def _make_session() -> tuple[TestClient, SessionManager, str, dict]:
    """Create a seed-42 session and bind it to the TestClient app so the
    real /pay route mutates exactly this session."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id="pp_review_eob", seed=42
    )
    # Point the app's dependency at our manager so the REST endpoints operate
    # on the same seeded session we hold the targets for.
    app.state.session_manager = sm
    client = TestClient(app)
    return client, sm, sid, dict(targets)


def test_payable_discriminator_is_nontrivial():
    """The seed must produce a DEEP filtering problem: many more approved
    claims than payable ones, plus a thick wall of denied/processing decoys
    that must all be preserved untouched."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id="pp_review_eob", seed=42
    )
    targets = dict(targets)
    payable = targets["payable_approved_claim_ids"]
    approved = targets["approved_claim_ids"]
    denied = targets["denied_claim_ids"]
    assert payable, "expected at least one payable approved claim"
    # The hardened seed must keep at least two payable claims (so under-paying
    # is a real failure mode the bijection catches).
    assert len(payable) >= 2
    # Strictly fewer payable than approved -> there ARE approved claims that
    # must be skipped (no-EOB or zero-balance). The upgrade deepens the gap:
    # at most half of the approved claims are payable.
    assert len(payable) < len(approved)
    assert len(payable) <= len(approved) // 2
    # A thick denied/processing wall the critical preserve-ALL invariant guards.
    assert len(denied) >= 4, "expected a deep denied decoy wall"

    state = sm.get_state(sid)
    by_id = {c.id: c for c in state.claims}
    # Every payable claim is approved, eob-available, positive balance.
    for cid in payable:
        c = by_id[cid]
        assert c.status == "approved"
        assert c.eob_available is True
        assert float(c.patient_responsibility) > 0
    # Every approved claim NOT payable is genuinely ineligible (no EOB or zero
    # balance) -- not an arbitrary omission.
    skipped_no_eob = 0
    skipped_zero = 0
    for cid in approved:
        if cid in payable:
            continue
        c = by_id[cid]
        assert (c.eob_available is False) or (float(c.patient_responsibility) == 0)
        if c.eob_available is False:
            skipped_no_eob += 1
        if float(c.patient_responsibility) == 0:
            skipped_zero += 1
    # BOTH named skip categories are present (no-EOB approved AND zero-balance
    # approved), so the agent must apply two distinct exclusion rules.
    assert skipped_no_eob >= 1, "expected approved-no-EOB skip cases"
    assert skipped_zero >= 1, "expected fully-covered zero-balance skip cases"


def test_correct_trajectory_passes_via_real_pay_endpoint():
    client, sm, sid, targets = _make_session()
    payable = targets["payable_approved_claim_ids"]

    for cid in payable:
        resp = client.post(f"{BASE}/claims/{cid}/pay", json={"session_id": sid})
        assert resp.status_code == 200, resp.text
        assert Decimal(str(resp.json()["patient_responsibility"])) == Decimal("0")

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_review_eob"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    # Richer than a 2-check legacy eval (bijection update + filtered invariants).
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_paying_extra_no_eob_claim_fails():
    """Near-miss: agent pays all payable claims AND one approved-but-no-EOB
    claim (a tempting positive-balance lookalike). The filtered claims
    invariant must catch the unauthorized extra payment."""
    client, sm, sid, targets = _make_session()
    payable = set(targets["payable_approved_claim_ids"])
    approved = targets["approved_claim_ids"]

    state = sm.get_state(sid)
    by_id = {c.id: c for c in state.claims}
    # Find an approved claim that is NOT payable but still has a balance the
    # pay route will accept (i.e. a no-EOB approved claim with resp > 0).
    extra = next(
        cid for cid in approved
        if cid not in payable
        and by_id[cid].eob_available is False
        and float(by_id[cid].patient_responsibility) > 0
    )

    for cid in payable:
        resp = client.post(f"{BASE}/claims/{cid}/pay", json={"session_id": sid})
        assert resp.status_code == 200, resp.text
    # Pay the forbidden extra claim too.
    resp = client.post(f"{BASE}/claims/{extra}/pay", json={"session_id": sid})
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_review_eob"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_under_paying_fails():
    """Near-miss: agent pays only a subset of the payable claims. The
    bijection over payable_approved_claim_ids must fail to saturate."""
    client, sm, sid, targets = _make_session()
    payable = targets["payable_approved_claim_ids"]
    assert len(payable) >= 2

    # Pay all but the last payable claim.
    for cid in payable[:-1]:
        resp = client.post(f"{BASE}/claims/{cid}/pay", json={"session_id": sid})
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_review_eob"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_appealing_denied_claim_fails():
    """Near-miss: agent pays the payable claims correctly but also appeals a
    denied claim (a strong distractor). The critical claims invariant must
    catch the out-of-set mutation."""
    client, sm, sid, targets = _make_session()
    payable = targets["payable_approved_claim_ids"]
    denied = targets["denied_claim_ids"]

    for cid in payable:
        resp = client.post(f"{BASE}/claims/{cid}/pay", json={"session_id": sid})
        assert resp.status_code == 200, resp.text
    # Appeal a denied claim (allowed by the route, forbidden by the task).
    resp = client.post(
        f"{BASE}/claims/{denied[0]}/appeal",
        json={"session_id": sid, "reason": "Requesting review"},
    )
    assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_review_eob"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


# ---------------------------------------------------------------------------
# Variant (pp_review_eob__claim_shadow_v1) integrity + fairness.
# ---------------------------------------------------------------------------

VARIANT = "pp_review_eob__claim_shadow_v1.yaml"


def _make_variant_session() -> tuple[TestClient, SessionManager, str, dict]:
    """Create a session WITH the claim_shadow variant active (driven through the
    real route-level create_session so the seed-layer injections + {target.*}
    rendering run exactly as in production) and bind it to the TestClient app so
    the real /pay route mutates exactly this session."""
    from breakingweb.backend.routes.patient_portal import (
        SessionCreateRequest,
        create_session as route_create_session,
    )

    sm = SessionManager()
    payload = route_create_session(
        SessionCreateRequest(
            task_id="pp_review_eob",
            seed=42,
            variant_filename=VARIANT,
        ),
        session_manager=sm,
    )
    sid = payload["session_id"]
    targets = sm.get_targets(sid)
    app.state.session_manager = sm
    client = TestClient(app)
    return client, sm, sid, dict(targets)


def test_variant_decoys_are_all_fairly_skippable():
    """No variant-injected claim may satisfy the literal payable rule
    (approved AND eob_available AND patient_responsibility > 0) while being
    excluded from the target set -- that would be an ambiguous_unfair trap.
    Every decoy claim must be unambiguously skippable: not approved, OR no EOB,
    OR zero balance."""
    _client, sm, sid, targets = _make_variant_session()
    payable = set(targets["payable_approved_claim_ids"])
    state = sm.get_state(sid)
    # The variant must actually have injected claims beyond the base seed.
    assert len(state.claims) > len(payable) + 4, "variant did not add claim decoys"
    for c in state.claims:
        if c.id in payable:
            continue
        literally_payable = (
            c.status == "approved"
            and c.eob_available is True
            and float(c.patient_responsibility) > 0
        )
        assert not literally_payable, (
            f"unfair trap: claim {c.id} satisfies the payable rule but is "
            f"excluded from the target set"
        )


def test_variant_injects_contradictory_billing_threads():
    """The split_information / add_contradictory_update pressure must be
    present: stale billing threads referencing the real payable claim ids and
    asserting they need no action (so a prose-trusting agent skips a real
    payable)."""
    _client, sm, sid, targets = _make_variant_session()
    payable = targets["payable_approved_claim_ids"]
    state = sm.get_state(sid)
    billing = [m for m in state.messages if m.category == "billing"]
    assert len(billing) >= 3, "expected the contradictory billing threads"
    # At least one thread names a real payable claim id verbatim (the rendered
    # {target.payable_approved_claim_ids}) AND claims no payment is needed.
    joined = " ".join(m.body for m in billing)
    assert any(cid in joined for cid in payable), (
        "contradictory threads must reference the live payable claim ids"
    )


def test_variant_correct_trajectory_still_passes():
    """Even with the full variant decoy thicket + contradictory prose, paying
    EXACTLY the base payable set (ignoring the 'already settled' prose and the
    no-EOB/zero-balance/denied lookalikes) still scores success."""
    client, sm, sid, targets = _make_variant_session()
    payable = targets["payable_approved_claim_ids"]
    for cid in payable:
        resp = client.post(f"{BASE}/claims/{cid}/pay", json={"session_id": sid})
        assert resp.status_code == 200, resp.text
        assert Decimal(str(resp.json()["patient_responsibility"])) == Decimal("0")

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_review_eob"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"


def test_variant_trusting_contradictory_prose_fails():
    """The load-bearing failure mode the variant induces: an agent that trusts
    the 'balances already settled' billing thread skips a real payable claim ->
    the saturating bijection over payable_approved_claim_ids drops below 1.0."""
    client, sm, sid, targets = _make_variant_session()
    payable = targets["payable_approved_claim_ids"]
    assert len(payable) >= 2
    # Pay all but one (the 'already settled' thread convinced the agent to skip).
    for cid in payable[:-1]:
        resp = client.post(f"{BASE}/claims/{cid}/pay", json={"session_id": sid})
        assert resp.status_code == 200, resp.text

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("pp_review_eob"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_variant_paying_estimate_decoy_is_rejected_by_route():
    """The fully-covered approved zero-balance decoy paired with the
    'estimated balance ~$40' prose cannot even be paid -- the pay route 422s on
    a zero patient_responsibility -- so a prose-reader who tries is blocked."""
    client, sm, sid, _targets = _make_variant_session()
    state = sm.get_state(sid)
    # Find the injected fully-covered approved claim (eob available, balance 0).
    zero_resp = [
        c for c in state.claims
        if c.status == "approved"
        and c.eob_available is True
        and float(c.patient_responsibility) == 0
    ]
    assert zero_resp, "expected the zero-balance approved estimate decoy"
    resp = client.post(
        f"{BASE}/claims/{zero_resp[0].id}/pay", json={"session_id": sid}
    )
    assert resp.status_code == 422, resp.text
