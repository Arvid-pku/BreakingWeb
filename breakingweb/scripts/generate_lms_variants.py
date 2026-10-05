from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from breakingweb.tasks._registry import env_tasks


VARIANTS_DIR = Path(__file__).resolve().parents[1] / "injector" / "variants"

PRIMITIVE_QUOTAS: dict[str, int] = {
    "grounding": 7,
    "backtracking": 3,
    "patience": 8,
    "exploration": 8,
    "planning": 18,
    "verification": 18,
    "state_tracking": 8,
}

PRIMITIVE_BASE_PRIORITY = {
    "backtracking": 70,
    "grounding": 60,
    "patience": 50,
    "exploration": 45,
    "planning": 40,
    "verification": 35,
    "state_tracking": 5,
}

SECONDARY_PRIMITIVE_QUOTAS: dict[str, int] = {
    "grounding": 8,
    "backtracking": 6,
    "patience": 12,
    "exploration": 12,
    "planning": 16,
    "verification": 16,
    "state_tracking": 10,
}


def singular_target_key(task: Any, preferred: list[str], *, token: str | None = None, allow_generic: bool = True) -> str | None:
    targets = set((task.seed.targets or {}).keys()) if task.seed else set()
    for key in preferred:
        if key in targets:
            return key
    for key in sorted(targets):
        if token and token not in key:
            continue
        if key.endswith("_id") and not key.endswith("_ids"):
            return key
    if allow_generic:
        for key in sorted(targets):
            if key.endswith("_id") and not key.endswith("_ids"):
                return key
    return None


def family_for_task(task: Any) -> str:
    target_keys = set((task.seed.targets or {}).keys()) if task.seed else set()
    task_id = task.task_id
    start_path = task.start_path or "/"

    if start_path == "/peer-reviews" or "peer_review" in task_id or any(
        key in target_keys for key in ("pending_review_ids", "completed_review_ids", "target_review_id")
    ):
        return "peer_review"
    if "discussion" in task_id or any(
        key in target_keys for key in ("target_discussion_id", "discussion_title", "target_discussion_title")
    ):
        return "discussion"
    if "module" in task_id or "prereq" in task_id or any(
        key in target_keys for key in ("next_available_module_id", "first_locked_module_id", "module_ids", "module_title")
    ):
        return "module"
    if start_path == "/calendar" or any(
        token in task_id for token in ("exam", "deadline", "study", "schedule")
    ):
        return "calendar"
    if "announcement" in task_id or any(
        key in target_keys for key in ("latest_announcement_id", "urgent_announcement_id", "unread_announcement_ids")
    ):
        return "announcement"
    if any(token in task_id for token in ("drop_course", "waitlist", "course_selection", "course_load")):
        return "course"
    if any(
        key in target_keys
        for key in (
            "target_assignment_id",
            "assignment_title",
            "feedback_assignment_id",
            "missing_assignment_ids",
            "priority_order_ids",
            "resubmit_assignment_id",
        )
    ) or any(token in task_id for token in ("submit", "resubmit", "assignment", "rubric", "late", "portfolio")):
        return "assignment"
    return "grade"


def primitive_preferences(task: Any, family: str) -> list[str]:
    primaries = list(task.primary_primitives or [])
    task_id = task.task_id
    prefs: list[str] = []

    def add(name: str) -> None:
        if name in primaries and name not in prefs:
            prefs.append(name)

    if "backtracking" in primaries:
        add("backtracking")

    if "grounding" in primaries and (
        len(primaries) == 1 or family in {"assignment", "announcement", "discussion", "course"}
    ):
        add("grounding")

    if "patience" in primaries and (
        family in {"peer_review", "discussion", "module"}
        or any(token in task_id for token in ("audit", "sprint", "marathon", "cycle", "mega"))
    ):
        add("patience")

    if "exploration" in primaries and (
        family in {"announcement", "calendar"}
        or any(token in task_id for token in ("find", "selection", "dispute", "conflict", "missing"))
    ):
        add("exploration")

    if "planning" in primaries and (
        family in {"module", "calendar", "course"}
        or task.start_path == "/dashboard"
        or any(token in task_id for token in ("plan", "priority", "recovery", "optimization", "threshold", "what_if"))
    ):
        add("planning")

    if "verification" in primaries and (
        family in {"announcement", "grade", "peer_review"}
        or any(token in task_id for token in ("check", "compare", "grade", "audit", "review", "verify", "appeal", "maintenance"))
    ):
        add("verification")

    if "state_tracking" in primaries:
        add("state_tracking")

    for primitive in primaries:
        add(primitive)
    return prefs


