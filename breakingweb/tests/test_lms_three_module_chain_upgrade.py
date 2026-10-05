"""Solvability + near-miss proof for the hardened lms_three_module_chain task.

The task is EXPERT. CS101 contains a single prerequisite chain whose links are a
HETEROGENEOUS mix of ``prerequisite`` and ``min_score`` gates, interleaved among
three off-chain "available" decoy modules that share the chain's title style and
sit at positions that PRECEDE the real currently-available chain module (so the
first module that shows as "available" in position order is a decoy, not the
answer). The agent must re-derive the chain by following the unlock links and
complete exactly the next three chain modules (each requires finishing all three
of its content items first) while leaving the decoys — and every other module —
untouched.

The correct solution is driven through the REAL backend endpoints via a
TestClient so the proof confirms the seed targets are achievable past the
server's prerequisite + min_score + content-item gates (and that the server's
auto-unlock cascade is tolerated by the canonical_diff). Several near-miss
trajectories — completing a decoy, stopping one module short, picking the
position-first "available" decoy, and over-completing into the cascade successor
— must all fail.
"""

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _create_session():
    """Create a session on the app's own SessionManager and return ids/targets.

    Using ``app.state.session_manager`` (rather than a throwaway instance)
    means the TestClient endpoints below mutate the exact same state we later
    evaluate, so the proof exercises the real route gates end to end.
    """
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="lms", task_id="lms_three_module_chain", seed=42
    )
    return sm, sid, dict(targets)


def _complete_module_via_api(client: TestClient, sid: str, state, module_id: str):
    """Complete every content item then mark the module done via real routes."""
    module = state.get_module(module_id)
    assert module is not None, f"module {module_id} missing from state"
    for idx in range(len(module.content_items)):
        r = client.post(
            f"/api/env/lms/modules/{module_id}/items/{idx}/complete",
            json={"session_id": sid},
        )
        assert r.status_code == 200, (module_id, idx, r.status_code, r.text)
    r = client.post(
        f"/api/env/lms/modules/{module_id}/complete",
        json={"session_id": sid},
    )
    assert r.status_code == 200, (module_id, r.status_code, r.text)


def test_correct_trajectory_passes_via_backend():
    sm, sid, targets = _create_session()
    state = sm.get_state(sid)

    chain = targets["next_chain_module_ids"].split(",")
    assert len(chain) == 3, targets["next_chain_module_ids"]

    by_id_initial = {m.id: m for m in state.modules}

    # Structural hardening assertions: the chain is heterogeneous (a min_score
    # gate appears alongside prerequisite gates), each target module carries the
    # bumped 3 content items, and the FIRST module that shows as "available" in
    # position order is an off-chain decoy — so a "pick the first available
    # module" heuristic is actively wrong.
    gate_types = {by_id_initial[m].unlock_condition for m in chain}
    assert "min_score" in gate_types and "prerequisite" in gate_types, gate_types
    for m in chain:
        assert len(by_id_initial[m].content_items) == 3, (m, by_id_initial[m].content_items)
    course_modules = state.modules_for_course(targets["target_course_id"])
    first_available = next(m for m in course_modules if m.status == "available")
    decoy_ids = set(targets["decoy_module_ids"].split(","))
    assert first_available.id in decoy_ids, (
        "expected the position-first available module to be a decoy, got "
        f"{first_available.id}"
    )
    assert chain[0] == targets["next_available_module_id"], (chain[0], targets)

    with TestClient(app) as client:
        for module_id in chain:
            _complete_module_via_api(client, sid, state, module_id)

    # Refresh state handle after mutations.
    state = sm.get_state(sid)

    # Sanity: the three target chain modules are completed, the cascade
    # successor is now available (server side effect), and the decoys are
    # still untouched.
    by_id = {m.id: m for m in state.modules}
    for module_id in chain:
        assert by_id[module_id].status == "completed", module_id
    cascade_id = targets["cascade_unlocked_module_id"]
    assert by_id[cascade_id].status == "available", cascade_id
    for decoy_id in targets["decoy_module_ids"].split(","):
        assert by_id[decoy_id].status == "available", decoy_id

    result = evaluate(
        task=get_task("lms_three_module_chain"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    # Richer than the legacy 2-check eval (update + many invariants/constraints).
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_completing_a_decoy_module_fails():
    """Near-miss: agent completes the three chain modules BUT also a decoy."""
    sm, sid, targets = _create_session()
    state = sm.get_state(sid)

    chain = targets["next_chain_module_ids"].split(",")
    decoy_id = targets["decoy_module_ids"].split(",")[0]

    with TestClient(app) as client:
        for module_id in chain:
            _complete_module_via_api(client, sid, state, module_id)
        # The decoy has unlock_condition "none", so it is completable on its
        # own — but the task forbids touching it.
        _complete_module_via_api(client, sid, state, decoy_id)

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("lms_three_module_chain"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_completing_only_two_chain_modules_fails():
    """Near-miss: agent stops one module short of the requested three."""
    sm, sid, targets = _create_session()
    state = sm.get_state(sid)

    chain = targets["next_chain_module_ids"].split(",")

    with TestClient(app) as client:
        for module_id in chain[:2]:
            _complete_module_via_api(client, sid, state, module_id)

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("lms_three_module_chain"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_picking_position_first_available_decoy_fails():
    """Near-miss: agent follows a "first available module in the list" heuristic.

    The position-first available module is an off-chain decoy. Completing it
    (plus the three real chain modules) must fail the decoy / exact-set
    constraints.
    """
    sm, sid, targets = _create_session()
    state = sm.get_state(sid)

    chain = targets["next_chain_module_ids"].split(",")
    course_modules = state.modules_for_course(targets["target_course_id"])
    decoy_ids = set(targets["decoy_module_ids"].split(","))
    first_available_decoy = next(
        m for m in course_modules if m.status == "available" and m.id in decoy_ids
    )

    with TestClient(app) as client:
        for module_id in chain:
            _complete_module_via_api(client, sid, state, module_id)
        _complete_module_via_api(client, sid, state, first_available_decoy.id)

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("lms_three_module_chain"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"


def test_over_completing_into_cascade_successor_fails():
    """Near-miss: agent completes the requested three AND the cascade successor.

    The successor auto-unlocks when the third module is completed; a greedy
    "keep going" agent then completes it too, busting the exact-completed-count
    and exact-set constraints.
    """
    sm, sid, targets = _create_session()
    state = sm.get_state(sid)

    chain = targets["next_chain_module_ids"].split(",")
    cascade_id = targets["cascade_unlocked_module_id"]
    assert cascade_id, "expected a cascade successor for this near-miss"

    with TestClient(app) as client:
        for module_id in chain:
            _complete_module_via_api(client, sid, state, module_id)
        # Refresh so the successor is now unlocked/available before completing.
        state = sm.get_state(sid)
        _complete_module_via_api(client, sid, state, cascade_id)

    state = sm.get_state(sid)
    result = evaluate(
        task=get_task("lms_three_module_chain"),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"expected failure, got: {result}"
