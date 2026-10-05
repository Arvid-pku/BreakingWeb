"""Composable seed builder framework for the Booking.com environment.

Provides :class:`BookingSeedContext` and a registry of reusable builder
functions that generate deterministic test data for booking benchmark tasks.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from breakingweb.backend.models.booking import (
    CancellationPolicy,
    GeoLocation,
    HouseRules,
    NearbyAttraction,
    Property,
    ReservationGuest,
    Reservation,
    Review,
    ReviewBreakdown,
    RoomType,
    SavedList,
    Message,
    Notification,
    PaymentMethod,
    SearchHistoryEntry,
    WalletTransaction,
)


# ---------------------------------------------------------------------------
# Seed context
# ---------------------------------------------------------------------------


@dataclass
class BookingSeedContext:
    seed: int
    rng: random.Random
    fake: Any
    now: datetime
    base: dict[str, Any]
    actors: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    _prop_counter: int = 0
    _room_counter: int = 0
    _res_counter: int = 0
    _review_counter: int = 0

    def resolve_actor(
        self,
        key: str,
        domain: str | None = None,
        is_vip: bool = False,
        name: str | None = None,
    ) -> dict[str, Any]:
        actor_name = name or self.fake.name()
        email = f"{actor_name.lower().replace(' ', '.')}@{domain or 'example.com'}"
        actor = {"name": actor_name, "email": email, "is_vip": is_vip}
        self.actors[key] = actor
        return actor

    def make_property(
        self,
        name: str,
        city: str,
        country: str,
        *,
        property_type: str = "hotel",
        star_rating: int = 4,
        neighborhood: str = "",
        address: str = "",
        lat: float = 0.0,
        lng: float = 0.0,
        description: str = "",
        review_score: float = 0.0,
        review_count: int = 0,
        amenities: list[str] | None = None,
        popular_facilities: list[str] | None = None,
        distance_from_center_km: float = 1.0,
        genius_discount_pct: int = 0,
        chain_name: str = "",
        currency: str = "USD",
    ) -> Property:
        self._prop_counter += 1
        pid = f"prop_{self._prop_counter}"

        # Derive review label
        label = ""
        if review_score >= 9.5:
            label = "Exceptional"
        elif review_score >= 9.0:
            label = "Superb"
        elif review_score >= 8.5:
            label = "Fabulous"
        elif review_score >= 8.0:
            label = "Very Good"
        elif review_score >= 7.0:
            label = "Good"
        elif review_score >= 6.0:
            label = "Pleasant"

        return Property(
            id=pid,
            name=name,
            property_type=property_type,
            star_rating=star_rating,
            city=city,
            country=country,
            neighborhood=neighborhood,
            address=address,
            geo=GeoLocation(lat=lat, lng=lng),
            description=description,
            review_score=review_score,
            review_score_label=label,
            review_count=review_count,
            review_breakdown=ReviewBreakdown(
                staff=round(review_score + self.rng.uniform(-0.5, 0.3), 1),
                facilities=round(review_score + self.rng.uniform(-0.6, 0.2), 1),
                cleanliness=round(review_score + self.rng.uniform(-0.3, 0.4), 1),
                comfort=round(review_score + self.rng.uniform(-0.4, 0.3), 1),
                value_for_money=round(review_score + self.rng.uniform(-0.8, 0.1), 1),
                location=round(review_score + self.rng.uniform(-0.2, 0.5), 1),
                free_wifi=round(review_score + self.rng.uniform(-0.5, 0.2), 1),
            ),
            amenities=amenities or [],
            popular_facilities=popular_facilities or [],
            images=self._property_images(),
            distance_from_center_km=distance_from_center_km,
            genius_discount_pct=genius_discount_pct,
            is_genius_property=genius_discount_pct > 0,
            chain_name=chain_name,
            currency=currency,
        )

    def _property_images(self) -> list[str]:
        """Assign 3 deterministic hotel images based on counter."""
        from breakingweb.backend.seeders.booking import _HOTEL_IMAGES
        n = len(_HOTEL_IMAGES)
        base = self._prop_counter % n
        return [_HOTEL_IMAGES[(base + i) % n] for i in range(3)]

    def _room_images(self) -> list[str]:
        """Assign 1 deterministic room image based on counter."""
        from breakingweb.backend.seeders.booking import _ROOM_IMAGES
        return [_ROOM_IMAGES[self._room_counter % len(_ROOM_IMAGES)]]

    def make_room(
        self,
        property_id: str,
        name: str,
        price: float,
        *,
        max_occupancy: int = 2,
        bed_type: str = "double",
        bed_count: int = 1,
        room_size_sqm: float = 25.0,
        original_price: float | None = None,
        amenities: list[str] | None = None,
        meals_included: str = "none",
        cancel_type: str = "free_cancellation",
        cancel_days: int = 1,
        view_type: str = "",
        rooms_left: int = 5,
    ) -> RoomType:
        self._room_counter += 1
        rid = f"room_{self._room_counter}"
        return RoomType(
            id=rid,
            property_id=property_id,
            name=name,
            max_occupancy=max_occupancy,
            bed_type=bed_type,
            bed_count=bed_count,
            room_size_sqm=room_size_sqm,
            price_per_night=price,
            original_price=original_price,
            amenities=amenities or ["Air conditioning", "Private bathroom", "TV", "Free WiFi"],
            meals_included=meals_included,
            cancellation_policy=CancellationPolicy(
                type=cancel_type,
                free_cancel_before_days=cancel_days,
                penalty_percentage=100.0 if cancel_type == "non_refundable" else 0.0,
                description=(
                    f"Free cancellation until {cancel_days} day(s) before check-in"
                    if cancel_type == "free_cancellation"
                    else "Non-refundable"
                    if cancel_type == "non_refundable"
                    else f"50% penalty if cancelled within {cancel_days} days"
                ),
            ),
            images=self._room_images(),
            is_available=True,
            rooms_left=rooms_left,
            view_type=view_type,
        )

    def make_reservation(
        self,
        property_id: str,
        property_name: str,
        room_type_id: str,
        room_type_name: str,
        check_in: str,
        check_out: str,
        price_per_night: float,
        status: str = "confirmed",
        *,
        guests: int = 2,
        rooms: int = 1,
        payment_method_id: str = "pm_1",
        days_ago: int = 30,
    ) -> Reservation:
        self._res_counter += 1
        rid = f"res_{self._res_counter}"
        from datetime import date
        d_in = date.fromisoformat(check_in)
        d_out = date.fromisoformat(check_out)
        nights = (d_out - d_in).days
        subtotal = price_per_night * nights * rooms
        taxes = round(subtotal * 0.12, 2)
        total = round(subtotal + taxes, 2)

        return Reservation(
            id=rid,
            property_id=property_id,
            property_name=property_name,
            room_type_id=room_type_id,
            room_type_name=room_type_name,
            check_in=check_in,
            check_out=check_out,
            nights=nights,
            guests=guests,
            rooms=rooms,
            price_per_night=price_per_night,
            total_price=total,
            taxes_and_fees=taxes,
            status=status,
            booked_at=self.now - timedelta(days=days_ago),
            guest_info=ReservationGuest(
                full_name=self.base.get("owner_name", "Jordan Parker"),
                email=self.base.get("owner_email", "jordan.parker@email.com"),
            ),
            payment_method_id=payment_method_id,
            confirmation_number=f"BK-{self.rng.randint(10000000, 99999999)}",
        )


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------


BuilderFn = Callable[[BookingSeedContext, dict[str, Any]], dict[str, Any]]
BOOKING_BUILDER_REGISTRY: dict[str, BuilderFn] = {}


def _register(name: str) -> Callable[[BuilderFn], BuilderFn]:
    def decorator(fn: BuilderFn) -> BuilderFn:
        BOOKING_BUILDER_REGISTRY[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


@_register("featured_property")
def build_featured_property(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a specific featured property for task targeting."""
    name = params.get("name", "Grand Hotel")
    city = params.get("city", "New York")
    country = params.get("country", "United States")
    star_rating = params.get("star_rating", 4)
    review_score = params.get("review_score", 8.5)
    review_count = params.get("review_count", 500)
    price = params.get("price", 200.0)
    property_type = params.get("property_type", "hotel")
    genius_discount = params.get("genius_discount_pct", 0)

    prop = ctx.make_property(
        name=name,
        city=city,
        country=country,
        property_type=property_type,
        star_rating=star_rating,
        neighborhood=params.get("neighborhood", "City Center"),
        address=params.get("address", "123 Main Street"),
        review_score=review_score,
        review_count=review_count,
        amenities=params.get("amenities", [
            "Free WiFi", "Air conditioning", "24-hour front desk", "Restaurant",
            "Bar", "Fitness center", "Room service", "Non-smoking rooms",
        ]),
        popular_facilities=params.get("popular_facilities", [
            "Free WiFi", "Restaurant", "Bar", "Fitness center",
        ]),
        distance_from_center_km=params.get("distance_km", 0.5),
        genius_discount_pct=genius_discount,
    )

    # Add rooms
    rooms_config = params.get("rooms", [
        {"name": "Standard Double Room", "price": price, "bed_type": "double"},
        {"name": "Deluxe Double Room", "price": price * 1.4, "bed_type": "queen"},
        {"name": "Superior Suite", "price": price * 2.2, "bed_type": "king", "max_occupancy": 3},
    ])

    for rc in rooms_config:
        room = ctx.make_room(
            prop.id,
            rc.get("name", "Standard Room"),
            rc.get("price", price),
            max_occupancy=rc.get("max_occupancy", 2),
            bed_type=rc.get("bed_type", "double"),
            room_size_sqm=rc.get("room_size_sqm", 25.0),
            original_price=rc.get("original_price"),
            meals_included=rc.get("meals_included", "none"),
            cancel_type=rc.get("cancel_type", "free_cancellation"),
            view_type=rc.get("view_type", ""),
        )
        prop.room_types.append(room)

    ctx.base["properties"].append(prop)
    return {
        "property_id": prop.id,
        "property_name": prop.name,
        "cheapest_room_id": prop.room_types[0].id if prop.room_types else "",
        "cheapest_room_name": prop.room_types[0].name if prop.room_types else "",
    }