def choose_target_primitive(tasks: list[Any]) -> dict[str, str]:
    remaining = dict(PRIMITIVE_QUOTAS)
    assignments: dict[str, str] = {}

    def task_sort_key(task: Any) -> tuple[int, int, str]:
        prefs = primitive_preferences(task, family_for_task(task))
        return (len(task.primary_primitives or []), len(prefs), task.task_id)

    for task in sorted(tasks, key=task_sort_key):
        family = family_for_task(task)
        prefs = primitive_preferences(task, family)
        best = None
        best_score = None
        for primitive in task.primary_primitives or []:
            remaining_quota = remaining.get(primitive, 0)
            pref_bonus = max(0, 20 - 3 * prefs.index(primitive)) if primitive in prefs else 0
            score = (
                1 if remaining_quota > 0 else 0,
                remaining_quota,
                pref_bonus + PRIMITIVE_BASE_PRIORITY.get(primitive, 0),
                -len(task.primary_primitives or []),
            )
            if best is None or score > best_score:
                best = primitive
                best_score = score
        assert best is not None, f"task {task.task_id} has no primary primitives"
        assignments[task.task_id] = best
        if remaining.get(best, 0) > 0:
            remaining[best] -= 1
    return assignments


def choose_secondary_primitive(tasks: list[Any], primary_map: dict[str, str]) -> dict[str, str]:
    remaining = dict(SECONDARY_PRIMITIVE_QUOTAS)
    assignments: dict[str, str] = {}

    def task_sort_key(task: Any) -> tuple[int, int, str]:
        prefs = primitive_preferences(task, family_for_task(task))
        return (len(task.primary_primitives or []), len(prefs), task.task_id)

    for task in sorted(tasks, key=task_sort_key):
        family = family_for_task(task)
        prefs = primitive_preferences(task, family)
        primary = primary_map[task.task_id]
        candidates = [primitive for primitive in prefs if primitive != primary]
        if not candidates:
            candidates = [primary]
        best = None
        best_score = None
        for primitive in candidates:
            remaining_quota = remaining.get(primitive, 0)
            pref_bonus = max(0, 20 - 3 * prefs.index(primitive)) if primitive in prefs else 0
            score = (
                1 if primitive != primary else 0,
                1 if remaining_quota > 0 else 0,
                remaining_quota,
                pref_bonus + PRIMITIVE_BASE_PRIORITY.get(primitive, 0),
            )
            if best is None or score > best_score:
                best = primitive
                best_score = score
        assert best is not None, f"task {task.task_id} has no secondary primitive candidate"
        assignments[task.task_id] = best
        if remaining.get(best, 0) > 0:
            remaining[best] -= 1
    return assignments


def course_ref(task: Any) -> str | None:
    key = singular_target_key(
        task,
        [
            "target_course_id",
            "most_lenient_course_id",
            "strictest_course_id",
            "lower_grade_course_id",
            "higher_grade_conflict_course_id",
            "lower_grade_conflict_course_id",
            "ta_course_id",
            "student_course_id",
        ],
        token="course",
        allow_generic=False,
    )
    return f"{{target.{key}}}" if key else None


def course_code_ref(task: Any) -> str | None:
    targets = set((task.seed.targets or {}).keys()) if task.seed else set()
    for key in (
        "course_code",
        "course_code_1",
        "course_code_2",
        "course_code_a",
        "course_code_b",
        "ta_course_code",
        "student_course_code",
        "target_course_code",
    ):
        if key in targets:
            return f"{{target.{key}}}"
    return None


def discussion_ref(task: Any) -> str | None:
    key = singular_target_key(task, ["target_discussion_id"], token="discussion", allow_generic=False)
    return f"{{target.{key}}}" if key else None


def review_ref(task: Any) -> str | None:
    key = singular_target_key(task, ["target_review_id"], token="review", allow_generic=False)
    return f"{{target.{key}}}" if key else None


