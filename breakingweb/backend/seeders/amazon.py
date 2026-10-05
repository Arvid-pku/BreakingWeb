"""Composable seed runner for Amazon shopping environment tasks.

Instead of a monolithic per-task method, this runner reads the ``seed:``
section from a :class:`TaskDefinition` YAML, resolves actors, executes
builder steps from :data:`AMAZON_BUILDER_REGISTRY`, adds distractors, and
evaluates target templates.
"""

from __future__ import annotations

import re
import random
from datetime import timedelta
from typing import Any

import json
from pathlib import Path

from breakingweb.backend.models.amazon import (
    AmazonSettings,
    Address,
    PaymentMethod,
    Order,
    OrderItem,
    Review,
    ReturnRequest as ReturnRequestModel,
    Notification,
    BrowsingHistory,
)
from breakingweb.backend.seeder import derive_anchor_time
from breakingweb.backend.seeders._common import _assign_output
from breakingweb.tasks._schema import TaskDefinition
from breakingweb.tasks._seed_builders_amazon import (
    AMAZON_BUILDER_REGISTRY,
    AmazonSeedContext,
)

# Load real product data scraped from Amazon
_REAL_PRODUCTS_PATH = Path(__file__).parent.parent.parent / "tasks" / "amazon_real_products.json"
_REAL_PRODUCTS: dict[str, list[dict[str, Any]]] = {}
if _REAL_PRODUCTS_PATH.exists():
    _REAL_PRODUCTS = json.loads(_REAL_PRODUCTS_PATH.read_text())
_REAL_PRODUCT_IMAGE_COUNTS: dict[str, int] = {}
_REAL_PRODUCT_IMAGE_CATEGORIES: dict[str, set[str]] = {}
for _category, _items in _REAL_PRODUCTS.items():
    for _item in _items:
        _image = _item.get("image")
        if _image:
            _REAL_PRODUCT_IMAGE_COUNTS[_image] = _REAL_PRODUCT_IMAGE_COUNTS.get(_image, 0) + 1
            _REAL_PRODUCT_IMAGE_CATEGORIES.setdefault(_image, set()).add(_category)

_MAX_REAL_IMAGE_REUSE = 2

_TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
_EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")
_MISSING_OUTPUT = object()

