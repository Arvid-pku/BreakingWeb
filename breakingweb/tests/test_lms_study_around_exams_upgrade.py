"""Solvability proof for the hardened lms_study_around_exams task.

The task was upgraded from medium → hard (v2). The agent must:
  1. Read the calendar and identify which courses have an exam in the next 14 days
     — where several exams sit RIGHT around the 14-day boundary (days 12-13 just
     inside, days 15-16 just outside), so a per-course exam-date-vs-cutoff
     comparison is required (not "the nearest few exams").
  2. Mark ONLY the UNREAD announcements in those exam-courses as read.
  3. Leave every other announcement untouched (unread announcements in
     non-exam courses — including the near-boundary day-15/16 courses — and
     already-read announcements everywhere).

The discriminator (unread AND course-has-upcoming-exam) is precomputed in the
seed builder and exposed as the scalar target ``unread_in_exam_courses_ids``.
The correct solution sweeps exactly that set via the real backend endpoint.

Modeled on test_pp_immunization_end_to_end.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.seeders.lms import derive_anchor_time
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _create_session() -> tuple[SessionManager, str, dict, object]:
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="lms",
        task_id="lms_study_around_exams",
        seed=42,
    )
    state = sm.get_state(sid)
    return sm, sid, dict(targets), state


def test_seed_answer_set_is_non_trivial() -> None:
    """The exam-course unread set must be a STRICT subset of all unread.

    This is what makes the task hard: a naive "mark every unread announcement
    as read" agent would touch the non-exam-course decoys and fail.
    """
    _sm, _sid, targets, state = _create_session()
    all_unread = [a for a in targets["unread_announcement_ids"].split(",") if a]
    exam_unread = [a for a in targets["unread_in_exam_courses_ids"].split(",") if a]
    non_exam_unread = [
        a for a in targets["unread_in_non_exam_courses_ids"].split(",") if a
    ]

    assert exam_unread, "expected at least one unread announcement in an exam course"
    assert non_exam_unread, (
        "expected unread DECOY announcements in non-exam courses — "
        "otherwise the task degenerates to 'mark all unread'"
    )
    # exam-unread is a strict subset of all-unread
    assert set(exam_unread) < set(all_unread)
    # The two partitions are disjoint and together cover all unread.
    assert set(exam_unread).isdisjoint(set(non_exam_unread))
    assert set(exam_unread) | set(non_exam_unread) == set(all_unread)
    assert int(targets["unread_in_exam_courses_count"]) == len(exam_unread)

    # Recompute the discriminator independently from raw state to prove the
    # builder's intersection is the genuine (unread ∧ exam-course) set.
    exam_courses = {c for c in targets["courses_with_upcoming_exams"].split(",") if c}
    recomputed = sorted(
        a.id
        for a in state.announcements
        if (not a.is_read) and a.course_id in exam_courses
    )
    assert recomputed == sorted(exam_unread)


def test_exams_straddle_the_14_day_boundary() -> None:
    """The hardened world MUST place exams just inside AND just outside the cutoff.

    This is the v2 difficulty lever: with exams at days 12-13 (in) and 15-16
    (out), an agent cannot use "the soonest exam(s)" — it must compute each
    course's exam-date-minus-now against the 14-day cutoff per course.
    """
    _sm, _sid, targets, state = _create_session()
    now = derive_anchor_time(42)
    cutoff = now + timedelta(days=14)

    exam_courses = {c for c in targets["courses_with_upcoming_exams"].split(",") if c}
    non_exam_courses = {
        c for c in targets["courses_without_upcoming_exams"].split(",") if c
    }
    assert len(exam_courses) >= 2
    assert len(non_exam_courses) >= 2

    # Earliest exam per course.
    earliest: dict[str, datetime] = {}
    for ev in state.calendar_events:
        if ev.event_type != "exam":
            continue
        prev = earliest.get(ev.course_id)
        if prev is None or ev.start_datetime < prev:
            earliest[ev.course_id] = ev.start_datetime

    # Every exam-course exam is in (now, cutoff]; every non-exam course's
    # earliest exam is strictly after the cutoff.
    for cid in exam_courses:
        assert now < earliest[cid] <= cutoff, (cid, earliest[cid].isoformat())
    for cid in non_exam_courses:
        assert earliest[cid] > cutoff, (cid, earliest[cid].isoformat())

    # There exists at least one near-boundary IN exam (>= day 12) and at least
    # one near-boundary OUT exam (<= day 17) — i.e. exams genuinely straddle.
    in_days = sorted((earliest[c] - now).days for c in exam_courses)
    out_days = sorted((earliest[c] - now).days for c in non_exam_courses)
    assert max(in_days) >= 12, in_days  # an in-window exam sits near the edge
    assert min(out_days) <= 17, out_days  # an out-window exam sits near the edge
    assert min(out_days) - max(in_days) <= 4, (in_days, out_days)



def test_correct_trajectory_via_endpoint_passes() -> None:
    """Driving the real mark-read endpoint over the exam-course unread set passes."""
    sm, sid, targets, state = _create_session()
    app.state.session_manager = sm
    client = TestClient(app)

    exam_unread = [a for a in targets["unread_in_exam_courses_ids"].split(",") if a]
    assert exam_unread

    for ann_id in exam_unread:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["announcement"]["is_read"] is True

    task = get_task("lms_study_around_exams")
    result = evaluate(
        task=task,
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # Richer than a 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_mark_all_unread_fails() -> None:
    """The most tempting wrong solution — mark EVERY unread announcement — fails.

    Marking the non-exam-course unread decoys trips the critical
    'did not mark unread announcements read in courses without an upcoming exam'
    invariant and the exact-count constraint.
    """
    sm, sid, targets, state = _create_session()
    app.state.session_manager = sm
    client = TestClient(app)

    # mark_all_read endpoint flips every unread announcement (exam + non-exam).
    resp = client.post(
        "/api/env/lms/announcements/mark_all_read",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    task = get_task("lms_study_around_exams")
    result = evaluate(
        task=task,
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"mark-all-unread should fail the discriminator but passed: {result}"
    )


def test_partial_miss_fails() -> None:
    """Marking only SOME of the exam-course unread set is a near-miss that fails."""
    sm, sid, targets, state = _create_session()
    app.state.session_manager = sm
    client = TestClient(app)

    exam_unread = [a for a in targets["unread_in_exam_courses_ids"].split(",") if a]
    assert len(exam_unread) >= 2, "need >=2 to drop one and still have a positive"

    # Mark all but the last exam-course unread announcement.
    for ann_id in exam_unread[:-1]:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text

    task = get_task("lms_study_around_exams")
    result = evaluate(
        task=task,
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"incomplete sweep should fail bijection saturation: {result}"
    )


def test_marking_near_boundary_decoy_course_fails() -> None:
    """Marking the day-15/16 (just-out-of-window) courses' unread fails.

    These near-boundary courses are the most tempting wrong target: their exam
    is only one or two days past the cutoff. Doing the full correct sweep AND
    additionally marking a near-boundary decoy course's unread announcements
    trips the critical near-boundary-decoy constraint.
    """
    sm, sid, targets, state = _create_session()
    app.state.session_manager = sm
    client = TestClient(app)

    exam_unread = [a for a in targets["unread_in_exam_courses_ids"].split(",") if a]
    near_boundary_cids = {
        targets["first_non_exam_course_id"],
        targets["second_non_exam_course_id"],
    }
    near_boundary_unread = [
        a.id
        for a in state.announcements
        if (not a.is_read) and a.course_id in near_boundary_cids
    ]
    assert near_boundary_unread, "expected unread decoys in the near-boundary courses"

    # Correct sweep PLUS the near-boundary decoy course unread (the trap).
    for ann_id in exam_unread + near_boundary_unread:
        resp = client.post(
            f"/api/env/lms/announcements/{ann_id}/read",
            json={"session_id": sid},
        )
        assert resp.status_code == 200, resp.text

    task = get_task("lms_study_around_exams")
    result = evaluate(
        task=task,
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False, (
        f"marking the near-boundary decoy courses should fail: {result}"
    )

