"""Solvability + adversarial proof for the upgraded ``lms_grade_with_curve``.

The upgraded task is a two-branch ``oneof`` gated on a seed-computed
discriminator the agent must re-derive (does +5 on the midterm cross a letter
band for the target course?).

* Branch 1 (curve RAISES the letter grade): acknowledge by marking EVERY
  unread announcement that belongs to the target course as read — a saturating
  bijection over the precomputed ``unread_target_announcement_ids`` set, with
  other-course unread announcements present as distractors that must NOT be
  touched (so a blunt ``mark_all_read`` fails).
* Branch 2 (curve does NOT change the letter grade): submit
  ``curve_appeal.pdf`` to the midterm assignment with tightened field
  predicates (exact file name, freshness, attempt increment).

All correct solutions are driven through the REAL LMS backend route handlers
(``mark_announcement_read`` / ``submit_assignment``) so the proof confirms the
intended answer is achievable past every server gate.

Canonical eval seed is 42 (validate stage 3 + variant integrity both use it),
which lands on Branch 1. Branch 2 is proven on seed 3, where the discriminator
is ``false`` and the target-course midterm is submittable.

The v2 upgrade calibrates the target course's graded midterm + supporting
grades so the *displayed* weighted score sits at a sharp near-90 boundary: a
+5-point midterm curve crosses the A/B letter line on Branch-1 seeds and stays
inside the same band on Branch-2 seeds. The discriminator the agent must
re-derive (weighted score with drop-lowest + re-normalization over graded
categories, then +5 on the midterm, then the A>=90/B>=80 band) is therefore a
genuine boundary computation rather than a far-from-edge flag.
"""

from __future__ import annotations

from breakingweb.backend.routes.lms import (
    SessionScopedRequest,
    SubmitAssignmentRequest,
    mark_all_announcements_read,
    mark_announcement_read,
    submit_assignment,
)
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task

TASK_ID = "lms_grade_with_curve"

# Seed 42 calibrates to Branch 1 (curve raises the letter); seed 3 calibrates
# to Branch 2 (curve holds the letter). Both are deterministic per the seeded
# near-boundary calibration in grade_book.
BRANCH1_SEED = 42
BRANCH2_SEED = 3


def _session(seed: int):
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="lms", task_id=TASK_ID, seed=seed)
    return sm, sid, dict(targets), sm.get_state(sid)


# ── Branch 1: curve raises the letter grade (canonical seed 42) ──────────────