# Product generation data used by both the catalog builder and distractors.
_CATEGORIES: dict[str, dict[str, Any]] = {
    "Electronics": {
        "brands": ["TechVolt", "NovaByte", "PixelEdge", "SonicWave", "ZenithPro"],
        "names": [
            "Wireless Bluetooth Earbuds",
            "USB-C Fast Charging Hub",
            "Portable Bluetooth Speaker",
            "Noise-Cancelling Headphones",
            "Smart LED Desk Lamp",
            "Mechanical Keyboard",
            "HD Webcam with Microphone",
            "Wireless Charging Pad",
        ],
        "price_range": (15.99, 349.99),
    },
    "Books": {
        "brands": ["Penguin", "HarperCollins", "Vintage Press", "Beacon Books", "Elm Street Publishing"],
        "names": [
            "The Art of Problem Solving",
            "Mindful Leadership",
            "Data-Driven Decisions",
            "Creative Confidence",
            "The Productivity Playbook",
            "Atomic Habits for Teams",
            "Deep Work Revisited",
            "The Innovation Stack",
        ],
        "price_range": (8.99, 34.99),
    },
    "Home & Kitchen": {
        "brands": ["HomeNest", "CulinaryCraft", "PureComfort", "AquaBliss", "UrbanRoots"],
        "names": [
            "Stainless Steel Water Bottle",
            "Non-Stick Ceramic Frying Pan",
            "Bamboo Cutting Board Set",
            "Insulated Travel Mug",
            "Silicone Kitchen Utensil Set",
            "Electric Kettle",
            "Airtight Food Storage Containers",
            "Cast Iron Dutch Oven",
        ],
        "price_range": (12.99, 89.99),
    },
    "Clothing": {
        "brands": ["UrbanThread", "CrestLine", "EverFit", "NorthTrail", "Loom & Lace"],
        "names": [
            "Slim-Fit Cotton T-Shirt",
            "Moisture-Wicking Running Shorts",
            "Lightweight Puffer Jacket",
            "Classic Denim Jeans",
            "Merino Wool Crew Socks",
            "Stretch Chino Pants",
            "Fleece Pullover Hoodie",
            "Breathable Polo Shirt",
        ],
        "price_range": (14.99, 129.99),
    },
    "Sports & Outdoors": {
        "brands": ["TrailBlaze", "SummitGear", "IronPulse", "AquaTrek", "WindRunner"],
        "names": [
            "Yoga Mat with Carrying Strap",
            "Adjustable Dumbbell Set",
            "Resistance Bands Kit",
            "Insulated Hiking Backpack",
            "Collapsible Water Bottle",
            "Foam Roller for Recovery",
            "LED Headlamp Rechargeable",
            "Camping Hammock with Straps",
        ],
        "price_range": (9.99, 149.99),
    },
    "Toys & Games": {
        "brands": ["FunSpark", "BrainQuest", "PlayCraft", "WonderBox", "TinyTinkers"],
        "names": [
            "1000-Piece Jigsaw Puzzle",
            "Building Blocks Mega Set",
            "Strategy Board Game",
            "Remote Control Car",
            "Science Experiment Kit",
            "Magnetic Tile Set",
            "Card Game Collection",
            "Wooden Train Set",
        ],
        "price_range": (9.99, 79.99),
    },
    "Health & Beauty": {
        "brands": ["PureGlow", "VitaBlend", "ZenCare", "NaturEssence", "ClearSkin"],
        "names": [
            "Vitamin C Serum",
            "Electric Toothbrush",
            "Moisturizing Face Cream",
            "Hair Repair Conditioner",
            "SPF 50 Sunscreen Lotion",
            "Essential Oil Diffuser",
            "Collagen Supplement Capsules",
            "Exfoliating Body Scrub",
        ],
        "price_range": (7.99, 59.99),
    },
    "Office Supplies": {
        "brands": ["DeskPro", "WriteWell", "ClipBoard", "NeatFiles", "InkJoy"],
        "names": [
            "Gel Pen Multipack",
            "Desk Organizer with Drawers",
            "Laminating Machine",
            "Whiteboard Markers Set",
            "Ergonomic Mouse Pad",
            "Document Shredder",
            "Sticky Notes Variety Pack",
            "Cable Management Kit",
        ],
        "price_range": (5.99, 89.99),
    },
}


