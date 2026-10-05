"""Tests for Robinhood FastAPI routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from breakingweb.backend.routes.robinhood import router
from breakingweb.backend.state import SessionManager


BASE = "/api/env/robinhood"


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.session_manager = SessionManager()
    return TestClient(app)


@pytest.fixture()
def session_id(client: TestClient) -> str:
    resp = client.post(f"{BASE}/session", json={"task_id": "rh_buy_market_order", "seed": 42})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "session_id" in data
    return data["session_id"]


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def test_create_session(client: TestClient):
    resp = client.post(f"{BASE}/session", json={"task_id": "rh_buy_market_order", "seed": 42})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["start_path"] == "/"
    assert data["title"] == "Buy Shares at Market Price"
    assert data["degradation_active"] is False


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

def test_get_account(client: TestClient, session_id: str):
    resp = client.get(f"{BASE}/account", params={"session_id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert "owner_name" in data
    assert "cash_balance" in data
    assert "counts" in data


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def test_list_positions(client: TestClient, session_id: str):
    resp = client.get(f"{BASE}/positions", params={"session_id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ---------------------------------------------------------------------------
# Orders: market order + fill
# ---------------------------------------------------------------------------

def test_place_market_order_and_fill(client: TestClient, session_id: str):
    # First check we have stocks available
    account = client.get(f"{BASE}/account", params={"session_id": session_id}).json()
    assert float(account["cash_balance"]) > 0

    # Search for a stock to get a valid symbol
    positions = client.get(f"{BASE}/positions", params={"session_id": session_id}).json()

    # Place a market buy — need to find a stock symbol that exists
    # Use the search endpoint or check what stocks exist
    search_resp = client.get(f"{BASE}/search", params={"session_id": session_id, "q": "A"})
    assert search_resp.status_code == 200
    stocks = search_resp.json()["items"]
    if not stocks:
        pytest.skip("No stocks seeded for this task")

    symbol = stocks[0]["symbol"]
    resp = client.post(f"{BASE}/orders", json={
        "session_id": session_id,
        "symbol": symbol,
        "side": "buy",
        "order_type": "market",
        "quantity": "1",
    })
    assert resp.status_code == 200, resp.text
    order = resp.json()["order"]
    assert order["status"] == "filled"
    assert order["symbol"] == symbol
    assert order["filled_quantity"] == "1"

    # Verify position exists now
    pos_resp = client.get(f"{BASE}/positions/{symbol}", params={"session_id": session_id})
    assert pos_resp.status_code == 200


# ---------------------------------------------------------------------------
# Orders: limit order + cancel
# ---------------------------------------------------------------------------

def test_place_limit_order_and_cancel(client: TestClient, session_id: str):
    search_resp = client.get(f"{BASE}/search", params={"session_id": session_id, "q": "A"})
    stocks = search_resp.json()["items"]
    if not stocks:
        pytest.skip("No stocks seeded for this task")

    symbol = stocks[0]["symbol"]
    resp = client.post(f"{BASE}/orders", json={
        "session_id": session_id,
        "symbol": symbol,
        "side": "buy",
        "order_type": "limit",
        "quantity": "1",
        "limit_price": "1.00",
    })
    assert resp.status_code == 200, resp.text
    order = resp.json()["order"]
    assert order["status"] == "pending"
    order_id = order["id"]

    # Cancel it
    cancel_resp = client.post(f"{BASE}/orders/{order_id}/cancel", json={"session_id": session_id})
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["order"]["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Watchlist CRUD
# ---------------------------------------------------------------------------

def test_watchlist_crud(client: TestClient, session_id: str):
    # Create watchlist
    resp = client.post(f"{BASE}/watchlists", json={
        "session_id": session_id,
        "name": "Tech Stocks",
    })
    assert resp.status_code == 200
    wl = resp.json()["watchlist"]
    wl_id = wl["id"]
    assert wl["name"] == "Tech Stocks"

    # Add symbol
    resp = client.post(f"{BASE}/watchlists/{wl_id}/symbols", json={
        "session_id": session_id,
        "symbol": "AAPL",
    })
    assert resp.status_code == 200
    assert "AAPL" in resp.json()["watchlist"]["symbols"]

    # List watchlists
    resp = client.get(f"{BASE}/watchlists", params={"session_id": session_id})
    assert resp.status_code == 200
    found = [w for w in resp.json()["items"] if w["id"] == wl_id]
    assert len(found) == 1


# ---------------------------------------------------------------------------
# Transfers: deposit
# ---------------------------------------------------------------------------

def test_initiate_deposit(client: TestClient, session_id: str):
    # First get banks
    banks_resp = client.get(f"{BASE}/banks", params={"session_id": session_id})
    assert banks_resp.status_code == 200
    banks = banks_resp.json()["items"]
    if not banks:
        # Link a bank first
        link_resp = client.post(f"{BASE}/banks", json={
            "session_id": session_id,
            "bank_name": "Test Bank",
            "account_type": "checking",
            "last_four": "1234",
        })
        assert link_resp.status_code == 200
        bank_id = link_resp.json()["bank"]["id"]
    else:
        bank_id = banks[0]["id"]

    # Initiate deposit
    resp = client.post(f"{BASE}/transfers", json={
        "session_id": session_id,
        "direction": "deposit",
        "amount": "500.00",
        "bank_account_id": bank_id,
    })
    assert resp.status_code == 200
    transfer = resp.json()["transfer"]
    assert transfer["direction"] == "deposit"
    assert transfer["amount"] == "500.00"


# ---------------------------------------------------------------------------
# Price Alerts: create + delete
# ---------------------------------------------------------------------------

def test_create_and_delete_price_alert(client: TestClient, session_id: str):
    resp = client.post(f"{BASE}/alerts", json={
        "session_id": session_id,
        "symbol": "AAPL",
        "condition": "above",
        "target_price": "200.00",
    })
    assert resp.status_code == 200
    alert = resp.json()["alert"]
    alert_id = alert["id"]
    assert alert["symbol"] == "AAPL"
    assert alert["condition"] == "above"
    assert alert["status"] == "active"

    # Delete
    resp = client.delete(f"{BASE}/alerts/{alert_id}", params={"session_id": session_id})
    assert resp.status_code == 200
    assert resp.json()["alert"]["id"] == alert_id

    # Verify it's gone
    resp = client.get(f"{BASE}/alerts", params={"session_id": session_id})
    assert resp.status_code == 200
    assert all(a["id"] != alert_id for a in resp.json()["items"])


# ---------------------------------------------------------------------------
# Notifications: mark read
# ---------------------------------------------------------------------------

def test_mark_notifications_read(client: TestClient, session_id: str):
    # Place a market order to generate a notification
    search_resp = client.get(f"{BASE}/search", params={"session_id": session_id, "q": "A"})
    stocks = search_resp.json()["items"]
    if not stocks:
        pytest.skip("No stocks seeded")

    symbol = stocks[0]["symbol"]
    client.post(f"{BASE}/orders", json={
        "session_id": session_id,
        "symbol": symbol,
        "side": "buy",
        "order_type": "market",
        "quantity": "1",
    })

    # Check notifications
    notifs_resp = client.get(f"{BASE}/notifications", params={"session_id": session_id})
    assert notifs_resp.status_code == 200
    notifs = notifs_resp.json()["items"]

    unread = [n for n in notifs if not n["is_read"]]
    if not unread:
        pytest.skip("No unread notifications")

    # Mark one read
    nid = unread[0]["id"]
    resp = client.post(f"{BASE}/notifications/{nid}/read", json={"session_id": session_id})
    assert resp.status_code == 200
    assert resp.json()["notification"]["is_read"] is True

    # Mark all read
    resp = client.post(f"{BASE}/notifications/read-all", json={"session_id": session_id})
    assert resp.status_code == 200
    assert "marked_count" in resp.json()


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------

def test_evaluate(client: TestClient, session_id: str):
    resp = client.post(f"{BASE}/evaluate", json={
        "session_id": session_id,
        "trajectory": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "success" in data or "score" in data or "checks" in data
