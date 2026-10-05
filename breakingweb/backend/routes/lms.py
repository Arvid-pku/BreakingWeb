"""LMS environment API routes.

Provides session management, CRUD endpoints for all LMS entities
(courses, assignments, modules, discussions, grades, announcements,
calendar, peer reviews, messages), and the evaluate endpoint.
"""
from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...tasks._evaluator import evaluate as unified_evaluate
from ...tasks._registry import get_task
from ..models.base import AuditEntry
from ..models.lms import Grade, LMSState
from ..security import (
    build_public_session_summary,
    has_controller_access,
    require_evaluation_access,
)
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/lms", tags=["lms"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    task_id: str
    seed: int | None = None
    degradation: dict | None = None
    variant_filename: str | None = None


class SessionScopedRequest(BaseModel):
    session_id: str


class EvaluateRequest(SessionScopedRequest):
    task_id: str | None = None
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


class TrajectoryRequest(SessionScopedRequest):
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


# --- Assignments ---

class SubmitAssignmentRequest(SessionScopedRequest):
    file_name: str = "submission.pdf"


class ResubmitAssignmentRequest(SessionScopedRequest):
    file_name: str = "submission_v2.pdf"


# --- Discussions ---

class CreatePostRequest(SessionScopedRequest):
    body: str


class ReplyPostRequest(SessionScopedRequest):
    body: str


class UpdatePostRequest(SessionScopedRequest):
    body: str


# --- Peer Reviews ---

class SubmitPeerReviewRequest(SessionScopedRequest):
    rubric_scores: dict[str, int] = Field(default_factory=dict)
    comments: str = ""


# --- Grades ---

class WhatIfRequest(SessionScopedRequest):
    hypothetical_scores: dict[str, str] = Field(default_factory=dict)


# --- Profile ---

class UpdateProfileRequest(SessionScopedRequest):
    name: str | None = None
    email: str | None = None


# --- Enrollment ---

class EnrollRequest(SessionScopedRequest):
    course_id: str
    role: Literal["student", "ta"] = "student"


# --- Messages ---

class SendMessageRequest(SessionScopedRequest):
    to: str
    subject: str
    body: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured on app.state")
    return session_manager


def _lms_state(session_manager: SessionManager, session_id: str) -> LMSState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, LMSState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not an LMS session")
    return state


def _render_degradation_params(degradation: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    """Resolve {target.*} placeholders inside degradation injections."""
    return {
        **degradation,
        "injections": [
            {
                **injection,
                "params": render_template(injection.get("params", {}), targets),
            }
            for injection in degradation.get("injections", [])
        ],
    }


def _mutate(
    session_manager: SessionManager,
    session_id: str,
    action: str,
    payload: dict[str, Any],
    mutator: Callable[[Any], Any],
) -> Any:
    """Run a mutation, translating domain errors to HTTP errors."""
    try:
        return session_manager.mutate(session_id, action, payload, mutator)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _unlock_available_modules(state: LMSState, course_id: str) -> None:
    for module in state.modules_for_course(course_id):
        if module.status == "locked" and state.is_module_unlocked(module.id):
            module.status = "available"


def _course_modules_payload(state: LMSState, course_id: str) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in state.modules_for_course(course_id)]


def _normalise_rubric_key(key: str) -> str:
    return "_".join(str(key).strip().lower().split())


