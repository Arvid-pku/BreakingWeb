from datetime import datetime, timezone
from decimal import Decimal

import pytest


def test_student_creation():
    from breakingweb.backend.models.lms import Student

    s = Student(
        id="student_1",
        name="Jordan Rivera",
        email="jordan.rivera@thornton.com",
        student_id="S-20240915",
        enrollment_status="active",
        gpa=Decimal("3.45"),
        advisor_id="adv_1",
        advisor_name="Dr. Sarah Chen",
    )
    assert s.name == "Jordan Rivera"
    assert s.enrollment_status == "active"
    assert s.gpa == Decimal("3.45")


def test_course_with_syllabus():
    from breakingweb.backend.models.lms import (
        CategoryPolicy, Course, LatePolicy, Syllabus,
    )

    syllabus = Syllabus(
        grading_policy={
            "homework": CategoryPolicy(weight=Decimal("0.30"), drop_lowest=2),
            "midterm": CategoryPolicy(weight=Decimal("0.25")),
            "final": CategoryPolicy(weight=Decimal("0.25")),
            "participation": CategoryPolicy(weight=Decimal("0.10")),
            "project": CategoryPolicy(weight=Decimal("0.10")),
        },
        late_policy=LatePolicy(
            penalty_per_day=Decimal("0.10"),
            max_late_days=5,
            grace_period_hours=2,
        ),
    )
    c = Course(
        id="course_1",
        course_code="CS101",
        title="Introduction to Computer Science",
        instructor_id="inst_1",
        instructor_name="Dr. Alan Turing",
        semester="Spring 2026",
        credits=3,
        syllabus=syllabus,
        drop_deadline=datetime(2026, 3, 15, tzinfo=timezone.utc),
        final_exam_date=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
    )
    assert c.course_code == "CS101"
    assert c.syllabus.grading_policy["homework"].drop_lowest == 2
    total_weight = sum(p.weight for p in c.syllabus.grading_policy.values())
    assert total_weight == Decimal("1.00")


def test_assignment_creation():
    from breakingweb.backend.models.lms import Assignment

    a = Assignment(
        id="assign_1",
        course_id="course_1",
        title="Problem Set 1",
        type="homework",
        due_at=datetime(2026, 2, 15, 23, 59, tzinfo=timezone.utc),
        points_possible=Decimal("100"),
        submission_status="graded",
        score=Decimal("85"),
        feedback="Good work on recursion problems.",
        weight_category="homework",
    )
    assert a.type == "homework"
    assert a.score == Decimal("85")
    assert a.submission_status == "graded"


def test_module_with_prerequisites():
    from breakingweb.backend.models.lms import ContentItem, Module

    m = Module(
        id="mod_3",
        course_id="course_1",
        title="Data Structures",
        position=3,
        unlock_condition="min_score",
        unlock_value=["mod_2:70"],
        status="locked",
        content_items=[
            ContentItem(title="Binary Trees Reading", type="reading"),
            ContentItem(title="BST Quiz", type="quiz", linked_assignment_id="assign_5"),
        ],
    )
    assert m.unlock_condition == "min_score"
    assert m.status == "locked"
    assert len(m.content_items) == 2


def test_grade_with_late_penalty():
    from breakingweb.backend.models.lms import Grade

    g = Grade(
        id="grade_1",
        enrollment_id="enr_1",
        course_id="course_1",
        assignment_id="assign_1",
        score=Decimal("85"),
        points_possible=Decimal("100"),
        weight_category="homework",
        is_dropped=False,
        late_penalty_applied=Decimal("0.10"),
    )
    assert g.late_penalty_applied == Decimal("0.10")
    assert not g.is_dropped


# ---------------------------------------------------------------------------
# Task 2: LMSState query methods + grade computation engine
# ---------------------------------------------------------------------------

