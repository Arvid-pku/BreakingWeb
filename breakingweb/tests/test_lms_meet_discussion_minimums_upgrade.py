"""Solvability proof for the v2-hardened lms_meet_discussion_minimums task.

The upgraded (state_tracking) task now requires the agent to:
  * read the TARGET discussion's OWN stated minimums (min_posts=3, min_replies=2)
    while sibling discussions carry DIFFERENT minimums (1 post / 3 replies) so the
    agent cannot copy a neighbor's banner,
  * author exactly 3 new top-level posts,
  * post exactly 2 replies, each attached to a DISTINCT existing classmate post,
  * with fresh timestamps (>= session_start) and substantive bodies (>= 20 chars),
  * without editing existing posts, posting elsewhere, or sending messages.

The correct solution is driven through the REAL backend endpoints
(``/discussions/{id}/posts`` and ``/discussions/{id}/posts/{pid}/reply``) via a
Starlette ``TestClient`` so the proof confirms the answer is achievable past the
route gates (parent-post existence, author identity stamping, etc.).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "lms_meet_discussion_minimums"
ENV_ID = "lms"

_BODY = "My substantive analysis of this discussion topic, paragraph "


def _create_session():
    """Create a session on the app's shared session_manager (so TestClient
    route mutations land on the same state the evaluator reads)."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id=ENV_ID, task_id=TASK_ID, seed=42)
    return sm, sid, dict(targets)


def _parents(targets):
    return [p.strip() for p in targets["reply_parent_post_ids"].split(",") if p.strip()]


def test_seed_exposes_harder_asymmetric_minimums_and_distinct_parents() -> None:
    """The hardened seed must produce ASYMMETRIC target minimums (3 posts / 2
    replies) that differ from the sibling discussions, plus two distinct
    top-level classmate parents to reply to."""
    sm, sid, targets = _create_session()
    try:
        state = sm.get_state(sid)
        assert int(targets["target_min_posts"]) == 3
        assert int(targets["target_min_replies"]) == 2
        # Asymmetry is the discriminator: posts != replies.
        assert int(targets["target_min_posts"]) != int(targets["target_min_replies"])

        parents = _parents(targets)
        assert len(parents) == 2, f"expected 2 distinct reply parents, got {parents}"
        assert len(set(parents)) == 2, "reply parents must be distinct"

        tid = targets["target_discussion_id"]
        by_id = {p.id: p for p in state.discussion_posts}
        for pid in parents:
            post = by_id[pid]
            assert post.discussion_id == tid, "reply parent must live in the target discussion"
            assert post.parent_post_id is None, "reply parent must be a top-level post"
            assert post.author_id != state.student.id, "reply parent must be a classmate post"

        disc = state.get_discussion(tid)
        assert disc.min_posts == 3 and disc.min_replies == 2

        # Sibling discussions must carry DIFFERENT minimums so a neighbor-copy fails.
        siblings = [d for d in state.discussions if d.id != tid]
        assert siblings, "expected sibling discussions"
        for sib in siblings:
            assert (sib.min_posts, sib.min_replies) != (3, 2), (
                "sibling minimums must differ from the target's, "
                f"got {(sib.min_posts, sib.min_replies)}"
            )

        # No pre-existing student top-level post in target (exact-count stays honest).
        student_tl = [
            p for p in state.discussion_posts
            if p.discussion_id == tid and p.author_id == state.student.id and p.parent_post_id is None
        ]
        assert len(student_tl) == 0
    finally:
        sm.destroy(sid)


