"""Solvability proof for the v2-upgraded lms_mark_all_announcements_read task.

v1 re-tiered easy -> medium: mark ONLY the unread *urgent* announcements as read,
leaving every unread normal-priority (and every already-read) announcement
untouched. v2 makes the grounding load genuinely harder for a frontier model by
turning the discriminator into a 3-axis, cross-collection join rather than a
plain 2-field filter:

  * priority x is_read cross-product is now fully populated — the seed contains
    unread+urgent (some are targets), unread+normal (decoys, must stay unread),
    AND read+urgent (urgent-looking decoys that are already read), so neither
    "filter on priority" nor "filter on is_read" alone is sufficient.
  * a course-scoping discriminator: the student is a TA in exactly one course.
    The urgent+unread announcement posted in that TA course is a DECOY — the
    agent must JOIN announcement.course_id against enrollment.role and EXCLUDE
    the TA course's urgent announcement from the target set.

Correct trajectory: mark exactly the unread+urgent announcements posted in a
course where the student is enrolled as a *student* (role != "ta"). Driven
through the REAL backend endpoint POST /announcements/{id}/read via starlette
TestClient so the proof confirms the action is reachable past all gates.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _make_session() -> tuple[SessionManager, str, dict]:
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_mark_all_announcements_read",
        seed=42,
    )
    return sm, sid, dict(targets)


def _ids(targets: dict, key: str) -> list[str]:
    return [i for i in targets[key].split(",") if i]


def test_seed_engineers_full_cross_product_and_ta_decoy():
    """The harder base must expose every discriminator the upgrade relies on."""
    sm, sid, targets = _make_session()
    try:
        state = sm.get_state(sid)

        enrolled = _ids(targets, "unread_urgent_enrolled_announcement_ids")
        ta_urgent = _ids(targets, "unread_urgent_ta_course_announcement_ids")
        read_urgent = _ids(targets, "read_urgent_announcement_ids")
        unread_normal = _ids(targets, "unread_normal_announcement_ids")

        # 3 real targets (urgent + unread + student-role course).
        assert len(enrolled) == 3, f"expected 3 enrolled urgent targets, got {enrolled}"
        # At least one urgent+unread decoy sits in the TA course.
        assert len(ta_urgent) >= 1, f"expected a TA-course urgent decoy, got {ta_urgent}"
        # The TA decoy is NOT in the target set (cross-collection join is load-bearing).
        assert not (set(enrolled) & set(ta_urgent))
        # read+urgent decoys exist (the read+urgent cross-product cell).
        assert len(read_urgent) >= 1, f"expected read+urgent decoys, got {read_urgent}"
        # unread+normal decoys exist and are raised in count.
        assert len(unread_normal) >= 5, f"expected >=5 unread-normal decoys, got {unread_normal}"

        by_id = {a.id: a for a in state.announcements}
        # Targets are unread + urgent in the seeded state.
        for aid in enrolled:
            assert by_id[aid].is_read is False and by_id[aid].priority == "urgent"
        # TA decoy is genuinely urgent + unread (so it tempts a naive 2-axis filter).
        for aid in ta_urgent:
            assert by_id[aid].is_read is False and by_id[aid].priority == "urgent"
        # read+urgent decoys are urgent but already read.
        for aid in read_urgent:
            assert by_id[aid].is_read is True and by_id[aid].priority == "urgent"

        # The TA course really carries role == "ta" and the decoy is posted there.
        ta_course_ids = {e.course_id for e in state.enrollments if e.role == "ta"}
        assert ta_course_ids, "expected exactly one TA-role enrollment"
        for aid in ta_urgent:
            assert by_id[aid].course_id in ta_course_ids
    finally:
        sm.destroy(sid)


def test_correct_trajectory_marks_only_enrolled_unread_urgent_and_passes():
    """Marking exactly the student-course unread-urgent set via the real endpoint passes."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    try:
        enrolled = _ids(targets, "unread_urgent_enrolled_announcement_ids")
        assert len(enrolled) == 3

        for ann_id in enrolled:
            resp = client.post(
                f"/api/env/lms/announcements/{ann_id}/read",
                json={"session_id": sid},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["announcement"]["is_read"] is True

        state = sm.get_state(sid)
        # The unread normal decoys and the TA-course urgent decoy stay unread.
        must_stay_unread = set(
            _ids(targets, "unread_normal_announcement_ids")
            + _ids(targets, "unread_urgent_ta_course_announcement_ids")
        )
        for a in state.announcements:
            if a.id in must_stay_unread:
                assert a.is_read is False

        result = evaluate(
            task=get_task("lms_mark_all_announcements_read"),
            server_state=state,
            targets=targets,
            trajectory=[],
        )
        assert result.get("success") is True, f"result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"result: {result}"
        assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2
    finally:
        sm.destroy(sid)


def test_mark_all_read_bulk_shortcut_fails():
    """The naive `mark_all_read` over-marks every unread decoy -> evaluation fails."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    try:
        resp = client.post(
            "/api/env/lms/announcements/mark_all_read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text
        # It marked the 9 unread (4 urgent incl. TA + 5 normal).
        assert resp.json()["marked_read"] == 9

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task("lms_mark_all_announcements_read"),
            server_state=state,
            targets=targets,
            trajectory=[],
        )
        assert result.get("success") is False, f"bulk shortcut should fail: {result}"
    finally:
        sm.destroy(sid)


def test_two_axis_filter_overmarks_ta_course_urgent_fails():
    """Marking ALL unread+urgent (incl. the TA-course one) — the naive 2-axis
    filter that ignores enrollment role — over-marks the TA decoy and fails."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    try:
        all_unread_urgent = _ids(targets, "unread_urgent_announcement_ids")
        ta_urgent = set(_ids(targets, "unread_urgent_ta_course_announcement_ids"))
        # Sanity: the naive set strictly contains the TA decoy.
        assert ta_urgent and ta_urgent.issubset(set(all_unread_urgent))

        for ann_id in all_unread_urgent:
            resp = client.post(
                f"/api/env/lms/announcements/{ann_id}/read",
                json={"session_id": sid},
            )
            assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task("lms_mark_all_announcements_read"),
            server_state=state,
            targets=targets,
            trajectory=[],
        )
        assert result.get("success") is False, (
            f"over-marking the TA-course urgent decoy should fail: {result}"
        )
    finally:
        sm.destroy(sid)


def test_partial_miss_one_enrolled_urgent_fails():
    """Marking only 2 of the 3 enrolled unread-urgent announcements fails the bijection."""
    sm, sid, targets = _make_session()
    client = TestClient(app)
    try:
        enrolled = _ids(targets, "unread_urgent_enrolled_announcement_ids")
        for ann_id in enrolled[:-1]:  # deliberately skip the last enrolled urgent one
            resp = client.post(
                f"/api/env/lms/announcements/{ann_id}/read",
                json={"session_id": sid},
            )
            assert resp.status_code == 200, resp.text

        state = sm.get_state(sid)
        result = evaluate(
            task=get_task("lms_mark_all_announcements_read"),
            server_state=state,
            targets=targets,
            trajectory=[],
        )
        assert result.get("success") is False, f"partial should fail: {result}"
    finally:
        sm.destroy(sid)
