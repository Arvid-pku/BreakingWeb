"""Tests for the upgraded `hide_prerequisite` / `hide_watchlist` server actions.

The actions accept a `prerequisites: [{kind, name}, …]` list so a single
Planning task can force the agent to recreate multiple missing pieces.
"""

from __future__ import annotations

from types import SimpleNamespace

from breakingweb.injector.server import apply_server_injection


def _gmail_state(*, labels=(), contacts=(), filters=()):
    return SimpleNamespace(
        labels=[SimpleNamespace(name=name) for name in labels],
        contacts=[SimpleNamespace(name=name, email=f"{name.replace(' ', '.').lower()}@x.co") for name in contacts],
        filters=[SimpleNamespace(name=name, query=name) for name in filters],
    )


def _rh_state(*, watchlists=(), settings_dict=None):
    return SimpleNamespace(
        watchlists=[SimpleNamespace(name=name) for name in watchlists],
        settings=dict(settings_dict or {"position_threshold_alert_pct": 5}),
    )


# ---------------------------------------------------------------------------
# Multi-prerequisite hide for Gmail (label + contact + filter)
# ---------------------------------------------------------------------------

def test_hide_prerequisite_removes_label_contact_and_filter() -> None:
    state = _gmail_state(
        labels=["Delegated", "Personal"],
        contacts=["Delegate Owner", "Other Contact"],
        filters=["delegated-inbound", "spam-bucket"],
    )
    apply_server_injection(state, {
        "action": "hide_prerequisite",
        "prerequisites": [
            {"kind": "label", "name": "Delegated"},
            {"kind": "contact", "name": "Delegate Owner"},
            {"kind": "filter", "name": "delegated-inbound"},
        ],
    })
    assert [lab.name for lab in state.labels] == ["Personal"]
    assert [c.name for c in state.contacts] == ["Other Contact"]
    assert [f.name for f in state.filters] == ["spam-bucket"]


def test_hide_prerequisite_legacy_label_name_still_works() -> None:
    """The pre-upgrade `label_name: Foo` shape stays functional."""
    state = _gmail_state(labels=["Delegated", "Personal"])
    apply_server_injection(state, {"action": "hide_prerequisite", "label_name": "Delegated"})
    assert [lab.name for lab in state.labels] == ["Personal"]


# ---------------------------------------------------------------------------
# Multi-prerequisite hide for RH (watchlist + setting)
# ---------------------------------------------------------------------------

def test_hide_watchlist_removes_watchlist_and_clears_setting() -> None:
    state = _rh_state(
        watchlists=["My First List", "Other List"],
        settings_dict={"position_threshold_alert_pct": 5},
    )
    apply_server_injection(state, {
        "action": "hide_watchlist",
        "prerequisites": [
            {"kind": "watchlist", "name": "My First List"},
            {"kind": "setting", "key": "position_threshold_alert_pct", "default": None},
        ],
    })
    assert [w.name for w in state.watchlists] == ["Other List"]
    assert state.settings["position_threshold_alert_pct"] is None


def test_hide_watchlist_legacy_watchlist_name_still_works() -> None:
    state = _rh_state(watchlists=["My First List", "Other List"])
    apply_server_injection(state, {"action": "hide_watchlist", "watchlist_name": "My First List"})
    assert [w.name for w in state.watchlists] == ["Other List"]


# ---------------------------------------------------------------------------
# corrupt_state — multi-field + swap
# ---------------------------------------------------------------------------

def test_corrupt_state_supports_multiple_fields() -> None:
    e1 = SimpleNamespace(id="e1", subject="A", body="A-body")
    e2 = SimpleNamespace(id="e2", subject="B", body="B-body")
    state = SimpleNamespace(emails=[e1, e2])
    apply_server_injection(state, {
        "action": "corrupt_state",
        "corruptions": [
            {"email_id": "e1", "field": "subject", "value": "MUTATED"},
            {"email_id": "e2", "field": "body", "value": "ALSO-MUTATED"},
        ],
    })
    assert e1.subject == "MUTATED"
    assert e2.body == "ALSO-MUTATED"


def test_corrupt_state_swap_exchanges_fields_between_records() -> None:
    e1 = SimpleNamespace(id="e1", subject="Real subject", from_name="Alice")
    e2 = SimpleNamespace(id="e2", subject="Wrong subject", from_name="Bob")
    state = SimpleNamespace(emails=[e1, e2])
    apply_server_injection(state, {
        "action": "corrupt_state",
        "swap": {"email_id_a": "e1", "email_id_b": "e2", "fields": ["subject", "from_name"]},
    })
    # After swap, each record holds the other's former values — both are
    # still type-correct strings, so nothing dangles as a placeholder.
    assert e1.subject == "Wrong subject"
    assert e1.from_name == "Bob"
    assert e2.subject == "Real subject"
    assert e2.from_name == "Alice"


# ---------------------------------------------------------------------------
# corrupt_state — RH (positions / orders) extension
# ---------------------------------------------------------------------------

def test_corrupt_state_swaps_quantity_between_two_positions() -> None:
    p1 = SimpleNamespace(id="pos_1", symbol="AAPL", quantity=10, avg_cost_basis=180)
    p2 = SimpleNamespace(id="pos_2", symbol="MSFT", quantity=20, avg_cost_basis=400)
    state = SimpleNamespace(positions=[p1, p2])
    apply_server_injection(state, {
        "action": "corrupt_state",
        "swap": {
            "target": "positions",
            "target_id_a": "pos_1",
            "target_id_b": "pos_2",
            "fields": ["quantity"],
        },
    })
    # Both positions still have valid integer quantities — totals balance,
    # but the assignment is now wrong.
    assert p1.quantity == 20
    assert p2.quantity == 10
    # Costs unchanged.
    assert p1.avg_cost_basis == 180
    assert p2.avg_cost_basis == 400


def test_corrupt_state_multi_corruptions_on_orders() -> None:
    o1 = SimpleNamespace(id="ord_1", symbol="AAPL", limit_price=180, status="pending")
    o2 = SimpleNamespace(id="ord_2", symbol="MSFT", limit_price=400, status="pending")
    state = SimpleNamespace(orders=[o1, o2])
    apply_server_injection(state, {
        "action": "corrupt_state",
        "corruptions": [
            {"target": "orders", "target_id": "ord_1", "field": "limit_price", "value": 999},
            {"target": "orders", "target_id": "ord_2", "field": "status", "value": "cancelled"},
        ],
    })
    assert o1.limit_price == 999
    assert o2.status == "cancelled"
