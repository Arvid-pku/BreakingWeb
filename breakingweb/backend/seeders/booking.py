"""Composable seed runner for Booking.com environment tasks.

Reads the ``seed:`` section from a :class:`TaskDefinition` YAML, resolves
actors, executes builder steps, adds distractors, and evaluates targets.
"""

from __future__ import annotations

import json
import random
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from breakingweb.backend.models.booking import (
    BookingSettings,
    CancellationPolicy,
    GeoLocation,
    HouseRules,
    Message,
    NearbyAttraction,
    Notification,
    PaymentMethod,
    Reservation,
    ReservationGuest,
    Review,
    ReviewBreakdown,
    RoomType,
    SavedList,
    SearchHistoryEntry,
    WalletTransaction,
)
from breakingweb.backend.seeder import derive_anchor_time
from breakingweb.backend.seeders._common import _assign_output
from breakingweb.tasks._schema import TaskDefinition
from breakingweb.tasks._seed_builders_booking import (
    BOOKING_BUILDER_REGISTRY,
    BookingSeedContext,
)

# Load real hotel data
_REAL_HOTELS_PATH = Path(__file__).parent.parent.parent / "tasks" / "booking_real_hotels.json"
_REAL_HOTELS: dict[str, list[dict[str, Any]]] = {}
if _REAL_HOTELS_PATH.exists():
    _REAL_HOTELS = json.loads(_REAL_HOTELS_PATH.read_text())

_TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
_EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")

# ---------------------------------------------------------------------------
# City data for distractor generation
# ---------------------------------------------------------------------------

_CITIES: dict[str, dict[str, Any]] = {
    "New York": {"country": "United States", "currency": "USD", "lat": 40.7128, "lng": -73.9060},
    "Paris": {"country": "France", "currency": "EUR", "lat": 48.8566, "lng": 2.3522},
    "Tokyo": {"country": "Japan", "currency": "JPY", "lat": 35.6762, "lng": 139.6503},
    "London": {"country": "United Kingdom", "currency": "GBP", "lat": 51.5074, "lng": -0.1278},
    "Barcelona": {"country": "Spain", "currency": "EUR", "lat": 41.3874, "lng": 2.1686},
    "Rome": {"country": "Italy", "currency": "EUR", "lat": 41.9028, "lng": 12.4964},
    "Dubai": {"country": "United Arab Emirates", "currency": "AED", "lat": 25.2048, "lng": 55.2708},
    "Bangkok": {"country": "Thailand", "currency": "THB", "lat": 13.7563, "lng": 100.5018},
}

_IMG = "https://images.unsplash.com"
_HOTEL_IMAGES = [
    f"{_IMG}/photo-1566073771259-6a8506099945?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1551882547-ff40c63fe5fa?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1564501049412-61c2a3083791?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1520250497591-112f2f40a3f4?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1542314831-068cd1dbfeeb?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1571896349842-33c89424de2d?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1586611292717-f828b167408c?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1582719508461-905c673771fd?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1445019980597-93fa8acb246c?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1584132967334-10e028bd69f7?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1568084680786-a84f91d1153c?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1596436889106-be35e843f974?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1578683010236-d716f9a3f461?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1455587734955-081b22074882?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1611892440504-42a792e24d32?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1590490360182-c33d955e0bbf?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1563911302283-d2bc129e7570?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1609949279531-cf48d64bed89?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1512918728675-ed5a9ecdebfd?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1518733057094-95b53143d2a7?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1549294413-26f195471c9c?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1559599238-308793637427?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1580041065738-e72023775cdc?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1587213811864-46e59f6873b1?w=800&h=600&fit=crop&auto=format",
    f"{_IMG}/photo-1573052905904-34ad8c27f0cc?w=800&h=600&fit=crop&auto=format",
]

_ROOM_IMAGES = [
    f"{_IMG}/photo-1618773928121-c32f949e0e40?w=600&h=400&fit=crop&auto=format",
    f"{_IMG}/photo-1631049307264-da0ec9d70304?w=600&h=400&fit=crop&auto=format",
    f"{_IMG}/photo-1582719478250-c89cae4dc85b?w=600&h=400&fit=crop&auto=format",
    f"{_IMG}/photo-1566665797739-1674de7a421a?w=600&h=400&fit=crop&auto=format",
    f"{_IMG}/photo-1595576508898-0ad5c879a061?w=600&h=400&fit=crop&auto=format",
    f"{_IMG}/photo-1540518614846-7eded433c457?w=600&h=400&fit=crop&auto=format",
    f"{_IMG}/photo-1560448204-e02f11c3d0e2?w=600&h=400&fit=crop&auto=format",
    f"{_IMG}/photo-1578683010236-d716f9a3f461?w=600&h=400&fit=crop&auto=format",
]

_AMENITIES_POOL = [
    "Free WiFi", "Air conditioning", "24-hour front desk", "Restaurant", "Bar",
    "Fitness center", "Room service", "Non-smoking rooms", "Parking", "Pool",
    "Spa", "Laundry", "Concierge", "Business center", "Airport shuttle",
    "Pet-friendly", "Elevator", "Heating", "Garden", "Terrace",
    "Sauna", "Hot tub", "Kids' club", "Tennis court", "EV charging",
]

