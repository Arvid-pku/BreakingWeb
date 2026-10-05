from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...tasks._evaluator import evaluate as unified_evaluate
from ...tasks._registry import get_task
from ..models.base import AuditEntry
from ..models.amazon import (
    AmazonState, CartItem, Address, PaymentMethod, Order, Review,
    ReturnRequest as ReturnRequestModel, PromoCode, ProductQuestion,
    ProductAnswer, GiftCard, Notification,
)
from ..security import (
    build_public_session_summary,
    has_controller_access,
    require_evaluation_access,
)
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/amazon", tags=["amazon"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    task_id: str
    seed: int | None = None
    degradation: dict | None = None  # Optional seed/server injections to apply post-seed
    variant_filename: str | None = None  # Load degradation from injector/variants/<filename>


class SessionScopedRequest(BaseModel):
    session_id: str


class AddToCartRequest(SessionScopedRequest):
    product_id: str
    quantity: int = 1
    variant_selections: dict[str, str] = Field(default_factory=dict)


class UpdateCartRequest(SessionScopedRequest):
    quantity: int


class PlaceOrderRequest(SessionScopedRequest):
    shipping_address_id: str
    payment_method_id: str
    promo_code: str | None = None


class AddAddressRequest(SessionScopedRequest):
    full_name: str
    street_address: str
    apt_suite: str = ""
    city: str
    state: str
    zip_code: str
    country: str = "United States"
    phone: str = ""
    is_default: bool = False


class UpdateAddressRequest(SessionScopedRequest):
    full_name: str | None = None
    street_address: str | None = None
    apt_suite: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None
    phone: str | None = None
    is_default: bool | None = None


class AddPaymentRequest(SessionScopedRequest):
    card_type: str
    last_four: str
    expiry: str
    holder_name: str
    is_default: bool = False


class AddReviewRequest(SessionScopedRequest):
    product_id: str
    rating: int
    title: str
    body: str


class WishlistRequest(SessionScopedRequest):
    product_id: str


class EvaluateRequest(SessionScopedRequest):
    task_id: str | None = None
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


class UpdateSettingsRequest(SessionScopedRequest):
    default_address_id: str | None = None
    default_payment_id: str | None = None
    prime_member: bool | None = None
    one_click_enabled: bool | None = None
    email_notifications: bool | None = None
    order_updates_email: bool | None = None
    deal_alerts_email: bool | None = None
    two_factor_enabled: bool | None = None
    language: str | None = None
    currency: str | None = None


class LoginRequest(SessionScopedRequest):
    email: str
    password: str = "simulated"


class ReturnRequest(SessionScopedRequest):
    order_id: str
    order_item_index: int
    reason: str


class UpdateReturnRequest(SessionScopedRequest):
    status: str
    resolution_note: str = ""


class ApplyPromoRequest(SessionScopedRequest):
    code: str


class ClearPromoRequest(SessionScopedRequest):
    pass


class AskQuestionRequest(SessionScopedRequest):
    product_id: str
    question: str


class AnswerQuestionRequest(SessionScopedRequest):
    answer: str
    is_seller: bool = False


class GiftCardRequest(SessionScopedRequest):
    code: str
    amount: float

    @classmethod
    def validate_code_format(cls, code: str) -> bool:
        """Gift card codes must match XXXX-XXXX-XXXX (alphanumeric)."""
        import re
        return bool(re.fullmatch(r"[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}", code))


class UpdateOrderStatusRequest(SessionScopedRequest):
    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured on app.state")
    return session_manager


