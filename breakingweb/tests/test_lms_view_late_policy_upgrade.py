"""Solvability proof for the upgraded ``lms_view_late_policy`` task.

The task asks the agent to read EACH course's late policy, re-derive the set of
recoverable overdue assignments (past due but within the course's max_late_days,
*inclusive* of the boundary), and submit every one of them with
``late_submit.pdf`` (bijection saturation) — while leaving the unrecoverable
overdue assignments (overdue by even one day MORE than max_late_days) and
already-submitted work untouched, and sending no messages.

The v2 upgrade makes the recoverability computation genuinely hard for a strong
model: ``boundary_missing_count`` seeds, in every course (whose policies vary
7 / 5 / 3 max late days), a BOUNDARY PAIR — one assignment overdue by EXACTLY
max_late_days (recoverable) and one overdue by max_late_days + 1 (unrecoverable).
An off-by-one in the per-course day count flips a recoverable into an
unrecoverable (trips the critical constraint) or vice-versa (drops a required
submission). The recoverable set is now multi-element (6-7 assignments), so the
bijection must saturate across courses.

The correct trajectory is driven through the REAL backend submit endpoint via
starlette TestClient so the proof also confirms the action is reachable past the
``/assignments/{id}/submit`` gates.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.lms import SessionCreateRequest, create_session
from breakingweb.backend.seeders.lms import derive_anchor_time
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

# Seeds that should exercise the boundary machinery deterministically.
_SEEDS = (42, 1, 7, 100, 5, 999)


def _split(csv: str) -> list[str]:
    return [x for x in (csv or "").split(",") if x]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _new_session(seed: int = 42) -> tuple[str, dict]:
    payload = create_session(
        SessionCreateRequest(task_id="lms_view_late_policy", seed=seed),
        session_manager=app.state.session_manager,
    )
    sid = payload["session_id"]
    state = app.state.session_manager.get(sid)
    return sid, dict(state.resolved_targets)


def test_seed_fixture_is_non_vacuous() -> None:
    """The recoverable set must be MULTI-element and the unrecoverable trap present."""
    sid, targets = _new_session()
    try:
        recoverable = _split(targets["recoverable_missing_assignment_ids"])
        unrecoverable = _split(targets["unrecoverable_assignment_ids"])
        # v2: the bijection must be non-trivial (was cardinality 1 in v1).
        assert len(recoverable) >= 3, f"recoverable set too small: {recoverable}"
        assert unrecoverable, "expected unrecoverable overdue decoys (the trap)"
        # The two sets must be disjoint or the task is contradictory.
        assert not (set(recoverable) & set(unrecoverable))
        assert targets["allows_late_submit"] == "true"
    finally:
        app.state.session_manager.destroy(sid)


def test_boundary_pairs_are_exact_and_correctly_classified() -> None:
    """Every recoverable is overdue by <= max_late_days; every unrecoverable by >.

    Crucially there must exist at least one recoverable assignment overdue by
    EXACTLY max_late_days (the inclusive boundary) and one unrecoverable overdue
    by EXACTLY max_late_days + 1 — the off-by-one trap. Verified across seeds so
    the difficulty lever is robust, not a single-seed accident.
    """
    for seed in _SEEDS:
        sid, targets = _new_session(seed)
        try:
            state = app.state.session_manager.get(sid)
            now = derive_anchor_time(seed)
            maxlate = {
                c.id: int(c.syllabus.late_policy.max_late_days) for c in state.courses
            }
            recoverable = _split(targets["recoverable_missing_assignment_ids"])
            unrecoverable = _split(targets["unrecoverable_assignment_ids"])
            assert len(recoverable) >= 3
            by_id = {a.id: a for a in state.assignments}

            rec_at_boundary = 0
            for aid in recoverable:
                a = by_id[aid]
                days_late = (now - a.due_at).days
                mx = maxlate[a.course_id]
                assert a.submission_status == "not_submitted", aid
                assert 0 <= days_late <= mx, (
                    f"seed {seed}: recoverable {aid} days_late={days_late} mx={mx}"
                )
                if days_late == mx:
                    rec_at_boundary += 1

            unr_just_over = 0
            for aid in unrecoverable:
                a = by_id[aid]
                days_late = (now - a.due_at).days
                mx = maxlate[a.course_id]
                assert days_late > mx, (
                    f"seed {seed}: unrecoverable {aid} days_late={days_late} mx={mx}"
                )
                if days_late == mx + 1:
                    unr_just_over += 1

            assert rec_at_boundary >= 1, (
                f"seed {seed}: no recoverable at exactly max_late_days boundary"
            )
            assert unr_just_over >= 1, (
                f"seed {seed}: no unrecoverable at exactly max_late_days+1 boundary"
            )
        finally:
            app.state.session_manager.destroy(sid)


def test_correct_trajectory_passes(client: TestClient) -> None:
    """Submitting every recoverable overdue assignment via the real endpoint passes."""
    sid, targets = _new_session()
    try:
        recoverable = _split(targets["recoverable_missing_assignment_ids"])
        assert len(recoverable) >= 3

        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": "late_submit.pdf"},
            )
            assert resp.status_code == 200, resp.text
            # These are overdue, so the backend marks them 'late'.
            assert resp.json()["assignment"]["submission_status"] in ("late", "submitted")

        state = app.state.session_manager.get(sid)
        result = evaluate(
            task=get_task("lms_view_late_policy"),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is True, f"result: {result}"
        assert result.get("score", 0.0) >= 0.99, f"score: {result.get('score')}"
        # Richer than a 2-check eval (bijection + invariants + constraints).
        assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2
    finally:
        app.state.session_manager.destroy(sid)


def test_submitting_boundary_plus_one_unrecoverable_fails(client: TestClient) -> None:
    """Submitting the just-over-boundary (max_late_days + 1) assignment is a critical miss.

    This is the off-by-one trap: an agent that treats 'within max late days' as
    a strict-less-than (or miscounts by a day) submits an unrecoverable boundary
    assignment and trips the critical constraint.
    """
    sid, targets = _new_session()
    try:
        state = app.state.session_manager.get(sid)
        now = derive_anchor_time(42)
        maxlate = {c.id: int(c.syllabus.late_policy.max_late_days) for c in state.courses}
        recoverable = _split(targets["recoverable_missing_assignment_ids"])
        unrecoverable = _split(targets["unrecoverable_assignment_ids"])
        by_id = {a.id: a for a in state.assignments}

        # Pick the unrecoverable assignment that is exactly max_late_days + 1 overdue.
        boundary_over = [
            aid for aid in unrecoverable
            if (now - by_id[aid].due_at).days == maxlate[by_id[aid].course_id] + 1
        ]
        assert boundary_over, "expected a +1 boundary unrecoverable assignment"

        # Do the right thing for the recoverable set...
        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": "late_submit.pdf"},
            )
            assert resp.status_code == 200, resp.text

        # ...but ALSO submit a forbidden just-over-boundary assignment.
        resp = client.post(
            f"/api/env/lms/assignments/{boundary_over[0]}/submit",
            json={"session_id": sid, "file_name": "late_submit.pdf"},
        )
        assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get(sid)
        result = evaluate(
            task=get_task("lms_view_late_policy"),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_submitting_unrecoverable_assignment_fails(client: TestClient) -> None:
    """Submitting any unrecoverable (past-max-late-days) assignment is a critical miss."""
    sid, targets = _new_session()
    try:
        recoverable = _split(targets["recoverable_missing_assignment_ids"])
        unrecoverable = _split(targets["unrecoverable_assignment_ids"])
        assert unrecoverable

        # Do the right thing for the recoverable set...
        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": "late_submit.pdf"},
            )
            assert resp.status_code == 200, resp.text

        # ...but ALSO submit a forbidden unrecoverable overdue assignment.
        bad = unrecoverable[0]
        resp = client.post(
            f"/api/env/lms/assignments/{bad}/submit",
            json={"session_id": sid, "file_name": "late_submit.pdf"},
        )
        assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get(sid)
        result = evaluate(
            task=get_task("lms_view_late_policy"),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_missing_a_recoverable_assignment_fails(client: TestClient) -> None:
    """Skipping even one recoverable assignment leaves the bijection unsaturated."""
    sid, targets = _new_session()
    try:
        recoverable = _split(targets["recoverable_missing_assignment_ids"])
        assert len(recoverable) >= 3
        # Submit all but the last recoverable assignment.
        for aid in recoverable[:-1]:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": "late_submit.pdf"},
            )
            assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get(sid)
        result = evaluate(
            task=get_task("lms_view_late_policy"),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result should fail (unsaturated): {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_sending_message_fails(client: TestClient) -> None:
    """Sending a message violates the high-severity no-message constraint."""
    sid, targets = _new_session()
    try:
        recoverable = _split(targets["recoverable_missing_assignment_ids"])
        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": "late_submit.pdf"},
            )
            assert resp.status_code == 200, resp.text

        resp = client.post(
            "/api/env/lms/messages/send",
            json={
                "session_id": sid,
                "to": "Advisor",
                "subject": "Late work",
                "body": "I have submitted my recoverable overdue work.",
            },
        )
        assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get(sid)
        result = evaluate(
            task=get_task("lms_view_late_policy"),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"result should fail (message sent): {result}"
    finally:
        app.state.session_manager.destroy(sid)

