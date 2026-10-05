"""Solvability proof for the upgraded ``lms_read_urgent_announcement`` task.

v2 difficulty upgrade. The single graded action is no longer "find the urgent
announcement" or even "find the most recent urgent unread among an
unambiguous set". The feed is now a CONTESTED three-way conjunction problem:
the agent must mark exactly the announcement that is urgent AND unread AND has
the latest ``posted_at`` among the urgent-unread set, while the feed deliberately
contains two wrong-branch attractors:

* a high-salience URGENT but ALREADY-READ decoy posted *more recently* than the
  true target (the "newest urgent overall" — drops the *unread* qualifier), and
* a NORMAL-priority UNREAD decoy posted later than every urgent record (the
  "newest unread overall" — drops the *urgent* qualifier).

The genuine urgent-unread runner-up is only ONE SECOND behind the target, so a
position/coarse-time heuristic cannot resolve it — an exact ``posted_at``
comparison is required. The discriminator ``target_urgent_announcement_id`` is
re-derived in the seed builder (max posted_at over the urgent-unread pool), so
the positive predicate stays a clean single-key expr.

Correct path is driven through the REAL backend endpoint
``POST /api/env/lms/announcements/{id}/read`` via TestClient; evaluation goes
through the real ``evaluate()``.
"""

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager, materialize_task_state
from breakingweb.runner import controller_headers, ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_read_urgent_announcement"
ENV_ID = "lms"
SEED = 42


def _client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _state_and_targets(seed: int = SEED):
    """Return (state, targets) from a fresh materialization, robust to the
    tuple ordering of ``materialize_task_state``."""
    res = materialize_task_state(ENV_ID, TASK_ID, seed)
    state = next(x for x in res if hasattr(x, "announcements"))
    targets = next(
        dict(x)
        for x in res
        if isinstance(x, dict) and "target_urgent_announcement_id" in dict(x)
    )
    return state, targets


def _create_api_session(client: TestClient, seed: int = SEED) -> tuple[str, dict]:
    r = client.post(
        f"/api/env/{ENV_ID}/session",
        json={"task_id": TASK_ID, "seed": seed},
        headers=controller_headers(),
    )
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _, targets = _state_and_targets(seed)
    return sid, dict(targets)


def _mark_read(client: TestClient, sid: str, ann_id: str):
    return client.post(
        f"/api/env/{ENV_ID}/announcements/{ann_id}/read",
        json={"session_id": sid},
        headers={"Referer": f"http://testserver/env/{ENV_ID}/courses?session={sid}"},
    )


def test_targets_are_nontrivial_and_contested():
    """The graded answer must be a NON-FIRST urgent (re-derived by recency),
    there must be several urgent-unread competing, AND the feed must contain the
    two wrong-branch attractors that make the conjunction load-bearing:
    a newer already-read urgent, and a newer unread normal."""
    state, targets = _state_and_targets()
    answer = targets["target_urgent_announcement_id"]
    first_urgent = targets["urgent_announcement_id"]
    urgent_unread = targets["urgent_unread_announcement_ids"].split(",")
    assert answer, "no discriminator target produced"
    assert len(urgent_unread) >= 3, urgent_unread
    assert answer in urgent_unread
    # The discriminator genuinely matters: the answer is a later urgent than
    # the first one an agent encounters.
    assert answer != first_urgent, (answer, first_urgent)

    anns = {a.id: a for a in state.announcements}
    target = anns[answer]

    # (1) Newest urgent OVERALL is an already-read decoy, NOT the target.
    newest_urgent = max(
        (a for a in state.announcements if a.priority == "urgent"),
        key=lambda a: a.posted_at,
    )
    assert newest_urgent.id != answer, "target must not be the newest urgent overall"
    assert newest_urgent.is_read is True, "the newest urgent decoy must be already read"

    # (2) Newest UNREAD overall is a normal-priority decoy, NOT the target.
    newest_unread = max(
        (a for a in state.announcements if not a.is_read),
        key=lambda a: a.posted_at,
    )
    assert newest_unread.id != answer, "target must not be the newest unread overall"
    assert newest_unread.priority == "normal", "the newest unread decoy must be normal"

    # (3) The genuine runner-up urgent-unread is only seconds behind the target,
    # defeating coarse-time/position heuristics.
    runner_up = anns[first_urgent]
    gap = (target.posted_at - runner_up.posted_at).total_seconds()
    assert 0 < gap <= 5, f"runner-up gap should be a few seconds, got {gap}s"

    # (4) Target is genuinely the latest urgent-unread by posted_at.
    derived = max(
        (a for a in state.announcements if a.priority == "urgent" and not a.is_read),
        key=lambda a: a.posted_at,
    )
    assert derived.id == answer, (derived.id, answer)