def _sanitise_peer_review_scores(review: Any, raw_scores: dict[str, Any]) -> dict[str, int]:
    by_key = {_normalise_rubric_key(k): v for k, v in (raw_scores or {}).items()}
    valid_keys = [_normalise_rubric_key(item.criterion) for item in review.assignment_rubric]
    cleaned: dict[str, int] = {}
    for key in valid_keys:
        if key not in by_key:
            continue
        try:
            value = int(by_key[key])
        except (TypeError, ValueError):
            continue
        cleaned[key] = max(1, min(5, value))
    return cleaned


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.post("/session")
def create_session(
    body: SessionCreateRequest,
    request: Request = None,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    task = get_task(body.task_id)
    if task.env_id != "lms":
        raise HTTPException(status_code=404, detail=f"Unknown LMS task_id: {body.task_id}")

    degradation = dict(body.degradation) if body.degradation else None
    if body.variant_filename and not degradation:
        if "/" in body.variant_filename or "\\" in body.variant_filename or ".." in body.variant_filename:
            raise HTTPException(status_code=400, detail="Invalid variant filename")
        if body.variant_filename.startswith("__auto__"):
            remainder = body.variant_filename[len("__auto__"):]
            sep_pos = remainder.rfind("__")
            if sep_pos > 0:
                auto_task_id = remainder[:sep_pos]
                auto_primitive = remainder[sep_pos + 2:]
                from ...injector.config import DegradationConfig
                auto_cfg = DegradationConfig.default_for_primitive(auto_task_id, auto_primitive)
                if auto_cfg is None:
                    raise HTTPException(status_code=404, detail=f"No default template for primitive: {auto_primitive}")
                degradation = {
                    "variant_filename": body.variant_filename,
                    "variant_id": auto_cfg.variant_id,
                    "base_task_id": auto_cfg.base_task_id,
                    "target_primitive": auto_cfg.target_primitive,
                    "description": auto_cfg.description,
                    "injections": [{"layer": inj.layer, "params": inj.params} for inj in auto_cfg.injections],
                }
            else:
                raise HTTPException(status_code=400, detail=f"Malformed auto variant filename: {body.variant_filename}")
        else:
            from pathlib import Path
            import yaml

            variant_path = Path(__file__).parent.parent.parent / "injector" / "variants" / body.variant_filename
            if not variant_path.exists():
                raise HTTPException(status_code=404, detail=f"Unknown degradation variant: {body.variant_filename}")
            variant_data = yaml.safe_load(variant_path.read_text()) or {}
            degradation = {
                "variant_filename": body.variant_filename,
                **variant_data,
            }

    if degradation and degradation.get("base_task_id") and degradation.get("base_task_id") != body.task_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Degradation variant is bound to task {degradation.get('base_task_id')!r}, "
                f"but the session request targets {body.task_id!r}"
            ),
        )

    session_id, resolved_targets, actual_seed = session_manager.create_session("lms", body.task_id, body.seed)
    state = session_manager.get(session_id)
    if degradation:
        degradation = _render_degradation_params(degradation, resolved_targets)

    if degradation:
        state._degradation = {
            "variant_filename": degradation.get("variant_filename"),
            "variant_id": degradation.get("variant_id", ""),
            "base_task_id": degradation.get("base_task_id", body.task_id),
            "target_primitive": degradation.get("target_primitive", ""),
            "description": degradation.get("description", ""),
            "injections": list(degradation.get("injections", [])),
        }
        state.audit_log.append(
            AuditEntry(
                action="benchmark.degradation.apply",
                payload={
                    "variant_id": state.degradation.get("variant_id", ""),
                    "target_primitive": state.degradation.get("target_primitive", ""),
                    "variant_filename": state.degradation.get("variant_filename"),
                    "injections": len(state.degradation.get("injections", [])),
                },
                summary="Applied degradation configuration",
                snapshot={"task_id": state.task_id, "seed": state.seed},
            )
        )

    if degradation:
        from ...injector.seed import apply_seed_injection
        from ...injector.server import apply_server_injection
        seed_rng = random.Random(actual_seed)
        for injection in degradation.get("injections", []):
            layer = injection.get("layer")
            params = injection.get("params", {})
            if layer == "seed":
                apply_seed_injection(state, params, rng=seed_rng)
            elif layer == "server":
                apply_server_injection(state, params)
        state.touch()

    if degradation:
        from ...injector.middleware import register_session_degradation
        register_session_degradation(session_id, degradation.get("injections", []))

    # Capture baseline snapshot for collateral-damage detection.
    # Must run after degradation injections so initial reflects post-injection state.
    if hasattr(state, "state_snapshot"):
        state._initial_snapshot = state.state_snapshot()
    state._initial_state_copy = state.model_copy(deep=True)

    instruction = render_template(
        task.instruction_template or task.instruction or "", resolved_targets
    )
    resp: dict[str, Any] = {
        "session_id": session_id,
        "start_path": task.start_path or "/",
        "title": task.title,
        "instruction": instruction,
        "degradation_active": bool(degradation),
    }
    if request is not None and has_controller_access(request):
        resp["resolved_targets"] = resolved_targets
    return resp


