from __future__ import annotations

import random
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from ...tasks._evaluator import evaluate as unified_evaluate
from ...tasks._registry import get_task
from ..models.base import AuditEntry
from ..models.robinhood import (
    OptionsLeg,
    RobinhoodState,
)
from ..security import (
    build_public_session_summary,
    has_controller_access,
    require_evaluation_access,
)
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/robinhood", tags=["robinhood"])


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


# --- Orders ---

class PlaceOrderRequest(SessionScopedRequest):
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"] = "market"
    quantity: float | str
    limit_price: float | str | None = None
    stop_price: float | str | None = None
    trail_amount: float | str | None = None
    trail_pct: float | str | None = None
    time_in_force: Literal["gfd", "gtc", "ioc", "opg"] = "gfd"
    extended_hours: bool = False


class CancelOrderRequest(SessionScopedRequest):
    pass


# --- Options ---

class OptionsLegInput(BaseModel):
    # The OptionsTrade page submits ``underlying_symbol`` while older API
    # callers use ``symbol``. Accept both names so leg.symbol is populated
    # either way; without this alias the frontend's value silently gets
    # dropped to None and OptionsLeg.underlying_symbol is saved as None,
    # causing every options task's canonical_diff predicates that reference
    # ``leg.underlying_symbol`` to fail.
    model_config = ConfigDict(populate_by_name=True)

    side: Literal["buy", "sell"]
    option_type: Literal["call", "put"]
    strike: str
    expiration: date
    quantity: int
    premium: str
    symbol: str | None = Field(
        default=None,
        validation_alias=AliasChoices("symbol", "underlying_symbol"),
    )


class PlaceOptionsOrderRequest(SessionScopedRequest):
    strategy: str
    legs: list[OptionsLegInput] = Field(default_factory=list)


# --- Watchlists ---

class CreateWatchlistRequest(SessionScopedRequest):
    name: str
    symbols: list[str] = Field(default_factory=list)


class UpdateWatchlistRequest(SessionScopedRequest):
    name: str | None = None


class AddSymbolRequest(SessionScopedRequest):
    symbol: str


# --- Transfers / Banks ---

class InitiateTransferRequest(SessionScopedRequest):
    direction: Literal["deposit", "withdrawal"]
    amount: float | str
    bank_account_id: str


class LinkBankRequest(SessionScopedRequest):
    bank_name: str
    account_type: Literal["checking", "savings"]
    last_four: str


# --- Recurring Investments ---

class CreateRecurringRequest(SessionScopedRequest):
    symbol: str
    amount: float | str
    frequency: Literal["daily", "weekly", "biweekly", "monthly"]
    next_execution_date: date


class UpdateRecurringRequest(SessionScopedRequest):
    amount: float | str | None = None
    frequency: str | None = None
    status: str | None = None


# --- Price Alerts ---

class CreateAlertRequest(SessionScopedRequest):
    symbol: str
    condition: Literal["above", "below"]
    target_price: float | str


# --- Settings ---

class UpdateSettingsRequest(SessionScopedRequest):
    display_theme: str | None = None
    default_order_type: str | None = None
    reinvest_dividends: bool | None = None
    extended_hours_enabled: bool | None = None
    biometric_login: bool | None = None
    two_factor_method: str | None = None
    notification_prefs: dict[str, bool] | None = None


# --- Security ---

