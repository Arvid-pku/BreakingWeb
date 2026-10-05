"""Human recording mode: annotator-facing assignment list + trace save.

Flow:
  1. Annotator opens /static/human.html?annotator=P1.
  2. Frontend calls GET /api/human/assignments?annotator=P1 and renders the
     filtered list (no primitive labels / expected steps / variant internals).
  3. Annotator clicks "start cold attempt on <task>". The frontend POSTs to
     /api/env/{env}/session with task_id + seed=42 (+ variant_filename when
     the assignment is the intervention condition), and receives a
     session_id + start_path from the existing env infrastructure.
  4. Frontend opens an iframe / new tab at
     http://localhost:{env_port}/env/{env}{start_path}?session_id=...
     plus human_* query params. BenchmarkToolbar already includes a hook that
     reads these params (added in this change) and, on evaluate, POSTs the
     trace to /api/human/attempt/save.
  5. Backend writes trace.json + metadata.json under
     breakingweb/human/traces/{annotator}/{role}/{env}/{base}/{cond}/{attempt}/
     and updates progress.json.
  6. After the warm attempt is saved, the frontend shows a post-task form,
     which POSTs to /api/human/attempt/post_task_form to mark the assignment
     fully complete.

Pause == redo: only fully-saved attempts are recorded in progress.json. A
crashed / abandoned mid-attempt is discarded on next start.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..state import SessionManager

router = APIRouter(prefix="/api/human", tags=["human"])

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_HUMAN_DIR = _REPO_ROOT / "breakingweb" / "human"
_ASSIGNMENTS_YAML = _HUMAN_DIR / "assignments_v1.yaml"
_TRACES_ROOT = _HUMAN_DIR / "traces"


# ---------------------------------------------------------------------------
# Assignment loading (cached)
# ---------------------------------------------------------------------------

_ASSIGNMENTS_CACHE: dict[str, Any] | None = None
_ASSIGNMENTS_LOCK = Lock()


def _load_assignments() -> dict[str, Any]:
    global _ASSIGNMENTS_CACHE
    with _ASSIGNMENTS_LOCK:
        if _ASSIGNMENTS_CACHE is None:
            if not _ASSIGNMENTS_YAML.exists():
                raise HTTPException(
                    status_code=500,
                    detail=f"Assignment YAML missing at {_ASSIGNMENTS_YAML}",
                )
            with open(_ASSIGNMENTS_YAML) as f:
                _ASSIGNMENTS_CACHE = yaml.safe_load(f) or {}
        return _ASSIGNMENTS_CACHE


def _all_assignments() -> list[dict[str, Any]]:
    data = _load_assignments()
    primary = data.get("condition_assignments") or []
    duplicate = data.get("duplicate_condition_assignments") or []
    return list(primary) + list(duplicate)


def _find_assignment(aid: str) -> dict[str, Any]:
    for a in _all_assignments():
        if a.get("aid") == aid:
            return a
    raise HTTPException(status_code=404, detail=f"Unknown assignment id: {aid}")


# ---------------------------------------------------------------------------
# SessionManager dependency (same pattern as env route files)
# ---------------------------------------------------------------------------


def get_session_manager(request: Request) -> SessionManager:
    sm = getattr(request.app.state, "session_manager", None)
    if sm is None:
        raise HTTPException(
            status_code=500, detail="SessionManager is not configured on app.state"
        )
    return sm


# ---------------------------------------------------------------------------
# Progress tracking (per-annotator JSON file)
# ---------------------------------------------------------------------------

_PROGRESS_LOCK = Lock()


def _annotator_root(annotator: str) -> Path:
    return _TRACES_ROOT / annotator


def _progress_path(annotator: str) -> Path:
    return _annotator_root(annotator) / "progress.json"


def _load_progress(annotator: str) -> dict[str, Any]:
    path = _progress_path(annotator)
    if not path.exists():
        return {"annotator": annotator, "assignments": {}}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"annotator": annotator, "assignments": {}}


def _save_progress(annotator: str, progress: dict[str, Any]) -> None:
    path = _progress_path(annotator)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(progress, f, indent=2, default=str)


def _update_assignment_status(
    annotator: str,
    aid: str,
    *,
    cold_done: bool | None = None,
    warm_done: bool | None = None,
    form_done: bool | None = None,
    reset: bool = False,
) -> dict[str, Any]:
    with _PROGRESS_LOCK:
        progress = _load_progress(annotator)
        if reset:
            progress["assignments"][aid] = {
                "cold_done": False,
                "warm_done": False,
                "form_done": False,
            }
        slot = progress["assignments"].setdefault(
            aid,
            {"cold_done": False, "warm_done": False, "form_done": False},
        )
        if cold_done is not None:
            slot["cold_done"] = cold_done
        if warm_done is not None:
            slot["warm_done"] = warm_done
        if form_done is not None:
            slot["form_done"] = form_done
        slot["updated_at"] = datetime.now(timezone.utc).isoformat()
        progress["updated_at"] = slot["updated_at"]
        _save_progress(annotator, progress)
        return slot


# ---------------------------------------------------------------------------
# Public view for annotator UI (strips benchmark-only fields)
# ---------------------------------------------------------------------------


def _public_assignment_view(a: dict[str, Any]) -> dict[str, Any]:
    """Return only fields safe to show the annotator.

    Hidden: primary_primitive (`prim`), expected_steps (`steps`), variant
    internals like `target_primitive` / `description`.

    Shown: condition label (clean/intervention) — annotators must know which
    condition they're recording, but not which primitive the intervention is
    stressing.

    variant_filename is included (basename, no path) because the frontend
    needs it to call /api/env/{env}/session with the right variant. It's not
    rendered as user-facing text.
    """
    variant = a.get("variant") or {}
    variant_filename = None
    if variant.get("yaml"):
        variant_filename = Path(variant["yaml"]).name
    return {
        "aid": a["aid"],
        "role": a["role"],
        "base_task_id": a["base"],
        "env": a["env"],
        "difficulty": a["diff"],
        "title": a["title"],
        "condition": a["cond"],
        "task_yaml": a["yaml"],
        "variant_filename": variant_filename,
    }


# ---------------------------------------------------------------------------
# GET /api/human/assignments
# ---------------------------------------------------------------------------


_DIFF_RANK = {"easy": 0, "medium": 1, "hard": 2, "expert": 3, "frontier": 4}


@router.get("/assignments")
def list_assignments(
    annotator: str = Query(..., min_length=1),
    env: str | None = Query(default=None),
) -> dict[str, Any]:
    norm = annotator.strip()
    all_assignments = _all_assignments()
    matched = [
        a for a in all_assignments if a.get("annotator", "").lower() == norm.lower()
    ]
    if not matched:
        known = sorted({a["annotator"] for a in all_assignments})
        raise HTTPException(
            status_code=404,
            detail=f"No assignments for annotator '{annotator}'. Known: {known}",
        )
    if env:
        matched = [a for a in matched if a.get("env") == env]

    progress = _load_progress(norm)
    prog_map = progress.get("assignments", {})

    entries: list[dict[str, Any]] = []
    for a in matched:
        view = _public_assignment_view(a)
        slot = prog_map.get(a["aid"], {})
        view["status"] = {
            "cold_done": bool(slot.get("cold_done", False)),
            "warm_done": bool(slot.get("warm_done", False)),
            "form_done": bool(slot.get("form_done", False)),
            "updated_at": slot.get("updated_at"),
        }
        # An assignment counts as complete once both cold and warm traces
        # are saved. The post-task form is optional — annotators who want to
        # flag a bug / ambiguity can still fill it, but it isn't required.
        view["completed"] = (
            view["status"]["cold_done"] and view["status"]["warm_done"]
        )
        entries.append(view)

    entries.sort(
        key=lambda v: (
            v["env"],
            _DIFF_RANK.get(v["difficulty"], 99),
            v["base_task_id"],
            v["condition"],
        )
    )

    completed = sum(1 for v in entries if v["completed"])
    return {
        "annotator": norm,
        "total": len(entries),
        "completed": completed,
        "assignments": entries,
    }


# ---------------------------------------------------------------------------
# GET /api/human/progress
# ---------------------------------------------------------------------------


@router.get("/progress")
def get_progress(annotator: str = Query(..., min_length=1)) -> dict[str, Any]:
    return _load_progress(annotator.strip())


# ---------------------------------------------------------------------------
# GET /api/human/summary (for CLI / monitoring)
# ---------------------------------------------------------------------------


@router.get("/summary")
def summary(annotator: str = Query(..., min_length=1)) -> dict[str, Any]:
    norm = annotator.strip()
    prog = _load_progress(norm)
    slots = prog.get("assignments", {})
    all_aids = [
        a["aid"] for a in _all_assignments() if a["annotator"].lower() == norm.lower()
    ]
    not_started = [aid for aid in all_aids if aid not in slots]
    partial = [
        aid
        for aid, s in slots.items()
        if not (s.get("cold_done") and s.get("warm_done"))
    ]
    completed = [
        aid
        for aid, s in slots.items()
        if s.get("cold_done") and s.get("warm_done")
    ]
    return {
        "annotator": norm,
        "total_assigned": len(all_aids),
        "completed": len(completed),
        "partial": len(partial),
        "not_started": len(not_started),
        "partial_ids": partial,
        "not_started_ids": not_started,
        "completed_ids": completed,
    }


# ---------------------------------------------------------------------------
# POST /api/human/attempt/save — the core trace write
# ---------------------------------------------------------------------------


def _trace_dir(
    *,
    annotator: str,
    role: str,
    env: str,
    base: str,
    condition: str,
    attempt: str,
) -> Path:
    return (
        _TRACES_ROOT / annotator / role / env / base / condition / attempt
    )


def _mark_existing_attempts_abandoned(annotator: str, aid: str) -> list[str]:
    """Stamp any on-disk cold/ + warm/ trace files for this assignment with
    abandoned=True so analysts can filter them out without losing the data.

    Files are NOT deleted. The next save to the same path overwrites the
    metadata cleanly (the new save dict has no `abandoned` key), so a fresh
    attempt automatically clears the marker.
    """
    assignment = _find_assignment(aid)
    base_dir = (
        _TRACES_ROOT
        / annotator.strip()
        / assignment["role"]
        / assignment["env"]
        / assignment["base"]
        / assignment["cond"]
    )
    if not base_dir.exists():
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    marked: list[str] = []
    for attempt in ("cold", "warm"):
        meta_path = base_dir / attempt / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if meta.get("abandoned"):
            continue
        meta["abandoned"] = True
        meta["abandoned_at"] = now_iso
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        trace_path = base_dir / attempt / "trace.json"
        if trace_path.exists():
            try:
                with open(trace_path) as f:
                    trace = json.load(f)
                if isinstance(trace.get("metadata"), dict):
                    trace["metadata"]["abandoned"] = True
                    trace["metadata"]["abandoned_at"] = now_iso
                    with open(trace_path, "w") as f:
                        json.dump(trace, f, indent=2, default=str)
            except (json.JSONDecodeError, OSError):
                pass
        marked.append(attempt)
    return marked


class AttemptSaveRequest(BaseModel):
    annotator: str
    aid: str
    attempt: str  # cold | warm
    session_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    started_at_ms: int = 0
    ended_at_ms: int = 0
    viewport: dict[str, Any] = Field(default_factory=dict)
    client_metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/attempt/save")
def attempt_save(
    body: AttemptSaveRequest,
    sm: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    if body.attempt not in {"cold", "warm"}:
        raise HTTPException(status_code=400, detail="attempt must be 'cold' or 'warm'")

    assignment = _find_assignment(body.aid)
    if assignment.get("annotator", "").lower() != body.annotator.strip().lower():
        raise HTTPException(status_code=403, detail="Assignment not owned by this annotator")

    try:
        state = sm.get(body.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    out_dir = _trace_dir(
        annotator=body.annotator.strip(),
        role=assignment["role"],
        env=assignment["env"],
        base=assignment["base"],
        condition=assignment["cond"],
        attempt=body.attempt,
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    wall_clock_ms = (
        body.ended_at_ms - body.started_at_ms
        if body.started_at_ms and body.ended_at_ms
        else 0
    )
    pass_fail = bool(body.evaluation.get("success"))
    final_score = float(body.evaluation.get("score", 0.0)) if body.evaluation else 0.0

    metadata = {
        "assignment_id": body.aid,
        "assignment_role": assignment["role"],
        "annotator": body.annotator.strip(),
        "base_task_id": assignment["base"],
        "env": assignment["env"],
        "difficulty": assignment["diff"],
        "condition": assignment["cond"],
        "attempt_type": body.attempt,
        "seed": 42,
        "intervention_variant_id": (assignment.get("variant") or {}).get("id"),
        "intervention_variant_yaml": (assignment.get("variant") or {}).get("yaml"),
        "title": assignment["title"],
        "session_id": body.session_id,
        "recorded_at": now_iso,
        "started_at_ms": body.started_at_ms,
        "ended_at_ms": body.ended_at_ms,
        "wall_clock_ms": wall_clock_ms,
        "raw_event_count": len(body.events),
        "audit_entry_count": len(state.audit_log),
        "final_score": final_score,
        "pass": pass_fail,
        "viewport": body.viewport,
        "client_metadata": body.client_metadata,
    }
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    trace = {
        "metadata": metadata,
        "events": body.events,
        "audit_log": [entry.model_dump() for entry in state.audit_log],
        "resolved_targets": state.resolved_targets,
        "evaluation": body.evaluation,
    }
    with open(out_dir / "trace.json", "w") as f:
        json.dump(trace, f, indent=2, default=str)

    # State machine: cold wipes prior warm/form so interrupted flows can't
    # accumulate. Warm is only accepted if cold is already done for this
    # assignment (the dashboard "Start" button resets this pair atomically,
    # so the only valid ordering is cold -> warm).
    if body.attempt == "cold":
        _update_assignment_status(body.annotator, body.aid, reset=True)
        _update_assignment_status(body.annotator, body.aid, cold_done=True)
    else:
        current = _load_progress(body.annotator.strip())["assignments"].get(body.aid, {})
        if not current.get("cold_done"):
            raise HTTPException(
                status_code=400,
                detail="Warm attempt requires a completed cold attempt for this assignment.",
            )
        _update_assignment_status(body.annotator, body.aid, warm_done=True)

    slot = _load_progress(body.annotator.strip())["assignments"].get(body.aid, {})
    # After cold: annotator moves to warm. After warm: assignment is already
    # complete — the post-task form is offered as a short optional step.
    next_action = "reset_for_warm"
    if slot.get("cold_done") and slot.get("warm_done"):
        next_action = "done_form_optional"
    return {
        "saved": True,
        "trace_dir": str(out_dir.relative_to(_REPO_ROOT)),
        "next_action": next_action,
        "pass": pass_fail,
        "final_score": final_score,
        "event_count": len(body.events),
        "audit_entry_count": len(state.audit_log),
    }


# ---------------------------------------------------------------------------
# POST /api/human/attempt/post_task_form
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# POST /api/human/attempt/reset — called by dashboard before starting a task
# ---------------------------------------------------------------------------


class AttemptResetRequest(BaseModel):
    annotator: str
    aid: str


@router.post("/attempt/reset")
def attempt_reset(body: AttemptResetRequest) -> dict[str, Any]:
    """Wipe progress flags for an assignment before the annotator starts.

    User-visible rule: cold+warm+form is atomic per assignment. If an annotator
    abandons mid-flow and comes back, clicking Start re-runs the whole
    sequence, not just the missing piece. This endpoint wipes cold_done /
    warm_done / form_done so progress counters stay honest, and stamps any
    on-disk trace files for this assignment with abandoned=True so analysts
    can filter them out without losing the recording.
    """
    _find_assignment(body.aid)  # validates aid exists and raises 404 if not
    abandoned = _mark_existing_attempts_abandoned(body.annotator.strip(), body.aid)
    slot = _update_assignment_status(body.annotator, body.aid, reset=True)
    return {"ok": True, "slot": slot, "abandoned_attempts": abandoned}


class PostTaskForm(BaseModel):
    annotator: str
    aid: str
    clarity: int = Field(ge=1, le=5)
    realism: int = Field(ge=1, le=5)
    fun_value: int = Field(ge=1, le=5)
    intervention_naturalness: int | None = Field(default=None, ge=1, le=5)
    suspected_bug: bool = False
    ambiguous_instruction: bool = False
    alternate_valid_strategy: bool = False
    comments: str = ""


@router.post("/attempt/post_task_form")
def submit_post_task_form(body: PostTaskForm) -> dict[str, Any]:
    assignment = _find_assignment(body.aid)
    if assignment.get("annotator", "").lower() != body.annotator.strip().lower():
        raise HTTPException(status_code=403, detail="Assignment not owned by this annotator")

    # Form requires both cold and warm to have saved first.
    current = _load_progress(body.annotator.strip())["assignments"].get(body.aid, {})
    if not (current.get("cold_done") and current.get("warm_done")):
        raise HTTPException(
            status_code=400,
            detail="Post-task form requires both cold and warm attempts saved.",
        )

    cond_dir = (
        _TRACES_ROOT
        / body.annotator.strip()
        / assignment["role"]
        / assignment["env"]
        / assignment["base"]
        / assignment["cond"]
    )
    cond_dir.mkdir(parents=True, exist_ok=True)
    payload = body.model_dump()
    payload["submitted_at"] = datetime.now(timezone.utc).isoformat()
    with open(cond_dir / "post_task_form.json", "w") as f:
        json.dump(payload, f, indent=2)

    slot = _update_assignment_status(body.annotator, body.aid, form_done=True)
    return {"saved": True, "slot": slot}