def _build_test_state():
    """Build a minimal LMSState with 1 course, 5 assignments, grades, and 1 module chain."""
    from breakingweb.backend.models.lms import (
        Assignment, CalendarEvent, CategoryPolicy, Course, Enrollment,
        Grade, LatePolicy, LMSState, Module, Student, Syllabus,
    )

    student = Student(
        id="student_1", name="Jordan Rivera", email="jordan@thornton.com",
        student_id="S-20240915", enrollment_status="active",
        gpa=Decimal("3.45"), advisor_id="adv_1", advisor_name="Dr. Chen",
    )
    syllabus = Syllabus(
        grading_policy={
            "homework": CategoryPolicy(weight=Decimal("0.30"), drop_lowest=1),
            "midterm": CategoryPolicy(weight=Decimal("0.25")),
            "final": CategoryPolicy(weight=Decimal("0.25")),
            "participation": CategoryPolicy(weight=Decimal("0.10")),
            "project": CategoryPolicy(weight=Decimal("0.10")),
        },
        late_policy=LatePolicy(
            penalty_per_day=Decimal("0.10"), max_late_days=5, grace_period_hours=2,
        ),
    )
    course = Course(
        id="course_1", course_code="CS101", title="Intro to CS",
        instructor_id="inst_1", instructor_name="Dr. Turing",
        semester="Spring 2026", credits=3, syllabus=syllabus,
        drop_deadline=datetime(2026, 3, 15, tzinfo=timezone.utc),
        final_exam_date=datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc),
    )
    enrollment = Enrollment(
        id="enr_1", student_id="student_1", course_id="course_1",
        role="student", status="enrolled",
    )
    # 4 homeworks (scores: 90, 70, 85, 60), drop lowest (60)
    # After drop: avg = (90+70+85)/3 = 81.67
    assignments = [
        Assignment(id=f"assign_{i}", course_id="course_1", title=f"HW {i}",
                   type="homework", due_at=datetime(2026, 2, i*5, 23, 59, tzinfo=timezone.utc),
                   points_possible=Decimal("100"), submission_status="graded",
                   score=Decimal(str(s)), weight_category="homework")
        for i, s in [(1, 90), (2, 70), (3, 85), (4, 60)]
    ]
    # Midterm: 78/100
    assignments.append(Assignment(
        id="assign_5", course_id="course_1", title="Midterm",
        type="exam", due_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        points_possible=Decimal("100"), submission_status="graded",
        score=Decimal("78"), weight_category="midterm",
    ))
    grades = [
        Grade(id=f"grade_{i}", enrollment_id="enr_1", course_id="course_1",
              assignment_id=f"assign_{i}", score=Decimal(str(s)),
              points_possible=Decimal("100"), weight_category="homework")
        for i, s in [(1, 90), (2, 70), (3, 85), (4, 60)]
    ]
    grades.append(Grade(
        id="grade_5", enrollment_id="enr_1", course_id="course_1",
        assignment_id="assign_5", score=Decimal("78"),
        points_possible=Decimal("100"), weight_category="midterm",
    ))

    return LMSState(
        env_id="lms", task_id="test_task",
        student=student, courses=[course], enrollments=[enrollment],
        assignments=assignments, grades=grades,
    )


def test_get_course():
    state = _build_test_state()
    assert state.get_course("course_1") is not None
    assert state.get_course("nonexistent") is None


def test_get_course_by_code():
    state = _build_test_state()
    assert state.get_course_by_code("CS101").id == "course_1"
    assert state.get_course_by_code("MATH201") is None


def test_assignments_for_course():
    state = _build_test_state()
    assigns = state.assignments_for_course("course_1")
    assert len(assigns) == 5


def test_grades_for_course():
    state = _build_test_state()
    grades = state.get_grades_for_course("course_1")
    assert len(grades) == 5


def test_dropped_grades_for_category():
    state = _build_test_state()
    dropped = state.dropped_grades_for_category("course_1", "homework")
    assert len(dropped) == 1
    # The lowest homework score is 60 (assign_4)
    assert dropped[0].assignment_id == "assign_4"


def test_category_score_with_drops():
    state = _build_test_state()
    # homework: drop lowest 1 from [90, 70, 85, 60] -> avg(90, 70, 85) = 81.67
    score = state.category_score("course_1", "homework")
    assert score is not None
    assert abs(score - Decimal("81.67")) < Decimal("0.01")


def test_weighted_score_for_course():
    state = _build_test_state()
    # homework (30%): 81.67, midterm (25%): 78.00
    # Only graded categories contribute proportionally:
    # total_graded_weight = 0.30 + 0.25 = 0.55
    # weighted = (81.67 * 0.30 + 78.00 * 0.25) / 0.55
    score = state.weighted_score_for_course("course_1")
    assert score is not None
    # (24.501 + 19.5) / 0.55 = 80.0018...
    assert abs(score - Decimal("80.00")) < Decimal("0.1")


def test_late_penalty_calculation():
    from breakingweb.backend.models.lms import Assignment

    state = _build_test_state()
    # Assignment due 2026-02-05 23:59 UTC, grace period 2h
    # Submit at 2026-02-06 12:00 UTC -> ~12h after due, minus 2h grace = 10h => ceil(10/24) = 1 day late
    submit_time = datetime(2026, 2, 6, 12, 0, tzinfo=timezone.utc)
    penalty = state.late_penalty_for_assignment("assign_1", submit_time)
    assert penalty == Decimal("0.10")  # 1 day * 10%/day


def test_net_score_after_penalty():
    state = _build_test_state()
    submit_time = datetime(2026, 2, 6, 12, 0, tzinfo=timezone.utc)
    net = state.net_score_after_penalty("assign_1", Decimal("90"), submit_time)
    assert net == Decimal("81.0")  # 90 * (1 - 0.10)


def test_module_prerequisite_chain():
    from breakingweb.backend.models.lms import ContentItem, Module

    state = _build_test_state()
    # Add a 3-module chain: mod_1 (available) -> mod_2 (prereq mod_1) -> mod_3 (min_score mod_2:70)
    state.modules = [
        Module(id="mod_1", course_id="course_1", title="Intro", position=1,
               unlock_condition="none", status="completed",
               content_items=[ContentItem(title="Welcome", type="reading", completed=True)]),
        Module(id="mod_2", course_id="course_1", title="Basics", position=2,
               unlock_condition="prerequisite", unlock_value=["mod_1"],
               status="available"),
        Module(id="mod_3", course_id="course_1", title="Advanced", position=3,
               unlock_condition="min_score", unlock_value=["mod_2:70"],
               status="locked"),
    ]
    assert state.is_module_unlocked("mod_1")
    assert state.is_module_unlocked("mod_2")  # mod_1 is completed
    assert not state.is_module_unlocked("mod_3")  # mod_2 not completed yet
    assert state.next_available_module("course_1").id == "mod_2"
