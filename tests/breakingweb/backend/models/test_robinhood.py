"""Tests for Robinhood Pydantic models."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from breakingweb.backend.models.robinhood import (
    AccountSettings,
    Greeks,
    HistoricalPrice,
    LinkedBank,
    Notification,
    OptionsContract,
    OptionsLeg,
    OptionsOrder,
    OptionsPosition,
    Order,
    Position,
    PriceAlert,
    RecurringExecution,
    RecurringInvestment,
    RealizedGainLoss,
    Referral,
    RobinhoodState,
    SecurityEntry,
    Stock,
    TaxDocument,
    TaxLot,
    Transaction,
    Transfer,
    Watchlist,
)


def _make_settings() -> AccountSettings:
    return AccountSettings(
        id="settings_1",
        display_theme="dark",
        default_order_type="market",
        reinvest_dividends=True,
        extended_hours_enabled=False,
        biometric_login=True,
        two_factor_method="sms",
        notification_prefs={"order_fill": True, "price_alert": True},
    )


def _make_state(**overrides) -> RobinhoodState:
    defaults = dict(
        env_id="env_1",
        task_id="task_1",
        owner_name="Jane Doe",
        owner_email="jane@example.com",
        account_type="individual",
        cash_balance=Decimal("10000.00"),
        buying_power=Decimal("10000.00"),
        portfolio_value=Decimal("25000.00"),
        instant_deposits_limit=Decimal("1000.00"),
        margin_maintenance=Decimal("0.00"),
        gold_subscription=False,
        day_trade_count=0,
        account_created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        settings=_make_settings(),
    )
    defaults.update(overrides)
    return RobinhoodState(**defaults)


def _make_stock(symbol: str = "AAPL", name: str = "Apple Inc.", price: str = "175.00") -> Stock:
    return Stock(
        symbol=symbol,
        name=name,
        asset_type="stock",
        price=Decimal(price),
        previous_close=Decimal("173.50"),
        day_change=Decimal("1.50"),
        day_change_pct=Decimal("0.87"),
        bid=Decimal("174.95"),
        ask=Decimal("175.05"),
        bid_size=100,
        ask_size=200,
        volume=50000000,
        avg_volume=60000000,
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("124.17"),
        sector="Technology",
        industry="Consumer Electronics",
        about="Apple Inc. designs, manufactures, and markets smartphones.",
        historical_prices=[],
    )


# ---- Basic model creation ----


class TestPositionCreation:
    def test_position_with_tax_lots(self):
        lot = TaxLot(
            shares=Decimal("10"),
            cost_per_share=Decimal("150.00"),
            acquired_date=date(2023, 6, 15),
        )
        pos = Position(
            id="pos_1",
            symbol="AAPL",
            name="Apple Inc.",
            asset_type="stock",
            quantity=Decimal("10"),
            avg_cost_basis=Decimal("150.00"),
            current_price=Decimal("175.00"),
            day_change_pct=Decimal("0.87"),
            total_return=Decimal("250.00"),
            total_return_pct=Decimal("16.67"),
            lots=[lot],
        )
        assert pos.symbol == "AAPL"
        assert pos.quantity == Decimal("10")
        assert len(pos.lots) == 1
        assert pos.lots[0].cost_per_share == Decimal("150.00")


class TestOrderCreation:
    def test_market_buy_order(self):
        order = Order(
            id="ord_1",
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("5"),
            filled_quantity=Decimal("0"),
            time_in_force="gfd",
            status="pending",
            extended_hours=False,
            created_at=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
        )
        assert order.side == "buy"
        assert order.order_type == "market"
        assert order.limit_price is None
        assert order.stop_price is None


class TestStockCreation:
    def test_stock_fields(self):
        stock = _make_stock()
        assert stock.symbol == "AAPL"
        assert stock.price == Decimal("175.00")
        assert stock.pe_ratio is None
        assert stock.dividend_yield is None
        assert stock.historical_prices == []


class TestRobinhoodStateCreation:
    def test_basic_state(self):
        state = _make_state()
        assert state.owner_name == "Jane Doe"
        assert state.cash_balance == Decimal("10000.00")
        assert state.positions == []
        assert state.orders == []
        assert state.settings.display_theme == "dark"


# ---- Mutation methods ----


class TestPlaceOrder:
    def test_market_buy(self):
        stock = _make_stock()
        state = _make_state(stocks=[stock])
        order = state.place_order(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
        )
        assert order.status == "filled"
        assert order.filled_quantity == Decimal("10")
        assert order.filled_at is not None

        # Cash should decrease by price * quantity
        expected_cost = Decimal("175.00") * Decimal("10")
        assert state.cash_balance == Decimal("10000.00") - expected_cost
        assert state.buying_power == Decimal("10000.00") - expected_cost

        # Position should be created
        pos = state.get_position("AAPL")
        assert pos is not None
        assert pos.quantity == Decimal("10")

        # Transaction should be created
        assert len(state.transactions) == 1
        assert state.transactions[0].type == "buy"

        # Notification should be created
        assert len(state.notifications) == 1

    def test_market_sell(self):
        stock = _make_stock()
        pos = Position(
            id="pos_1",
            symbol="AAPL",
            name="Apple Inc.",
            asset_type="stock",
            quantity=Decimal("20"),
            avg_cost_basis=Decimal("150.00"),
            current_price=Decimal("175.00"),
            day_change_pct=Decimal("0.87"),
            total_return=Decimal("500.00"),
            total_return_pct=Decimal("16.67"),
            lots=[],
        )
        state = _make_state(stocks=[stock], positions=[pos])
        order = state.place_order(
            symbol="AAPL",
            side="sell",
            order_type="market",
            quantity=Decimal("5"),
        )
        assert order.status == "filled"
        assert state.cash_balance == Decimal("10000.00") + Decimal("175.00") * Decimal("5")
        assert state.get_position("AAPL").quantity == Decimal("15")

    def test_limit_order_stays_pending(self):
        stock = _make_stock()
        state = _make_state(stocks=[stock])
        order = state.place_order(
            symbol="AAPL",
            side="buy",
            order_type="limit",
            quantity=Decimal("10"),
            limit_price=Decimal("170.00"),
        )
        assert order.status == "pending"
        assert order.filled_quantity == Decimal("0")
        # Cash should NOT change for pending limit orders
        assert state.cash_balance == Decimal("10000.00")


class TestCancelOrder:
    def test_cancel_pending_order(self):
        stock = _make_stock()
        state = _make_state(stocks=[stock])
        order = state.place_order(
            symbol="AAPL",
            side="buy",
            order_type="limit",
            quantity=Decimal("10"),
            limit_price=Decimal("170.00"),
        )
        cancelled = state.cancel_order(order.id)
        assert cancelled.status == "cancelled"
        assert cancelled.cancelled_at is not None

    def test_cancel_filled_order_raises(self):
        stock = _make_stock()
        state = _make_state(stocks=[stock])
        order = state.place_order(
            symbol="AAPL",
            side="buy",
            order_type="market",
            quantity=Decimal("1"),
        )
        with pytest.raises(ValueError):
            state.cancel_order(order.id)


class TestWatchlist:
    def test_create_and_add(self):
        state = _make_state()
        wl = state.create_watchlist("Tech", ["AAPL", "GOOG"])
        assert wl.name == "Tech"
        assert wl.symbols == ["AAPL", "GOOG"]

        wl2 = state.add_to_watchlist(wl.id, "MSFT")
        assert "MSFT" in wl2.symbols
        assert len(wl2.symbols) == 3

    def test_remove_from_watchlist(self):
        state = _make_state()
        wl = state.create_watchlist("Tech", ["AAPL", "GOOG", "MSFT"])
        wl2 = state.remove_from_watchlist(wl.id, "GOOG")
        assert "GOOG" not in wl2.symbols
        assert len(wl2.symbols) == 2


class TestTransfer:
    def test_deposit(self):
        bank = LinkedBank(
            id="bank_1",
            bank_name="Chase",
            account_type="checking",
            last_four="1234",
            status="verified",
            is_default=True,
        )
        state = _make_state(linked_banks=[bank])
        transfer = state.initiate_transfer(
            direction="deposit",
            amount=Decimal("500.00"),
            bank_account_id="bank_1",
        )
        assert transfer.status == "pending"
        assert transfer.amount == Decimal("500.00")
        assert state.cash_balance == Decimal("10500.00")
        assert state.buying_power == Decimal("10500.00")
        assert len(state.transactions) == 1
        assert state.transactions[0].type == "deposit"

    def test_withdrawal(self):
        bank = LinkedBank(
            id="bank_1",
            bank_name="Chase",
            account_type="checking",
            last_four="1234",
            status="verified",
            is_default=True,
        )
        state = _make_state(linked_banks=[bank])
        transfer = state.initiate_transfer(
            direction="withdrawal",
            amount=Decimal("2000.00"),
            bank_account_id="bank_1",
        )
        assert state.cash_balance == Decimal("8000.00")


class TestNotifications:
    def test_mark_read(self):
        notif = Notification(
            id="notif_1",
            type="order_fill",
            title="Order Filled",
            message="Your order for AAPL was filled.",
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            is_read=False,
        )
        state = _make_state(notifications=[notif])
        updated = state.mark_notification_read("notif_1")
        assert updated.is_read is True

    def test_mark_all_read(self):
        notifs = [
            Notification(
                id=f"notif_{i}",
                type="order_fill",
                title=f"Notification {i}",
                message=f"Message {i}",
                timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
                is_read=False,
            )
            for i in range(3)
        ]
        state = _make_state(notifications=notifs)
        count = state.mark_all_notifications_read()
        assert count == 3
        assert all(n.is_read for n in state.notifications)

    def test_unread_notifications(self):
        notifs = [
            Notification(
                id="notif_1",
                type="order_fill",
                title="N1",
                message="M1",
                timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
                is_read=False,
            ),
            Notification(
                id="notif_2",
                type="price_alert",
                title="N2",
                message="M2",
                timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
                is_read=True,
            ),
        ]
        state = _make_state(notifications=notifs)
        unread = state.unread_notifications()
        assert len(unread) == 1
        assert unread[0].id == "notif_1"


class TestPriceAlert:
    def test_create_price_alert(self):
        state = _make_state()
        alert = state.create_price_alert("AAPL", "above", Decimal("200.00"))
        assert alert.symbol == "AAPL"
        assert alert.condition == "above"
        assert alert.target_price == Decimal("200.00")
        assert alert.status == "active"
        assert len(state.price_alerts) == 1


class TestListTransactions:
    def test_filter_by_type(self):
        txns = [
            Transaction(
                id="txn_1",
                type="buy",
                symbol="AAPL",
                quantity=Decimal("10"),
                amount=Decimal("1750.00"),
                description="Bought AAPL",
                timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ),
            Transaction(
                id="txn_2",
                type="dividend",
                symbol="AAPL",
                quantity=None,
                amount=Decimal("5.00"),
                description="Dividend from AAPL",
                timestamp=datetime(2024, 2, 15, tzinfo=timezone.utc),
            ),
            Transaction(
                id="txn_3",
                type="deposit",
                symbol=None,
                quantity=None,
                amount=Decimal("1000.00"),
                description="Bank deposit",
                timestamp=datetime(2024, 3, 1, tzinfo=timezone.utc),
            ),
        ]
        state = _make_state(transactions=txns)

        buys = state.list_transactions(type="buy")
        assert len(buys) == 1
        assert buys[0].id == "txn_1"

    def test_filter_by_symbol(self):
        txns = [
            Transaction(
                id="txn_1",
                type="buy",
                symbol="AAPL",
                quantity=Decimal("10"),
                amount=Decimal("1750.00"),
                description="Bought AAPL",
                timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ),
            Transaction(
                id="txn_2",
                type="buy",
                symbol="GOOG",
                quantity=Decimal("5"),
                amount=Decimal("700.00"),
                description="Bought GOOG",
                timestamp=datetime(2024, 1, 16, tzinfo=timezone.utc),
            ),
        ]
        state = _make_state(transactions=txns)
        result = state.list_transactions(symbol="AAPL")
        assert len(result) == 1

    def test_filter_by_date_range(self):
        txns = [
            Transaction(
                id="txn_1",
                type="buy",
                symbol="AAPL",
                quantity=Decimal("10"),
                amount=Decimal("1750.00"),
                description="Bought AAPL",
                timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
            ),
            Transaction(
                id="txn_2",
                type="buy",
                symbol="GOOG",
                quantity=Decimal("5"),
                amount=Decimal("700.00"),
                description="Bought GOOG",
                timestamp=datetime(2024, 6, 15, tzinfo=timezone.utc),
            ),
        ]
        state = _make_state(transactions=txns)
        result = state.list_transactions(
            from_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            to_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        )
        assert len(result) == 1
        assert result[0].id == "txn_1"


class TestSearchStocks:
    def test_search_by_symbol(self):
        stocks = [_make_stock("AAPL", "Apple Inc."), _make_stock("AMZN", "Amazon.com Inc.")]
        state = _make_state(stocks=stocks)
        result = state.search_stocks("AAPL")
        assert len(result) == 1
        assert result[0].symbol == "AAPL"

    def test_search_by_name(self):
        stocks = [_make_stock("AAPL", "Apple Inc."), _make_stock("AMZN", "Amazon.com Inc.")]
        state = _make_state(stocks=stocks)
        result = state.search_stocks("amazon")
        assert len(result) == 1
        assert result[0].symbol == "AMZN"

    def test_search_no_match(self):
        stocks = [_make_stock("AAPL", "Apple Inc.")]
        state = _make_state(stocks=stocks)
        result = state.search_stocks("TSLA")
        assert len(result) == 0


class TestSessionSummary:
    def test_summary(self):
        stock = _make_stock()
        pos = Position(
            id="pos_1",
            symbol="AAPL",
            name="Apple Inc.",
            asset_type="stock",
            quantity=Decimal("10"),
            avg_cost_basis=Decimal("150.00"),
            current_price=Decimal("175.00"),
            day_change_pct=Decimal("0.87"),
            total_return=Decimal("250.00"),
            total_return_pct=Decimal("16.67"),
            lots=[],
        )
        state = _make_state(stocks=[stock], positions=[pos])
        summary = state.session_summary()
        assert summary["owner_name"] == "Jane Doe"
        assert summary["counts"]["positions"] == 1
        assert summary["counts"]["stocks"] == 1