def assignment_ref(task: Any) -> str | None:
    key = singular_target_key(
        task,
        [
            "target_assignment_id",
            "feedback_assignment_id",
            "exam_assignment_id",
            "resubmit_assignment_id",
            "worst_category_assignment_id",
            "highest_weight_ungraded_id",
            "next_deadline_assignment_id",
            "missing_assignment_id",
            "most_recent_graded_id",
            "most_impactful_graded_id",
            "unsubmitted_hw_id",
            "lowest_hw_id",
            "lowest_homework_id",
            "overdue_assignment_id",
        ],
        token="assignment",
        allow_generic=False,
    )
    return f"{{target.{key}}}" if key else None


def title_ref(task: Any, family: str) -> str | None:
    targets = set((task.seed.targets or {}).keys()) if task.seed else set()
    if family == "assignment":
        for key in ("assignment_title", "target_assignment_title", "overdue_assignment_title"):
            if key in targets:
                return f"{{target.{key}}}"
    if family == "discussion":
        for key in ("discussion_title", "target_discussion_title"):
            if key in targets:
                return f"{{target.{key}}}"
    if family == "module":
        if "module_title" in targets:
            return "{target.module_title}"
    if family == "course":
        for key in ("course_code", "course_code_1", "course_code_a", "ta_course_code", "student_course_code"):
            if key in targets:
                return f"{{target.{key}}}"
    return None


def read_pattern(task: Any, family: str) -> str:
    if family == "announcement":
        return "**/api/env/lms/announcements**"
    if family == "calendar":
        return "**/api/env/lms/calendar**"
    if family == "discussion":
        return "**/api/env/lms/courses/*/discussions"
    if family == "peer_review":
        return "**/api/env/lms/peer-reviews"
    if family == "module":
        return "**/api/env/lms/courses/*/modules"
    if family == "course":
        return "**/api/env/lms/courses"
    if family == "assignment":
        if assignment_ref(task):
            return "**/api/env/lms/grades/*"
        return "**/api/env/lms/courses/*/assignments"
    return "**/api/env/lms/courses/*/grades"


def write_pattern(task: Any, family: str) -> tuple[str, list[str]] | None:
    instruction = (task.instruction_template or task.instruction or "").lower()
    task_id = task.task_id
    if family == "discussion":
        if "update_discussion_post" in task_id:
            return ("**/api/env/lms/discussions/*/posts/*", ["PUT"])
        if "reply" in task_id:
            return ("**/api/env/lms/discussions/*/posts/*/reply", ["POST"])
        return ("**/api/env/lms/discussions/*/posts", ["POST"])
    if family == "peer_review":
        return ("**/api/env/lms/peer-reviews/*/submit", ["POST"])
    if family == "announcement":
        if "mark_all" in task_id or "all_announcements" in task_id:
            return ("**/api/env/lms/announcements/mark_all_read", ["POST"])
        return ("**/api/env/lms/announcements/*/read", ["POST"])
    if family == "module":
        return ("**/api/env/lms/modules/*/items/*/complete", ["POST"])
    if "drop_course" in task_id or "compare_course_grades" in task_id:
        return ("**/api/env/lms/courses/*/drop", ["POST"])
    if "send a brief" in instruction or "send a message" in instruction:
        return ("**/api/env/lms/messages/send", ["POST"])
    if "resubmit" in task_id:
        return ("**/api/env/lms/assignments/*/resubmit", ["POST"])
    if "what_if" in task_id:
        return ("**/api/env/lms/courses/*/grades/what-if", ["POST"])
    if any(token in task_id for token in ("submit", "assignment", "late", "priority", "sprint", "portfolio", "recovery", "optimization", "maintenance")):
        return ("**/api/env/lms/assignments/*/submit", ["POST"])
    return None


def stale_body(task: Any, family: str) -> dict[str, Any]:
    if family in {"announcement", "calendar", "discussion", "peer_review", "module", "course"}:
        return {"items": []}
    if family == "assignment" and assignment_ref(task):
        return {
            "assignment_id": assignment_ref(task) or "",
            "assignment_title": title_ref(task, "assignment") or "Assignment",
            "score": None,
            "points_possible": "100",
            "feedback": None,
            "submission_status": "graded",
            "grade": None,
        }
    if family == "assignment":
        return {"items": []}
    course_value = course_ref(task) or ""
    course_title_value = None
    for key in ("course_code", "course_code_1", "course_code_a", "ta_course_code", "student_course_code"):
        if task.seed and key in (task.seed.targets or {}):
            course_title_value = f"{{target.{key}}}"
            break
    return {
        "course_id": course_value,
        "course_code": course_title_value or "COURSE",
        "weighted_score": None,
        "category_scores": {},
        "grades": [],
    }