@router.get("/session/{session_id}")
def get_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        summary = session_manager.session_summary(session_id)
        state = session_manager.get(session_id)
        task = get_task(state.task_id)
        return build_public_session_summary(
            summary,
            title=task.title,
            instruction=render_template(
                task.instruction_template or task.instruction or "", state.resolved_targets
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/session/{session_id}/reset")
def reset_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        state = session_manager.get(session_id)
        next_session = create_session(
            SessionCreateRequest(
                task_id=state.task_id,
                seed=state.seed,
                degradation=dict(state.degradation) if state.degradation else None,
            ),
            session_manager=session_manager,
        )
        delete_session(session_id, session_manager=session_manager)
        return next_session
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/session/{session_id}")
def delete_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        from ...injector.middleware import unregister_session_degradation
        unregister_session_degradation(session_id)
        session_manager.destroy(session_id)
        return {"deleted": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/evaluate")
def evaluate_session(
    body: EvaluateRequest,
    request: Request = None,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    try:
        state = session_manager.get(body.session_id)
        require_evaluation_access(
            request,
            requested_task_id=body.task_id,
            bound_task_id=state.task_id,
        )
        if body.benchmark_state is not None:
            session_manager.set_benchmark_state(body.session_id, body.benchmark_state)
        if body.task_id and body.task_id != state.task_id:
            raise HTTPException(
                status_code=400,
                detail=f"Session {body.session_id} is bound to task {state.task_id!r}, not {body.task_id!r}",
            )
        task = get_task(state.task_id)
        return unified_evaluate(
            task,
            server_state=state,
            targets=state.resolved_targets,
            trajectory=body.trajectory or [],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/degradation/{session_id}")
def get_client_degradation(session_id: str) -> dict[str, Any]:
    """Return client-layer degradation injections for a session."""
    from ...injector.middleware import get_client_injections
    injections = get_client_injections(session_id)
    return {"session_id": session_id, "client_injections": injections}


@router.get("/variants")
def list_variants() -> list[dict[str, Any]]:
    """List available degradation variants for the LMS environment."""
    from pathlib import Path
    import yaml as _yaml

    variants_dir = Path(__file__).parent.parent.parent / "injector" / "variants"
    result: list[dict[str, Any]] = []
    if variants_dir.exists():
        for f in sorted(variants_dir.glob("lms_*.yaml")):
            try:
                data = _yaml.safe_load(f.read_text())
                result.append({
                    "filename": f.name,
                    "variant_id": data.get("variant_id", ""),
                    "base_task_id": data.get("base_task_id", ""),
                    "target_primitive": data.get("target_primitive", ""),
                    "description": data.get("description", ""),
                    "source": "yaml",
                })
            except Exception:
                pass
    return result


@router.post("/trajectory")
def save_trajectory(
    body: TrajectoryRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    state.audit_log.append(
        AuditEntry(
            action="lms.trajectory.save",
            payload={"steps": len(body.trajectory)},
            summary=f"Saved trajectory with {len(body.trajectory)} steps",
        )
    )
    state.touch()
    return {"saved": True, "steps": len(body.trajectory)}


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/profile")
def get_profile(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    return {"student": state.student.model_dump(mode="json")}


@router.post("/profile/update")
def update_profile(
    body: UpdateProfileRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    changes: dict[str, Any] = {}
    if body.name is not None:
        state.student.name = body.name
        changes["name"] = body.name
    if body.email is not None:
        state.student.email = body.email
        changes["email"] = body.email
    if changes:
        state.audit_log.append(
            AuditEntry(
                action="lms.profile.update",
                payload=changes,
                summary=f"Updated profile: {', '.join(changes.keys())}",
            )
        )
        state.touch()
    return {"student": state.student.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

@router.get("/courses")
def list_courses(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    enrolled_course_ids = {
        e.course_id for e in state.enrollments
        if e.student_id == state.student.id and e.status == "enrolled"
    }
    courses = [c for c in state.courses if c.id in enrolled_course_ids]
    return {"items": [c.model_dump(mode="json") for c in courses]}


@router.get("/courses/{course_id}")
def get_course(
    course_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    course = state.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"Unknown course: {course_id}")
    return {"course": course.model_dump(mode="json")}


@router.get("/courses/{course_id}/syllabus")
def get_syllabus(
    course_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    course = state.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"Unknown course: {course_id}")
    syllabus_data = course.syllabus.model_dump(mode="json")
    return {
        "course_id": course_id,
        "course_code": course.course_code,
        "title": course.title,
        "syllabus": syllabus_data,
    }


@router.post("/courses/{course_id}/drop")
def drop_course(
    course_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    enrollment = state.get_enrollment_for_course(course_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail=f"No enrollment found for course: {course_id}")
    if enrollment.status != "enrolled":
        raise HTTPException(
            status_code=422,
            detail=f"Cannot drop course: enrollment status is '{enrollment.status}', expected 'enrolled'",
        )
    course = state.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"Unknown course: {course_id}")
    now = datetime.now(timezone.utc)
    if now > course.drop_deadline:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot drop course: drop deadline ({course.drop_deadline.isoformat()}) has passed",
        )
    enrollment.status = "dropped"
    state.audit_log.append(
        AuditEntry(
            action="lms.course.drop",
            payload={"course_id": course_id, "enrollment_id": enrollment.id},
            summary=f"Dropped course {course.course_code}",
        )
    )
    state.touch()
    return {"enrollment": enrollment.model_dump(mode="json"), "dropped": True}


# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------

@router.get("/enrollments")
def list_enrollments(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    student_enrollments = [e for e in state.enrollments if e.student_id == state.student.id]
    return {"items": [e.model_dump(mode="json") for e in student_enrollments]}


@router.post("/enrollments")
def create_enrollment(
    body: EnrollRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    course = state.get_course(body.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"Unknown course: {body.course_id}")
    existing = state.get_enrollment_for_course(body.course_id)
    if existing is not None:
        raise HTTPException(status_code=422, detail=f"Already enrolled in course: {body.course_id}")
    from ..models.lms import Enrollment
    enrollment_id = f"enrollment_{len(state.enrollments) + 1}"
    enrollment = Enrollment(
        id=enrollment_id,
        student_id=state.student.id,
        course_id=body.course_id,
        role=body.role,
        status="enrolled",
    )
    state.enrollments.append(enrollment)
    state.audit_log.append(
        AuditEntry(
            action="lms.enrollment.create",
            payload={"course_id": body.course_id, "enrollment_id": enrollment_id, "role": body.role},
            summary=f"Enrolled in {course.course_code} as {body.role}",
        )
    )
    state.touch()
    return {"enrollment": enrollment.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

@router.get("/courses/{course_id}/assignments")
def list_assignments(
    course_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    assignments = state.assignments_for_course(course_id)
    return {"items": [a.model_dump(mode="json") for a in assignments]}


@router.get("/assignments/{assignment_id}")
def get_assignment(
    assignment_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail=f"Unknown assignment: {assignment_id}")
    return {"assignment": assignment.model_dump(mode="json")}


@router.get("/assignments/{assignment_id}/rubric")
def get_rubric(
    assignment_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail=f"Unknown assignment: {assignment_id}")
    return {
        "assignment_id": assignment_id,
        "rubric": [r.model_dump(mode="json") for r in assignment.rubric],
    }


@router.post("/assignments/{assignment_id}/submit")
def submit_assignment(
    assignment_id: str,
    body: SubmitAssignmentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail=f"Unknown assignment: {assignment_id}")
    if assignment.submission_status not in ("not_submitted", "resubmit_requested", "graded", "late"):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot submit: assignment status is '{assignment.submission_status}'",
        )
    if assignment.attempt_count >= assignment.max_attempts:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot submit: max attempts ({assignment.max_attempts}) reached",
        )
    now = datetime.now(timezone.utc)
    assignment.submitted_at = now
    assignment.attempt_count += 1
    assignment.file_name = body.file_name
    if now > assignment.due_at:
        assignment.submission_status = "late"
    else:
        assignment.submission_status = "submitted"
    state.audit_log.append(
        AuditEntry(
            action="lms.assignment.submit",
            payload={
                "assignment_id": assignment_id,
                "file_name": body.file_name,
                "status": assignment.submission_status,
                "attempt": assignment.attempt_count,
            },
            summary=f"Submitted assignment {assignment.title}",
        )
    )
    state.touch()
    return {"assignment": assignment.model_dump(mode="json")}


@router.post("/assignments/{assignment_id}/resubmit")
def resubmit_assignment(
    assignment_id: str,
    body: ResubmitAssignmentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail=f"Unknown assignment: {assignment_id}")
    if assignment.submission_status != "resubmit_requested":
        raise HTTPException(
            status_code=422,
            detail=f"Cannot resubmit: assignment status is '{assignment.submission_status}', expected 'resubmit_requested'",
        )
    if assignment.attempt_count >= assignment.max_attempts:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot resubmit: max attempts ({assignment.max_attempts}) reached",
        )
    now = datetime.now(timezone.utc)
    assignment.submitted_at = now
    assignment.attempt_count += 1
    assignment.file_name = body.file_name
    if now > assignment.due_at:
        assignment.submission_status = "late"
    else:
        assignment.submission_status = "submitted"
    state.audit_log.append(
        AuditEntry(
            action="lms.assignment.resubmit",
            payload={
                "assignment_id": assignment_id,
                "file_name": body.file_name,
                "status": assignment.submission_status,
                "attempt": assignment.attempt_count,
            },
            summary=f"Resubmitted assignment {assignment.title}",
        )
    )
    state.touch()
    return {"assignment": assignment.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

@router.get("/courses/{course_id}/modules")
def list_modules(
    course_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    modules = state.modules_for_course(course_id)
    return {"items": [m.model_dump(mode="json") for m in modules]}


@router.get("/modules/{module_id}")
def get_module(
    module_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    module = state.get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module_id}")
    return {"module": module.model_dump(mode="json")}


@router.post("/modules/{module_id}/complete")
def complete_module(
    module_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    module = state.get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module_id}")
    if not state.is_module_unlocked(module_id):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot complete module: prerequisites not met for {module.title}",
        )
    # Check all content items are completed
    incomplete = [item for item in module.content_items if not item.completed]
    if incomplete:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot complete module: {len(incomplete)} content items still incomplete",
        )
    module.status = "completed"
    # Propagate unlock to downstream modules in the same course. The frontend
    # (CourseView.tsx) renders lock state via `mod.status === "locked"`, so
    # unless we transition dependents off "locked" here, completing a
    # prerequisite never visibly unlocks its successors even though
    # state.is_module_unlocked() would report them unlocked.
    _unlock_available_modules(state, module.course_id)
    state.audit_log.append(
        AuditEntry(
            action="lms.module.complete",
            payload={"module_id": module_id},
            summary=f"Completed module {module.title}",
        )
    )
    state.touch()
    return {
        "module": module.model_dump(mode="json"),
        "modules": _course_modules_payload(state, module.course_id),
    }


@router.post("/modules/{module_id}/items/{item_index}/complete")
def complete_module_item(
    module_id: str,
    item_index: int,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    module = state.get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module_id}")
    if not state.is_module_unlocked(module_id):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot access module: prerequisites not met for {module.title}",
        )
    if item_index < 0 or item_index >= len(module.content_items):
        raise HTTPException(status_code=404, detail=f"Invalid item index: {item_index}")
    module.content_items[item_index].completed = True
    state.audit_log.append(
        AuditEntry(
            action="lms.module.item.complete",
            payload={"module_id": module_id, "item_index": item_index},
            summary=f"Completed item '{module.content_items[item_index].title}' in {module.title}",
        )
    )
    state.touch()
    return {
        "module": module.model_dump(mode="json"),
        "modules": _course_modules_payload(state, module.course_id),
    }


# ---------------------------------------------------------------------------
# Discussions
# ---------------------------------------------------------------------------

@router.get("/courses/{course_id}/discussions")
def list_discussions(
    course_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    discussions = [d for d in state.discussions if d.course_id == course_id]
    return {"items": [d.model_dump(mode="json") for d in discussions]}


@router.get("/discussions/{discussion_id}")
def get_discussion(
    discussion_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    discussion = state.get_discussion(discussion_id)
    if discussion is None:
        raise HTTPException(status_code=404, detail=f"Unknown discussion: {discussion_id}")
    posts = state.posts_for_discussion(discussion_id)
    return {
        "discussion": discussion.model_dump(mode="json"),
        "posts": [p.model_dump(mode="json") for p in posts],
    }


@router.get("/discussions/{discussion_id}/posts")
def get_discussion_posts(
    discussion_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    posts = [p.model_dump(mode="json") for p in state.posts_for_discussion(discussion_id)]
    if not posts and state.get_discussion(discussion_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown discussion: {discussion_id}")
    return {"items": posts}


@router.post("/discussions/{discussion_id}/posts")
def create_post(
    discussion_id: str,
    body: CreatePostRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    discussion = state.get_discussion(discussion_id)
    if discussion is None:
        raise HTTPException(status_code=404, detail=f"Unknown discussion: {discussion_id}")
    from ..models.lms import DiscussionPost
    post_id = f"post_{len(state.discussion_posts) + 1}"
    now = datetime.now(timezone.utc)
    post = DiscussionPost(
        id=post_id,
        discussion_id=discussion_id,
        author_id=state.student.id,
        author_name=state.student.name,
        body=body.body,
        timestamp=now,
    )
    state.discussion_posts.append(post)
    state.audit_log.append(
        AuditEntry(
            action="lms.discussion.post",
            payload={"discussion_id": discussion_id, "post_id": post_id},
            summary=f"Posted in discussion {discussion.title}",
        )
    )
    state.touch()
    return {"post": post.model_dump(mode="json")}


@router.post("/discussions/{discussion_id}/posts/{post_id}/reply")
def reply_to_post(
    discussion_id: str,
    post_id: str,
    body: ReplyPostRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    discussion = state.get_discussion(discussion_id)
    if discussion is None:
        raise HTTPException(status_code=404, detail=f"Unknown discussion: {discussion_id}")
    parent = next((p for p in state.discussion_posts if p.id == post_id), None)
    if parent is None:
        raise HTTPException(status_code=404, detail=f"Unknown post: {post_id}")
    from ..models.lms import DiscussionPost
    reply_id = f"post_{len(state.discussion_posts) + 1}"
    now = datetime.now(timezone.utc)
    reply = DiscussionPost(
        id=reply_id,
        discussion_id=discussion_id,
        author_id=state.student.id,
        author_name=state.student.name,
        body=body.body,
        parent_post_id=post_id,
        timestamp=now,
    )
    state.discussion_posts.append(reply)
    state.audit_log.append(
        AuditEntry(
            action="lms.discussion.reply",
            payload={"discussion_id": discussion_id, "parent_post_id": post_id, "reply_id": reply_id},
            summary=f"Replied to post in discussion {discussion.title}",
        )
    )
    state.touch()
    return {"post": reply.model_dump(mode="json")}


@router.put("/discussions/{discussion_id}/posts/{post_id}")
def update_post(
    discussion_id: str,
    post_id: str,
    body: UpdatePostRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    post = next((p for p in state.discussion_posts if p.id == post_id and p.discussion_id == discussion_id), None)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Unknown post: {post_id}")
    if post.author_id != state.student.id:
        raise HTTPException(status_code=403, detail="Cannot edit another student's post")
    post.body = body.body
    post.updated_at = datetime.now(timezone.utc)
    state.audit_log.append(
        AuditEntry(
            action="lms.discussion.post.update",
            payload={"discussion_id": discussion_id, "post_id": post_id},
            summary=f"Updated post {post_id} in discussion",
        )
    )
    state.touch()
    return {"post": post.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Peer Reviews
# ---------------------------------------------------------------------------

@router.get("/peer-reviews")
def list_peer_reviews(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    reviews = [r for r in state.peer_reviews if r.reviewer_student_id == state.student.id]
    return {"items": [r.model_dump(mode="json") for r in reviews]}


@router.get("/peer-reviews/{review_id}")
def get_peer_review(
    review_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    review = state.get_peer_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Unknown peer review: {review_id}")
    return {"peer_review": review.model_dump(mode="json")}


@router.post("/peer-reviews/{review_id}/submit")
def submit_peer_review(
    review_id: str,
    body: SubmitPeerReviewRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    review = state.get_peer_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Unknown peer review: {review_id}")
    if review.status == "submitted":
        raise HTTPException(status_code=422, detail="Peer review already submitted")
    review.rubric_scores = _sanitise_peer_review_scores(review, body.rubric_scores)
    review.comments = body.comments
    review.status = "submitted"
    state.audit_log.append(
        AuditEntry(
            action="lms.peer_review.submit",
            payload={"review_id": review_id},
            summary=f"Submitted peer review {review_id}",
        )
    )
    state.touch()
    return {"peer_review": review.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Grades
# ---------------------------------------------------------------------------

@router.get("/courses/{course_id}/grades")
def get_course_grades(
    course_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    course = state.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"Unknown course: {course_id}")
    grades = state.get_grades_for_course(course_id)
    weighted_score = state.weighted_score_for_course(course_id)
    category_scores: dict[str, str | None] = {}
    for cat_name in course.syllabus.grading_policy:
        cat_score = state.category_score(course_id, cat_name)
        category_scores[cat_name] = str(cat_score) if cat_score is not None else None
    dropped_ids = {
        dropped.id
        for cat_name in course.syllabus.grading_policy
        for dropped in state.dropped_grades_for_category(course_id, cat_name)
    }
    grade_rows: list[dict[str, Any]] = []
    for grade in grades:
        row = grade.model_dump(mode="json")
        row["is_dropped"] = grade.id in dropped_ids
        grade_rows.append(row)
    return {
        "course_id": course_id,
        "course_code": course.course_code,
        "weighted_score": str(weighted_score) if weighted_score is not None else None,
        "category_scores": category_scores,
        "grades": grade_rows,
    }


@router.get("/grades/{assignment_id}")
def get_assignment_grade(
    assignment_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    assignment = state.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail=f"Unknown assignment: {assignment_id}")
    grade = next((g for g in state.grades if g.assignment_id == assignment_id), None)
    return {
        "assignment_id": assignment_id,
        "assignment_title": assignment.title,
        "score": str(assignment.score) if assignment.score is not None else None,
        "points_possible": str(assignment.points_possible),
        "feedback": assignment.feedback,
        "submission_status": assignment.submission_status,
        "grade": grade.model_dump(mode="json") if grade is not None else None,
    }


@router.post("/courses/{course_id}/grades/what-if")
def what_if_grades(
    course_id: str,
    body: WhatIfRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    course = state.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"Unknown course: {course_id}")

    # Apply hypothetical scores temporarily to both assignment and grade records.
    original_assignment_scores: dict[str, tuple[Decimal | None, str]] = {}
    original_grade_scores: dict[str, tuple[Decimal | None, bool, Decimal]] = {}
    temp_grade_ids: set[str] = set()
    enrollment = state.get_enrollment_for_course(course_id)

    for assign_id, score_str in body.hypothetical_scores.items():
        assignment = state.get_assignment(assign_id)
        if assignment is None or assignment.course_id != course_id:
            continue

        try:
            score = Decimal(score_str)
        except Exception:
            continue
        original_assignment_scores[assign_id] = (assignment.score, assignment.submission_status)
        assignment.score = score
        if assignment.submission_status == "not_submitted":
            assignment.submission_status = "submitted"

        grade = next((g for g in state.grades if g.assignment_id == assign_id and g.course_id == course_id), None)
        if grade is not None:
            original_grade_scores[grade.id] = (grade.score, grade.is_dropped, grade.late_penalty_applied)
            grade.score = score
        elif enrollment is not None:
            base_grade_id = f"tmp_what_if_{assign_id}"
            grade_id = base_grade_id
            while any(g.id == grade_id for g in state.grades):
                grade_id = f"{base_grade_id}_{len(temp_grade_ids) + 1}"
            temp_grade = Grade(
                id=grade_id,
                enrollment_id=enrollment.id,
                course_id=course_id,
                assignment_id=assign_id,
                score=score,
                points_possible=assignment.points_possible,
                weight_category=assignment.weight_category,
            )
            state.grades.append(temp_grade)
            temp_grade_ids.add(grade_id)

    weighted = state.weighted_score_for_course(course_id)

    # Restore originals
    for assign_id, (orig_score, orig_status) in original_assignment_scores.items():
        assignment = state.get_assignment(assign_id)
        if assignment is not None:
            assignment.score = orig_score
            assignment.submission_status = orig_status

    for grade_id, orig_score in original_grade_scores.items():
        grade = state.get_grade(grade_id)
        if grade is not None:
            grade.score, grade.is_dropped, grade.late_penalty_applied = orig_score

    if temp_grade_ids:
        state.grades = [g for g in state.grades if g.id not in temp_grade_ids]

    return {
        "course_id": course_id,
        "what_if_weighted_score": str(weighted) if weighted is not None else None,
        "hypothetical_scores": body.hypothetical_scores,
    }


@router.get("/student")
def get_student(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    current_course_ids = {
        e.course_id
        for e in state.enrollments
        if e.status == "enrolled"
    }
    current_credits = sum(
        course.credits
        for course in state.courses
        if course.id in current_course_ids
    )
    return {
        "student": state.student.model_dump(mode="json"),
        "enrolled_course_count": len(current_course_ids),
        "current_enrolled_credits": current_credits,
    }


@router.get("/transcript")
def get_transcript(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    transcript_rows: list[dict[str, Any]] = []
    for e in state.enrollments:
        course = state.get_course(e.course_id)
        if not course:
            continue
        if e.status != "completed" and e.final_grade is None and e.final_score is None:
            continue
        transcript_rows.append({
            "course_id": e.course_id,
            "course_code": course.course_code,
            "course_title": course.title,
            "final_grade": e.final_grade,
            "final_score": str(e.final_score) if e.final_score is not None else None,
            "credits": course.credits,
            "status": e.status,
        })

    completed_credits = sum(row["credits"] for row in transcript_rows if row["status"] == "completed")
    return {
        "student_id": state.student.student_id,
        "transcript": transcript_rows,
        "completed_credits": completed_credits,
    }


@router.get("/gpa")
def get_gpa(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    completed = [e for e in state.enrollments if e.status == "completed"]
    total_credits = 0
    for e in completed:
        course = state.get_course(e.course_id)
        if course is not None:
            total_credits += course.credits

    return {
        "student_gpa": str(state.student.gpa),
        "completed_course_count": len(completed),
        "completed_credits": total_credits,
    }


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------

@router.get("/announcements")
def list_announcements(
    session_id: str = Query(...),
    course_id: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    if course_id:
        announcements = state.announcements_for_course(course_id)
    else:
        announcements = sorted(state.announcements, key=lambda a: a.posted_at, reverse=True)
    return {"items": [a.model_dump(mode="json") for a in announcements]}


@router.post("/announcements/{announcement_id}/read")
def mark_announcement_read(
    announcement_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    announcement = state.get_announcement(announcement_id)
    if announcement is None:
        raise HTTPException(status_code=404, detail=f"Unknown announcement: {announcement_id}")
    announcement.is_read = True
    state.audit_log.append(
        AuditEntry(
            action="lms.announcement.read",
            payload={"announcement_id": announcement_id},
            summary=f"Marked announcement '{announcement.title}' as read",
        )
    )
    state.touch()
    return {"announcement": announcement.model_dump(mode="json")}


@router.post("/announcements/mark_all_read")
def mark_all_announcements_read(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    count = 0
    for ann in state.announcements:
        if not ann.is_read:
            ann.is_read = True
            count += 1
    state.audit_log.append(
        AuditEntry(
            action="lms.announcements.mark_all_read",
            payload={"count": count},
            summary=f"Marked {count} announcements as read",
        )
    )
    state.touch()
    return {"marked_read": count}


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

@router.get("/calendar")
def get_calendar(
    session_id: str = Query(...),
    course_id: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    events = state.calendar_events
    if course_id:
        events = [e for e in events if e.course_id == course_id]
    return {"items": [e.model_dump(mode="json") for e in events]}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.get("/messages")
def list_messages(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, session_id)
    return {"items": list(state.sent_messages)}


@router.post("/messages/send")
def send_message(
    body: SendMessageRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _lms_state(session_manager, body.session_id)
    now = datetime.now(timezone.utc)
    message = {
        "to": body.to,
        "subject": body.subject,
        "body": body.body,
        "sent_at": now.isoformat(),
        "from": state.student.email,
    }
    state.sent_messages.append(message)
    state.audit_log.append(
        AuditEntry(
            action="lms.message.send",
            payload={"to": body.to, "subject": body.subject},
            summary=f"Sent message to {body.to}: {body.subject}",
        )
    )
    state.touch()
    return {"message": message, "sent": True}
