"""Solvability proof for the upgraded lms_submit_peer_review task.

Confirms the (now harder) "redo the returned peer review" task:
  * is achievable past the real backend gate (POST /peer-reviews/{id}/submit),
  * passes the canonical_diff evaluator when the agent submits the RETURNED
    review with all three rubric criteria scored to the EXACT re-derived values
    (previous score + 2 capped at 5; unscored criterion -> 3) and a >=80-char
    comment that addresses the reviewee by first name, and
  * fails on representative near-miss trajectories (wrong review, plausible but
    NON-exact scores, too-short comment, comment missing the reviewee first name).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "lms_submit_peer_review"


def _create_session(client: TestClient) -> str:
    resp = client.post(f"/api/env/lms/session", json={"task_id": TASK_ID, "seed": 42})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


def _targets_and_state(session_id: str):
    sm = app.state.session_manager
    targets = dict(sm.get_targets(session_id))
    state = sm.get_state(session_id)
    return targets, state


def _good_comment(reviewee_first: str) -> str:
    base = (
        f"Hi {reviewee_first}, your submission states its thesis clearly, but the "
        f"middle section needs deeper analysis and at least one original example "
        f"to support the central claim before resubmission."
    )
    assert len(base.strip()) >= 80
    assert reviewee_first.lower() in base.lower()
    return base


def _correct_scores(targets: dict) -> dict:
    """The EXACT re-derived scores: prev+2 (cap 5) per scored criterion, 3 if unscored."""
    return {
        "clarity": int(targets["req_clarity"]),
        "depth": int(targets["req_depth"]),
        "originality": int(targets["req_originality"]),
    }


def test_correct_trajectory_passes():
    client = TestClient(app)
    session_id = _create_session(client)
    targets, _ = _targets_and_state(session_id)

    review_id = targets["target_review_id"]
    scores = _correct_scores(targets)
    comment = _good_comment(targets["reviewee_first"])

    resp = client.post(
        f"/api/env/lms/peer-reviews/{review_id}/submit",
        json={"session_id": session_id, "rubric_scores": scores, "comments": comment},
    )
    assert resp.status_code == 200, resp.text

    # Re-read post-mutation state + targets from the app's session manager.
    targets, state = _targets_and_state(session_id)
    result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # Richer than the legacy 2-check eval: positive update + many invariants.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_wrong_review_fails():
    """Submitting a DIFFERENT (assigned) review instead of the returned one fails."""
    client = TestClient(app)
    session_id = _create_session(client)
    targets, state = _targets_and_state(session_id)

    target_id = targets["target_review_id"]
    other = next(
        (r for r in state.peer_reviews if r.id != target_id and r.status != "submitted"),
        None,
    )
    assert other is not None, "expected another non-submitted review to exist"

    comment = _good_comment(targets["reviewee_first"])
    resp = client.post(
        f"/api/env/lms/peer-reviews/{other.id}/submit",
        json={"session_id": session_id, "rubric_scores": _correct_scores(targets), "comments": comment},
    )
    assert resp.status_code == 200, resp.text

    targets, state = _targets_and_state(session_id)
    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected failure, got {result}"


def test_non_exact_scores_fail():
    """Submitting the returned review with plausible-but-NOT-exact re-derived scores fails.

    A near-miss agent that improves every criterion (max-everything, or +1 instead
    of the published +2) lands wrong integers and must fail the exact predicate.
    """
    client = TestClient(app)
    session_id = _create_session(client)
    targets, _ = _targets_and_state(session_id)

    review_id = targets["target_review_id"]
    correct = _correct_scores(targets)
    # Plausible "improve everything to the top" answer that does NOT match the rule.
    near_miss = {"clarity": 5, "depth": 5, "originality": 5}
    assert near_miss != correct, "near-miss must differ from the exact answer"
    comment = _good_comment(targets["reviewee_first"])

    resp = client.post(
        f"/api/env/lms/peer-reviews/{review_id}/submit",
        json={"session_id": session_id, "rubric_scores": near_miss, "comments": comment},
    )
    assert resp.status_code == 200, resp.text

    targets, state = _targets_and_state(session_id)
    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected failure, got {result}"


def test_unchanged_previous_scores_fails():
    """Submitting the returned review but keeping the previous clarity/depth fails."""
    client = TestClient(app)
    session_id = _create_session(client)
    targets, _ = _targets_and_state(session_id)

    review_id = targets["target_review_id"]
    # Reuse the exact previously-recorded clarity & depth -> must NOT pass.
    prev_clarity = int(targets["prev_clarity"])
    prev_depth = int(targets["prev_depth"])
    scores = {"clarity": prev_clarity, "depth": prev_depth, "originality": 3}
    comment = _good_comment(targets["reviewee_first"])

    resp = client.post(
        f"/api/env/lms/peer-reviews/{review_id}/submit",
        json={"session_id": session_id, "rubric_scores": scores, "comments": comment},
    )
    assert resp.status_code == 200, resp.text

    targets, state = _targets_and_state(session_id)
    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected failure, got {result}"


def test_short_comment_fails():
    """A comment shorter than 80 chars fails even with correct scores."""
    client = TestClient(app)
    session_id = _create_session(client)
    targets, _ = _targets_and_state(session_id)

    review_id = targets["target_review_id"]
    scores = _correct_scores(targets)
    short = f"{targets['reviewee_first']}: good work overall."  # < 80 chars
    assert len(short.strip()) < 80

    resp = client.post(
        f"/api/env/lms/peer-reviews/{review_id}/submit",
        json={"session_id": session_id, "rubric_scores": scores, "comments": short},
    )
    assert resp.status_code == 200, resp.text

    targets, state = _targets_and_state(session_id)
    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected failure, got {result}"


def test_comment_missing_reviewee_name_fails():
    """A long comment that never names the reviewee (first name) fails the comment predicate."""
    client = TestClient(app)
    session_id = _create_session(client)
    targets, _ = _targets_and_state(session_id)

    review_id = targets["target_review_id"]
    scores = _correct_scores(targets)
    comment = (
        "The submission states its thesis clearly, but the middle section needs "
        "deeper analysis and at least one original example to support the central claim."
    )
    assert len(comment.strip()) >= 80
    assert targets["reviewee_first"].lower() not in comment.lower()

    resp = client.post(
        f"/api/env/lms/peer-reviews/{review_id}/submit",
        json={"session_id": session_id, "rubric_scores": scores, "comments": comment},
    )
    assert resp.status_code == 200, resp.text

    targets, state = _targets_and_state(session_id)
    result = evaluate(task=get_task(TASK_ID), server_state=state, targets=dict(targets), trajectory=[])
    assert result.get("success") is False, f"expected failure, got {result}"