def decoys_for_family(task: Any, family: str) -> list[dict[str, Any]]:
    course_value = course_ref(task)
    course_code_value = course_code_ref(task)
    title_value = title_ref(task, family)
    assignment_value = assignment_ref(task)
    discussion_value = discussion_ref(task)
    review_value = review_ref(task)
    decoys: list[dict[str, Any]]
    course_selector: dict[str, Any] = {}
    if course_value is not None:
        course_selector["course_id"] = course_value
    if course_code_value is not None:
        course_selector["course_code"] = course_code_value

    if family == "announcement":
        base = title_value or "Course update"
        decoys = [
            {
                "type": "announcement",
                **course_selector,
                "title": f"{base} follow-up",
                "body": "Archived clarification that does not replace the active announcement.",
                "priority": "normal",
            },
            {
                "type": "announcement",
                **course_selector,
                "title": f"{base} correction",
                "body": "Earlier logistics note for a prior announcement batch.",
                "priority": "urgent",
            },
        ]
    elif family == "discussion":
        base = title_value or "Week 4 discussion"
        decoys = [
            {
                "type": "discussion",
                **course_selector,
                "title": f"{base} archive",
                "prompt": "Archived discussion shell from a previous cohort.",
                "posts": [
                    {
                        "body": "This older thread stays visible for reference only.",
                        "author_name": "Dr. Morgan Hale",
                    }
                ],
            }
        ]
        if discussion_value:
            decoys.append(
                {
                    "type": "discussion",
                    **course_selector,
                    "discussion_id": discussion_value,
                    "posts": [
                        {
                            "body": "Reminder: use the current grading criteria, not last week's note.",
                            "author_name": "Course Staff",
                        }
                    ],
                }
            )
    elif family == "module":
        base = title_value or "Module checkpoint"
        decoys = [
            {
                "type": "module",
                **course_selector,
                "title": f"{base} review copy",
                "position": 2,
                "status": "available",
                "content_items": [
                    {"title": "Archived reading", "type": "reading", "completed": False},
                    {"title": "Reference quiz", "type": "quiz", "completed": False},
                ],
            }
        ]
    elif family == "peer_review":
        base = title_value or "Reflection submission"
        decoys = [
            {
                "type": "peer_review",
                **course_selector,
                "assignment_id": assignment_value,
                "reviewee_name": "Jordan Perez",
                "submission_title": f"{base} draft",
                "submission_body": "Near-match draft that is not the active review target.",
                "status": "assigned",
            }
        ]
        if review_value:
            decoys.append(
                {
                    "type": "peer_review",
                    **course_selector,
                    "assignment_id": assignment_value,
                    "submission_title": f"{base} revision copy",
                    "submission_body": "Returned draft with older comments.",
                    "status": "in_progress",
                    "returned_for_revision": True,
                }
            )
    elif family == "calendar":
        base = title_value or "Course event"
        decoys = [
            {
                "type": "calendar_event",
                **course_selector,
                "title": f"{base} review session",
                "event_type": "lecture",
                "location": "Library 204",
            },
            {
                "type": "calendar_event",
                **course_selector,
                "title": f"{base} deadline reminder",
                "event_type": "deadline",
                "location": "LMS",
            },
        ]
    elif family == "course":
        base = title_value or "COURSE"
        decoys = [
            {
                "type": "course",
                "course_code": f"{base}-ALT",
                "title": f"{base} Alternate Section",
                "status": "enrolled",
            },
            {
                "type": "announcement",
                **course_selector,
                "title": f"{base} registration note",
                "body": "Archived enrollment reminder for a similar course code.",
                "priority": "normal",
            },
        ]
    elif family == "assignment":
        base = title_value or "Weekly submission"
        decoys = [
            {
                "type": "assignment",
                **course_selector,
                "title": f"{base} practice copy",
                "assignment_type": "homework",
                "submission_status": "not_submitted",
            },
            {
                "type": "assignment",
                **course_selector,
                "title": f"{base} archived version",
                "assignment_type": "homework",
                "submission_status": "graded",
                "score": "88",
                "feedback": "This is an older graded copy.",
            },
        ]
    else:
        base = title_value or "Grade review"
        decoys = [
            {
                "type": "assignment",
                **course_selector,
                "title": f"{base} worksheet",
                "assignment_type": "homework",
                "submission_status": "graded",
                "score": "92",
                "feedback": "Reference score from a lower-weight practice item.",
            },
            {
                "type": "announcement",
                **course_selector,
                "title": f"{base} clarification",
                "body": "Reminder that grade calculations should use the active syllabus weights.",
                "priority": "normal",
            },
        ]
    return [
        decoy
        for decoy in decoys
        if ("course_id" not in decoy or decoy.get("course_id") not in ("", None))
        or ("course_code" in decoy and decoy.get("course_code") not in ("", None))
    ]


