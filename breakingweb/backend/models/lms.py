from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .base import BaseEntity, BaseEnvState, utc_now


# ---------------------------------------------------------------------------
# 1. Student
# ---------------------------------------------------------------------------

class Student(BaseEntity):
    name: str
    email: str
    student_id: str
    enrollment_status: Literal["active", "probation", "suspended"]
    gpa: Decimal
    advisor_id: str
    advisor_name: str


# ---------------------------------------------------------------------------
# 2. CategoryPolicy / LatePolicy / Syllabus
# ---------------------------------------------------------------------------

class CategoryPolicy(BaseModel):
    weight: Decimal
    drop_lowest: int = 0

    model_config = ConfigDict(extra="forbid")


class LatePolicy(BaseModel):
    penalty_per_day: Decimal
    max_late_days: int
    grace_period_hours: int

    model_config = ConfigDict(extra="forbid")


class Syllabus(BaseModel):
    grading_policy: dict[str, CategoryPolicy]
    late_policy: LatePolicy

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 3. Course
# ---------------------------------------------------------------------------

class Course(BaseEntity):
    course_code: str
    title: str
    instructor_id: str
    instructor_name: str
    semester: str
    credits: int
    syllabus: Syllabus
    drop_deadline: datetime
    final_exam_date: datetime


# ---------------------------------------------------------------------------
# 4. Enrollment
# ---------------------------------------------------------------------------

class Enrollment(BaseEntity):
    student_id: str
    course_id: str
    role: Literal["student", "ta"]
    status: Literal["enrolled", "waitlisted", "dropped", "completed"]
    final_grade: str | None = None
    final_score: Decimal | None = None


# ---------------------------------------------------------------------------
# 5. RubricItem
# ---------------------------------------------------------------------------

class RubricItem(BaseModel):
    criterion: str
    max_points: Decimal
    description: str

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 6. Assignment
# ---------------------------------------------------------------------------

class Assignment(BaseEntity):
    course_id: str
    title: str
    type: Literal["homework", "essay", "project", "quiz", "exam", "peer_review", "participation"]
    due_at: datetime
    points_possible: Decimal
    submission_status: Literal[
        "not_submitted", "submitted", "late", "graded", "resubmit_requested"
    ]
    score: Decimal | None = None
    feedback: str | None = None
    attempt_count: int = 0
    max_attempts: int = 1
    rubric: list[RubricItem] = Field(default_factory=list)
    weight_category: str
    submitted_at: datetime | None = None
    file_name: str | None = None


# ---------------------------------------------------------------------------
# 7. ContentItem / Module
# ---------------------------------------------------------------------------

