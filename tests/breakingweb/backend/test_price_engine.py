from __future__ import annotations

from decimal import Decimal

import pytest

from breakingweb.backend.models.robinhood import (
    AccountSettings,
    Order,
    Position,
    PriceAlert,
    RobinhoodState,
    Stock,
    TaxLot,
)
from breakingweb.backend.models.base import utc_now
from breakingweb.backend.price_engine import (
    PriceEngine,
    StockTrajectory,
    TrajectoryConfig,
    cascade_update,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stock(symbol: str, price: float, **overrides) -> Stock:
    defaults = dict(
        symbol=symbol,
        name=f"{symbol} Inc.",
        asset_type="stock",
        price=Decimal(str(price)),
        previous_close=Decimal(str(price)),
        day_change=Decimal("0"),
        day_change_pct=Decimal("0"),
        bid=Decimal(str(round(price - 0.01, 2))),
        ask=Decimal(str(round(price + 0.01, 2))),
        bid_size=100,
        ask_size=100,
        volume=1_000_000,
        avg_volume=1_000_000,
        fifty_two_week_high=Decimal(str(round(price * 1.5, 2))),
        fifty_two_week_low=Decimal(str(round(price * 0.5, 2))),
        sector="Technology",
        industry="Software",
        about="A test stock.",
    )
    defaults.update(overrides)
    return Stock(**defaults)


def _make_state(stocks: list[Stock] | None = None, **kwargs) -> RobinhoodState:
    defaults = dict(
        env_id="robinhood",
        task_id="test",
        owner_name="Test",
        owner_email="test@test.com",
        cash_balance=Decimal("5000"),
        buying_power=Decimal("5000"),
        portfolio_value=Decimal("0"),
        settings=AccountSettings(id="s1"),
        stocks=stocks or [],
    )
    defaults.update(kwargs)
    return RobinhoodState(**defaults)


# ---------------------------------------------------------------------------
# Tests: PriceEngine basics
# ---------------------------------------------------------------------------

class TestEngineCreation:
    def test_engine_creation(self):
        config = TrajectoryConfig(
            tick_interval_seconds=1.0,
            stocks={
                "AAPL": StockTrajectory(keyframes=[[0, 150.0], [10, 160.0]]),
                "GOOG": StockTrajectory(keyframes=[[0, 2800.0], [5, 2900.0]]),
            },
        )
        engine = PriceEngine(config, seed=42)

        assert engine.tick_count == 0
        assert engine.enabled is True
        assert len(engine._noise) == 2
        assert "AAPL" in engine._noise
        assert "GOOG" in engine._noise


class TestInterpolation:
    def test_interpolation_at_keyframes(self):
        config = TrajectoryConfig(stocks={
            "X": StockTrajectory(keyframes=[[0, 100.0], [10, 200.0]], noise_pct=0),
        })
        engine = PriceEngine(config)

        # At first keyframe
        assert engine.price_at_tick("X", 0) == Decimal("100.0")
        # At last keyframe
        assert engine.price_at_tick("X", 10) == Decimal("200.0")
        # Midpoint
        assert engine.price_at_tick("X", 5) == Decimal("150.0")
        # Quarter
        assert engine.price_at_tick("X", 2) == Decimal("120.0")

    def test_beyond_last_keyframe_holds(self):
        config = TrajectoryConfig(stocks={
            "X": StockTrajectory(keyframes=[[0, 50.0], [5, 80.0]], noise_pct=0),
        })
        engine = PriceEngine(config)

        assert engine.price_at_tick("X", 5) == Decimal("80.0")
        assert engine.price_at_tick("X", 10) == Decimal("80.0")
        assert engine.price_at_tick("X", 100) == Decimal("80.0")


class TestNoise:
    def test_noise_is_bounded(self):
        noise_pct = 0.5
        config = TrajectoryConfig(stocks={
            "X": StockTrajectory(
                keyframes=[[0, 100.0], [100, 100.0]],
                noise_pct=noise_pct,
            ),
        })
        engine = PriceEngine(config, seed=7)

        for tick in range(1, 80):
            price = float(engine.price_at_tick("X", tick))
            lower = 100.0 * (1 - noise_pct / 100)
            upper = 100.0 * (1 + noise_pct / 100)
            assert lower <= price <= upper, f"tick={tick} price={price} out of [{lower}, {upper}]"

    def test_noise_is_deterministic(self):
        config = TrajectoryConfig(stocks={
            "X": StockTrajectory(keyframes=[[0, 100.0], [50, 200.0]], noise_pct=0.3),
        })

        engine_a = PriceEngine(config, seed=99)
        engine_b = PriceEngine(config, seed=99)

        for tick in range(0, 40):
            assert engine_a.price_at_tick("X", tick) == engine_b.price_at_tick("X", tick)


class TestAdvance:
    def test_advance_ticks(self):
        config = TrajectoryConfig(stocks={
            "A": StockTrajectory(keyframes=[[0, 10.0], [10, 20.0]], noise_pct=0),
        })
        engine = PriceEngine(config)

        assert engine.tick_count == 0
        prices = engine.advance(5)
        assert engine.tick_count == 5
        assert prices["A"] == Decimal("15.0")

        prices2 = engine.advance(5)
        assert engine.tick_count == 10
        assert prices2["A"] == Decimal("20.0")


class TestDisabledEngine:
    def test_disabled_engine(self):
        config = TrajectoryConfig(stocks={})
        engine = PriceEngine(config)

        assert engine.enabled is False
        assert engine.tick_by_clock() == {}


# ---------------------------------------------------------------------------
# Tests: cascade_update
# ---------------------------------------------------------------------------

class TestCascadePositions:
    def test_cascade_updates_positions(self):
        stock = _make_stock("AAPL", 150.0)
        state = _make_state(
            stocks=[stock],
            positions=[
                Position(
                    id="pos_1",
                    symbol="AAPL",
                    name="Apple Inc.",
                    asset_type="stock",
                    quantity=Decimal("10"),
                    avg_cost_basis=Decimal("140"),
                    current_price=Decimal("150"),
                    day_change_pct=Decimal("0"),
                    total_return=Decimal("100"),
                    total_return_pct=Decimal("7.14"),
                ),
            ],
            portfolio_value=Decimal("1500"),
        )

        config = TrajectoryConfig(stocks={
            "AAPL": StockTrajectory(keyframes=[[0, 150.0], [10, 170.0]], noise_pct=0),
        })
        engine = PriceEngine(config)

        new_prices = {"AAPL": Decimal("160.00")}
        events = cascade_update(state, new_prices, engine)

        assert len(events) >= 1
        assert state.stocks[0].price == Decimal("160.00")

        pos = state.get_position("AAPL")
        assert pos is not None
        assert pos.current_price == Decimal("160.00")
        # total_return = (160 * 10) - (140 * 10) = 200
        assert pos.total_return == Decimal("200")
        # portfolio_value recalculated
        assert state.portfolio_value == Decimal("1600")


class TestCascadeFillOrders:
    def test_cascade_fills_limit_buy(self):
        stock = _make_stock("TSLA", 200.0)
        state = _make_state(
            stocks=[stock],
            orders=[
                Order(
                    id="ord_1",
                    symbol="TSLA",
                    side="buy",
                    order_type="limit",
                    quantity=Decimal("5"),
                    filled_quantity=Decimal("0"),
                    limit_price=Decimal("190.00"),
                    time_in_force="gtc",
                    status="pending",
                    created_at=utc_now(),
                ),
            ],
        )

        config = TrajectoryConfig(stocks={
            "TSLA": StockTrajectory(keyframes=[[0, 200.0]], noise_pct=0),
        })
        engine = PriceEngine(config)

        # Price drops to 185 — below the 190 limit
        new_prices = {"TSLA": Decimal("185.00")}
        events = cascade_update(state, new_prices, engine)

        order = state.get_order("ord_1")
        assert order is not None
        assert order.status == "filled"
        assert order.filled_quantity == Decimal("5")

        # Cash reduced by limit_price * quantity = 190 * 5 = 950
        assert state.cash_balance == Decimal("5000") - Decimal("950")

        # Position created
        pos = state.get_position("TSLA")
        assert pos is not None
        assert pos.quantity == Decimal("5")

        # Transaction + notification created
        assert any(t.symbol == "TSLA" and t.type == "buy" for t in state.transactions)
        assert any(n.type == "order_fill" for n in state.notifications)

        assert any("fill:" in e for e in events)

    def test_cascade_fills_limit_sell(self):
        stock = _make_stock("MSFT", 300.0)
        state = _make_state(
            stocks=[stock],
            positions=[
                Position(
                    id="pos_1",
                    symbol="MSFT",
                    name="Microsoft Corp.",
                    asset_type="stock",
                    quantity=Decimal("10"),
                    avg_cost_basis=Decimal("280"),
                    current_price=Decimal("300"),
                    day_change_pct=Decimal("0"),
                    total_return=Decimal("200"),
                    total_return_pct=Decimal("7.14"),
                ),
            ],
            orders=[
                Order(
                    id="ord_1",
                    symbol="MSFT",
                    side="sell",
                    order_type="limit",
                    quantity=Decimal("10"),
                    filled_quantity=Decimal("0"),
                    limit_price=Decimal("320.00"),
                    time_in_force="gtc",
                    status="pending",
                    created_at=utc_now(),
                ),
            ],
            portfolio_value=Decimal("3000"),
        )

        config = TrajectoryConfig(stocks={
            "MSFT": StockTrajectory(keyframes=[[0, 300.0]], noise_pct=0),
        })
        engine = PriceEngine(config)

        # Price rises to 325 — above the 320 limit
        new_prices = {"MSFT": Decimal("325.00")}
        events = cascade_update(state, new_prices, engine)

        order = state.get_order("ord_1")
        assert order is not None
        assert order.status == "filled"

        # Cash increased by limit_price * quantity = 320 * 10 = 3200
        assert state.cash_balance == Decimal("5000") + Decimal("3200")

        # Position removed (all shares sold)
        pos = state.get_position("MSFT")
        assert pos is None

        assert any("fill:" in e for e in events)


class TestCascadeAlerts:
    def test_cascade_triggers_price_alert(self):
        stock = _make_stock("NVDA", 500.0)
        state = _make_state(
            stocks=[stock],
            price_alerts=[
                PriceAlert(
                    id="alert_1",
                    symbol="NVDA",
                    condition="above",
                    target_price=Decimal("550.00"),
                    status="active",
                    created_at=utc_now(),
                ),
            ],
        )

        config = TrajectoryConfig(stocks={
            "NVDA": StockTrajectory(keyframes=[[0, 500.0]], noise_pct=0),
        })
        engine = PriceEngine(config)

        # Price jumps above target
        new_prices = {"NVDA": Decimal("560.00")}
        events = cascade_update(state, new_prices, engine)

        alert = state.price_alerts[0]
        assert alert.status == "triggered"
        assert alert.triggered_at is not None

        # Notification created
        assert any(n.type == "price_alert" and "NVDA" in n.title for n in state.notifications)
        assert any("alert:" in e for e in events)