def variant_suffix(task: Any, primitive: str, family: str, *, profile: str) -> str:
    if profile == "secondary":
        if primitive == "grounding":
            return f"{family}_shadow_refresh_v2"
        if primitive == "exploration":
            return f"{family}_search_noise_v2"
        if primitive == "planning":
            return f"{family}_replan_v2"
        if primitive == "verification":
            if family in {"assignment", "grade"}:
                return "grade_persist_check_v2"
            return f"{family}_persist_check_v2"
        if primitive == "patience":
            return f"{family}_slow_retry_v2"
        if primitive == "backtracking":
            return f"{family}_correction_retry_v2"
        return f"{family}_update_shadow_v2"
    if primitive == "grounding":
        return f"{family}_shadow_v1"
    if primitive == "exploration":
        return f"{family}_clutter_v1"
    if primitive == "planning":
        return f"{family}_ordering_shift_v1"
    if primitive == "verification":
        if family in {"assignment", "grade"}:
            return "grade_verify_v1"
        return f"{family}_verify_v1"
    if primitive == "patience":
        return f"{family}_retry_v1"
    if primitive == "backtracking":
        return f"{family}_backtrack_retry_v1"
    return f"{family}_state_shadow_v1"


def description_for_variant(task: Any, primitive: str, family: str, *, profile: str) -> str:
    if profile == "secondary":
        if primitive == "grounding":
            return f"Shadow {family.replace('_', ' ')} records plus a later correction compete for attention, so the agent must ground on the exact LMS target before acting."
        if primitive == "exploration":
            return f"Search-space noise and a later LMS correction spread the clue trail across surfaces. The agent must continue exploring until the real target is confirmed."
        if primitive == "planning":
            return "A later LMS correction changes the action context after the first pass, so the agent must re-plan instead of following its initial route blindly."
        if primitive == "verification":
            return "The LMS presents an initially plausible state, then a later correction or refresh reveals the true outcome. The agent must verify persisted state before stopping."
        if primitive == "patience":
            return "A task-critical LMS read path is slow and transiently unavailable. The agent must keep retrying without losing its place."
        if primitive == "backtracking":
            return "A transient LMS failure is followed by a correction notice, so the agent must revisit and redo the right step rather than committing to the first path."
        return "Relevant LMS state is updated after the first clue, so the agent must keep tracking the current object and not anchor on the initial snapshot."
    if primitive == "grounding":
        return f"Lookalike {family.replace('_', ' ')} records sit near the target, so the agent must match the exact LMS entity before acting."
    if primitive == "exploration":
        return f"Extra {family.replace('_', ' ')} noise expands the LMS search surface. The agent must keep exploring until it finds the real target."
    if primitive == "planning":
        return "Ordering cues are perturbed and the first snapshot can be incomplete, so the agent must re-plan against the current LMS state."
    if primitive == "verification":
        return "A key LMS read or write initially returns a misleading success or stale snapshot. The agent must verify the real persisted outcome."
    if primitive == "patience":
        return "A task-critical LMS route is delayed or fails transiently. The agent must wait, retry, and keep progress coherent."
    if primitive == "backtracking":
        return "The first LMS attempt fails transiently, so the agent must recover cleanly and redo the correct action."
    return "Additional LMS shadows split relevant state across similar entities. The agent must track the right object throughout the workflow."


def correction_notice_injection(task: Any, family: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "action": "add_lms_correction_notice",
        "seed": 42,
        "title": "Correction: use the latest LMS update",
        "body": "Correction: the earlier LMS view was incomplete. Use the latest course state before you finish.",
        "priority": "normal",
    }
    if course_ref(task):
        params["course_id"] = course_ref(task)
    elif course_code_ref(task):
        params["course_code"] = course_code_ref(task)
    if family == "discussion" and discussion_ref(task):
        params["type"] = "discussion_post"
        params["discussion_id"] = discussion_ref(task)
    else:
        params["type"] = "announcement"
    return {"layer": "server", "params": params}


