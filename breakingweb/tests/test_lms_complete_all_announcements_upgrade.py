"""Solvability proof for the upgraded lms_complete_all_announcements task.

The upgraded task ("Clear Urgent Announcements for Active Courses") is a
SELECTIVE announcement-completion task: the agent must mark read ONLY the
unread announcements that are (a) urgent priority AND (b) belong to a course
the student is actively enrolled in (status == "enrolled"). Unread+urgent
announcements in a NON-enrolled course (waitlisted OR dropped) must stay
unread, and every non-urgent unread announcement must stay unread.

v2 hardening (vs the v1 upgrade):
  * Urgency is no longer title-readable — the builder runs with
    plain_urgent_titles=True, so the "URGENT:" prefix is gone and priority is
    ONLY discoverable in the structured `priority` field.
  * The non-enrolled cross-reference now spans TWO statuses across TWO courses
    (one waitlisted + one dropped via dropped_count=1), and the urgent feed is
    larger (count=20, unread=14, urgent=9), so ~2 urgent-unread land in
    non-enrolled courses and the positive set is ~7. A single missed
    cross-reference is no longer the whole failure surface.
  * Two NEW critical discriminators punish BOTH error directions: an
    under-marking guard (every target must be read) and an exact-count guard
    (the number of unread->read transitions must equal the target size).

This test:
  1. Drives the CORRECT solution through the REAL backend
     POST /announcements/{id}/read endpoints via TestClient (confirms the
     intended answer is achievable past every backend gate) and asserts the
     canonical_diff evaluator scores it as a pass.
  2. Asserts four NEAR-MISS trajectories fail:
       - the mark_all_read shortcut (touches preserved-unread decoys),
       - "mark every urgent" (touches the non-enrolled urgent decoys),
       - "mark every unread" (touches non-urgent unread decoys),
       - under-marking (skips one target — trips the no-under-marking guard).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.runner import ensure_controller_secret
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_complete_all_announcements"
SEED = 42


@pytest.fixture()
def client() -> TestClient:
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


def _ctrl_headers() -> dict:
    return {CONTROLLER_SECRET_HEADER: app.state.controller_secret}


def _split(csv: str) -> list[str]:
    return [x for x in (csv or "").split(",") if x]


def _create_session(client: TestClient) -> tuple[str, dict]:
    resp = client.post(
        "/api/env/lms/session",
        json={"task_id": TASK_ID, "seed": SEED},
        headers=_ctrl_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    sid = data["session_id"]
    targets = data["resolved_targets"]
    return sid, targets


def _state_for(sid: str):
    return app.state.session_manager.get_state(sid)


def _evaluate(sid: str, targets: dict) -> dict:
    state = _state_for(sid)
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )


# ---------------------------------------------------------------------------
# Correct solution — drive real endpoints
# ---------------------------------------------------------------------------

def test_correct_selective_completion_passes():
    client = TestClient(app)
    app.state.controller_secret = ensure_controller_secret()
    sid, targets = _create_session(client)

    target_ids = _split(targets["enrolled_unread_urgent_announcement_ids"])
    # The discriminator must be non-vacuous and must NOT be the whole unread set.
    # v2 raises the positive cardinality so a single cross-reference is not the
    # entire failure surface.
    assert len(target_ids) >= 5, target_ids
    assert set(target_ids) != set(_split(targets["unread_announcement_ids"]))
    assert _split(targets["preserved_unread_announcement_ids"]), "need decoys"

    # v2: the non-enrolled cross-reference spans >=2 courses (waitlisted+dropped)
    # and >=2 urgent-unread announcements must be preserved because their course
    # is not enrolled — confirming the join is genuinely load-bearing.
    state = _state_for(sid)
    non_enrolled = set(_split(targets["non_enrolled_course_ids"]))
    assert len(non_enrolled) >= 2, non_enrolled
    urgent_unread_in_non_enrolled = [
        a.id for a in state.announcements
        if a.priority == "urgent" and not a.is_read and a.course_id in non_enrolled
    ]
    assert len(urgent_unread_in_non_enrolled) >= 2, urgent_unread_in_non_enrolled
    # v2: urgency must NOT be readable from the title string (no "URGENT:" tell).
    for a in state.announcements:
        if a.priority == "urgent":
            assert "URGENT" not in a.title.upper(), a.title

    # Drive the REAL mark-read endpoint for each target announcement only.
    for ann_id in target_ids:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["announcement"]["is_read"] is True

    result = _evaluate(sid, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
    # canonical_diff is richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


# ---------------------------------------------------------------------------
# Near-miss: mark_all_read shortcut (touches preserved-unread decoys)
# ---------------------------------------------------------------------------

def test_mark_all_read_shortcut_fails():
    client = TestClient(app)
    app.state.controller_secret = ensure_controller_secret()
    sid, targets = _create_session(client)

    resp = client.post(
        "/api/env/lms/announcements/mark_all_read",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"mark_all_read must fail: {result}"


# ---------------------------------------------------------------------------
# Near-miss: "mark every urgent" — touches the waitlisted-course urgent decoy
# ---------------------------------------------------------------------------

def test_mark_all_urgent_including_waitlisted_fails():
    client = TestClient(app)
    app.state.controller_secret = ensure_controller_secret()
    sid, targets = _create_session(client)
    state = _state_for(sid)

    # Mark read every urgent announcement, ignoring enrollment status — this
    # incorrectly touches the urgent announcement in the waitlisted course.
    urgent_ids = [a.id for a in state.announcements if a.priority == "urgent" and not a.is_read]
    # Must include at least one waitlisted-course urgent decoy for the test to be meaningful.
    preserved = set(_split(targets["preserved_unread_announcement_ids"]))
    assert any(uid in preserved for uid in urgent_ids), urgent_ids
    for ann_id in urgent_ids:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"all-urgent must fail: {result}"


# ---------------------------------------------------------------------------
# Near-miss: "mark every unread" — touches non-urgent unread decoys
# ---------------------------------------------------------------------------

def test_mark_all_unread_fails():
    client = TestClient(app)
    app.state.controller_secret = ensure_controller_secret()
    sid, targets = _create_session(client)

    for ann_id in _split(targets["unread_announcement_ids"]):
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"all-unread must fail: {result}"


# ---------------------------------------------------------------------------
# Near-miss: under-marking — skip exactly one target announcement
# ---------------------------------------------------------------------------

def test_under_marking_one_target_fails():
    client = TestClient(app)
    app.state.controller_secret = ensure_controller_secret()
    sid, targets = _create_session(client)

    target_ids = _split(targets["enrolled_unread_urgent_announcement_ids"])
    assert len(target_ids) >= 2, target_ids
    # Mark all but the last target — a single missed item must still fail the
    # v2 "no under-marking" critical discriminator.
    for ann_id in target_ids[:-1]:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"under-marking must fail: {result}"
