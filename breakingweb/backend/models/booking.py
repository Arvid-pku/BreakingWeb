from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseEntity, BaseEnvState


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class GeoLocation(BaseModel):
    lat: float
    lng: float

    model_config = ConfigDict(extra="forbid")


class ReviewBreakdown(BaseModel):
    staff: float = 0.0
    facilities: float = 0.0
    cleanliness: float = 0.0
    comfort: float = 0.0
    value_for_money: float = 0.0
    location: float = 0.0
    free_wifi: float = 0.0

    model_config = ConfigDict(extra="forbid")


class HouseRules(BaseModel):
    check_in_from: str = "14:00"
    check_in_until: str = "23:00"
    check_out_from: str = "07:00"
    check_out_until: str = "11:00"
    children_allowed: bool = True
    pets_allowed: bool = False
    pet_fee: float = 0.0
    smoking_allowed: bool = False
    parties_allowed: bool = False
    quiet_hours_from: str = "22:00"
    quiet_hours_until: str = "08:00"

    model_config = ConfigDict(extra="forbid")


class CancellationPolicy(BaseModel):
    type: str = "free_cancellation"  # free_cancellation, non_refundable, partial_refund
    free_cancel_before_days: int = 1
    penalty_percentage: float = 0.0
    description: str = "Free cancellation until 1 day before check-in"

    model_config = ConfigDict(extra="forbid")


class NearbyAttraction(BaseModel):
    name: str
    distance_km: float
    type: str = "landmark"  # landmark, transport, restaurant, shopping

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


class RoomType(BaseEntity):
    property_id: str
    name: str  # e.g. "Deluxe Double Room", "Superior Suite"
    description: str = ""
    max_occupancy: int = 2
    bed_type: str = "double"  # single, twin, double, queen, king
    bed_count: int = 1
    room_size_sqm: float = 25.0
    price_per_night: float
    original_price: float | None = None  # if on sale
    amenities: list[str] = Field(default_factory=list)
    meals_included: str = "none"  # none, breakfast, half_board, full_board, all_inclusive
    cancellation_policy: CancellationPolicy = Field(default_factory=CancellationPolicy)
    is_available: bool = True
    rooms_left: int = 5
    images: list[str] = Field(default_factory=list)
    view_type: str = ""  # city, sea, garden, pool, mountain


class Property(BaseEntity):
    # ``room_types`` contains per-room availability counters (``rooms_left``,
    # ``is_available``) that the booking routes mutate as a side effect of
    # reservation create/cancel. Hazard Class 6: hide those nested
    # side-effect mutations from ``compute_diff`` so cancel/create tasks
    # don't trip the "unaccounted update on property" sweep. No booking
    # task directly agent-mutates room fields; if one ever does, either
    # promote RoomType to a top-level collection or use a canonical_diff
    # constraint against ``state.properties[...].room_types``.
    # ``review_score``, ``review_score_label``, and ``review_count`` are
    # similarly updated as side effects of ``add_review`` — hide them too.
    DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]] = (
        "room_types",
        "review_score",
        "review_score_label",
        "review_count",
    )

    name: str
    property_type: str = "hotel"  # hotel, apartment, resort, hostel, villa, b&b, aparthotel
    star_rating: int = 4  # 1–5
    city: str
    country: str
    neighborhood: str = ""
    address: str
    geo: GeoLocation = Field(default_factory=lambda: GeoLocation(lat=0.0, lng=0.0))
    description: str
    short_description: str = ""
    review_score: float = 0.0  # 1–10
    review_score_label: str = ""  # Superb, Fabulous, Very Good, Good, Pleasant
    review_count: int = 0
    review_breakdown: ReviewBreakdown = Field(default_factory=ReviewBreakdown)
    amenities: list[str] = Field(default_factory=list)
    popular_facilities: list[str] = Field(default_factory=list)
    room_types: list[RoomType] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    house_rules: HouseRules = Field(default_factory=HouseRules)
    distance_from_center_km: float = 0.0
    nearby_attractions: list[NearbyAttraction] = Field(default_factory=list)
    genius_discount_pct: int = 0  # 0, 10, 15, 20
    is_genius_property: bool = False
    languages_spoken: list[str] = Field(default_factory=lambda: ["English"])
    chain_name: str = ""
    sustainability_badge: bool = False
    currency: str = "USD"


# ---------------------------------------------------------------------------
# Rebooking assistant (Feature I)
# ---------------------------------------------------------------------------


