"""Tests for the Robinhood seed runner and registration."""

from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest


def test_seeder_registered():
    """RobinhoodSeedRunner is present in SEEDER_REGISTRY."""
    from breakingweb.backend.seeders import SEEDER_REGISTRY

    assert "robinhood" in SEEDER_REGISTRY


def test_state_type_registered():
    """RobinhoodState is present in STATE_TYPES."""
    from breakingweb.backend.state import STATE_TYPES

    assert "robinhood" in STATE_TYPES


def test_robinhood_seeder_runs():
    """Seeder can run a simple Robinhood task end-to-end."""
    from breakingweb.backend.seeders.robinhood import RobinhoodSeedRunner
    from breakingweb.tasks._registry import get_task

    runner = RobinhoodSeedRunner()
    task = get_task("rh_buy_market_order")
    seed = 42
    rng = random.Random(seed)
    fake = MagicMock()
    fake.name.return_value = "Jordan Baker"
    fake.domain_word.return_value = "example"

    base, targets = runner.run(task, seed, fake, rng)

    assert base["env_id"] == "robinhood"
    assert base["task_id"] == "rh_buy_market_order"
    assert len(base["stocks"]) > 0
    assert any(s.symbol == "AAPL" for s in base["stocks"])
    assert targets["symbol"] == "AAPL"


def test_robinhood_seeder_validates_with_model():
    """Seeded data can be validated by RobinhoodState model."""
    from breakingweb.backend.models.robinhood import RobinhoodState
    from breakingweb.backend.seeders.robinhood import RobinhoodSeedRunner
    from breakingweb.tasks._registry import get_task

    runner = RobinhoodSeedRunner()
    task = get_task("rh_enable_extended_hours")
    seed = 42
    rng = random.Random(seed)
    fake = MagicMock()
    fake.name.return_value = "Jordan Baker"
    fake.domain_word.return_value = "example"

    base, _targets = runner.run(task, seed, fake, rng)
    state = RobinhoodState.model_validate(base)

    assert state.env_id == "robinhood"
    assert state.settings.extended_hours_enabled is False