def test_correct_trajectory_via_backend_passes() -> None:
    """Driving the intended solution through the real endpoints passes evaluate()."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    try:
        tid = targets["target_discussion_id"]
        parents = _parents(targets)

        # 3 new top-level posts (matches min_posts), each with a substantive body.
        for i in range(int(targets["target_min_posts"])):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts",
                json={"session_id": sid, "body": f"{_BODY}{i + 1}."},
            )
            assert resp.status_code == 200, resp.text

        # 2 replies, each to a DISTINCT existing classmate post (matches min_replies).
        for i, parent_id in enumerate(parents):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts/{parent_id}/reply",
                json={"session_id": sid, "body": f"Building on your point, substantive reply {i + 1}."},
            )
            assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is True, f"result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
        # canonical_diff coverage is rich: 4 create checks + invariants + constraints.
        assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 5
    finally:
        sm.destroy(sid)


def test_reply_to_non_seed_classmate_parents_passes() -> None:
    """Freedom path (regression): the instruction allows replying to ANY distinct
    existing classmate posts, not only the seed's first two. Replying to classmate
    top-level posts OUTSIDE reply_parent_post_ids must PASS — previously the first-2
    bijection + set-equality constraint mis-graded this instruction-faithful path as
    failure."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    try:
        tid = targets["target_discussion_id"]
        state = sm.get_state(sid)
        seed_parents = set(_parents(targets))
        # Eligible = classmate top-level posts in the target discussion that are NOT
        # the seed's first-2 pinned parents.
        alt_parents = [
            p.id for p in state.discussion_posts
            if p.discussion_id == tid and p.parent_post_id is None
            and p.author_id != state.student.id and p.id not in seed_parents
        ]
        assert len(alt_parents) >= 2, f"need >=2 non-seed classmate parents, got {alt_parents}"
        chosen = alt_parents[:2]

        for i in range(int(targets["target_min_posts"])):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts",
                json={"session_id": sid, "body": f"{_BODY}{i + 1}."},
            )
            assert resp.status_code == 200, resp.text
        for i, parent_id in enumerate(chosen):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts/{parent_id}/reply",
                json={"session_id": sid, "body": f"Engaging with your distinct point, substantive reply {i + 1}."},
            )
            assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is True, (
            f"replying to non-seed classmate parents is instruction-compliant: {result}"
        )
        assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    finally:
        sm.destroy(sid)


def test_reply_to_same_parent_twice_fails() -> None:
    """Near-miss: correct counts but both replies attach to the SAME parent.

    The reply bijection over the two distinct required parents cannot saturate
    (only one parent is covered), so the task must fail."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    try:
        tid = targets["target_discussion_id"]
        parents = _parents(targets)

        for i in range(int(targets["target_min_posts"])):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts",
                json={"session_id": sid, "body": f"{_BODY}{i + 1}."},
            )
            assert resp.status_code == 200, resp.text

        # Both replies target the SAME (first) parent — distinctness violated.
        for i in range(int(targets["target_min_replies"])):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts/{parents[0]}/reply",
                json={"session_id": sid, "body": f"Same-parent substantive reply {i + 1}."},
            )
            assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"expected failure, got {result}"
    finally:
        sm.destroy(sid)


def test_neighbor_minimums_two_posts_two_replies_fails() -> None:
    """Near-miss: the agent used a SYMMETRIC 2/2 count (the v1 answer, or a
    neighbor-derived guess) instead of the target's own 3 posts / 2 replies.

    Only 2 of the required 3 top-level posts exist, so the exact-count
    constraint fails."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    try:
        tid = targets["target_discussion_id"]
        parents = _parents(targets)

        # Wrong post count: 2 instead of the target's 3.
        for i in range(2):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts",
                json={"session_id": sid, "body": f"{_BODY}{i + 1}."},
            )
            assert resp.status_code == 200, resp.text

        for i, parent_id in enumerate(parents):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts/{parent_id}/reply",
                json={"session_id": sid, "body": f"Distinct substantive reply {i + 1}."},
            )
            assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"expected failure, got {result}"
    finally:
        sm.destroy(sid)


def test_short_placeholder_bodies_fail() -> None:
    """Near-miss: correct counts and distinct parents, but the bodies are short
    placeholders (< 20 chars), so the substantive-body gate fails."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    try:
        tid = targets["target_discussion_id"]
        parents = _parents(targets)

        for i in range(int(targets["target_min_posts"])):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts",
                json={"session_id": sid, "body": "ok"},
            )
            assert resp.status_code == 200, resp.text

        for i, parent_id in enumerate(parents):
            resp = client.post(
                f"/api/env/lms/discussions/{tid}/posts/{parent_id}/reply",
                json={"session_id": sid, "body": "+1"},
            )
            assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"expected failure, got {result}"
    finally:
        sm.destroy(sid)


def test_only_one_post_one_reply_fails() -> None:
    """Near-miss: the OLD easy answer (1 post + 1 reply) no longer satisfies the
    raised minimums (3 posts + 2 distinct replies)."""
    sm, sid, targets = _create_session()
    client = TestClient(app)
    try:
        tid = targets["target_discussion_id"]
        parents = _parents(targets)

        resp = client.post(
            f"/api/env/lms/discussions/{tid}/posts",
            json={"session_id": sid, "body": f"{_BODY}1."},
        )
        assert resp.status_code == 200, resp.text
        resp = client.post(
            f"/api/env/lms/discussions/{tid}/posts/{parents[0]}/reply",
            json={"session_id": sid, "body": "Only one substantive reply here."},
        )
        assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"expected failure, got {result}"
    finally:
        sm.destroy(sid)
