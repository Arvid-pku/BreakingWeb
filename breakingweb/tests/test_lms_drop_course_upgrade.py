"""Solvability + difficulty proof for the upgraded lms_drop_course task (v2).

The task no longer names the course to drop. The agent must re-derive which
single enrolled course can no longer reach a B (a final weighted score >= 80%)
given the recorded grades and remaining assignments, then drop ONLY that
course's enrollment while leaving every other enrollment frozen.

v2 difficulty: the seed builder (near_threshold_b) engineers a genuine CLOSE
CALL — the impossible course's required remaining score is only just over 100%
(need ~104), and a near-threshold CONFUSER course is A-impossible but still
B-achievable (need ~94). The confuser's CURRENT displayed average is the lowest
of all courses, so eyeballing "the lowest grade" actively MISFIRES and points at
a course that must stay enrolled. Only the per-category weighted B-solve
distinguishes the two.

Everything is driven through the REAL backend mutation endpoint
(POST /api/env/lms/courses/{course_id}/drop) via starlette TestClient so the
proof also confirms the action is reachable past every gate (enrollment exists,
status == 'enrolled', now <= drop_deadline).
"""

from __future__ import annotations

from decimal import Decimal

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.lms import SessionCreateRequest, create_session
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _create_session(seed: int, variant_filename: str | None = None):
    """Create a session and return (client, sid, targets, state).

    Plain (clean) sessions go straight through the SessionManager. Variant
    sessions go through the LMS route's create_session so the degradation
    injections are applied and the initial snapshot is re-captured after
    injection (mirroring the real benchmark path)."""
    sm = app.state.session_manager
    client = TestClient(app)
    if variant_filename is None:
        sid, targets, _ = sm.create_session(
            env_id="lms", task_id="lms_drop_course", seed=seed,
        )
        state = sm.get_state(sid)
        return client, sid, dict(targets), state

    payload = create_session(
        SessionCreateRequest(
            task_id="lms_drop_course", seed=seed, variant_filename=variant_filename,
        ),
        session_manager=sm,
    )
    sid = payload["session_id"]
    state = sm.get(sid)
    return client, sid, dict(state.resolved_targets), state


def _enrollment_status(state, enrollment_id):
    return next(e.status for e in state.enrollments if e.id == enrollment_id)


def _need_to_reach_b(state, course_id) -> Decimal | None:
    """Re-derive the minimum remaining-work score needed to still finish with a
    B (80%), per the same per-category weighted method the seed builder uses.
    Returns None when there is no remaining work / no graded leverage."""
    course = state.get_course(course_id)
    gp = course.syllabus.grading_policy
    remaining = [a for a in state.assignments if a.course_id == course_id and a.score is None]
    tw = Decimal("0")
    fixed = Decimal("0")
    xcoeff = Decimal("0")
    for cat_name, cat in gp.items():
        w = Decimal(str(cat.weight))
        graded = [
            g for g in state.grades
            if g.course_id == course_id and g.weight_category == cat_name
            and g.score is not None and not g.is_dropped
        ]
        rem_in_cat = [r for r in remaining if r.weight_category == cat_name]
        n = len(graded) + len(rem_in_cat)
        if n == 0:
            continue
        ss = Decimal("0")
        for g in graded:
            eff = Decimal(str(g.score)) * (Decimal("1") - Decimal(str(g.late_penalty_applied)))
            ss += (eff / Decimal(str(g.points_possible))) * Decimal("100")
        tw += w
        fixed += w * ss / Decimal(str(n))
        xcoeff += w * Decimal(str(len(rem_in_cat))) / Decimal(str(n))
    if tw > 0 and xcoeff > 0:
        return (Decimal("80") * tw - fixed) / xcoeff
    return None


# ---------------------------------------------------------------------------
# Structure of the engineered close call (the difficulty itself)
# ---------------------------------------------------------------------------