class Update2FARequest(SessionScopedRequest):
    method: Literal["sms", "authenticator", "none"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured on app.state")
    return session_manager


def _robinhood_state(session_manager: SessionManager, session_id: str) -> RobinhoodState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, RobinhoodState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not a Robinhood session")
    state.tick()  # Advance prices based on wall-clock time
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
    if task.env_id != "robinhood":
        raise HTTPException(status_code=404, detail=f"Unknown Robinhood task_id: {body.task_id}")

    degradation = dict(body.degradation) if body.degradation else None
    if body.variant_filename and not degradation:
        # Reject path traversal attempts in variant filenames
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

    session_id, resolved_targets, actual_seed = session_manager.create_session("robinhood", body.task_id, body.seed)
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

    # Capture baseline snapshot for collateral-damage detection (always, not just degraded sessions).
    # Must run AFTER degradation injections so the evaluator's initial baseline
    # reflects the post-injection state, not the pre-degradation seed state.
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
    variants_dir = Path(__file__).parent.parent.parent / "injector" / "variants"
    if not variants_dir.is_dir():
        return []
    import yaml
    results = []
    for f in sorted(variants_dir.glob("*.yaml")):
        if not f.name.startswith("rh_"):
            continue
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
# Account
# ---------------------------------------------------------------------------

@router.get("/account")
def get_account(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return state.session_summary()


@router.get("/account/portfolio")
def get_portfolio(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    total_value = state.portfolio_value
    day_change = sum(
        (p.current_price * p.quantity * p.day_change_pct / Decimal("100"))
        for p in state.positions
    )
    return {
        "portfolio_value": str(total_value),
        "cash_balance": str(state.cash_balance),
        "day_change": str(day_change),
        "positions_count": len(state.positions),
    }


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@router.get("/positions")
def list_positions(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [p.model_dump(mode="json") for p in state.positions]}


@router.get("/positions/{symbol}")
def get_position(
    symbol: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    pos = state.get_position(symbol)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No position for symbol: {symbol}")
    return {"position": pos.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Stocks
# ---------------------------------------------------------------------------

@router.get("/stocks/{symbol}")
def get_stock(
    symbol: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    stock = state.get_stock(symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown stock: {symbol}")
    return {"stock": stock.model_dump(mode="json")}


@router.get("/stocks/{symbol}/chart")
def get_stock_chart(
    symbol: str,
    session_id: str = Query(...),
    period: str = Query("1M"),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    stock = state.get_stock(symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown stock: {symbol}")
    return {
        "symbol": symbol,
        "period": period,
        "prices": [hp.model_dump(mode="json") for hp in stock.historical_prices],
    }


@router.get("/stocks/{symbol}/options")
def get_stock_options(
    symbol: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    chain = state.options_chains.get(symbol, [])
    return {"symbol": symbol, "contracts": [c.model_dump(mode="json") for c in chain]}


@router.get("/stocks/{symbol}/earnings")
def get_stock_earnings(
    symbol: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    events = [e for e in state.earnings_events if e.symbol == symbol]
    return {"symbol": symbol, "items": [e.model_dump(mode="json") for e in events]}


@router.get("/stocks/{symbol}/dividends")
def get_stock_dividends(
    symbol: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    divs = [d for d in state.dividend_schedule if d.symbol == symbol]
    return {"symbol": symbol, "items": [d.model_dump(mode="json") for d in divs]}


@router.get("/prices")
def get_live_prices(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    """Lightweight endpoint for frontend price polling."""
    state = _robinhood_state(session_manager, session_id)
    engine = state._price_engine
    prices = {}
    for stock in state.stocks:
        prices[stock.symbol] = {
            "price": str(stock.price),
            "day_change": str(stock.day_change),
            "day_change_pct": str(stock.day_change_pct),
            "bid": str(stock.bid),
            "ask": str(stock.ask),
        }
    filled_ids = [
        o.id for o in state.orders
        if o.status == "filled" and o.filled_at is not None
    ]
    return {
        "tick": engine.tick_count if engine else 0,
        "prices": prices,
        "portfolio_value": str(state.portfolio_value),
        "cash_balance": str(state.cash_balance),
        "pending_orders_filled": filled_ids,
    }


@router.get("/search")
def search_stocks(
    session_id: str = Query(...),
    q: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    results = state.search_stocks(q)
    return {"items": [s.model_dump(mode="json") for s in results]}


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@router.post("/orders")
def place_order(
    body: PlaceOrderRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.order.place",
        {"symbol": body.symbol, "side": body.side, "order_type": body.order_type, "quantity": body.quantity},
        lambda s: s.place_order(
            symbol=body.symbol,
            side=body.side,
            order_type=body.order_type,
            quantity=Decimal(str(body.quantity)),
            limit_price=Decimal(str(body.limit_price)) if body.limit_price is not None else None,
            stop_price=Decimal(str(body.stop_price)) if body.stop_price is not None else None,
            trail_amount=Decimal(str(body.trail_amount)) if body.trail_amount is not None else None,
            trail_pct=Decimal(str(body.trail_pct)) if body.trail_pct is not None else None,
            time_in_force=body.time_in_force,
            extended_hours=body.extended_hours,
        ),
    )
    return {"order": result.model_dump(mode="json")}


@router.get("/orders")
def list_orders(
    session_id: str = Query(...),
    status: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    orders = list(state.orders)
    if status is not None:
        orders = [o for o in orders if o.status == status]
    return {"items": [o.model_dump(mode="json") for o in orders]}


@router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    order = state.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Unknown order id: {order_id}")
    return order.model_dump(mode="json")


@router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.order.cancel",
        {"order_id": order_id},
        lambda s: s.cancel_order(order_id),
    )
    return {"order": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

@router.post("/options/orders")
def place_options_order(
    body: PlaceOptionsOrderRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    legs = [
        OptionsLeg(
            underlying_symbol=leg.symbol,
            side=leg.side,
            option_type=leg.option_type,
            strike=Decimal(leg.strike),
            expiration=leg.expiration,
            quantity=leg.quantity,
            premium=Decimal(leg.premium),
        )
        for leg in body.legs
    ]
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.options.order.place",
        {"strategy": body.strategy, "legs_count": len(legs)},
        lambda s: s.place_options_order(strategy=body.strategy, legs=legs),
    )
    return {"order": result.model_dump(mode="json")}


@router.get("/options/orders")
def list_options_orders(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [o.model_dump(mode="json") for o in state.options_orders]}


@router.get("/options/orders/{order_id}")
def get_options_order(
    order_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    order = next((o for o in state.options_orders if o.id == order_id), None)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Unknown options order id: {order_id}")
    return order.model_dump(mode="json")


@router.get("/options/positions")
def list_options_positions(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [p.model_dump(mode="json") for p in state.options_positions]}


# ---------------------------------------------------------------------------
# Watchlists
# ---------------------------------------------------------------------------

@router.get("/watchlists")
def list_watchlists(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [w.model_dump(mode="json") for w in state.watchlists]}


@router.post("/watchlists")
def create_watchlist(
    body: CreateWatchlistRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.watchlist.create",
        {"name": body.name, "symbols": body.symbols},
        lambda s: s.create_watchlist(body.name, body.symbols or None),
    )
    return {"watchlist": result.model_dump(mode="json")}


@router.put("/watchlists/{watchlist_id}")
def update_watchlist(
    watchlist_id: str,
    body: UpdateWatchlistRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.watchlist.rename",
        {"watchlist_id": watchlist_id, "name": body.name},
        lambda s: s.rename_watchlist(watchlist_id, body.name or ""),
    )
    return {"watchlist": result.model_dump(mode="json")}


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist(
    watchlist_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "robinhood.watchlist.delete",
        {"watchlist_id": watchlist_id},
        lambda s: s.delete_watchlist(watchlist_id),
    )
    return {"watchlist": result.model_dump(mode="json")}


@router.post("/watchlists/{watchlist_id}/symbols")
def add_watchlist_symbol(
    watchlist_id: str,
    body: AddSymbolRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.watchlist.add_symbol",
        {"watchlist_id": watchlist_id, "symbol": body.symbol},
        lambda s: s.add_to_watchlist(watchlist_id, body.symbol),
    )
    return {"watchlist": result.model_dump(mode="json")}


@router.delete("/watchlists/{watchlist_id}/symbols/{symbol}")
def remove_watchlist_symbol(
    watchlist_id: str,
    symbol: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "robinhood.watchlist.remove_symbol",
        {"watchlist_id": watchlist_id, "symbol": symbol},
        lambda s: s.remove_from_watchlist(watchlist_id, symbol),
    )
    return {"watchlist": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Transfers & Banks
# ---------------------------------------------------------------------------

@router.get("/transfers")
def list_transfers(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [t.model_dump(mode="json") for t in state.transfers]}


@router.post("/transfers")
def initiate_transfer(
    body: InitiateTransferRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.transfer.initiate",
        {"direction": body.direction, "amount": body.amount, "bank_account_id": body.bank_account_id},
        lambda s: s.initiate_transfer(body.direction, Decimal(str(body.amount)), body.bank_account_id),
    )
    return {"transfer": result.model_dump(mode="json")}


@router.get("/banks")
def list_banks(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [b.model_dump(mode="json") for b in state.linked_banks]}


@router.post("/banks")
def link_bank(
    body: LinkBankRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.bank.link",
        {"bank_name": body.bank_name, "account_type": body.account_type, "last_four": body.last_four},
        lambda s: s.link_bank(body.bank_name, body.account_type, body.last_four),
    )
    return {"bank": result.model_dump(mode="json")}


@router.delete("/banks/{bank_id}")
def unlink_bank(
    bank_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "robinhood.bank.unlink",
        {"bank_id": bank_id},
        lambda s: s.unlink_bank(bank_id),
    )
    return {"bank": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Recurring Investments
# ---------------------------------------------------------------------------

@router.get("/recurring")
def list_recurring(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [r.model_dump(mode="json") for r in state.recurring_investments]}


@router.post("/recurring")
def create_recurring(
    body: CreateRecurringRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.recurring.create",
        {"symbol": body.symbol, "amount": body.amount, "frequency": body.frequency},
        lambda s: s.create_recurring_investment(
            body.symbol, Decimal(str(body.amount)), body.frequency, body.next_execution_date,
        ),
    )
    return {"recurring": result.model_dump(mode="json")}


@router.put("/recurring/{ri_id}")
def update_recurring(
    ri_id: str,
    body: UpdateRecurringRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.recurring.update",
        {"ri_id": ri_id},
        lambda s: s.update_recurring_investment(
            ri_id,
            amount=Decimal(str(body.amount)) if body.amount is not None else None,
            frequency=body.frequency,
            status=body.status,
        ),
    )
    return {"recurring": result.model_dump(mode="json")}


@router.delete("/recurring/{ri_id}")
def delete_recurring(
    ri_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "robinhood.recurring.delete",
        {"ri_id": ri_id},
        lambda s: s.delete_recurring_investment(ri_id),
    )
    return {"recurring": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@router.get("/transactions")
def list_transactions(
    session_id: str = Query(...),
    type: str | None = Query(None),
    symbol: str | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    items = state.list_transactions(type=type, symbol=symbol, from_date=from_date, to_date=to_date)
    return {"items": [t.model_dump(mode="json") for t in items]}


# ---------------------------------------------------------------------------
# Tax
# ---------------------------------------------------------------------------

@router.get("/tax/documents")
def list_tax_documents(
    session_id: str = Query(...),
    year: int | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    docs = list(state.tax_documents)
    if year is not None:
        docs = [d for d in docs if d.tax_year == year]
    return {"items": [d.model_dump(mode="json") for d in docs]}


@router.get("/tax/documents/{doc_id}")
def get_tax_document(
    doc_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    doc = next((d for d in state.tax_documents if d.id == doc_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Unknown tax document id: {doc_id}")
    return doc.model_dump(mode="json")


@router.get("/tax/gains")
def list_realized_gains(
    session_id: str = Query(...),
    year: int | None = Query(None),
    symbol: str | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    gains: list[dict[str, Any]] = []
    for doc in state.tax_documents:
        if year is not None and doc.tax_year != year:
            continue
        for g in doc.realized_gains:
            if symbol is not None and g.symbol != symbol:
                continue
            gains.append(g.model_dump(mode="json"))
    return {"items": gains}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications")
def list_notifications(
    session_id: str = Query(...),
    type: str | None = Query(None),
    unread: bool | None = Query(None),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    notifs = list(state.notifications)
    if type is not None:
        notifs = [n for n in notifs if n.type == type]
    if unread is not None:
        notifs = [n for n in notifs if n.is_read is (not unread)]
    return {"items": [n.model_dump(mode="json") for n in notifs]}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.notification.read",
        {"notification_id": notification_id},
        lambda s: s.mark_notification_read(notification_id),
    )
    return {"notification": result.model_dump(mode="json")}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    body: SessionScopedRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.notification.read_all",
        {},
        lambda s: s.mark_all_notifications_read(),
    )
    return {"marked_count": result, "count": result}


# ---------------------------------------------------------------------------
# Price Alerts
# ---------------------------------------------------------------------------

@router.get("/alerts")
def list_alerts(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [a.model_dump(mode="json") for a in state.price_alerts]}


@router.post("/alerts")
def create_alert(
    body: CreateAlertRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.alert.create",
        {"symbol": body.symbol, "condition": body.condition, "target_price": body.target_price},
        lambda s: s.create_price_alert(body.symbol, body.condition, Decimal(str(body.target_price))),
    )
    return {"alert": result.model_dump(mode="json")}


@router.delete("/alerts/{alert_id}")
def delete_alert(
    alert_id: str,
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    result = _mutate(
        session_manager, session_id,
        "robinhood.alert.delete",
        {"alert_id": alert_id},
        lambda s: s.delete_price_alert(alert_id),
    )
    return {"alert": result.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Dividends
# ---------------------------------------------------------------------------

@router.get("/dividends")
def list_dividends(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [d.model_dump(mode="json") for d in state.dividend_schedule]}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/settings")
def get_settings(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return state.settings.model_dump(mode="json")


@router.put("/settings")
def update_settings(
    body: UpdateSettingsRequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    kwargs = {
        k: v for k, v in body.model_dump(exclude={"session_id"}).items()
        if v is not None
    }
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.settings.update",
        kwargs,
        lambda s: s.update_settings(**kwargs),
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

@router.get("/security/log")
def get_security_log(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [e.model_dump(mode="json") for e in state.security_log]}


@router.put("/security/2fa")
def update_2fa(
    body: Update2FARequest,
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, body.session_id)
    result = _mutate(
        session_manager, body.session_id,
        "robinhood.security.2fa",
        {"method": body.method},
        lambda s: s.update_2fa(body.method),
    )
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------

@router.get("/referrals")
def get_referrals(
    session_id: str = Query(...),
    session_manager: SessionManager = Depends(get_session_manager),
) -> dict[str, Any]:
    state = _robinhood_state(session_manager, session_id)
    return {"items": [r.model_dump(mode="json") for r in state.referral_history]}
