"""Tests for price trajectory economic validation."""

from __future__ import annotations

from breakingweb.backend.price_engine import StockTrajectory, TrajectoryConfig
from breakingweb.backend.price_validation import validate_trajectory


def _cfg(stocks: dict[str, StockTrajectory]) -> TrajectoryConfig:
    return TrajectoryConfig(stocks=stocks)


# ── Passing ──────────────────────────────────────────────────────────────

def test_valid_trajectory_passes():
    config = _cfg({
        "AAPL": StockTrajectory(
            keyframes=[[0, 150.0], [10, 152.0], [20, 153.0]],
            noise_pct=0.3,
        ),
    })
    assert validate_trajectory(config) == []


# ── Failing ──────────────────────────────────────────────────────────────

def test_negative_price_fails():
    config = _cfg({
        "AAPL": StockTrajectory(keyframes=[[0, -5.0]], noise_pct=0.3),
    })
    errors = validate_trajectory(config)
    assert len(errors) == 1
    assert "non-positive price" in errors[0]
    assert "AAPL" in errors[0]


def test_excessive_per_tick_change_fails():
    # $100 -> $50 in 1 tick = 50% change per tick
    config = _cfg({
        "TSLA": StockTrajectory(
            keyframes=[[0, 100.0], [1, 50.0]],
            noise_pct=0.3,
        ),
    })
    errors = validate_trajectory(config)
    assert any("per-tick change" in e and "TSLA" in e for e in errors)


def test_non_monotonic_ticks_fails():
    config = _cfg({
        "GOOG": StockTrajectory(
            keyframes=[[0, 100.0], [10, 101.0], [5, 102.0]],
            noise_pct=0.3,
        ),
    })
    errors = validate_trajectory(config)
    assert any("not strictly increasing" in e and "GOOG" in e for e in errors)


def test_excessive_noise_fails():
    config = _cfg({
        "MSFT": StockTrajectory(keyframes=[[0, 300.0]], noise_pct=5.0),
    })
    errors = validate_trajectory(config)
    assert len(errors) == 1
    assert "noise_pct" in errors[0]
    assert "MSFT" in errors[0]


def test_no_keyframes_fails():
    config = _cfg({
        "AMZN": StockTrajectory(keyframes=[], noise_pct=0.3),
    })
    errors = validate_trajectory(config)
    assert len(errors) == 1
    assert "at least one keyframe" in errors[0]
    assert "AMZN" in errors[0]


def test_zero_price_fails():
    config = _cfg({
        "META": StockTrajectory(keyframes=[[0, 0]], noise_pct=0.3),
    })
    errors = validate_trajectory(config)
    assert any("non-positive price" in e and "META" in e for e in errors)
