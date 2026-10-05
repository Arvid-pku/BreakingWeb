from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...tasks._evaluator import evaluate as unified_evaluate
from ...tasks._registry import get_task
from ..models.base import AuditEntry
from ..models.reddit import (
    Comment,
    Message,
    Notification,
    Post,
    RedditState,
    Subreddit,
)
from ..security import (
    build_public_session_summary,
    has_controller_access,
    require_evaluation_access,
)
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/reddit", tags=["reddit"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    task_id: str
    seed: int | None = None
    degradation: dict | None = None
    variant_filename: str | None = None


class SessionScopedRequest(BaseModel):
    session_id: str


class VoteRequest(SessionScopedRequest):
    direction: int  # -1, 0, 1


class CreatePostRequest(SessionScopedRequest):
    subreddit_name: str
    title: str
    body: str = ""
    url: str = ""
    post_type: str = "text"
    flair_text: str | None = None
    is_spoiler: bool = False
    is_nsfw: bool = False


class EditPostRequest(SessionScopedRequest):
    body: str


class CreateCommentRequest(SessionScopedRequest):
    body: str
    parent_id: str | None = None


class EditCommentRequest(SessionScopedRequest):
    body: str


class SendMessageRequest(SessionScopedRequest):
    to_user: str
    subject: str
    body: str
    parent_id: str | None = None


class SubscribeRequest(SessionScopedRequest):
    action: Literal["subscribe", "unsubscribe"] = "subscribe"


class UpdateSettingsRequest(SessionScopedRequest):
    default_feed_sort: str | None = None
    default_comment_sort: str | None = None
    show_nsfw: bool | None = None
    blur_nsfw: bool | None = None
    open_links_in_new_tab: bool | None = None
    theme: str | None = None
    compact_view: bool | None = None
    email_comment_reply: bool | None = None
    email_post_reply: bool | None = None
    email_mentions: bool | None = None
    email_messages: bool | None = None
    email_digest: bool | None = None
    show_online_status: bool | None = None
    allow_followers: bool | None = None
    show_active_communities: bool | None = None
    country: str | None = None
    language: str | None = None
    auto_play_media: bool | None = None
    reduce_animations: bool | None = None


class EvaluateRequest(SessionScopedRequest):
    task_id: str | None = None
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured on app.state")
    return session_manager


def _reddit_state(session_manager: SessionManager, session_id: str) -> RedditState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, RedditState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not a Reddit session")
    return state