class RebookingCandidate(BaseModel):
    """A single alternative property offered after a cancellation."""
    property_id: str
    property_name: str
    city: str
    star_rating: int
    review_score: float
    room_type_id: str
    room_type_name: str
    price_per_night: float
    nights: int
    base_total: float          # price_per_night * nights
    taxes: float
    city_fee: float
    resort_fee: float
    cleaning_fee: float
    total_with_fees: float
    currency: str = "USD"

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Fee model (Feature C: multi-dim pricing)
# ---------------------------------------------------------------------------
#
# Each booking's total is composed of:
#   base_price     = price_per_night * nights * rooms
#   taxes          = base_price * TAX_RATES[city]       (hotel/VAT tax, per-city)
#   city_fee       = CITY_FEES_PER_NIGHT[city] * nights (tourist tax, per-night)
#   resort_fee     = 25.0 * nights  (only if property_type is "resort")
#   cleaning_fee   = 40.0           (one-time; for every booking)
#   total_price    = sum of the above minus genius_discount
#
# Cities not in the tables fall back to DEFAULT_TAX_RATE / DEFAULT_CITY_FEE.

TAX_RATES: dict[str, float] = {
    "Venice": 0.10, "Rome": 0.22, "Milan": 0.22, "Funchal": 0.23,
    "Istanbul": 0.18, "Paris": 0.20, "London": 0.125, "Bath": 0.20,
    "Edinburgh": 0.20, "New York": 0.1475, "Tokyo": 0.10, "Dubai": 0.10,
    "Barcelona": 0.10, "Sydney": 0.10, "Bangkok": 0.07, "Singapore": 0.09,
    "Copenhagen": 0.25, "Vienna": 0.20, "Prague": 0.21, "Madrid": 0.10,
    "Amsterdam": 0.21, "Berlin": 0.19, "Dublin": 0.135, "Lisbon": 0.23,
    "Athens": 0.13, "Hong Kong": 0.03, "Seoul": 0.10, "Los Angeles": 0.14,
    "San Francisco": 0.14, "Miami": 0.13, "Chicago": 0.175, "Boston": 0.1445,
}
DEFAULT_TAX_RATE = 0.12

CITY_FEES_PER_NIGHT: dict[str, float] = {
    "Venice": 5.0, "Rome": 7.0, "Milan": 5.0, "Funchal": 2.0,
    "Istanbul": 3.0, "Paris": 3.0, "London": 1.0, "Bath": 2.0,
    "Edinburgh": 2.0, "New York": 3.5, "Tokyo": 2.0, "Dubai": 5.0,
    "Barcelona": 4.0, "Sydney": 5.0, "Bangkok": 0.0, "Singapore": 0.0,
    "Copenhagen": 3.0, "Vienna": 3.2, "Prague": 2.5, "Madrid": 3.0,
    "Amsterdam": 3.5, "Berlin": 5.0, "Dublin": 0.0, "Lisbon": 2.0,
    "Athens": 1.5, "Hong Kong": 0.0, "Seoul": 0.0, "Los Angeles": 4.0,
    "San Francisco": 4.0, "Miami": 3.0, "Chicago": 4.5, "Boston": 3.5,
}
DEFAULT_CITY_FEE_PER_NIGHT = 2.0

RESORT_FEE_PER_NIGHT = 25.0
CLEANING_FEE_FLAT = 40.0


def compute_fee_breakdown(
    city: str,
    property_type: str,
    base_price: float,
    nights: int,
) -> dict[str, float]:
    """Return itemized taxes/fees for a booking. All amounts rounded to 2dp.

    Keys: taxes, city_fee, resort_fee, cleaning_fee, total_fees.
    """
    tax_rate = TAX_RATES.get(city, DEFAULT_TAX_RATE)
    per_night = CITY_FEES_PER_NIGHT.get(city, DEFAULT_CITY_FEE_PER_NIGHT)
    taxes = round(base_price * tax_rate, 2)
    city_fee = round(per_night * max(1, nights), 2)
    resort_fee = round(RESORT_FEE_PER_NIGHT * nights, 2) if property_type == "resort" else 0.0
    cleaning_fee = CLEANING_FEE_FLAT
    total_fees = round(taxes + city_fee + resort_fee + cleaning_fee, 2)
    return {
        "taxes": taxes,
        "city_fee": city_fee,
        "resort_fee": resort_fee,
        "cleaning_fee": cleaning_fee,
        "total_fees": total_fees,
    }


