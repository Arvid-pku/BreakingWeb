"""Solvability proof for the v2-upgraded lms_submit_assignment task.

The clean/base task (re-tiered easy -> medium, then hardened for grounding)
now seeds 6 courses x 8 assignments (~48 rows) with three adjacent past-due
buckets the agent must discriminate per-course:
  * RECOVERABLE-MISSING: past due, not_submitted, inside the course's late
    window (days_late <= that course's max_late_days). Submit EXACTLY these.
  * UNRECOVERABLE: past due, not_submitted, beyond the window. Must NOT submit.
  * LATE-WITHIN-GRACE: already turned in late inside grace. Must NOT touch.
The recoverable set spans MULTIPLE courses, so the per-assignment catch-up file
name "catchup_<COURSE_CODE>.pdf" must be derived from each assignment's OWN
course, not the course currently being viewed.

The canonical_diff requires:
  * a bijection over target['recoverable_missing_assignment_ids'] that must
    SATURATE (submit every one, no more no fewer),
  * a per-assignment computed file_name (catchup_<own course code>.pdf),
  * attempt_count >= initial+1 and a fresh submitted_at,
  * a comprehensive preserve-ALL invariant freezing every other assignment
    (decoys / unrecoverable / grace) at critical severity,
  * critical constraints: no unrecoverable submitted, no grace assignment
    re-submitted (attempt_count unchanged), and every freshly-submitted row is
    in the recoverable set.

The correct solution is driven through the REAL backend submit endpoint
(POST /api/env/lms/assignments/{id}/submit) via TestClient on the shared app
SessionManager so the TestClient endpoints and the evaluator share state.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "lms_submit_assignment"


def _split(csv: str) -> list[str]:
    return [x for x in (csv or "").split(",") if x]


def _new_session(seed: int = 42):
    """Create a session on the shared app SessionManager and return (sid, targets, state)."""
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=seed)
    state = sm.get_state(sid)
    return sid, dict(targets), state


def _file_for(state, assignment_id: str) -> str:
    a = state.get_assignment(assignment_id)
    code = state.get_course(a.course_id).course_code
    return f"catchup_{code}.pdf"


# Several seeds so the proof is not pinned to one lucky draw of the recoverable
# set (each seed yields 3-5 recoverable assignments across 3 distinct courses).
_SEEDS = (42, 7, 100, 3, 999, 1, 2, 5)


def test_correct_trajectory_via_real_submit_endpoint_passes() -> None:
    """Submitting every recoverable-missing assignment (per-course file) passes on every seed."""
    client = TestClient(app)
    for seed in _SEEDS:
        sid, targets, state = _new_session(seed)
        recoverable = _split(targets["recoverable_missing_assignment_ids"])
        assert recoverable, f"seed {seed}: expected recoverable missing assignments"
        # The hardened base must spread the recoverable set across >1 course so
        # per-assignment file-name derivation is genuinely required.
        rec_courses = {state.get_assignment(a).course_id for a in recoverable}
        assert len(rec_courses) >= 2, f"seed {seed}: recoverable set should span multiple courses"

        try:
            for aid in recoverable:
                resp = client.post(
                    f"/api/env/lms/assignments/{aid}/submit",
                    json={"session_id": sid, "file_name": _file_for(state, aid)},
                )
                assert resp.status_code == 200, resp.text
                body = resp.json()["assignment"]
                assert body["submission_status"] in ("submitted", "late")

            state = app.state.session_manager.get_state(sid)
            result = evaluate(
                task=get_task(TASK_ID),
                server_state=state,
                targets=dict(targets),
                trajectory=[],
            )
            assert result.get("success") is True, f"seed {seed}: {result}"
            assert result.get("score", 0.0) >= 0.99, f"seed {seed}: score too low: {result}"
            # Richer than a single-check eval: bijection + sibling guards + constraints.
            assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2
        finally:
            app.state.session_manager.destroy(sid)


def test_submitting_unrecoverable_assignment_fails() -> None:
    """Submitting a past-window (unrecoverable) assignment trips the critical constraint."""
    client = TestClient(app)
    sid, targets, state = _new_session()
    recoverable = _split(targets["recoverable_missing_assignment_ids"])
    unrecoverable = _split(targets["unrecoverable_assignment_ids"])
    assert unrecoverable, "seed must produce at least one unrecoverable assignment"

    try:
        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": _file_for(state, aid)},
            )
            assert resp.status_code == 200, resp.text
        # ...but ALSO submit an unrecoverable one (the most-tempting wrong move).
        bad = unrecoverable[0]
        resp = client.post(
            f"/api/env/lms/assignments/{bad}/submit",
            json={"session_id": sid, "file_name": _file_for(state, bad)},
        )
        assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"unrecoverable submit should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_resubmitting_within_grace_late_assignment_fails() -> None:
    """Re-submitting an already-late (within-grace) assignment trips the grace constraint."""
    client = TestClient(app)
    sid, targets, state = _new_session()
    recoverable = _split(targets["recoverable_missing_assignment_ids"])
    grace = _split(targets["late_within_grace_ids"])
    assert grace, "seed must produce at least one within-grace late assignment"

    try:
        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": _file_for(state, aid)},
            )
            assert resp.status_code == 200, resp.text
        # Over-eager: re-submit an already-late assignment (bumps attempt_count).
        resp = client.post(
            f"/api/env/lms/assignments/{grace[0]}/submit",
            json={"session_id": sid, "file_name": _file_for(state, grace[0])},
        )
        assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"grace re-submit should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_cross_course_file_mislabel_fails() -> None:
    """Right assignment set but the catch-up file is labeled with the WRONG course code."""
    client = TestClient(app)
    sid, targets, state = _new_session()
    recoverable = _split(targets["recoverable_missing_assignment_ids"])
    assert len(recoverable) >= 2, "need >= 2 recoverable across courses to mislabel"

    try:
        # Use the FIRST recoverable assignment's course code for ALL submissions
        # (wrong for the ones that belong to other courses) — the classic
        # grounding error: label by the course you are viewing, not the
        # assignment's own course.
        wrong_file = _file_for(state, recoverable[0])
        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": wrong_file},
            )
            assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"cross-course mislabel should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_partial_submission_does_not_saturate_bijection_fails() -> None:
    """Submitting only some recoverable assignments fails to saturate the bijection."""
    client = TestClient(app)
    sid, targets, state = _new_session()
    recoverable = _split(targets["recoverable_missing_assignment_ids"])
    assert len(recoverable) >= 2, "hardened base should always seed >= 2 recoverable"

    try:
        # Submit all but the last recoverable assignment.
        for aid in recoverable[:-1]:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": _file_for(state, aid)},
            )
            assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"partial submission should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)


def test_wrong_file_name_fails() -> None:
    """Correct assignment set but wrong file-naming convention fails."""
    client = TestClient(app)
    sid, targets, state = _new_session()
    recoverable = _split(targets["recoverable_missing_assignment_ids"])

    try:
        for aid in recoverable:
            resp = client.post(
                f"/api/env/lms/assignments/{aid}/submit",
                json={"session_id": sid, "file_name": "submission.pdf"},
            )
            assert resp.status_code == 200, resp.text

        state = app.state.session_manager.get_state(sid)
        result = evaluate(
            task=get_task(TASK_ID),
            server_state=state,
            targets=dict(targets),
            trajectory=[],
        )
        assert result.get("success") is False, f"wrong file name should fail: {result}"
    finally:
        app.state.session_manager.destroy(sid)
