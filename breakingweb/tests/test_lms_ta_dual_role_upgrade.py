"""Solvability proof for the v2-hardened lms_ta_dual_role task.

Drives the CORRECT solution through the REAL LMS backend endpoints
(starlette TestClient) so we confirm the intended answer is achievable
past every server gate, then evaluates the resulting state through the
canonical_diff evaluator. Several near-miss trajectories are asserted to
fail.

v2 difficulty levers exercised here (primary_primitive == exploration):
  * The student is a TA in TWO courses; GET /peer-reviews returns ALL 12
    reviews assigned to them (8 in the in-scope TA course + 4 in a sibling
    TA course) with NO status cue separating them — the decoys carry the
    SAME assigned/in_progress statuses as the real targets. The agent must
    re-derive scope by tracing each review's assignment -> course.
  * 8 pending peer reviews saturate the bijection (up from 5); 3 of them are
    returned-for-revision (every previously-scored rubric criterion must be
    re-scored STRICTLY higher).
  * Comments must be >= 60 chars AND name the reviewee.
  * Assignment submit must be exactly one attempt with a fresh timestamp,
    pinned to the student course (not either TA course).
  * Two critical guards: exact-cardinality of submitted reviews AND a
    dedicated "did not touch the sibling TA course look-alikes" constraint,
    plus the critical preserve-ALL invariant on peer_reviews.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.runner import controller_headers, ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_ta_dual_role"
ENV = "lms"
SEED = 42


@pytest.fixture()
def client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _create_session(client: TestClient) -> tuple[str, dict]:
    resp = client.post(
        f"/api/env/{ENV}/session",
        json={"task_id": TASK_ID, "seed": SEED},
        headers=controller_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["session_id"], data["resolved_targets"]


def _parse_min_scores(targets: dict) -> dict[str, list[int]]:
    """rid -> [min_clarity, min_depth, min_originality]."""
    out: dict[str, list[int]] = {}
    raw = targets.get("pending_review_min_scores", "")
    for entry in [e for e in raw.split("|") if e]:
        rid, mins = entry.split("=", 1)
        out[rid] = [int(s) for s in mins.split("~")]
    return out


def _parse_name_tokens(targets: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    raw = targets.get("pending_review_name_tokens", "")
    for entry in [e for e in raw.split("|") if e]:
        rid, name = entry.split(":", 1)
        out[rid] = name
    return out


def _correct_scores(mins: list[int]) -> dict[str, int]:
    """Pick a valid 1..5 score per criterion that satisfies the minimum."""
    crit = ["clarity", "depth", "originality"]
    return {c: min(max(mins[i], 1), 5) for i, c in enumerate(crit)}


def _comment_for(name: str) -> str:
    base = (
        f"Strong submission overall, {name}. Your analysis is clear and the "
        f"argument is well organized; tighten the conclusion next time."
    )
    assert len(base) >= 60
    return base


def _ids(csv: str) -> list[str]:
    return [v.strip() for v in csv.split(",") if v.strip()]


def test_dual_role_structure_is_a_real_exploration_problem(client: TestClient):
    """The decoys are status-identical and the in-scope set is only resolvable
    by tracing assignment -> course; that's what makes this exploration."""
    sid, targets = _create_session(client)
    pending = _ids(targets["pending_review_ids"])
    sibling = _ids(targets["sibling_pending_review_ids"])
    assert len(pending) == 8
    assert len(sibling) == 4
    assert not (set(pending) & set(sibling))

    state = app.state.session_manager.get_state(sid)

    # Every review (real + decoy) is assigned to the student and visible.
    resp = client.get(f"/api/env/{ENV}/peer-reviews", params={"session_id": sid})
    assert resp.status_code == 200, resp.text
    visible = {r["id"] for r in resp.json()["items"]}
    assert set(pending).issubset(visible)
    assert set(sibling).issubset(visible)

    # No free status filter: decoys share the real statuses (assigned/in_progress).
    by_id = {r.id: r for r in state.peer_reviews}
    real_statuses = {by_id[r].status for r in pending}
    decoy_statuses = {by_id[r].status for r in sibling}
    assert decoy_statuses.issubset({"assigned", "in_progress"})
    assert real_statuses.issubset({"assigned", "in_progress"})

    # Scope is only recoverable via assignment -> course.
    ta_course = targets["ta_course_id"]
    sib_course = targets["sibling_ta_course_id"]
    assert ta_course != sib_course
    for rid in pending:
        a = state.get_assignment(by_id[rid].assignment_id)
        assert a is not None and a.course_id == ta_course
    for rid in sibling:
        a = state.get_assignment(by_id[rid].assignment_id)
        assert a is not None and a.course_id == sib_course

    # The student-submit target is in NEITHER TA course.
    target_a = state.get_assignment(targets["target_assignment_id"])
    assert target_a is not None
    assert target_a.course_id not in (ta_course, sib_course)


