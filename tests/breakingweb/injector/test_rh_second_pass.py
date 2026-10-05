"""Sanity assertions for the second-pass RH intervention upgrades.

The 41 RH "both opus and sonnet pass intervention" tasks each got one
targeted yaml addition designed to introduce a verification trap, an
on-path decoy, or a stacked-write trap. This test guards against those
additions silently regressing.

The expected file changes are encoded as: each variant must contain
*at least one* injection matching the listed (action, optional methods,
optional url_pattern_substring) signature. We don't assert exact
parameter values — just that the upgrade-shape is present.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

VARIANT_DIR = Path(__file__).resolve().parents[3] / "breakingweb/injector/variants"


# Each entry: (variant_filename, [list of required signatures]).
# A signature is matched by `action` and (optionally) substring-match on
# `url_pattern` and inclusion in `methods`.
EXPECTED: list[tuple[str, list[dict]]] = [
    # Lever A — misleading_success on retry-style writes.
    ("rh_check_buying_power__trade_retry.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_sell_loser_buy_winner__trade_retry.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_sell_shares__trade_retry.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_deposit_funds__transfer_retry.yaml", [{"action": "misleading_success", "url": "/transfers"}]),
    ("rh_deposit_then_buy__transfer_retry.yaml", [{"action": "misleading_success", "url": "/transfers"}]),
    ("rh_transfer_and_withdraw__transfer_retry.yaml", [{"action": "misleading_success", "url": "/transfers"}]),
    ("rh_security_audit__security_retry.yaml", [{"action": "misleading_success", "url": "/security/2fa"}]),
    ("rh_setup_recurring_investment__recurring_retry.yaml", [{"action": "misleading_success", "url": "/recurring"}]),
    ("rh_mark_notifications_read__notification_retry.yaml", [{"action": "misleading_success", "url": "/notifications"}]),

    # Lever B — misleading_success on cancels.
    ("rh_cancel_pending_order__order_noise.yaml", [{"action": "misleading_success", "url": "/cancel"}]),
    ("rh_fix_duplicate_orders__same_symbol_different_qty.yaml", [{"action": "misleading_success", "url": "/cancel"}]),
    ("rh_review_and_cancel_orders__near_threshold_noise.yaml", [{"action": "misleading_success", "url": "/cancel"}]),

    # Lever C — live tasks.
    ("rh_live_buy_the_dip__quote_delay.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_take_profit__quote_delay.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_alert_and_buy__misleading_notif.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_alert_and_sell__misleading_notif.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_bracket_order__grounding_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_dual_alert_decision__grounding_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_intraday_reversal__patience_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_watch_spread__grounding_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_cross_stock_alert__exploration_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),

    # Lever D — ticker_twin variants get a fired alert.
    ("rh_add_to_watchlist__ticker_twin.yaml", [{"action": "add_misleading_alert"}]),
    ("rh_compare_dividend_yields__ticker_twin.yaml", [{"action": "add_misleading_alert"}]),
    ("rh_create_watchlist__ticker_twin.yaml", [{"action": "add_misleading_alert"}]),
    ("rh_limit_order_with_check__ticker_twin.yaml", [{"action": "add_misleading_alert"}]),
    ("rh_set_price_alert__ticker_twin.yaml", [{"action": "add_misleading_alert"}]),
    ("rh_watchlist_organize__ticker_twin.yaml", [{"action": "add_misleading_alert"}]),
    ("rh_tax_loss_harvest__replacement_etf_twin.yaml", [{"action": "add_misleading_alert"}]),

    # Planning + state_tracking + remaining.
    ("rh_consolidate_recurring__planning_v1.yaml", [
        {"action": "add_misleading_alert"},
        {"action": "misleading_success", "url": "/recurring"},
    ]),
    ("rh_portfolio_rebalance__planning_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_margin_call_resolution__planning_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_multi_stock_limits__planning_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_live_alert_chain__state_tracking_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_suspicious_activity_investigation__state_tracking_v1.yaml", [{"action": "misleading_success", "url": "/cancel"}]),
    ("rh_wash_sale_avoidance__state_tracking_v1.yaml", [{"action": "misleading_success", "url": "/orders"}]),
    ("rh_transfer_history_audit__state_tracking_v1.yaml", [{"action": "scramble_order_timestamps"}]),
    ("rh_enable_extended_hours__settings_retry.yaml", [{"action": "stale_data", "url": "/settings"}]),
    ("rh_earnings_play_setup__exploration_v1.yaml", [{"action": "add_misleading_alert"}]),
    ("rh_verify_no_action_needed__drop_notice.yaml", [{"action": "inject_distractor_notifications"}]),
    ("rh_buy_market_order__adjacent_selection.yaml", [{"action": "save_drift"}]),
    ("rh_sector_concentration__planning_v1.yaml", [{"action": "add_confusing_positions"}]),
]


def _signature_match(inj_params: dict, sig: dict) -> bool:
    if inj_params.get("action") != sig["action"]:
        return False
    url_substr = sig.get("url")
    if url_substr is not None:
        url_pattern = inj_params.get("url_pattern", "")
        if url_substr not in url_pattern:
            return False
    methods = sig.get("methods")
    if methods is not None:
        inj_methods = set(inj_params.get("methods", []))
        if not set(methods).issubset(inj_methods):
            return False
    return True


@pytest.mark.parametrize("variant_filename,sigs", EXPECTED)
def test_second_pass_upgrades_present(variant_filename: str, sigs: list[dict]) -> None:
    path = VARIANT_DIR / variant_filename
    assert path.exists(), f"variant file missing: {variant_filename}"
    data = yaml.safe_load(path.read_text())
    injections = (data or {}).get("injections") or []
    params_list = [(inj or {}).get("params", {}) for inj in injections]
    for sig in sigs:
        assert any(_signature_match(p, sig) for p in params_list), (
            f"{variant_filename}: missing expected upgrade signature {sig}. "
            f"Current actions: {[p.get('action') for p in params_list]}"
        )


def test_second_pass_covers_41_distinct_variants() -> None:
    """Sanity: the expected list covers a meaningful slice of the both-pass set."""
    distinct = {entry[0] for entry in EXPECTED}
    assert len(distinct) >= 40, (
        f"Second-pass coverage shrank to {len(distinct)} variants — "
        "expected ≥ 40."
    )