def _render_degradation_params(degradation: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
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


def _audit(session_manager: SessionManager, session_id: str, action: str, payload: dict[str, Any]) -> None:
    state = session_manager.get(session_id)
    state.audit_log.append(
        AuditEntry(action=action, payload=payload, summary=action)
    )


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@router.post("/session")
def create_session(body: SessionCreateRequest, request: Request = None, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    task = get_task(body.task_id)
    if task.env_id != "reddit":
        raise HTTPException(status_code=404, detail=f"Unknown Reddit task_id: {body.task_id}")

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
            degradation = {"variant_filename": body.variant_filename, **variant_data}

    if degradation and degradation.get("base_task_id") and degradation.get("base_task_id") != body.task_id:
        raise HTTPException(
            status_code=400,
            detail=f"Degradation variant is bound to task {degradation.get('base_task_id')!r}, but the session request targets {body.task_id!r}",
        )

    session_id, resolved_targets, actual_seed = session_manager.create_session("reddit", body.task_id, body.seed)
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
    if isinstance(state, RedditState):
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
def get_session(session_id: str, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
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


@router.get("/variants")
def list_variants() -> list[dict[str, Any]]:
    from pathlib import Path
    import yaml
    variants_dir = Path(__file__).parent.parent.parent / "injector" / "variants"
    result = []
    if variants_dir.exists():
        for f in sorted(variants_dir.glob("reddit_*.yaml")):
            try:
                data = yaml.safe_load(f.read_text())
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
def save_gold_trajectory(
    body: dict[str, Any],
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    import json as _json
    from pathlib import Path
    from datetime import datetime, timezone

    session_id = body.get("session_id", "")
    events = body.get("events", [])
    evaluation = body.get("evaluation", {})
    is_gold = bool(evaluation.get("success"))

    try:
        state = session_manager.get(session_id)
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
            "session_id": session_id,
            "seed": state.seed,
            "degradation": state.degradation,
            "resolved_targets": state.resolved_targets,
        },
        "evaluation": evaluation,
        "events": events,
        "audit_log": [entry.model_dump() for entry in state.audit_log],
        "total_events": len(events),
        "total_audit_entries": len(state.audit_log),
    }

    base_dir = Path(__file__).parent.parent.parent
    save_dir = base_dir / ("gold_trajectories" if is_gold else "trajectories")
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = "gold_" if is_gold else ""
    filename = f"{prefix}{state.task_id}_{timestamp}.json"
    path = save_dir / filename

    with open(path, "w") as f:
        _json.dump(record, f, indent=2, default=str)

    return {"saved": True, "gold": is_gold, "path": str(path), "filename": filename, "events": len(events)}


@router.get("/degradation/{session_id}")
def get_client_degradation(session_id: str) -> dict[str, Any]:
    from ...injector.middleware import get_client_injections
    injections = get_client_injections(session_id)
    return {"session_id": session_id, "client_injections": injections}


# ---------------------------------------------------------------------------
# Feed & Posts
# ---------------------------------------------------------------------------

@router.get("/feed")
def get_feed(
    session_id: str = Query(...),
    sort: str = Query("hot"),
    time_filter: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    posts = state.feed_posts(sort=sort, time_filter=time_filter)
    items = [p.model_dump(mode="json") for p in posts]
    payload = _paginate(items, page, page_size)
    payload["sort"] = sort
    payload["time_filter"] = time_filter
    return payload


@router.get("/r/{subreddit_name}")
def get_subreddit_page(
    subreddit_name: str,
    session_id: str = Query(...),
    sort: str = Query("hot"),
    time_filter: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    sub = state.get_subreddit_by_name(subreddit_name)
    if sub is None:
        raise HTTPException(status_code=404, detail=f"Unknown subreddit: {subreddit_name}")
    posts = state.list_posts(subreddit_name=subreddit_name, sort=sort, time_filter=time_filter)
    items = [p.model_dump(mode="json") for p in posts]
    payload = _paginate(items, page, page_size)
    payload["subreddit"] = sub.model_dump(mode="json")
    payload["sort"] = sort
    return payload


@router.post("/r/{subreddit_name}/subscribe")
def subscribe_subreddit(
    subreddit_name: str,
    body: SubscribeRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    sub = state.get_subreddit_by_name(subreddit_name)
    if sub is None:
        raise HTTPException(status_code=404, detail=f"Unknown subreddit: {subreddit_name}")
    if body.action == "subscribe":
        result = _mutate(
            session_manager, body.session_id,
            "reddit.subreddit.subscribe",
            {"subreddit": subreddit_name},
            lambda s: s.subscribe(sub.id),
        )
    else:
        result = _mutate(
            session_manager, body.session_id,
            "reddit.subreddit.unsubscribe",
            {"subreddit": subreddit_name},
            lambda s: s.unsubscribe(sub.id),
        )
    return {"subreddit": result.model_dump(mode="json")}


@router.get("/posts/{post_id}")
def get_post(
    post_id: str,
    session_id: str = Query(...),
    comment_sort: str = Query("best"),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    post = state.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Unknown post id: {post_id}")
    comments = state.get_post_comments(post_id, sort=comment_sort)
    return {
        "post": post.model_dump(mode="json"),
        "comments": [c.model_dump(mode="json") for c in comments],
        "comment_sort": comment_sort,
    }


@router.post("/posts")
def create_post(
    body: CreatePostRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.post.create",
        {"subreddit": body.subreddit_name, "title": body.title},
        lambda s: s.create_post(
            subreddit_name=body.subreddit_name,
            title=body.title,
            body=body.body,
            url=body.url,
            post_type=body.post_type,
            flair_text=body.flair_text,
            is_spoiler=body.is_spoiler,
            is_nsfw=body.is_nsfw,
        ),
    )
    return {"post": result.model_dump(mode="json")}


@router.post("/posts/{post_id}/vote")
def vote_post(
    post_id: str,
    body: VoteRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.post.vote",
        {"post_id": post_id, "direction": body.direction},
        lambda s: s.vote_post(post_id, body.direction),
    )
    return {"post": result.model_dump(mode="json")}


@router.post("/posts/{post_id}/save")
def save_post(
    post_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.post.save",
        {"post_id": post_id},
        lambda s: s.save_post(post_id),
    )
    return {"post": result.model_dump(mode="json")}


@router.post("/posts/{post_id}/unsave")
def unsave_post(
    post_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.post.unsave",
        {"post_id": post_id},
        lambda s: s.unsave_post(post_id),
    )
    return {"post": result.model_dump(mode="json")}


@router.post("/posts/{post_id}/hide")
def hide_post(
    post_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.post.hide",
        {"post_id": post_id},
        lambda s: s.hide_post(post_id),
    )
    return {"post": result.model_dump(mode="json")}


@router.post("/posts/{post_id}/unhide")
def unhide_post(
    post_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.post.unhide",
        {"post_id": post_id},
        lambda s: s.unhide_post(post_id),
    )
    return {"post": result.model_dump(mode="json")}


@router.put("/posts/{post_id}")
def edit_post(
    post_id: str,
    body: EditPostRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.post.edit",
        {"post_id": post_id},
        lambda s: s.edit_post(post_id, body.body),
    )
    return {"post": result.model_dump(mode="json")}


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "reddit.post.delete",
        {"post_id": post_id},
        lambda s: s.delete_post(post_id),
    )
    return {"post": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@router.get("/posts/{post_id}/comments")
def list_comments(
    post_id: str,
    session_id: str = Query(...),
    sort: str = Query("best"),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    comments = state.get_post_comments(post_id, sort=sort)
    return {"items": [c.model_dump(mode="json") for c in comments], "sort": sort}


@router.post("/posts/{post_id}/comments")
def create_comment(
    post_id: str,
    body: CreateCommentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.comment.create",
        {"post_id": post_id, "parent_id": body.parent_id},
        lambda s: s.add_comment(
            post_id=post_id, body=body.body, parent_id=body.parent_id,
        ),
    )
    return {"comment": result.model_dump(mode="json")}


@router.post("/comments/{comment_id}/vote")
def vote_comment(
    comment_id: str,
    body: VoteRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.comment.vote",
        {"comment_id": comment_id, "direction": body.direction},
        lambda s: s.vote_comment(comment_id, body.direction),
    )
    return {"comment": result.model_dump(mode="json")}


@router.put("/comments/{comment_id}")
def edit_comment(
    comment_id: str,
    body: EditCommentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.comment.edit",
        {"comment_id": comment_id},
        lambda s: s.edit_comment(comment_id, body.body),
    )
    return {"comment": result.model_dump(mode="json")}


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "reddit.comment.delete",
        {"comment_id": comment_id},
        lambda s: s.delete_comment(comment_id),
    )
    return {"comment": result.model_dump(mode="json")}


@router.post("/comments/{comment_id}/save")
def save_comment(
    comment_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.comment.save",
        {"comment_id": comment_id},
        lambda s: s.save_comment(comment_id),
    )
    return {"comment": result.model_dump(mode="json")}


@router.post("/comments/{comment_id}/unsave")
def unsave_comment(
    comment_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.comment.unsave",
        {"comment_id": comment_id},
        lambda s: s.unsave_comment(comment_id),
    )
    return {"comment": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.get("/messages")
def list_messages(
    session_id: str = Query(...),
    folder: str = Query("inbox"),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    if folder == "sent":
        msgs = sorted(state.sent_messages, key=lambda m: m.created_at, reverse=True)
    else:
        msgs = sorted(state.messages, key=lambda m: m.created_at, reverse=True)
    return {
        "items": [m.model_dump(mode="json") for m in msgs],
        "folder": folder,
        "unread_count": state.unread_message_count(),
    }


@router.get("/messages/{message_id}")
def get_message(
    message_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    msg = state.get_message(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail=f"Unknown message id: {message_id}")
    return {"message": msg.model_dump(mode="json")}


@router.post("/messages")
def send_message(
    body: SendMessageRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.message.send",
        {"to_user": body.to_user, "subject": body.subject},
        lambda s: s.send_message(
            to_user=body.to_user, subject=body.subject,
            body=body.body, parent_id=body.parent_id,
        ),
    )
    return {"message": result.model_dump(mode="json")}


@router.post("/messages/{message_id}/read")
def mark_message_read(
    message_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.message.read",
        {"message_id": message_id},
        lambda s: s.mark_message_read(message_id),
    )
    return {"message": result.model_dump(mode="json")}


@router.post("/messages/mark-all-read")
def mark_all_messages_read(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    count = _mutate(
        session_manager, body.session_id,
        "reddit.message.mark_all_read",
        {},
        lambda s: s.mark_all_messages_read(),
    )
    return {"marked": count}


@router.delete("/messages/{message_id}")
def delete_message(
    message_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "reddit.message.delete",
        {"message_id": message_id},
        lambda s: s.delete_message(message_id),
    )
    return {"message": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications")
def list_notifications(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    notifs = sorted(state.notifications, key=lambda n: n.created_at, reverse=True)
    return {
        "items": [n.model_dump(mode="json") for n in notifs],
        "unread_count": state.unread_notification_count(),
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "reddit.notification.read",
        {"notification_id": notification_id},
        lambda s: s.mark_notification_read(notification_id),
    )
    return {"notification": result.model_dump(mode="json")}


@router.post("/notifications/mark-all-read")
def mark_all_notifications_read(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    count = _mutate(
        session_manager, body.session_id,
        "reddit.notification.mark_all_read",
        {},
        lambda s: s.mark_all_notifications_read(),
    )
    return {"marked": count}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("/search")
def search(
    q: str = Query(...),
    session_id: str = Query(...),
    type: str = Query("posts"),
    subreddit: str | None = Query(None),
    sort: str = Query("relevance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    if type == "subreddits":
        results = state.search_subreddits(q)
        items = [s.model_dump(mode="json") for s in results]
    else:
        results = state.search_posts(q, subreddit_name=subreddit, sort=sort)
        items = [p.model_dump(mode="json") for p in results]
    payload = _paginate(items, page, page_size)
    payload["query"] = q
    payload["type"] = type
    return payload


# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

@router.get("/user/{username}")
def get_user_profile(
    username: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    # Return the owner's profile
    if username.lower() == state.owner_username.lower():
        posts = [p for p in state.posts if p.author_name == state.owner_username and not p.is_removed]
        comments = [c for c in state.comments if c.author_name == state.owner_username and not c.is_removed]
        return {
            "user": {
                "username": state.owner_username,
                "display_name": state.owner_display_name,
                "avatar_url": state.owner_avatar_url,
                "about": state.owner_about,
                "post_karma": state.owner_post_karma,
                "comment_karma": state.owner_comment_karma,
                "cake_day": state.owner_cake_day.isoformat() if state.owner_cake_day else None,
                "is_premium": False,
            },
            "posts": [p.model_dump(mode="json") for p in sorted(posts, key=lambda p: p.created_at, reverse=True)],
            "comments": [c.model_dump(mode="json") for c in sorted(comments, key=lambda c: c.created_at, reverse=True)],
        }
    # Return other user profiles
    profile = state.get_user_profile(username)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown user: {username}")
    posts = [p for p in state.posts if p.author_name.lower() == username.lower() and not p.is_removed]
    comments = [c for c in state.comments if c.author_name.lower() == username.lower() and not c.is_removed]
    return {
        "user": profile.model_dump(mode="json"),
        "posts": [p.model_dump(mode="json") for p in sorted(posts, key=lambda p: p.created_at, reverse=True)],
        "comments": [c.model_dump(mode="json") for c in sorted(comments, key=lambda c: c.created_at, reverse=True)],
    }


@router.get("/me")
def get_my_profile(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    return {
        "username": state.owner_username,
        "display_name": state.owner_display_name,
        "avatar_url": state.owner_avatar_url,
        "about": state.owner_about,
        "post_karma": state.owner_post_karma,
        "comment_karma": state.owner_comment_karma,
        "cake_day": state.owner_cake_day.isoformat() if state.owner_cake_day else None,
        "subscriptions": [s.model_dump(mode="json") for s in state.list_subscribed_subreddits()],
        "unread_messages": state.unread_message_count(),
        "unread_notifications": state.unread_notification_count(),
        "blocked_users": sorted(state.blocked_users),
    }


@router.get("/saved")
def get_saved(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    saved_posts = [p.model_dump(mode="json") for p in state.posts if p.id in state.saved_post_ids]
    saved_comments = [c.model_dump(mode="json") for c in state.comments if c.id in state.saved_comment_ids]
    return {"posts": saved_posts, "comments": saved_comments}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/settings")
def get_settings(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    return {"settings": state.settings.model_dump(mode="json")}


@router.put("/settings")
def update_settings(
    body: UpdateSettingsRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    updates = body.model_dump(exclude={"session_id"}, exclude_none=True)

    def apply_update(current_state: Any) -> Any:
        return state.update_settings(**updates)

    result = _mutate(
        session_manager, body.session_id,
        "reddit.settings.update",
        updates,
        apply_update,
    )
    return {"settings": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Subreddits list
# ---------------------------------------------------------------------------

@router.get("/subreddits")
def list_subreddits(
    session_id: str = Query(...),
    filter: str = Query("all"),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, session_id)
    if filter == "subscribed":
        subs = state.list_subscribed_subreddits()
    else:
        subs = sorted(state.subreddits, key=lambda s: s.subscriber_count, reverse=True)
    return {"items": [s.model_dump(mode="json") for s in subs]}


# ---------------------------------------------------------------------------
# Block / unblock
# ---------------------------------------------------------------------------

@router.post("/block/{username}")
def block_user(
    username: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    _mutate(
        session_manager, body.session_id,
        "reddit.user.block",
        {"username": username},
        lambda s: s.block_user(username),
    )
    return {"blocked": True, "username": username}


@router.post("/unblock/{username}")
def unblock_user(
    username: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _reddit_state(session_manager, body.session_id)
    _mutate(
        session_manager, body.session_id,
        "reddit.user.unblock",
        {"username": username},
        lambda s: s.unblock_user(username),
    )
    return {"blocked": False, "username": username}