def injection_signature(task: Any, primitive: str, family: str, *, profile: str) -> list[dict[str, Any]]:
    task_hash = sum(ord(ch) for ch in task.task_id)
    decoy_injection = {
        "layer": "seed",
        "params": {
            "action": "add_confusing_decoys",
            "decoys": decoys_for_family(task, family),
        },
    }
    scramble_injection = {
        "layer": "server",
        "params": {
            "action": "scramble_timestamps",
            "seed": 42,
        },
    }
    stale_injection = {
        "layer": "network",
        "params": {
            "action": "stale_data",
            "url_pattern": read_pattern(task, family),
            "stale_body": stale_body(task, family),
            "stale_count": 1,
            "behavior": {"mode": "once"},
        },
    }
    correction_injection = correction_notice_injection(task, family)
    read_delay_injection = {
        "layer": "network",
        "params": {
            "action": "delay",
            "url_pattern": read_pattern(task, family),
            "methods": ["GET"],
            "delay_ms": 1800,
            "behavior": {
                "mode": "progressive",
                "stages": [
                    {"after_call": 0, "delay_ms": 900},
                    {"after_call": 2, "delay_ms": 1800},
                ],
            },
        },
    }
    read_retry_injection = {
        "layer": "network",
        "params": {
            "action": "error_then_success",
            "url_pattern": read_pattern(task, family),
            "methods": ["GET"],
            "error_count": 1,
            "error_status": 503,
            "error_message": "Temporary LMS read failure. Refresh and try again.",
            "behavior": {"mode": "once"},
        },
    }

    write = write_pattern(task, family)
    retry_injection = None
    silent_injection = None
    delay_injection = None
    if write is not None:
        url_pattern, methods = write
        retry_injection = {
            "layer": "network",
            "params": {
                "action": "error_then_success",
                "url_pattern": url_pattern,
                "methods": methods,
                "error_count": 1,
                "error_status": 503,
                "error_message": "Temporary LMS failure. Retry the request.",
                "behavior": {"mode": "once"},
            },
        }
        silent_injection = {
            "layer": "network",
            "params": {
                "action": "silent_fail",
                "url_pattern": url_pattern,
                "methods": methods,
                "fail_count": 1,
                "response_body": silent_fail_body(task, family, write_url=url_pattern),
                "behavior": {"mode": "once"},
            },
        }
        delay_injection = {
            "layer": "network",
            "params": {
                "action": "delay",
                "url_pattern": url_pattern,
                "methods": methods,
                "delay_ms": 1600,
                "behavior": {
                    "mode": "progressive",
                    "stages": [
                        {"after_call": 0, "delay_ms": 800},
                        {"after_call": 2, "delay_ms": 1600},
                    ],
                },
            },
        }

    if profile == "secondary":
        if primitive == "grounding":
            return [decoy_injection, correction_injection]
        if primitive == "exploration":
            return [correction_injection, stale_injection]
        if primitive == "planning":
            return [scramble_injection, correction_injection]
        if primitive == "verification":
            if silent_injection is not None and family not in {"assignment", "discussion", "peer_review", "announcement"}:
                return [silent_injection, correction_injection]
            return [stale_injection, correction_injection]
        if primitive == "patience":
            return [read_delay_injection, read_retry_injection]
        if primitive == "backtracking":
            return [retry_injection or read_retry_injection, correction_injection]
        return [correction_injection, stale_injection]

    if primitive == "grounding":
        return [decoy_injection]
    if primitive == "exploration":
        return [decoy_injection, stale_injection]
    if primitive == "planning":
        if family in {"calendar", "grade", "course"} or task_hash % 2 == 0:
            return [scramble_injection, stale_injection]
        return [decoy_injection, scramble_injection]
    if primitive == "verification":
        if silent_injection is not None and family in {"assignment", "discussion", "peer_review", "announcement"}:
            return [silent_injection, decoy_injection]
        return [stale_injection, decoy_injection]
    if primitive == "patience":
        if delay_injection is not None and retry_injection is not None:
            return [delay_injection, retry_injection]
        return [delay_injection or stale_injection, decoy_injection]
    if primitive == "backtracking":
        return [retry_injection or stale_injection, decoy_injection]
    if task_hash % 2 == 0:
        return [decoy_injection, scramble_injection]
    return [decoy_injection, stale_injection]