def test_close_call_structure_is_genuine_not_an_outlier():
    """The impossible course is just-over-the-line, the confuser is just-under,
    and the confuser (not the impossible course) has the lowest current grade —
    so the task cannot be solved by eyeballing the lowest displayed average."""
    _client, _sid, targets, state = _create_session(seed=42)

    impossible_course_id = targets["impossible_course_id"]
    confuser_course_id = targets["confuser_course_id"]
    achievable = [c for c in targets["achievable_course_ids"].split(",") if c]

    assert impossible_course_id, "seed must expose exactly one impossible course"
    assert confuser_course_id, "seed must expose a near-threshold confuser"
    assert confuser_course_id != impossible_course_id
    # The confuser is B-achievable, so it is in the protected achievable set.
    assert confuser_course_id in achievable

    # Exactly one impossible course across the whole catalogue.
    impossible = [
        c.id for c in state.courses
        if (_need_to_reach_b(state, c.id) or Decimal("0")) > Decimal("100")
    ]
    assert impossible == [impossible_course_id], impossible

    imp_need = _need_to_reach_b(state, impossible_course_id)
    conf_need = _need_to_reach_b(state, confuser_course_id)
    # Just over the line — NOT a stark outlier requiring no math.
    assert imp_need is not None and Decimal("100") < imp_need <= Decimal("115"), imp_need
    # A-impossible but B-achievable — a genuine near-miss the agent must reject.
    assert conf_need is not None and Decimal("85") <= conf_need <= Decimal("100"), conf_need

    # Eyeballing the lowest CURRENT average misfires: the confuser is the lowest,
    # not the (correct) impossible course.
    currents = {
        c.id: state.weighted_score_for_course(c.id)
        for c in state.courses
        if state.weighted_score_for_course(c.id) is not None
    }
    lowest_cid = min(currents, key=lambda cid: currents[cid])
    assert lowest_cid == confuser_course_id, (lowest_cid, currents)
    assert lowest_cid != impossible_course_id
    # The impossible course's current is strictly above the confuser's, proving
    # the surface signal points the wrong way.
    assert currents[impossible_course_id] > currents[confuser_course_id]


# ---------------------------------------------------------------------------
# Solvability: the correct drop passes
# ---------------------------------------------------------------------------

