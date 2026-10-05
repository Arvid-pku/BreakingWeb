"""Tests for Robinhood task YAML loading and seeding."""

from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest

from breakingweb.backend.models.robinhood import RobinhoodState
from breakingweb.backend.seeders.robinhood import RobinhoodSeedRunner
from breakingweb.tasks._registry import load_all_tasks, get_task


EXPECTED_RH_EASY_TASKS = [
    "rh_buy_market_order",
    "rh_sell_shares",
    "rh_add_to_watchlist",
    "rh_cancel_pending_order",
    "rh_create_watchlist",
    "rh_set_price_alert",
    "rh_mark_notifications_read",
    "rh_check_buying_power",
    "rh_enable_extended_hours",
    "rh_deposit_funds",
]

EXPECTED_RH_MEDIUM_TASKS = [
    "rh_limit_order_with_check",
    "rh_deposit_then_buy",
    "rh_compare_dividend_yields",
    "rh_setup_recurring_investment",
    "rh_review_and_cancel_orders",
    "rh_transfer_and_withdraw",
    "rh_find_earnings_and_alert",
    "rh_sell_loser_buy_winner",
    "rh_options_buy_call",
    "rh_security_audit",
    "rh_live_buy_the_dip",
    "rh_live_take_profit",
    "rh_live_alert_and_buy",
    "rh_live_alert_and_sell",
    "rh_live_watch_and_buy",
]

EXPECTED_RH_HARD_TASKS = [
    "rh_portfolio_rebalance",
    "rh_covered_call_strategy",
    "rh_dividend_income_report",
    "rh_wash_sale_avoidance",
    "rh_cost_basis_reconciliation",
    "rh_options_chain_analysis",
    "rh_consolidate_recurring",
    "rh_notification_triage",
    "rh_sector_concentration",
    "rh_transfer_history_audit",
    "rh_live_stop_loss_execution",
    "rh_live_dual_alert_decision",
    "rh_live_watch_portfolio",
    "rh_live_watch_spread",
]

EXPECTED_RH_EXPERT_TASKS = [
    "rh_multi_leg_options",
    "rh_tax_optimization",
    "rh_portfolio_risk_assessment",
    "rh_earnings_play_setup",
    "rh_dividend_reinvestment_analysis",
    "rh_margin_call_resolution",
    "rh_watchlist_screening",
    "rh_recurring_optimization",
    "rh_cross_reference_1099",
    "rh_options_roll_strategy",
    "rh_live_bracket_order",
    "rh_live_alert_chain",
    "rh_live_intraday_reversal",
]

EXPECTED_RH_FRONTIER_TASKS = [
    "rh_full_portfolio_rebalance_with_tax",
    "rh_options_income_portfolio",
    "rh_year_end_tax_planning",
    "rh_suspicious_activity_investigation",
    "rh_complex_transfer_reconciliation",
    "rh_portfolio_transition",
    "rh_options_expiration_management",
    "rh_complete_account_audit",
    "rh_multi_strategy_execution",
    "rh_quarterly_performance_review",
    "rh_live_multi_stock_limits",
    "rh_live_cross_stock_alert",
    "rh_live_comparative_watch",
]

EXPECTED_RH_TASKS = (
    EXPECTED_RH_EASY_TASKS
    + EXPECTED_RH_MEDIUM_TASKS
    + EXPECTED_RH_HARD_TASKS
    + EXPECTED_RH_EXPERT_TASKS
    + EXPECTED_RH_FRONTIER_TASKS
)


def test_all_robinhood_tasks_load():
    """All rh_ tasks load with correct env_id and difficulty."""
    all_tasks = load_all_tasks()

    difficulty_map = {}
    for t in EXPECTED_RH_EASY_TASKS:
        difficulty_map[t] = "easy"
    for t in EXPECTED_RH_MEDIUM_TASKS:
        difficulty_map[t] = "medium"
    for t in EXPECTED_RH_HARD_TASKS:
        difficulty_map[t] = "hard"
    for t in EXPECTED_RH_EXPERT_TASKS:
        difficulty_map[t] = "expert"
    for t in EXPECTED_RH_FRONTIER_TASKS:
        difficulty_map[t] = "frontier"

    for task_id in EXPECTED_RH_TASKS:
        assert task_id in all_tasks, f"Task {task_id} not found in registry"
        task = all_tasks[task_id]
        assert task.env_id == "robinhood", f"{task_id} has wrong env_id: {task.env_id}"
        assert task.difficulty == difficulty_map[task_id], f"{task_id} has wrong difficulty: {task.difficulty}"
        assert task.task_id == task_id
        assert len(task.primary_primitives) > 0, f"{task_id} has no primary primitives"


@pytest.mark.parametrize("task_id", EXPECTED_RH_TASKS)
def test_all_robinhood_tasks_seed(task_id: str):
    """Each rh_ task can be seeded with seed=42 and produces valid state."""
    runner = RobinhoodSeedRunner()
    task = get_task(task_id)
    seed = 42
    rng = random.Random(seed)
    fake = MagicMock()
    fake.name.return_value = "Jordan Baker"
    fake.domain_word.return_value = "example"

    base, targets = runner.run(task, seed, fake, rng)

    # Validate the base state against the Pydantic model
    state = RobinhoodState.model_validate(base)
    assert state.env_id == "robinhood"
    assert state.task_id == task_id

    # Verify canonical_diff exists (the runtime evaluation format)
    assert task.canonical_diff is not None, f"{task_id} has no canonical_diff"


def test_all_live_task_trajectories_valid():
    """Every task with price_trajectory must pass economic validation."""
    from breakingweb.backend.price_validation import validate_trajectory
    from breakingweb.backend.price_engine import TrajectoryConfig, StockTrajectory

    all_tasks = load_all_tasks()
    rh_tasks = {k: v for k, v in all_tasks.items() if k.startswith("rh_")}
    live_count = 0

    for task_id, task in rh_tasks.items():
        if task.seed is None:
            continue
        pt = getattr(task.seed, "price_trajectory", None)
        if pt is None:
            continue
        live_count += 1
        config = TrajectoryConfig(
            tick_interval_seconds=pt.tick_interval_seconds,
            stocks={
                sym: StockTrajectory(keyframes=ts.keyframes, noise_pct=ts.noise_pct)
                for sym, ts in pt.stocks.items()
            },
        )
        errors = validate_trajectory(config)
        assert not errors, f"{task_id} trajectory validation failed: {errors}"

    assert live_count == 15, f"Expected 15 live tasks, found {live_count}"