def _amazon_state(session_manager: SessionManager, session_id: str) -> AmazonState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, AmazonState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not an Amazon session")
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
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _paginate(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "pages": max(1, (len(items) + page_size - 1) // page_size),
    }


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
# Degradation & Variants
# ---------------------------------------------------------------------------


@router.get("/degradation/{session_id}")
def get_client_degradation(session_id: str) -> dict[str, Any]:
    """Return client-layer degradation injections for a session as executable JS."""
    from ...injector.middleware import get_client_injections
    injections = get_client_injections(session_id)
    return {"session_id": session_id, "client_injections": injections}


@router.get("/variants")
def list_variants() -> list[dict[str, Any]]:
    """List available degradation variants for the Amazon environment."""
    from pathlib import Path
    import yaml

    variants_dir = Path(__file__).parent.parent.parent / "injector" / "variants"
    result = []

    if variants_dir.exists():
        for f in sorted(variants_dir.glob("amazon_*.yaml")):
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


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


@router.post("/session")
def create_session(body: SessionCreateRequest, request: Request = None, session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    task = get_task(body.task_id)
    if task.env_id != "amazon":
        raise HTTPException(status_code=404, detail=f"Unknown Amazon task_id: {body.task_id}")

    # Load/validate degradation before creating the session so mismatched variants
    # never allocate live benchmark state.
    degradation = dict(body.degradation) if body.degradation else None
    if body.variant_filename and not degradation:
        # Reject path traversal attempts in variant filenames
        if "/" in body.variant_filename or "\\" in body.variant_filename or ".." in body.variant_filename:
            raise HTTPException(status_code=400, detail="Invalid variant filename")
        # Handle auto-generated variants (filename starts with __auto__)
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

    session_id, resolved_targets, actual_seed = session_manager.create_session("amazon", body.task_id, body.seed)
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
    # Must run after degradation injections so initial reflects post-injection state.
    if isinstance(state, AmazonState):
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
    # Only include resolved_targets for privileged callers (harness/tests).
    # Agents in the browser must not see raw target values.
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


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


@router.get("/products")
def list_products(
    session_id: str = Query(...),
    q: str | None = Query(None),
    category: str | None = Query(None),
    min_price: float | None = Query(None),
    max_price: float | None = Query(None),
    min_rating: float | None = Query(None),
    sort_by: str = Query("relevance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    products = state.search_products(
        query=q or "",
        category=category,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        sort_by=sort_by,
    )
    items = [p.model_dump(mode="json") for p in products]
    return _paginate(items, page, page_size)


@router.get("/products/{product_id}")
def get_product(
    product_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    product = state.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Unknown product id: {product_id}")
    # Track recently viewed and browsing history
    state.add_to_browsing_history(product_id)
    reviews = [r.model_dump(mode="json") for r in state.reviews if r.product_id == product_id]
    return {
        "product": product.model_dump(mode="json"),
        "reviews": reviews,
    }


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


def _enrich_cart_item(state: AmazonState, item_data: dict[str, Any]) -> dict[str, Any]:
    """Add product display fields to a cart item dict."""
    product = state.get_product(item_data.get("product_id", ""))
    if product is not None:
        item_data["image_url"] = product.image_url
        item_data["category"] = product.category
        item_data["subcategory"] = product.subcategory
        item_data["prime_eligible"] = product.prime_eligible
        item_data["in_stock"] = product.in_stock
    return item_data


def _enrich_order(state: AmazonState, order_data: dict[str, Any]) -> dict[str, Any]:
    """Add product display fields to serialized order items without changing stored order state."""
    for item in order_data.get("items", []):
        if not isinstance(item, dict):
            continue
        product = state.get_product(item.get("product_id", ""))
        if product is not None:
            if not item.get("image_url"):
                item["image_url"] = product.image_url
            item["category"] = product.category
            item["subcategory"] = product.subcategory
    return order_data


def _enrich_return(state: AmazonState, return_data: dict[str, Any]) -> dict[str, Any]:
    """Add product display fields to serialized returns for order/returns pages."""
    product = state.get_product(return_data.get("product_id", ""))
    if product is not None:
        if not return_data.get("image_url"):
            return_data["image_url"] = product.image_url
        return_data["category"] = product.category
        return_data["subcategory"] = product.subcategory
    return return_data


@router.get("/cart")
def get_cart(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    items = [_enrich_cart_item(state, item.model_dump(mode="json")) for item in state.cart_items]
    totals = state.cart_total()
    return {
        "items": items,
        "totals": totals,
    }


@router.post("/cart/add")
def add_to_cart(
    body: AddToCartRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "amazon.cart.add",
        {"product_id": body.product_id, "quantity": body.quantity},
        lambda s: s.add_to_cart(body.product_id, body.quantity, body.variant_selections),
    )
    return {"cart_item": _enrich_cart_item(state, result.model_dump(mode="json"))}


@router.put("/cart/{item_id}")
def update_cart_item(
    item_id: str,
    body: UpdateCartRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "amazon.cart.update",
        {"item_id": item_id, "quantity": body.quantity},
        lambda s: s.update_cart_quantity(item_id, body.quantity),
    )
    return {"cart_item": result.model_dump(mode="json")}


@router.delete("/cart/{item_id}")
def remove_cart_item(
    item_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "amazon.cart.remove",
        {"item_id": item_id},
        lambda s: s.remove_from_cart(item_id),
    )
    return {"cart_item": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Checkout & Orders
# ---------------------------------------------------------------------------


@router.post("/checkout")
def place_order(
    body: PlaceOrderRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    def do_checkout(s: Any) -> Order:
        if body.promo_code:
            s.apply_promo_code(body.promo_code)
        return s.place_order(
            body.shipping_address_id,
            body.payment_method_id,
            body.promo_code,
        )

    result = _mutate(
        session_manager, body.session_id,
        "amazon.checkout",
        {
            "shipping_address_id": body.shipping_address_id,
            "payment_method_id": body.payment_method_id,
            "promo_code": body.promo_code,
        },
        do_checkout,
    )
    return {"order": _enrich_order(state, result.model_dump(mode="json"))}


@router.get("/orders")
def list_orders(
    session_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    items = [_enrich_order(state, order.model_dump(mode="json")) for order in state.orders]
    return _paginate(items, page, page_size)


@router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    order = state.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Unknown order id: {order_id}")
    if order_id not in state.viewed_order_ids:
        state.viewed_order_ids.insert(0, order_id)
        if len(state.viewed_order_ids) > 50:
            state.viewed_order_ids = state.viewed_order_ids[:50]
        state.touch()
    return {"order": _enrich_order(state, order.model_dump(mode="json"))}


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------


@router.get("/addresses")
def list_addresses(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    return {"items": [addr.model_dump(mode="json") for addr in state.addresses]}


@router.post("/addresses")
def add_address(
    body: AddAddressRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    def do_add(s: Any) -> Address:
        address = Address(
            id=s._next_id("addr"),
            full_name=body.full_name,
            street_address=body.street_address,
            apt_suite=body.apt_suite,
            city=body.city,
            state=body.state,
            zip_code=body.zip_code,
            country=body.country,
            phone=body.phone,
            is_default=body.is_default,
        )
        return s.add_address(address)

    result = _mutate(
        session_manager, body.session_id,
        "amazon.address.add",
        {"full_name": body.full_name, "city": body.city},
        do_add,
    )
    return {"address": result.model_dump(mode="json")}


@router.put("/addresses/{address_id}")
def update_address(
    address_id: str,
    body: UpdateAddressRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    updates = body.model_dump(exclude={"session_id"}, exclude_unset=True)
    result = _mutate(
        session_manager, body.session_id,
        "amazon.address.update",
        {"address_id": address_id, **updates},
        lambda s: s.update_address(address_id, **updates),
    )
    return {"address": result.model_dump(mode="json")}


@router.delete("/addresses/{address_id}")
def remove_address(
    address_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "amazon.address.remove",
        {"address_id": address_id},
        lambda s: s.remove_address(address_id),
    )
    return {"address": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Payment Methods
# ---------------------------------------------------------------------------


@router.get("/payment-methods")
def list_payment_methods(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    return {"items": [pm.model_dump(mode="json") for pm in state.payment_methods]}


@router.post("/payment-methods")
def add_payment_method(
    body: AddPaymentRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    def do_add(s: Any) -> PaymentMethod:
        pm = PaymentMethod(
            id=s._next_id("pm"),
            card_type=body.card_type,
            last_four=body.last_four,
            expiry=body.expiry,
            holder_name=body.holder_name,
            is_default=body.is_default,
        )
        return s.add_payment_method(pm)

    result = _mutate(
        session_manager, body.session_id,
        "amazon.payment.add",
        {"card_type": body.card_type, "last_four": body.last_four},
        do_add,
    )
    return {"payment_method": result.model_dump(mode="json")}


@router.delete("/payment-methods/{pm_id}")
def remove_payment_method(
    pm_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "amazon.payment.remove",
        {"pm_id": pm_id},
        lambda s: s.remove_payment_method(pm_id),
    )
    return {"payment_method": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------


@router.get("/wishlist")
def get_wishlist(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    # Resolve product details for each wishlist product_id
    products = []
    for pid in state.wishlist:
        product = state.get_product(pid)
        if product is not None:
            products.append(product.model_dump(mode="json"))
    return {"items": products}


@router.post("/wishlist/add")
def add_to_wishlist(
    body: WishlistRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    _mutate(
        session_manager, body.session_id,
        "amazon.wishlist.add",
        {"product_id": body.product_id},
        lambda s: s.add_to_wishlist(body.product_id),
    )
    return {"ok": True, "product_id": body.product_id}


@router.post("/wishlist/remove")
def remove_from_wishlist(
    body: WishlistRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    _mutate(
        session_manager, body.session_id,
        "amazon.wishlist.remove",
        {"product_id": body.product_id},
        lambda s: s.remove_from_wishlist(body.product_id),
    )
    return {"ok": True, "product_id": body.product_id}


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


@router.get("/products/{product_id}/reviews")
def get_product_reviews(
    product_id: str,
    session_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    reviews = [r.model_dump(mode="json") for r in state.reviews if r.product_id == product_id]
    return _paginate(reviews, page, page_size)


@router.post("/products/{product_id}/reviews")
def add_review(
    product_id: str,
    body: AddReviewRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    def do_add(s: Any) -> Review:
        review = Review(
            id=s._next_id("review"),
            product_id=product_id,
            author_name=s.owner_name,
            rating=body.rating,
            title=body.title,
            body=body.body,
            helpful_count=0,
            verified_purchase=True,
            created_at=datetime.now(timezone.utc),
        )
        return s.add_review(review)

    result = _mutate(
        session_manager, body.session_id,
        "amazon.review.add",
        {"product_id": product_id, "rating": body.rating, "title": body.title},
        do_add,
    )
    return {"review": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings")
def get_settings(session_id: str = Query(...), session_manager: SessionManager = Depends(get_session_manager)) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    return {"settings": state.settings.model_dump(mode="json")}


@router.put("/settings")
def update_settings(
    body: UpdateSettingsRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    updates = body.model_dump(exclude={"session_id"}, exclude_none=True)

    def apply_update(current_state: Any) -> Any:
        for key, value in updates.items():
            setattr(current_state.settings, key, value)
        default_address_id = updates.get("default_address_id")
        if default_address_id is not None:
            for address in current_state.addresses:
                address.is_default = address.id == default_address_id
        default_payment_id = updates.get("default_payment_id")
        if default_payment_id is not None:
            for payment_method in current_state.payment_methods:
                payment_method.is_default = payment_method.id == default_payment_id
        current_state.touch()
        return current_state.settings

    result = _mutate(
        session_manager, body.session_id,
        "amazon.settings.update",
        updates,
        apply_update,
    )
    return {"settings": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Search (alias for /products with q param)
# ---------------------------------------------------------------------------


@router.get("/search")
def search_products(
    q: str = Query(...),
    session_id: str = Query(...),
    category: str | None = Query(None),
    min_price: float | None = Query(None),
    max_price: float | None = Query(None),
    min_rating: float | None = Query(None),
    sort_by: str = Query("relevance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    # Track search history
    if q and q not in state.search_history:
        state.search_history.insert(0, q)
        if len(state.search_history) > 50:
            state.search_history = state.search_history[:50]
        state.touch()
    products = state.search_products(
        query=q,
        category=category,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        sort_by=sort_by,
    )
    items = [p.model_dump(mode="json") for p in products]
    payload = _paginate(items, page, page_size)
    payload["query"] = q
    return payload


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@router.post("/login")
def login(
    body: LoginRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    _mutate(
        session_manager, body.session_id,
        "amazon.auth.login",
        {"email": body.email},
        lambda s: s.login(body.email, body.password),
    )
    return {
        "ok": True,
        "email": body.email,
        "message": "Login successful (simulated)",
    }


@router.post("/logout")
def logout(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    _mutate(
        session_manager, body.session_id,
        "amazon.auth.logout",
        {},
        lambda s: setattr(s, "is_logged_in", False) or s.touch() or True,
    )
    return {"ok": True, "message": "Logged out (simulated)"}


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------


@router.get("/returns")
def list_returns(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    items = [_enrich_return(state, r.model_dump(mode="json")) for r in state.returns]
    return {"items": items, "total": len(items)}


@router.post("/returns")
def create_return(
    body: ReturnRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    result = _mutate(
        session_manager, body.session_id,
        "amazon.return.create",
        {"order_id": body.order_id, "order_item_index": body.order_item_index, "reason": body.reason},
        lambda s: s.request_return(body.order_id, body.order_item_index, body.reason),
    )
    return {"return": _enrich_return(state, result.model_dump(mode="json"))}


@router.get("/returns/{return_id}")
def get_return(
    return_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    ret = next((r for r in state.returns if r.id == return_id), None)
    if ret is None:
        raise HTTPException(status_code=404, detail=f"Unknown return id: {return_id}")
    return {"return": _enrich_return(state, ret.model_dump(mode="json"))}


@router.put("/returns/{return_id}")
def update_return(
    return_id: str,
    body: UpdateReturnRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    ret = next((r for r in state.returns if r.id == return_id), None)
    if ret is None:
        raise HTTPException(status_code=404, detail=f"Unknown return id: {return_id}")

    def do_update(s: Any) -> ReturnRequestModel:
        ret.status = body.status
        if body.resolution_note:
            ret.resolution_note = body.resolution_note
        s.touch()
        return ret

    result = _mutate(
        session_manager, body.session_id,
        "amazon.return.update",
        {"return_id": return_id, "status": body.status},
        do_update,
    )
    return {"return": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Promo Codes
# ---------------------------------------------------------------------------


@router.post("/promo/apply")
def apply_promo(
    body: ApplyPromoRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    promo = state.get_promo_code(body.code)
    if promo is None:
        raise HTTPException(status_code=404, detail=f"Unknown promo code: {body.code}")

    def do_apply(s: Any) -> PromoCode:
        s.apply_promo_code(body.code)
        return promo

    result = _mutate(
        session_manager, body.session_id,
        "amazon.promo.apply",
        {"code": body.code},
        do_apply,
    )
    return {"promo": result.model_dump(mode="json")}


@router.post("/promo/clear")
def clear_promo(
    body: ClearPromoRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    _mutate(
        session_manager,
        body.session_id,
        "amazon.promo.clear",
        {},
        lambda s: s.clear_promo_code() or True,
    )
    return {"ok": True}


@router.get("/promo/validate/{code}")
def validate_promo(
    code: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    promo = next((p for p in state.promo_codes if p.code == code), None)
    if promo is None:
        return {"valid": False, "reason": "Unknown promo code"}
    if not promo.active:
        return {"valid": False, "reason": "Promo code is no longer active"}
    if promo.used_count >= promo.max_uses:
        return {"valid": False, "reason": "Promo code has been fully redeemed"}
    return {"valid": True, "promo": promo.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------


@router.get("/products/{product_id}/questions")
def list_product_questions(
    product_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    questions = [q.model_dump(mode="json") for q in state.questions if q.product_id == product_id]
    return {"items": questions, "total": len(questions)}


@router.post("/products/{product_id}/questions")
def ask_question(
    product_id: str,
    body: AskQuestionRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    product = state.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Unknown product id: {product_id}")

    def do_ask(s: Any) -> ProductQuestion:
        return s.ask_question(product_id, body.question)

    result = _mutate(
        session_manager, body.session_id,
        "amazon.question.ask",
        {"product_id": product_id, "question": body.question},
        do_ask,
    )
    return {"question": result.model_dump(mode="json")}


@router.post("/products/{product_id}/questions/{question_id}/answer")
def answer_question(
    product_id: str,
    question_id: str,
    body: AnswerQuestionRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    question = next(
        (q for q in state.questions if q.id == question_id and q.product_id == product_id),
        None,
    )
    if question is None:
        raise HTTPException(status_code=404, detail=f"Unknown question id: {question_id}")

    answer = ProductAnswer(
        answer=body.answer,
        author_name=state.owner_name,
        answered_at=datetime.now(timezone.utc),
        is_seller_response=body.is_seller,
    )

    def do_answer(s: Any) -> ProductQuestion:
        question.answers.append(answer)
        s.touch()
        return question

    result = _mutate(
        session_manager, body.session_id,
        "amazon.question.answer",
        {"question_id": question_id, "answer": body.answer},
        do_answer,
    )
    return {"question": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Gift Cards
# ---------------------------------------------------------------------------


@router.post("/gift-cards/add")
def add_gift_card(
    body: GiftCardRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    if not GiftCardRequest.validate_code_format(body.code):
        raise HTTPException(
            status_code=400,
            detail="Invalid gift card code. Must be in format XXXX-XXXX-XXXX (letters and digits).",
        )
    state = _amazon_state(session_manager, body.session_id)

    def do_add(s: Any) -> GiftCard:
        return s.add_gift_card(body.code, body.amount)

    result = _mutate(
        session_manager, body.session_id,
        "amazon.gift_card.add",
        {"code": body.code, "amount": body.amount},
        do_add,
    )
    return {"gift_card": result.model_dump(mode="json")}


@router.post("/gift-cards/{gift_card_id}/redeem")
def redeem_gift_card(
    gift_card_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    gc = next((g for g in state.gift_cards if g.id == gift_card_id), None)
    if gc is None:
        raise HTTPException(status_code=404, detail=f"Unknown gift card id: {gift_card_id}")
    if gc.redeemed:
        raise HTTPException(status_code=400, detail="Gift card already redeemed")

    def do_redeem(s: Any) -> GiftCard:
        gc.redeemed = True
        s.settings.gift_card_balance += gc.balance
        gc.balance = 0.0
        s.touch()
        return gc

    result = _mutate(
        session_manager, body.session_id,
        "amazon.gift_card.redeem",
        {"gift_card_id": gift_card_id},
        do_redeem,
    )
    return {"gift_card": result.model_dump(mode="json"), "new_balance": state.settings.gift_card_balance}


@router.get("/gift-cards")
def list_gift_cards(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    items = [gc.model_dump(mode="json") for gc in state.gift_cards]
    return {"items": items, "total": len(items), "account_balance": state.settings.gift_card_balance}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@router.get("/notifications")
def list_notifications(
    session_id: str = Query(...),
    unread_only: bool = Query(False),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    notifs = state.notifications
    if unread_only:
        notifs = [n for n in notifs if not n.read]
    items = [n.model_dump(mode="json") for n in notifs]
    return {"items": items, "total": len(items)}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    notif = next((n for n in state.notifications if n.id == notification_id), None)
    if notif is None:
        raise HTTPException(status_code=404, detail=f"Unknown notification id: {notification_id}")

    def do_mark(s: Any) -> Notification:
        notif.read = True
        s.touch()
        return notif

    result = _mutate(
        session_manager, body.session_id,
        "amazon.notification.read",
        {"notification_id": notification_id},
        do_mark,
    )
    return {"notification": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Order Management
# ---------------------------------------------------------------------------


@router.put("/orders/{order_id}/status")
def update_order_status(
    order_id: str,
    body: UpdateOrderStatusRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)

    order = state.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Unknown order id: {order_id}")

    def do_update(s: Any) -> Order:
        order.status = body.status
        s.touch()
        return order

    result = _mutate(
        session_manager, body.session_id,
        "amazon.order.update_status",
        {"order_id": order_id, "status": body.status},
        do_update,
    )
    return {"order": result.model_dump(mode="json")}


@router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "amazon.order.cancel",
        {"order_id": order_id},
        lambda s: s.cancel_order(order_id),
    )
    return {"order": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Categories & Deals
# ---------------------------------------------------------------------------


@router.get("/categories")
def list_categories(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    categories: dict[str, set[str]] = {}
    for product in state.products:
        if product.category not in categories:
            categories[product.category] = set()
        categories[product.category].add(product.subcategory)
    items = [
        {"category": cat, "subcategories": sorted(subs)}
        for cat, subs in sorted(categories.items())
    ]
    return {"items": items, "total": len(items)}


@router.get("/deals")
def list_deals(
    session_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    # Products on sale = those with a list_price higher than price.
    # Sort by discount percentage descending so task-seeded featured deals
    # (which carry the biggest markdowns) surface on the first page
    # instead of being buried alphabetically with the baseline catalog.
    on_sale = [
        p for p in state.products
        if p.list_price is not None and p.list_price > p.price
    ]
    on_sale.sort(
        key=lambda p: (p.list_price - p.price) / p.list_price if p.list_price else 0.0,
        reverse=True,
    )
    deals = [p.model_dump(mode="json") for p in on_sale]
    return _paginate(deals, page, page_size)


@router.get("/browsing-history")
def get_browsing_history(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    # Use the dedicated browsing_history list if populated, otherwise fall
    # back to the recently_viewed product-id list for backward compat.
    if state.browsing_history:
        items = [bh.model_dump(mode="json") for bh in state.browsing_history]
    else:
        items = [{"product_id": pid} for pid in state.recently_viewed]
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


@router.get("/account")
def get_account(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _amazon_state(session_manager, session_id)
    return {
        "owner_name": state.owner_name,
        "email": state.owner_email,
        "is_logged_in": state.is_logged_in,
        "settings": state.settings.model_dump(mode="json"),
    }


@router.put("/account/password")
def change_password(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    # Simulated password change -- always succeeds
    state = _amazon_state(session_manager, body.session_id)
    _mutate(
        session_manager, body.session_id,
        "amazon.account.password_change",
        {},
        lambda s: (setattr(s, "password_hash", "simulated_new_hash"), s.touch(), True)[-1],
    )
    return {"ok": True, "message": "Password changed (simulated)"}
