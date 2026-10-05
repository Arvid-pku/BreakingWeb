"""Full API routes for the Patient Portal environment.

Provides ~36 endpoints covering session lifecycle, appointments, messages,
medications, labs, referrals, claims, profile, immunizations, and providers.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...tasks._evaluator import evaluate as unified_evaluate
from ...tasks._registry import get_task
from ..models.base import AuditEntry, utc_now
from ..models.patient_portal import (
    Appointment,
    ClinicalMessage,
    InsuranceClaim,
    PatientPortalState,
    Pharmacy,
    Referral,
)
from ..security import (
    build_public_session_summary,
    has_controller_access,
    require_evaluation_access,
)
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/patient_portal", tags=["patient_portal"])


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


class CreateAppointmentRequest(SessionScopedRequest):
    provider_id: str
    slot_datetime: str
    type: str
    reason: str = ""
    notes: str | None = None
    linked_referral_id: str | None = None


class RescheduleAppointmentRequest(SessionScopedRequest):
    new_slot_datetime: str
    new_type: str | None = None


class CancelAppointmentRequest(SessionScopedRequest):
    # Optional cancellation reason. The default-None preserves backward
    # compatibility with callers that POST the legacy session-only payload.
    reason: str | None = None


class SendMessageRequest(SessionScopedRequest):
    provider_id: str
    subject: str
    body: str
    category: str = "clinical"
    linked_entity_id: str | None = None
    linked_entity_type: str | None = None
    is_urgent: bool = False


class ReplyMessageRequest(SessionScopedRequest):
    body: str
    is_urgent: bool = False


class TransferPrescriptionRequest(SessionScopedRequest):
    pharmacy_id: str


class AppealClaimRequest(SessionScopedRequest):
    reason: str
    evidence_references: list[str] = Field(default_factory=list)


class PayClaimRequest(SessionScopedRequest):
    pass


class SubmitClaimRequest(SessionScopedRequest):
    appointment_id: str
    procedure_code: str
    diagnosis_code: str


class UpdateDemographicsRequest(SessionScopedRequest):
    phone: str | None = None
    email: str | None = None
    emergency_contact: dict | None = None


class UpdateInsuranceRequest(SessionScopedRequest):
    plan_name: str | None = None
    member_id: str | None = None
    group_number: str | None = None


class AddPharmacyRequest(SessionScopedRequest):
    name: str
    address: str
    phone: str
    is_mail_order: bool = False


class RequestReferralRequest(SessionScopedRequest):
    to_specialty: str
    reason: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured on app.state")
    return session_manager


def _pp_state(session_manager: SessionManager, session_id: str) -> PatientPortalState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, PatientPortalState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not a Patient Portal session")
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
    if task.env_id != "patient_portal":
        raise HTTPException(status_code=404, detail=f"Unknown Patient Portal task_id: {body.task_id}")

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

    session_id, resolved_targets, actual_seed = session_manager.create_session("patient_portal", body.task_id, body.seed)
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


@router.get("/degradation/{session_id}")
def get_client_degradation(session_id: str) -> dict[str, Any]:
    from ...injector.middleware import get_client_injections
    injections = get_client_injections(session_id)
    return {"session_id": session_id, "client_injections": injections}


@router.get("/variants")
def list_variants() -> list[dict[str, Any]]:
    from pathlib import Path
    import yaml

    variants_dir = Path(__file__).parent.parent.parent / "injector" / "variants"
    results: list[dict[str, Any]] = []
    if variants_dir.is_dir():
        for f in sorted(variants_dir.glob("pp_*.yaml")):
            try:
                data = yaml.safe_load(f.read_text())
                results.append({
                    "filename": f.name,
                    "variant_id": data.get("variant_id", f.stem),
                    "base_task_id": data.get("base_task_id", ""),
                    "target_primitive": data.get("target_primitive", ""),
                    "description": data.get("description", ""),
                    "source": "yaml",
                })
            except Exception:
                continue
    return results


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


# ---------------------------------------------------------------------------
# Trajectory
# ---------------------------------------------------------------------------

class TrajectorySubmission(BaseModel):
    session_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)


@router.post("/trajectory")
def save_gold_trajectory(
    body: TrajectorySubmission,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    """Save a human gold trajectory for a passed task."""
    import json as _json
    from pathlib import Path
    from datetime import datetime, timezone

    is_gold = bool(body.evaluation.get("success"))

    try:
        state = session_manager.get(body.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    task = get_task(state.task_id)
    instruction = render_template(
        task.instruction_template or task.instruction or "", state.resolved_targets
    )

    record = {
        "type": "gold_trajectory" if is_gold else "trajectory",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "recorder": "human",
        "task_id": state.task_id,
        "env_id": state.env_id,
        "title": task.title,
        "difficulty": task.difficulty,
        "primitives": task.primary_primitives,
        "instruction": instruction,
        "settings": {
            "session_id": body.session_id,
            "seed": state.seed,
            "degradation": state.degradation,
            "resolved_targets": state.resolved_targets,
        },
        "evaluation": body.evaluation,
        "events": body.events,
        "audit_log": [entry.model_dump() for entry in state.audit_log],
        "total_events": len(body.events),
        "total_audit_entries": len(state.audit_log),
    }

    base_dir = Path(__file__).parent.parent.parent
    if is_gold:
        save_dir = base_dir / "gold_trajectories"
    else:
        save_dir = base_dir / "trajectories"
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = "gold_" if is_gold else ""
    filename = f"{prefix}{state.task_id}_{timestamp}.json"
    path = save_dir / filename

    with open(path, "w") as f:
        _json.dump(record, f, indent=2, default=str)

    return {"saved": True, "gold": is_gold, "path": str(path), "filename": filename, "events": len(body.events)}


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

@router.get("/appointments")
def list_appointments(
    session_id: str = Query(...),
    status: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    appointments = list(state.appointments)
    if status is not None:
        appointments = [a for a in appointments if a.status == status]
    return {"items": [a.model_dump(mode="json") for a in appointments]}


@router.get("/appointments/available-slots")
def get_available_slots(
    session_id: str = Query(...),
    provider_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    provider = state.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"items": [s.model_dump(mode="json") for s in provider.available_slots]}


@router.get("/appointments/{apt_id}")
def get_appointment(
    apt_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    apt = state.get_appointment(apt_id)
    if apt is None:
        raise HTTPException(status_code=404, detail=f"Appointment {apt_id} not found")
    return apt.model_dump(mode="json")


@router.post("/appointments/create")
def create_appointment(
    body: CreateAppointmentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    provider = state.get_provider(body.provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Prerequisite chain for specialist visits
    # Bypass referral requirement for immunization/vaccine appointments and
    # echocardiogram/echo diagnostic procedures (ordered directly by cardiologist)
    _reason_lower = (body.reason or "").lower()
    _is_immunization_appt = any(
        kw in _reason_lower
        for kw in ("vaccine", "vaccination", "immunization", "immunisation", "booster", "tdap", "flu shot")
    )
    _is_echo_appt = any(
        kw in _reason_lower
        for kw in ("echocardiogram", "echo", "cardiac echo", "cardiac ultrasound")
    )
    # Phlebotomy / outpatient lab also bypasses the referral chain — patients
    # routinely walk into the lab with a standing order or self-pay request,
    # no referral needed.
    if provider.specialty not in ("pcp", "billing", "admin", "phlebotomy") and not _is_immunization_appt and not _is_echo_appt:
        approved_referral = next(
            (r for r in state.referrals
             if r.to_specialty == provider.specialty and r.status == "approved"),
            None,
        )
        if approved_referral is None:
            raise HTTPException(
                status_code=422,
                detail=f"No approved referral exists for {provider.specialty}. "
                       f"Please obtain a referral from your PCP first.",
            )
        if approved_referral.prior_auth_required and approved_referral.prior_auth_status != "approved":
            raise HTTPException(
                status_code=422,
                detail=f"Insurance pre-authorization is {approved_referral.prior_auth_status}, "
                       f"not approved. Pre-auth must be approved before scheduling.",
            )

    # Verify slot availability
    slot_dt_str = body.slot_datetime
    matching_slot = None
    for slot in provider.available_slots:
        if slot.datetime.isoformat() == slot_dt_str:
            matching_slot = slot
            break
    if matching_slot is None:
        # Try parsing the provided datetime for a looser match
        try:
            parsed_dt = datetime.fromisoformat(slot_dt_str)
            for slot in provider.available_slots:
                if slot.datetime == parsed_dt:
                    matching_slot = slot
                    break
        except (ValueError, TypeError):
            pass
    if matching_slot is None:
        raise HTTPException(
            status_code=422,
            detail=f"No available slot at {slot_dt_str} for provider {provider.name}",
        )

    # Consume the slot
    provider.available_slots.remove(matching_slot)

    # Create the appointment. If the provider's specialty appears in
    # ``state.auto_confirm_specialties`` (opt-in via seed builder), the
    # appointment lands as awaiting confirmation — the agent must call
    # POST /appointments/{id}/confirm to finish the workflow.
    auto_confirm = provider.specialty in (state.auto_confirm_specialties or [])
    apt_id = state._gen_id("apt")
    apt = Appointment(
        id=apt_id,
        provider_id=body.provider_id,
        datetime=matching_slot.datetime,
        type=body.type or matching_slot.type,
        status="scheduled",
        reason=body.reason,
        notes=body.notes or "",
        linked_referral_id=body.linked_referral_id,
        booked_at=utc_now(),
        location="Main Campus" if (body.type or matching_slot.type) == "in-person" else "Telehealth",
        requires_confirmation=auto_confirm,
        confirmation_state="pending" if auto_confirm else "not_required",
    )
    state.appointments.append(apt)

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.appointment.create",
        {"provider_id": body.provider_id, "slot_datetime": slot_dt_str, "type": body.type},
        lambda s: apt,
    )
    return result.model_dump(mode="json")


@router.post("/appointments/{apt_id}/cancel")
def cancel_appointment(
    apt_id: str,
    body: CancelAppointmentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    apt = state.get_appointment(apt_id)
    if apt is None:
        raise HTTPException(status_code=404, detail=f"Appointment {apt_id} not found")
    if apt.status != "scheduled":
        raise HTTPException(status_code=422, detail=f"Appointment is {apt.status}, not scheduled")

    reason = (body.reason or "").strip() or None

    def _do_cancel(s: PatientPortalState) -> Appointment:
        apt_obj = s.get_appointment(apt_id)
        apt_obj.status = "cancelled"
        if reason:
            apt_obj.cancellation_reason = reason
        return apt_obj

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.appointment.cancel",
        {"appointment_id": apt_id, "reason": reason},
        _do_cancel,
    )
    return result.model_dump(mode="json")


@router.post("/appointments/{apt_id}/confirm")
def confirm_appointment(
    apt_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    """Transition a pending-confirmation appointment to confirmed.

    Only valid when ``requires_confirmation`` is True and
    ``confirmation_state`` is ``"pending"``. The seed builder marks
    high-stakes appointments (specialist visits, procedures) as requiring
    confirmation so the agent must complete a two-step workflow rather than
    a single book-and-forget action.
    """
    state = _pp_state(session_manager, body.session_id)
    apt = state.get_appointment(apt_id)
    if apt is None:
        raise HTTPException(status_code=404, detail=f"Appointment {apt_id} not found")
    if not apt.requires_confirmation:
        raise HTTPException(status_code=422, detail="Appointment does not require confirmation")
    if apt.confirmation_state == "confirmed":
        raise HTTPException(status_code=422, detail="Appointment already confirmed")
    if apt.status != "scheduled":
        raise HTTPException(status_code=422, detail=f"Appointment is {apt.status}, not scheduled")

    def _do_confirm(s: PatientPortalState) -> Appointment:
        apt_obj = s.get_appointment(apt_id)
        apt_obj.confirmation_state = "confirmed"
        apt_obj.confirmed_at = utc_now()
        return apt_obj

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.appointment.confirm",
        {"appointment_id": apt_id},
        _do_confirm,
    )
    return result.model_dump(mode="json")


@router.post("/appointments/{apt_id}/reschedule")
def reschedule_appointment(
    apt_id: str,
    body: RescheduleAppointmentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    apt = state.get_appointment(apt_id)
    if apt is None:
        raise HTTPException(status_code=404, detail=f"Appointment {apt_id} not found")
    if apt.status != "scheduled":
        raise HTTPException(status_code=422, detail=f"Appointment is {apt.status}, not scheduled")

    provider = state.get_provider(apt.provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Find the new slot
    new_dt_str = body.new_slot_datetime
    matching_slot = None
    try:
        parsed_dt = datetime.fromisoformat(new_dt_str)
        for slot in provider.available_slots:
            if slot.datetime == parsed_dt or slot.datetime.isoformat() == new_dt_str:
                matching_slot = slot
                break
    except (ValueError, TypeError):
        for slot in provider.available_slots:
            if slot.datetime.isoformat() == new_dt_str:
                matching_slot = slot
                break

    if matching_slot is None:
        raise HTTPException(
            status_code=422,
            detail=f"No available slot at {new_dt_str} for provider {provider.name}",
        )

    # Consume new slot
    provider.available_slots.remove(matching_slot)

    def _do_reschedule(s: PatientPortalState) -> Appointment:
        apt_obj = s.get_appointment(apt_id)
        apt_obj.datetime = matching_slot.datetime
        if body.new_type:
            apt_obj.type = body.new_type
        apt_obj.location = "Main Campus" if apt_obj.type == "in-person" else "Telehealth"
        return apt_obj

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.appointment.reschedule",
        {"appointment_id": apt_id, "new_slot_datetime": new_dt_str},
        _do_reschedule,
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.get("/messages")
def list_messages(
    session_id: str = Query(...),
    category: str | None = Query(None),
    unread: bool | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    messages = list(state.messages)
    if category is not None:
        messages = [m for m in messages if m.category == category]
    if unread is not None:
        messages = [m for m in messages if m.is_read is (not unread)]
    return {"items": [m.model_dump(mode="json") for m in messages]}


@router.get("/messages/thread/{thread_id}")
def get_thread(
    thread_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    thread_msgs = state.messages_in_thread(thread_id)
    return {"items": [m.model_dump(mode="json") for m in thread_msgs]}


@router.post("/messages/send")
def send_message(
    body: SendMessageRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    provider = state.get_provider(body.provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    msg_id = state._gen_id("msg")
    thread_id = f"thread_{msg_id}"
    msg = ClinicalMessage(
        id=msg_id,
        from_type="patient",
        provider_id=body.provider_id,
        subject=body.subject,
        body=body.body,
        thread_id=thread_id,
        category=body.category,
        is_read=True,
        linked_entity_id=body.linked_entity_id,
        linked_entity_type=body.linked_entity_type,
        is_urgent=body.is_urgent,
    )
    state.messages.append(msg)

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.message.send",
        {"provider_id": body.provider_id, "subject": body.subject, "category": body.category},
        lambda s: msg,
    )
    return result.model_dump(mode="json")


@router.post("/messages/{msg_id}/reply")
def reply_to_message(
    msg_id: str,
    body: ReplyMessageRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    original = state.get_message(msg_id)
    if original is None:
        raise HTTPException(status_code=404, detail=f"Message {msg_id} not found")

    reply_id = state._gen_id("msg")
    reply = ClinicalMessage(
        id=reply_id,
        from_type="patient",
        provider_id=original.provider_id,
        subject=f"Re: {original.subject}",
        body=body.body,
        thread_id=original.thread_id,
        category=original.category,
        is_read=True,
        is_urgent=body.is_urgent,
    )
    state.messages.append(reply)

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.message.reply",
        {"original_msg_id": msg_id, "thread_id": original.thread_id},
        lambda s: reply,
    )
    return result.model_dump(mode="json")


@router.post("/messages/{msg_id}/read")
def mark_message_read(
    msg_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)

    def _do_read(s: PatientPortalState) -> ClinicalMessage:
        msg = s.get_message(msg_id)
        if msg is None:
            raise KeyError(f"Message {msg_id} not found")
        msg.is_read = True
        return msg

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.message.read",
        {"message_id": msg_id},
        _do_read,
    )
    return result.model_dump(mode="json")


@router.post("/messages/mark-all-read")
def mark_all_messages_read(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    def _do_mark_all(s: PatientPortalState) -> int:
        count = 0
        for msg in s.messages:
            if not msg.is_read:
                msg.is_read = True
                count += 1
        return count

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.message.mark_all_read",
        {},
        _do_mark_all,
    )
    return {"count": result}


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------

@router.get("/medications")
def list_medications(
    session_id: str = Query(...),
    status: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    prescriptions = list(state.prescriptions)
    if status is not None:
        prescriptions = [r for r in prescriptions if r.status == status]
    return {"items": [r.model_dump(mode="json") for r in prescriptions]}


@router.post("/medications/{rx_id}/refill")
def refill_medication(
    rx_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    rx = state.get_prescription(rx_id)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    if rx.status != "active":
        raise HTTPException(status_code=422, detail=f"Prescription is {rx.status}, not active")
    if rx.refills_remaining <= 0:
        raise HTTPException(status_code=422, detail="No refills remaining. Please request a renewal.")

    def _do_refill(s: PatientPortalState):
        r = s.get_prescription(rx_id)
        r.refills_remaining -= 1
        r.last_filled = utc_now()
        return r

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.medication.refill",
        {"prescription_id": rx_id},
        _do_refill,
    )
    return result.model_dump(mode="json")


@router.post("/medications/{rx_id}/renewal")
def request_renewal(
    rx_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    rx = state.get_prescription(rx_id)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    if rx.status not in ("active", "expired"):
        raise HTTPException(status_code=422, detail=f"Prescription is {rx.status}, cannot renew")

    # Auto-create a message to the prescribing provider
    msg_id = state._gen_id("msg")
    thread_id = f"thread_{msg_id}"
    msg = ClinicalMessage(
        id=msg_id,
        from_type="patient",
        provider_id=rx.provider_id,
        subject=f"Prescription renewal request: {rx.medication}",
        body=f"I would like to request a renewal for {rx.medication} ({rx.dosage}, {rx.frequency}).",
        thread_id=thread_id,
        category="rx_renewal",
        is_read=True,
        linked_entity_id=rx_id,
        linked_entity_type="prescription",
    )
    state.messages.append(msg)

    def _do_renewal(s: PatientPortalState):
        r = s.get_prescription(rx_id)
        r.status = "pending_renewal"
        return r

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.medication.renewal",
        {"prescription_id": rx_id, "message_id": msg_id},
        _do_renewal,
    )
    return result.model_dump(mode="json")


@router.post("/medications/{rx_id}/transfer")
def transfer_medication(
    rx_id: str,
    body: TransferPrescriptionRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    rx = state.get_prescription(rx_id)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    if rx.status != "active":
        raise HTTPException(status_code=422, detail=f"Prescription is {rx.status}, not active")
    pharmacy = state.get_pharmacy(body.pharmacy_id)
    if pharmacy is None:
        raise HTTPException(status_code=404, detail=f"Pharmacy {body.pharmacy_id} not found")

    def _do_transfer(s: PatientPortalState):
        r = s.get_prescription(rx_id)
        r.pharmacy_id = body.pharmacy_id
        return r

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.medication.transfer",
        {"prescription_id": rx_id, "pharmacy_id": body.pharmacy_id},
        _do_transfer,
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Labs
# ---------------------------------------------------------------------------

@router.get("/labs")
def list_labs(
    session_id: str = Query(...),
    flag: str | None = Query(None),
    status: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    labs = list(state.lab_results)
    if flag is not None:
        labs = [lab for lab in labs if lab.flag == flag]
    if status is not None:
        labs = [lab for lab in labs if lab.status == status]
    return {"items": [lab.model_dump(mode="json") for lab in labs]}


@router.get("/labs/{lab_id}")
def get_lab(
    lab_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    lab = state.get_lab(lab_id)
    if lab is None:
        raise HTTPException(status_code=404, detail=f"Lab result {lab_id} not found")
    return lab.model_dump(mode="json")


@router.get("/labs/trend/{test_name}")
def get_lab_trend(
    test_name: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    matching = [lab for lab in state.lab_results if lab.test_name == test_name]
    matching.sort(key=lambda lab: lab.collected_at)
    return {"test_name": test_name, "items": [lab.model_dump(mode="json") for lab in matching]}


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------

@router.get("/referrals")
def list_referrals(
    session_id: str = Query(...),
    status: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    referrals = list(state.referrals)
    if status is not None:
        referrals = [r for r in referrals if r.status == status]
    return {"items": [r.model_dump(mode="json") for r in referrals]}


@router.get("/referrals/{ref_id}")
def get_referral(
    ref_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    ref = state.get_referral(ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail=f"Referral {ref_id} not found")
    return ref.model_dump(mode="json")


@router.post("/referrals/request")
def request_referral(
    body: RequestReferralRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    pcp_id = state.patient.pcp_id

    ref_id = state._gen_id("ref")
    ref = Referral(
        id=ref_id,
        from_provider_id=pcp_id,
        to_specialty=body.to_specialty,
        reason=body.reason,
        status="requested",
        expires_at=utc_now() + __import__("datetime").timedelta(days=90),
    )
    state.referrals.append(ref)

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.referral.request",
        {"to_specialty": body.to_specialty, "reason": body.reason},
        lambda s: ref,
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

@router.get("/claims")
def list_claims(
    session_id: str = Query(...),
    status: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    claims = list(state.claims)
    if status is not None:
        claims = [c for c in claims if c.status == status]
    return {"items": [c.model_dump(mode="json") for c in claims]}


@router.get("/claims/{clm_id}")
def get_claim(
    clm_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    claim = state.get_claim(clm_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {clm_id} not found")
    return claim.model_dump(mode="json")


@router.post("/claims/submit")
def submit_claim(
    body: SubmitClaimRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)

    # Validate appointment exists and is completed
    apt = state.get_appointment(body.appointment_id)
    if apt is None:
        raise HTTPException(status_code=404, detail=f"Appointment {body.appointment_id} not found")
    if apt.status != "completed":
        raise HTTPException(status_code=422, detail=f"Appointment is {apt.status}, must be completed to submit a claim")

    clm_id = state._gen_id("clm")
    amount_billed = Decimal(str(__import__("random").Random(hash(clm_id)).randint(150, 2500)))
    claim = InsuranceClaim(
        id=clm_id,
        service_date=apt.datetime.date(),
        provider_id=apt.provider_id,
        appointment_id=body.appointment_id,
        procedure_code=body.procedure_code,
        diagnosis_code=body.diagnosis_code,
        status="submitted",
        amount_billed=amount_billed,
        appeal_deadline=utc_now() + __import__("datetime").timedelta(days=180),
    )
    state.claims.append(claim)

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.claim.submit",
        {"appointment_id": body.appointment_id, "procedure_code": body.procedure_code},
        lambda s: claim,
    )
    return result.model_dump(mode="json")


@router.post("/claims/{clm_id}/appeal")
def appeal_claim(
    clm_id: str,
    body: AppealClaimRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    claim = state.get_claim(clm_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {clm_id} not found")
    if claim.status != "denied":
        raise HTTPException(status_code=422, detail=f"Claim is {claim.status}, only denied claims can be appealed")
    if not claim.eob_available:
        raise HTTPException(status_code=422, detail="EOB is not yet available for this claim")
    if claim.appeal_deadline < utc_now():
        raise HTTPException(status_code=422, detail="Appeal deadline has passed")

    def _do_appeal(s: PatientPortalState) -> InsuranceClaim:
        c = s.get_claim(clm_id)
        c.status = "appealed"
        return c

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.claim.appeal",
        {"claim_id": clm_id, "reason": body.reason},
        _do_appeal,
    )
    return result.model_dump(mode="json")


@router.post("/claims/{clm_id}/pay")
def pay_claim(
    clm_id: str,
    body: PayClaimRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    claim = state.get_claim(clm_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {clm_id} not found")
    if claim.patient_responsibility <= 0:
        raise HTTPException(status_code=422, detail="No patient responsibility to pay")

    def _do_pay(s: PatientPortalState) -> InsuranceClaim:
        c = s.get_claim(clm_id)
        c.patient_responsibility = Decimal("0")
        return c

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.claim.pay",
        {"claim_id": clm_id},
        _do_pay,
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/profile")
def get_profile(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    profile = state.patient.model_dump(mode="json")
    profile["default_pharmacy"] = None
    default_ph = state.default_pharmacy()
    if default_ph:
        profile["default_pharmacy"] = default_ph.model_dump(mode="json")
    return profile


@router.post("/profile/demographics")
def update_demographics(
    body: UpdateDemographicsRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    def _do_update(s: PatientPortalState):
        if body.phone is not None:
            s.patient.phone = body.phone
        if body.email is not None:
            s.patient.email = body.email
        if body.emergency_contact is not None:
            from ..models.patient_portal import EmergencyContact
            s.patient.emergency_contact = EmergencyContact(**body.emergency_contact)
        return s.patient

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.profile.demographics",
        {k: v for k, v in body.model_dump(exclude={"session_id"}).items() if v is not None},
        _do_update,
    )
    return result.model_dump(mode="json")


@router.post("/profile/insurance")
def update_insurance(
    body: UpdateInsuranceRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    def _do_update(s: PatientPortalState):
        ins = s.patient.insurance_plan
        if body.plan_name is not None:
            ins.plan_name = body.plan_name
        if body.member_id is not None:
            ins.member_id = body.member_id
        if body.group_number is not None:
            ins.group_number = body.group_number
        return s.patient

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.profile.insurance",
        {k: v for k, v in body.model_dump(exclude={"session_id"}).items() if v is not None},
        _do_update,
    )
    return result.model_dump(mode="json")


@router.post("/profile/pharmacy/add")
def add_pharmacy(
    body: AddPharmacyRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)

    pharm_id = state._gen_id("pharm")
    pharm = Pharmacy(
        id=pharm_id,
        name=body.name,
        address=body.address,
        phone=body.phone,
        is_default=False,
        is_mail_order=body.is_mail_order,
    )
    state.pharmacies.append(pharm)
    state.patient.pharmacy_ids.append(pharm_id)

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.pharmacy.add",
        {"name": body.name, "pharmacy_id": pharm_id},
        lambda s: pharm,
    )
    return result.model_dump(mode="json")


@router.post("/profile/pharmacy/{pharm_id}/set-default")
def set_default_pharmacy(
    pharm_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    target = state.get_pharmacy(pharm_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Pharmacy {pharm_id} not found")

    def _do_set_default(s: PatientPortalState) -> Pharmacy:
        for p in s.pharmacies:
            p.is_default = (p.id == pharm_id)
        return s.get_pharmacy(pharm_id)

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.pharmacy.set_default",
        {"pharmacy_id": pharm_id},
        _do_set_default,
    )
    return result.model_dump(mode="json")


@router.post("/profile/pharmacy/{pharm_id}/remove")
def remove_pharmacy(
    pharm_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, body.session_id)
    target = state.get_pharmacy(pharm_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Pharmacy {pharm_id} not found")
    if target.is_default:
        raise HTTPException(status_code=422, detail="Cannot remove the default pharmacy")

    def _do_remove(s: PatientPortalState) -> Pharmacy:
        p = s.get_pharmacy(pharm_id)
        s.pharmacies = [ph for ph in s.pharmacies if ph.id != pharm_id]
        if pharm_id in s.patient.pharmacy_ids:
            s.patient.pharmacy_ids.remove(pharm_id)
        return p

    result = _mutate(
        session_manager, body.session_id,
        "patient_portal.pharmacy.remove",
        {"pharmacy_id": pharm_id},
        _do_remove,
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Immunizations
# ---------------------------------------------------------------------------

@router.get("/immunizations")
def list_immunizations(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    return {"items": [i.model_dump(mode="json") for i in state.immunizations]}


# ---------------------------------------------------------------------------
# Pharmacies
# ---------------------------------------------------------------------------

@router.get("/pharmacies")
def list_pharmacies(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    return {"items": [p.model_dump(mode="json") for p in state.pharmacies]}


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@router.get("/providers")
def list_providers(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    return {"items": [p.model_dump(mode="json") for p in state.providers]}


@router.get("/providers/search")
def search_providers(
    session_id: str = Query(...),
    specialty: str | None = Query(None),
    accepting_new: bool | None = Query(None),
    slot_type: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _pp_state(session_manager, session_id)
    providers = list(state.providers)
    if specialty is not None:
        providers = [p for p in providers if p.specialty == specialty]
    if accepting_new is not None:
        providers = [p for p in providers if p.accepting_new is accepting_new]
    if slot_type is not None:
        providers = [p for p in providers if any(s.type == slot_type for s in p.available_slots)]
    return {"items": [p.model_dump(mode="json") for p in providers]}