def silent_fail_body(task: Any, family: str, *, write_url: str | None = None) -> dict[str, Any]:
    timestamp = "2026-01-15T12:00:00+00:00"
    if write_url and "messages/send" in write_url:
        return {
            "message": {
                "to": "advisor@school.edu",
                "subject": "Question about next steps",
                "body": "This looked sent, but the LMS did not persist it.",
                "sent_at": timestamp,
                "from": "student@example.edu",
            },
            "sent": False,
        }
    if write_url and "/courses/*/drop" in write_url:
        return {
            "enrollment": {
                "id": "enrollment_fake",
                "student_id": "student_fake",
                "course_id": course_ref(task) or "course_fake",
                "role": "student",
                "status": "dropped",
                "final_grade": None,
                "final_score": None,
            },
            "dropped": True,
        }
    if family == "announcement":
        return {
            "announcement": {
                "id": "ann_fake",
                "course_id": course_ref(task) or "course_fake",
                "title": "Announcement copy",
                "body": "Archived message that should not be trusted without verification.",
                "posted_at": timestamp,
                "is_read": True,
                "priority": "normal",
            }
        }
    if family == "discussion":
        return {
            "post": {
                "id": "post_fake",
                "discussion_id": discussion_ref(task) or "discussion_fake",
                "author_id": "student_fake",
                "author_name": "Student",
                "body": "Looks posted, but the server did not persist it.",
                "parent_post_id": None,
                "timestamp": timestamp,
                "updated_at": None,
                "is_anonymous": False,
            }
        }
    if family == "peer_review":
        return {
            "peer_review": {
                "id": review_ref(task) or "review_fake",
                "assignment_id": assignment_ref(task) or "assignment_fake",
                "reviewer_student_id": "student_fake",
                "reviewee_student_id": "peer_fake",
                "reviewee_name": "Jordan Perez",
                "submission_title": "Draft reflection",
                "submission_body": "This response should not be treated as persisted.",
                "assignment_rubric": [],
                "rubric_scores": {},
                "comments": "",
                "status": "submitted",
                "returned_for_revision": False,
                "previous_rubric_scores": {},
                "previous_comments": "",
                "due_at": timestamp,
            }
        }
    return {
        "assignment": {
            "id": assignment_ref(task) or "assignment_fake",
            "course_id": course_ref(task) or "course_fake",
            "title": title_ref(task, "assignment") or "Assignment",
            "type": "homework",
            "due_at": timestamp,
            "points_possible": "100",
            "submission_status": "submitted",
            "score": None,
            "feedback": None,
            "attempt_count": 1,
            "max_attempts": 3,
            "rubric": [],
            "weight_category": "homework",
            "submitted_at": timestamp,
            "file_name": "degraded.pdf",
        }
    }


def build_variant(task: Any, primitive: str, *, profile: str) -> dict[str, Any]:
    family = family_for_task(task)
    suffix = variant_suffix(task, primitive, family, profile=profile)
    return {
        "variant_id": f"{task.task_id}__{suffix}",
        "base_task_id": task.task_id,
        "target_primitive": primitive,
        "description": description_for_variant(task, primitive, family, profile=profile),
        "injections": injection_signature(task, primitive, family, profile=profile),
    }


def write_variants() -> Counter[str]:
    tasks = env_tasks("lms")
    primary_map = choose_target_primitive(tasks)
    secondary_map = choose_secondary_primitive(tasks, primary_map)
    counts: Counter[str] = Counter()
    for path in VARIANTS_DIR.glob("lms_*.yaml"):
        path.unlink()
    for task in tasks:
        variants = [
            build_variant(task, primary_map[task.task_id], profile="primary"),
            build_variant(task, secondary_map[task.task_id], profile="secondary"),
        ]
        for variant in variants:
            filename = f"{variant['variant_id']}.yaml"
            path = VARIANTS_DIR / filename
            path.write_text(yaml.safe_dump(variant, sort_keys=False))
            counts[variant["target_primitive"]] += 1
    return counts


if __name__ == "__main__":
    counts = write_variants()
    print("Generated LMS variants:")
    for primitive, count in sorted(counts.items()):
        print(f"  {primitive}: {count}")
