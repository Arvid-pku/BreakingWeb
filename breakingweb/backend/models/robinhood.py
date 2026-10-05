from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .base import BaseEntity, BaseEnvState, diff_dict_of_dicts, utc_now


# ---------------------------------------------------------------------------
# 1. HistoricalPrice
# ---------------------------------------------------------------------------

class HistoricalPrice(BaseModel):
    date: date
    close: Decimal

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 2. TaxLot
# ---------------------------------------------------------------------------

class TaxLot(BaseModel):
    shares: Decimal
    cost_per_share: Decimal
    acquired_date: date

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 3. Position
# ---------------------------------------------------------------------------

class Position(BaseEntity):
    symbol: str
    name: str
    asset_type: Literal["stock", "etf", "crypto", "option"]
    quantity: Decimal
    avg_cost_basis: Decimal
    current_price: Decimal
    day_change_pct: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    lots: list[TaxLot] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Order
# ---------------------------------------------------------------------------

class Order(BaseEntity):
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"]
    quantity: Decimal
    filled_quantity: Decimal
    filled_price: Decimal | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    trail_amount: Decimal | None = None
    trail_pct: Decimal | None = None
    time_in_force: Literal["gfd", "gtc", "ioc", "opg"] = "gfd"
    status: Literal["pending", "partially_filled", "filled", "cancelled", "rejected"]
    extended_hours: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    filled_at: datetime | None = None
    filled_tick: int | None = None
    cancelled_at: datetime | None = None


# ---------------------------------------------------------------------------
# 5. Stock
# ---------------------------------------------------------------------------

class Stock(BaseModel):
    symbol: str
    name: str
    asset_type: Literal["stock", "etf"]
    price: Decimal
    previous_close: Decimal
    day_change: Decimal
    day_change_pct: Decimal
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    volume: int
    avg_volume: int
    market_cap: Decimal | None = None
    pe_ratio: Decimal | None = None
    eps: Decimal | None = None
    dividend_yield: Decimal | None = None
    fifty_two_week_high: Decimal
    fifty_two_week_low: Decimal
    sector: str
    industry: str
    about: str
    historical_prices: list[HistoricalPrice] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 6. Greeks
# ---------------------------------------------------------------------------

class Greeks(BaseModel):
    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 7. OptionsContract
# ---------------------------------------------------------------------------

class OptionsContract(BaseModel):
    contract_id: str
    underlying: str
    option_type: Literal["call", "put"]
    strike: Decimal
    expiration: date
    bid: Decimal
    ask: Decimal
    last_price: Decimal
    volume: int
    open_interest: int
    implied_volatility: Decimal
    greeks: Greeks = Field(default_factory=Greeks)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 8. OptionsPosition
# ---------------------------------------------------------------------------

class OptionsPosition(BaseEntity):
    contract_id: str
    underlying_symbol: str
    position_side: Literal["long", "short"] = "long"
    option_type: Literal["call", "put"]
    strike_price: Decimal
    expiration_date: date
    quantity: int
    avg_cost: Decimal
    current_premium: Decimal
    greeks: Greeks = Field(default_factory=Greeks)
    status: Literal["open", "closed", "exercised", "expired"] = "open"


# ---------------------------------------------------------------------------
# 9. OptionsLeg
# ---------------------------------------------------------------------------

class OptionsLeg(BaseModel):
    underlying_symbol: str | None = None
    side: Literal["buy", "sell"]
    option_type: Literal["call", "put"]
    strike: Decimal
    expiration: date
    quantity: int
    premium: Decimal

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 10. OptionsOrder
# ---------------------------------------------------------------------------

class OptionsOrder(BaseEntity):
    strategy: Literal[
        "single", "vertical", "iron_condor", "straddle", "strangle",
        "covered_call", "protective_put",
    ]
    legs: list[OptionsLeg] = Field(default_factory=list)
    status: Literal["pending", "filled", "cancelled", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)
    filled_at: datetime | None = None


# ---------------------------------------------------------------------------
# 11. Watchlist
# ---------------------------------------------------------------------------

class Watchlist(BaseEntity):
    name: str
    symbols: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# 12. Transfer
# ---------------------------------------------------------------------------

class Transfer(BaseEntity):
    direction: Literal["deposit", "withdrawal"]
    amount: Decimal
    status: Literal["pending", "completed", "failed", "reversed"] = "pending"
    bank_account_id: str
    initiated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    expected_date: date | None = None


# ---------------------------------------------------------------------------
# 13. LinkedBank
# ---------------------------------------------------------------------------

class LinkedBank(BaseEntity):
    bank_name: str
    account_type: Literal["checking", "savings"]
    last_four: str
    status: Literal["verified", "pending"] = "verified"
    is_default: bool = False


# ---------------------------------------------------------------------------
# 14. RecurringExecution
# ---------------------------------------------------------------------------

class RecurringExecution(BaseModel):
    date: date
    amount: Decimal
    shares_bought: Decimal
    price: Decimal

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 15. RecurringInvestment
# ---------------------------------------------------------------------------

class RecurringInvestment(BaseEntity):
    symbol: str
    amount: Decimal
    frequency: Literal["daily", "weekly", "biweekly", "monthly"]
    next_execution_date: date
    status: Literal["active", "paused"] = "active"
    history: list[RecurringExecution] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 16. Transaction
# ---------------------------------------------------------------------------

class Transaction(BaseEntity):
    type: Literal[
        "buy", "sell", "dividend", "interest", "deposit", "withdrawal",
        "split", "merger", "fee", "referral_bonus", "option_exercise",
        "option_assignment", "option_expiration",
    ]
    symbol: str | None = None
    quantity: Decimal | None = None
    amount: Decimal
    description: str
    timestamp: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# 17. RealizedGainLoss
# ---------------------------------------------------------------------------

class RealizedGainLoss(BaseModel):
    symbol: str
    buy_date: date
    sell_date: date
    proceeds: Decimal
    cost_basis: Decimal
    gain_loss: Decimal
    wash_sale: bool = False
    holding_period: Literal["short", "long"]

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 18. TaxDocument
# ---------------------------------------------------------------------------

class TaxDocument(BaseEntity):
    type: Literal["1099_B", "1099_DIV", "1099_INT", "1099_CONSOLIDATED"]
    tax_year: int
    available_date: date
    realized_gains: list[RealizedGainLoss] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 19. PriceAlert
# ---------------------------------------------------------------------------