_ROOM_AMENITIES = [
    "Air conditioning", "Private bathroom", "TV", "Free WiFi", "Minibar",
    "Safe", "Coffee machine", "Hairdryer", "Iron", "Desk",
    "Bathrobe", "Slippers", "Balcony", "Soundproofing", "Refrigerator",
]

_REVIEW_POSITIVES = [
    "Excellent location, walking distance to major attractions.",
    "Staff was incredibly friendly and helpful throughout our stay.",
    "The room was spotlessly clean and very comfortable.",
    "Great breakfast with a wide variety of options.",
    "Beautiful property with stunning views from the room.",
    "Perfect for a city break, close to public transport.",
    "The spa was amazing, highly recommend the treatments.",
    "Quiet despite being in the city center. Great soundproofing.",
    "The bed was incredibly comfortable, best sleep in ages.",
    "Great value for money considering the quality and location.",
]

_REVIEW_NEGATIVES = [
    "Room was a bit smaller than expected.",
    "WiFi could be faster in the rooms.",
    "Breakfast was good but got crowded during peak hours.",
    "Parking was expensive and limited.",
    "Check-in took longer than expected.",
    "Air conditioning was a bit noisy.",
    "Could use more power outlets near the bed.",
    "The bathroom could use an update.",
    "",  # some reviews have no negatives
    "",
]

_COUNTRIES_FOR_REVIEWERS = [
    "United States", "United Kingdom", "Germany", "France", "Australia",
    "Canada", "Netherlands", "Italy", "Spain", "Japan", "Brazil",
    "South Korea", "Sweden", "Switzerland", "India",
]


