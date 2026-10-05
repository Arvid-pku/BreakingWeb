"""Control-panel API: recording state sync between control tab and benchmark tab.

Env-agnostic. The benchmark tab polls `record-state` to know whether to
capture DOM events. The control tab calls `start`/`stop` to toggle.

Recording state is in-memory only (dies with the process). Events are
buffered in the benchmark page's JS and submitted in bulk via the existing
`/api/env/{env}/trajectory` endpoint.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/control", tags=["control"])


class RecordState(BaseModel):
    recording: bool = False
    started_at_ms: int = 0
    event_count: int = 0
    last_heartbeat_ms: int = 0
    # Human-recording context: set by the control tab (human_control.html) at
    # record-start. The env tab reads this on record-stop to also write a copy
    # of the trace to /api/human/attempt/save with annotator metadata.
    human: dict[str, Any] | None = None
    # Evaluation result passed from the control tab on stop so the env tab can
    # ship it along with the events instead of saving with evaluation: {}.
    stop_evaluation: dict[str, Any] | None = None
    # Fill path written by the env tab after it actually saved the trace, so
    # the control tab can stop polling and move to the next phase.
    save_result: dict[str, Any] | None = None


# In-memory state keyed by session_id.
_RECORD_STATE: dict[str, RecordState] = {}


def _get(session_id: str) -> RecordState:
    return _RECORD_STATE.setdefault(session_id, RecordState())


class StartRequest(BaseModel):
    human: dict[str, Any] | None = None


class StopRequest(BaseModel):
    evaluation: dict[str, Any] | None = None


@router.get("/{session_id}/record-state")
def get_record_state(session_id: str) -> dict[str, Any]:
    state = _get(session_id)
    return state.model_dump()


@router.post("/{session_id}/record/start")
def record_start(session_id: str, body: StartRequest | None = None) -> dict[str, Any]:
    state = _get(session_id)
    if state.recording:
        raise HTTPException(status_code=409, detail="Already recording")
    state.recording = True
    state.started_at_ms = int(time.time() * 1000)
    state.event_count = 0
    state.save_result = None
    state.stop_evaluation = None
    if body and body.human is not None:
        state.human = body.human
    return state.model_dump()


@router.post("/{session_id}/record/stop")
def record_stop(session_id: str, body: StopRequest | None = None) -> dict[str, Any]:
    state = _get(session_id)
    state.recording = False
    if body and body.evaluation is not None:
        state.stop_evaluation = body.evaluation
    return state.model_dump()


class SaveResultRequest(BaseModel):
    save_result: dict[str, Any]


@router.post("/{session_id}/record/save-result")
def record_save_result(session_id: str, body: SaveResultRequest) -> dict[str, Any]:
    """Env tab reports back after it successfully saved the human trace."""
    state = _get(session_id)
    state.save_result = body.save_result
    return state.model_dump()


class EventCountUpdate(BaseModel):
    event_count: int


@router.post("/{session_id}/record/heartbeat")
def record_heartbeat(session_id: str, body: EventCountUpdate) -> dict[str, Any]:
    """Benchmark page reports its current event count so the control tab can show it.

    Also updates ``last_heartbeat_ms`` so the control tab knows whether a
    benchmark tab is still open.
    """
    state = _get(session_id)
    state.event_count = body.event_count
    state.last_heartbeat_ms = int(time.time() * 1000)
    return state.model_dump()


@router.post("/{session_id}/record/reset")
def record_reset(session_id: str) -> dict[str, Any]:
    """Clear recording state. Does not touch the simulated env state."""
    _RECORD_STATE.pop(session_id, None)
    return {"ok": True}