def test_correct_trajectory_passes(client: TestClient):
    sid, targets = _create_session(client)
    pending = _ids(targets["pending_review_ids"])
    assert len(pending) == 8
    mins = _parse_min_scores(targets)
    names = _parse_name_tokens(targets)

    # (1) Complete every in-scope pending peer review (leave the sibling ones).
    for rid in pending:
        scores = _correct_scores(mins[rid])
        resp = client.post(
            f"/api/env/{ENV}/peer-reviews/{rid}/submit",
            json={
                "session_id": sid,
                "rubric_scores": scores,
                "comments": _comment_for(names[rid]),
            },
        )
        assert resp.status_code == 200, resp.text

    # (2) Submit the student-course assignment exactly once with the file.
    resp = client.post(
        f"/api/env/{ENV}/assignments/{targets['target_assignment_id']}/submit",
        json={"session_id": sid, "file_name": "ta_student_submission.pdf"},
    )
    assert resp.status_code == 200, resp.text

    state = app.state.session_manager.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"


def test_touching_sibling_course_review_fails(client: TestClient):
    """Near-miss: completing a look-alike review in the SIBLING TA course
    (out of scope) trips the critical sibling guard and preserve-ALL invariant,
    even though all 8 real reviews were done correctly."""
    sid, targets = _create_session(client)
    pending = _ids(targets["pending_review_ids"])
    sibling = _ids(targets["sibling_pending_review_ids"])
    mins = _parse_min_scores(targets)
    names = _parse_name_tokens(targets)

    for rid in pending:
        client.post(
            f"/api/env/{ENV}/peer-reviews/{rid}/submit",
            json={
                "session_id": sid,
                "rubric_scores": _correct_scores(mins[rid]),
                "comments": _comment_for(names[rid]),
            },
        )

    # Wrongly submit ONE sibling-course review.
    bad = sibling[0]
    client.post(
        f"/api/env/{ENV}/peer-reviews/{bad}/submit",
        json={
            "session_id": sid,
            "rubric_scores": {"clarity": 4, "depth": 4, "originality": 4},
            "comments": "Thorough work here with a clear structure and solid supporting detail throughout.",
        },
    )

    client.post(
        f"/api/env/{ENV}/assignments/{targets['target_assignment_id']}/submit",
        json={"session_id": sid, "file_name": "ta_student_submission.pdf"},
    )

    state = app.state.session_manager.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"should fail but passed: {result}"


def test_missing_one_in_scope_review_fails(client: TestClient):
    """Near-miss: completing only 7 of the 8 in-scope reviews leaves the
    bijection unsaturated (critical update[0] + critical cardinality)."""
    sid, targets = _create_session(client)
    pending = _ids(targets["pending_review_ids"])
    mins = _parse_min_scores(targets)
    names = _parse_name_tokens(targets)

    for rid in pending[:-1]:  # skip the last one
        client.post(
            f"/api/env/{ENV}/peer-reviews/{rid}/submit",
            json={
                "session_id": sid,
                "rubric_scores": _correct_scores(mins[rid]),
                "comments": _comment_for(names[rid]),
            },
        )

    client.post(
        f"/api/env/{ENV}/assignments/{targets['target_assignment_id']}/submit",
        json={"session_id": sid, "file_name": "ta_student_submission.pdf"},
    )

    state = app.state.session_manager.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"should fail but passed: {result}"


def test_returned_review_not_improved_fails(client: TestClient):
    """Near-miss: leaving a returned review's previous scores un-improved fails."""
    sid, targets = _create_session(client)
    pending = _ids(targets["pending_review_ids"])
    mins = _parse_min_scores(targets)
    names = _parse_name_tokens(targets)

    # Find a returned-for-revision review (min on some criterion is > 1).
    returned_rid = next(r for r in pending if max(mins[r]) > 1)

    for rid in pending:
        if rid == returned_rid:
            scores = {"clarity": 1, "depth": 1, "originality": 1}
        else:
            scores = _correct_scores(mins[rid])
        client.post(
            f"/api/env/{ENV}/peer-reviews/{rid}/submit",
            json={
                "session_id": sid,
                "rubric_scores": scores,
                "comments": _comment_for(names[rid]),
            },
        )

    client.post(
        f"/api/env/{ENV}/assignments/{targets['target_assignment_id']}/submit",
        json={"session_id": sid, "file_name": "ta_student_submission.pdf"},
    )

    state = app.state.session_manager.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"should fail but passed: {result}"


def test_missing_reviewee_name_fails(client: TestClient):
    """Near-miss: a comment that omits the reviewee's name fails the comment guard."""
    sid, targets = _create_session(client)
    pending = _ids(targets["pending_review_ids"])
    mins = _parse_min_scores(targets)
    names = _parse_name_tokens(targets)

    for idx, rid in enumerate(pending):
        scores = _correct_scores(mins[rid])
        if idx == 0:
            comment = (
                "Overall this is a solid piece of work with a clear thesis and "
                "well-supported reasoning throughout the submission."
            )
        else:
            comment = _comment_for(names[rid])
        client.post(
            f"/api/env/{ENV}/peer-reviews/{rid}/submit",
            json={"session_id": sid, "rubric_scores": scores, "comments": comment},
        )

    client.post(
        f"/api/env/{ENV}/assignments/{targets['target_assignment_id']}/submit",
        json={"session_id": sid, "file_name": "ta_student_submission.pdf"},
    )

    state = app.state.session_manager.get_state(sid)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, f"should fail but passed: {result}"