class BookingSeedRunner:
    """Execute the declarative ``seed:`` config from a Booking task YAML."""

    def run(
        self,
        task: TaskDefinition,
        seed: int,
        fake: Any,
        rng: random.Random,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        now = derive_anchor_time(seed)
        base = self._base_skeleton(task.task_id)
        ctx = BookingSeedContext(seed=seed, rng=rng, fake=fake, now=now, base=base)

        seed_cfg = task.seed
        if seed_cfg is None:
            raise ValueError(f"Task {task.task_id} has no seed config")

        # 1. Resolve actors
        for key, actor_spec in seed_cfg.actors.items():
            ctx.resolve_actor(key, domain=actor_spec.domain, is_vip=actor_spec.is_vip, name=actor_spec.name)

        # 2. Load real hotel catalog (skip if task disables it for clean test)
        if not getattr(seed_cfg, "skip_real_hotels", False):
            self._add_real_hotels(ctx)

        # 3. Add distractor properties
        self._add_distractor_properties(ctx, count=seed_cfg.distractors)

        # 4. Execute builder steps
        for step in seed_cfg.steps:
            builder = BOOKING_BUILDER_REGISTRY.get(step.use)
            if builder is None:
                raise KeyError(f"No builder '{step.use}' for task {task.task_id}")
            resolved_params = self._resolve_params(step.params, ctx)
            result = builder(ctx, resolved_params)
            self._store_step_outputs(
                task_id=task.task_id,
                builder_name=step.use,
                declared_outputs=step.outputs,
                result=result,
                ctx=ctx,
            )

        # 5. Seed realistic account state
        self._add_initial_account_state(ctx)

        # 6. Sync id_counters to avoid collisions with seeded IDs
        self._sync_id_counters(base, ctx)

        # 7. Sort properties by review_count (popularity)
        base["properties"] = sorted(base["properties"], key=lambda p: p.review_count, reverse=True)

        # 8. Resolve targets
        targets = self._resolve_targets(seed_cfg.targets, ctx)
        return base, targets

    @staticmethod
    def _sync_id_counters(base: dict[str, Any], ctx: BookingSeedContext) -> None:
        """Set id_counters high enough to avoid collisions with seeded IDs."""
        base["id_counters"]["review"] = ctx._review_counter
        base["id_counters"]["res"] = ctx._res_counter
        base["id_counters"]["room"] = ctx._room_counter
        base["id_counters"]["prop"] = ctx._prop_counter
        # Count existing messages, notifications, saved lists
        base["id_counters"]["msg"] = len(base.get("messages", []))
        base["id_counters"]["notif"] = len(base.get("notifications", []))
        base["id_counters"]["list"] = len(base.get("saved_lists", []))
        base["id_counters"]["conf"] = ctx._res_counter
        base["id_counters"]["pm"] = len(base.get("payment_methods", []))

    # ------------------------------------------------------------------
    # Base skeleton
    # ------------------------------------------------------------------

    @staticmethod
    def _base_skeleton(task_id: str) -> dict[str, Any]:
        payment_methods = [
            PaymentMethod(
                id="pm_1", card_type="Visa", last_four="4242",
                expiry="12/28", holder_name="Jordan Parker", is_default=True,
            ),
            PaymentMethod(
                id="pm_2", card_type="Mastercard", last_four="8888",
                expiry="03/27", holder_name="Jordan Parker", is_default=False,
            ),
            PaymentMethod(
                id="pm_3", card_type="Amex", last_four="1234",
                expiry="09/29", holder_name="Jordan Parker", is_default=False,
            ),
            PaymentMethod(
                id="pm_4", card_type="Visa", last_four="9876",
                expiry="06/27", holder_name="Jordan Parker", is_default=False,
            ),
        ]
        return {
            "env_id": "booking",
            "task_id": task_id,
            "owner_name": "Jordan Parker",
            "owner_email": "jordan.parker@email.com",
            "owner_phone": "+1-217-555-0142",
            "owner_nationality": "United States",
            "owner_date_of_birth": "1990-06-15",
            "owner_gender": "male",
            "owner_address": "742 Evergreen Terrace, Springfield, IL 62704",
            "properties": [],
            "reservations": [],
            "reviews": [],
            "saved_lists": [],
            "payment_methods": payment_methods,
            "messages": [],
            "notifications": [],
            "search_history": [],
            "genius": {
                "level": 2,
                "total_bookings": 12,
                "bookings_needed_for_next": 3,
                "benefits": [
                    "10-15% discounts on select stays",
                    "Free breakfast at select properties",
                    "Free room upgrades at select properties",
                ],
            },
            "travel_preferences": {
                "smoking": False,
                "preferred_bed_type": "king",
                "floor_preference": "high",
                "accessibility_needs": False,
                "preferred_room_type": "Deluxe",
                "dietary_restrictions": ["vegetarian"],
                "preferred_language": "English",
                "preferred_currency": "USD",
            },
            "wallet": {
                "balance": 47.50,
                "currency": "USD",
                "transactions": [],
            },
            "recently_viewed": [],
            "is_logged_in": True,
            "password_hash": "simulated_hash",
            "id_counters": {"pm": 5},
            "settings": BookingSettings(
                id="settings_booking",
                default_payment_id="pm_1",
                email_notifications=True,
                deal_alerts=True,
                review_reminders=True,
                price_alerts=True,
                newsletter=False,
                sms_notifications=True,
                language="English",
                currency="USD",
                country="United States",
                two_factor_enabled=False,
            ),
        }

    # ------------------------------------------------------------------
    # Load real hotel data
    # ------------------------------------------------------------------

    @staticmethod
    def _add_real_hotels(ctx: BookingSeedContext) -> None:
        """Load real hotel data from the JSON file."""
        if not _REAL_HOTELS:
            return

        for city, hotels in _REAL_HOTELS.items():
            city_info = _CITIES.get(city, {"country": "", "currency": "USD", "lat": 0, "lng": 0})
            shuffled = list(hotels)
            ctx.rng.shuffle(shuffled)

            for hotel_data in shuffled[:25]:  # Up to 25 per city
                name = hotel_data.get("name", "")
                if not name:
                    continue

                amenities = hotel_data.get("amenities", [])
                if not amenities:
                    amenities = ctx.rng.sample(_AMENITIES_POOL, k=min(10, len(_AMENITIES_POOL)))

                review_score = hotel_data.get("review_score", round(ctx.rng.uniform(7.0, 9.5), 1))
                prop = ctx.make_property(
                    name=name,
                    city=city,
                    country=city_info["country"],
                    property_type=hotel_data.get("property_type", "hotel"),
                    star_rating=hotel_data.get("star_rating", 4),
                    neighborhood=hotel_data.get("neighborhood", "City Center"),
                    address=hotel_data.get("address", ""),
                    lat=hotel_data.get("lat", city_info["lat"] + ctx.rng.uniform(-0.05, 0.05)),
                    lng=hotel_data.get("lng", city_info["lng"] + ctx.rng.uniform(-0.05, 0.05)),
                    description=hotel_data.get("description", f"Welcome to {name}, located in the heart of {city}."),
                    review_score=review_score,
                    review_count=hotel_data.get("review_count", ctx.rng.randint(200, 5000)),
                    amenities=amenities,
                    popular_facilities=hotel_data.get("popular_facilities", amenities[:5]),
                    distance_from_center_km=hotel_data.get("distance_from_center_km",
                                                            round(ctx.rng.uniform(0.2, 5.0), 1)),
                    genius_discount_pct=hotel_data.get("genius_discount_pct", ctx.rng.choice([0, 0, 0, 10, 15])),
                    chain_name=hotel_data.get("chain_name", ""),
                    currency=city_info["currency"],
                )

                # Add nearby attractions
                attractions = hotel_data.get("nearby_attractions", [])
                for attr in attractions[:5]:
                    prop.nearby_attractions.append(NearbyAttraction(
                        name=attr.get("name", ""),
                        distance_km=attr.get("distance_km", 0.5),
                        type=attr.get("type", "landmark"),
                    ))

                # Add rooms from data or generate
                rooms_data = hotel_data.get("rooms", [])
                if rooms_data:
                    for rd in rooms_data:
                        price = rd.get("price_per_night", 150.0)
                        room = ctx.make_room(
                            prop.id,
                            rd.get("name", "Standard Room"),
                            price,
                            max_occupancy=rd.get("max_occupancy", 2),
                            bed_type=rd.get("bed_type", "double"),
                            bed_count=rd.get("bed_count", 1),
                            room_size_sqm=rd.get("room_size_sqm", 25.0),
                            original_price=rd.get("original_price"),
                            amenities=rd.get("amenities", ctx.rng.sample(_ROOM_AMENITIES, k=6)),
                            meals_included=rd.get("meals_included", "none"),
                            cancel_type=rd.get("cancellation_type", "free_cancellation"),
                            cancel_days=rd.get("free_cancel_before_days", 1),
                            view_type=rd.get("view_type", ""),
                        )
                        prop.room_types.append(room)
                else:
                    # Generate rooms based on star rating
                    BookingSeedRunner._generate_rooms(ctx, prop)

                # Add sample reviews from data
                sample_reviews = hotel_data.get("sample_reviews", [])
                for sr in sample_reviews:
                    ctx._review_counter += 1
                    review = Review(
                        id=f"review_{ctx._review_counter}",
                        property_id=prop.id,
                        author_name=sr.get("author_name", ctx.fake.name()),
                        author_country=sr.get("author_country", ctx.rng.choice(_COUNTRIES_FOR_REVIEWERS)),
                        overall_score=sr.get("overall_score", review_score),
                        title=sr.get("title", ""),
                        positive=sr.get("positive", ctx.rng.choice(_REVIEW_POSITIVES)),
                        negative=sr.get("negative", ctx.rng.choice(_REVIEW_NEGATIVES)),
                        travel_purpose=sr.get("travel_purpose", ctx.rng.choice(["business", "leisure", "family"])),
                        traveled_with=sr.get("traveled_with", ctx.rng.choice(["solo", "couple", "family", "friends"])),
                        stay_date=sr.get("stay_date", (ctx.now - timedelta(days=ctx.rng.randint(30, 365))).strftime("%Y-%m")),
                        created_at=ctx.now - timedelta(days=ctx.rng.randint(5, 365)),
                    )
                    ctx.base["reviews"].append(review)

                ctx.base["properties"].append(prop)

    @staticmethod
    def _generate_rooms(ctx: BookingSeedContext, prop: Property) -> None:
        """Generate realistic rooms based on property star rating."""
        star = prop.star_rating
        base_price = {1: 40, 2: 70, 3: 120, 4: 200, 5: 450}.get(star, 150)
        # Adjust for city
        city_mult = {"New York": 1.5, "Paris": 1.3, "Tokyo": 1.2, "London": 1.4,
                     "Barcelona": 1.0, "Rome": 1.0, "Dubai": 1.3, "Bangkok": 0.6}.get(prop.city, 1.0)
        base_price = round(base_price * city_mult * ctx.rng.uniform(0.85, 1.15), 2)

        room_configs = [
            ("Standard Double Room", base_price, "double", 2, 22),
            ("Deluxe Double Room", base_price * 1.4, "queen", 2, 28),
            ("Superior Suite", base_price * 2.0, "king", 3, 40),
        ]
        if star >= 4:
            room_configs.append(("Family Room", base_price * 1.6, "twin", 4, 35))
        if star >= 5:
            room_configs.append(("Presidential Suite", base_price * 4.0, "king", 2, 75))

        for name, price, bed, occ, size in room_configs:
            is_deal = ctx.rng.random() < 0.2
            orig = round(price * ctx.rng.uniform(1.15, 1.35), 2) if is_deal else None
            cancel = ctx.rng.choice(["free_cancellation", "free_cancellation", "non_refundable"])
            meals = ctx.rng.choice(["none", "none", "breakfast"]) if star >= 3 else "none"
            room = ctx.make_room(
                prop.id, name, round(price, 2),
                max_occupancy=occ, bed_type=bed, room_size_sqm=size,
                original_price=orig,
                amenities=ctx.rng.sample(_ROOM_AMENITIES, k=min(7, len(_ROOM_AMENITIES))),
                meals_included=meals,
                cancel_type=cancel,
                view_type=ctx.rng.choice(["", "city", "garden"]),
                rooms_left=ctx.rng.randint(1, 8),
            )
            prop.room_types.append(room)

    # ------------------------------------------------------------------
    # Distractors
    # ------------------------------------------------------------------

    @staticmethod
    def _add_distractor_properties(ctx: BookingSeedContext, count: int) -> None:
        """Add distractor properties from random cities."""
        cities = list(_CITIES.keys())
        generic_names = [
            "Central Inn", "Park View Hotel", "City Lodge", "Grand Palace",
            "Riverside Suites", "Harbor Hotel", "Metro Stay", "Urban Loft Hotel",
            "Sunset Resort", "Crown Plaza Inn", "The Heritage", "Royal Garden Hotel",
            "Oceanfront Lodge", "Lakeside Inn", "Mountain View Resort",
        ]
        for _ in range(count):
            city = ctx.rng.choice(cities)
            ci = _CITIES[city]
            name = f"{ctx.rng.choice(generic_names)} {city}"
            star = ctx.rng.choice([2, 3, 3, 4, 4, 4, 5])
            score = round(ctx.rng.uniform(6.5, 9.2), 1)

            prop = ctx.make_property(
                name=name, city=city, country=ci["country"],
                star_rating=star,
                review_score=score,
                review_count=ctx.rng.randint(50, 3000),
                amenities=ctx.rng.sample(_AMENITIES_POOL, k=ctx.rng.randint(5, 12)),
                distance_from_center_km=round(ctx.rng.uniform(0.5, 8.0), 1),
                genius_discount_pct=ctx.rng.choice([0, 0, 0, 10]),
                currency=ci["currency"],
            )
            prop.popular_facilities = prop.amenities[:4]
            BookingSeedRunner._generate_rooms(ctx, prop)
            ctx.base["properties"].append(prop)

    # ------------------------------------------------------------------
    # Initial account state
    # ------------------------------------------------------------------

    @staticmethod
    def _add_initial_account_state(ctx: BookingSeedContext) -> None:
        """Populate with a rich, realistic, lived-in account state."""
        base = ctx.base
        properties = base["properties"]
        if len(properties) < 20:
            return

        pool = list(properties)
        ctx.rng.shuffle(pool)
        idx = 0

        owner = base["owner_name"]
        email = base["owner_email"]
        pm_ids = [pm.id for pm in base["payment_methods"]]

        # ================================================================
        # Past reservations (15 — spanning 2 years of travel history)
        # ================================================================
        res_specs = [
            # (days_ago, status, nights, guests, rooms, purpose)
            (730, "completed", 5, 2, 1, "leisure"),       # 2-year-old trip
            (540, "completed", 3, 1, 1, "business"),      # business trip
            (450, "completed", 7, 2, 1, "leisure"),       # week vacation
            (365, "completed", 4, 4, 2, "leisure"),       # family trip
            (300, "completed", 2, 1, 1, "business"),      # quick business
            (240, "completed", 3, 2, 1, "leisure"),       # weekend getaway
            (180, "completed", 5, 2, 1, "leisure"),       # summer trip
            (120, "completed", 2, 1, 1, "business"),      # conference
            (90,  "completed", 4, 2, 1, "leisure"),       # autumn trip
            (60,  "completed", 3, 2, 1, "leisure"),       # recent trip
            (30,  "completed", 2, 1, 1, "business"),      # last month
            (21,  "confirmed", 3, 2, 1, "leisure"),       # upcoming soon
            (14,  "confirmed", 5, 2, 1, "leisure"),       # upcoming vacation
            (7,   "cancelled", 2, 1, 1, "business"),      # cancelled trip
            (5,   "modified", 4, 2, 1, "leisure"),        # modified booking
        ]
        created_reservations: list[Reservation] = []
        for i, (days_ago, status, nights, guests, rooms, purpose) in enumerate(res_specs):
            prop = pool[idx % len(pool)]
            idx += 1
            room = prop.room_types[0] if prop.room_types else None
            if not room:
                continue
            # Use a mix of room types
            if len(prop.room_types) > 1 and ctx.rng.random() < 0.4:
                room = ctx.rng.choice(prop.room_types[1:])
            check_in = (ctx.now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            check_out = (ctx.now - timedelta(days=days_ago - nights)).strftime("%Y-%m-%d")
            pm_id = ctx.rng.choice(pm_ids)
            res = ctx.make_reservation(
                property_id=prop.id, property_name=prop.name,
                room_type_id=room.id, room_type_name=room.name,
                check_in=check_in, check_out=check_out,
                price_per_night=room.price_per_night, status=status,
                guests=guests, rooms=rooms,
                payment_method_id=pm_id,
                days_ago=days_ago + ctx.rng.randint(10, 40),
            )
            # Add meals for some
            if ctx.rng.random() < 0.3:
                res.meals_included = ctx.rng.choice(["breakfast", "half_board"])
            # Genius deals for some
            if prop.is_genius_property and ctx.rng.random() < 0.5:
                res.is_genius_deal = True
                res.genius_discount = round(res.total_price * 0.1, 2)
                res.total_price = round(res.total_price - res.genius_discount, 2)
            created_reservations.append(res)
            base["reservations"].append(res)

        # ================================================================
        # Reviews for completed stays (10 reviews with varied quality)
        # ================================================================
        completed = [r for r in created_reservations if r.status == "completed"]
        review_templates = [
            (9.5, "Exceptional stay!", "Absolutely outstanding in every way. The staff anticipated our every need. Room was immaculate and the view was breathtaking. The spa treatment was the best I've ever had.", "Minor: elevator wait times during peak hours."),
            (9.0, "Wonderful experience", "Everything was perfect from check-in to check-out. The location is unbeatable and the breakfast spread was impressive. Will definitely return.", "WiFi was a bit slow in the room."),
            (8.5, "Highly recommended", "Staff was incredibly friendly and helpful. Room was clean, comfortable, and well-appointed. Great restaurant on-site.", "Street-facing room was a bit noisy at night."),
            (8.0, "Very good hotel", "Nice property with good facilities. The pool area was lovely and the bar had great cocktails. Good value for the location.", "Room could have been slightly larger. Bathroom needs updating."),
            (7.5, "Good, with some issues", "Decent location and clean rooms. Breakfast was varied and tasty. Staff was generally helpful.", "Air conditioning was noisy. Had to call maintenance. Checkout queue was long."),
            (7.0, "Adequate for the price", "It served its purpose well. Location was convenient for my meetings. Bed was comfortable.", "Room felt dated. Limited dining options. Parking was confusing."),
            (8.8, "Perfect for business", "Excellent business facilities, fast WiFi, quiet rooms. The concierge arranged everything perfectly for my meetings. Great executive lounge.", "No pool, which would have been nice for relaxation after work."),
            (9.2, "Dream vacation spot", "This hotel made our anniversary trip unforgettable. The surprise champagne and rose petals were a wonderful touch. Rooftop dinner was magical.", ""),
            (6.5, "Below expectations", "The location is good but the room didn't match the photos online. Bathroom was small and the fixtures felt cheap.", "Housekeeping missed our room one day. Front desk was unhelpful about the issue."),
            (8.3, "Great family hotel", "Kids loved the pool and the kids' club. Family room was spacious. The restaurant had a good children's menu. Close to major attractions.", "Could use more power outlets near the beds."),
        ]
        for i, res in enumerate(completed[:10]):
            score, title, pos, neg = review_templates[i % len(review_templates)]
            ctx._review_counter += 1
            purposes = ["leisure", "business", "family"]
            companions = ["solo", "couple", "family", "friends"]
            review = Review(
                id=f"review_{ctx._review_counter}",
                property_id=res.property_id,
                reservation_id=res.id,
                author_name=owner,
                author_country=base["owner_nationality"],
                overall_score=score,
                scores=ReviewBreakdown(
                    staff=round(score + ctx.rng.uniform(-0.5, 0.5), 1),
                    facilities=round(score + ctx.rng.uniform(-0.8, 0.3), 1),
                    cleanliness=round(score + ctx.rng.uniform(-0.3, 0.5), 1),
                    comfort=round(score + ctx.rng.uniform(-0.4, 0.4), 1),
                    value_for_money=round(score + ctx.rng.uniform(-1.0, 0.2), 1),
                    location=round(score + ctx.rng.uniform(-0.2, 0.6), 1),
                    free_wifi=round(score + ctx.rng.uniform(-0.8, 0.3), 1),
                ),
                title=title, positive=pos, negative=neg,
                travel_purpose=ctx.rng.choice(purposes),
                traveled_with=ctx.rng.choice(companions),
                stay_date=res.check_in[:7],
                created_at=ctx.now - timedelta(days=ctx.rng.randint(2, 60)),
            )
            base["reviews"].append(review)
            res.rating_submitted = True

        # ================================================================
        # Saved lists (5 lists with varied themes)
        # ================================================================
        list_configs = [
            ("Summer 2026 Ideas", 6),
            ("Business Trip Hotels", 4),
            ("Romantic Getaways", 5),
            ("Family-Friendly Stays", 4),
            ("Budget Finds", 3),
        ]
        for li, (list_name, count) in enumerate(list_configs, 1):
            pids = []
            for j in range(count):
                p = pool[(idx + j) % len(pool)]
                if p.id not in pids:
                    pids.append(p.id)
            idx += count
            sl = SavedList(
                id=f"list_initial_{li}", name=list_name,
                property_ids=pids,
                created_at=ctx.now - timedelta(days=ctx.rng.randint(10, 120)),
                updated_at=ctx.now - timedelta(days=ctx.rng.randint(0, 15)),
            )
            base["saved_lists"].append(sl)

        # ================================================================
        # Messages (12 — conversations with multiple properties)
        # ================================================================
        msg_id = 0
        msg_templates = [
            # (days_ago, sender, subject, body_template, read)
            (95, "property", "Welcome! Your reservation is confirmed",
             "Dear {name}, thank you for choosing {hotel}. We're delighted to confirm your reservation. Check-in is from 14:00. If you have any special requests, please let us know. We look forward to welcoming you!", True),
            (94, "guest", "Re: Welcome! Your reservation is confirmed",
             "Thank you! Could you please arrange a late check-out until 13:00? Also, we'd appreciate a quiet room on a higher floor if possible.", True),
            (93, "property", "Re: Re: Welcome! Your reservation is confirmed",
             "Of course, {name}! We've noted your preference for a high-floor quiet room. Late check-out until 13:00 has been arranged at no extra charge. See you soon!", True),
            (85, "property", "Thank you for staying with us",
             "Dear {name}, we hope you had a wonderful stay at {hotel}. Your feedback is valuable to us. Would you consider leaving a review? Thank you for being a loyal guest!", True),
            (70, "property", "Special offer for returning guests",
             "Dear {name}, as a valued past guest, we're pleased to offer you an exclusive 15% discount on your next stay at {hotel}. Use code RETURNING15 at checkout. Valid for the next 90 days.", False),
            (45, "property", "Your upcoming reservation",
             "Dear {name}, we're preparing for your arrival at {hotel}. Please let us know if you need airport transfer or restaurant reservations. Our concierge team is at your service.", True),
            (44, "guest", "Re: Your upcoming reservation",
             "Thanks for the reminder! Could you recommend a good restaurant nearby for a dinner reservation on our first evening? Also, is the spa open in the evenings?", True),
            (43, "property", "Re: Re: Your upcoming reservation",
             "Great question! We recommend Le Petit Bistro just 5 minutes away — shall we make a reservation for you? The spa is open until 21:00 daily. We also have in-room massage options.", True),
            (20, "property", "Important: Updated check-in information",
             "Dear {name}, please note that our main entrance is temporarily under renovation. Please use the side entrance on Oak Street. A porter will be available to assist with your luggage. We apologize for any inconvenience.", False),
            (10, "property", "Exclusive Genius deal for you",
             "Dear {name}, as a Genius Level 2 member, you're eligible for an additional 5% off our already discounted rates this month. Don't miss out — limited availability!", False),
            (5, "property", "We miss you! Come back soon",
             "Dear {name}, it's been a while since your last visit to {hotel}. We've made some exciting upgrades including a new rooftop bar. Book now and enjoy our loyalty discount!", False),
            (2, "property", "Booking modification confirmed",
             "Dear {name}, your booking modification has been processed. Your new dates are confirmed. If you have any questions, please don't hesitate to contact us.", False),
        ]
        # Distribute messages across the first 4 completed reservations
        msg_res_pool = completed[:4]
        for mi, (days_ago, sender, subject, body_tpl, is_read) in enumerate(msg_templates):
            msg_id += 1
            res_for_msg = msg_res_pool[mi % len(msg_res_pool)] if msg_res_pool else created_reservations[0]
            prop_for_msg = next((p for p in properties if p.id == res_for_msg.property_id), pool[0])
            body = body_tpl.replace("{name}", owner).replace("{hotel}", prop_for_msg.name)
            msg = Message(
                id=f"msg_initial_{msg_id}",
                property_id=prop_for_msg.id,
                property_name=prop_for_msg.name,
                reservation_id=res_for_msg.id,
                subject=subject, body=body,
                sender=sender, read=is_read,
                created_at=ctx.now - timedelta(days=days_ago),
            )
            base["messages"].append(msg)

        # ================================================================
        # Notifications (15 — varied types)
        # ================================================================
        notif_templates = [
            ("booking_confirmed", "Booking confirmed", "Your reservation at {hotel} has been confirmed. Confirmation number: {conf}. Have a great trip!", True, 180),
            ("booking_confirmed", "Booking confirmed", "Your reservation at {hotel} has been confirmed. Check-in: {checkin}.", True, 120),
            ("booking_confirmed", "Booking confirmed", "Your upcoming stay at {hotel} is confirmed. We look forward to welcoming you!", True, 30),
            ("booking_cancelled", "Booking cancelled", "Your reservation at {hotel} has been cancelled. A refund will be processed within 5-10 business days.", True, 7),
            ("review_reminder", "How was your stay at {hotel}?", "Share your experience and help other travelers. Leave a review now!", False, 55),
            ("review_reminder", "Don't forget to review {hotel}", "Your feedback helps the property improve and helps other travelers choose. It only takes 2 minutes!", False, 25),
            ("deal_alert", "Flash deal: 25% off in Paris", "Exclusive savings on select Paris properties this weekend. Book by Friday for the best rates!", False, 12),
            ("deal_alert", "Weekend getaway deals", "Escape the city! Up to 30% off on countryside retreats and spa hotels. Limited rooms available.", False, 8),
            ("deal_alert", "Last-minute deal: Tokyo", "Save up to 20% on select Tokyo hotels for travel within the next 2 weeks. Don't miss out!", False, 4),
            ("genius_upgrade", "You're now Genius Level 2!", "Congratulations! You've unlocked Genius Level 2. Enjoy free breakfast, room upgrades, and up to 15% off at select properties worldwide.", True, 90),
            ("price_drop", "Price drop on a saved property", "Great news! The price has dropped on a property in your 'Summer 2026 Ideas' list. Check it out before it goes back up!", False, 6),
            ("price_drop", "Price alert: {hotel}", "A room you viewed recently has dropped in price by 18%. Book now to lock in the savings!", False, 3),
            ("booking_reminder", "Your trip is in 3 days!", "Reminder: your stay at {hotel} starts in 3 days. Don't forget to check the property's COVID-19 policies and check-in instructions.", False, 18),
            ("loyalty_reward", "You earned $15 in travel credits!", "Thanks for your recent stay. $15 has been added to your Booking.com Wallet. Use it on your next booking!", True, 45),
            ("system", "Account security update", "We've updated our security policies. We recommend enabling two-factor authentication for added protection.", False, 15),
        ]
        for ni, (ntype, title_tpl, msg_tpl, is_read, days_ago) in enumerate(notif_templates, 1):
            # Fill in property references from reservations
            ref_res = created_reservations[ni % len(created_reservations)]
            ref_prop = next((p for p in properties if p.id == ref_res.property_id), pool[0])
            title = title_tpl.replace("{hotel}", ref_prop.name)
            msg = msg_tpl.replace("{hotel}", ref_prop.name).replace(
                "{conf}", ref_res.confirmation_number).replace(
                "{checkin}", ref_res.check_in)
            related = ref_res.id if "booking" in ntype else None
            notif = Notification(
                id=f"notif_initial_{ni}", type=ntype, title=title, message=msg,
                read=is_read, related_id=related,
                created_at=ctx.now - timedelta(days=days_ago),
            )
            base["notifications"].append(notif)

        # ================================================================
        # Recently viewed (12 properties)
        # ================================================================
        for j in range(min(12, len(pool) - idx)):
            pid = pool[(idx + j) % len(pool)].id
            if pid not in base["recently_viewed"]:
                base["recently_viewed"].append(pid)
        idx += 12

        # ================================================================
        # Search history (10 searches)
        # ================================================================
        search_entries = [
            ("New York", "2026-03-15", "2026-03-18", 2, 1, 35),
            ("Paris", "2026-04-01", "2026-04-05", 2, 1, 28),
            ("Tokyo hotels near Shinjuku", "2026-05-10", "2026-05-15", 1, 1, 22),
            ("London boutique hotel", "2026-05-20", "2026-05-24", 2, 1, 18),
            ("Barcelona beach hotel", "2026-06-20", "2026-06-25", 2, 1, 14),
            ("Rome family hotel", "2026-07-01", "2026-07-07", 4, 2, 10),
            ("Dubai luxury resort", "2026-08-10", "2026-08-14", 2, 1, 7),
            ("Bangkok", "2026-09-01", "2026-09-05", 2, 1, 5),
            ("New York 5 star", "2026-10-01", "2026-10-05", 2, 1, 3),
            ("Paris apartments", "2026-04-15", "2026-04-20", 3, 1, 1),
        ]
        for dest, ci, co, guests, rooms, days_ago in search_entries:
            base["search_history"].append(SearchHistoryEntry(
                destination=dest, check_in=ci, check_out=co,
                guests=guests, rooms=rooms,
                searched_at=ctx.now - timedelta(days=days_ago),
            ))

        # ================================================================
        # Wallet transactions (6 entries)
        # ================================================================
        base["wallet"]["transactions"] = [
            WalletTransaction(
                amount=20.00, type="credit",
                description="Welcome bonus for Genius Level 2",
                created_at=ctx.now - timedelta(days=180),
            ),
            WalletTransaction(
                amount=15.00, type="credit",
                description="Reward for 10th booking milestone",
                created_at=ctx.now - timedelta(days=120),
            ),
            WalletTransaction(
                amount=12.50, type="debit",
                description="Applied to reservation at " + (completed[2].property_name if len(completed) > 2 else "hotel"),
                created_at=ctx.now - timedelta(days=90),
            ),
            WalletTransaction(
                amount=10.00, type="credit",
                description="Cashback from Genius deal booking",
                created_at=ctx.now - timedelta(days=60),
            ),
            WalletTransaction(
                amount=15.00, type="credit",
                description="Reward for leaving 5 reviews",
                created_at=ctx.now - timedelta(days=30),
            ),
            WalletTransaction(
                amount=0.00, type="credit",
                description="Referral bonus pending approval",
                created_at=ctx.now - timedelta(days=5),
            ),
        ]
        base["wallet"]["balance"] = 47.50

    # ------------------------------------------------------------------
    # Output / target resolution (same pattern as Amazon)
    # ------------------------------------------------------------------

    @staticmethod
    def _store_step_outputs(
        *, task_id: str, builder_name: str, declared_outputs: list[str],
        result: dict[str, Any], ctx: BookingSeedContext,
    ) -> None:
        result_keys = list(result.keys())
        for index, out_key in enumerate(declared_outputs):
            if out_key in result:
                value = result[out_key]
            elif len(declared_outputs) == len(result_keys):
                # Positional fallback
                value = result[result_keys[index]]
            elif len(result_keys) == 1:
                value = result[result_keys[0]]
            else:
                available = ", ".join(result_keys) if result_keys else "<none>"
                raise KeyError(
                    f"Builder '{builder_name}' for task {task_id} did not produce "
                    f"requested output '{out_key}'. Available: {available}"
                )
            _assign_output(ctx.outputs, out_key, value, task_id=task_id, builder_name=builder_name)

    _TEMPLATE_RE = _TEMPLATE_RE
    _EXACT_REF_RE = _EXACT_REF_RE

    @classmethod
    def _resolve_params(cls, params: dict[str, Any], ctx: BookingSeedContext) -> dict[str, Any]:
        return {k: cls._resolve_value(v, ctx) for k, v in params.items()}

    @classmethod
    def _resolve_value(cls, value: Any, ctx: BookingSeedContext) -> Any:
        if isinstance(value, str):
            exact = cls._EXACT_REF_RE.match(value)
            if exact:
                return cls._raw_lookup(exact.group(1), exact.group(2), ctx)
            return cls._TEMPLATE_RE.sub(
                lambda m: str(cls._raw_lookup(m.group(1), m.group(2), ctx)), value,
            )
        if isinstance(value, list):
            return [cls._resolve_value(v, ctx) for v in value]
        if isinstance(value, dict):
            return {k: cls._resolve_value(v, ctx) for k, v in value.items()}
        return value

    @staticmethod
    def _raw_lookup(kind: str, path: str, ctx: BookingSeedContext) -> Any:
        if kind == "actor":
            parts = path.split(".", 1)
            actor = ctx.actors[parts[0]]
            if len(parts) == 1:
                return actor["name"] if isinstance(actor, dict) else actor.name
            field = parts[1]
            return actor[field] if isinstance(actor, dict) else getattr(actor, field)
        parts = path.split(".")
        obj: Any = ctx.outputs
        for part in parts:
            obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
        return obj

    @classmethod
    def _resolve_targets(cls, templates: dict[str, str], ctx: BookingSeedContext) -> dict[str, Any]:
        return {key: cls._resolve_value(tmpl, ctx) for key, tmpl in templates.items()}