def test_branch1_correct_marks_target_unread_passes():
    """Marking exactly the target-course unread announcements via the real
    endpoint passes with full score."""
    sm, sid, t, state = _session(BRANCH1_SEED)
    assert t["curve_changes_letter"] == "true", "seed must select Branch 1"
    target_ids = [a for a in t["unread_target_announcement_ids"].split(",") if a]
    assert len(target_ids) >= 2, "task should require marking a multi-element set"

    for aid in target_ids:
        mark_announcement_read(
            aid, SessionScopedRequest(session_id=sid), session_manager=sm
        )

    result = evaluate(
        task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[]
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99
    # canonical_diff coverage is richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_branch1_partial_marking_fails():
    """Marking only a strict subset of the target-course unread set fails the
    saturating bijection (cardinality)."""
    sm, sid, t, state = _session(BRANCH1_SEED)
    target_ids = [a for a in t["unread_target_announcement_ids"].split(",") if a]
    for aid in target_ids[:-1]:  # leave one unread
        mark_announcement_read(
            aid, SessionScopedRequest(session_id=sid), session_manager=sm
        )
    result = evaluate(
        task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[]
    )
    assert result.get("success") is False


def test_branch1_mark_all_read_fails_on_collateral():
    """Using 'mark all as read' touches unread announcements in OTHER courses,
    violating the critical collateral invariant/constraint."""
    sm, sid, t, state = _session(BRANCH1_SEED)
    mark_all_announcements_read(
        SessionScopedRequest(session_id=sid), session_manager=sm
    )
    result = evaluate(
        task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[]
    )
    assert result.get("success") is False


def test_branch1_wrong_branch_action_fails():
    """On a Branch-1 seed, taking the Branch-2 action (submitting the appeal)
    must fail — the discriminator genuinely gates the branch."""
    sm, sid, t, state = _session(BRANCH1_SEED)
    exam = t["exam_assignment_id"]
    a = state.get_assignment(exam)
    # The calibrated midterm is submittable (graded, attempt 1 of max 2), so the
    # submit endpoint succeeds — but it is the WRONG branch, so the eval must
    # still fail (the appeal update's where-clause requires
    # curve_changes_letter == 'false', and the stray submission also trips the
    # Branch-1 assignment invariant). Guard against the endpoint raising anyway.
    try:
        submit_assignment(
            exam,
            SubmitAssignmentRequest(session_id=sid, file_name="curve_appeal.pdf"),
            session_manager=sm,
        )
    except Exception:
        pass
    result = evaluate(
        task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[]
    )
    assert result.get("success") is False


# ── Branch 2: curve does not change the letter grade (seed 3) ────────────────

def test_branch2_correct_submits_appeal_passes():
    """Submitting curve_appeal.pdf to the midterm via the real endpoint passes
    with full score on a discriminator='false' seed."""
    sm, sid, t, state = _session(BRANCH2_SEED)
    assert t["curve_changes_letter"] == "false", "seed must select Branch 2"
    exam = t["exam_assignment_id"]
    submit_assignment(
        exam,
        SubmitAssignmentRequest(session_id=sid, file_name="curve_appeal.pdf"),
        session_manager=sm,
    )
    result = evaluate(
        task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[]
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99


def test_branch2_wrong_file_name_fails():
    """Submitting the wrong file name fails the exact-literal predicate."""
    sm, sid, t, state = _session(BRANCH2_SEED)
    exam = t["exam_assignment_id"]
    submit_assignment(
        exam,
        SubmitAssignmentRequest(session_id=sid, file_name="wrong_file.pdf"),
        session_manager=sm,
    )
    result = evaluate(
        task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[]
    )
    assert result.get("success") is False


def test_branch2_wrong_branch_action_fails():
    """On a Branch-2 seed, taking the Branch-1 action (marking announcements)
    must fail — the discriminator genuinely gates the branch."""
    sm, sid, t, state = _session(BRANCH2_SEED)
    for aid in (a for a in t["unread_target_announcement_ids"].split(",") if a):
        mark_announcement_read(
            aid, SessionScopedRequest(session_id=sid), session_manager=sm
        )
    result = evaluate(
        task=get_task(TASK_ID), server_state=state, targets=t, trajectory=[]
    )
    assert result.get("success") is False


# ── Discriminator is a genuine near-90 boundary computation ──────────────────

def _curved_letter_band(state, course_id):
    """Reproduce the agent's required computation against the LIVE grades the
    agent can read: displayed weighted score (pre-curve) and the score after
    adding +5 points to the midterm grade, mapped to the instruction's coarse
    5-band scale (A>=90, B>=80, C>=70, D>=60, F)."""
    from decimal import Decimal

    def band(s):
        s = Decimal(str(s))
        return "A" if s >= 90 else "B" if s >= 80 else "C" if s >= 70 else (
            "D" if s >= 60 else "F"
        )

    pre = state.weighted_score_for_course(course_id)
    mids = [
        g for g in state.grades
        if g.course_id == course_id and g.weight_category == "midterm" and not g.is_dropped
    ]
    assert mids, "calibrated target course must have an active midterm grade"
    mg = mids[0]
    orig = mg.score
    mg.score = min(Decimal(str(orig)) + Decimal("5"), Decimal(str(mg.points_possible)))
    curved = state.weighted_score_for_course(course_id)
    mg.score = orig
    return pre, curved, band(pre), band(curved)


def test_branch1_discriminator_is_near_boundary_crossing():
    """On a Branch-1 seed the pre-curve weighted score is a B (80-90) that the
    +5 midterm curve pushes to an A (>=90) — i.e. the flag is a true boundary
    crossing computed exactly the way the live grades page reports it, not a
    far-from-edge artifact."""
    sm, sid, t, state = _session(BRANCH1_SEED)
    cid = t["target_course_id"]
    pre, curved, pre_band, curved_band = _curved_letter_band(state, cid)
    assert t["curve_changes_letter"] == "true"
    assert pre_band == "B" and curved_band == "A", (pre, curved)
    assert curved >= 90 > pre  # genuine 90-line crossing


def test_branch2_discriminator_is_near_boundary_hold():
    """On a Branch-2 seed the pre-curve weighted score is a B that the +5 curve
    leaves still < 90 — a near miss of the boundary, so an agent that
    miscomputes (e.g. forgets drop-lowest or re-normalization, or trusts a
    stale/inflated number) flips to the wrong branch."""
    sm, sid, t, state = _session(BRANCH2_SEED)
    cid = t["target_course_id"]
    pre, curved, pre_band, curved_band = _curved_letter_band(state, cid)
    assert t["curve_changes_letter"] == "false"
    assert pre_band == "B" and curved_band == "B", (pre, curved)
    assert pre < 90 and curved < 90  # stays below the A line after the curve