class ContentItem(BaseModel):
    title: str
    type: Literal["reading", "video", "quiz", "assignment", "external_link"]
    completed: bool = False
    linked_assignment_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class Module(BaseEntity):
    course_id: str
    title: str
    position: int
    unlock_condition: Literal["none", "date", "prerequisite", "min_score"]
    unlock_value: list[str] = Field(default_factory=list)
    unlock_logic: Literal["all", "any"] = "all"
    status: Literal["locked", "available", "completed"]
    content_items: list[ContentItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 8. Discussion
# ---------------------------------------------------------------------------

class Discussion(BaseEntity):
    course_id: str
    module_id: str | None = None
    title: str
    prompt: str
    due_at: datetime
    min_posts: int
    min_replies: int
    points_possible: Decimal
    weight_category: str


# ---------------------------------------------------------------------------
# 9. DiscussionPost
# ---------------------------------------------------------------------------

class DiscussionPost(BaseEntity):
    discussion_id: str
    author_id: str
    author_name: str
    body: str
    parent_post_id: str | None = None
    timestamp: datetime
    updated_at: datetime | None = None
    is_anonymous: bool = False


# ---------------------------------------------------------------------------
# 10. PeerReview
# ---------------------------------------------------------------------------

class PeerReview(BaseEntity):
    assignment_id: str
    reviewer_student_id: str
    reviewee_student_id: str
    reviewee_name: str
    submission_title: str
    submission_body: str
    assignment_rubric: list[RubricItem] = Field(default_factory=list)
    rubric_scores: dict[str, int] = Field(default_factory=dict)
    comments: str = ""
    status: Literal["assigned", "in_progress", "submitted"]
    returned_for_revision: bool = False
    previous_rubric_scores: dict[str, int] = Field(default_factory=dict)
    previous_comments: str = ""
    due_at: datetime


# ---------------------------------------------------------------------------
# 11. Announcement
# ---------------------------------------------------------------------------

class Announcement(BaseEntity):
    course_id: str
    title: str
    body: str
    posted_at: datetime
    is_read: bool = False
    priority: Literal["normal", "urgent"]


# ---------------------------------------------------------------------------
# 12. Grade
# ---------------------------------------------------------------------------

class Grade(BaseEntity):
    enrollment_id: str
    course_id: str
    assignment_id: str
    score: Decimal | None = None
    points_possible: Decimal
    weight_category: str
    is_dropped: bool = False
    late_penalty_applied: Decimal = Decimal("0")


# ---------------------------------------------------------------------------
# 13. CalendarEvent
# ---------------------------------------------------------------------------

class CalendarEvent(BaseEntity):
    course_id: str
    title: str
    event_type: Literal["lecture", "office_hours", "exam", "deadline", "lab"]
    start_datetime: datetime
    end_datetime: datetime
    location: str = ""
    recurrence: Literal["none", "weekly"] = "none"
    recurrence_end_date: datetime | None = None


# ---------------------------------------------------------------------------
# 14. LMSState
# ---------------------------------------------------------------------------

class LMSState(BaseEnvState):
    DIFF_DIFFABLE_SINGLETONS: ClassVar[tuple[str, ...]] = ("student",)

    env_id: str = "lms"

    # Core entities
    student: Student
    courses: list[Course] = Field(default_factory=list)
    enrollments: list[Enrollment] = Field(default_factory=list)
    assignments: list[Assignment] = Field(default_factory=list)
    modules: list[Module] = Field(default_factory=list)
    discussions: list[Discussion] = Field(default_factory=list)
    discussion_posts: list[DiscussionPost] = Field(default_factory=list)
    peer_reviews: list[PeerReview] = Field(default_factory=list)
    announcements: list[Announcement] = Field(default_factory=list)
    grades: list[Grade] = Field(default_factory=list)
    calendar_events: list[CalendarEvent] = Field(default_factory=list)

    # Agent-created messages
    sent_messages: list[dict[str, Any]] = Field(default_factory=list)

    # Private attributes
    _initial_gpa: Decimal = PrivateAttr(default=Decimal("0"))
    _initial_enrollment_statuses: dict[str, str] = PrivateAttr(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        self._initial_gpa = self.student.gpa
        self._initial_enrollment_statuses = {
            e.id: e.status for e in self.enrollments
        }

    # -------------------------------------------------------------------
    # Entity lookup methods
    # -------------------------------------------------------------------

    def get_course(self, course_id: str) -> Course | None:
        return next((c for c in self.courses if c.id == course_id), None)

    def get_course_by_code(self, code: str) -> Course | None:
        return next((c for c in self.courses if c.course_code == code), None)

    def get_assignment(self, assignment_id: str) -> Assignment | None:
        return next((a for a in self.assignments if a.id == assignment_id), None)

    def get_enrollment(self, enrollment_id: str) -> Enrollment | None:
        return next((e for e in self.enrollments if e.id == enrollment_id), None)

    def get_enrollment_for_course(self, course_id: str) -> Enrollment | None:
        return next(
            (e for e in self.enrollments
             if e.course_id == course_id and e.student_id == self.student.id),
            None,
        )

    def get_module(self, module_id: str) -> Module | None:
        return next((m for m in self.modules if m.id == module_id), None)

    def get_discussion(self, discussion_id: str) -> Discussion | None:
        return next((d for d in self.discussions if d.id == discussion_id), None)

    def get_peer_review(self, review_id: str) -> PeerReview | None:
        return next((r for r in self.peer_reviews if r.id == review_id), None)

    def get_announcement(self, announcement_id: str) -> Announcement | None:
        return next((a for a in self.announcements if a.id == announcement_id), None)

    def get_grade(self, grade_id: str) -> Grade | None:
        return next((g for g in self.grades if g.id == grade_id), None)

    # -------------------------------------------------------------------
    # Filtered collection methods
    # -------------------------------------------------------------------

    def assignments_for_course(self, course_id: str) -> list[Assignment]:
        return [a for a in self.assignments if a.course_id == course_id]

    def modules_for_course(self, course_id: str) -> list[Module]:
        return sorted(
            [m for m in self.modules if m.course_id == course_id],
            key=lambda m: m.position,
        )

    def grades_for_enrollment(self, enrollment_id: str) -> list[Grade]:
        return [g for g in self.grades if g.enrollment_id == enrollment_id]

    def get_grades_for_course(self, course_id: str) -> list[Grade]:
        return [g for g in self.grades if g.course_id == course_id]

    def posts_for_discussion(self, discussion_id: str) -> list[DiscussionPost]:
        return sorted(
            [p for p in self.discussion_posts if p.discussion_id == discussion_id],
            key=lambda p: p.timestamp,
        )

    def announcements_for_course(self, course_id: str) -> list[Announcement]:
        return sorted(
            [a for a in self.announcements if a.course_id == course_id],
            key=lambda a: a.posted_at,
            reverse=True,
        )

    def unread_announcements(self) -> list[Announcement]:
        return [a for a in self.announcements if not a.is_read]

    # -------------------------------------------------------------------
    # Grade computation engine
    # -------------------------------------------------------------------

    def dropped_grades_for_category(
        self, course_id: str, category: str,
    ) -> list[Grade]:
        """Find the lowest N grades to drop in a category.

        Edge case: when graded_count <= drop_lowest, drop max(0, count - 1)
        to keep at least one grade.
        """
        course = self.get_course(course_id)
        if course is None:
            return []
        policy = course.syllabus.grading_policy.get(category)
        if policy is None or policy.drop_lowest == 0:
            return []

        course_grades = [
            g for g in self.get_grades_for_course(course_id)
            if g.weight_category == category and g.score is not None
        ]
        if not course_grades:
            return []

        drop_count = policy.drop_lowest
        if len(course_grades) <= drop_count:
            drop_count = max(0, len(course_grades) - 1)

        # Sort by score/points_possible ratio ascending (lowest first)
        sorted_grades = sorted(
            course_grades,
            key=lambda g: g.score / g.points_possible if g.points_possible else Decimal("0"),
        )
        return sorted_grades[:drop_count]

    @staticmethod
    def _letter_from_percentage(score: Decimal) -> str:
        """Map a weighted percentage to a conventional letter grade."""
        if score >= 93:
            return "A"
        if score >= 90:
            return "A-"
        if score >= 87:
            return "B+"
        if score >= 83:
            return "B"
        if score >= 80:
            return "B-"
        if score >= 77:
            return "C+"
        if score >= 73:
            return "C"
        if score >= 70:
            return "C-"
        if score >= 67:
            return "D+"
        if score >= 63:
            return "D"
        if score >= 60:
            return "D-"
        return "F"

    def assignment_curve_changes_letter(
        self,
        course_id: str,
        assignment_id: str,
        increment_points: str,
    ) -> bool:
        """Return whether adding `increment_points` to an assignment can raise letter grade.

        This is evaluated against live state without persisting changes.
        """
        assignment = self.get_assignment(assignment_id)
        if assignment is None or assignment.course_id != course_id:
            return False

        grade = next(
            (g for g in self.get_grades_for_course(course_id)
             if g.assignment_id == assignment_id and g.score is not None),
            None,
        )
        if grade is None or grade.is_dropped:
            return False

        current_total = self.weighted_score_for_course(course_id)
        if current_total is None:
            return False

        original_letter = self._letter_from_percentage(current_total)
        original_score = grade.score
        if original_score is None:
            return False

        bonus = Decimal(str(increment_points))
        boosted = min(original_score + bonus, grade.points_possible)

        grade.score = boosted
        try:
            boosted_total = self.weighted_score_for_course(course_id)
        finally:
            grade.score = original_score

        if boosted_total is None:
            return False
        return self._letter_from_percentage(boosted_total) != original_letter

    def category_score(
        self, course_id: str, category: str,
    ) -> Decimal | None:
        """Average score for a category after drops and late penalties.

        Returns the percentage score (0-100 scale) for the category,
        or None if no graded assignments exist in this category.
        """
        course_grades = [
            g for g in self.get_grades_for_course(course_id)
            if g.weight_category == category and g.score is not None
        ]
        if not course_grades:
            return None

        dropped = {g.id for g in self.dropped_grades_for_category(course_id, category)}

        active_grades = [g for g in course_grades if g.id not in dropped]
        if not active_grades:
            return None

        total = Decimal("0")
        for g in active_grades:
            effective = g.score * (Decimal("1") - g.late_penalty_applied)
            total += (effective / g.points_possible) * Decimal("100")

        return (total / Decimal(str(len(active_grades)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

    def weighted_score_for_course(self, course_id: str) -> Decimal | None:
        """Weighted average across all graded categories.

        Only categories with at least one graded assignment contribute.
        The weights are re-normalized proportionally to the graded weight sum.
        """
        course = self.get_course(course_id)
        if course is None:
            return None

        graded_weight = Decimal("0")
        weighted_sum = Decimal("0")

        for cat_name, policy in course.syllabus.grading_policy.items():
            cat_score = self.category_score(course_id, cat_name)
            if cat_score is not None:
                graded_weight += policy.weight
                weighted_sum += cat_score * policy.weight

        if graded_weight == Decimal("0"):
            return None

        return (weighted_sum / graded_weight).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

    def late_penalty_for_assignment(
        self, assignment_id: str, submit_time: datetime,
    ) -> Decimal:
        """Calculate late penalty fraction for a submission.

        Returns min(ceil((elapsed - grace) / 24h) * rate, 1.0), or 0 if within grace.
        """
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            return Decimal("0")

        course = self.get_course(assignment.course_id)
        if course is None:
            return Decimal("0")

        late_policy = course.syllabus.late_policy
        elapsed = submit_time - assignment.due_at
        elapsed_hours = Decimal(str(elapsed.total_seconds())) / Decimal("3600")

        grace = Decimal(str(late_policy.grace_period_hours))
        if elapsed_hours <= grace:
            return Decimal("0")

        hours_past_grace = elapsed_hours - grace
        days_late = math.ceil(float(hours_past_grace) / 24)

        if days_late > late_policy.max_late_days:
            return Decimal("1")

        penalty = Decimal(str(days_late)) * late_policy.penalty_per_day
        return min(penalty, Decimal("1"))

    def net_score_after_penalty(
        self, assignment_id: str, raw_score: Decimal, submit_time: datetime,
    ) -> Decimal:
        """Apply late penalty to a raw score."""
        penalty = self.late_penalty_for_assignment(assignment_id, submit_time)
        return (raw_score * (Decimal("1") - penalty)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP,
        )

    def is_assignment_still_worth_submitting(
        self, assignment_id: str, estimated_score: Decimal, submit_time: datetime,
    ) -> bool:
        """Check if a late submission would still yield a positive score."""
        net = self.net_score_after_penalty(assignment_id, estimated_score, submit_time)
        return net > Decimal("0")

    def minimum_score_for_grade(
        self,
        course_id: str,
        target_letter: str,
        remaining_assignments: list[dict[str, Any]],
    ) -> Decimal | None:
        """Solve for the minimum average score needed on remaining assignments
        to achieve a target letter grade.

        target_letter maps to a minimum percentage threshold:
          A: 90, B: 80, C: 70, D: 60, F: 0

        remaining_assignments is a list of dicts with:
          - weight_category: str
          - points_possible: Decimal

        Returns the minimum score percentage (0-100) needed on all remaining
        assignments equally, or None if impossible.
        """
        thresholds = {
            "A": Decimal("90"), "B": Decimal("80"),
            "C": Decimal("70"), "D": Decimal("60"), "F": Decimal("0"),
        }
        target = thresholds.get(target_letter)
        if target is None:
            return None

        course = self.get_course(course_id)
        if course is None:
            return None

        # Current weighted contributions: for each category, gather existing
        # category scores and remaining capacity
        policy = course.syllabus.grading_policy

        # Build category -> (current_score_sum, current_count, remaining_count)
        cat_info: dict[str, dict[str, Any]] = {}
        for cat_name in policy:
            existing = [
                g for g in self.get_grades_for_course(course_id)
                if g.weight_category == cat_name and g.score is not None
            ]
            dropped = {g.id for g in self.dropped_grades_for_category(course_id, cat_name)}
            active = [g for g in existing if g.id not in dropped]

            score_sum = Decimal("0")
            for g in active:
                effective = g.score * (Decimal("1") - g.late_penalty_applied)
                score_sum += (effective / g.points_possible) * Decimal("100")

            remaining = [
                r for r in remaining_assignments if r["weight_category"] == cat_name
            ]

            cat_info[cat_name] = {
                "current_sum": score_sum,
                "current_count": len(active),
                "remaining_count": len(remaining),
            }

        # Solve: target = sum(cat_weight * cat_avg) for all categories
        # where cat_avg = (current_sum + remaining_count * x) / (current_count + remaining_count)
        # and x is what we want to find (the score percentage on each remaining assignment)
        #
        # target = sum(w_i * (S_i + R_i * x) / (N_i + R_i)) / sum(w_i for graded categories)
        # But we normalize proportionally over all categories that have any grades or remaining.

        total_weight = Decimal("0")
        fixed_part = Decimal("0")
        x_coefficient = Decimal("0")

        for cat_name, info in cat_info.items():
            w = policy[cat_name].weight
            n = info["current_count"] + info["remaining_count"]
            if n == 0:
                continue
            total_weight += w
            denom = Decimal(str(n))
            fixed_part += w * info["current_sum"] / denom
            x_coefficient += w * Decimal(str(info["remaining_count"])) / denom

        if total_weight == Decimal("0") or x_coefficient == Decimal("0"):
            return None

        # target = (fixed_part + x_coefficient * x) / total_weight
        # x = (target * total_weight - fixed_part) / x_coefficient
        needed = (target * total_weight - fixed_part) / x_coefficient

        if needed > Decimal("100"):
            return None  # impossible
        if needed < Decimal("0"):
            needed = Decimal("0")

        return needed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # -------------------------------------------------------------------
    # Module prerequisite methods
    # -------------------------------------------------------------------

    def is_module_unlocked(self, module_id: str) -> bool:
        """Evaluate whether a module's unlock condition is satisfied."""
        module = self.get_module(module_id)
        if module is None:
            return False

        if module.status == "completed":
            return True

        if module.unlock_condition == "none":
            return True

        if module.unlock_condition == "date":
            if not module.unlock_value:
                return True
            unlock_dt = datetime.fromisoformat(module.unlock_value[0])
            return datetime.now(timezone.utc) >= unlock_dt

        if module.unlock_condition == "prerequisite":
            checks = [
                self._is_module_completed(prereq_id)
                for prereq_id in module.unlock_value
            ]
            if module.unlock_logic == "all":
                return all(checks) if checks else True
            return any(checks) if checks else True

        if module.unlock_condition == "min_score":
            checks = []
            for spec in module.unlock_value:
                parts = spec.split(":")
                prereq_id = parts[0]
                min_score = Decimal(parts[1]) if len(parts) > 1 else Decimal("0")
                prereq = self.get_module(prereq_id)
                if prereq is None or prereq.status != "completed":
                    checks.append(False)
                    continue
                # Check if any category score for the module's course meets the minimum
                # For min_score, we check that the prerequisite module is completed
                # and (optionally) a score threshold is met on the module's linked assignments
                checks.append(self._module_score_meets(prereq_id, min_score))
            if module.unlock_logic == "all":
                return all(checks) if checks else True
            return any(checks) if checks else True

        return False

    def _is_module_completed(self, module_id: str) -> bool:
        """Check if a module has status 'completed'."""
        m = self.get_module(module_id)
        return m is not None and m.status == "completed"

    def _module_score_meets(self, module_id: str, min_score: Decimal) -> bool:
        """Check if a module's linked assignment scores meet the minimum threshold."""
        module = self.get_module(module_id)
        if module is None:
            return False
        # Find linked assignments from content items
        linked_ids = [
            item.linked_assignment_id
            for item in module.content_items
            if item.linked_assignment_id is not None
        ]
        if not linked_ids:
            # No linked assignments -- completion alone satisfies
            return module.status == "completed"
        for aid in linked_ids:
            assignment = self.get_assignment(aid)
            if assignment is None or assignment.score is None:
                return False
            pct = (assignment.score / assignment.points_possible) * Decimal("100")
            if pct < min_score:
                return False
        return True

    def module_chain(self, course_id: str) -> list[Module]:
        """Topological sort of modules by prerequisites for a course."""
        modules = self.modules_for_course(course_id)
        module_map = {m.id: m for m in modules}

        # Build adjacency: prereq -> depends_on
        visited: set[str] = set()
        result: list[Module] = []

        def visit(mid: str) -> None:
            if mid in visited or mid not in module_map:
                return
            visited.add(mid)
            m = module_map[mid]
            if m.unlock_condition in ("prerequisite", "min_score"):
                for val in m.unlock_value:
                    prereq_id = val.split(":")[0]
                    visit(prereq_id)
            result.append(m)

        for m in modules:
            visit(m.id)
        return result

    def next_available_module(self, course_id: str) -> Module | None:
        """First module in the chain that is available (unlocked) and not completed."""
        for m in self.module_chain(course_id):
            if m.status != "completed" and self.is_module_unlocked(m.id):
                return m
        return None

    # -------------------------------------------------------------------
    # Discussion participation
    # -------------------------------------------------------------------

    def student_post_count(self, discussion_id: str) -> int:
        """Count top-level posts by the current student in a discussion."""
        return sum(
            1 for p in self.discussion_posts
            if p.discussion_id == discussion_id
            and p.author_id == self.student.id
            and p.parent_post_id is None
        )

    def student_reply_count(self, discussion_id: str) -> int:
        """Count replies by the current student in a discussion."""
        return sum(
            1 for p in self.discussion_posts
            if p.discussion_id == discussion_id
            and p.author_id == self.student.id
            and p.parent_post_id is not None
        )

    def meets_discussion_requirements(self, discussion_id: str) -> bool:
        """Check if the student meets the minimum post/reply requirements."""
        discussion = self.get_discussion(discussion_id)
        if discussion is None:
            return False
        posts = self.student_post_count(discussion_id)
        replies = self.student_reply_count(discussion_id)
        return posts >= discussion.min_posts and replies >= discussion.min_replies

    # -------------------------------------------------------------------
    # Cross-course summaries
    # -------------------------------------------------------------------

    def upcoming_deadlines(self, within_days: int = 7) -> list[Assignment]:
        """Return assignments due within the given number of days from now."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=within_days)
        upcoming = [
            a for a in self.assignments
            if now <= a.due_at <= cutoff
            and a.submission_status in ("not_submitted", "submitted", "resubmit_requested")
        ]
        return sorted(upcoming, key=lambda a: a.due_at)

    def missing_assignments(self) -> list[Assignment]:
        """Return assignments that are past due and not submitted."""
        now = datetime.now(timezone.utc)
        return [
            a for a in self.assignments
            if a.due_at < now and a.submission_status == "not_submitted"
        ]

    def gpa_after_grades(
        self, hypothetical_grades: dict[str, str],
    ) -> Decimal:
        """Compute hypothetical GPA given letter grades for courses.

        hypothetical_grades: {course_id: letter_grade}
        Letter grades map to GPA points: A=4.0, A-=3.7, B+=3.3, B=3.0,
        B-=2.7, C+=2.3, C=2.0, C-=1.7, D+=1.3, D=1.0, D-=0.7, F=0.0
        """
        gpa_scale: dict[str, Decimal] = {
            "A": Decimal("4.0"), "A-": Decimal("3.7"),
            "B+": Decimal("3.3"), "B": Decimal("3.0"), "B-": Decimal("2.7"),
            "C+": Decimal("2.3"), "C": Decimal("2.0"), "C-": Decimal("1.7"),
            "D+": Decimal("1.3"), "D": Decimal("1.0"), "D-": Decimal("0.7"),
            "F": Decimal("0.0"),
        }

        total_points = Decimal("0")
        total_credits = Decimal("0")

        for course_id, letter in hypothetical_grades.items():
            course = self.get_course(course_id)
            if course is None:
                continue
            points = gpa_scale.get(letter)
            if points is None:
                continue
            credits = Decimal(str(course.credits))
            total_points += points * credits
            total_credits += credits

        if total_credits == Decimal("0"):
            return self.student.gpa

        return (total_points / total_credits).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )

    # -------------------------------------------------------------------
    # State snapshot
    # -------------------------------------------------------------------

    def state_snapshot(self) -> dict[str, Any]:
        """Capture all mutable state dimensions for collateral-damage detection."""
        grade_snap: dict[str, dict[str, Any]] = {}
        for g in self.grades:
            grade_snap[g.id] = {
                "score": str(g.score) if g.score is not None else None,
                "is_dropped": g.is_dropped,
                "late_penalty_applied": str(g.late_penalty_applied),
            }

        enrollment_snap: dict[str, dict[str, Any]] = {}
        for e in self.enrollments:
            enrollment_snap[e.id] = {
                "status": e.status,
                "final_grade": e.final_grade,
                "final_score": str(e.final_score) if e.final_score is not None else None,
            }

        assignment_snap: dict[str, dict[str, Any]] = {}
        for a in self.assignments:
            assignment_snap[a.id] = {
                "submission_status": a.submission_status,
                "score": str(a.score) if a.score is not None else None,
            }

        module_snap: dict[str, dict[str, Any]] = {}
        for m in self.modules:
            module_snap[m.id] = {
                "status": m.status,
                "content_completed": [
                    item.completed for item in m.content_items
                ],
            }

        announcement_snap: dict[str, dict[str, Any]] = {}
        for ann in self.announcements:
            announcement_snap[ann.id] = {
                "is_read": ann.is_read,
            }

        return {
            "student_gpa": str(self.student.gpa),
            "student_enrollment_status": self.student.enrollment_status,
            "grades": grade_snap,
            "enrollments": enrollment_snap,
            "assignments": assignment_snap,
            "modules": module_snap,
            "announcements": announcement_snap,
            "sent_message_count": len(self.sent_messages),
        }