def test_correct_trajectory_via_real_endpoint_passes():
    """Marking the most-recent urgent unread announcement read passes 1.0."""
    client = _client()
    sid, targets = _create_api_session(client)
    answer = targets["target_urgent_announcement_id"]

    resp = _mark_read(client, sid, answer)
    assert resp.status_code == 200, resp.text

    state = app.state.session_manager.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    # canonical_diff is richer than a 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_wrong_first_urgent_announcement_fails():
    """Marking the salient runner-up urgent (1s older, NOT the latest) fails:
    it both misses the positive obligation and trips the non-target invariant."""
    client = _client()
    sid, targets = _create_api_session(client)
    wrong = targets["urgent_announcement_id"]
    assert wrong != targets["target_urgent_announcement_id"]

    resp = _mark_read(client, sid, wrong)
    assert resp.status_code == 200, resp.text

    state = app.state.session_manager.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_wrong_newest_urgent_but_already_read_decoy_fails():
    """Marking the NEWEST urgent overall (an already-read decoy — drops the
    'unread' qualifier) fails: the positive where.id expr does not match, and
    marking a non-target announcement read trips the frozen-sibling invariant."""
    client = _client()
    sid, targets = _create_api_session(client)
    state = app.state.session_manager.get(sid)
    newest_urgent = max(
        (a for a in state.announcements if a.priority == "urgent"),
        key=lambda a: a.posted_at,
    )
    assert newest_urgent.id != targets["target_urgent_announcement_id"]

    resp = _mark_read(client, sid, newest_urgent.id)
    assert resp.status_code == 200, resp.text

    state = app.state.session_manager.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_wrong_newest_unread_normal_decoy_fails():
    """Marking the NEWEST unread overall (a normal-priority decoy — drops the
    'urgent' qualifier) fails the positive obligation and the invariant."""
    client = _client()
    sid, targets = _create_api_session(client)
    state = app.state.session_manager.get(sid)
    newest_unread = max(
        (a for a in state.announcements if not a.is_read),
        key=lambda a: a.posted_at,
    )
    assert newest_unread.id != targets["target_urgent_announcement_id"]
    assert newest_unread.priority == "normal"

    resp = _mark_read(client, sid, newest_unread.id)
    assert resp.status_code == 200, resp.text

    state = app.state.session_manager.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_mark_all_read_fails():
    """Bulk mark-all-read marks every announcement read, which violates the
    'other urgent unread left unread' constraint and the non-target invariant."""
    client = _client()
    sid, targets = _create_api_session(client)

    resp = client.post(
        f"/api/env/{ENV_ID}/announcements/mark_all_read",
        json={"session_id": sid},
        headers={"Referer": f"http://testserver/env/{ENV_ID}/courses?session={sid}"},
    )
    assert resp.status_code == 200, resp.text

    state = app.state.session_manager.get(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"


def test_extra_side_effect_message_fails():
    """Doing the right read PLUS sending a message trips the no-messages
    constraint/invariant."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id=ENV_ID, task_id=TASK_ID, seed=SEED)
    targets = dict(targets)
    state = sm.get_state(sid)

    # Correct read (mirrors POST /announcements/{id}/read).
    ann = state.get_announcement(targets["target_urgent_announcement_id"])
    assert ann is not None
    ann.is_read = True
    # Illegal side-effect: send a message.
    state.sent_messages.append(
        {"to": "advisor", "subject": "fyi", "body": "done", "sent_at": "x", "from": "s"}
    )

    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=targets,
        trajectory=[],
    )
    assert result.get("success") is False, f"result: {result}"
