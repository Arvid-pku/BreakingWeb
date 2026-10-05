from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from decimal import Decimal

from breakingweb.backend.models.base import utc_now
from breakingweb.backend.models.robinhood import (
    Notification,
    Position,
    RobinhoodState,
    TaxLot,
    Transaction,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class StockTrajectory:
    keyframes: list[list[float]]  # [[tick_number, target_price], ...]
    noise_pct: float = 0.3        # ±0.3% max noise per tick


@dataclass
class TrajectoryConfig:
    tick_interval_seconds: float = 2.0
    stocks: dict[str, StockTrajectory] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PriceEngine
# ---------------------------------------------------------------------------

class PriceEngine:
    """Simulate live stock price movements using scripted trajectories.

    Prices interpolate linearly between keyframes with optional seeded noise.
    Advances based on wall-clock time when ``tick_by_clock()`` is called
    (tick-on-read pattern).
    """

    def __init__(self, config: TrajectoryConfig, seed: int = 42) -> None:
        self.config = config
        self.tick_count = 0
        self.start_time = time.monotonic()
        self.last_tick_time = self.start_time
        self.enabled = bool(config.stocks)

        # Pre-generate noise for determinism: for each symbol,
        # a list of random floats in [-1, 1] indexed by tick.
        rng = random.Random(seed)
        max_tick = max(
            (int(t.keyframes[-1][0]) + 20 for t in config.stocks.values() if t.keyframes),
            default=100,
        )
        max_tick = max(max_tick, 100)
        self._noise: dict[str, list[float]] = {}
        for symbol in config.stocks:
            self._noise[symbol] = [rng.uniform(-1, 1) for _ in range(max_tick)]

    # ------------------------------------------------------------------
    # Price calculation
    # ------------------------------------------------------------------

    def price_at_tick(self, symbol: str, tick: int) -> Decimal:
        """Calculate price for a symbol at a specific tick via linear interpolation + noise."""
        trajectory = self.config.stocks.get(symbol)
        if not trajectory or not trajectory.keyframes:
            return Decimal("0")

        kf = trajectory.keyframes

        # Interpolation logic
        if tick <= kf[0][0]:
            base = kf[0][1]
        elif tick >= kf[-1][0]:
            base = kf[-1][1]
        else:
            for i in range(len(kf) - 1):
                t0, p0 = kf[i]
                t1, p1 = kf[i + 1]
                if t0 <= tick <= t1:
                    progress = (tick - t0) / (t1 - t0) if t1 != t0 else 0
                    base = p0 + (p1 - p0) * progress
                    break
            else:
                base = kf[-1][1]

        # Apply noise (not at tick 0)
        if trajectory.noise_pct > 0 and tick > 0:
            noise_list = self._noise.get(symbol, [])
            noise_val = noise_list[tick % len(noise_list)] if noise_list else 0
            base *= 1 + noise_val * (trajectory.noise_pct / 100)

        return Decimal(str(round(base, 2)))

    # ------------------------------------------------------------------
    # Tick advancement
    # ------------------------------------------------------------------

    def advance(self, num_ticks: int) -> dict[str, Decimal]:
        """Advance by *num_ticks*. Returns ``{symbol: new_price}``."""
        if num_ticks <= 0:
            return {}
        new_tick = self.tick_count + num_ticks
        prices = {sym: self.price_at_tick(sym, new_tick) for sym in self.config.stocks}
        self.tick_count = new_tick
        return prices

    def tick_by_clock(self) -> dict[str, Decimal]:
        """Advance based on wall-clock time since last tick."""
        if not self.enabled:
            return {}
        now = time.monotonic()
        elapsed = now - self.last_tick_time
        new_ticks = int(elapsed / self.config.tick_interval_seconds)
        if new_ticks <= 0:
            return {}
        self.last_tick_time += new_ticks * self.config.tick_interval_seconds
        return self.advance(new_ticks)


# ---------------------------------------------------------------------------
# cascade_update  (standalone — keeps PriceEngine decoupled from state model)
# ---------------------------------------------------------------------------

def cascade_update(
    state: RobinhoodState,
    new_prices: dict[str, Decimal],
    engine: PriceEngine,
) -> list[str]:
    """Apply price changes to *state*: update stocks, positions, fill orders,
    trigger alerts, and recalculate portfolio value.

    Returns a list of event description strings for logging.
    """
    events: list[str] = []
    now = utc_now()

    # 1. Update stock prices -------------------------------------------------
    for stock in state.stocks:
        if stock.symbol not in new_prices:
            continue
        new_price = new_prices[stock.symbol]
        stock.price = new_price
        stock.day_change = new_price - stock.previous_close
        stock.day_change_pct = (
            Decimal(str(round(float(stock.day_change) / float(stock.previous_close) * 100, 2)))
            if stock.previous_close != 0
            else Decimal("0")
        )
        stock.bid = new_price - Decimal("0.01")
        stock.ask = new_price + Decimal("0.01")
        events.append(f"price:{stock.symbol}={new_price}")

    # 2. Update positions ----------------------------------------------------
    for pos in state.positions:
        stock = state.get_stock(pos.symbol)
        if stock is None:
            continue
        pos.current_price = stock.price
        cost_total = pos.avg_cost_basis * pos.quantity
        market_total = pos.current_price * pos.quantity
        pos.total_return = market_total - cost_total
        pos.total_return_pct = (
            Decimal(str(round(float(pos.total_return) / float(cost_total) * 100, 2)))
            if cost_total != 0
            else Decimal("0")
        )
        pos.day_change_pct = stock.day_change_pct

    # 3. Check pending order fills -------------------------------------------
    for order in list(state.orders):
        if order.status != "pending":
            continue
        stock = state.get_stock(order.symbol)
        if stock is None:
            continue

        should_fill = False
        fill_price = stock.price

        if order.order_type == "limit":
            if order.side == "buy" and order.limit_price is not None:
                should_fill = stock.price <= order.limit_price
                fill_price = order.limit_price
            elif order.side == "sell" and order.limit_price is not None:
                should_fill = stock.price >= order.limit_price
                fill_price = order.limit_price
        elif order.order_type == "stop":
            if order.side == "sell" and order.stop_price is not None:
                should_fill = stock.price <= order.stop_price
                fill_price = stock.price
            elif order.side == "buy" and order.stop_price is not None:
                should_fill = stock.price >= order.stop_price
                fill_price = stock.price

        if not should_fill:
            continue

        # Fill the order
        order.status = "filled"
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.filled_tick = engine.tick_count
        order.filled_at = now
        total = fill_price * order.quantity

        if order.side == "buy":
            state.cash_balance -= total
            state.buying_power -= total

            pos = state.get_position(order.symbol)
            if pos is None:
                pos = Position(
                    id=state._gen_id("pos"),
                    symbol=order.symbol,
                    name=stock.name,
                    asset_type=stock.asset_type,
                    quantity=order.quantity,
                    avg_cost_basis=fill_price,
                    current_price=stock.price,
                    day_change_pct=stock.day_change_pct,
                    total_return=Decimal("0"),
                    total_return_pct=Decimal("0"),
                    lots=[TaxLot(shares=order.quantity, cost_per_share=fill_price, acquired_date=now.date())],
                )
                state.positions.append(pos)
            else:
                new_qty = pos.quantity + order.quantity
                pos.avg_cost_basis = (
                    (pos.avg_cost_basis * pos.quantity + fill_price * order.quantity) / new_qty
                )
                pos.quantity = new_qty
                pos.current_price = stock.price
                pos.lots.append(TaxLot(shares=order.quantity, cost_per_share=fill_price, acquired_date=now.date()))
        else:  # sell
            state.cash_balance += total
            state.buying_power += total
            pos = state.get_position(order.symbol)
            if pos is not None:
                pos.quantity -= order.quantity
                if pos.quantity <= 0:
                    state.positions = [p for p in state.positions if p.symbol != order.symbol]

        state.transactions.append(
            Transaction(
                id=state._gen_id("txn"),
                type=order.side,
                symbol=order.symbol,
                quantity=order.quantity,
                amount=total,
                description=f"{order.order_type.title()} {order.side} {order.quantity} shares of {order.symbol} @ ${fill_price}",
                timestamp=now,
            )
        )
        state.notifications.append(
            Notification(
                id=state._gen_id("notif"),
                type="order_fill",
                title=f"Order Filled: {order.symbol}",
                message=f"Your {order.order_type} {order.side} order for {order.quantity} shares of {order.symbol} was filled at ${fill_price}.",
                timestamp=now,
            )
        )
        events.append(f"fill:{order.side} {order.quantity} {order.symbol}@{fill_price}")

    # 4. Check price alerts --------------------------------------------------
    for alert in state.price_alerts:
        if alert.status != "active":
            continue
        stock = state.get_stock(alert.symbol)
        if stock is None:
            continue

        triggered = False
        if alert.condition == "above" and stock.price >= alert.target_price:
            triggered = True
        elif alert.condition == "below" and stock.price <= alert.target_price:
            triggered = True

        if triggered:
            alert.status = "triggered"
            alert.triggered_at = now
            state.notifications.append(
                Notification(
                    id=state._gen_id("notif"),
                    type="price_alert",
                    title=f"Price Alert: {alert.symbol}",
                    message=f"{alert.symbol} is now {alert.condition} ${alert.target_price} (current: ${stock.price}).",
                    timestamp=now,
                )
            )
            events.append(f"alert:{alert.symbol} {alert.condition} {alert.target_price}")

    # 5. Recalculate portfolio value -----------------------------------------
    state.portfolio_value = sum(
        pos.current_price * pos.quantity for pos in state.positions
    )

    return events
