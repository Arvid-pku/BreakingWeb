"""
test_frontend_field_coverage.py

Linter that ensures every field referenced by task instructions is actually
rendered in the corresponding frontend component.

Methodology:
  1. For each task YAML in each environment's tasks/ directory, scan the
     instruction_template for known field-reference keywords.
  2. For each match, assert that the target frontend file contains the field name
     (as a React prop or data access expression).

Add new entries to TASK_FIELD_REQUIREMENTS when a task is added that references
a new data field not yet covered.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent

TASK_DIRS = [
    REPO_ROOT / "breakingweb/tasks/patient_portal",
    REPO_ROOT / "breakingweb/tasks/lms",
    REPO_ROOT / "breakingweb/tasks/amazon",
    REPO_ROOT / "breakingweb/tasks/robinhood",
    REPO_ROOT / "breakingweb/tasks/gmail",
    REPO_ROOT / "breakingweb/tasks/booking",
    REPO_ROOT / "breakingweb/tasks/reddit",
]

PP_PAGES = REPO_ROOT / "breakingweb/environments/patient_portal/src/pages"
LMS_PAGES = REPO_ROOT / "breakingweb/environments/lms/src/pages"
AMAZON_COMPONENTS = REPO_ROOT / "breakingweb/environments/amazon/src/components"
RH_PAGES = REPO_ROOT / "breakingweb/environments/robinhood/src/pages"
GMAIL_PAGES = REPO_ROOT / "breakingweb/environments/gmail/src/pages"

# Maps (instruction keyword regex) -> (frontend_file, field_string_that_must_appear)
# The keyword regex is matched case-insensitively against instruction_template.
# The field_string is searched as a substring of the frontend file content.
TASK_FIELD_REQUIREMENTS: list[tuple[str, str, str]] = [
    # Patient Portal — Appointments
    (r"booked.at|booked (more )?recently|booked later|earlier.booked",
     str(PP_PAGES / "Appointments.tsx"), "booked_at"),
    (r"pre.auth|pre_auth|prior auth",
     str(PP_PAGES / "Appointments.tsx"), "pre_auth_status"),

    # Patient Portal — Medications
    (r"refills? remaining|0 refills",
     str(PP_PAGES / "Medications.tsx"), "refills_remaining"),
    (r"expir(ing|es?|ation)|prescription.*expir",
     str(PP_PAGES / "Medications.tsx"), "expires_at"),
    (r"last (filled|fill)",
     str(PP_PAGES / "Medications.tsx"), "last_filled"),
    (r"drug interaction|interaction warning|interaction",
     str(PP_PAGES / "Medications.tsx"), "interactions"),

    # Patient Portal — Labs
    (r"ordered (by|that) (lab|provider)|provider who ordered",
     str(PP_PAGES / "Labs.tsx"), "ordered_by"),
    (r"reference range|normal range",
     str(PP_PAGES / "Labs.tsx"), "reference_range"),
    (r"critical lab|abnormal|lab.*flag|flag.*lab",
     str(PP_PAGES / "Labs.tsx"), "flag"),

    # Patient Portal — Billing
    (r"denial reason|denied.*reason|why.*denied",
     str(PP_PAGES / "Billing.tsx"), "denial_reason"),
    (r"appeal deadline",
     str(PP_PAGES / "Billing.tsx"), "appeal_deadline"),
    (r"eob|explanation of benefits",
     str(PP_PAGES / "Billing.tsx"), "eob_available"),
    (r"service date",
     str(PP_PAGES / "Billing.tsx"), "service_date"),

    # Patient Portal — Profile
    (r"applicable screenings?|overdue screening|screening.*next_due",
     str(PP_PAGES / "Profile.tsx"), "applicable_screenings"),

    # Patient Portal — Messages
    (r"linked (claim|referral|entity|appointment).*message|message.*linked (claim|referral|entity)",
     str(PP_PAGES / "Messages.tsx"), "linked_entity_id"),

    # LMS — Assignment
    (r"review the rubric|rubric criteria|rubric.*assignment",
     str(LMS_PAGES / "Assignment.tsx"), "rubric"),
    (r"read.*feedback|instructor.*feedback|feedback.*resubmit",
     str(LMS_PAGES / "Assignment.tsx"), "feedback"),
    (r"remaining attempts|attempt.*remain|retake",
     str(LMS_PAGES / "Assignment.tsx"), "max_attempts"),
    (r"weight.?category|grade weight",
     str(LMS_PAGES / "Assignment.tsx"), "weight_category"),

    # LMS — Grades
    (r"dropped? (grade|assignment|lowest)|drop.lowest",
     str(LMS_PAGES / "Grades.tsx"), "is_dropped"),

    # LMS — CourseView (Syllabus tab)
    (r"late policy|late.penalty|max late days|grace period",
     str(LMS_PAGES / "CourseView.tsx"), "late_policy"),
    (r"drop deadline",
     str(LMS_PAGES / "Courses.tsx"), "drop_deadline"),

    # LMS — PeerReviews
    (r"read.*submission|submission.*rubric|reviewee.*submission",
     str(LMS_PAGES / "PeerReviews.tsx"), "submission_body"),

    # Amazon — Cart
    # CartItem.in_stock: tasks ask agent to remove out-of-stock items from cart.
    # "Currently unavailable" badge is rendered in CartItem.tsx when in_stock === false.
    (r"out.of.stock|out-of-stock|remove.*unavailable|unavailable.*item.*cart|diagnose.*cart",
     str(AMAZON_COMPONENTS / "CartItem.tsx"), "in_stock"),

    # Robinhood — Portfolio (margin maintenance)
    # rh_margin_call_resolution asks agent to read margin_maintenance and sell/deposit to cover it.
    (r"margin maintenance|margin.call|maintenance requirement|margin.*warning",
     str(RH_PAGES / "Portfolio.tsx"), "margin_maintenance"),

    # Robinhood — Recurring (execution history / average purchase price)
    # rh_recurring_optimization asks agent to compare avg purchase price from history vs current price.
    (r"average purchase price.*history|history.*average|purchase.*history|recurring.*history",
     str(RH_PAGES / "Recurring.tsx"), "avgPrice"),

    # Gmail — Labels / Contacts (last_contacted_at)
    # gmail_contact_audit and gmail_annual_contact_review ask agent to read "Last Contact" column.
    (r"last.contact|not been in touch|email activity.*days|contact.*days",
     str(GMAIL_PAGES / "Labels.tsx"), "last_contacted_at"),
]


def load_instructions(task_dirs: list[Path]) -> list[tuple[Path, str]]:
    """Return (yaml_path, instruction_template) pairs for all tasks."""
    results = []
    for d in task_dirs:
        for p in sorted(d.glob("*.yaml")):
            try:
                data = yaml.safe_load(p.read_text())
            except Exception:
                continue
            instruction = data.get("instruction_template", "") or ""
            results.append((p, instruction))
    return results


def read_frontend(path: str) -> str:
    return Path(path).read_text()


# Pre-load frontend contents once
_FRONTEND_CACHE: dict[str, str] = {}


def frontend_content(path: str) -> str:
    if path not in _FRONTEND_CACHE:
        _FRONTEND_CACHE[path] = read_frontend(path)
    return _FRONTEND_CACHE[path]


@pytest.mark.parametrize("yaml_path,instruction", load_instructions(TASK_DIRS))
def test_task_fields_are_rendered(yaml_path: Path, instruction: str) -> None:
    """
    For each task instruction, check that any referenced field is visible in
    the corresponding frontend component.
    """
    failures: list[str] = []

    for keyword_pattern, frontend_file, field_name in TASK_FIELD_REQUIREMENTS:
        if not re.search(keyword_pattern, instruction, re.IGNORECASE):
            continue  # this task doesn't reference this field
        content = frontend_content(frontend_file)
        if field_name not in content:
            component = Path(frontend_file).name
            failures.append(
                f"Task '{yaml_path.stem}' references '{keyword_pattern}' but "
                f"'{field_name}' is NOT rendered in {component}"
            )

    if failures:
        msg = "\n".join(failures)
        pytest.fail(f"Frontend field coverage gaps detected:\n{msg}")


def test_all_checked_frontend_files_exist() -> None:
    """Verify every frontend file referenced in TASK_FIELD_REQUIREMENTS exists."""
    checked = {req[1] for req in TASK_FIELD_REQUIREMENTS}
    for path in checked:
        assert Path(path).exists(), f"Frontend file does not exist: {path}"
