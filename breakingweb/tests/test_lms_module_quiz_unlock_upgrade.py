"""Solvability proof for the upgraded lms_module_quiz_unlock task (v2).

The v2 base escalates the planning surface beyond raw step count:

  * The chain is now ``chain_type='mixed'`` — Modules 3 and 5 are gated by a
    ``min_score`` unlock condition (``{prereq_id}:70``), not a plain
    prerequisite. Since the gated modules carry no linked assignment, the gate
    is satisfied by COMPLETING the prerequisite module (all content items done
    + marked done), so the agent must reason that "complete the prior module"
    is what clears the score gate, then re-derive the next completable module.
  * Five OFF-CHAIN decoy modules (Modules 8-12) are seeded ``available`` with
    completable content items and "Optional ..." titles. They are NOT part of
    the prerequisite chain. Completing any one is a scored CRITICAL violation
    (dedicated decoy invariant + decoy constraint), so a greedy "complete every
    available module" agent fails. The agent must follow the prerequisite links
    to identify the real chain.
  * Each chain module now has 5 content items; the per-module ``content_items``
    predicate requires ``len(x) >= 5`` so the "finish all items first" subgoal
    stays load-bearing.
  * Completing the four chain modules cascades the capstone module (Module 6)
    from locked -> available, and Module 6 must NOT itself be completed. Module
    7 (terminal, min_score-gated on Module 6 which is never completed) must
    remain locked, guarded by a CRITICAL invariant + constraint.

This drives the CORRECT solution through the REAL LMS backend endpoints via
starlette TestClient (item-complete + module-complete), then evaluates with the
unified evaluator. Three near-misses (over-completing the capstone, completing
an off-chain decoy, partial chain) are asserted to fail.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.lms import SessionCreateRequest, create_session
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "lms_module_quiz_unlock"


@pytest.fixture(autouse=True)
def _reset_degradations():
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _open_session() -> tuple[str, dict]:
    """Create a real app-managed session and return (session_id, targets)."""
    payload = create_session(
        SessionCreateRequest(task_id=TASK_ID, seed=42),
        session_manager=app.state.session_manager,
    )
    sid = payload["session_id"]
    state = app.state.session_manager.get(sid)
    return sid, dict(state.resolved_targets)


def _complete_module_via_api(client: TestClient, sid: str, module_id: str) -> None:
    """Complete every content item then mark the module done, via real routes."""
    state = app.state.session_manager.get(sid)
    module = state.get_module(module_id)
    assert module is not None, f"module {module_id} missing"
    for idx in range(len(module.content_items)):
        resp = client.post(
            f"/api/env/lms/modules/{module_id}/items/{idx}/complete",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/api/env/lms/modules/{module_id}/complete",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text


def test_chain_is_mixed_with_min_score_gates_and_decoys(client: TestClient):
    """The seeded state matches the v2 design: mixed gates + 5 off-chain decoys."""
    sid, targets = _open_session()
    try:
        state = app.state.session_manager.get(sid)
        chain_ids = targets["module_ids"].split(",")
        decoy_ids = targets["decoy_module_ids"].split(",")

        # 7 chain modules + 5 decoys.
        assert len(chain_ids) == 7, chain_ids
        assert len(decoy_ids) == 5, decoy_ids
        assert len(state.modules) == 12, len(state.modules)

        # Modules 3 and 5 (indices 2 and 4) are min_score gated — that is what
        # makes "just complete the next available module" insufficient without
        # reasoning that completing the prerequisite clears the score gate.
        gate_module_3 = state.get_module(chain_ids[2])
        gate_module_5 = state.get_module(chain_ids[4])
        assert gate_module_3.unlock_condition == "min_score", gate_module_3.unlock_condition
        assert gate_module_5.unlock_condition == "min_score", gate_module_5.unlock_condition

        # Every decoy is independently available with completable items but is
        # NOT in the prerequisite chain.
        for did in decoy_ids:
            decoy = state.get_module(did)
            assert decoy is not None, did
            assert decoy.status == "available", (did, decoy.status)
            assert decoy.unlock_condition == "none", (did, decoy.unlock_condition)
            assert did not in chain_ids

        # Every chain module to complete carries >=5 content items.
        for mid in targets["modules_to_complete"].split(","):
            assert len(state.get_module(mid).content_items) >= 5
    finally:
        app.state.session_manager.destroy(sid)


def test_correct_ordered_chain_completion_passes(client: TestClient):
    """Completing the four chain modules in order via the real backend passes."""
    sid, targets = _open_session()
    try:
        to_complete = targets["modules_to_complete"].split(",")
        assert len(to_complete) == 4, to_complete

        # Drive the ordered chain through the REAL endpoints. Each module is
        # only unlockable once its predecessor is completed (server gate,
        # including the min_score gates on Modules 3 and 5), so the order
        # matters — out-of-order calls would 422.
        for module_id in to_complete:
            _complete_module_via_api(client, sid, module_id)

        state = app.state.session_manager.get(sid)

        # Sanity: the cascade left the capstone available and the terminal
        # module locked, and NO decoy was touched.
        final_unlocked = state.get_module(targets["final_unlocked_module_id"])
        terminal_locked = state.get_module(targets["terminal_locked_module_id"])
        assert final_unlocked.status == "available", final_unlocked.status
        assert terminal_locked.status == "locked", terminal_locked.status
        for did in targets["decoy_module_ids"].split(","):
            assert state.get_module(did).status == "available"

        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is True, f"result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
        # Richer than the legacy single-update check.
        assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 3
    finally:
        app.state.session_manager.destroy(sid)


def test_over_completing_capstone_module_fails(client: TestClient):
    """Completing the capstone module as well (greedy over-completion) fails.

    The capstone module must stay merely AVAILABLE after the cascade. If the
    agent also finishes its items and marks it done, update[1] (status==available)
    no longer holds and the CRITICAL 'capstone unlocked but not completed'
    constraint flips — the task must reject this near-miss.
    """
    sid, targets = _open_session()
    try:
        for module_id in targets["modules_to_complete"].split(","):
            _complete_module_via_api(client, sid, module_id)
        # ...then ALSO over-complete the capstone (now available via cascade).
        _complete_module_via_api(client, sid, targets["final_unlocked_module_id"])

        state = app.state.session_manager.get(sid)
        assert state.get_module(targets["final_unlocked_module_id"]).status == "completed"

        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"expected failure, got {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_completing_offchain_decoy_module_fails(client: TestClient):
    """Completing a look-alike 'available' decoy is a scored CRITICAL failure.

    The whole point of the v2 selection-under-planning upgrade: a greedy agent
    that completes every 'available' module (including the optional supplements)
    must fail. Here we do the right chain AND wrongly complete one decoy.
    """
    sid, targets = _open_session()
    try:
        for module_id in targets["modules_to_complete"].split(","):
            _complete_module_via_api(client, sid, module_id)

        decoy_id = targets["decoy_module_ids"].split(",")[0]
        _complete_module_via_api(client, sid, decoy_id)

        state = app.state.session_manager.get(sid)
        assert state.get_module(decoy_id).status == "completed"

        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"expected failure, got {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_partial_chain_completion_fails(client: TestClient):
    """Completing only the first two chain modules (missing 4 and 5) fails."""
    sid, targets = _open_session()
    try:
        partial = targets["modules_to_complete"].split(",")[:2]
        for module_id in partial:
            _complete_module_via_api(client, sid, module_id)

        state = app.state.session_manager.get(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"expected failure, got {result}"
    finally:
        app.state.session_manager.destroy(sid)