class PriceAlert(BaseEntity):
    symbol: str
    condition: Literal["above", "below"]
    target_price: Decimal
    status: Literal["active", "triggered"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    triggered_at: datetime | None = None

    @property
    def triggered(self) -> bool:
        return self.status == "triggered"


# ---------------------------------------------------------------------------
# 20. Notification
# ---------------------------------------------------------------------------

class Notification(BaseEntity):
    type: Literal[
        "order_fill", "price_alert", "dividend", "earnings",
        "transfer_complete", "security_alert", "recurring_investment",
        "tax_document", "margin_call", "corporate_action",
    ]
    title: str
    message: str
    timestamp: datetime = Field(default_factory=utc_now)
    is_read: bool = False
    action_url: str | None = None


# ---------------------------------------------------------------------------
# 21. EarningsEvent
# ---------------------------------------------------------------------------

class EarningsEvent(BaseModel):
    symbol: str
    date: date
    time: Literal["before_market", "after_market"]
    eps_estimate: Decimal | None = None
    eps_actual: Decimal | None = None
    revenue_estimate: Decimal | None = None
    revenue_actual: Decimal | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 22. DividendEntry
# ---------------------------------------------------------------------------

class DividendEntry(BaseModel):
    symbol: str
    ex_date: date
    pay_date: date
    amount_per_share: Decimal
    estimated_total: Decimal
    status: Literal["upcoming", "paid"]

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 23. AccountSettings
# ---------------------------------------------------------------------------

class AccountSettings(BaseEntity):
    display_theme: Literal["light", "dark"] = "light"
    default_order_type: Literal["market", "limit"] = "market"
    reinvest_dividends: bool = True
    extended_hours_enabled: bool = False
    biometric_login: bool = False
    two_factor_method: Literal["sms", "authenticator", "none"] = "none"
    notification_prefs: dict[str, bool] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 24. SecurityEntry
# ---------------------------------------------------------------------------

class SecurityEntry(BaseModel):
    event: Literal["login", "password_change", "2fa_change", "device_added"]
    device: str
    ip_address: str
    location: str
    timestamp: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 25. Referral
# ---------------------------------------------------------------------------

class Referral(BaseModel):
    referred_name: str
    status: Literal["pending", "completed"]
    reward_stock: str
    reward_value: Decimal
    date: date

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 26. RobinhoodState
# ---------------------------------------------------------------------------

class RobinhoodState(BaseEnvState):
    DIFF_DIFFABLE_SINGLETONS: ClassVar[tuple[str, ...]] = ("settings",)

    # Account info
    owner_name: str
    owner_email: str
    account_type: Literal["individual", "margin"] = "individual"
    cash_balance: Decimal = Decimal("0")
    buying_power: Decimal = Decimal("0")
    portfolio_value: Decimal = Decimal("0")
    instant_deposits_limit: Decimal = Decimal("1000")
    margin_maintenance: Decimal = Decimal("0")
    gold_subscription: bool = False
    day_trade_count: int = 0
    account_created_at: datetime = Field(default_factory=utc_now)

    # Collections
    positions: list[Position] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    options_positions: list[OptionsPosition] = Field(default_factory=list)
    options_orders: list[OptionsOrder] = Field(default_factory=list)
    stocks: list[Stock] = Field(default_factory=list)
    options_chains: dict[str, list[OptionsContract]] = Field(default_factory=dict)
    watchlists: list[Watchlist] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    transfers: list[Transfer] = Field(default_factory=list)
    linked_banks: list[LinkedBank] = Field(default_factory=list)
    recurring_investments: list[RecurringInvestment] = Field(default_factory=list)
    tax_documents: list[TaxDocument] = Field(default_factory=list)
    price_alerts: list[PriceAlert] = Field(default_factory=list)
    notifications: list[Notification] = Field(default_factory=list)
    earnings_events: list[EarningsEvent] = Field(default_factory=list)
    dividend_schedule: list[DividendEntry] = Field(default_factory=list)
    settings: AccountSettings
    security_log: list[SecurityEntry] = Field(default_factory=list)
    referral_history: list[Referral] = Field(default_factory=list)

    # Monotonic counter for ID generation (survives deletions)
    _next_id: int = PrivateAttr(default=1)
    _price_engine: Any = PrivateAttr(default=None)
    _cost_basis_snapshots: dict[str, Decimal] = PrivateAttr(default_factory=dict)
    _initial_quantities: dict[str, Decimal] = PrivateAttr(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        """Set the monotonic counter past any IDs already present from seed data."""
        max_id = 0
        for collection in (
            self.positions, self.orders, self.options_orders, self.watchlists,
            self.transactions, self.transfers, self.linked_banks,
            self.recurring_investments, self.price_alerts, self.notifications,
        ):
            for item in collection:
                if hasattr(item, "id") and isinstance(item.id, str) and "_" in item.id:
                    try:
                        max_id = max(max_id, int(item.id.rsplit("_", 1)[1]))
                    except (ValueError, IndexError):
                        pass
        self._next_id = max_id + 1
        self._cost_basis_snapshots = {
            position.symbol: position.avg_cost_basis
            for position in self.positions
            if position.quantity > Decimal("0")
        }
        self._initial_quantities = {
            position.symbol: position.quantity
            for position in self.positions
            if position.quantity > Decimal("0")
        }

    def _gen_id(self, prefix: str) -> str:
        """Generate a unique ID with the given prefix using a monotonic counter."""
        id_val = f"{prefix}_{self._next_id}"
        self._next_id += 1
        return id_val

    def tick(self) -> list[str]:
        """Advance the price engine based on wall-clock time. Returns event list.

        Steps through ticks individually when pending orders or active alerts
        exist so that ``cascade_update`` can detect fills / triggers at
        intermediate prices (instead of jumping to the final tick and missing
        keyframe-crossing events).
        """
        if self._price_engine is None:
            return []
        from breakingweb.backend.price_engine import cascade_update

        import time as _time

        eng = self._price_engine
        now = _time.monotonic()
        elapsed = now - eng.last_tick_time
        num_ticks = int(elapsed / eng.config.tick_interval_seconds)
        if num_ticks <= 0:
            return []
        eng.last_tick_time += num_ticks * eng.config.tick_interval_seconds

        has_triggers = (
            any(o.status == "pending" for o in self.orders)
            or any(a.status == "active" for a in self.price_alerts)
        )

        if has_triggers:
            # Step one tick at a time so fills/alerts fire at intermediate prices
            all_events: list[str] = []
            for _ in range(num_ticks):
                new_prices = eng.advance(1)
                if new_prices:
                    all_events.extend(cascade_update(self, new_prices, eng))
            return all_events
        else:
            new_prices = eng.advance(num_ticks)
            if not new_prices:
                return []
            return cascade_update(self, new_prices, eng)

    # ---- Query methods ----

    def get_position(self, symbol: str) -> Position | None:
        return next((p for p in self.positions if p.symbol == symbol), None)

    def get_stock(self, symbol: str) -> Stock | None:
        return next((s for s in self.stocks if s.symbol == symbol), None)

    def get_order(self, order_id: str) -> Order | None:
        return next((o for o in self.orders if o.id == order_id), None)

    def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        return next((w for w in self.watchlists if w.id == watchlist_id), None)

    def get_bank(self, bank_id: str) -> LinkedBank | None:
        return next((b for b in self.linked_banks if b.id == bank_id), None)

    def default_bank(self) -> LinkedBank | None:
        return next((b for b in self.linked_banks if b.is_default), None)

    @property
    def pending_orders(self) -> list[Order]:
        return [o for o in self.orders if o.status == "pending"]

    @property
    def filled_orders(self) -> list[Order]:
        return [o for o in self.orders if o.status == "filled"]

    def unread_notifications(self) -> list[Notification]:
        return [n for n in self.notifications if not n.is_read]

    def notifications_of_type(self, notification_type: str) -> list[Notification]:
        return [notification for notification in self.notifications if notification.type == notification_type]

    def search_stocks(self, query: str) -> list[Stock]:
        q = query.lower()
        candidates = [
            s for s in self.stocks
            if q in s.symbol.lower() or q in s.name.lower()
        ]
        def _rank(s: Stock) -> int:
            sym = s.symbol.lower()
            if sym == q:
                return 0
            if sym.startswith(q):
                return 1
            if q in sym:
                return 2
            return 3
        return sorted(candidates, key=_rank)

    def watchlist_named(self, name: str) -> Watchlist | None:
        return next((w for w in self.watchlists if w.name == name), None)

    def watchlist_symbols(self, name: str) -> set[str]:
        watchlist = self.watchlist_named(name)
        if watchlist is None:
            return set()
        return set(watchlist.symbols)

    def bank_named(self, name: str) -> LinkedBank | None:
        return next((bank for bank in self.linked_banks if bank.bank_name == name), None)

    def transfers_for_bank(
        self,
        bank_name: str,
        *,
        direction: Literal["deposit", "withdrawal"] | None = None,
        status: Literal["pending", "completed", "failed", "reversed"] | None = None,
    ) -> list[Transfer]:
        bank = self.bank_named(bank_name)
        if bank is None:
            return []
        return [
            transfer
            for transfer in self.transfers
            if transfer.bank_account_id == bank.id
            and (direction is None or transfer.direction == direction)
            and (status is None or transfer.status == status)
        ]

    def active_recurring_investments(self, symbol: str | None = None) -> list[RecurringInvestment]:
        return [
            investment
            for investment in self.recurring_investments
            if investment.status == "active" and (symbol is None or investment.symbol == symbol)
        ]

    def overdue_recurring_investments(self) -> list[RecurringInvestment]:
        anchor = self.anchor_date()
        return [
            investment
            for investment in self.active_recurring_investments()
            if investment.next_execution_date < anchor
        ]

    def duplicate_active_recurring_symbols(self) -> list[str]:
        counts: dict[str, int] = {}
        for investment in self.active_recurring_investments():
            counts[investment.symbol] = counts.get(investment.symbol, 0) + 1
        return sorted(symbol for symbol, count in counts.items() if count > 1)

    def recurring_total_amount(
        self,
        symbol: str,
        *,
        frequency: Literal["daily", "weekly", "biweekly", "monthly"] | None = None,
        status: Literal["active", "paused"] | None = "active",
    ) -> Decimal:
        return sum(
            (
                investment.amount
                for investment in self.recurring_investments
                if investment.symbol == symbol
                and (frequency is None or investment.frequency == frequency)
                and (status is None or investment.status == status)
            ),
            Decimal("0"),
        )

    def position_value(self, symbol: str) -> Decimal:
        position = self.get_position(symbol)
        if position is None:
            return Decimal("0")
        return position.current_price * position.quantity

    def total_position_value(self) -> Decimal:
        return sum((self.position_value(p.symbol) for p in self.positions), Decimal("0"))

    def owned_symbols(self) -> set[str]:
        return {position.symbol for position in self.positions}

    def net_transaction_quantity(self, symbol: str) -> Decimal:
        total = Decimal("0")
        for txn in self.transactions:
            if txn.symbol != symbol or txn.quantity is None:
                continue
            if txn.type == "buy":
                total += txn.quantity
            elif txn.type == "sell":
                total -= txn.quantity
        return total

    def total_position_cost_basis(self, symbol: str) -> Decimal:
        position = self.get_position(symbol)
        if position is None:
            return Decimal("0")
        return sum((lot.shares * lot.cost_per_share for lot in position.lots), Decimal("0"))

    def total_purchase_cost_basis(self, symbol: str) -> Decimal:
        return sum(
            (txn.amount for txn in self.transactions if txn.symbol == symbol and txn.type == "buy"),
            Decimal("0"),
        )

    def sector_value(self, sector: str) -> Decimal:
        return sum(
            (self.position_value(p.symbol) for p in self.positions if self.get_stock(p.symbol) and self.get_stock(p.symbol).sector == sector),
            Decimal("0"),
        )

    def sector_pct(self, sector: str) -> Decimal:
        total = self.total_position_value()
        if total == Decimal("0"):
            return Decimal("0")
        return (self.sector_value(sector) / total) * Decimal("100")

    def highest_value_symbol_in_sector(self, sector: str) -> str | None:
        candidates = [
            position for position in self.positions
            if self.get_stock(position.symbol) and self.get_stock(position.symbol).sector == sector
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda position: self.position_value(position.symbol)).symbol

    def concentrated_symbols(self, threshold_pct: float = 25.0) -> list[str]:
        total = self.total_position_value()
        if total == Decimal("0"):
            return []
        return sorted([
            position.symbol
            for position in self.positions
            if (self.position_value(position.symbol) / total) * Decimal("100") > Decimal(str(threshold_pct))
        ])

    def best_position_symbol(self) -> str | None:
        if not self.positions:
            return None
        return max(self.positions, key=lambda p: p.total_return_pct).symbol

    def worst_position_symbol(self) -> str | None:
        if not self.positions:
            return None
        return min(self.positions, key=lambda p: p.total_return_pct).symbol

    def smallest_return_impact_symbol(self) -> str | None:
        if not self.positions:
            return None
        return min(self.positions, key=lambda position: abs(position.total_return)).symbol

    def position_symbols_at_or_above_shares(self, minimum_shares: Decimal) -> list[str]:
        return sorted([
            position.symbol
            for position in self.positions
            if position.quantity >= minimum_shares
        ])

    def highest_yield_symbol(self, symbols: list[str]) -> str | None:
        candidates = [self.get_stock(symbol) for symbol in symbols]
        candidates = [stock for stock in candidates if stock and stock.dividend_yield is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda stock: stock.dividend_yield).symbol

    def highest_yield_symbol_from_watchlist(self, watchlist_name: str) -> str | None:
        watchlist = self.watchlist_named(watchlist_name)
        if watchlist is None:
            return None
        return self.highest_yield_symbol(watchlist.symbols)

    def top_yield_symbols(self, symbols: list[str], count: int) -> list[str]:
        candidates = [self.get_stock(symbol) for symbol in symbols]
        candidates = [stock for stock in candidates if stock and stock.dividend_yield is not None]
        ranked = sorted(candidates, key=lambda stock: stock.dividend_yield, reverse=True)
        return [stock.symbol for stock in ranked[:count]]

    def top_yield_symbols_from_watchlist(self, watchlist_name: str, count: int) -> list[str]:
        watchlist = self.watchlist_named(watchlist_name)
        if watchlist is None:
            return []
        return self.top_yield_symbols(watchlist.symbols, count)

    def yield_on_cost(self, symbol: str) -> Decimal:
        cost_basis = self.total_position_cost_basis(symbol)
        if cost_basis == Decimal("0"):
            return Decimal("0")
        return (self.annual_dividend_income(symbol) / cost_basis) * Decimal("100")

    def highest_yield_on_cost_symbol(self) -> str | None:
        candidates = [
            position.symbol
            for position in self.positions
            if self.total_position_cost_basis(position.symbol) > Decimal("0")
        ]
        if not candidates:
            return None
        return max(candidates, key=self.yield_on_cost)

    def annual_dividend_income(self, symbol: str | None = None) -> Decimal:
        entries = [
            entry for entry in self.dividend_schedule
            if entry.status == "upcoming" and (symbol is None or entry.symbol == symbol)
        ]
        return sum((entry.estimated_total for entry in entries), Decimal("0"))

    def estimated_annual_dividend_income_for_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        stock = self.get_stock(symbol)
        if stock is None or stock.dividend_yield is None or quantity <= Decimal("0"):
            return Decimal("0")
        return quantity * stock.price * stock.dividend_yield / Decimal("100")

    def current_annual_dividend_income_from_positions(self) -> Decimal:
        return sum(
            (self.estimated_annual_dividend_income_for_quantity(position.symbol, position.quantity) for position in self.positions),
            Decimal("0"),
        )

    def projected_quantities_after_orders(self) -> dict[str, Decimal]:
        projected = {position.symbol: position.quantity for position in self.positions}
        for order in self.orders:
            if order.status == "pending":
                delta = order.quantity if order.side == "buy" else -order.quantity
            elif order.status == "partially_filled":
                remaining = max(order.quantity - order.filled_quantity, Decimal("0"))
                if remaining == Decimal("0"):
                    continue
                delta = remaining if order.side == "buy" else -remaining
            elif order.status == "filled":
                # Filled orders already affected positions, but we need to
                # account for them when comparing against the pre-order
                # snapshot stored in _cost_basis_snapshots.  Skip here since
                # positions already reflect the fill.
                continue
            else:
                continue
            projected[order.symbol] = projected.get(order.symbol, Decimal("0")) + delta
        return {symbol: quantity for symbol, quantity in projected.items() if quantity > Decimal("0")}

    def projected_quantity_after_orders(self, symbol: str) -> Decimal:
        return self.projected_quantities_after_orders().get(symbol, Decimal("0"))

    def projected_position_value_after_orders(self, symbol: str) -> Decimal:
        stock = self.get_stock(symbol)
        if stock is None:
            return Decimal("0")
        return self.projected_quantity_after_orders(symbol) * stock.price

    def current_allocation_pct(self, symbol: str) -> Decimal:
        total = self.total_position_value()
        if total == Decimal("0"):
            return Decimal("0")
        return (self.position_value(symbol) / total) * Decimal("100")

    def allocation_error_vs_targets(self, targets: dict[str, Decimal | int | float]) -> Decimal:
        return sum(
            (
                abs(self.current_allocation_pct(symbol) - Decimal(str(target_pct)))
                for symbol, target_pct in targets.items()
            ),
            Decimal("0"),
        )

    def projected_total_position_value_after_orders(self) -> Decimal:
        return sum(
            (self.projected_position_value_after_orders(symbol) for symbol in self.projected_quantities_after_orders()),
            Decimal("0"),
        )

    def projected_allocation_pct_after_orders(self, symbol: str) -> Decimal:
        total = self.projected_total_position_value_after_orders()
        if total == Decimal("0"):
            return Decimal("0")
        return (self.projected_position_value_after_orders(symbol) / total) * Decimal("100")

    def initial_quantity(self, symbol: str) -> Decimal:
        """Return the quantity of *symbol* snapshotted at session creation."""
        return self._initial_quantities.get(symbol, Decimal("0"))

    def allocation_error_vs_targets_initial(self, targets: dict[str, Decimal | int | float]) -> Decimal:
        """Allocation error using the position quantities snapshotted at session start."""
        initial_values: dict[str, Decimal] = {}
        for symbol, qty in self._initial_quantities.items():
            stock = self.get_stock(symbol)
            if stock:
                initial_values[symbol] = stock.price * qty
        total = sum(initial_values.values(), Decimal("0"))
        if total == Decimal("0"):
            return Decimal("999")
        return sum(
            (
                abs((initial_values.get(symbol, Decimal("0")) / total) * Decimal("100") - Decimal(str(target_pct)))
                for symbol, target_pct in targets.items()
            ),
            Decimal("0"),
        )

    def allocation_error_vs_targets_after_orders(self, targets: dict[str, Decimal | int | float]) -> Decimal:
        return sum(
            (
                abs(self.projected_allocation_pct_after_orders(symbol) - Decimal(str(target_pct)))
                for symbol, target_pct in targets.items()
            ),
            Decimal("0"),
        )

    def projected_annual_dividend_income_after_orders(self) -> Decimal:
        return sum(
            (self.estimated_annual_dividend_income_for_quantity(symbol, quantity) for symbol, quantity in self.projected_quantities_after_orders().items()),
            Decimal("0"),
        )

    def projected_annual_dividend_income_change_from_orders(self) -> Decimal:
        return self.projected_annual_dividend_income_after_orders() - self.current_annual_dividend_income_from_positions()

    def lowest_dividend_income_symbol(self) -> str | None:
        candidates = [
            position.symbol
            for position in self.positions
            if self.annual_dividend_income(position.symbol) > Decimal("0")
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda symbol: self.annual_dividend_income(symbol))

    def positions_below_dividend_yield(self, threshold_pct: Decimal) -> list[str]:
        result: list[str] = []
        for position in self.positions:
            stock = self.get_stock(position.symbol)
            if stock is None or stock.dividend_yield is None:
                continue
            if stock.dividend_yield < threshold_pct:
                result.append(position.symbol)
        return sorted(set(result))

    def symbols_meeting_screen(
        self,
        symbols: list[str],
        *,
        pe_max: Decimal,
        dividend_yield_min: Decimal,
        within_high_pct: Decimal,
    ) -> list[str]:
        passing: list[str] = []
        for symbol in symbols:
            stock = self.get_stock(symbol)
            if stock is None or stock.pe_ratio is None or stock.dividend_yield is None:
                continue
            price_ratio = (stock.price / stock.fifty_two_week_high) * Decimal("100") if stock.fifty_two_week_high else Decimal("0")
            if (
                stock.pe_ratio < pe_max
                and stock.dividend_yield > dividend_yield_min
                and price_ratio >= (Decimal("100") - within_high_pct)
            ):
                passing.append(symbol)
        return sorted(set(passing))

    def screening_pass_symbols(
        self,
        watchlist_name: str,
        *,
        pe_max: Decimal,
        dividend_yield_min: Decimal,
        within_high_pct: Decimal,
    ) -> list[str]:
        watchlist = self.watchlist_named(watchlist_name)
        if watchlist is None:
            return []
        return self.symbols_meeting_screen(
            watchlist.symbols,
            pe_max=pe_max,
            dividend_yield_min=dividend_yield_min,
            within_high_pct=within_high_pct,
        )

    def symbols_with_earnings_within(self, days: int) -> list[str]:
        if days < 0:
            return []
        from breakingweb.backend.seeders.robinhood import derive_anchor_time

        anchor = derive_anchor_time(self.seed).date() if self.seed is not None else utc_now().date()
        return sorted({
            event.symbol
            for event in self.earnings_events
            if 0 <= (event.date - anchor).days <= days
        })

    def portfolio_symbols_with_earnings_within(self, days: int) -> list[str]:
        return sorted(set(self.symbols_with_earnings_within(days)).intersection(self.owned_symbols()))

    def recurring_average_execution_price(self, ri_id: str) -> Decimal:
        investment = next((ri for ri in self.recurring_investments if ri.id == ri_id), None)
        if investment is None or not investment.history:
            return Decimal("0")
        total_amount = sum((execution.amount for execution in investment.history), Decimal("0"))
        total_shares = sum((execution.shares_bought for execution in investment.history), Decimal("0"))
        if total_shares == Decimal("0"):
            return Decimal("0")
        return total_amount / total_shares

    def recurring_ids_overpaying(self, threshold_pct: Decimal) -> list[str]:
        risky_ids: list[str] = []
        for investment in self.recurring_investments:
            stock = self.get_stock(investment.symbol)
            if stock is None or not investment.history:
                continue
            if self.recurring_average_execution_price(investment.id) > stock.price * (Decimal("1") + threshold_pct / Decimal("100")):
                risky_ids.append(investment.id)
        return sorted(risky_ids)

    def recurring_ids_with_earnings_within(self, days: int) -> list[str]:
        risky_symbols = set(self.symbols_with_earnings_within(days))
        return sorted([
            investment.id
            for investment in self.recurring_investments
            if investment.symbol in risky_symbols
        ])

    def recent_purchase_symbols(self, days: int) -> set[str]:
        if not self.transactions:
            return set()
        from breakingweb.backend.seeders.robinhood import derive_anchor_time

        anchor = derive_anchor_time(self.seed) if self.seed is not None else max(txn.timestamp for txn in self.transactions)
        cutoff = anchor.date().toordinal() - days
        return {
            txn.symbol
            for txn in self.transactions
            if txn.type == "buy" and txn.symbol and txn.timestamp.date().toordinal() >= cutoff
        }

    def wash_sale_risk_symbols(self, days: int = 30) -> set[str]:
        return self.recent_purchase_symbols(days)

    def pending_transfers_older_than(self, days: int) -> list[Transfer]:
        from breakingweb.backend.seeders.robinhood import derive_anchor_time

        if not self.transfers:
            return []
        anchor = derive_anchor_time(self.seed) if self.seed is not None else max(xfer.initiated_at for xfer in self.transfers)
        cutoff = anchor.date().toordinal() - days
        return [
            xfer
            for xfer in self.transfers
            if xfer.status == "pending" and xfer.initiated_at.date().toordinal() <= cutoff
        ]

    def stale_alert_symbols(self) -> set[str]:
        owned = {position.symbol for position in self.positions}
        return {alert.symbol for alert in self.price_alerts if alert.symbol not in owned}

    def out_of_country_logins(self) -> list[SecurityEntry]:
        suspicious_markers = ("russia", "nigeria", "unknown vpn")
        return [
            entry
            for entry in self.security_log
            if any(marker in entry.location.lower() for marker in suspicious_markers)
        ]

    def pending_limit_buy_orders_more_than_pct_below_market(self, threshold_pct: Decimal) -> list[Order]:
        orders: list[Order] = []
        multiplier = Decimal("1") - (threshold_pct / Decimal("100"))
        for order in self.orders:
            if order.status != "pending" or order.side != "buy" or order.order_type != "limit" or order.limit_price is None:
                continue
            stock = self.get_stock(order.symbol)
            if stock is None:
                continue
            if order.limit_price < stock.price * multiplier:
                orders.append(order)
        return orders

    def day_change_pct_at_tick(self, symbol: str, tick: int) -> Decimal:
        """Return the day_change_pct for a symbol at a specific price engine tick."""
        if self._price_engine is None:
            # No live prices — fall back to current static value
            stock = self.get_stock(symbol)
            return stock.day_change_pct if stock else Decimal("0")
        price = self._price_engine.price_at_tick(symbol, tick)
        stock = self.get_stock(symbol)
        if stock is None or stock.previous_close == 0:
            return Decimal("0")
        return Decimal(str(round(float((price - stock.previous_close) / stock.previous_close * 100), 2)))

    def pct_gap_at_tick(self, tick: int, sym_a: str, sym_b: str) -> Decimal:
        """Return day_change_pct(sym_a) - day_change_pct(sym_b) at a specific tick."""
        return self.day_change_pct_at_tick(sym_a, tick) - self.day_change_pct_at_tick(sym_b, tick)

    def total_transferred(self, direction: Literal["deposit", "withdrawal"]) -> Decimal:
        return sum((xfer.amount for xfer in self.transfers if xfer.direction == direction), Decimal("0"))

    def total_fees_paid(self, days: int | None = None) -> Decimal:
        fee_txns = [txn for txn in self.transactions if txn.type == "fee"]
        if days is not None and fee_txns:
            anchor = max(txn.timestamp for txn in fee_txns)
            cutoff = anchor.date().toordinal() - days
            fee_txns = [txn for txn in fee_txns if txn.timestamp.date().toordinal() >= cutoff]
        return sum((txn.amount for txn in fee_txns), Decimal("0"))

    def total_dividends_received(self, days: int | None = None) -> Decimal:
        dividend_txns = [txn for txn in self.transactions if txn.type == "dividend"]
        if days is not None and dividend_txns:
            anchor = max(txn.timestamp for txn in dividend_txns)
            cutoff = anchor.date().toordinal() - days
            dividend_txns = [txn for txn in dividend_txns if txn.timestamp.date().toordinal() >= cutoff]
        return sum((txn.amount for txn in dividend_txns), Decimal("0"))

    def total_dividends_received_between(self, min_days_ago: int, max_days_ago: int) -> Decimal:
        if min_days_ago < 0 or max_days_ago < min_days_ago:
            return Decimal("0")
        from breakingweb.backend.seeders.robinhood import derive_anchor_time

        anchor = derive_anchor_time(self.seed) if self.seed is not None else utc_now()
        total = Decimal("0")
        for txn in self.transactions:
            if txn.type != "dividend":
                continue
            age_days = (anchor.date() - txn.timestamp.date()).days
            if min_days_ago <= age_days < max_days_ago:
                total += txn.amount
        return total

    def tax_document_for_year(self, tax_year: int | None = None) -> TaxDocument | None:
        if not self.tax_documents:
            return None
        if tax_year is None:
            return max(self.tax_documents, key=lambda doc: doc.tax_year)
        return next((doc for doc in self.tax_documents if doc.tax_year == tax_year), None)

    def total_realized_gains(
        self,
        *,
        holding_period: Literal["short", "long"] | None = None,
        gains_only: bool = False,
    ) -> Decimal:
        total = Decimal("0")
        for doc in self.tax_documents:
            for gain in doc.realized_gains:
                if holding_period is not None and gain.holding_period != holding_period:
                    continue
                if gains_only and gain.gain_loss <= Decimal("0"):
                    continue
                total += gain.gain_loss
        return total

    def margin_utilization_pct(self) -> Decimal:
        portfolio = self.total_position_value()
        if portfolio == Decimal("0"):
            return Decimal("0")
        margin_used = max(self.buying_power - self.cash_balance, Decimal("0"))
        return (margin_used / portfolio) * Decimal("100")

    def estimated_cost_basis_per_share(self, symbol: str) -> Decimal:
        position = self.get_position(symbol)
        if position is not None and position.quantity > Decimal("0"):
            return position.avg_cost_basis
        if symbol in self._cost_basis_snapshots:
            return self._cost_basis_snapshots[symbol]

        total_quantity = Decimal("0")
        total_cost = Decimal("0")
        for txn in self.transactions:
            if txn.symbol != symbol or txn.type != "buy" or txn.quantity is None or txn.quantity <= Decimal("0"):
                continue
            total_quantity += txn.quantity
            total_cost += txn.amount
        if total_quantity == Decimal("0"):
            return Decimal("0")
        return total_cost / total_quantity

    def estimated_harvested_loss(self) -> Decimal:
        total = Decimal("0")
        for order in self.orders:
            if order.side != "sell" or order.status not in ("pending", "partially_filled", "filled"):
                continue
            cost_basis_per_share = self.estimated_cost_basis_per_share(order.symbol)
            stock = self.get_stock(order.symbol)
            if cost_basis_per_share == Decimal("0") or stock is None:
                continue
            sale_price = order.filled_price if order.status == "filled" and order.filled_price is not None else stock.price
            per_share_loss = max(cost_basis_per_share - sale_price, Decimal("0"))
            total += per_share_loss * order.quantity
        return total

    def highest_open_interest_contract(
        self,
        symbol: str,
        *,
        option_type: Literal["call", "put"] | None = None,
        max_days: int | None = None,
    ) -> OptionsContract | None:
        contracts = self.options_chains.get(symbol, [])
        if not contracts:
            return None
        anchor = min(contract.expiration for contract in contracts)
        filtered = [
            contract
            for contract in contracts
            if (option_type is None or contract.option_type == option_type)
            and (max_days is None or 0 <= (contract.expiration - anchor).days <= max_days)
        ]
        if not filtered:
            return None
        return max(filtered, key=lambda contract: contract.open_interest)

    def expiring_options_positions(self, days: int) -> list[OptionsPosition]:
        from breakingweb.backend.seeders.robinhood import derive_anchor_time

        anchor = derive_anchor_time(self.seed).date() if self.seed is not None else utc_now().date()
        return [
            position for position in self.options_positions
            if 0 <= (position.expiration_date - anchor).days <= days
        ]

    def anchor_date(self) -> date:
        from breakingweb.backend.seeders.robinhood import derive_anchor_time

        return derive_anchor_time(self.seed).date() if self.seed is not None else utc_now().date()

    def days_until(self, value: date) -> int:
        return (value - self.anchor_date()).days

    def option_position_gain_pct(self, position: OptionsPosition) -> Decimal:
        if position.avg_cost == Decimal("0"):
            return Decimal("0")
        if position.position_side == "long":
            return ((position.current_premium - position.avg_cost) / position.avg_cost) * Decimal("100")
        return ((position.avg_cost - position.current_premium) / position.avg_cost) * Decimal("100")

    def option_position_is_in_the_money(self, position: OptionsPosition) -> bool:
        stock = self.get_stock(position.underlying_symbol)
        if stock is None:
            return False
        if position.option_type == "call":
            return stock.price > position.strike_price
        return stock.price < position.strike_price

    def expiring_options_positions_requiring_action(
        self,
        days: int,
        *,
        long_gain_threshold_pct: Decimal = Decimal("20"),
    ) -> list[OptionsPosition]:
        requiring_action: list[OptionsPosition] = []
        for position in self.expiring_options_positions(days):
            if position.position_side == "long":
                if self.option_position_gain_pct(position) > long_gain_threshold_pct:
                    requiring_action.append(position)
            elif self.option_position_is_in_the_money(position):
                requiring_action.append(position)
        return requiring_action

    def options_orders_for_symbol(self, symbol: str) -> list[OptionsOrder]:
        return [
            order for order in self.options_orders
            if any(leg.underlying_symbol == symbol for leg in order.legs)
        ]

    def latest_options_order(
        self,
        *,
        strategy: str | None = None,
        symbol: str | None = None,
    ) -> OptionsOrder | None:
        candidates = [
            order
            for order in self.options_orders
            if (strategy is None or order.strategy == strategy)
            and (symbol is None or any(leg.underlying_symbol == symbol for leg in order.legs))
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda order: order.created_at)

    def options_order_net_premium(self, order: OptionsOrder) -> Decimal:
        total = Decimal("0")
        for leg in order.legs:
            multiplier = Decimal("1") if leg.side == "sell" else Decimal("-1")
            total += multiplier * leg.premium * Decimal(str(leg.quantity)) * Decimal("100")
        return total

    def total_options_order_net_premium(self, symbol: str | None = None) -> Decimal:
        return sum(
            (
                self.options_order_net_premium(order)
                for order in self.options_orders
                if symbol is None or any(leg.underlying_symbol == symbol for leg in order.legs)
            ),
            Decimal("0"),
        )

    def options_order_max_profit(self, order: OptionsOrder) -> Decimal:
        if order.strategy == "iron_condor":
            return max(self.options_order_net_premium(order), Decimal("0"))
        return self.options_order_net_premium(order)

    def options_order_max_loss(self, order: OptionsOrder) -> Decimal:
        if order.strategy != "iron_condor":
            return Decimal("0")
        short_calls = [leg for leg in order.legs if leg.option_type == "call" and leg.side == "sell"]
        long_calls = [leg for leg in order.legs if leg.option_type == "call" and leg.side == "buy"]
        short_puts = [leg for leg in order.legs if leg.option_type == "put" and leg.side == "sell"]
        long_puts = [leg for leg in order.legs if leg.option_type == "put" and leg.side == "buy"]
        if not short_calls or not long_calls or not short_puts or not long_puts:
            return Decimal("0")
        call_width = max(leg.strike for leg in long_calls) - min(leg.strike for leg in short_calls)
        put_width = max(leg.strike for leg in short_puts) - min(leg.strike for leg in long_puts)
        width = min(call_width, put_width)
        quantity = min(
            [leg.quantity for leg in short_calls + long_calls + short_puts + long_puts],
            default=1,
        )
        gross_risk = width * Decimal(str(quantity)) * Decimal("100")
        return max(gross_risk - self.options_order_net_premium(order), Decimal("0"))

    def total_short_put_assignment_risk(self, symbol: str | None = None) -> Decimal:
        total = Decimal("0")
        for order in self.options_orders:
            for leg in order.legs:
                if leg.side != "sell" or leg.option_type != "put":
                    continue
                if symbol is not None and leg.underlying_symbol != symbol:
                    continue
                total += leg.strike * Decimal(str(leg.quantity)) * Decimal("100")
        return total

    def filled_limit_order_symbols_with_slippage(self, threshold_pct: Decimal) -> list[str]:
        symbols: set[str] = set()
        for order in self.orders:
            if (
                order.order_type != "limit"
                or order.status != "filled"
                or order.limit_price is None
                or order.filled_price is None
                or order.limit_price == Decimal("0")
            ):
                continue
            slippage_pct = (abs(order.filled_price - order.limit_price) / order.limit_price) * Decimal("100")
            if slippage_pct > threshold_pct:
                symbols.add(order.symbol)
        return sorted(symbols)

    def corporate_action_symbols(self) -> list[str]:
        symbols: set[str] = set()
        for notification in self.notifications_of_type("corporate_action"):
            if ":" in notification.title:
                maybe_symbol = notification.title.split(":", 1)[1].strip().split()[0]
                if maybe_symbol:
                    symbols.add(maybe_symbol)
        return sorted(symbols)

    def nearest_expiration_contract(
        self,
        symbol: str,
        *,
        option_type: Literal["call", "put"] | None = None,
    ) -> OptionsContract | None:
        contracts = self.options_chains.get(symbol, [])
        filtered = [
            contract for contract in contracts
            if option_type is None or contract.option_type == option_type
        ]
        if not filtered:
            return None
        earliest = min(contract.expiration for contract in filtered)
        candidates = [contract for contract in filtered if contract.expiration == earliest]
        stock = self.get_stock(symbol)
        if stock is None:
            return candidates[0]
        return min(candidates, key=lambda contract: abs(float(contract.strike) - float(stock.price)))

    def list_transactions(
        self,
        *,
        type: str | None = None,
        symbol: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Transaction]:
        result = list(self.transactions)
        if type is not None:
            result = [t for t in result if t.type == type]
        if symbol is not None:
            result = [t for t in result if t.symbol == symbol]
        if from_date is not None:
            result = [t for t in result if t.timestamp >= from_date]
        if to_date is not None:
            result = [t for t in result if t.timestamp <= to_date]
        return result

    def state_snapshot(self) -> dict[str, Any]:
        """Capture all mutable state dimensions for collateral-damage detection.

        Called once after seeding to record the baseline.  At evaluation time
        the evaluator diffs the current state against this snapshot and reports
        any unintended mutations as analytics-only collateral metrics.
        """
        position_snap: dict[str, dict[str, Any]] = {}
        for p in self.positions:
            position_snap[p.symbol] = {
                "quantity": str(p.quantity),
                "avg_cost_basis": str(p.avg_cost_basis),
            }

        order_ids = sorted(o.id for o in self.orders)
        order_statuses: dict[str, str] = {o.id: o.status for o in self.orders}

        options_position_snap: dict[str, dict[str, Any]] = {}
        for op in self.options_positions:
            options_position_snap[op.contract_id] = {
                "quantity": op.quantity,
                "status": op.status,
                "position_side": op.position_side,
            }

        options_order_ids = sorted(o.id for o in self.options_orders)
        options_order_statuses: dict[str, str] = {o.id: o.status for o in self.options_orders}

        watchlist_snap: dict[str, dict[str, Any]] = {}
        for w in self.watchlists:
            watchlist_snap[w.id] = {
                "name": w.name,
                "symbols": sorted(w.symbols),
            }

        transfer_snap: dict[str, dict[str, Any]] = {}
        for t in self.transfers:
            transfer_snap[t.id] = {
                "direction": t.direction,
                "amount": str(t.amount),
                "status": t.status,
            }

        recurring_snap: dict[str, dict[str, Any]] = {}
        for ri in self.recurring_investments:
            recurring_snap[ri.id] = {
                "symbol": ri.symbol,
                "amount": str(ri.amount),
                "frequency": ri.frequency,
                "status": ri.status,
            }

        alert_snap: dict[str, dict[str, Any]] = {}
        for a in self.price_alerts:
            alert_snap[a.id] = {
                "symbol": a.symbol,
                "condition": a.condition,
                "target_price": str(a.target_price),
                "status": a.status,
            }

        notification_read: dict[str, bool] = {
            n.id: n.is_read for n in self.notifications
        }

        settings = self.settings.model_dump(mode="json")
        settings.pop("id", None)

        return {
            "cash_balance": str(self.cash_balance),
            "buying_power": str(self.buying_power),
            "portfolio_value": str(self.portfolio_value),
            "positions": position_snap,
            "order_ids": order_ids,
            "order_statuses": order_statuses,
            "options_positions": options_position_snap,
            "options_order_ids": options_order_ids,
            "options_order_statuses": options_order_statuses,
            "watchlists": watchlist_snap,
            "transfers": transfer_snap,
            "transfer_count": len(self.transfers),
            "recurring_investments": recurring_snap,
            "price_alerts": alert_snap,
            "notification_ids": sorted(notification_read.keys()),
            "notification_read": notification_read,
            "transaction_count": len(self.transactions),
            "settings": settings,
        }

    def compute_collateral(self, initial: dict[str, Any]) -> dict[str, Any]:
        """Diff current state against the initial snapshot.

        Returns a structured report of unintended mutations, categorised by
        dimension.  Analytics-only — never affects the score.
        """
        current = self.state_snapshot()
        report: dict[str, Any] = {}

        # Account-level scalars
        for key in ("cash_balance", "buying_power", "portfolio_value"):
            if initial.get(key) != current.get(key):
                report.setdefault("account_changes", {})[key] = {
                    "before": initial.get(key),
                    "after": current.get(key),
                }

        # Dict-of-dicts dimensions
        for snapshot_key, prefix, id_label in (
            ("positions", "positions", "symbol"),
            ("options_positions", "options_positions", "contract_id"),
            ("watchlists", "watchlists", "watchlist_id"),
            ("transfers", "transfers", "transfer_id"),
            ("recurring_investments", "recurring_investments", "recurring_id"),
            ("price_alerts", "price_alerts", "alert_id"),
        ):
            added, removed, modified = diff_dict_of_dicts(
                initial.get(snapshot_key, {}),
                current.get(snapshot_key, {}),
                id_label,
            )
            if added:
                report[f"{prefix}_added"] = added
            if removed:
                report[f"{prefix}_removed"] = removed
            if modified:
                report[f"{prefix}_modified"] = modified

        # Orders (ID-set + status map, not dict-of-dicts)
        init_order_ids = set(initial.get("order_ids", []))
        curr_order_ids = set(current.get("order_ids", []))
        orders_created = sorted(curr_order_ids - init_order_ids)
        if orders_created:
            report["orders_created"] = orders_created
        init_ostatus = initial.get("order_statuses", {})
        curr_ostatus = current.get("order_statuses", {})
        order_status_changes = [
            {"order_id": oid, "before": init_ostatus[oid], "after": curr_ostatus[oid]}
            for oid in sorted(init_order_ids & curr_order_ids)
            if init_ostatus.get(oid) != curr_ostatus.get(oid)
        ]
        if order_status_changes:
            report["order_status_changes"] = order_status_changes

        # Options orders (ID-set only)
        init_oo_ids = set(initial.get("options_order_ids", []))
        curr_oo_ids = set(current.get("options_order_ids", []))
        oo_created = sorted(curr_oo_ids - init_oo_ids)
        if oo_created:
            report["options_orders_created"] = oo_created

        # Notifications read
        init_read = initial.get("notification_read", {})
        curr_read = current.get("notification_read", {})
        newly_read = [nid for nid in init_read if not init_read[nid] and curr_read.get(nid, False)]
        if newly_read:
            report["notifications_read"] = sorted(newly_read)

        # Transactions delta
        txn_delta = current.get("transaction_count", 0) - initial.get("transaction_count", 0)
        if txn_delta > 0:
            report["transactions_added"] = txn_delta

        # Settings
        init_settings = initial.get("settings", {})
        curr_settings = current.get("settings", {})
        settings_changed = {k: {"before": init_settings[k], "after": curr_settings[k]}
                            for k in init_settings
                            if init_settings.get(k) != curr_settings.get(k)}
        if settings_changed:
            report["settings_changed"] = settings_changed

        return report

    def session_summary(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "task_id": self.task_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "account_type": self.account_type,
            "cash_balance": str(self.cash_balance),
            "buying_power": str(self.buying_power),
            "portfolio_value": str(self.portfolio_value),
            "counts": {
                "positions": len(self.positions),
                "orders": len(self.orders),
                "stocks": len(self.stocks),
                "watchlists": len(self.watchlists),
                "transactions": len(self.transactions),
                "notifications": len(self.notifications),
                "unread_notifications": len(self.unread_notifications()),
                "price_alerts": len(self.price_alerts),
            },
        }

    # ---- Mutation methods ----

    def place_order(
        self,
        *,
        symbol: str,
        side: Literal["buy", "sell"],
        order_type: Literal["market", "limit", "stop", "stop_limit", "trailing_stop"] = "market",
        quantity: Decimal,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        trail_amount: Decimal | None = None,
        trail_pct: Decimal | None = None,
        time_in_force: Literal["gfd", "gtc", "ioc", "opg"] = "gfd",
        extended_hours: bool = False,
    ) -> Order:
        order_id = self._gen_id("ord")
        now = utc_now()

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            filled_quantity=Decimal("0"),
            limit_price=limit_price,
            stop_price=stop_price,
            trail_amount=trail_amount,
            trail_pct=trail_pct,
            time_in_force=time_in_force,
            status="pending",
            extended_hours=extended_hours,
            created_at=now,
        )

        # Auto-fill market orders
        if order_type == "market":
            stock = self.get_stock(symbol)
            if stock is None:
                raise ValueError(f"Unknown stock: {symbol}")
            price = stock.price
            total = price * quantity

            if side == "buy":
                if total > self.buying_power:
                    raise ValueError("Insufficient funds")
                self.cash_balance -= total
                self.buying_power -= total

                # Create or update position
                pos = self.get_position(symbol)
                if pos is None:
                    pos = Position(
                        id=self._gen_id("pos"),
                        symbol=symbol,
                        name=stock.name,
                        asset_type=stock.asset_type,
                        quantity=quantity,
                        avg_cost_basis=price,
                        current_price=price,
                        day_change_pct=stock.day_change_pct,
                        total_return=Decimal("0"),
                        total_return_pct=Decimal("0"),
                        lots=[TaxLot(shares=quantity, cost_per_share=price, acquired_date=now.date())],
                    )
                    self.positions.append(pos)
                    self._cost_basis_snapshots[symbol] = pos.avg_cost_basis
                else:
                    new_qty = pos.quantity + quantity
                    pos.avg_cost_basis = (
                        (pos.avg_cost_basis * pos.quantity + price * quantity) / new_qty
                    )
                    pos.quantity = new_qty
                    pos.current_price = price
                    pos.lots.append(TaxLot(shares=quantity, cost_per_share=price, acquired_date=now.date()))
                    self._cost_basis_snapshots[symbol] = pos.avg_cost_basis
            else:  # sell
                pos = self.get_position(symbol)
                if pos is None or pos.quantity < quantity:
                    raise ValueError("Insufficient shares")
                self.cash_balance += total
                self.buying_power += total
                self._cost_basis_snapshots[symbol] = pos.avg_cost_basis
                pos.quantity -= quantity
                if pos.quantity == Decimal("0"):
                    self.positions = [p for p in self.positions if p.symbol != symbol]

            order.status = "filled"
            order.filled_quantity = quantity
            order.filled_price = price
            order.filled_at = now
            if self._price_engine is not None:
                order.filled_tick = self._price_engine.tick_count

            # Add transaction
            self.transactions.append(
                Transaction(
                    id=self._gen_id("txn"),
                    type=side,
                    symbol=symbol,
                    quantity=quantity,
                    amount=total,
                    description=f"Market {side} {quantity} shares of {symbol} @ ${price}",
                    timestamp=now,
                )
            )

            # Add notification
            self.notifications.append(
                Notification(
                    id=self._gen_id("notif"),
                    type="order_fill",
                    title=f"Order Filled: {symbol}",
                    message=f"Your market {side} order for {quantity} shares of {symbol} was filled at ${price}.",
                    timestamp=now,
                )
            )

        self.orders.append(order)
        self.touch()
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"Unknown order id: {order_id}")
        if order.status not in ("pending", "partially_filled"):
            raise ValueError(f"Cannot cancel order with status: {order.status}")
        order.status = "cancelled"
        order.cancelled_at = utc_now()
        self.touch()
        return order

    def place_options_order(
        self,
        *,
        strategy: str,
        legs: list[OptionsLeg],
    ) -> OptionsOrder:
        order = OptionsOrder(
            id=self._gen_id("oord"),
            strategy=strategy,
            legs=legs,
            status="pending",
            created_at=utc_now(),
        )
        self.options_orders.append(order)
        self.touch()
        return order

    def create_watchlist(self, name: str, symbols: list[str] | None = None) -> Watchlist:
        wl = Watchlist(
            id=self._gen_id("wl"),
            name=name,
            symbols=list(symbols or []),
            created_at=utc_now(),
        )
        self.watchlists.append(wl)
        self.touch()
        return wl

    def add_to_watchlist(self, watchlist_id: str, symbol: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        if symbol not in wl.symbols:
            wl.symbols.append(symbol)
        self.touch()
        return wl

    def remove_from_watchlist(self, watchlist_id: str, symbol: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        wl.symbols = [s for s in wl.symbols if s != symbol]
        self.touch()
        return wl

    def initiate_transfer(
        self,
        direction: Literal["deposit", "withdrawal"],
        amount: Decimal,
        bank_account_id: str,
    ) -> Transfer:
        bank = self.get_bank(bank_account_id)
        if bank is None:
            raise KeyError(f"Unknown bank account id: {bank_account_id}")

        now = utc_now()
        transfer = Transfer(
            id=self._gen_id("xfer"),
            direction=direction,
            amount=amount,
            status="pending",
            bank_account_id=bank_account_id,
            initiated_at=now,
        )

        if direction == "deposit":
            self.cash_balance += amount
            self.buying_power += amount
        else:  # withdrawal
            if amount > self.buying_power:
                raise ValueError("Insufficient funds for withdrawal")
            self.cash_balance -= amount
            self.buying_power -= amount

        self.transactions.append(
            Transaction(
                id=self._gen_id("txn"),
                type=direction,
                symbol=None,
                quantity=None,
                amount=amount,
                description=f"{'Deposit from' if direction == 'deposit' else 'Withdrawal to'} {bank.bank_name} ****{bank.last_four}",
                timestamp=now,
            )
        )

        self.transfers.append(transfer)
        self.touch()
        return transfer

    def create_recurring_investment(
        self,
        symbol: str,
        amount: Decimal,
        frequency: Literal["daily", "weekly", "biweekly", "monthly"],
        next_execution_date: date,
    ) -> RecurringInvestment:
        ri = RecurringInvestment(
            id=self._gen_id("ri"),
            symbol=symbol,
            amount=amount,
            frequency=frequency,
            next_execution_date=next_execution_date,
            status="active",
        )
        self.recurring_investments.append(ri)
        self.touch()
        return ri

    def update_recurring_investment(
        self,
        ri_id: str,
        *,
        amount: Decimal | None = None,
        frequency: str | None = None,
        status: str | None = None,
    ) -> RecurringInvestment:
        ri = next((r for r in self.recurring_investments if r.id == ri_id), None)
        if ri is None:
            raise KeyError(f"Unknown recurring investment id: {ri_id}")
        if amount is not None:
            ri.amount = amount
        if frequency is not None:
            ri.frequency = frequency  # type: ignore[assignment]
        if status is not None:
            ri.status = status  # type: ignore[assignment]
        self.touch()
        return ri

    def create_price_alert(
        self,
        symbol: str,
        condition: Literal["above", "below"],
        target_price: Decimal,
    ) -> PriceAlert:
        alert = PriceAlert(
            id=self._gen_id("alert"),
            symbol=symbol,
            condition=condition,
            target_price=target_price,
            status="active",
            created_at=utc_now(),
        )
        self.price_alerts.append(alert)
        self.touch()
        return alert

    def mark_notification_read(self, notification_id: str) -> Notification:
        notif = next((n for n in self.notifications if n.id == notification_id), None)
        if notif is None:
            raise KeyError(f"Unknown notification id: {notification_id}")
        notif.is_read = True
        self.touch()
        return notif

    def mark_all_notifications_read(self) -> int:
        count = 0
        for n in self.notifications:
            if not n.is_read:
                n.is_read = True
                count += 1
        if count > 0:
            self.touch()
        return count

    def update_settings(self, **kwargs: Any) -> AccountSettings:
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
            else:
                raise ValueError(f"Unknown setting: {key}")
        self.touch()
        return self.settings

    def rename_watchlist(self, watchlist_id: str, name: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        wl.name = name
        self.touch()
        return wl

    def delete_watchlist(self, watchlist_id: str) -> Watchlist:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            raise KeyError(f"Unknown watchlist id: {watchlist_id}")
        self.watchlists = [w for w in self.watchlists if w.id != watchlist_id]
        self.touch()
        return wl

    def link_bank(
        self,
        bank_name: str,
        account_type: Literal["checking", "savings"],
        last_four: str,
    ) -> LinkedBank:
        bank = LinkedBank(
            id=self._gen_id("bank"),
            bank_name=bank_name,
            account_type=account_type,
            last_four=last_four,
            status="verified",
            is_default=len(self.linked_banks) == 0,
        )
        self.linked_banks.append(bank)
        self.touch()
        return bank

    def unlink_bank(self, bank_id: str) -> LinkedBank:
        bank = self.get_bank(bank_id)
        if bank is None:
            raise KeyError(f"Unknown bank account id: {bank_id}")
        self.linked_banks = [b for b in self.linked_banks if b.id != bank_id]
        self.touch()
        return bank

    def delete_recurring_investment(self, ri_id: str) -> RecurringInvestment:
        ri = next((r for r in self.recurring_investments if r.id == ri_id), None)
        if ri is None:
            raise KeyError(f"Unknown recurring investment id: {ri_id}")
        self.recurring_investments = [r for r in self.recurring_investments if r.id != ri_id]
        self.touch()
        return ri

    def delete_price_alert(self, alert_id: str) -> PriceAlert:
        alert = next((a for a in self.price_alerts if a.id == alert_id), None)
        if alert is None:
            raise KeyError(f"Unknown price alert id: {alert_id}")
        self.price_alerts = [a for a in self.price_alerts if a.id != alert_id]
        self.touch()
        return alert

    def update_2fa(self, method: Literal["sms", "authenticator", "none"]) -> AccountSettings:
        self.settings.two_factor_method = method
        self.security_log.append(
            SecurityEntry(
                event="2fa_change",
                device="web",
                ip_address="0.0.0.0",
                location="Unknown",
                timestamp=utc_now(),
            )
        )
        self.touch()
        return self.settings
