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
from ..models.booking import (
    BookingState, Property, RoomType, Reservation, Review,
    SavedList, PaymentMethod, Message, Notification,
    ReservationGuest, CancellationPolicy, ReviewBreakdown,
    SearchHistoryEntry,
)
from ..security import (
    build_public_session_summary,
    has_controller_access,
    require_evaluation_access,
)
from ..state import SessionManager
from ...task_rendering import render_template

router = APIRouter(prefix="/api/env/booking", tags=["booking"])


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


class SearchRequest(SessionScopedRequest):
    destination: str = ""
    name: str = ""
    check_in: str = ""
    check_out: str = ""
    guests: int = 2
    rooms: int = 1
    min_price: float | None = None
    max_price: float | None = None
    min_rating: float | None = None
    star_rating: int | None = None
    star_ratings: list[int] = Field(default_factory=list)
    property_type: str | None = None
    amenities: list[str] = Field(default_factory=list)
    free_cancellation: bool = False
    meals_included: str | None = None
    sort_by: str = "popularity"
    page: int = 1
    page_size: int = 20


class CreateReservationRequest(SessionScopedRequest):
    property_id: str
    room_type_id: str
    check_in: str
    check_out: str
    guests: int = 2
    rooms: int = 1
    payment_method_id: str
    full_name: str
    email: str
    phone: str = ""
    country: str = ""
    special_requests: str = ""
    meals_included: str = "none"


class ModifyReservationRequest(SessionScopedRequest):
    check_in: str | None = None
    check_out: str | None = None
    guests: int | None = None
    special_requests: str | None = None


class AddReviewRequest(SessionScopedRequest):
    property_id: str
    reservation_id: str = ""
    overall_score: float
    staff: float = 0.0
    facilities: float = 0.0
    cleanliness: float = 0.0
    comfort: float = 0.0
    value_for_money: float = 0.0
    location: float = 0.0
    free_wifi: float = 0.0
    title: str = ""
    positive: str = ""
    negative: str = ""
    travel_purpose: str = ""
    traveled_with: str = ""


class SavedListRequest(SessionScopedRequest):
    name: str


class SavedListPropertyRequest(SessionScopedRequest):
    property_id: str


class AddPaymentRequest(SessionScopedRequest):
    card_type: str
    last_four: str
    expiry: str
    holder_name: str
    is_default: bool = False


class SendMessageRequest(SessionScopedRequest):
    property_id: str
    reservation_id: str = ""
    subject: str
    body: str


class UpdateSettingsRequest(SessionScopedRequest):
    default_payment_id: str | None = None
    email_notifications: bool | None = None
    deal_alerts: bool | None = None
    review_reminders: bool | None = None
    price_alerts: bool | None = None
    newsletter: bool | None = None
    sms_notifications: bool | None = None
    language: str | None = None
    currency: str | None = None
    country: str | None = None
    two_factor_enabled: bool | None = None


class UpdateProfileRequest(SessionScopedRequest):
    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    owner_nationality: str | None = None
    owner_date_of_birth: str | None = None
    owner_gender: str | None = None
    owner_address: str | None = None


class UpdatePreferencesRequest(SessionScopedRequest):
    smoking: bool | None = None
    preferred_bed_type: str | None = None
    floor_preference: str | None = None
    accessibility_needs: bool | None = None
    preferred_room_type: str | None = None
    dietary_restrictions: list[str] | None = None
    preferred_language: str | None = None
    preferred_currency: str | None = None


class EvaluateRequest(SessionScopedRequest):
    task_id: str | None = None
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: str
    password: str = "simulated"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_session_manager(request: Request) -> SessionManager:
    session_manager = getattr(request.app.state, "session_manager", None)
    if session_manager is None:
        raise HTTPException(status_code=500, detail="SessionManager is not configured")
    return session_manager


def _booking_state(session_manager: SessionManager, session_id: str) -> BookingState:
    try:
        state = session_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not isinstance(state, BookingState):
        raise HTTPException(status_code=404, detail=f"Session {session_id} is not a Booking session")
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
    fn: Callable[[BookingState], Any],
) -> Any:
    return session_manager.mutate(session_id, action, payload, fn)