class ReservationGuest(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    country: str = ""
    special_requests: str = ""

    model_config = ConfigDict(extra="forbid")


class Reservation(BaseEntity):
    property_id: str
    property_name: str
    room_type_id: str
    room_type_name: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    nights: int = 1
    guests: int = 2
    rooms: int = 1
    price_per_night: float
    total_price: float
    taxes_and_fees: float = 0.0  # sum of taxes + city_fee + resort_fee + cleaning_fee (back-compat)
    taxes: float = 0.0
    city_fee: float = 0.0
    resort_fee: float = 0.0
    cleaning_fee: float = 0.0
    currency: str = "USD"
    status: str = "confirmed"  # confirmed, upcoming, completed, cancelled, no_show, modified
    booked_at: datetime
    guest_info: ReservationGuest
    payment_method_id: str
    cancellation_policy: CancellationPolicy = Field(default_factory=CancellationPolicy)
    confirmation_number: str = ""
    is_genius_deal: bool = False
    genius_discount: float = 0.0
    meals_included: str = "none"
    rating_submitted: bool = False


class Review(BaseEntity):
    property_id: str
    reservation_id: str = ""
    author_name: str
    author_country: str = ""
    overall_score: float  # 1–10
    scores: ReviewBreakdown = Field(default_factory=ReviewBreakdown)
    title: str = ""
    positive: str = ""
    negative: str = ""
    room_type: str = ""
    travel_purpose: str = ""  # business, leisure, family, couple
    traveled_with: str = ""  # solo, couple, family, friends, group
    stay_date: str = ""  # YYYY-MM
    created_at: datetime
    helpful_count: int = 0
    property_response: str = ""


class SavedList(BaseEntity):
    name: str
    property_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PaymentMethod(BaseEntity):
    card_type: str  # visa, mastercard, amex
    last_four: str
    expiry: str
    holder_name: str
    is_default: bool = False


class Message(BaseEntity):
    property_id: str
    property_name: str
    reservation_id: str = ""
    subject: str
    body: str
    sender: str  # "guest" or "property"
    read: bool = False
    created_at: datetime


class Notification(BaseEntity):
    type: str  # booking_confirmed, booking_cancelled, price_drop, review_reminder, genius_upgrade, deal_alert
    title: str
    message: str
    read: bool = False
    created_at: datetime
    related_id: str | None = None


class SearchHistoryEntry(BaseModel):
    destination: str
    check_in: str = ""
    check_out: str = ""
    guests: int = 2
    rooms: int = 1
    searched_at: datetime

    model_config = ConfigDict(extra="forbid")


class GeniusInfo(BaseModel):
    level: int = 1  # 1, 2, 3
    total_bookings: int = 0
    bookings_needed_for_next: int = 5
    benefits: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class TravelPreferences(BaseModel):
    smoking: bool = False
    preferred_bed_type: str = "double"
    floor_preference: str = ""  # high, low, any
    accessibility_needs: bool = False
    preferred_room_type: str = ""
    dietary_restrictions: list[str] = Field(default_factory=list)
    preferred_language: str = "English"
    preferred_currency: str = "USD"

    model_config = ConfigDict(extra="forbid")


class WalletTransaction(BaseModel):
    amount: float
    type: str  # credit, debit
    description: str
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class Wallet(BaseModel):
    balance: float = 0.0
    currency: str = "USD"
    transactions: list[WalletTransaction] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RebookingSuggestion(BaseEntity):
    """System-generated alternatives shown to the user after they cancel a booking.

    ``DIFF_SYSTEM_COLLECTION`` tells the diff engine in ``evaluator_diff`` to
    skip this collection entirely — these entries are server-side side-effects
    of cancellations, not agent-authored state. Canonical_diff authors use
    ``constraint`` expressions (``state.rebooking_suggestions``) to assert on
    them instead of declaring create/invariant blocks.
    """
    DIFF_SYSTEM_COLLECTION: ClassVar[bool] = True

    original_reservation_id: str
    city: str
    check_in: str
    check_out: str
    guests: int = 2
    candidates: list[RebookingCandidate] = Field(default_factory=list)
    created_at: datetime
    consumed_at: datetime | None = None  # set when the user books one of the candidates
    consumed_property_id: str | None = None


class BookingSettings(BaseEntity):
    default_payment_id: str | None = None
    email_notifications: bool = True
    deal_alerts: bool = True
    review_reminders: bool = True
    price_alerts: bool = True
    newsletter: bool = False
    sms_notifications: bool = False
    language: str = "English"
    currency: str = "USD"
    country: str = "United States"
    two_factor_enabled: bool = False


# ---------------------------------------------------------------------------
# Root state
# ---------------------------------------------------------------------------


class BookingState(BaseEnvState):
    DIFF_DIFFABLE_SINGLETONS: ClassVar[tuple[str, ...]] = (
        "settings", "travel_preferences",
    )
    DIFF_DIFFABLE_SCALARS: ClassVar[tuple[str, ...]] = (
        "owner_name", "owner_email", "owner_phone",
        "owner_nationality", "owner_date_of_birth", "owner_gender", "owner_address",
    )

    owner_name: str
    owner_email: str
    owner_phone: str = ""
    owner_nationality: str = "United States"
    owner_date_of_birth: str = ""
    owner_gender: str = ""
    owner_address: str = ""

    properties: list[Property] = Field(default_factory=list)
    reservations: list[Reservation] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    saved_lists: list[SavedList] = Field(default_factory=list)
    payment_methods: list[PaymentMethod] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    notifications: list[Notification] = Field(default_factory=list)
    search_history: list[SearchHistoryEntry] = Field(default_factory=list)
    rebooking_suggestions: list[RebookingSuggestion] = Field(default_factory=list)
    genius: GeniusInfo = Field(default_factory=GeniusInfo)
    travel_preferences: TravelPreferences = Field(default_factory=TravelPreferences)
    wallet: Wallet = Field(default_factory=Wallet)
    settings: BookingSettings

    recently_viewed: list[str] = Field(default_factory=list)  # property IDs
    is_logged_in: bool = True
    password_hash: str = "simulated_hash"
    id_counters: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def _next_id(self, prefix: str) -> str:
        count = self.id_counters.get(prefix, 0) + 1
        self.id_counters[prefix] = count
        return f"{prefix}_{count}"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def get_property(self, property_id: str) -> Property | None:
        return next((p for p in self.properties if p.id == property_id), None)

    def search_properties(
        self,
        destination: str = "",
        check_in: str = "",
        check_out: str = "",
        guests: int = 2,
        rooms: int = 1,
        min_price: float | None = None,
        max_price: float | None = None,
        min_rating: float | None = None,
        star_rating: int | None = None,
        star_ratings: list[int] | None = None,
        property_type: str | None = None,
        amenities: list[str] | None = None,
        free_cancellation: bool = False,
        meals_included: str | None = None,
        sort_by: str = "popularity",
    ) -> list[Property]:
        results: list[Property] = []
        dest_lower = destination.lower() if destination else ""

        for prop in self.properties:
            # Destination filter (city, country, neighborhood, name)
            if dest_lower:
                searchable = " ".join([
                    prop.city.lower(), prop.country.lower(),
                    prop.neighborhood.lower(), prop.name.lower(),
                ]).lower()
                if not all(tok in searchable for tok in dest_lower.split()):
                    continue

            # Star rating filter (single or multi)
            if star_ratings and prop.star_rating not in star_ratings:
                continue
            if star_rating is not None and not star_ratings and prop.star_rating != star_rating:
                continue

            # Property type filter
            if property_type and prop.property_type.lower() != property_type.lower():
                continue

            # Review score filter
            if min_rating is not None and prop.review_score < min_rating:
                continue

            # Amenity filter
            if amenities:
                prop_amenities_lower = [a.lower() for a in prop.amenities]
                if not all(a.lower() in prop_amenities_lower for a in amenities):
                    continue

            # Price filter — check cheapest available room
            cheapest = self._cheapest_room(prop, guests)
            if cheapest is None:
                continue
            if min_price is not None and cheapest.price_per_night < min_price:
                continue
            if max_price is not None and cheapest.price_per_night > max_price:
                continue

            # Free cancellation filter
            if free_cancellation:
                if not any(
                    rt.cancellation_policy.type == "free_cancellation"
                    for rt in prop.room_types
                    if rt.is_available
                ):
                    continue

            # Meals filter
            if meals_included:
                if not any(
                    rt.meals_included == meals_included
                    for rt in prop.room_types
                    if rt.is_available
                ):
                    continue

            results.append(prop)

        # Sort
        if sort_by == "price_low":
            results.sort(key=lambda p: self._min_price(p))
        elif sort_by == "price_high":
            results.sort(key=lambda p: self._min_price(p), reverse=True)
        elif sort_by == "rating":
            results.sort(key=lambda p: p.review_score, reverse=True)
        elif sort_by == "stars":
            results.sort(key=lambda p: p.star_rating, reverse=True)
        elif sort_by == "distance":
            results.sort(key=lambda p: p.distance_from_center_km)
        else:  # popularity — sort by review_count
            results.sort(key=lambda p: p.review_count, reverse=True)

        return results

    def _cheapest_room(self, prop: Property, guests: int = 2) -> RoomType | None:
        available = [
            rt for rt in prop.room_types
            if rt.is_available and rt.max_occupancy >= guests
        ]
        if not available:
            # Fallback: any available room
            available = [rt for rt in prop.room_types if rt.is_available]
        return min(available, key=lambda rt: rt.price_per_night) if available else None

    def _min_price(self, prop: Property) -> float:
        cheapest = self._cheapest_room(prop)
        return cheapest.price_per_night if cheapest else float("inf")

    # ------------------------------------------------------------------
    # Reservations
    # ------------------------------------------------------------------

    def create_reservation(
        self,
        property_id: str,
        room_type_id: str,
        check_in: str,
        check_out: str,
        guests: int,
        rooms: int,
        payment_method_id: str,
        guest_info: ReservationGuest,
        meals_included: str = "none",
    ) -> Reservation:
        prop = self.get_property(property_id)
        if prop is None:
            raise KeyError(f"Unknown property id: {property_id}")

        room = next((rt for rt in prop.room_types if rt.id == room_type_id), None)
        if room is None:
            raise KeyError(f"Unknown room type: {room_type_id}")
        if not room.is_available or room.rooms_left < rooms:
            raise ValueError("Room not available")

        pm = next((p for p in self.payment_methods if p.id == payment_method_id), None)
        if pm is None:
            raise KeyError(f"Unknown payment method: {payment_method_id}")

        # Calculate dates and pricing
        from datetime import date
        d_in = date.fromisoformat(check_in)
        d_out = date.fromisoformat(check_out)
        nights = (d_out - d_in).days
        if nights <= 0:
            raise ValueError("Check-out must be after check-in")

        price_per_night = room.price_per_night
        subtotal = price_per_night * nights * rooms
        breakdown = compute_fee_breakdown(
            city=prop.city,
            property_type=prop.property_type,
            base_price=subtotal,
            nights=nights,
        )

        # Genius discount
        genius_discount = 0.0
        is_genius = False
        if prop.is_genius_property and prop.genius_discount_pct > 0:
            genius_discount = round(subtotal * prop.genius_discount_pct / 100, 2)
            is_genius = True

        total = round(subtotal + breakdown["total_fees"] - genius_discount, 2)
        confirmation_number = f"BK-{self._next_id('conf').split('_')[1].zfill(8)}"

        reservation = Reservation(
            id=self._next_id("res"),
            property_id=property_id,
            property_name=prop.name,
            room_type_id=room_type_id,
            room_type_name=room.name,
            check_in=check_in,
            check_out=check_out,
            nights=nights,
            guests=guests,
            rooms=rooms,
            price_per_night=price_per_night,
            total_price=total,
            taxes_and_fees=breakdown["total_fees"],
            taxes=breakdown["taxes"],
            city_fee=breakdown["city_fee"],
            resort_fee=breakdown["resort_fee"],
            cleaning_fee=breakdown["cleaning_fee"],
            currency=prop.currency,
            status="confirmed",
            booked_at=datetime.now(timezone.utc),
            guest_info=guest_info,
            payment_method_id=payment_method_id,
            cancellation_policy=room.cancellation_policy,
            confirmation_number=confirmation_number,
            is_genius_deal=is_genius,
            genius_discount=genius_discount,
            meals_included=meals_included,
        )

        # Update room availability
        room.rooms_left = max(0, room.rooms_left - rooms)
        if room.rooms_left == 0:
            room.is_available = False

        # Update genius bookings
        self.genius.total_bookings += 1
        self._check_genius_upgrade()

        self.reservations.append(reservation)
        self.touch()
        return reservation

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        return next((r for r in self.reservations if r.id == reservation_id), None)

    def compute_cancel_fee(self, reservation_id: str, now: datetime | None = None) -> dict:
        """Compute cancellation fee preview for a reservation.

        Returns a dict with fee_amount (USD), days_until_checkin, policy_description,
        refundable flag, and total_price. Pure computation — does not mutate state.
        """
        res = self.get_reservation(reservation_id)
        if res is None:
            raise KeyError(f"Unknown reservation: {reservation_id}")
        if res.status in ("cancelled", "completed", "no_show"):
            raise ValueError(f"Cannot preview cancellation for status '{res.status}'")

        now = now or datetime.now(timezone.utc)
        check_in = datetime.strptime(res.check_in, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_until = (check_in - now).days
        total = res.total_price
        policy = res.cancellation_policy

        if policy.type == "non_refundable":
            fee = total
        elif policy.type == "free_cancellation":
            fee = 0.0 if days_until >= policy.free_cancel_before_days else total * (policy.penalty_percentage / 100.0)
        elif policy.type == "partial_refund":
            fee = total * (policy.penalty_percentage / 100.0)
        else:
            fee = 0.0

        fee = round(fee, 2)
        return {
            "reservation_id": reservation_id,
            "fee_amount": fee,
            "total_price": total,
            "days_until_checkin": days_until,
            "policy_type": policy.type,
            "policy_description": policy.description,
            "refundable": fee < total,
            "currency": res.currency,
        }

    def cancel_reservation(self, reservation_id: str, fee_accepted: float | None = None) -> Reservation:
        """Cancel a reservation.

        If ``fee_accepted`` is provided it must match the computed fee within a
        1-cent tolerance. This is how the benchmark captures whether the agent
        acknowledged the cancellation fee before proceeding.
        """
        res = self.get_reservation(reservation_id)
        if res is None:
            raise KeyError(f"Unknown reservation: {reservation_id}")
        if res.status in ("cancelled", "completed", "no_show"):
            raise ValueError(f"Cannot cancel reservation with status '{res.status}'")

        preview = self.compute_cancel_fee(reservation_id)
        expected_fee = preview["fee_amount"]
        if fee_accepted is None:
            raise ValueError(
                "fee_accepted is required. Fetch /cancel-preview first, then pass the "
                "returned fee_amount in the cancel request body."
            )
        if abs(fee_accepted - expected_fee) > 0.01:
            raise ValueError(
                f"fee_accepted ({fee_accepted}) does not match computed fee ({expected_fee}). "
                "Fetch /cancel-preview first."
            )

        res.status = "cancelled"

        # Restore room availability
        prop = self.get_property(res.property_id)
        if prop:
            room = next((rt for rt in prop.room_types if rt.id == res.room_type_id), None)
            if room:
                room.rooms_left += res.rooms
                room.is_available = True

        # Feature I: generate 3 rebooking alternatives in the same city.
        # Prefer cheaper same-city properties than the cancelled one; fall back
        # to any same-city property if fewer than 3 cheaper options exist.
        self._create_rebooking_suggestion(res, prop)

        self.touch()
        return res

    def _create_rebooking_suggestion(
        self,
        cancelled_res: "Reservation",
        cancelled_prop: "Property | None",
    ) -> "RebookingSuggestion | None":
        """Create a RebookingSuggestion after a cancel. Returns the suggestion
        (or None if no candidates were found)."""
        if cancelled_prop is None:
            return None

        city = cancelled_prop.city
        check_in = cancelled_res.check_in
        check_out = cancelled_res.check_out
        nights = cancelled_res.nights
        original_ppn = cancelled_res.price_per_night

        same_city_props: list[Property] = [
            p for p in self.properties
            if p.city == city and p.id != cancelled_prop.id and p.room_types
        ]

        def _cheapest_room(p: Property) -> "RoomType | None":
            avail = [rt for rt in p.room_types if rt.is_available and rt.rooms_left > 0]
            if not avail:
                return None
            return min(avail, key=lambda rt: rt.price_per_night)

        # Rank candidates by similarity to the original's price — i.e. pick
        # "peer" properties in the same price band rather than the absolute
        # cheapest three. Ties break by star_rating and review_score (higher
        # first), so featured properties tend to win over bare distractors.
        scored: list[tuple[Property, RoomType]] = []
        for p in same_city_props:
            room = _cheapest_room(p)
            if room is None:
                continue
            scored.append((p, room))
        if not scored:
            return None

        scored.sort(key=lambda pr: (
            abs(pr[1].price_per_night - original_ppn),
            -pr[0].star_rating,
            -pr[0].review_score,
        ))
        picked = scored[:3]

        candidates: list[RebookingCandidate] = []
        for prop, room in picked:
            base_total = round(room.price_per_night * nights, 2)
            breakdown = compute_fee_breakdown(
                city=prop.city,
                property_type=prop.property_type,
                base_price=base_total,
                nights=nights,
            )
            candidates.append(RebookingCandidate(
                property_id=prop.id,
                property_name=prop.name,
                city=prop.city,
                star_rating=prop.star_rating,
                review_score=prop.review_score,
                room_type_id=room.id,
                room_type_name=room.name,
                price_per_night=room.price_per_night,
                nights=nights,
                base_total=base_total,
                taxes=breakdown["taxes"],
                city_fee=breakdown["city_fee"],
                resort_fee=breakdown["resort_fee"],
                cleaning_fee=breakdown["cleaning_fee"],
                total_with_fees=round(base_total + breakdown["total_fees"], 2),
                currency=prop.currency,
            ))
        if not candidates:
            return None

        suggestion = RebookingSuggestion(
            id=self._next_id("rebook"),
            original_reservation_id=cancelled_res.id,
            city=city,
            check_in=check_in,
            check_out=check_out,
            guests=cancelled_res.guests,
            candidates=candidates,
            created_at=datetime.now(timezone.utc),
        )
        self.rebooking_suggestions.append(suggestion)
        return suggestion

    def modify_reservation(
        self, reservation_id: str, **kwargs: Any
    ) -> Reservation:
        res = self.get_reservation(reservation_id)
        if res is None:
            raise KeyError(f"Unknown reservation: {reservation_id}")
        if res.status not in ("confirmed", "upcoming", "modified"):
            raise ValueError(f"Cannot modify reservation with status '{res.status}'")

        # Handle special_requests → goes into guest_info
        special_requests = kwargs.pop("special_requests", None)
        if special_requests is not None:
            res.guest_info.special_requests = special_requests

        # Handle date changes — recalculate nights and total
        for key, value in kwargs.items():
            if hasattr(res, key):
                setattr(res, key, value)

        if "check_in" in kwargs or "check_out" in kwargs:
            from datetime import date
            d_in = date.fromisoformat(res.check_in)
            d_out = date.fromisoformat(res.check_out)
            res.nights = (d_out - d_in).days
            if res.nights <= 0:
                raise ValueError("Check-out must be after check-in")
            subtotal = res.price_per_night * res.nights * res.rooms
            res.taxes_and_fees = round(subtotal * 0.12, 2)
            res.total_price = round(subtotal + res.taxes_and_fees - res.genius_discount, 2)

        if "guests" in kwargs:
            res.guests = kwargs["guests"]

        res.status = "modified"
        self.touch()
        return res

    def _check_genius_upgrade(self) -> None:
        total = self.genius.total_bookings
        if total >= 15 and self.genius.level < 3:
            self.genius.level = 3
            self.genius.benefits = [
                "10-20% discounts on select stays",
                "10-15% off car rentals",
                "Free breakfast at select properties",
                "Free room upgrades at select properties",
                "Priority customer support",
            ]
            self.genius.bookings_needed_for_next = 0
        elif total >= 5 and self.genius.level < 2:
            self.genius.level = 2
            self.genius.benefits = [
                "10-15% discounts on select stays",
                "Free breakfast at select properties",
                "Free room upgrades at select properties",
            ]
            self.genius.bookings_needed_for_next = 15 - total

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    def add_review(self, review: Review) -> Review:
        self.reviews.append(review)
        # Update property review score
        prop = self.get_property(review.property_id)
        if prop:
            prop.review_count += 1
            # Recalculate average
            prop_reviews = [r for r in self.reviews if r.property_id == prop.id]
            if prop_reviews:
                prop.review_score = round(
                    sum(r.overall_score for r in prop_reviews) / len(prop_reviews), 1
                )
                prop.review_score_label = self._score_label(prop.review_score)
        self.touch()
        return review

    @staticmethod
    def _score_label(score: float) -> str:
        if score >= 9.5:
            return "Exceptional"
        if score >= 9.0:
            return "Superb"
        if score >= 8.5:
            return "Fabulous"
        if score >= 8.0:
            return "Very Good"
        if score >= 7.0:
            return "Good"
        if score >= 6.0:
            return "Pleasant"
        return ""

    def get_reviews_for_property(self, property_id: str) -> list[Review]:
        return [r for r in self.reviews if r.property_id == property_id]

    # ------------------------------------------------------------------
    # Saved Lists
    # ------------------------------------------------------------------

    def create_saved_list(self, name: str) -> SavedList:
        now = datetime.now(timezone.utc)
        sl = SavedList(
            id=self._next_id("list"),
            name=name,
            created_at=now,
            updated_at=now,
        )
        self.saved_lists.append(sl)
        self.touch()
        return sl

    def add_to_saved_list(self, list_id: str, property_id: str) -> SavedList:
        sl = next((s for s in self.saved_lists if s.id == list_id), None)
        if sl is None:
            raise KeyError(f"Unknown list: {list_id}")
        if property_id not in sl.property_ids:
            sl.property_ids.append(property_id)
            sl.updated_at = datetime.now(timezone.utc)
        self.touch()
        return sl

    def remove_from_saved_list(self, list_id: str, property_id: str) -> SavedList:
        sl = next((s for s in self.saved_lists if s.id == list_id), None)
        if sl is None:
            raise KeyError(f"Unknown list: {list_id}")
        if property_id in sl.property_ids:
            sl.property_ids.remove(property_id)
            sl.updated_at = datetime.now(timezone.utc)
        self.touch()
        return sl

    def delete_saved_list(self, list_id: str) -> SavedList:
        for i, sl in enumerate(self.saved_lists):
            if sl.id == list_id:
                removed = self.saved_lists.pop(i)
                self.touch()
                return removed
        raise KeyError(f"Unknown list: {list_id}")

    # ------------------------------------------------------------------
    # Payment Methods
    # ------------------------------------------------------------------

    def add_payment_method(self, pm: PaymentMethod) -> PaymentMethod:
        if pm.is_default:
            for existing in self.payment_methods:
                existing.is_default = False
            self.settings.default_payment_id = pm.id
        self.payment_methods.append(pm)
        self.touch()
        return pm

    def remove_payment_method(self, pm_id: str) -> PaymentMethod:
        for i, pm in enumerate(self.payment_methods):
            if pm.id == pm_id:
                removed = self.payment_methods.pop(i)
                self.touch()
                return removed
        raise KeyError(f"Unknown payment method: {pm_id}")

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def send_message(
        self,
        property_id: str,
        reservation_id: str,
        subject: str,
        body: str,
    ) -> Message:
        prop = self.get_property(property_id)
        if prop is None:
            raise KeyError(f"Unknown property: {property_id}")
        msg = Message(
            id=self._next_id("msg"),
            property_id=property_id,
            property_name=prop.name,
            reservation_id=reservation_id,
            subject=subject,
            body=body,
            sender="guest",
            read=False,
            created_at=datetime.now(timezone.utc),
        )
        self.messages.append(msg)
        self.touch()
        return msg

    def mark_message_read(self, message_id: str) -> Message:
        msg = next((m for m in self.messages if m.id == message_id), None)
        if msg is None:
            raise KeyError(f"Unknown message: {message_id}")
        msg.read = True
        self.touch()
        return msg

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def add_notification(
        self, type: str, title: str, message: str, related_id: str | None = None
    ) -> Notification:
        notif = Notification(
            id=self._next_id("notif"),
            type=type,
            title=title,
            message=message,
            created_at=datetime.now(timezone.utc),
            related_id=related_id,
        )
        self.notifications.append(notif)
        self.touch()
        return notif

    def mark_notification_read(self, notification_id: str) -> Notification:
        notif = next((n for n in self.notifications if n.id == notification_id), None)
        if notif is None:
            raise KeyError(f"Unknown notification: {notification_id}")
        notif.read = True
        self.touch()
        return notif

    def unread_notification_count(self) -> int:
        return sum(1 for n in self.notifications if not n.read)

    # ------------------------------------------------------------------
    # Browsing
    # ------------------------------------------------------------------

    def add_to_recently_viewed(self, property_id: str) -> None:
        if property_id in self.recently_viewed:
            self.recently_viewed.remove(property_id)
        self.recently_viewed.insert(0, property_id)
        if len(self.recently_viewed) > 20:
            self.recently_viewed = self.recently_viewed[:20]
        self.touch()

    def add_search_history(self, entry: SearchHistoryEntry) -> None:
        self.search_history.insert(0, entry)
        if len(self.search_history) > 20:
            self.search_history = self.search_history[:20]
        self.touch()

    # ------------------------------------------------------------------
    # Wallet
    # ------------------------------------------------------------------

    def add_wallet_credit(self, amount: float, description: str) -> None:
        self.wallet.balance = round(self.wallet.balance + amount, 2)
        self.wallet.transactions.append(
            WalletTransaction(
                amount=amount,
                type="credit",
                description=description,
                created_at=datetime.now(timezone.utc),
            )
        )
        self.touch()

    def use_wallet_credit(self, amount: float, description: str) -> None:
        if amount > self.wallet.balance:
            raise ValueError("Insufficient wallet balance")
        self.wallet.balance = round(self.wallet.balance - amount, 2)
        self.wallet.transactions.append(
            WalletTransaction(
                amount=amount,
                type="debit",
                description=description,
                created_at=datetime.now(timezone.utc),
            )
        )
        self.touch()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> bool:
        self.is_logged_in = True
        self.touch()
        return True

    def logout(self) -> None:
        self.is_logged_in = False
        self.touch()

    # ------------------------------------------------------------------
    # Snapshots & summaries
    # ------------------------------------------------------------------

    def state_snapshot(self) -> dict[str, Any]:
        property_snap: dict[str, dict[str, Any]] = {}
        for p in self.properties:
            property_snap[p.id] = {
                "name": p.name,
                "star_rating": p.star_rating,
                "review_score": p.review_score,
                "review_count": p.review_count,
                "room_count": len(p.room_types),
            }

        reservation_snap: dict[str, dict[str, Any]] = {}
        for r in self.reservations:
            reservation_snap[r.id] = {
                "property_id": r.property_id,
                "status": r.status,
                "check_in": r.check_in,
                "check_out": r.check_out,
                "total_price": r.total_price,
                "guests": r.guests,
            }

        review_snap: dict[str, dict[str, Any]] = {}
        for rv in self.reviews:
            review_snap[rv.id] = {
                "property_id": rv.property_id,
                "overall_score": rv.overall_score,
                "title": rv.title,
            }

        saved_snap: dict[str, dict[str, Any]] = {}
        for sl in self.saved_lists:
            saved_snap[sl.id] = {
                "name": sl.name,
                "count": len(sl.property_ids),
            }

        payment_snap: dict[str, dict[str, Any]] = {}
        for pm in self.payment_methods:
            payment_snap[pm.id] = {
                "card_type": pm.card_type,
                "last_four": pm.last_four,
                "is_default": pm.is_default,
            }

        message_snap: dict[str, dict[str, Any]] = {}
        for msg in self.messages:
            message_snap[msg.id] = {
                "property_id": msg.property_id,
                "subject": msg.subject,
                "sender": msg.sender,
                "read": msg.read,
            }

        notification_snap: dict[str, dict[str, Any]] = {}
        for n in self.notifications:
            notification_snap[n.id] = {
                "type": n.type,
                "title": n.title,
                "read": n.read,
            }

        settings = self.settings.model_dump(mode="json")
        settings.pop("id", None)

        return {
            "property_ids": sorted(property_snap.keys()),
            "properties": property_snap,
            "reservations": reservation_snap,
            "reviews": review_snap,
            "saved_lists": saved_snap,
            "payment_methods": payment_snap,
            "messages": message_snap,
            "notifications": notification_snap,
            "recently_viewed": list(self.recently_viewed),
            "search_history_count": len(self.search_history),
            "genius": self.genius.model_dump(),
            "wallet_balance": self.wallet.balance,
            "settings": settings,
        }

    def session_summary(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "task_id": self.task_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "counts": {
                "properties": len(self.properties),
                "reservations": len(self.reservations),
                "reviews": len(self.reviews),
                "saved_lists": len(self.saved_lists),
                "payment_methods": len(self.payment_methods),
                "messages": len(self.messages),
                "notifications": len(self.notifications),
                "unread_notifications": self.unread_notification_count(),
                "search_history": len(self.search_history),
                "recently_viewed": len(self.recently_viewed),
            },
        }
