"""Tests for Robinhood seed builders."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from breakingweb.tasks._seed_builders_robinhood import (
    ROBINHOOD_BUILDER_REGISTRY,
    RobinhoodSeedContext,
    _STOCK_SEED_DATA,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(seed: int = 42) -> RobinhoodSeedContext:
    """Create a RobinhoodSeedContext with deterministic seed."""
    rng = random.Random(seed)
    fake = MagicMock()
    fake.name.return_value = "Jordan Baker"
    fake.domain_word.return_value = "example"
    now = datetime(2025, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    base: dict = {
        "owner_name": "Alex Thompson",
        "owner_email": "alex.thompson@thornton.com",
        "stocks": [],
        "positions": [],
        "orders": [],
        "watchlists": [],
        "linked_banks": [],
        "options_positions": [],
        "options_orders": [],
        "options_chains": {},
        "recurring_investments": [],
        "transfers": [],
        "transactions": [],
        "tax_documents": [],
        "price_alerts": [],
        "notifications": [],
        "earnings_events": [],
        "dividend_schedule": [],
        "security_log": [],
        "cash_balance": Decimal("10000"),
        "buying_power": Decimal("10000"),
        "portfolio_value": Decimal("0"),
    }
    return RobinhoodSeedContext(seed=seed, rng=rng, fake=fake, now=now, base=base)


def _ensure_stock_universe(ctx: RobinhoodSeedContext, count: int = 30, must_include: list[str] | None = None) -> None:
    """Build stock universe as a prerequisite."""
    builder = ROBINHOOD_BUILDER_REGISTRY["stock_universe"]
    builder(ctx, {"count": count, "must_include": must_include or []})


# ---------------------------------------------------------------------------
# Test: stock seed data completeness
# ---------------------------------------------------------------------------

def test_stock_seed_data_has_at_least_80_entries():
    assert len(_STOCK_SEED_DATA) >= 80


def test_stock_seed_data_covers_all_sectors():
    sectors = {sd["sector"] for sd in _STOCK_SEED_DATA}
    expected = {"Technology", "Healthcare", "Financial", "Energy", "Industrial", "ETF"}
    assert expected.issubset(sectors), f"Missing sectors: {expected - sectors}"


# ---------------------------------------------------------------------------
# Test: stock_universe builder
# ---------------------------------------------------------------------------

def test_stock_universe_generates_correct_count():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=20)
    assert len(ctx.base["stocks"]) == 20


def test_stock_universe_must_include():
    ctx = _make_ctx()
    must = ["AAPL", "MSFT", "TSLA"]
    _ensure_stock_universe(ctx, count=10, must_include=must)
    symbols = {s.symbol for s in ctx.base["stocks"]}
    for sym in must:
        assert sym in symbols, f"{sym} not in stock universe despite must_include"


def test_stock_universe_deterministic():
    ctx1 = _make_ctx(seed=99)
    _ensure_stock_universe(ctx1, count=15)
    ctx2 = _make_ctx(seed=99)
    _ensure_stock_universe(ctx2, count=15)

    prices1 = [(s.symbol, s.price) for s in ctx1.base["stocks"]]
    prices2 = [(s.symbol, s.price) for s in ctx2.base["stocks"]]
    assert prices1 == prices2


def test_stock_universe_historical_prices():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=5)
    for stock in ctx.base["stocks"]:
        assert len(stock.historical_prices) == 90
        # Dates should be in order
        dates = [h.date for h in stock.historical_prices]
        assert dates == sorted(dates)


def test_stock_universe_etf_asset_type():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=80, must_include=["SPY", "QQQ", "VTI"])
    spy = next(s for s in ctx.base["stocks"] if s.symbol == "SPY")
    assert spy.asset_type == "etf"
    aapl = next((s for s in ctx.base["stocks"] if s.symbol == "AAPL"), None)
    if aapl:
        assert aapl.asset_type == "stock"


# ---------------------------------------------------------------------------
# Test: portfolio_basic builder
# ---------------------------------------------------------------------------

def test_portfolio_basic_creates_positions():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=30, must_include=["AAPL", "MSFT", "GOOGL"])

    builder = ROBINHOOD_BUILDER_REGISTRY["portfolio_basic"]
    result = builder(ctx, {
        "stocks": ["AAPL", "MSFT", "GOOGL"],
        "quantities": ["10", "5", "20"],
        "cost_bases": ["150.00", "380.00", "140.00"],
    })

    assert len(result["position_ids"]) == 3
    assert len(ctx.base["positions"]) == 3

    aapl_pos = next(p for p in ctx.base["positions"] if p.symbol == "AAPL")
    assert aapl_pos.quantity == Decimal("10")
    assert aapl_pos.avg_cost_basis == Decimal("150.00")
    assert len(aapl_pos.lots) == 1


# ---------------------------------------------------------------------------
# Test: linked_banks builder
# ---------------------------------------------------------------------------

def test_linked_banks_first_is_default():
    ctx = _make_ctx()
    builder = ROBINHOOD_BUILDER_REGISTRY["linked_banks"]
    result = builder(ctx, {
        "banks": [
            {"name": "Chase Checking", "type": "checking", "last_four": "4521"},
            {"name": "Wells Fargo Savings", "type": "savings", "last_four": "7890"},
        ],
    })

    assert len(result["bank_ids"]) == 2
    assert len(ctx.base["linked_banks"]) == 2

    first = ctx.base["linked_banks"][0]
    second = ctx.base["linked_banks"][1]
    assert first.is_default is True
    assert second.is_default is False
    assert first.bank_name == "Chase Checking"
    assert second.last_four == "7890"


# ---------------------------------------------------------------------------
# Test: watchlist builder
# ---------------------------------------------------------------------------

def test_watchlist_creates_with_correct_symbols():
    ctx = _make_ctx()
    builder = ROBINHOOD_BUILDER_REGISTRY["watchlist"]
    result = builder(ctx, {
        "name": "Tech Favorites",
        "symbols": ["AAPL", "MSFT", "GOOGL", "NVDA"],
    })

    assert "watchlist_id" in result
    assert len(ctx.base["watchlists"]) == 1
    wl = ctx.base["watchlists"][0]
    assert wl.name == "Tech Favorites"
    assert wl.symbols == ["AAPL", "MSFT", "GOOGL", "NVDA"]


# ---------------------------------------------------------------------------
# Test: pending_orders builder
# ---------------------------------------------------------------------------

def test_pending_orders_creates_correct_count():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=30)

    builder = ROBINHOOD_BUILDER_REGISTRY["pending_orders"]
    result = builder(ctx, {"count": 5})

    assert len(result["order_ids"]) == 5
    assert len(ctx.base["orders"]) == 5
    for order in ctx.base["orders"]:
        assert order.status == "pending"
        assert order.filled_quantity == Decimal("0")


# ---------------------------------------------------------------------------
# Test: notifications builder
# ---------------------------------------------------------------------------

def test_notifications_unread_ratio():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=30)

    builder = ROBINHOOD_BUILDER_REGISTRY["notifications"]
    builder(ctx, {"count": 10, "unread_ratio": 0.3})

    assert len(ctx.base["notifications"]) == 10
    unread = [n for n in ctx.base["notifications"] if not n.is_read]
    # unread_count = round(10 * 0.3) = 3
    assert len(unread) == 3


def test_notifications_all_unread():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=10)

    builder = ROBINHOOD_BUILDER_REGISTRY["notifications"]
    builder(ctx, {"count": 5, "unread_ratio": 1.0})

    unread = [n for n in ctx.base["notifications"] if not n.is_read]
    assert len(unread) == 5


# ---------------------------------------------------------------------------
# Test: registry completeness
# ---------------------------------------------------------------------------

def test_registry_has_all_20_builders():
    expected = {
        "stock_universe", "portfolio_basic", "portfolio_diverse",
        "pending_orders", "filled_orders", "watchlist", "linked_banks",
        "options_chain", "options_positions", "complex_options_book",
        "recurring_investments", "transfers_history", "transaction_ledger",
        "tax_documents", "price_alerts", "notifications",
        "earnings_calendar", "dividend_schedule", "security_log",
        "margin_account",
    }
    assert expected == set(ROBINHOOD_BUILDER_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Test: context helpers
# ---------------------------------------------------------------------------

def test_next_id_monotonic():
    ctx = _make_ctx()
    assert ctx.next_id("pos") == "pos_1"
    assert ctx.next_id("pos") == "pos_2"
    assert ctx.next_id("ord") == "ord_1"


def test_resolve_actor_cached():
    ctx = _make_ctx()
    a1 = ctx.resolve_actor("ceo", name="Alice Smith")
    a2 = ctx.resolve_actor("ceo")
    assert a1 is a2
    assert a1.name == "Alice Smith"
    assert a1.first_name == "Alice"


def test_pick_symbols():
    ctx = _make_ctx()
    _ensure_stock_universe(ctx, count=20)
    syms = ctx.pick_symbols(5)
    assert len(syms) == 5
    all_syms = {s.symbol for s in ctx.base["stocks"]}
    for s in syms:
        assert s in all_syms