class AmazonSeedRunner:
    """Execute the declarative ``seed:`` config from an Amazon task YAML."""

    def run(
        self,
        task: TaskDefinition,
        seed: int,
        fake: Any,
        rng: random.Random,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, targets)`` for one Amazon task seed."""
        now = derive_anchor_time(seed)

        # Build the skeleton base state (addresses, payments, empty lists).
        base = self._base_skeleton(task.task_id)

        # Create the context before generating catalog so fake / rng
        # draws stay stable for deterministic seeds.
        ctx = AmazonSeedContext(
            seed=seed,
            rng=rng,
            fake=fake,
            now=now,
            base=base,
        )

        seed_cfg = task.seed
        if seed_cfg is None:
            raise ValueError(
                f"Task {task.task_id} has no seed config — cannot run builder pipeline"
            )

        # 1. Resolve actors (order matches YAML dict order -> deterministic)
        for key, actor_spec in seed_cfg.actors.items():
            ctx.resolve_actor(
                key,
                domain=actor_spec.domain,
                is_vip=actor_spec.is_vip,
                name=actor_spec.name,
            )

        # 2. Add baseline catalog FIRST so builder steps can design
        #    products that beat everything already in the catalog
        #    (e.g. highest-rated, cheapest, biggest discount).
        #    Tasks can opt out via ``seed.skip_real_products`` when the
        #    real-products pool would dominate / collide with the seeded
        #    target (e.g. "highest-rated in Books under $X" — the catalog
        #    has dozens of Books capped at 4.6, so a featured product
        #    rated 4.5 is no longer the prompt-correct answer).
        if not getattr(seed_cfg, "skip_real_products", False):
            self._add_baseline_catalog(ctx, per_category=5)

        # 3. Add generic distractors (product catalog padding)
        self._add_generic_distractors(ctx, count=seed_cfg.distractors)

        # 4. Execute builder steps AFTER the catalog so that featured
        #    products are always added last and can be designed to win
        #    any comparison against the baseline catalog.
        for step in seed_cfg.steps:
            builder = AMAZON_BUILDER_REGISTRY.get(step.use)
            if builder is None:
                raise KeyError(
                    f"No builder registered for '{step.use}' "
                    f"(task {task.task_id})"
                )
            resolved_params = self._resolve_params(step.params, ctx)
            result = builder(ctx, resolved_params)
            self._store_step_outputs(
                task_id=task.task_id,
                builder_name=step.use,
                declared_outputs=step.outputs,
                result=result,
                ctx=ctx,
            )

        # 4b. Seed realistic account history (orders, reviews, returns, etc.)
        self._add_initial_account_state(ctx)

        # 5. Sync id_counters so the state model continues from where
        #    the seeder left off — prevents duplicate IDs at runtime.
        base["id_counters"].update(ctx.counters)

        # 6. Sort products alphabetically by name
        base["products"] = sorted(
            base["products"], key=lambda p: p.name.lower()
        )

        # 7. Resolve target templates
        targets = self._resolve_targets(seed_cfg.targets, ctx)

        return base, targets

    @staticmethod
    def _store_step_outputs(
        *,
        task_id: str,
        builder_name: str,
        declared_outputs: list[str],
        result: dict[str, Any],
        ctx: AmazonSeedContext,
    ) -> None:
        """Persist builder outputs, resolving YAML aliases when possible.

        Amazon task YAMLs often alias canonical builder outputs like
        ``product_id`` to names such as ``product_id_2`` or ``product_id_first``.
        Builders intentionally return stable canonical keys, so the runner needs
        to map those aliases instead of silently dropping them.
        """
        result_keys = list(result.keys())

        for index, out_key in enumerate(declared_outputs):
            if out_key in result:
                value = result[out_key]
            else:
                resolved = AmazonSeedRunner._resolve_output_alias(
                    requested_key=out_key,
                    output_index=index,
                    declared_outputs=declared_outputs,
                    result=result,
                    result_keys=result_keys,
                )
                if resolved is _MISSING_OUTPUT:
                    available = ", ".join(result_keys) if result_keys else "<none>"
                    raise KeyError(
                        f"Builder '{builder_name}' for task {task_id} did not produce "
                        f"requested output '{out_key}'. Available outputs: {available}"
                    )
                value = resolved
            _assign_output(ctx.outputs, out_key, value, task_id=task_id, builder_name=builder_name)

    @staticmethod
    def _resolve_output_alias(
        *,
        requested_key: str,
        output_index: int,
        declared_outputs: list[str],
        result: dict[str, Any],
        result_keys: list[str],
    ) -> Any:
        """Best-effort mapping from a requested alias to a canonical output."""
        if not result_keys:
            return _MISSING_OUTPUT

        # If the builder returns a single value, any declared alias refers to it.
        if len(result_keys) == 1:
            return result[result_keys[0]]

        # When YAML declares one alias per returned field, preserve the builder's
        # output ordering so ``product_name_2`` maps to ``product_name``.
        if len(declared_outputs) == len(result_keys):
            canonical_key = result_keys[output_index]
            return result[canonical_key]

        # Otherwise fall back to prefix matching for aliases like
        # ``product_id_ordered`` -> ``product_id``.
        candidates = [
            key
            for key in result_keys
            if requested_key.startswith(f"{key}_")
        ]
        if len(candidates) == 1:
            return result[candidates[0]]

        return _MISSING_OUTPUT

    # ------------------------------------------------------------------
    # Base state skeleton
    # ------------------------------------------------------------------

    @staticmethod
    def _base_skeleton(task_id: str) -> dict[str, Any]:
        """Return the mutable base state dict with default address, payment, and settings."""
        addresses = [
            Address(
                id="addr_1",
                full_name="Jordan Parker",
                street_address="742 Evergreen Terrace",
                city="Springfield",
                state="IL",
                zip_code="62704",
                country="United States",
                is_default=True,
                phone="217-555-0142",
            ),
            Address(
                id="addr_2",
                full_name="Jordan Parker",
                street_address="1600 Pennsylvania Ave NW",
                city="Washington",
                state="DC",
                zip_code="20500",
                country="United States",
                is_default=False,
                phone="202-555-0198",
            ),
            Address(
                id="addr_3",
                full_name="Alex Parker",
                street_address="350 Fifth Avenue",
                city="New York",
                state="NY",
                zip_code="10118",
                country="United States",
                is_default=False,
                phone="212-555-0175",
            ),
        ]
        payment_methods = [
            PaymentMethod(
                id="pm_1",
                card_type="Visa",
                last_four="4242",
                expiry="12/28",
                holder_name="Jordan Parker",
                is_default=True,
            ),
            PaymentMethod(
                id="pm_2",
                card_type="Mastercard",
                last_four="8888",
                expiry="03/27",
                holder_name="Jordan Parker",
                is_default=False,
            ),
            PaymentMethod(
                id="pm_3",
                card_type="Amex",
                last_four="1234",
                expiry="09/29",
                holder_name="Jordan Parker",
                is_default=False,
            ),
        ]
        return {
            "env_id": "amazon",
            "task_id": task_id,
            "owner_name": "Jordan Parker",
            "owner_email": "jordan.parker@email.com",
            "products": [],
            "cart_items": [],
            "addresses": addresses,
            "payment_methods": payment_methods,
            "orders": [],
            "reviews": [],
            "wishlist": [],
            "recently_viewed": [],
            "search_history": [],
            "returns": [],
            "promo_codes": [],
            "questions": [],
            "gift_cards": [],
            "notifications": [],
            "browsing_history": [],
            "applied_promo_code": None,
            "is_logged_in": True,
            "password_hash": "simulated_hash",
            "id_counters": {"addr": len(addresses), "pm": len(payment_methods)},
            "settings": AmazonSettings(
                id="settings_amazon",
                default_address_id="addr_1",
                default_payment_id="pm_1",
                prime_member=True,
                one_click_enabled=False,
                email_notifications=True,
                language="English",
            ),
        }

    # ------------------------------------------------------------------
    # Pre-seed realistic account state
    # ------------------------------------------------------------------

    @staticmethod
    def _add_initial_account_state(ctx: AmazonSeedContext) -> None:
        """Populate the account with realistic lived-in state.

        Adds past orders, reviews, a return request, notifications,
        wishlist items, browsing history, and search history so the
        environment looks like a real account.
        """
        base = ctx.base
        products = base["products"]
        if len(products) < 12:
            return  # not enough products to seed history

        # Pick a stable subset of products for history seeding.
        history_pool = list(products)
        ctx.rng.shuffle(history_pool)

        # ---- Past orders (6 orders) ----
        # Use list indices for address/payment IDs to avoid tight coupling
        addrs = base["addresses"]
        pms = base["payment_methods"]
        addr_0 = addrs[0].id if len(addrs) > 0 else "addr_1"
        addr_1 = addrs[1].id if len(addrs) > 1 else addr_0
        addr_2 = addrs[2].id if len(addrs) > 2 else addr_0
        pm_0 = pms[0].id if len(pms) > 0 else "pm_1"
        pm_1 = pms[1].id if len(pms) > 1 else pm_0
        pm_2 = pms[2].id if len(pms) > 2 else pm_0

        order_specs = [
            # (days_ago, num_items, status, addr_id, pm_id)
            (90, 2, "delivered", addr_0, pm_0),
            (60, 1, "delivered", addr_0, pm_1),
            (30, 3, "delivered", addr_1, pm_0),
            (14, 1, "shipped", addr_0, pm_0),
            (7, 2, "confirmed", addr_2, pm_2),
            (45, 1, "cancelled", addr_0, pm_1),
        ]

        pool_idx = 0
        created_orders: list[Order] = []
        for spec_idx, (days_ago, num_items, status, addr_id, pm_id) in enumerate(order_specs, 1):
            order_id = f"order_initial_{spec_idx}"
            placed_at = ctx.now - timedelta(days=days_ago)

            items: list[OrderItem] = []
            subtotal = 0.0
            for _ in range(num_items):
                p = history_pool[pool_idx % len(history_pool)]
                pool_idx += 1
                qty = ctx.rng.randint(1, 2)
                items.append(OrderItem(
                    product_id=p.id,
                    product_name=p.name,
                    quantity=qty,
                    unit_price=p.price,
                ))
                subtotal += p.price * qty

            tax = round(subtotal * 0.08, 2)
            shipping = 0.0 if subtotal > 35 else 5.99
            total = round(subtotal + tax + shipping, 2)

            est_delivery = ""
            if status in ("delivered", "shipped", "confirmed"):
                est_dt = placed_at + timedelta(days=ctx.rng.randint(3, 7))
                est_delivery = est_dt.strftime("%B %d, %Y")

            order = Order(
                id=order_id,
                items=items,
                shipping_address_id=addr_id,
                payment_method_id=pm_id,
                subtotal=round(subtotal, 2),
                shipping_cost=shipping,
                tax=tax,
                total=total,
                status=status,
                placed_at=placed_at,
                estimated_delivery=est_delivery,
            )
            created_orders.append(order)
            base["orders"].append(order)

        # ---- Past reviews (4 reviews on delivered-order products) ----
        delivered_orders = [o for o in created_orders if o.status == "delivered"]
        review_data = [
            (5, "Excellent quality!", "Absolutely love this product. Works exactly as described and arrived quickly."),
            (4, "Good value for the price", "Solid product overall. Minor packaging issue but the item itself is great."),
            (3, "Decent but not perfect", "Does the job but the build quality could be better. Okay for the price."),
            (2, "Disappointed", "Product didn't match the description. Returning it."),
        ]

        reviewed_items: list[OrderItem] = []
        review_idx = 0
        for order in delivered_orders:
            for item in order.items:
                if review_idx >= len(review_data):
                    break
                rating, title, body = review_data[review_idx]
                review = Review(
                    id=f"review_initial_{review_idx + 1}",
                    product_id=item.product_id,
                    author_name=base["owner_name"],
                    rating=rating,
                    title=title,
                    body=body,
                    helpful_count=ctx.rng.randint(0, 25),
                    verified_purchase=True,
                    created_at=ctx.now - timedelta(days=ctx.rng.randint(5, 80)),
                )
                base["reviews"].append(review)
                reviewed_items.append(item)
                review_idx += 1

        # ---- Return request (1 on a delivered order) ----
        if delivered_orders and delivered_orders[-1].items:
            ret_order = delivered_orders[-1]
            ret_item = ret_order.items[0]
            return_req = ReturnRequestModel(
                id="return_initial_1",
                order_id=ret_order.id,
                order_item_index=0,
                product_id=ret_item.product_id,
                product_name=ret_item.product_name,
                reason="no_longer_needed",
                status="refund_issued",
                refund_amount=ret_item.unit_price * ret_item.quantity,
                created_at=ctx.now - timedelta(days=20),
                resolution_note="Refund of ${:.2f} issued to original payment method.".format(
                    ret_item.unit_price * ret_item.quantity
                ),
            )
            base["returns"].append(return_req)

        # ---- Notifications (4) ----
        notif_specs = [
            ("delivery", "Your order has been delivered",
             "Your order {} has been delivered to your doorstep.".format(created_orders[0].id if created_orders else ""),
             created_orders[0].id if created_orders else None, 5, True),
            ("return_update", "Your return has been processed",
             "Your return request has been approved and a refund has been issued.",
             "return_initial_1", 18, True),
            ("price_drop", "Price drop on items in your wishlist",
             "Great news! An item on your wishlist has dropped in price. Check it out!",
             None, 3, False),
            ("order_update", "Your order has shipped",
             "Your order {} is on its way! Track your package for delivery updates.".format(
                 created_orders[3].id if len(created_orders) > 3 else ""),
             created_orders[3].id if len(created_orders) > 3 else None, 12, True),
        ]
        for n_idx, (ntype, title, message, related, days_ago, is_read) in enumerate(notif_specs, 1):
            notif = Notification(
                id=f"notif_initial_{n_idx}",
                type=ntype,
                title=title,
                message=message,
                read=is_read,
                created_at=ctx.now - timedelta(days=days_ago),
                related_id=related,
            )
            base["notifications"].append(notif)

        # ---- Wishlist (no pre-population) ----
        # Pre-wishlisting random catalog products contradicts the stated
        # wishlist count in instructions such as amazon_wishlist_to_cart
        # ("add all wishlist items to your cart") and
        # amazon_wishlist_cart_consolidation ("your wishlist has 4 items"):
        # tasks that want a seeded wishlist use the ``wishlist_items`` or
        # ``wishlist_stock_mix`` builders explicitly. We still advance
        # ``pool_idx`` by 4 so downstream browsing-history slicing stays
        # deterministic for existing seeds.
        pool_idx += 4

        # ---- Browsing history / recently viewed (6 products) ----
        browsing_products = history_pool[pool_idx:pool_idx + 6]
        pool_idx += 6
        for b_idx, p in enumerate(browsing_products):
            viewed_at = ctx.now - timedelta(hours=ctx.rng.randint(1, 72))
            base["browsing_history"].append(
                BrowsingHistory(product_id=p.id, viewed_at=viewed_at)
            )
            if p.id not in base["recently_viewed"]:
                base["recently_viewed"].append(p.id)

        # ---- Search history (4 terms) ----
        base["search_history"].extend([
            "wireless earbuds",
            "kitchen utensils",
            "running shoes",
            "desk organizer",
        ])

    # ------------------------------------------------------------------
    # Baseline catalog — ensures every category has products
    # ------------------------------------------------------------------

    # Maximum rating for baseline catalog products.  Featured products
    # with rating >= 4.7 will always win "highest rated" comparisons.
    _CATALOG_MAX_RATING = 4.6

    # Minimum price for baseline catalog products.  Featured products
    # priced below $15 will always win "cheapest" comparisons.
    _CATALOG_MIN_PRICE = 15.0

    @staticmethod
    def _add_baseline_catalog(ctx: AmazonSeedContext, per_category: int = 5) -> None:
        """Load real Amazon products into the catalog.

        Uses scraped product data from ``amazon_real_products.json``.
        Falls back to generated products for categories not in the
        real data file.

        Ratings are capped at ``_CATALOG_MAX_RATING`` (4.6) and prices
        are floored at ``_CATALOG_MIN_PRICE`` ($15) so that featured
        products seeded by builder steps can always be designed to beat
        the catalog on those dimensions.
        """
        max_rating = AmazonSeedRunner._CATALOG_MAX_RATING
        min_price = AmazonSeedRunner._CATALOG_MIN_PRICE

        # Count existing products per category
        existing: dict[str, int] = {}
        for p in ctx.base["products"]:
            existing[p.category] = existing.get(p.category, 0) + 1

        for cat, cat_data in _CATEGORIES.items():
            real_products = _REAL_PRODUCTS.get(cat, [])
            if real_products:
                # Shuffle deterministically and pick products
                shuffled = list(real_products)
                ctx.rng.shuffle(shuffled)
                # Add all real products (or up to 40 per category)
                for rp in shuffled[:40]:
                    name = rp.get("name", "")
                    if not name:
                        continue
                    price = rp.get("price", 0)
                    if price <= 0:
                        price = round(ctx.rng.uniform(min_price, 100), 2)
                    price = max(price, min_price)
                    rating = rp.get("rating", 0)
                    if rating <= 0:
                        rating = round(ctx.rng.uniform(3.5, max_rating), 1)
                    rating = min(rating, max_rating)
                    reviews = rp.get("reviews", 0) or rp.get("review_count", 0)
                    if reviews <= 0:
                        reviews = ctx.rng.randint(100, 5000)
                    # Extract brand from product name (first word or two)
                    brand_parts = name.split()[:2]
                    brand = " ".join(brand_parts) if brand_parts else cat_data["brands"][0]
                    # Some products get a higher list_price (deals).
                    # Discount percentage is capped so featured deals
                    # with larger discounts always win.
                    list_price = round(price * ctx.rng.uniform(1.10, 1.40), 2) if ctx.rng.random() < 0.25 else None
                    real_image = rp.get("image") or None
                    if real_image and (
                        _REAL_PRODUCT_IMAGE_COUNTS.get(real_image, 0) > _MAX_REAL_IMAGE_REUSE
                        or len(_REAL_PRODUCT_IMAGE_CATEGORIES.get(real_image, set())) > 1
                    ):
                        real_image = None
                    prod = ctx.product(
                        name=name[:120],  # Truncate very long names
                        category=cat,
                        brand=brand,
                        price=price,
                        list_price=list_price,
                        rating=rating,
                        review_count=reviews,
                        in_stock=ctx.rng.random() < 0.92,
                        prime_eligible=ctx.rng.random() < 0.75,
                        image_url=real_image,
                    )
                    ctx.base["products"].append(prod)
            else:
                # Fallback: generate products from category templates
                needed = max(per_category, 20)
                for _ in range(needed):
                    brand = ctx.rng.choice(cat_data["brands"])
                    name = ctx.rng.choice(cat_data["names"])
                    lo, hi = cat_data["price_range"]
                    price = round(ctx.rng.uniform(max(lo, min_price), hi), 2)
                    rating = round(ctx.rng.uniform(3.2, max_rating), 1)
                    review_count = ctx.rng.randint(50, 5000)
                    list_price = round(price * ctx.rng.uniform(1.10, 1.40), 2) if ctx.rng.random() < 0.3 else None
                    prod = ctx.product(
                        name=f"{brand} {name}",
                        category=cat,
                        brand=brand,
                        price=price,
                        list_price=list_price,
                        rating=rating,
                        review_count=review_count,
                        in_stock=ctx.rng.random() < 0.9,
                        prime_eligible=ctx.rng.random() < 0.7,
                    )
                    ctx.base["products"].append(prod)

    # ------------------------------------------------------------------
    # Product catalog generation
    # ------------------------------------------------------------------

    @staticmethod
    def _add_product_catalog(ctx: AmazonSeedContext, count: int) -> None:
        """Add *count* products spanning multiple categories to the catalog."""
        categories = list(_CATEGORIES.keys())
        for i in range(count):
            cat = categories[i % len(categories)]
            cat_data = _CATEGORIES[cat]
            brand = ctx.rng.choice(cat_data["brands"])
            name = ctx.rng.choice(cat_data["names"])
            lo, hi = cat_data["price_range"]
            price = round(ctx.rng.uniform(lo, hi), 2)
            rating = round(ctx.rng.uniform(3.0, 5.0), 1)
            review_count = ctx.rng.randint(10, 5000)
            prod = ctx.product(
                name=f"{brand} {name}",
                category=cat,
                brand=brand,
                price=price,
                rating=rating,
                review_count=review_count,
            )
            ctx.base["products"].append(prod)

    # ------------------------------------------------------------------
    # Generic distractors for catalog padding
    # ------------------------------------------------------------------

    @staticmethod
    def _add_generic_distractors(ctx: AmazonSeedContext, count: int) -> None:
        """Add *count* distractor products from random categories.

        Ratings and prices are capped/floored to the same limits as the
        baseline catalog so featured products always dominate comparisons.
        """
        max_rating = AmazonSeedRunner._CATALOG_MAX_RATING
        min_price = AmazonSeedRunner._CATALOG_MIN_PRICE
        categories = list(_CATEGORIES.keys())
        for _ in range(count):
            cat = ctx.rng.choice(categories)
            cat_data = _CATEGORIES[cat]
            brand = ctx.rng.choice(cat_data["brands"])
            name = ctx.rng.choice(cat_data["names"])
            lo, hi = cat_data["price_range"]
            price = round(ctx.rng.uniform(max(lo, min_price), hi), 2)
            rating = round(ctx.rng.uniform(3.0, max_rating), 1)
            review_count = ctx.rng.randint(10, 5000)

            in_stock = ctx.rng.random() < 0.85
            prime_eligible = ctx.rng.random() < 0.6

            prod = ctx.product(
                name=f"{brand} {name}",
                category=cat,
                brand=brand,
                price=price,
                rating=rating,
                review_count=review_count,
                in_stock=in_stock,
                prime_eligible=prime_eligible,
            )
            ctx.base["products"].append(prod)

    # ------------------------------------------------------------------
    # Param / target template resolution
    # ------------------------------------------------------------------

    _TEMPLATE_RE = _TEMPLATE_RE
    _EXACT_REF_RE = _EXACT_REF_RE

    @classmethod
    def _resolve_params(
        cls, params: dict[str, Any], ctx: AmazonSeedContext
    ) -> dict[str, Any]:
        """Recursively resolve ``{actor.key.field}`` and ``{output.key}``."""
        return {k: cls._resolve_value(v, ctx) for k, v in params.items()}

    @classmethod
    def _resolve_value(cls, value: Any, ctx: AmazonSeedContext) -> Any:
        if isinstance(value, str):
            # If the entire string is exactly one reference, return the raw
            # (possibly non-string) value so lists/dicts survive.
            exact = cls._EXACT_REF_RE.match(value)
            if exact:
                return cls._raw_lookup(exact.group(1), exact.group(2), ctx)
            return cls._TEMPLATE_RE.sub(
                lambda m: str(cls._raw_lookup(m.group(1), m.group(2), ctx)),
                value,
            )
        if isinstance(value, list):
            return [cls._resolve_value(v, ctx) for v in value]
        if isinstance(value, dict):
            return {k: cls._resolve_value(v, ctx) for k, v in value.items()}
        return value

    @staticmethod
    def _raw_lookup(kind: str, path: str, ctx: AmazonSeedContext) -> Any:
        """Return the raw (possibly non-string) referenced value."""
        if kind == "actor":
            parts = path.split(".", 1)
            actor = ctx.actors[parts[0]]
            if len(parts) == 1:
                return actor["name"] if isinstance(actor, dict) else actor.name
            field = parts[1]
            return actor[field] if isinstance(actor, dict) else getattr(actor, field)
        # kind == "output"
        parts = path.split(".")
        obj: Any = ctx.outputs
        for part in parts:
            obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
        return obj

    @classmethod
    def _resolve_targets(
        cls, templates: dict[str, str], ctx: AmazonSeedContext
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, tmpl in templates.items():
            resolved[key] = cls._resolve_value(tmpl, ctx)
        return resolved