def _serialize_property(prop: Property) -> dict[str, Any]:
    d = prop.model_dump(mode="json")
    # Add cheapest price for listing cards
    available_rooms = [rt for rt in prop.room_types if rt.is_available]
    if available_rooms:
        cheapest = min(available_rooms, key=lambda rt: rt.price_per_night)
        d["price_from"] = cheapest.price_per_night
        d["original_price_from"] = cheapest.original_price
    else:
        d["price_from"] = None
        d["original_price_from"] = None
    return d


def _serialize_property_brief(prop: Property) -> dict[str, Any]:
    """Lightweight property summary for listings."""
    available_rooms = [rt for rt in prop.room_types if rt.is_available]
    cheapest = min(available_rooms, key=lambda rt: rt.price_per_night) if available_rooms else None
    return {
        "id": prop.id,
        "name": prop.name,
        "property_type": prop.property_type,
        "star_rating": prop.star_rating,
        "city": prop.city,
        "country": prop.country,
        "neighborhood": prop.neighborhood,
        "review_score": prop.review_score,
        "review_score_label": prop.review_score_label,
        "review_count": prop.review_count,
        "distance_from_center_km": prop.distance_from_center_km,
        "popular_facilities": prop.popular_facilities[:5],
        "is_genius_property": prop.is_genius_property,
        "genius_discount_pct": prop.genius_discount_pct,
        "images": prop.images[:1],
        "price_from": cheapest.price_per_night if cheapest else None,
        "original_price_from": cheapest.original_price if cheapest else None,
        "currency": prop.currency,
        "free_cancellation": any(
            rt.cancellation_policy.type == "free_cancellation"
            for rt in prop.room_types if rt.is_available
        ),
        "breakfast_included": any(
            rt.meals_included in ("breakfast", "half_board", "full_board", "all_inclusive")
            for rt in prop.room_types if rt.is_available
        ),
        "rooms_available": sum(rt.rooms_left for rt in prop.room_types if rt.is_available),
    }


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


@router.post("/session")
async def create_session(
    body: SessionCreateRequest,
    request: Request = None,
    sm: SessionManager = Depends(get_session_manager),
):
    task_id = body.task_id
    task = get_task(task_id)
    if task.env_id != "booking":
        raise HTTPException(status_code=400, detail=f"Task {task_id} is not a booking task")

    session_id, targets, actual_seed = sm.create_session("booking", task_id, body.seed)
    state = _booking_state(sm, session_id)

    # Apply degradation if requested
    degradation = dict(body.degradation) if body.degradation else None
    if body.variant_filename and not degradation:
        # Reject path traversal attempts in variant filenames
        if "/" in body.variant_filename or "\\" in body.variant_filename or ".." in body.variant_filename:
            raise HTTPException(status_code=400, detail="Invalid variant filename")
        from pathlib import Path
        import yaml as _yaml

        variant_path = Path(__file__).parent.parent.parent / "injector" / "variants" / body.variant_filename
        if not variant_path.exists():
            raise HTTPException(status_code=404, detail=f"Unknown degradation variant: {body.variant_filename}")
        variant_data = _yaml.safe_load(variant_path.read_text()) or {}
        degradation = {
            "variant_filename": body.variant_filename,
            **variant_data,
        }

    if degradation:
        rendered = _render_degradation_params(degradation, targets)
        state._degradation = rendered
        from ...injector.seed import apply_seed_injection
        from ...injector.server import apply_server_injection
        for inj in rendered.get("injections", []):
            params = inj.get("params", {})
            if inj.get("layer") == "seed":
                apply_seed_injection(state, params)
            elif inj.get("layer") == "server":
                apply_server_injection(state, params)
        from ...injector.middleware import register_session_degradation
        register_session_degradation(session_id, rendered.get("injections", []))

    # Capture initial snapshot for collateral detection.
    # Must run after degradation injections so initial reflects post-injection state.
    if hasattr(state, "state_snapshot"):
        state._initial_snapshot = state.state_snapshot()
    state._initial_state_copy = state.model_copy(deep=True)

    instruction = task.instruction_template or task.instruction or ""
    if targets:
        instruction = render_template(instruction, targets)

    resp: dict[str, Any] = {
        "session_id": session_id,
        "start_path": task.start_path or "/",
        "title": task.title,
        "instruction": instruction,
        "degradation_active": bool(degradation),
    }
    if request is not None and has_controller_access(request):
        resp["resolved_targets"] = targets
    return resp


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    summary = sm.session_summary(session_id)
    task = get_task(state.task_id)
    return build_public_session_summary(
        summary,
        title=task.title,
        instruction=render_template(
            task.instruction_template or task.instruction or "", state.resolved_targets
        ),
    )


