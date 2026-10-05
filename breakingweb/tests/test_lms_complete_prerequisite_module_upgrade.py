"""Solvability proof for the upgraded lms_complete_prerequisite_module task (v2).

The v2 task (hard tier, planning-loaded) requires the agent to DERIVE the real
prerequisite segment from the unlock links rather than from display order or the
"available" badge. The course now contains THREE off-chain "available" decoy
modules (``decoy_module_ids``) alongside the real chain, so "available" alone no
longer identifies the chain — the agent must follow ``unlock_value`` to find the
next two consecutive chain modules:

  * the next available chain module (``next_chain_module_ids[0]`` == module index 1), and
  * its min-score-gated successor (``next_chain_module_ids[1]`` == module index 2),
    which becomes unlocked once the earlier module is completed.

Completing the second segment module triggers the server cascade
(``_unlock_available_modules``) which flips the next chain module
(``cascade_unlocked_module_id``) from ``locked`` to ``available``. Every other
module — the pre-existing completed module, later locked chain modules, and the
three off-chain decoys — must remain frozen, and NO module outside the segment
may be completed (completing a decoy or the cascade-unlocked successor is a hard
failure on the critical overshoot constraint).

The correct solution is driven through the REAL backend endpoints
(``POST /api/env/lms/modules/{id}/items/{idx}/complete`` and
``POST /api/env/lms/modules/{id}/complete``) so the test confirms the seed is
achievable past every server gate (unlock + all-content-items guards + cascade).
The session is created on ``app.state.session_manager`` — the exact same manager
the API routes resolve via ``get_session_manager`` — so the TestClient operates on
the very state object we then hand to ``evaluate``.
"""

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_complete_prerequisite_module"
PREFIX = "/api/env/lms"


def _new_session():
    """Create a session on the SAME manager the API routes use."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session("lms", TASK_ID, 42)
    return sm, sid, dict(targets)


def _module_ids(targets):
    return targets["module_ids"].split(",")


def _segment_ids(targets):
    return targets["next_chain_module_ids"].split(",")


def _decoy_ids(targets):
    return targets["decoy_module_ids"].split(",")


def _complete_module_via_backend(client: TestClient, sid: str, module_id: str, state) -> None:
    """Complete every content item, then complete the module, via real endpoints."""
    module = state.get_module(module_id)
    assert module is not None, f"module {module_id} missing"
    for idx in range(len(module.content_items)):
        resp = client.post(
            f"{PREFIX}/modules/{module_id}/items/{idx}/complete",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, (module_id, idx, resp.status_code, resp.text)
    resp = client.post(
        f"{PREFIX}/modules/{module_id}/complete",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, (module_id, resp.status_code, resp.text)


def test_seed_shape_matches_design():
    """The seed exposes the planning-relevant discriminators the diff relies on."""
    sm, sid, targets = _new_session()
    state = sm.get(sid)
    mids = _module_ids(targets)
    seg = _segment_ids(targets)
    decoys = _decoy_ids(targets)

    # The re-derivable segment is the two consecutive chain modules at index 1, 2.
    assert seg == mids[1:3], (seg, mids)
    assert targets["next_available_module_id"] == seg[0]
    assert targets["first_locked_module_id"] == seg[1]
    assert targets["cascade_unlocked_module_id"] == mids[3]

    # Three off-chain decoys exist, are NOT part of the chain, and are completable
    # ("available", unlock_condition "none") so display/"available" no longer
    # separates chain from supplement.
    assert len(decoys) == 3
    for d in decoys:
        m = state.get_module(d)
        assert m is not None and m.id not in mids
        assert m.status == "available" and m.unlock_condition == "none"

    # There is more than one "available" module, so "first available = target"
    # is not a valid heuristic — the agent must follow prerequisite links.
    available = [m.id for m in state.modules if m.status == "available"]
    assert seg[0] in available
    assert len([a for a in available if a in decoys]) == 3

    m_avail = state.get_module(seg[0])
    m_gate = state.get_module(seg[1])
    assert m_avail.status == "available"
    assert m_gate.status == "locked" and m_gate.unlock_condition == "min_score"


def test_correct_trajectory_evaluates_to_pass():
    """Driving exactly the derived two-module segment through the backend passes."""
    sm, sid, targets = _new_session()
    state = sm.get(sid)
    mids = _module_ids(targets)
    seg = _segment_ids(targets)

    client = TestClient(app)
    # Complete in prerequisite order so the second module's min-score gate is met.
    for module_id in seg:
        _complete_module_via_backend(client, sid, module_id, sm.get(sid))

    state = sm.get(sid)
    by_id = {m.id: m for m in state.modules}
    assert by_id[seg[0]].status == "completed"
    assert by_id[seg[1]].status == "completed"
    assert by_id[mids[3]].status == "available"  # cascade
    assert by_id[mids[4]].status == "locked"      # stays min-score-locked
    assert by_id[mids[0]].status == "completed"   # pre-existing
    # Decoys stay untouched.
    for d in _decoy_ids(targets):
        assert by_id[d].status == "available"
    assert len([m for m in state.modules if m.status == "completed"]) == 3

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_wrong_only_first_module_evaluates_to_fail():
    """Completing only the first segment module (skipping the gated successor) fails."""
    sm, sid, targets = _new_session()
    seg = _segment_ids(targets)

    client = TestClient(app)
    _complete_module_via_backend(client, sid, seg[0], sm.get(sid))

    state = sm.get(sid)
    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected fail, got: {result}"


def test_wrong_overshoot_chain_module_evaluates_to_fail():
    """Completing a third chain module (cascade successor) trips the overshoot guard."""
    sm, sid, targets = _new_session()
    mids = _module_ids(targets)
    seg = _segment_ids(targets)

    client = TestClient(app)
    # Complete the segment, then the cascade-unlocked successor (one too many).
    for module_id in seg + [mids[3]]:
        _complete_module_via_backend(client, sid, module_id, sm.get(sid))

    state = sm.get(sid)
    completed = [m.id for m in state.modules if m.status == "completed"]
    assert mids[3] in completed  # we really did overshoot

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected fail, got: {result}"


def test_wrong_completed_offchain_decoy_evaluates_to_fail():
    """Completing an off-chain 'available' decoy (the greedy trap) is a hard failure.

    This is the load-bearing planning failure mode: a model that grounds to
    "available" status or batch-completes available modules grabs a decoy, which
    trips the critical overshoot constraint even though the real segment is done.
    """
    sm, sid, targets = _new_session()
    seg = _segment_ids(targets)
    decoys = _decoy_ids(targets)

    client = TestClient(app)
    # Do the real segment correctly...
    for module_id in seg:
        _complete_module_via_backend(client, sid, module_id, sm.get(sid))
    # ...but also complete one off-chain decoy supplement.
    _complete_module_via_backend(client, sid, decoys[0], sm.get(sid))

    state = sm.get(sid)
    completed = [m.id for m in state.modules if m.status == "completed"]
    assert decoys[0] in completed  # the trap was sprung

    task = get_task(TASK_ID)
    result = evaluate(task=task, server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected fail, got: {result}"
