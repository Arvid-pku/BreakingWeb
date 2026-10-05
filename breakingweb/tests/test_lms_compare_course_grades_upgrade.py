"""Solvability + near-miss proof for the upgraded lms_compare_course_grades task.

The task (hardened to `hard`) seeds five enrolled courses. The agent must
recompute the DISPLAYED (penalty-adjusted) weighted grades of exactly the two
NAMED courses (course_code_a / course_code_b). The named pair is calibrated to a
knife-edge (engine gap 3.41 > 3.00 → DROP) where a NAIVE raw-percentage recompute
that ignores the visible late_penalty_applied column lands BELOW 3.00 (→ no-op,
the wrong branch). The agent must therefore drop the enrollment of the lower-grade
named course while leaving every other enrollment (including a global-lowest DECOY
course not part of the named pair) untouched.

The correct solution is driven through the REAL backend drop endpoint
(`breakingweb.backend.routes.lms.drop_course`), which enforces the live guards
(enrollment must be 'enrolled', drop deadline not passed). Targets returned by
the seed builder are the intended answer, so a passing eval confirms the task is
achievable past the real backend gate.
"""

from __future__ import annotations

from decimal import Decimal

from breakingweb.backend.routes.lms import SessionScopedRequest, drop_course
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_compare_course_grades"


def _new_session() -> tuple[SessionManager, str, dict, object]:
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=42)
    state = sm.get_state(sid)
    return sm, sid, dict(targets), state


def test_seed_targets_are_internally_consistent() -> None:
    """The named-pair lower must be the lower of the two named courses' DISPLAYED
    weighted grades, the gap must exceed the 3-point tolerance, and the named-pair
    lower enrollment must belong to the named-pair lower course."""
    _sm, _sid, targets, state = _new_session()

    code_to_id = {c.course_code: c.id for c in state.courses}
    id_to_enr = {e.course_id: e.id for e in state.enrollments}
    a_id = code_to_id[targets["course_code_a"]]
    b_id = code_to_id[targets["course_code_b"]]
    score_a = state.weighted_score_for_course(a_id)
    score_b = state.weighted_score_for_course(b_id)
    assert score_a is not None and score_b is not None

    expected_lower = a_id if score_a < score_b else b_id
    assert targets["named_pair_lower_course_id"] == expected_lower
    assert targets["named_pair_lower_enrollment_id"] == id_to_enr[expected_lower]
    # Gap discriminator must be self-consistent.
    gap = abs(score_a - score_b)
    assert Decimal(targets["named_pair_gap"]) == gap.quantize(Decimal("0.01"))
    assert targets["named_pair_gap_above_3"] == ("true" if gap > Decimal("3") else "false")
    # For the calibrated seed the engine gap is just above the 3-point tolerance,
    # so the DROP branch is the canonical answer.
    assert targets["named_pair_gap_above_3"] == "true"


