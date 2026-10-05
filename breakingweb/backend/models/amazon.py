from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseEntity, BaseEnvState


class ProductVariant(BaseModel):
    name: str
    value: str
    price_modifier: float = 0.0
    in_stock: bool = True

    model_config = ConfigDict(extra="forbid")


class Product(BaseEntity):
    name: str
    brand: str
    category: str
    subcategory: str
    description: str
    price: float
    list_price: float | None = None
    currency: str = "USD"
    rating: float
    review_count: int
    in_stock: bool = True
    stock_quantity: int = 100
    image_url: str
    features: list[str] = Field(default_factory=list)
    variants: list[ProductVariant] = Field(default_factory=list)
    seller: str = "Amazon.com"
    prime_eligible: bool = True
    delivery_estimate: str


class CartItem(BaseEntity):
    product_id: str
    product_name: str
    quantity: int = 1
    unit_price: float
    variant_selections: dict[str, str] = Field(default_factory=dict)
    added_at: datetime


class Address(BaseEntity):
    full_name: str
    street_address: str
    apt_suite: str = ""
    city: str
    state: str
    zip_code: str
    country: str = "United States"
    is_default: bool = False
    phone: str = ""


class PaymentMethod(BaseEntity):
    card_type: str
    last_four: str
    expiry: str
    holder_name: str
    is_default: bool = False


class OrderItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    variant_selections: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class Order(BaseEntity):
    items: list[OrderItem] = Field(default_factory=list)
    shipping_address_id: str
    payment_method_id: str
    subtotal: float
    shipping_cost: float = 0.0
    tax: float
    total: float
    status: str = "pending"
    placed_at: datetime | None = None
    estimated_delivery: str = ""
    promo_code: str | None = None
    discount: float = 0.0


class Review(BaseEntity):
    product_id: str
    author_name: str
    rating: int
    title: str
    body: str
    helpful_count: int = 0
    verified_purchase: bool = True
    created_at: datetime


class ProductAnswer(BaseModel):
    answer: str
    author_name: str
    answered_at: datetime
    helpful_count: int = 0
    is_seller_response: bool = False

    model_config = ConfigDict(extra="forbid")


class ReturnRequest(BaseEntity):
    order_id: str
    order_item_index: int
    product_id: str
    product_name: str
    reason: str
    status: str = "pending"
    refund_amount: float
    created_at: datetime
    resolution_note: str = ""


class PromoCode(BaseEntity):
    code: str
    discount_type: str
    discount_value: float
    min_order_amount: float = 0.0
    max_uses: int = 1
    used_count: int = 0
    valid_until: datetime
    applicable_categories: list[str] = Field(default_factory=list)
    active: bool = True


class ProductQuestion(BaseEntity):
    product_id: str
    question: str
    asker_name: str
    answers: list[ProductAnswer] = Field(default_factory=list)
    asked_at: datetime
    vote_count: int = 0


class GiftCard(BaseEntity):
    code: str
    balance: float
    initial_amount: float
    redeemed: bool = False
    added_at: datetime


class Notification(BaseEntity):
    type: str
    title: str
    message: str
    read: bool = False
    created_at: datetime
    related_id: str | None = None


class BrowsingHistory(BaseModel):
    product_id: str
    viewed_at: datetime

    model_config = ConfigDict(extra="forbid")


class AmazonSettings(BaseEntity):
    default_address_id: str | None = None
    default_payment_id: str | None = None
    prime_member: bool = False
    one_click_enabled: bool = False
    email_notifications: bool = True
    language: str = "English"
    currency: str = "USD"
    two_factor_enabled: bool = False
    order_updates_email: bool = True
    deal_alerts_email: bool = False
    gift_card_balance: float = 0.0


