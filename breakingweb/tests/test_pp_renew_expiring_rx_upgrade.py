"""Solvability + near-miss proof for the v2-hardened pp_renew_expiring_rx task.

The task was re-hardened in-place (tier stays ``hard``) to load
state_tracking rather than simple category-filtering. The seed now seats
zero-refill prescriptions on BOTH sides of the 30-day expiry cutoff,
computed against the floating seed clock, so the agent must compute each
prescription's days-to-expiry rather than eyeball an "expiring soon" label:

  - 4 expiring zero-refill rxes at anchor +26/+28/+29/+30 days — RENEW these,
  - 4 FAR zero-refill rxes at anchor +31/+33/+37/+44 days — SKIP these
    (they share the 0-refill axis with the targets but are out of window),
  - 2 expiring-with-refills rxes — SKIP (still have refills),
  - 1 standalone zero-refill rx not expiring within 30 days — SKIP,
  - 1 expired rx — SKIP.

The CORRECT solution is driven through the REAL backend renewal endpoint
(``request_renewal`` in backend/routes/patient_portal.py), which atomically
flips the prescription to ``pending_renewal`` and creates the linked
``rx_renewal`` ClinicalMessage. We evaluate the post-state with the real
``evaluate`` entry point. Method: real route-handler functions are invoked
directly with a local SessionManager (no HTTP plumbing) so the post-state is
directly inspectable; this exercises the identical backend mutation code path
the HTTP layer calls.
"""

from breakingweb.backend.state import SessionManager
from breakingweb.backend.routes.patient_portal import (
    SessionScopedRequest,
    request_renewal,
    refill_medication,
)
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "pp_renew_expiring_rx"


def _fresh_session(seed: int = 42):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=seed
    )
    return sm, sid, dict(targets)


def test_seed_shape_is_harder():
    """Seed exposes 4 required renewal slots PLUS a near-boundary trap set:
    far zero-refill rxes (out of the 30-day window) disjoint from the targets."""
    _, _, targets = _fresh_session()
    assert len(targets["expiring_zero_refill_rx_ids"]) == 4
    # The far (out-of-window) zero-refill traps exist and are disjoint from
    # the renew targets — this is the new state_tracking discriminator.
    assert len(targets["far_zero_refill_rx_ids"]) >= 3
    assert not (
        set(targets["far_zero_refill_rx_ids"])
        & set(targets["expiring_zero_refill_rx_ids"])
    )
    # Expiring-with-refills distractors exist and are disjoint from the targets.
    assert len(targets["expiring_with_refills_rx_ids"]) >= 2
    assert not (
        set(targets["expiring_with_refills_rx_ids"])
        & set(targets["expiring_zero_refill_rx_ids"])
    )
    # The standalone zero-refill (non-expiring) trap is not a target.
    assert targets["zero_refill_rx_id"] not in targets["expiring_zero_refill_rx_ids"]
    assert targets["zero_refill_rx_id"] not in targets["far_zero_refill_rx_ids"]


def test_correct_trajectory_via_renewal_endpoint_passes():
    """Renewing exactly the expiring zero-refill rxes via the real endpoint passes."""
    sm, sid, targets = _fresh_session()

    for rx_id in targets["expiring_zero_refill_rx_ids"]:
        request_renewal(
            rx_id=rx_id,
            body=SessionScopedRequest(session_id=sid),
            session_manager=sm,
        )

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99
    # Hardened diff is richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_correct_trajectory_passes_across_seeds():
    """The correct trajectory must saturate on every seed (boundary placement
    is robust against the ±24h anchor jitter)."""
    for seed in (7, 123, 999):
        sm, sid, targets = _fresh_session(seed)
        for rx_id in targets["expiring_zero_refill_rx_ids"]:
            request_renewal(
                rx_id=rx_id,
                body=SessionScopedRequest(session_id=sid),
                session_manager=sm,
            )
        state = sm.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is True, f"seed={seed} result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"seed={seed} result: {result}"


def test_missing_one_renewal_fails():
    """Renewing only 3 of the 4 required rxes fails the saturating bijection."""
    sm, sid, targets = _fresh_session()

    for rx_id in targets["expiring_zero_refill_rx_ids"][:-1]:  # skip last
        request_renewal(
            rx_id=rx_id,
            body=SessionScopedRequest(session_id=sid),
            session_manager=sm,
        )

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_renewing_a_far_zero_refill_rx_fails():
    """Renewing a FAR zero-refill rx — the new boundary trap: it has 0 refills
    like the targets but expires JUST OUTSIDE the 30-day window — trips the
    critical out-of-window constraint AND the sibling invariant even though all
    4 in-window targets are done. This is the load-bearing state_tracking miss:
    the agent must distinguish +29 days (renew) from +31 days (skip)."""
    sm, sid, targets = _fresh_session()

    for rx_id in targets["expiring_zero_refill_rx_ids"]:
        request_renewal(
            rx_id=rx_id,
            body=SessionScopedRequest(session_id=sid),
            session_manager=sm,
        )
    # Wrong extra action: renew an out-of-window zero-refill rx.
    request_renewal(
        rx_id=targets["far_zero_refill_rx_ids"][0],
        body=SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_renewing_a_zero_refill_non_expiring_rx_fails():
    """Renewing the standalone zero-refill rx that is NOT expiring within 30
    days trips the critical sibling invariant/constraint even though all 4
    targets are done."""
    sm, sid, targets = _fresh_session()

    for rx_id in targets["expiring_zero_refill_rx_ids"]:
        request_renewal(
            rx_id=rx_id,
            body=SessionScopedRequest(session_id=sid),
            session_manager=sm,
        )
    # Wrong extra action: renew the non-expiring zero-refill rx.
    request_renewal(
        rx_id=targets["zero_refill_rx_id"],
        body=SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_refilling_an_expiring_with_refills_rx_fails():
    """An agent that refills (instead of leaving alone) an expiring rx that
    still has refills mutates a frozen sibling and fails."""
    sm, sid, targets = _fresh_session()

    for rx_id in targets["expiring_zero_refill_rx_ids"]:
        request_renewal(
            rx_id=rx_id,
            body=SessionScopedRequest(session_id=sid),
            session_manager=sm,
        )
    # Wrong action: consume a refill on an expiring-with-refills rx.
    refill_medication(
        rx_id=targets["expiring_with_refills_rx_ids"][0],
        body=SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"
