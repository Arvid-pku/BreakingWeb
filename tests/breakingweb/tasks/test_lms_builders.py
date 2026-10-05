"""Tests for LMS seed builders -- determinism and correctness."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from breakingweb.backend.seeder import FakeDataGenerator
from breakingweb.tasks._seed_builders_lms import (
    LMS_BUILDER_REGISTRY,
    LMSSeedContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(seed: int = 42) -> LMSSeedContext:
    """Create an LMSSeedContext with deterministic seed."""
    rng = random.Random(seed)
    fake = FakeDataGenerator(seed)
    now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    base: dict = {
        "courses": [],
        "enrollments": [],
        "assignments": [],
        "modules": [],
        "discussions": [],
        "discussion_posts": [],
        "peer_reviews": [],
        "announcements": [],
        "grades": [],
        "calendar_events": [],
        "sent_messages": [],
    }
    return LMSSeedContext(seed=seed, rng=rng, fake=fake, now=now, base=base)


def _seed_through_grades(ctx: LMSSeedContext) -> None:
    """Run student_profile -> course_catalog -> enrollment_set -> assignment_battery -> grade_book."""
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 3})
    LMS_BUILDER_REGISTRY["enrollment_set"](ctx, {})
    LMS_BUILDER_REGISTRY["assignment_battery"](ctx, {"per_course_count": 6})
    LMS_BUILDER_REGISTRY["grade_book"](ctx, {})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_builders_registered():
    expected = {
        "student_profile", "course_catalog", "enrollment_set",
        "assignment_battery", "grade_book", "module_sequence",
        "discussion_forums", "announcements_feed", "calendar_events",
        "peer_review_assignments",
    }
    assert expected.issubset(set(LMS_BUILDER_REGISTRY.keys()))


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_student_profile_determinism():
    """Same seed produces identical output."""
    results = []
    for _ in range(2):
        rng = random.Random(42)
        fake = FakeDataGenerator(42)
        now = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        ctx = LMSSeedContext(seed=42, rng=rng, fake=fake, now=now, base={})
        out = LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
        results.append(out)
    assert results[0] == results[1]


def test_course_catalog_determinism():
    """Same seed produces identical courses."""
    results = []
    for _ in range(2):
        ctx = _make_ctx(99)
        LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
        out = LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 4})
        results.append(out)
    assert results[0] == results[1]


def test_full_pipeline_determinism():
    """Complete seed pipeline produces identical state."""
    snapshots = []
    for _ in range(2):
        ctx = _make_ctx(77)
        _seed_through_grades(ctx)
        snapshots.append(ctx.base)
    # Compare grade counts and course counts
    assert len(snapshots[0]["grades"]) == len(snapshots[1]["grades"])
    assert len(snapshots[0]["assignments"]) == len(snapshots[1]["assignments"])
    assert snapshots[0]["student"] == snapshots[1]["student"]


# ---------------------------------------------------------------------------
# Grading policy integrity
# ---------------------------------------------------------------------------

def test_course_catalog_weights_sum():
    """Every generated course's grading policy weights sum to 1.00."""
    ctx = _make_ctx(99)
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 4})
    for course_data in ctx.base.get("courses", []):
        policy = course_data["syllabus"]["grading_policy"]
        total = sum(Decimal(str(p["weight"])) for p in policy.values())
        assert total == Decimal("1.00"), f"Weights sum to {total} for {course_data['course_code']}"


def test_vary_late_policies():
    """When vary_late_policies=True, courses get different late policies."""
    ctx = _make_ctx(42)
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    out = LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 3, "vary_late_policies": True})
    assert out["strictest_late_policy_course_id"] != out["most_lenient_late_policy_course_id"]


# ---------------------------------------------------------------------------
# Builder output shapes
# ---------------------------------------------------------------------------

def test_student_profile_output_keys():
    ctx = _make_ctx()
    out = LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    assert "student_id" in out
    assert "student_name" in out
    assert "student_email" in out
    assert "gpa" in out
    assert "advisor_name" in out
    assert ctx.base["student"]["enrollment_status"] == "active"


def test_enrollment_set_creates_enrollments():
    ctx = _make_ctx()
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 3})
    out = LMS_BUILDER_REGISTRY["enrollment_set"](ctx, {})
    assert len(out["enrollment_ids"]) == 3
    assert len(ctx.base["enrollments"]) == 3


def test_assignment_battery_creates_assignments():
    ctx = _make_ctx()
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 2})
    LMS_BUILDER_REGISTRY["enrollment_set"](ctx, {})
    out = LMS_BUILDER_REGISTRY["assignment_battery"](ctx, {"per_course_count": 4})
    assert len(out["assignment_ids"]) == 8  # 2 courses * 4 each
    assert len(ctx.base["assignments"]) == 8


def test_grade_book_creates_grades():
    ctx = _make_ctx()
    _seed_through_grades(ctx)
    grades = ctx.base["grades"]
    assert len(grades) > 0
    # All grades should have valid scores
    for g in grades:
        assert g["score"] is not None
        assert Decimal(str(g["points_possible"])) > 0


def test_module_sequence_chain():
    ctx = _make_ctx()
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 1})
    out = LMS_BUILDER_REGISTRY["module_sequence"](
        ctx, {"course_id": ctx.base["courses"][0]["id"], "count": 5, "completed_count": 2},
    )
    assert len(out["module_ids"]) == 5
    assert out["next_available_module_id"] != ""
    # First module should have no prerequisites
    first_mod = ctx.base["modules"][0]
    assert first_mod["unlock_condition"] == "none"


def test_discussion_forums_creates_posts():
    ctx = _make_ctx()
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 1})
    out = LMS_BUILDER_REGISTRY["discussion_forums"](ctx, {"count": 2, "posts_per": 3})
    assert len(out["discussion_ids"]) == 2
    assert len(ctx.base["discussion_posts"]) > 0


def test_announcements_feed_unread():
    ctx = _make_ctx()
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 2})
    out = LMS_BUILDER_REGISTRY["announcements_feed"](ctx, {"count": 6, "unread_count": 2})
    assert len(out["unread_announcement_ids"]) == 2
    unread_set = set(out["unread_announcement_ids"])
    for ann in ctx.base["announcements"]:
        if ann["id"] in unread_set:
            assert ann["is_read"] is False


def test_calendar_events_created():
    ctx = _make_ctx()
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 2})
    LMS_BUILDER_REGISTRY["enrollment_set"](ctx, {})
    LMS_BUILDER_REGISTRY["assignment_battery"](ctx, {"per_course_count": 3})
    out = LMS_BUILDER_REGISTRY["calendar_events"](ctx, {"include_recurring": True, "weeks": 2})
    assert len(out["event_ids"]) > 0
    assert len(ctx.base["calendar_events"]) > 0


def test_peer_review_assignments():
    ctx = _make_ctx()
    LMS_BUILDER_REGISTRY["student_profile"](ctx, {})
    LMS_BUILDER_REGISTRY["course_catalog"](ctx, {"count": 1})
    LMS_BUILDER_REGISTRY["enrollment_set"](ctx, {})
    LMS_BUILDER_REGISTRY["assignment_battery"](ctx, {"per_course_count": 3})
    out = LMS_BUILDER_REGISTRY["peer_review_assignments"](ctx, {"count": 3})
    assert len(out["review_ids"]) == 3
    assert len(out["pending_review_ids"]) + len(out["completed_review_ids"]) == 3