class AmazonState(BaseEnvState):
    DIFF_DIFFABLE_PRIMITIVE_LISTS: ClassVar[tuple[str, ...]] = ("wishlist",)
    DIFF_DIFFABLE_SINGLETONS: ClassVar[tuple[str, ...]] = ("settings",)

    owner_name: str
    owner_email: str
    products: list[Product] = Field(default_factory=list)
    cart_items: list[CartItem] = Field(default_factory=list)
    addresses: list[Address] = Field(default_factory=list)
    payment_methods: list[PaymentMethod] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    wishlist: list[str] = Field(default_factory=list)
    recently_viewed: list[str] = Field(default_factory=list)
    settings: AmazonSettings
    search_history: list[str] = Field(default_factory=list)
    returns: list[ReturnRequest] = Field(default_factory=list)
    promo_codes: list[PromoCode] = Field(default_factory=list)
    questions: list[ProductQuestion] = Field(default_factory=list)
    gift_cards: list[GiftCard] = Field(default_factory=list)
    notifications: list[Notification] = Field(default_factory=list)
    browsing_history: list[BrowsingHistory] = Field(default_factory=list)
    viewed_order_ids: list[str] = Field(default_factory=list)
    applied_promo_code: str | None = None
    is_logged_in: bool = True
    password_hash: str = "simulated_hash"
    id_counters: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def _next_id(self, prefix: str) -> str:
        count = self.id_counters.get(prefix, 0) + 1
        self.id_counters[prefix] = count
        return f"{prefix}_{count}"

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def get_product(self, product_id: str) -> Product | None:
        return next((p for p in self.products if p.id == product_id), None)

    def search_products(
        self,
        query: str,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_rating: float | None = None,
        sort_by: str = "relevance",
    ) -> list[Product]:
        tokens = query.lower().split() if query else []

        results: list[Product] = []
        for product in self.products:
            if category and product.category.lower() != category.lower():
                continue
            if min_price is not None and product.price < min_price:
                continue
            if max_price is not None and product.price > max_price:
                continue
            if min_rating is not None and product.rating < min_rating:
                continue

            if tokens:
                haystacks = " ".join(
                    [
                        product.name.lower(),
                        product.brand.lower(),
                        product.description.lower(),
                        product.category.lower(),
                        product.subcategory.lower(),
                    ]
                )
                if not all(token in haystacks for token in tokens):
                    continue

            results.append(product)

        if sort_by in ("price_low", "price_asc"):
            results.sort(key=lambda p: p.price)
        elif sort_by in ("price_high", "price_desc"):
            results.sort(key=lambda p: p.price, reverse=True)
        elif sort_by == "rating":
            results.sort(key=lambda p: p.rating, reverse=True)
        elif sort_by == "review_count":
            results.sort(key=lambda p: p.review_count, reverse=True)
        elif sort_by == "newest":
            results.sort(
                key=lambda p: int(p.id.rsplit("_", 1)[-1]) if "_" in p.id else 0,
                reverse=True,
            )
        # "relevance" keeps the natural order

        return results

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------

    def get_cart_item(self, item_id: str) -> CartItem | None:
        return next((item for item in self.cart_items if item.id == item_id), None)

    def add_to_cart(
        self,
        product_id: str,
        quantity: int = 1,
        variant_selections: dict[str, str] | None = None,
    ) -> CartItem:
        variant_selections = variant_selections or {}
        product = self.get_product(product_id)
        if product is None:
            raise KeyError(f"Unknown product id: {product_id}")
        if not product.in_stock:
            raise ValueError(f"Product is out of stock: {product_id}")

        # Check if the same product+variants already exists in cart
        for item in self.cart_items:
            if item.product_id == product_id and item.variant_selections == variant_selections:
                item.quantity += quantity
                self.touch()
                return item

        cart_item = CartItem(
            id=self._next_id("cart"),
            product_id=product_id,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
            variant_selections=variant_selections,
            added_at=datetime.now(timezone.utc),
        )
        self.cart_items.append(cart_item)
        self.touch()
        return cart_item

    def update_cart_quantity(self, item_id: str, quantity: int) -> CartItem:
        if quantity <= 0:
            return self.remove_from_cart(item_id)
        item = self.get_cart_item(item_id)
        if item is None:
            raise KeyError(f"Unknown cart item id: {item_id}")
        item.quantity = quantity
        self.touch()
        return item

    def remove_from_cart(self, item_id: str) -> CartItem:
        for index, item in enumerate(self.cart_items):
            if item.id == item_id:
                removed = self.cart_items.pop(index)
                self.touch()
                return removed
        raise KeyError(f"Unknown cart item id: {item_id}")

    def cart_subtotal(self) -> float:
        return sum(item.unit_price * item.quantity for item in self.cart_items)

    def cart_total(self, tax_rate: float = 0.08) -> dict[str, float]:
        subtotal = self.cart_subtotal()
        shipping = 0.0
        if not self.settings.prime_member and subtotal < 25.0 and subtotal > 0:
            shipping = 5.99
        tax = round(subtotal * tax_rate, 2)
        discount = 0.0
        # Apply only the currently applied promo code
        if self.applied_promo_code:
            promo = self.get_promo_code(self.applied_promo_code)
            if promo and promo.active:
                if promo.discount_type == "percentage":
                    discount = round(subtotal * promo.discount_value / 100, 2)
                elif promo.discount_type == "fixed":
                    discount = promo.discount_value
        # Factor in gift card balance
        gift_card_balance = self.settings.gift_card_balance
        total_before_gc = round(subtotal + shipping + tax - discount, 2)
        gc_applied = min(gift_card_balance, max(total_before_gc, 0.0))
        total = round(max(total_before_gc - gc_applied, 0.0), 2)
        return {
            "subtotal": subtotal,
            "shipping": shipping,
            "tax": tax,
            "discount": discount,
            "gift_card_applied": gc_applied,
            "total": total,
        }

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(
        self,
        shipping_address_id: str,
        payment_method_id: str,
        promo_code: str | None = None,
    ) -> Order:
        # Validate address exists
        address = next((a for a in self.addresses if a.id == shipping_address_id), None)
        if address is None:
            raise KeyError(f"Unknown address id: {shipping_address_id}")

        # Validate payment method exists
        payment = next((p for p in self.payment_methods if p.id == payment_method_id), None)
        if payment is None:
            raise KeyError(f"Unknown payment method id: {payment_method_id}")

        if not self.cart_items:
            raise ValueError("Cart is empty")

        totals = self.cart_total()
        applied_promo_code = self.applied_promo_code or promo_code
        order_items = [
            OrderItem(
                product_id=item.product_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                variant_selections=dict(item.variant_selections),
            )
            for item in self.cart_items
        ]

        order = Order(
            id=self._next_id("order"),
            items=order_items,
            shipping_address_id=shipping_address_id,
            payment_method_id=payment_method_id,
            subtotal=totals["subtotal"],
            shipping_cost=totals["shipping"],
            tax=totals["tax"],
            total=totals["total"],
            status="confirmed",
            placed_at=datetime.now(timezone.utc),
            estimated_delivery="3-5 business days",
            promo_code=applied_promo_code,
            discount=totals["discount"],
        )
        if applied_promo_code:
            promo = self.get_promo_code(applied_promo_code)
            if promo is not None:
                promo.used_count += 1
        self.orders.append(order)
        self.cart_items.clear()
        self.applied_promo_code = None
        self.touch()
        return order

    def get_order(self, order_id: str) -> Order | None:
        return next((o for o in self.orders if o.id == order_id), None)

    # ------------------------------------------------------------------
    # Addresses
    # ------------------------------------------------------------------

    def add_address(self, address: Address) -> Address:
        if address.is_default:
            for existing in self.addresses:
                existing.is_default = False
            self.settings.default_address_id = address.id
        self.addresses.append(address)
        self.touch()
        return address

    def update_address(self, address_id: str, **kwargs: Any) -> Address:
        address = next((a for a in self.addresses if a.id == address_id), None)
        if address is None:
            raise KeyError(f"Unknown address id: {address_id}")
        make_default = bool(kwargs.get("is_default"))
        if make_default:
            for other in self.addresses:
                other.is_default = other.id == address_id
            self.settings.default_address_id = address_id
        for key, value in kwargs.items():
            if not hasattr(address, key):
                raise ValueError(f"Invalid address field: {key}")
            setattr(address, key, value)
        if kwargs.get("is_default") is False and self.settings.default_address_id == address_id:
            self.settings.default_address_id = None
        self.touch()
        return address

    def remove_address(self, address_id: str) -> Address:
        for index, address in enumerate(self.addresses):
            if address.id == address_id:
                removed = self.addresses.pop(index)
                self.touch()
                return removed
        raise KeyError(f"Unknown address id: {address_id}")

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
        for index, pm in enumerate(self.payment_methods):
            if pm.id == pm_id:
                removed = self.payment_methods.pop(index)
                self.touch()
                return removed
        raise KeyError(f"Unknown payment method id: {pm_id}")

    # ------------------------------------------------------------------
    # Wishlist
    # ------------------------------------------------------------------

    def add_to_wishlist(self, product_id: str) -> None:
        if product_id not in self.wishlist:
            self.wishlist.append(product_id)
            self.touch()

    def remove_from_wishlist(self, product_id: str) -> None:
        if product_id in self.wishlist:
            self.wishlist.remove(product_id)
            self.touch()

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    def add_review(self, review: Review) -> Review:
        self.reviews.append(review)
        # Update the product review count
        product = self.get_product(review.product_id)
        if product is not None:
            product.review_count += 1
        self.touch()
        return review

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> bool:
        """Simulated login -- always succeeds."""
        self.is_logged_in = True
        self.touch()
        return True

    def logout(self) -> None:
        self.is_logged_in = False
        self.touch()

    # ------------------------------------------------------------------
    # Returns
    # ------------------------------------------------------------------

    def request_return(
        self, order_id: str, order_item_index: int, reason: str
    ) -> ReturnRequest:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"Unknown order id: {order_id}")
        if order.status not in ("confirmed", "delivered"):
            raise ValueError(
                f"Order status must be 'confirmed' or 'delivered' to request return, got '{order.status}'"
            )
        if order_item_index < 0 or order_item_index >= len(order.items):
            raise IndexError(
                f"order_item_index {order_item_index} out of range for order with {len(order.items)} items"
            )
        item = order.items[order_item_index]
        ret = ReturnRequest(
            id=self._next_id("return"),
            order_id=order_id,
            order_item_index=order_item_index,
            product_id=item.product_id,
            product_name=item.product_name,
            reason=reason,
            refund_amount=round(item.unit_price * item.quantity, 2),
            created_at=datetime.now(timezone.utc),
        )
        self.returns.append(ret)
        self.touch()
        return ret

    def get_return(self, return_id: str) -> ReturnRequest | None:
        return next((r for r in self.returns if r.id == return_id), None)

    def update_return_status(
        self, return_id: str, status: str, resolution_note: str = ""
    ) -> ReturnRequest:
        ret = self.get_return(return_id)
        if ret is None:
            raise KeyError(f"Unknown return id: {return_id}")
        ret.status = status
        if resolution_note:
            ret.resolution_note = resolution_note
        self.touch()
        return ret

    # ------------------------------------------------------------------
    # Promo Codes
    # ------------------------------------------------------------------

    def apply_promo_code(self, code: str) -> dict:
        promo = self.get_promo_code(code)
        if promo is None:
            raise KeyError(f"Unknown promo code: {code}")
        if not promo.active:
            raise ValueError("Promo code is not active")
        if promo.used_count >= promo.max_uses:
            raise ValueError("Promo code has been fully used")
        if promo.valid_until < datetime.now(timezone.utc):
            raise ValueError("Promo code has expired")

        subtotal = self.cart_subtotal()
        if subtotal < promo.min_order_amount:
            raise ValueError(
                f"Order subtotal {subtotal} is below minimum {promo.min_order_amount}"
            )

        if promo.discount_type == "percentage":
            discount_amount = round(subtotal * promo.discount_value / 100, 2)
        else:
            discount_amount = promo.discount_value

        self.applied_promo_code = code
        self.touch()
        return {"code": code, "discount_amount": discount_amount}

    def clear_promo_code(self) -> None:
        self.applied_promo_code = None
        self.touch()

    def get_promo_code(self, code: str) -> PromoCode | None:
        return next((p for p in self.promo_codes if p.code == code), None)

    # ------------------------------------------------------------------
    # Q&A
    # ------------------------------------------------------------------

    def ask_question(self, product_id: str, question: str) -> ProductQuestion:
        product = self.get_product(product_id)
        if product is None:
            raise KeyError(f"Unknown product id: {product_id}")
        pq = ProductQuestion(
            id=self._next_id("question"),
            product_id=product_id,
            question=question,
            asker_name=self.owner_name,
            asked_at=datetime.now(timezone.utc),
        )
        self.questions.append(pq)
        self.touch()
        return pq

    def answer_question(
        self, question_id: str, answer: str, is_seller: bool = False
    ) -> ProductQuestion:
        pq = next((q for q in self.questions if q.id == question_id), None)
        if pq is None:
            raise KeyError(f"Unknown question id: {question_id}")
        pa = ProductAnswer(
            answer=answer,
            author_name=self.owner_name,
            answered_at=datetime.now(timezone.utc),
            is_seller_response=is_seller,
        )
        pq.answers.append(pa)
        self.touch()
        return pq

    # ------------------------------------------------------------------
    # Gift Cards
    # ------------------------------------------------------------------

    def add_gift_card(self, code: str, amount: float) -> GiftCard:
        gc = GiftCard(
            id=self._next_id("gc"),
            code=code,
            balance=amount,
            initial_amount=amount,
            added_at=datetime.now(timezone.utc),
        )
        self.gift_cards.append(gc)
        self.touch()
        return gc

    def redeem_gift_card(self, gift_card_id: str) -> GiftCard:
        gc = next((g for g in self.gift_cards if g.id == gift_card_id), None)
        if gc is None:
            raise KeyError(f"Unknown gift card id: {gift_card_id}")
        if gc.redeemed:
            raise ValueError("Gift card has already been redeemed")
        gc.redeemed = True
        self.settings.gift_card_balance += gc.balance
        gc.balance = 0.0
        self.touch()
        return gc

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def add_notification(
        self,
        type: str,
        title: str,
        message: str,
        related_id: str | None = None,
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
        notif = next(
            (n for n in self.notifications if n.id == notification_id), None
        )
        if notif is None:
            raise KeyError(f"Unknown notification id: {notification_id}")
        notif.read = True
        self.touch()
        return notif

    def unread_notification_count(self) -> int:
        return sum(1 for n in self.notifications if not n.read)

    # ------------------------------------------------------------------
    # Order Tracking
    # ------------------------------------------------------------------

    def update_order_status(self, order_id: str, status: str) -> Order:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"Unknown order id: {order_id}")
        order.status = status
        self.touch()
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"Unknown order id: {order_id}")
        if order.status in ("shipped", "delivered", "cancelled"):
            raise ValueError(
                f"Cannot cancel order with status '{order.status}'"
            )
        order.status = "cancelled"
        self.touch()
        return order

    # ------------------------------------------------------------------
    # Browsing
    # ------------------------------------------------------------------

    def add_to_browsing_history(self, product_id: str) -> None:
        self.browsing_history.append(
            BrowsingHistory(
                product_id=product_id,
                viewed_at=datetime.now(timezone.utc),
            )
        )
        # Also update recently_viewed
        if product_id in self.recently_viewed:
            self.recently_viewed.remove(product_id)
        self.recently_viewed.insert(0, product_id)
        self.touch()

    def get_categories(self) -> list[str]:
        return sorted({p.category for p in self.products})

    def get_products_by_category(self, category: str) -> list[Product]:
        return [
            p for p in self.products if p.category.lower() == category.lower()
        ]

    def get_deals(self) -> list[Product]:
        return [
            p
            for p in self.products
            if p.list_price is not None and p.list_price > p.price
        ]

    # ------------------------------------------------------------------
    # Snapshots & summaries
    # ------------------------------------------------------------------

    def state_snapshot(self) -> dict[str, Any]:
        """Capture all mutable state dimensions for collateral-damage detection.

        Called once after seeding to record the baseline.  At evaluation time
        the evaluator diffs the current state against this snapshot and reports
        any unintended mutations as analytics-only collateral metrics.
        """
        product_snap: dict[str, dict[str, Any]] = {}
        for product in self.products:
            product_snap[product.id] = {
                "name": product.name,
                "price": product.price,
                "in_stock": product.in_stock,
                "stock_quantity": product.stock_quantity,
                "rating": product.rating,
                "review_count": product.review_count,
            }

        cart_snap: dict[str, dict[str, Any]] = {}
        for item in self.cart_items:
            cart_snap[item.id] = {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "variant_selections": dict(item.variant_selections),
            }

        address_snap: dict[str, dict[str, Any]] = {}
        for address in self.addresses:
            address_snap[address.id] = {
                "full_name": address.full_name,
                "street_address": address.street_address,
                "apt_suite": address.apt_suite,
                "city": address.city,
                "state": address.state,
                "zip_code": address.zip_code,
                "country": address.country,
                "is_default": address.is_default,
                "phone": address.phone,
            }

        payment_snap: dict[str, dict[str, Any]] = {}
        for pm in self.payment_methods:
            payment_snap[pm.id] = {
                "card_type": pm.card_type,
                "last_four": pm.last_four,
                "expiry": pm.expiry,
                "holder_name": pm.holder_name,
                "is_default": pm.is_default,
            }

        order_snap: dict[str, dict[str, Any]] = {}
        for order in self.orders:
            order_snap[order.id] = {
                "status": order.status,
                "total": order.total,
                "item_count": len(order.items),
            }

        review_snap: dict[str, dict[str, Any]] = {}
        for review in self.reviews:
            review_snap[review.id] = {
                "product_id": review.product_id,
                "rating": review.rating,
                "title": review.title,
                "helpful_count": review.helpful_count,
            }

        return_snap: dict[str, dict[str, Any]] = {}
        for ret in self.returns:
            return_snap[ret.id] = {
                "order_id": ret.order_id,
                "product_id": ret.product_id,
                "reason": ret.reason,
                "status": ret.status,
                "refund_amount": ret.refund_amount,
            }

        promo_snap: dict[str, dict[str, Any]] = {}
        for promo in self.promo_codes:
            promo_snap[promo.id] = {
                "code": promo.code,
                "discount_type": promo.discount_type,
                "discount_value": promo.discount_value,
                "active": promo.active,
                "used_count": promo.used_count,
            }

        question_snap: dict[str, dict[str, Any]] = {}
        for q in self.questions:
            question_snap[q.id] = {
                "product_id": q.product_id,
                "question": q.question,
                "answer_count": len(q.answers),
                "vote_count": q.vote_count,
            }

        gift_card_snap: dict[str, dict[str, Any]] = {}
        for gc in self.gift_cards:
            gift_card_snap[gc.id] = {
                "code": gc.code,
                "balance": gc.balance,
                "initial_amount": gc.initial_amount,
                "redeemed": gc.redeemed,
            }

        notification_snap: dict[str, dict[str, Any]] = {}
        for notif in self.notifications:
            notification_snap[notif.id] = {
                "type": notif.type,
                "title": notif.title,
                "read": notif.read,
                "related_id": notif.related_id,
            }

        settings = self.settings.model_dump(mode="json")
        settings.pop("id", None)

        return {
            "product_ids": sorted(product_snap.keys()),
            "products": product_snap,
            "cart_items": cart_snap,
            "addresses": address_snap,
            "payment_methods": payment_snap,
            "order_count": len(self.orders),
            "orders": order_snap,
            "reviews": review_snap,
            "wishlist": sorted(self.wishlist),
            "recently_viewed": list(self.recently_viewed),
            "search_history": list(self.search_history),
            "returns": return_snap,
            "promo_codes": promo_snap,
            "questions": question_snap,
            "gift_cards": gift_card_snap,
            "notifications": notification_snap,
            "browsing_history": [{"product_id": bh.product_id} for bh in self.browsing_history],
            "applied_promo_code": self.applied_promo_code,
            "viewed_order_ids": list(self.viewed_order_ids) if hasattr(self, "viewed_order_ids") else [],
            "settings": settings,
        }

    def session_summary(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "task_id": self.task_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "counts": {
                "products": len(self.products),
                "cart_items": len(self.cart_items),
                "addresses": len(self.addresses),
                "payment_methods": len(self.payment_methods),
                "orders": len(self.orders),
                "reviews": len(self.reviews),
                "wishlist": len(self.wishlist),
                "recently_viewed": len(self.recently_viewed),
                "search_history": len(self.search_history),
                "returns": len(self.returns),
                "promo_codes": len(self.promo_codes),
                "questions": len(self.questions),
                "gift_cards": len(self.gift_cards),
                "notifications": len(self.notifications),
                "unread_notifications": self.unread_notification_count(),
            },
        }