def test_correct_drop_of_unrecoverable_course_passes():
    """Dropping exactly the unrecoverable course's enrollment via the real
    endpoint scores 1.0 / success on the harder base."""
    client, sid, targets, state = _create_session(seed=42)

    impossible_course_id = targets["impossible_course_id"]
    impossible_enrollment_id = targets["impossible_enrollment_id"]
    assert impossible_course_id and impossible_enrollment_id

    assert _enrollment_status(state, impossible_enrollment_id) == "enrolled"

    resp = client.post(
        f"/api/env/lms/courses/{impossible_course_id}/drop",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("dropped") is True

    assert _enrollment_status(state, impossible_enrollment_id) == "dropped"
    dropped = [e for e in state.enrollments if e.status == "dropped"]
    assert len(dropped) == 1

    task = get_task("lms_drop_course")
    result = evaluate(task=task, server_state=state, targets=targets, trajectory=[])
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


# ---------------------------------------------------------------------------
# Near-miss / wrong-target rejections
# ---------------------------------------------------------------------------

def test_dropping_the_near_threshold_confuser_fails():
    """Dropping the B-ACHIEVABLE confuser (the seductive near-miss whose current
    grade is the lowest) instead of the impossible course must fail."""
    client, sid, targets, state = _create_session(seed=42)

    impossible_course_id = targets["impossible_course_id"]
    confuser_course_id = targets["confuser_course_id"]
    assert confuser_course_id and confuser_course_id != impossible_course_id

    resp = client.post(
        f"/api/env/lms/courses/{confuser_course_id}/drop",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    task = get_task("lms_drop_course")
    result = evaluate(task=task, server_state=state, targets=targets, trajectory=[])
    # The required update did not match (wrong enrollment) AND the critical
    # "confuser stays enrolled" + "achievable stays enrolled" constraints fail.
    assert result.get("success") is False, f"result: {result}"


def test_dropping_wrong_course_fails():
    """Dropping any achievable course instead of the unrecoverable one fails."""
    client, sid, targets, state = _create_session(seed=42)

    impossible_course_id = targets["impossible_course_id"]
    achievable = [c for c in targets["achievable_course_ids"].split(",") if c]
    wrong_course_id = achievable[0]
    assert wrong_course_id and wrong_course_id != impossible_course_id

    resp = client.post(
        f"/api/env/lms/courses/{wrong_course_id}/drop",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text

    task = get_task("lms_drop_course")
    result = evaluate(task=task, server_state=state, targets=targets, trajectory=[])
    assert result.get("success") is False, f"result: {result}"


def test_over_dropping_both_courses_fails():
    """Dropping the correct course PLUS a sibling (extra side-effect) fails."""
    client, sid, targets, state = _create_session(seed=42)

    impossible_course_id = targets["impossible_course_id"]
    achievable = [c for c in targets["achievable_course_ids"].split(",") if c]
    extra_course_id = achievable[0]

    r1 = client.post(
        f"/api/env/lms/courses/{impossible_course_id}/drop",
        json={"session_id": sid},
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/env/lms/courses/{extra_course_id}/drop",
        json={"session_id": sid},
    )
    assert r2.status_code == 200, r2.text

    task = get_task("lms_drop_course")
    result = evaluate(task=task, server_state=state, targets=targets, trajectory=[])
    # Primary update satisfied, but the extra drop violates the critical
    # sibling-enrollment invariant and the critical "exactly one dropped"
    # constraint, so the task must fail.
    assert result.get("success") is False, f"result: {result}"


def test_collateral_message_fails():
    """Dropping the right course but also sending a message fails (critical)."""
    client, sid, targets, state = _create_session(seed=42)

    impossible_course_id = targets["impossible_course_id"]
    r1 = client.post(
        f"/api/env/lms/courses/{impossible_course_id}/drop",
        json={"session_id": sid},
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        "/api/env/lms/messages/send",
        json={"session_id": sid, "to": "Advisor", "subject": "FYI", "body": "Dropped a course."},
    )
    assert r2.status_code == 200, r2.text

    task = get_task("lms_drop_course")
    result = evaluate(task=task, server_state=state, targets=targets, trajectory=[])
    assert result.get("success") is False, f"result: {result}"


# ---------------------------------------------------------------------------
# Intervention variant: the misleading signals must NOT change the answer
# ---------------------------------------------------------------------------

def test_variant_correct_answer_unchanged_and_decoy_drop_fails():
    """Under the course_shadow_v1 degradation the canonical answer is unchanged:
    dropping the impossible course still passes, and following the variant's
    misleading "at risk" pull (dropping the still-B-achievable confuser) fails."""
    variant = "lms_drop_course__course_shadow_v1.yaml"

    # (a) Correct drop still passes despite the misleading decoys.
    client, sid, targets, state = _create_session(seed=42, variant_filename=variant)
    impossible_course_id = targets["impossible_course_id"]
    confuser_course_id = targets["confuser_course_id"]
    assert confuser_course_id and confuser_course_id != impossible_course_id

    resp = client.post(
        f"/api/env/lms/courses/{impossible_course_id}/drop",
        json={"session_id": sid},
    )
    assert resp.status_code == 200, resp.text
    task = get_task("lms_drop_course")
    result = evaluate(task=task, server_state=state, targets=targets, trajectory=[])
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"result: {result}"

    # (b) Following the variant's misleading "drop this one" signal (the confuser)
    # fails — proving the injection competes on the load-bearing predicate.
    client2, sid2, targets2, state2 = _create_session(seed=42, variant_filename=variant)
    resp2 = client2.post(
        f"/api/env/lms/courses/{targets2['confuser_course_id']}/drop",
        json={"session_id": sid2},
    )
    assert resp2.status_code == 200, resp2.text
    result2 = evaluate(task=task, server_state=state2, targets=targets2, trajectory=[])
    assert result2.get("success") is False, f"result: {result2}"