@router.get("/degradation/{session_id}")
def get_client_degradation(session_id: str) -> dict[str, Any]:
    """Return client-layer degradation injections for a session as executable JS."""
    from ...injector.middleware import get_client_injections
    injections = get_client_injections(session_id)
    return {"session_id": session_id, "client_injections": injections}


@router.post("/session/{session_id}/reset")
async def reset_session(
    session_id: str,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    next_session = await create_session(
        SessionCreateRequest(
            task_id=state.task_id,
            seed=state.seed,
            degradation=dict(state.degradation) if state.degradation else None,
        ),
        sm=sm,
    )
    await delete_session(session_id, sm=sm)
    return next_session


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    sm: SessionManager = Depends(get_session_manager),
):
    from ...injector.middleware import unregister_session_degradation
    unregister_session_degradation(session_id)
    sm.destroy(session_id)
    return {"ok": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# Properties (Search & Browse)
# ---------------------------------------------------------------------------


@router.post("/properties/search")
async def search_properties(
    body: SearchRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, body.session_id)

    # Record search history
    if body.destination:
        state.add_search_history(SearchHistoryEntry(
            destination=body.destination,
            check_in=body.check_in,
            check_out=body.check_out,
            guests=body.guests,
            rooms=body.rooms,
            searched_at=datetime.now(timezone.utc),
        ))

    results = state.search_properties(
        destination=body.destination,
        check_in=body.check_in,
        check_out=body.check_out,
        guests=body.guests,
        rooms=body.rooms,
        min_price=body.min_price,
        max_price=body.max_price,
        min_rating=body.min_rating,
        star_rating=body.star_rating,
        star_ratings=body.star_ratings if body.star_ratings else None,
        property_type=body.property_type,
        amenities=body.amenities,
        free_cancellation=body.free_cancellation,
        meals_included=body.meals_included,
        sort_by=body.sort_by,
    )

    # Filter by property name (fuzzy: match if all words appear in name)
    if body.name:
        words = body.name.lower().split()
        results = [p for p in results if all(w in p.name.lower() for w in words)]

    # Paginate
    total = len(results)
    start = (body.page - 1) * body.page_size
    end = start + body.page_size
    page_results = results[start:end]

    # Get unique cities and property types for filter suggestions
    all_cities = sorted({p.city for p in state.properties})
    all_types = sorted({p.property_type for p in state.properties})

    return {
        "results": [_serialize_property_brief(p) for p in page_results],
        "total": total,
        "page": body.page,
        "page_size": body.page_size,
        "total_pages": (total + body.page_size - 1) // body.page_size,
        "available_cities": all_cities,
        "available_property_types": all_types,
    }


@router.get("/properties/{property_id}")
async def get_property(
    property_id: str,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    prop = state.get_property(property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_id}")

    # Track view
    state.add_to_recently_viewed(property_id)

    # Get reviews for this property
    reviews = state.get_reviews_for_property(property_id)

    data = _serialize_property(prop)
    data["reviews"] = [r.model_dump(mode="json") for r in reviews[:20]]
    return data


@router.get("/properties")
async def list_properties(
    session_id: str = Query(...),
    city: str | None = None,
    limit: int = 20,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    props = state.properties
    if city:
        props = [p for p in props if p.city.lower() == city.lower()]
    return {
        "properties": [_serialize_property_brief(p) for p in props[:limit]],
        "total": len(props),
    }


@router.get("/destinations")
async def get_destinations(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    cities: dict[str, dict] = {}
    for p in state.properties:
        key = f"{p.city}, {p.country}"
        if key not in cities:
            cities[key] = {
                "city": p.city,
                "country": p.country,
                "property_count": 0,
                "min_price": float("inf"),
            }
        cities[key]["property_count"] += 1
        cheapest = state._cheapest_room(p)
        if cheapest and cheapest.price_per_night < cities[key]["min_price"]:
            cities[key]["min_price"] = cheapest.price_per_night

    for c in cities.values():
        if c["min_price"] == float("inf"):
            c["min_price"] = None

    return {"destinations": sorted(cities.values(), key=lambda x: x["property_count"], reverse=True)}


@router.get("/deals")
async def get_deals(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    deals = []
    for prop in state.properties:
        for rt in prop.room_types:
            if rt.original_price and rt.original_price > rt.price_per_night and rt.is_available:
                discount = round((1 - rt.price_per_night / rt.original_price) * 100)
                deals.append({
                    "property": _serialize_property_brief(prop),
                    "room_type": rt.name,
                    "price": rt.price_per_night,
                    "original_price": rt.original_price,
                    "discount_pct": discount,
                    "currency": prop.currency,
                })
    deals.sort(key=lambda d: d["discount_pct"], reverse=True)
    return {"deals": deals[:20]}


@router.get("/recently-viewed")
async def get_recently_viewed(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    props = []
    for pid in state.recently_viewed[:10]:
        p = state.get_property(pid)
        if p:
            props.append(_serialize_property_brief(p))
    return {"properties": props}


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------


@router.post("/reservations")
async def create_reservation(
    body: CreateReservationRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, body.session_id)
    guest_info = ReservationGuest(
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        country=body.country,
        special_requests=body.special_requests,
    )

    def do_create(s: BookingState) -> Reservation:
        return s.create_reservation(
            property_id=body.property_id,
            room_type_id=body.room_type_id,
            check_in=body.check_in,
            check_out=body.check_out,
            guests=body.guests,
            rooms=body.rooms,
            payment_method_id=body.payment_method_id,
            guest_info=guest_info,
            meals_included=body.meals_included,
        )

    try:
        res = _mutate(sm, body.session_id, "reservation.create", {
            "property_id": body.property_id,
            "room_type_id": body.room_type_id,
            "check_in": body.check_in,
            "check_out": body.check_out,
        }, do_create)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return res.model_dump(mode="json")


@router.get("/reservations")
async def list_reservations(
    session_id: str = Query(...),
    status: str | None = None,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    reservations = state.reservations
    if status:
        reservations = [r for r in reservations if r.status == status]
    return {
        "reservations": [r.model_dump(mode="json") for r in reservations],
        "total": len(reservations),
    }


@router.get("/reservations/{reservation_id}")
async def get_reservation(
    reservation_id: str,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    res = state.get_reservation(reservation_id)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Reservation not found: {reservation_id}")

    # Log the view for benchmark grading (durable server-side proof)
    from ..models.base import AuditEntry
    state.audit_log.append(AuditEntry(
        action="reservation.view",
        payload={"reservation_id": reservation_id},
        summary=f"Viewed reservation {reservation_id}",
    ))

    # Include property info
    prop = state.get_property(res.property_id)
    data = res.model_dump(mode="json")
    if prop:
        data["property"] = _serialize_property_brief(prop)
    return data


class CancelReservationRequest(SessionScopedRequest):
    fee_accepted: float | None = None


@router.post("/reservations/{reservation_id}/cancel-preview")
async def cancel_reservation_preview(
    reservation_id: str,
    body: SessionScopedRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    """Return cancellation fee preview without mutating state."""
    state = _booking_state(sm, body.session_id)
    try:
        return state.compute_cancel_fee(reservation_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: str,
    body: CancelReservationRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    """Cancel a reservation after fee has been acknowledged.

    The caller must first hit ``/cancel-preview`` to obtain ``fee_amount`` and
    then pass it back in ``fee_accepted``. The server validates the match and
    records ``fee_accepted`` in the audit_log entry.
    """
    fee_accepted = body.fee_accepted
    try:
        res = _mutate(sm, body.session_id, "reservation.cancel", {
            "reservation_id": reservation_id,
            "fee_accepted": fee_accepted,
        }, lambda s: s.cancel_reservation(reservation_id, fee_accepted=fee_accepted))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return res.model_dump(mode="json")


@router.put("/reservations/{reservation_id}")
async def modify_reservation(
    reservation_id: str,
    body: ModifyReservationRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "session_id"}
    try:
        res = _mutate(sm, body.session_id, "reservation.modify", {
            "reservation_id": reservation_id,
            **updates,
        }, lambda s: s.modify_reservation(reservation_id, **updates))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return res.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


@router.post("/reviews")
async def add_review(
    body: AddReviewRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, body.session_id)
    review = Review(
        id=state._next_id("review"),
        property_id=body.property_id,
        reservation_id=body.reservation_id,
        author_name=state.owner_name,
        author_country=state.owner_nationality,
        overall_score=body.overall_score,
        scores=ReviewBreakdown(
            staff=body.staff,
            facilities=body.facilities,
            cleanliness=body.cleanliness,
            comfort=body.comfort,
            value_for_money=body.value_for_money,
            location=body.location,
            free_wifi=body.free_wifi,
        ),
        title=body.title,
        positive=body.positive,
        negative=body.negative,
        travel_purpose=body.travel_purpose,
        traveled_with=body.traveled_with,
        created_at=datetime.now(timezone.utc),
    )

    def do_add(s: BookingState) -> Review:
        return s.add_review(review)

    result = _mutate(sm, body.session_id, "review.add", {
        "property_id": body.property_id,
        "overall_score": body.overall_score,
    }, do_add)

    # Mark reservation as reviewed
    if body.reservation_id:
        res = state.get_reservation(body.reservation_id)
        if res:
            res.rating_submitted = True

    return result.model_dump(mode="json")


@router.get("/reviews")
async def list_reviews(
    session_id: str = Query(...),
    property_id: str | None = None,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    reviews = state.reviews
    if property_id:
        reviews = [r for r in reviews if r.property_id == property_id]
    return {
        "reviews": [r.model_dump(mode="json") for r in reviews],
        "total": len(reviews),
    }


# ---------------------------------------------------------------------------
# Saved Lists
# ---------------------------------------------------------------------------


@router.post("/saved-lists")
async def create_saved_list(
    body: SavedListRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    result = _mutate(sm, body.session_id, "saved_list.create", {
        "name": body.name,
    }, lambda s: s.create_saved_list(body.name))
    return result.model_dump(mode="json")


@router.get("/price-preview")
async def price_preview(
    property_id: str = Query(...),
    room_type_id: str = Query(...),
    nights: int = Query(...),
    rooms: int = Query(1),
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    """Return itemized fees (taxes, city fee, resort fee, cleaning fee) for a
    potential booking, so the agent can read all-in cost before confirming."""
    from breakingweb.backend.models.booking import compute_fee_breakdown
    state = _booking_state(sm, session_id)
    prop = state.get_property(property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_id}")
    room = next((rt for rt in prop.room_types if rt.id == room_type_id), None)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_type_id}")
    base_total = round(room.price_per_night * max(1, nights) * max(1, rooms), 2)
    breakdown = compute_fee_breakdown(
        city=prop.city,
        property_type=prop.property_type,
        base_price=base_total,
        nights=nights,
    )
    return {
        "property_id": property_id,
        "room_type_id": room_type_id,
        "nights": nights,
        "rooms": rooms,
        "price_per_night": room.price_per_night,
        "base_total": base_total,
        "taxes": breakdown["taxes"],
        "city_fee": breakdown["city_fee"],
        "resort_fee": breakdown["resort_fee"],
        "cleaning_fee": breakdown["cleaning_fee"],
        "total_fees": breakdown["total_fees"],
        "total_with_fees": round(base_total + breakdown["total_fees"], 2),
        "currency": prop.currency,
    }


@router.get("/rebookings")
async def list_rebookings(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    """List all rebooking suggestions generated after cancellations in this session."""
    state = _booking_state(sm, session_id)
    return {
        "rebookings": [r.model_dump(mode="json") for r in state.rebooking_suggestions],
    }


@router.get("/rebookings/{rebooking_id}")
async def get_rebooking(
    rebooking_id: str,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    r = next((x for x in state.rebooking_suggestions if x.id == rebooking_id), None)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Rebooking not found: {rebooking_id}")
    return r.model_dump(mode="json")


@router.get("/rebookings/by-reservation/{reservation_id}")
async def get_rebooking_by_reservation(
    reservation_id: str,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    """Look up the rebooking suggestion generated for a specific cancelled reservation."""
    state = _booking_state(sm, session_id)
    r = next(
        (x for x in state.rebooking_suggestions if x.original_reservation_id == reservation_id),
        None,
    )
    if r is None:
        raise HTTPException(
            status_code=404,
            detail=f"No rebooking suggestion for reservation {reservation_id}",
        )
    return r.model_dump(mode="json")


@router.get("/saved-lists")
async def list_saved_lists(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    lists = []
    for sl in state.saved_lists:
        data = sl.model_dump(mode="json")
        # Include property previews
        previews = []
        for pid in sl.property_ids[:4]:
            p = state.get_property(pid)
            if p:
                previews.append({"id": p.id, "name": p.name, "city": p.city, "images": p.images[:1]})
        data["property_previews"] = previews
        lists.append(data)
    return {"lists": lists}


@router.post("/saved-lists/{list_id}/properties")
async def add_to_saved_list(
    list_id: str,
    body: SavedListPropertyRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    try:
        result = _mutate(sm, body.session_id, "saved_list.add_property", {
            "list_id": list_id,
            "property_id": body.property_id,
        }, lambda s: s.add_to_saved_list(list_id, body.property_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.delete("/saved-lists/{list_id}/properties/{property_id}")
async def remove_from_saved_list(
    list_id: str,
    property_id: str,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    try:
        result = _mutate(sm, session_id, "saved_list.remove_property", {
            "list_id": list_id,
            "property_id": property_id,
        }, lambda s: s.remove_from_saved_list(list_id, property_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.delete("/saved-lists/{list_id}")
async def delete_saved_list(
    list_id: str,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    try:
        result = _mutate(sm, session_id, "saved_list.delete", {
            "list_id": list_id,
        }, lambda s: s.delete_saved_list(list_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


# ---------------------------------------------------------------------------
# Payment Methods
# ---------------------------------------------------------------------------


@router.get("/payment-methods")
async def list_payment_methods(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return {"payment_methods": [pm.model_dump(mode="json") for pm in state.payment_methods]}


@router.post("/payment-methods")
async def add_payment_method(
    body: AddPaymentRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, body.session_id)
    pm = PaymentMethod(
        id=state._next_id("pm"),
        card_type=body.card_type,
        last_four=body.last_four,
        expiry=body.expiry,
        holder_name=body.holder_name,
        is_default=body.is_default,
    )
    result = _mutate(sm, body.session_id, "payment.add", {
        "card_type": body.card_type,
        "last_four": body.last_four,
    }, lambda s: s.add_payment_method(pm))
    return result.model_dump(mode="json")


@router.delete("/payment-methods/{pm_id}")
async def remove_payment_method(
    pm_id: str,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    try:
        _mutate(sm, session_id, "payment.remove", {
            "pm_id": pm_id,
        }, lambda s: s.remove_payment_method(pm_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.get("/messages")
async def list_messages(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return {
        "messages": [m.model_dump(mode="json") for m in state.messages],
        "unread": sum(1 for m in state.messages if not m.read and m.sender != "guest"),
    }


@router.post("/messages")
async def send_message(
    body: SendMessageRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    try:
        result = _mutate(sm, body.session_id, "message.send", {
            "property_id": body.property_id,
            "subject": body.subject,
        }, lambda s: s.send_message(body.property_id, body.reservation_id, body.subject, body.body))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


@router.post("/messages/{message_id}/read")
async def mark_message_read(
    message_id: str,
    body: SessionScopedRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    try:
        result = _mutate(sm, body.session_id, "message.read", {
            "message_id": message_id,
        }, lambda s: s.mark_message_read(message_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@router.get("/notifications")
async def list_notifications(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return {
        "notifications": [n.model_dump(mode="json") for n in state.notifications],
        "unread": state.unread_notification_count(),
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    body: SessionScopedRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    try:
        result = _mutate(sm, body.session_id, "notification.read", {
            "notification_id": notification_id,
        }, lambda s: s.mark_notification_read(notification_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Account & Settings
# ---------------------------------------------------------------------------


@router.get("/account")
async def get_account(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return {
        "name": state.owner_name,
        "email": state.owner_email,
        "phone": state.owner_phone,
        "nationality": state.owner_nationality,
        "date_of_birth": state.owner_date_of_birth,
        "gender": state.owner_gender,
        "address": state.owner_address,
        "genius": state.genius.model_dump(),
        "wallet": state.wallet.model_dump(mode="json"),
    }


@router.put("/account")
async def update_profile(
    body: UpdateProfileRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "session_id"}

    def do_update(s: BookingState) -> dict:
        for key, value in updates.items():
            if hasattr(s, key):
                setattr(s, key, value)
        return updates

    _mutate(sm, body.session_id, "account.update", updates, do_update)
    state = _booking_state(sm, body.session_id)
    return {
        "name": state.owner_name,
        "email": state.owner_email,
        "phone": state.owner_phone,
        "nationality": state.owner_nationality,
        "date_of_birth": state.owner_date_of_birth,
        "gender": state.owner_gender,
        "address": state.owner_address,
        "genius": state.genius.model_dump(),
        "wallet": state.wallet.model_dump(mode="json"),
    }


@router.get("/settings")
async def get_settings(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return state.settings.model_dump(mode="json")


@router.put("/settings")
async def update_settings(
    body: UpdateSettingsRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "session_id"}

    def do_update(s: BookingState) -> dict:
        for key, value in updates.items():
            if hasattr(s.settings, key):
                setattr(s.settings, key, value)
        # If default_payment_id changed, also update is_default on payment methods
        if "default_payment_id" in updates and updates["default_payment_id"]:
            new_default = updates["default_payment_id"]
            for pm in s.payment_methods:
                pm.is_default = pm.id == new_default
        return updates

    _mutate(sm, body.session_id, "settings.update", updates, do_update)
    state = _booking_state(sm, body.session_id)
    return state.settings.model_dump(mode="json")


@router.get("/preferences")
async def get_preferences(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return state.travel_preferences.model_dump()


@router.put("/preferences")
async def update_preferences(
    body: UpdatePreferencesRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "session_id"}

    def do_update(s: BookingState) -> dict:
        for key, value in updates.items():
            if hasattr(s.travel_preferences, key):
                setattr(s.travel_preferences, key, value)
        return updates

    _mutate(sm, body.session_id, "preferences.update", updates, do_update)
    state = _booking_state(sm, body.session_id)
    return state.travel_preferences.model_dump()


@router.get("/genius")
async def get_genius(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return state.genius.model_dump()


@router.get("/wallet")
async def get_wallet(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return state.wallet.model_dump(mode="json")


@router.get("/search-history")
async def get_search_history(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    return {"history": [h.model_dump(mode="json") for h in state.search_history[:10]]}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(
    body: LoginRequest,
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, session_id)
    state.login(body.email, body.password)
    return {"ok": True, "name": state.owner_name}


@router.post("/logout")
async def logout(
    body: SessionScopedRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    state = _booking_state(sm, body.session_id)
    state.logout()
    return {"ok": True}


@router.post("/change-password")
async def change_password(
    body: SessionScopedRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    """Simulated password change — always succeeds."""
    _mutate(sm, body.session_id, "account.change_password", {},
            lambda s: setattr(s, "password_hash", "simulated_new_hash"))
    return {"ok": True, "message": "Password changed successfully"}


@router.post("/payment-methods/{pm_id}/set-default")
async def set_default_payment(
    pm_id: str,
    body: SessionScopedRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    def do_set(s: BookingState) -> dict:
        found = False
        for pm in s.payment_methods:
            pm.is_default = pm.id == pm_id
            if pm.id == pm_id:
                found = True
        if not found:
            raise KeyError(f"Unknown payment method: {pm_id}")
        s.settings.default_payment_id = pm_id
        return {"default_payment_id": pm_id}

    try:
        result = _mutate(sm, body.session_id, "payment.set_default",
                         {"pm_id": pm_id}, do_set)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    body: SessionScopedRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    def do_read_all(s: BookingState) -> int:
        count = 0
        for n in s.notifications:
            if not n.read:
                n.read = True
                count += 1
        return count

    count = _mutate(sm, body.session_id, "notifications.read_all", {}, do_read_all)
    return {"ok": True, "marked_read": count}


@router.delete("/search-history")
async def clear_search_history(
    session_id: str = Query(...),
    sm: SessionManager = Depends(get_session_manager),
):
    def do_clear(s: BookingState) -> int:
        count = len(s.search_history)
        s.search_history.clear()
        return count

    count = _mutate(sm, session_id, "search_history.clear", {}, do_clear)
    return {"ok": True, "cleared": count}


class ApplyWalletRequest(SessionScopedRequest):
    reservation_id: str | None = None
    amount: float | None = None


@router.post("/wallet/apply")
async def apply_wallet_credit(
    body: ApplyWalletRequest,
    sm: SessionManager = Depends(get_session_manager),
):
    """Apply wallet credit to a reservation (deducts from wallet)."""
    state = _booking_state(sm, body.session_id)
    available = state.wallet.balance
    if available <= 0:
        raise HTTPException(status_code=400, detail="Wallet balance is zero")
    amount = body.amount if body.amount is not None else available
    amount = min(round(amount, 2), available)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    description = "Applied to reservation"
    if body.reservation_id:
        for r in state.reservations:
            if r.id == body.reservation_id:
                description = f"Applied to reservation at {r.property_name}"
                break

    def do_apply(s: BookingState) -> float:
        s.use_wallet_credit(amount, description)
        return s.wallet.balance

    new_balance = _mutate(
        sm, body.session_id, "wallet.apply",
        {"reservation_id": body.reservation_id, "amount": amount},
        do_apply,
    )
    return {
        "balance": new_balance,
        "currency": state.wallet.currency,
        "applied": amount,
        "message": f"Applied ${amount:.2f} from wallet",
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@router.post("/evaluate")
async def evaluate(
    body: EvaluateRequest,
    request: Request,
    sm: SessionManager = Depends(get_session_manager),
):
    session_id = body.session_id
    state = _booking_state(sm, session_id)
    require_evaluation_access(
        request,
        requested_task_id=body.task_id,
        bound_task_id=state.task_id,
    )

    if body.benchmark_state is not None:
        sm.set_benchmark_state(session_id, body.benchmark_state)

    if body.task_id and body.task_id != state.task_id:
        raise HTTPException(
            status_code=400,
            detail=f"Session {body.session_id} is bound to task {state.task_id!r}, not {body.task_id!r}",
        )
    task = get_task(state.task_id)
    targets = sm.get_targets(session_id)

    result = unified_evaluate(
        task,
        server_state=state,
        targets=targets,
        trajectory=body.trajectory or [],
    )
    return result


# ---------------------------------------------------------------------------
# Variants (for launcher UI)
# ---------------------------------------------------------------------------


@router.get("/variants")
def list_variants() -> list[dict[str, Any]]:
    """List available degradation variants for the Booking environment."""
    from pathlib import Path
    import yaml as _yaml

    variants_dir = Path(__file__).parent.parent.parent / "injector" / "variants"
    result: list[dict[str, Any]] = []
    if variants_dir.exists():
        for f in sorted(variants_dir.glob("booking_*.yaml")):
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