@_register("create_reservation")
def build_reservation(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a reservation for a property."""
    property_id = params["property_id"]
    prop = next((p for p in ctx.base["properties"] if p.id == property_id), None)
    if prop is None:
        raise KeyError(f"Property {property_id} not found")

    room = prop.room_types[0] if prop.room_types else None
    room_type_id = params.get("room_type_id", room.id if room else "room_1")
    room_type_name = params.get("room_type_name", room.name if room else "Standard Room")

    check_in = params.get("check_in", (ctx.now + timedelta(days=14)).strftime("%Y-%m-%d"))
    check_out = params.get("check_out", (ctx.now + timedelta(days=17)).strftime("%Y-%m-%d"))
    price = params.get("price_per_night", room.price_per_night if room else 150.0)

    res = ctx.make_reservation(
        property_id=property_id,
        property_name=prop.name,
        room_type_id=room_type_id,
        room_type_name=room_type_name,
        check_in=check_in,
        check_out=check_out,
        price_per_night=price,
        status=params.get("status", "confirmed"),
        guests=params.get("guests", 2),
        days_ago=params.get("booked_days_ago", 7),
    )

    # Optional cancellation_policy override — lets task YAMLs set policy
    # independently of the room type. Shape:
    #   cancellation_policy:
    #     type: "free_cancellation" | "non_refundable" | "partial_refund"
    #     free_cancel_before_days: int     # for free_cancellation
    #     penalty_percentage: float        # 0-100
    #     description: str                 # user-facing
    policy_override = params.get("cancellation_policy")
    if policy_override:
        res.cancellation_policy = CancellationPolicy(
            type=policy_override.get("type", "free_cancellation"),
            free_cancel_before_days=policy_override.get("free_cancel_before_days", 1),
            penalty_percentage=policy_override.get("penalty_percentage", 0.0),
            description=policy_override.get(
                "description", "Cancellation policy applies"
            ),
        )

    ctx.base["reservations"].append(res)
    return {
        "reservation_id": res.id,
        "confirmation_number": res.confirmation_number,
        "property_id": property_id,
    }


@_register("add_review")
def build_review(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Add a review for a property."""
    property_id = params["property_id"]
    ctx._review_counter += 1
    review = Review(
        id=f"review_{ctx._review_counter}",
        property_id=property_id,
        author_name=params.get("author_name", ctx.fake.name()),
        author_country=params.get("author_country", "United States"),
        overall_score=params.get("overall_score", 8.0),
        scores=ReviewBreakdown(
            staff=params.get("staff", 8.0),
            facilities=params.get("facilities", 8.0),
            cleanliness=params.get("cleanliness", 8.0),
            comfort=params.get("comfort", 8.0),
            value_for_money=params.get("value_for_money", 8.0),
            location=params.get("location", 8.0),
            free_wifi=params.get("free_wifi", 8.0),
        ),
        title=params.get("title", "Great stay"),
        positive=params.get("positive", "Excellent location and friendly staff."),
        negative=params.get("negative", ""),
        travel_purpose=params.get("travel_purpose", "leisure"),
        traveled_with=params.get("traveled_with", "couple"),
        stay_date=params.get("stay_date", ctx.now.strftime("%Y-%m")),
        created_at=ctx.now - timedelta(days=ctx.rng.randint(1, 60)),
    )
    ctx.base["reviews"].append(review)
    return {"review_id": review.id}


@_register("create_saved_list")
def build_saved_list(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a saved list with properties."""
    name = params.get("name", "My Trip")
    property_ids = params.get("property_ids", [])
    sl = SavedList(
        id=f"list_{len(ctx.base.get('saved_lists', [])) + 1}",
        name=name,
        property_ids=property_ids,
        created_at=ctx.now - timedelta(days=ctx.rng.randint(1, 30)),
        updated_at=ctx.now - timedelta(days=ctx.rng.randint(0, 5)),
    )
    ctx.base.setdefault("saved_lists", []).append(sl)
    return {"list_id": sl.id, "list_name": sl.name}


@_register("send_message")
def build_message(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a message in the inbox."""
    prop_id = params.get("property_id", "")
    prop_name = params.get("property_name")
    if not prop_name and prop_id:
        prop = next((p for p in ctx.base.get("properties", []) if p.id == prop_id), None)
        if prop:
            prop_name = prop.name
    if not prop_name:
        prop_name = "Hotel"
    msg = Message(
        id=f"msg_{len(ctx.base.get('messages', [])) + 1}",
        property_id=prop_id,
        property_name=prop_name,
        reservation_id=params.get("reservation_id", ""),
        subject=params.get("subject", "Booking inquiry"),
        body=params.get("body", "Thank you for your reservation."),
        sender=params.get("sender", "property"),
        read=params.get("read", False),
        created_at=ctx.now - timedelta(days=ctx.rng.randint(0, 10)),
    )
    ctx.base.setdefault("messages", []).append(msg)
    return {"message_id": msg.id}


@_register("add_notification")
def build_notification(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Add a notification."""
    notif = Notification(
        id=f"notif_{len(ctx.base.get('notifications', [])) + 1}",
        type=params.get("type", "deal_alert"),
        title=params.get("title", "Special deal"),
        message=params.get("message", "Check out these deals!"),
        read=params.get("read", False),
        created_at=ctx.now - timedelta(days=ctx.rng.randint(0, 14)),
        related_id=params.get("related_id"),
    )
    ctx.base.setdefault("notifications", []).append(notif)
    return {"notification_id": notif.id}


@_register("compare_properties")
def build_compare_properties(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create multiple competing properties for comparison tasks."""
    city = params.get("city", "New York")
    country = params.get("country", "United States")
    configs = params.get("properties", [])
    result: dict[str, Any] = {}

    for i, cfg in enumerate(configs):
        prop = ctx.make_property(
            name=cfg["name"], city=city, country=country,
            property_type=cfg.get("property_type", "hotel"),
            star_rating=cfg.get("star_rating", 4),
            neighborhood=cfg.get("neighborhood", "City Center"),
            address=cfg.get("address", ""),
            review_score=cfg.get("review_score", 8.0),
            review_count=cfg.get("review_count", 500),
            amenities=cfg.get("amenities", ["Free WiFi", "Restaurant", "Fitness center"]),
            popular_facilities=cfg.get("popular_facilities", ["Free WiFi"]),
            distance_from_center_km=cfg.get("distance_km", 1.0),
            genius_discount_pct=cfg.get("genius_discount_pct", 0),
        )
        price = cfg.get("price", 200.0)
        for rc in cfg.get("rooms", [{"name": "Standard Room", "price": price}]):
            room = ctx.make_room(
                prop.id, rc.get("name", "Standard Room"), rc.get("price", price),
                max_occupancy=rc.get("max_occupancy", 2),
                bed_type=rc.get("bed_type", "double"),
                original_price=rc.get("original_price"),
                meals_included=rc.get("meals_included", "none"),
                cancel_type=rc.get("cancel_type", "free_cancellation"),
            )
            prop.room_types.append(room)
        ctx.base["properties"].append(prop)
        result[f"property_id_{i+1}"] = prop.id
        result[f"property_name_{i+1}"] = prop.name
    return result


@_register("modify_reservation")
def build_modify_reservation(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a reservation that needs modification."""
    property_id = params["property_id"]
    prop = next((p for p in ctx.base["properties"] if p.id == property_id), None)
    if prop is None:
        raise KeyError(f"Property {property_id} not found")
    room = prop.room_types[0] if prop.room_types else None
    check_in = params.get("check_in", (ctx.now + timedelta(days=20)).strftime("%Y-%m-%d"))
    check_out = params.get("check_out", (ctx.now + timedelta(days=23)).strftime("%Y-%m-%d"))
    price = params.get("price_per_night", room.price_per_night if room else 150.0)
    res = ctx.make_reservation(
        property_id=property_id, property_name=prop.name,
        room_type_id=room.id if room else "room_1",
        room_type_name=room.name if room else "Standard Room",
        check_in=check_in, check_out=check_out,
        price_per_night=price, status="confirmed",
        guests=params.get("guests", 2),
        days_ago=params.get("booked_days_ago", 10),
    )
    res.guest_info.special_requests = params.get("special_requests", "")
    ctx.base["reservations"].append(res)
    return {
        "reservation_id": res.id,
        "confirmation_number": res.confirmation_number,
        "property_id": property_id,
        "check_in": check_in,
        "check_out": check_out,
    }


@_register("add_payment_method")
def build_payment_method(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Add a specific payment method to the account."""
    pm = PaymentMethod(
        id=f"pm_{len(ctx.base['payment_methods']) + 1}",
        card_type=params.get("card_type", "Visa"),
        last_four=params.get("last_four", "0000"),
        expiry=params.get("expiry", "12/29"),
        holder_name=params.get("holder_name", ctx.base["owner_name"]),
        is_default=params.get("is_default", False),
    )
    ctx.base["payment_methods"].append(pm)
    return {"payment_method_id": pm.id, "last_four": pm.last_four}


@_register("set_profile")
def build_set_profile(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Override specific profile fields for task scenarios."""
    for key in ["owner_name", "owner_email", "owner_phone", "owner_nationality",
                "owner_date_of_birth", "owner_gender", "owner_address"]:
        if key in params:
            ctx.base[key] = params[key]
    return {"owner_name": ctx.base["owner_name"]}


@_register("set_preferences")
def build_set_preferences(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Override travel preferences for task scenarios."""
    prefs = ctx.base["travel_preferences"]
    for key in ["smoking", "preferred_bed_type", "floor_preference",
                "accessibility_needs", "preferred_room_type",
                "dietary_restrictions", "preferred_language", "preferred_currency"]:
        if key in params:
            prefs[key] = params[key]
    return {"updated": True}


@_register("set_settings")
def build_set_settings(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Override account settings for task scenarios."""
    settings = ctx.base["settings"]
    for key in params:
        if hasattr(settings, key):
            setattr(settings, key, params[key])
    return {"updated": True}


@_register("add_wallet_credit")
def build_add_wallet(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Add wallet credit for task scenarios."""
    from breakingweb.backend.models.booking import WalletTransaction
    amount = params.get("amount", 50.0)
    desc = params.get("description", "Bonus credit")
    ctx.base["wallet"]["balance"] = round(ctx.base["wallet"]["balance"] + amount, 2)
    ctx.base["wallet"]["transactions"].append(WalletTransaction(
        amount=amount, type="credit", description=desc,
        created_at=ctx.now - timedelta(days=params.get("days_ago", 1)),
    ))
    return {"wallet_balance": ctx.base["wallet"]["balance"]}


@_register("decoy_property")
def build_decoy_property(ctx: BookingSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a decoy property designed to be a plausible wrong choice."""
    name = params.get("name", "Similar Hotel")
    city = params.get("city", "New York")
    country = params.get("country", "United States")
    prop = ctx.make_property(
        name=name, city=city, country=country,
        property_type=params.get("property_type", "hotel"),
        star_rating=params.get("star_rating", 4),
        neighborhood=params.get("neighborhood", "City Center"),
        review_score=params.get("review_score", 8.0),
        review_count=params.get("review_count", 500),
        amenities=params.get("amenities", ["Free WiFi", "Restaurant"]),
        distance_from_center_km=params.get("distance_km", 1.0),
        genius_discount_pct=params.get("genius_discount_pct", 0),
    )
    price = params.get("price", 200.0)
    room = ctx.make_room(prop.id, "Standard Room", price)
    prop.room_types.append(room)
    ctx.base["properties"].append(prop)
    return {"decoy_property_id": prop.id, "decoy_property_name": prop.name}