def test_knife_edge_displayed_gap_drops_but_naive_raw_recompute_would_not() -> None:
    """The verification trap (LMS-8): the DISPLAYED (penalty-adjusted) gap exceeds
    3.00 (→ DROP), but a NAIVE raw-percentage recompute that ignores the visible
    late-penalty column lands at or below 3.00 (→ no-op, the WRONG branch).

    This proves the base is genuinely on a knife-edge: an agent that does not read
    the late_penalty_applied column computes the wrong branch.
    """
    _sm, _sid, targets, state = _new_session()
    code_to_id = {c.course_code: c.id for c in state.courses}
    lo_id = targets["named_pair_lower_course_id"]
    hi_id = targets["named_pair_higher_course_id"]

    # Engine (displayed) gap — applies effective = score * (1 - late_penalty).
    engine_gap = abs(
        state.weighted_score_for_course(hi_id) - state.weighted_score_for_course(lo_id)
    )
    assert engine_gap > Decimal("3"), engine_gap

    # Naive raw-percentage recompute (ignores late_penalty_applied entirely).
    def _raw_weighted(course_id: str) -> Decimal:
        course = state.get_course(course_id)
        graded_weight = Decimal("0")
        weighted_sum = Decimal("0")
        for cat_name, policy in course.syllabus.grading_policy.items():
            cat_grades = [
                g for g in state.get_grades_for_course(course_id)
                if g.weight_category == cat_name and g.score is not None
            ]
            if not cat_grades:
                continue
            drop_n = policy.drop_lowest
            ratios = sorted(cat_grades, key=lambda g: g.score / g.points_possible)
            if len(cat_grades) <= drop_n:
                drop_n = max(0, len(cat_grades) - 1)
            keep = ratios[drop_n:]
            total = sum((g.score / g.points_possible) * Decimal("100") for g in keep)
            avg = (total / Decimal(len(keep))).quantize(Decimal("0.01"))
            graded_weight += policy.weight
            weighted_sum += avg * policy.weight
        return (weighted_sum / graded_weight).quantize(Decimal("0.01"))

    raw_gap = abs(_raw_weighted(hi_id) - _raw_weighted(lo_id))
    assert raw_gap <= Decimal("3"), raw_gap
    # The two recomputes land on OPPOSITE sides of the 3.00 boundary.
    assert engine_gap > Decimal("3") >= raw_gap


def test_naive_noop_due_to_raw_recompute_fails() -> None:
    """An agent that (wrongly) reads the gap as within tolerance and does NOTHING
    must fail — the displayed gap is above 3.00 so the no-op branch is wrong."""
    _sm, sid, targets, state = _new_session()
    eval_result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert eval_result.get("success") is False


def test_correct_drop_via_real_endpoint_passes() -> None:
    """Dropping exactly the named-pair lower enrollment through the real backend
    drop endpoint evaluates to a pass."""
    sm, sid, targets, state = _new_session()

    lower_course_id = targets["named_pair_lower_course_id"]
    # Drive the REAL backend mutation (enforces enrolled-status + drop-deadline guards).
    result = drop_course(
        course_id=lower_course_id,
        body=SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )
    assert result["dropped"] is True
    assert result["enrollment"]["id"] == targets["named_pair_lower_enrollment_id"]
    assert result["enrollment"]["status"] == "dropped"

    state = sm.get_state(sid)
    eval_result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert eval_result.get("success") is True, f"result: {eval_result}"
    assert eval_result.get("score", 0.0) >= 0.99


def test_dropping_the_higher_named_course_fails() -> None:
    """Dropping the HIGHER-grade named course (the wrong one of the pair) fails."""
    sm, sid, targets, state = _new_session()

    higher_course_id = targets["named_pair_higher_course_id"]
    drop_course(
        course_id=higher_course_id,
        body=SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )
    state = sm.get_state(sid)
    eval_result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert eval_result.get("success") is False


def test_doing_nothing_fails_when_gap_above_tolerance() -> None:
    """Because the named grades differ by > 3 points, the no-op (tie) branch must
    NOT pass: an agent that drops nothing fails."""
    _sm, sid, targets, state = _new_session()
    eval_result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert eval_result.get("success") is False


def test_dropping_a_decoy_course_in_addition_fails() -> None:
    """Over-acting — dropping the correct named-pair lower AND an extra
    (non-named) enrollment — trips the critical frozen-enrollment invariant."""
    sm, sid, targets, state = _new_session()

    lower_course_id = targets["named_pair_lower_course_id"]
    drop_course(
        course_id=lower_course_id,
        body=SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )
    # Find a different enrolled course (a decoy not in the named pair) and drop it too.
    state = sm.get_state(sid)
    extra = next(
        e for e in state.enrollments
        if e.status == "enrolled"
        and e.id != targets["named_pair_lower_enrollment_id"]
    )
    drop_course(
        course_id=extra.course_id,
        body=SessionScopedRequest(session_id=sid),
        session_manager=sm,
    )
    state = sm.get_state(sid)
    eval_result = evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert eval_result.get("success") is False
