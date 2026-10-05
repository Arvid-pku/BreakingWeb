from __future__ import annotations

import random
import shlex
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...tasks._evaluator import evaluate as unified_evaluate
from ...tasks._registry import get_task
from ..models.base import AuditEntry
from ..models.gmail import Attachment, Contact, Email, FilterRule, GmailState
from ..security import (
    build_public_session_summary,
    has_controller_access,
    require_evaluation_access,
)
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/gmail", tags=["gmail"])


class SessionCreateRequest(BaseModel):
    task_id: str
    seed: int | None = None
    degradation: dict | None = None  # Optional seed/server injections to apply post-seed
    variant_filename: str | None = None  # Load degradation from injector/variants/<filename>


class SessionScopedRequest(BaseModel):
    session_id: str


class ReadEmailRequest(SessionScopedRequest):
    is_read: bool = True


class StarEmailRequest(SessionScopedRequest):
    is_starred: bool | None = None


class LabelEmailRequest(SessionScopedRequest):
    label: str
    action: Literal["add", "remove"] = "add"


class ForwardEmailRequest(SessionScopedRequest):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    body: str = ""


class AttachmentInput(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    kind: str = "file"


class SendEmailRequest(SessionScopedRequest):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    thread_id: str | None = None
    in_reply_to: str | None = None
    attachments: list[AttachmentInput] = Field(default_factory=list)


class CreateLabelRequest(SessionScopedRequest):
    name: str
    color: str = "#1a73e8"
    show_in_label_list: str = "show"
    show_in_message_list: str = "show"
    show_in_imap: bool = True


class UpdateLabelRequest(SessionScopedRequest):
    name: str | None = None
    show_in_label_list: str | None = None
    show_in_message_list: str | None = None
    show_in_imap: bool | None = None


class CreateFilterRequest(SessionScopedRequest):
    name: str
    query: str = ""
    from_addresses: list[str] = Field(default_factory=list)
    subject_keywords: list[str] = Field(default_factory=list)
    label_requirements: list[str] = Field(default_factory=list)
    has_attachment: bool | None = None
    add_labels: list[str] = Field(default_factory=list)
    archive: bool = False
    mark_read: bool = False
    forward_to: str | None = None
    star: bool = False
    never_spam: bool = False


class CreateContactRequest(SessionScopedRequest):
    name: str
    email: str
    company: str | None = None
    note: str | None = None
    is_vip: bool = False
    is_starred: bool = False
    last_contacted_at: datetime | None = None


class UpdateContactRequest(SessionScopedRequest):
    name: str | None = None
    email: str | None = None
    company: str | None = None
    note: str | None = None
    is_vip: bool | None = None
    is_starred: bool | None = None
    last_contacted_at: datetime | None = None


class UpdateSettingsRequest(SessionScopedRequest):
    signature: str | None = None
    forwarding_address: str | None = None
    display_density: str | None = None
    vacation_responder_enabled: bool | None = None
    vacation_responder_message: str | None = None
    auto_advance: str | None = None
    language: str | None = None
    input_tools_enabled: bool | None = None
    right_to_left: bool | None = None
    max_page_size: int | None = None
    undo_send_seconds: int | None = None
    default_reply_behavior: str | None = None
    hover_actions_enabled: bool | None = None
    send_and_archive: bool | None = None
    default_text_style: str | None = None


class EvaluateRequest(SessionScopedRequest):
    task_id: str | None = None
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured on app.state")
    return session_manager


def _gmail_state(session_manager: SessionManager, session_id: str) -> GmailState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, GmailState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not a Gmail session")
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


def _serialize_email(state: GmailState, email: Email) -> dict[str, Any]:
    payload = email.model_dump(mode="json")
    payload["thread_size"] = len(state.get_thread(email.thread_id))
    payload["snippet"] = email.snippet
    return payload


def _serialize_filter(rule: FilterRule) -> dict[str, Any]:
    return rule.model_dump(mode="json")


def _serialize_contact(contact: Contact) -> dict[str, Any]:
    return contact.model_dump(mode="json")


def _serialize_attachment(attachment: AttachmentInput) -> Attachment:
    return Attachment(
        id=f"client_attachment_{attachment.filename}",
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        kind=attachment.kind,
    )


def _parse_filter_query(query: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "from_addresses": [],
        "subject_keywords": [],
        "label_requirements": [],
        "has_attachment": None,
    }
    if not query:
        return parsed
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.upper() == "OR":
            index += 1
            continue
        lowered = token.lower()
        if ":" not in lowered:
            index += 1
            continue
        key, value = lowered.split(":", 1)
        if key == "from":
            raw_value = token.split(":", 1)[1]
            if raw_value.startswith("@"):
                parsed["from_addresses"].append(f"*{raw_value}")
            else:
                parsed["from_addresses"].append(raw_value if "@" in raw_value else f"*{raw_value}")
        elif key == "subject":
            subject_parts = [token.split(":", 1)[1]]
            lookahead = index + 1
            while lookahead < len(tokens):
                next_token = tokens[lookahead]
                if next_token.upper() == "OR" or ":" in next_token:
                    break
                subject_parts.append(next_token)
                lookahead += 1
            parsed["subject_keywords"].append(" ".join(subject_parts))
            index = lookahead
            continue
        elif key == "label":
            parsed["label_requirements"].append(token.split(":", 1)[1])
        elif key == "has" and value == "attachment":
            parsed["has_attachment"] = True
        index += 1
    return parsed


def _normalize_filter_from_addresses(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        raw_value = value.strip()
        if not raw_value:
            continue
        if raw_value.startswith("@"):
            normalized.append(f"*{raw_value}")
        elif "@" not in raw_value and "*" not in raw_value:
            normalized.append(f"*{raw_value}")
        else:
            normalized.append(raw_value)
    return normalized


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


def _paginate(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "pages": max(1, (len(items) + page_size - 1) // page_size),
    }


class TrajectorySubmission(BaseModel):
    session_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)


@router.post("/trajectory")
def save_gold_trajectory(
    body: TrajectorySubmission,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    """Save a human gold trajectory for a passed task.

    Only saves if the evaluation indicates success. Stores the trajectory
    alongside task settings (seed, degradation, resolved targets) so it can
    be reproduced exactly.
    """
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

    # Build trajectory record
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

    # Gold trajectories go to gold_trajectories/, others to trajectories/
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


@router.get("/degradation/{session_id}")
def get_client_degradation(session_id: str) -> dict[str, Any]:
    """Return client-layer degradation injections for a session as executable JS."""
    from ...injector.middleware import get_client_injections
    injections = get_client_injections(session_id)
    return {"session_id": session_id, "client_injections": injections}


@router.get("/variants")
def list_variants() -> list[dict[str, Any]]:
    """List available degradation variants for the Gmail environment.

    Includes hand-written YAML variants plus auto-generated defaults for
    tasks whose primary primitive has no specific variant.
    """
    from pathlib import Path
    import yaml

    variants_dir = Path(__file__).parent.parent.parent / "injector" / "variants"
    result = []

    # Hand-written YAML variants (Gmail only)
    if variants_dir.exists():
        for f in sorted(variants_dir.glob("gmail_*.yaml")):
            try:
                data = yaml.safe_load(f.read_text())
                btid = data.get("base_task_id", "")
                prim = data.get("target_primitive", "")
                result.append({
                    "filename": f.name,
                    "variant_id": data.get("variant_id", ""),
                    "base_task_id": btid,
                    "target_primitive": prim,
                    "description": data.get("description", ""),
                    "source": "yaml",
                })
            except Exception:
                pass

    return result


@router.post("/session")
def create_session(body: SessionCreateRequest, request: Request = None, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    task = get_task(body.task_id)
    if task.env_id != "gmail":
        raise HTTPException(status_code=404, detail=f"Unknown Gmail task_id: {body.task_id}")

    # Load/validate degradation before creating the session so mismatched variants
    # never allocate live benchmark state.
    degradation = dict(body.degradation) if body.degradation else None
    if body.variant_filename and not degradation:
        # Reject path traversal attempts in variant filenames
        if "/" in body.variant_filename or "\\" in body.variant_filename or ".." in body.variant_filename:
            raise HTTPException(status_code=400, detail="Invalid variant filename")
        # Handle auto-generated variants (filename starts with __auto__)
        if body.variant_filename.startswith("__auto__"):
            # Format: __auto__{task_id}__{primitive}
            # Split from the right on __ to separate primitive from task_id
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

    session_id, resolved_targets, actual_seed = session_manager.create_session("gmail", body.task_id, body.seed)
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

    # Apply seed/server degradation injections post-seed, pre-response
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

    # Register network degradation for server-side middleware
    if degradation:
        from ...injector.middleware import register_session_degradation
        register_session_degradation(session_id, degradation.get("injections", []))

    # Capture baseline snapshot for collateral-damage detection.
    # Must happen after seed/server injections so the snapshot reflects the
    # actual initial state the agent will see.
    if isinstance(state, GmailState):
        state._initial_snapshot = state.state_snapshot()
    state._initial_state_copy = state.model_copy(deep=True)

    instruction = render_template(
        task.instruction_template or task.instruction or "", resolved_targets
    )
    resp: dict[str, Any] = {
        "session_id": session_id,
        "start_path": task.start_path or "/inbox",
        "title": task.title,
        "instruction": instruction,
        "degradation_active": bool(degradation),
    }
    # Only include resolved_targets for privileged callers (harness/tests).
    # Agents in the browser must not see raw target values.
    if request is not None and has_controller_access(request):
        resp["resolved_targets"] = resolved_targets
    return resp


@router.get("/session/{session_id}")
def get_session(session_id: str, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    try:
        summary = session_manager.session_summary(session_id)
        # Enrich with instruction and title for the human play toolbar
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
def reset_session(session_id: str, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
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
        destroy_session(session_id, session_manager=session_manager)
        return next_session
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/session/{session_id}")
def destroy_session(session_id: str, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    try:
        session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session_manager.destroy(session_id)
    from ...injector.middleware import unregister_session_degradation
    unregister_session_degradation(session_id)
    return {"ok": True, "session_id": session_id}


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


@router.get("/emails")
def list_emails(
    session_id: str = Query(...),
    label: str = Query("inbox"),
    q: str | None = Query(None),
    unread: bool | None = Query(None),
    starred: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    emails = state.list_emails(label=label, q=q)
    if unread is not None:
        emails = [email for email in emails if email.is_read is (not unread)]
    if starred is not None:
        emails = [email for email in emails if email.is_starred is starred]
    items = [_serialize_email(state, email) for email in emails]
    payload = _paginate(items, page, page_size)
    payload["counts"] = state.mailbox_counts()
    return payload


@router.get("/emails/{email_id}")
def get_email(
    email_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    email = state.get_email(email_id)
    if email is None:
        raise HTTPException(status_code=404, detail=f"Unknown email id: {email_id}")
    return {
        "email": _serialize_email(state, email),
        "thread": [_serialize_email(state, item) for item in state.get_thread(email.thread_id)],
    }


@router.post("/emails/{email_id}/read")
def mark_read(
    email_id: str,
    body: ReadEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.email.read",
        {"email_id": email_id, "is_read": body.is_read},
        lambda s: s.mark_read(email_id, body.is_read),
    )
    return {"email": _serialize_email(state, result)}


@router.post("/emails/mark-all-read")
def mark_all_read(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    def _do_mark_all_read(s: GmailState) -> int:
        count = 0
        for email in s.emails:
            if not email.is_read:
                email.is_read = True
                count += 1
        return count

    count = _mutate(
        session_manager, body.session_id,
        "gmail.email.mark_all_read",
        {"session_id": body.session_id},
        _do_mark_all_read,
    )
    return {"marked": count}


@router.post("/emails/{email_id}/star")
def toggle_star(
    email_id: str,
    body: StarEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.email.star",
        {"email_id": email_id, "is_starred": body.is_starred},
        lambda s: s.toggle_star(email_id, body.is_starred),
    )
    return {"email": _serialize_email(state, result)}


@router.post("/emails/{email_id}/label")
def label_email(
    email_id: str,
    body: LabelEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.email.label",
        {"email_id": email_id, "label": body.label, "action": body.action},
        lambda s: s.apply_label(email_id, body.label, body.action),
    )
    return {"email": _serialize_email(state, result)}


@router.post("/emails/{email_id}/archive")
def archive_email(
    email_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.email.archive",
        {"email_id": email_id},
        lambda s: s.archive_email(email_id),
    )
    return {"email": _serialize_email(state, result)}


@router.post("/emails/{email_id}/delete")
def delete_email(
    email_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.email.delete",
        {"email_id": email_id},
        lambda s: s.delete_email(email_id),
    )
    return {"email": result.model_dump(mode="json")}


@router.post("/emails/{email_id}/restore")
def restore_email(
    email_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.email.restore",
        {"email_id": email_id},
        lambda s: s.restore_email(email_id),
    )
    return {"email": _serialize_email(state, result)}


@router.post("/emails/{email_id}/forward")
def forward_email(
    email_id: str,
    body: ForwardEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.email.forward",
        {"email_id": email_id, "to": body.to},
        lambda s: s.forward_email(
            email_id, to=body.to, cc=body.cc, bcc=body.bcc, body=body.body,
        ),
    )
    return {"email": result.model_dump(mode="json")}


@router.post("/send")
def send_email(
    body: SendEmailRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    attachments = [_serialize_attachment(item) for item in body.attachments]
    result = _mutate(
        session_manager, body.session_id,
        "gmail.send",
        {"to": body.to, "subject": body.subject, "in_reply_to": body.in_reply_to},
        lambda s: s.send_email(
            subject=body.subject, body=body.body, to=body.to, cc=body.cc,
            bcc=body.bcc, thread_id=body.thread_id,
            in_reply_to=body.in_reply_to, attachments=attachments,
        ),
    )
    return {"email": result.model_dump(mode="json")}


@router.get("/labels")
def list_labels(session_id: str = Query(...), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    return {"items": [label.model_dump(mode="json") for label in state.labels]}


@router.post("/labels")
def create_label(
    body: CreateLabelRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.label.create",
        {"name": body.name, "color": body.color},
        lambda s: s.ensure_label(
            body.name, body.color,
            show_in_label_list=body.show_in_label_list,
            show_in_message_list=body.show_in_message_list,
            show_in_imap=body.show_in_imap,
        ),
    )
    return {"label": result.model_dump(mode="json")}


@router.put("/labels/{label_id}")
def update_label(
    label_id: str,
    body: UpdateLabelRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.label.update",
        {"label_id": label_id},
        lambda s: s.update_label(
            label_id, name=body.name,
            show_in_label_list=body.show_in_label_list,
            show_in_message_list=body.show_in_message_list,
            show_in_imap=body.show_in_imap,
        ),
    )
    return {"label": result.model_dump(mode="json")}


@router.delete("/labels/{label_id}")
def delete_label(
    label_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "gmail.label.delete",
        {"label_id": label_id},
        lambda s: s.remove_label(label_id),
    )
    return {"label": result.model_dump(mode="json")}


@router.get("/filters")
def list_filters(session_id: str = Query(...), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    return {"items": [_serialize_filter(rule) for rule in state.filters]}


@router.post("/filters")
def create_filter(
    body: CreateFilterRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    parsed = _parse_filter_query(body.query)
    rule = FilterRule(
        id=f"filter_{len(state.filters) + 1}",
        name=body.name or body.query or "Untitled filter",
        query=body.query,
        from_addresses=_normalize_filter_from_addresses(body.from_addresses) or parsed["from_addresses"],
        subject_keywords=body.subject_keywords or parsed["subject_keywords"],
        label_requirements=body.label_requirements or parsed["label_requirements"],
        has_attachment=body.has_attachment if body.has_attachment is not None else parsed["has_attachment"],
        add_labels=body.add_labels,
        archive=body.archive,
        mark_read=body.mark_read,
        forward_to=body.forward_to,
        star=body.star,
        never_spam=body.never_spam,
    )
    result = _mutate(
        session_manager, body.session_id,
        "gmail.filter.create",
        {"name": body.name, "query": body.query},
        lambda s: s.create_filter(rule),
    )
    return {"filter": result.model_dump(mode="json")}


@router.delete("/filters/{filter_id}")
def delete_filter(
    filter_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "gmail.filter.delete",
        {"filter_id": filter_id},
        lambda s: s.remove_filter(filter_id),
    )
    return {"filter": result.model_dump(mode="json")}


@router.get("/contacts")
def list_contacts(
    session_id: str = Query(...),
    q: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    contacts = state.contacts
    if q:
        lowered = q.lower()
        contacts = [
            contact
            for contact in contacts
            if lowered in contact.name.lower() or lowered in contact.email.lower()
        ]
    return {"items": [_serialize_contact(contact) for contact in contacts]}


@router.post("/contacts")
def create_contact(
    body: CreateContactRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    contact = Contact(
        id=f"contact_manual_{len(state.contacts) + 1}",
        name=body.name,
        email=body.email,
        company=body.company,
        note=body.note,
        is_vip=body.is_vip,
        is_starred=body.is_starred,
        source="manual",
        last_contacted_at=body.last_contacted_at,
    )
    result = _mutate(
        session_manager, body.session_id,
        "gmail.contact.create",
        {"email": body.email},
        lambda s: s.add_contact(contact),
    )
    return {"contact": result.model_dump(mode="json")}


@router.put("/contacts/{contact_id}")
def update_contact(
    contact_id: str,
    body: UpdateContactRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    updates = body.model_dump(exclude={"session_id"}, exclude_unset=True)
    result = _mutate(
        session_manager, body.session_id,
        "gmail.contact.update",
        {"contact_id": contact_id, **updates},
        lambda s: s.update_contact(contact_id, **updates),
    )
    return {"contact": result.model_dump(mode="json")}


@router.delete("/contacts/{contact_id}")
def delete_contact(
    contact_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "gmail.contact.delete",
        {"contact_id": contact_id},
        lambda s: s.remove_contact(contact_id),
    )
    return {"contact": result.model_dump(mode="json")}


@router.get("/settings")
def get_settings(session_id: str = Query(...), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    return {"settings": state.settings.model_dump(mode="json")}


@router.put("/settings")
def update_settings(
    body: UpdateSettingsRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, body.session_id)
    updates = body.model_dump(exclude={"session_id"}, exclude_none=True)

    def apply_update(current_state: Any) -> Any:
        for key, value in updates.items():
            setattr(state.settings, key, value)
        state.touch()
        return state.settings

    result = _mutate(
        session_manager, body.session_id,
        "gmail.settings.update",
        updates,
        apply_update,
    )
    return {"settings": result.model_dump(mode="json")}


@router.get("/search")
def search_mail(
    q: str = Query(...),
    session_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _gmail_state(session_manager, session_id)
    items = [_serialize_email(state, email) for email in state.search(q)]
    payload = _paginate(items, page, page_size)
    payload["query"] = q
    return payload
