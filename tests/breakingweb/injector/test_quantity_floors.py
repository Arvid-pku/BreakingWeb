"""Quantity-floor assertions for Gmail/RH variants — guard the difficulty bumps.

Two distinct tests:

1. **Multiplier applied** — every Gmail/RH variant that uses one of the
   multiplier-aware seed actions has either `multiplier >= 2` OR a `count`
   knob whose value is at least the post-bump minimum (so the upgrade can't
   silently regress to 1× quantities).

2. **Network delay within budget** — `delay_ms` for any single network
   call ≤ 35% of the per-task `time_limit_seconds`. Prevents accidentally
   exceeding the task time budget when bumping latency.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

VARIANT_DIR = Path(__file__).resolve().parents[3] / "breakingweb/injector/variants"

# Multiplier-aware seed actions with the post-bump count floor: variants
# that use a `count: N` knob (rather than a hand-typed list) must have
# N ≥ this value, OR variants with hand-typed lists must declare
# multiplier ≥ 2.
SEED_ACTION_COUNT_FLOORS: dict[str, int] = {
    "add_confusing_decoys": 4,
    "alias_entities": 4,
    "add_decoy_notifications": 4,
    "add_noise_orders": 4,
    "add_confusing_positions": 4,
    "add_confusing_stocks": 4,
}

# Same idea for the server-layer count-only injectors.
SERVER_ACTION_COUNT_FLOORS: dict[str, int] = {
    "inject_distractor_emails": 5,         # was median 5–10 → bumped 1.5×
    "inject_distractor_notifications": 5,  # similar median
}

# increase_distractors floor (after 1.5× bump, originally 8–35).
INCREASE_DISTRACTORS_FLOOR = 8


def _gmail_rh_variants() -> list[Path]:
    return sorted(
        list(VARIANT_DIR.glob("gmail_*.yaml")) + list(VARIANT_DIR.glob("rh_*.yaml"))
    )


def _list_for_action(action: str, params: dict) -> list | None:
    """Return the hand-typed list parameter for an action, if any."""
    candidate_keys = {
        "add_confusing_decoys": ("decoys",),
        "alias_entities": ("aliases", "entities"),
        "add_decoy_notifications": ("decoys", "notifications", "messages"),
        "add_noise_orders": ("orders",),
        "add_confusing_positions": ("positions",),
        "add_confusing_stocks": ("decoys", "stocks"),
    }
    for key in candidate_keys.get(action, ()):
        val = params.get(key)
        if isinstance(val, list):
            return val
    return None


@pytest.mark.parametrize("variant_path", _gmail_rh_variants(), ids=lambda p: p.name)
def test_multiplier_or_bumped_count_present(variant_path: Path) -> None:
    """For multiplier-aware actions, multiplier ≥ 2 or count meets floor."""
    with open(variant_path) as f:
        data = yaml.safe_load(f)
    for inj in (data or {}).get("injections") or []:
        params = (inj or {}).get("params") or {}
        action = params.get("action")
        if action not in SEED_ACTION_COUNT_FLOORS:
            continue
        multiplier = params.get("multiplier", 1)
        count = params.get("count")
        hand_list = _list_for_action(action, params)

        if isinstance(count, int):
            assert count >= SEED_ACTION_COUNT_FLOORS[action], (
                f"{variant_path.name}: action {action!r} count={count} below "
                f"floor {SEED_ACTION_COUNT_FLOORS[action]}"
            )
            continue

        if hand_list:
            assert isinstance(multiplier, int) and multiplier >= 2, (
                f"{variant_path.name}: action {action!r} has a hand-typed "
                f"list of {len(hand_list)} entries but multiplier={multiplier!r} "
                "(expected ≥ 2)."
            )
            continue

        # Falls through: no list, no count. The variant probably uses
        # symbols/messages/etc. — skip without failing.


@pytest.mark.parametrize("variant_path", _gmail_rh_variants(), ids=lambda p: p.name)
def test_server_distractor_counts_meet_floor(variant_path: Path) -> None:
    with open(variant_path) as f:
        data = yaml.safe_load(f)
    for inj in (data or {}).get("injections") or []:
        params = (inj or {}).get("params") or {}
        action = params.get("action")
        if action not in SERVER_ACTION_COUNT_FLOORS:
            continue
        count = params.get("count")
        if count is None:
            # Some variants omit count and rely on the default; skip.
            continue
        assert isinstance(count, int) and count >= SERVER_ACTION_COUNT_FLOORS[action], (
            f"{variant_path.name}: server action {action!r} count={count} "
            f"below floor {SERVER_ACTION_COUNT_FLOORS[action]}"
        )


@pytest.mark.parametrize("variant_path", _gmail_rh_variants(), ids=lambda p: p.name)
def test_increase_distractors_count_meets_floor(variant_path: Path) -> None:
    with open(variant_path) as f:
        data = yaml.safe_load(f)
    for inj in (data or {}).get("injections") or []:
        params = (inj or {}).get("params") or {}
        if params.get("action") != "increase_distractors":
            continue
        count = params.get("count")
        if count is None:
            continue
        assert isinstance(count, int) and count >= INCREASE_DISTRACTORS_FLOOR, (
            f"{variant_path.name}: increase_distractors count={count} below "
            f"floor {INCREASE_DISTRACTORS_FLOOR}"
        )


# ---------------------------------------------------------------------------
# Network knob bounds: delays must not exceed the per-task budget margin.
# ---------------------------------------------------------------------------

def _task_time_limits() -> dict[str, int]:
    out: dict[str, int] = {}
    repo_root = Path(__file__).resolve().parents[3]
    for kind in ("gmail", "robinhood"):
        for path in (repo_root / "breakingweb/tasks" / kind).glob("*.yaml"):
            try:
                with open(path) as f:
                    raw = yaml.safe_load(f)
                tid = raw.get("task_id")
                tl = raw.get("time_limit_seconds")
                if tid and isinstance(tl, int):
                    out[tid] = tl
            except Exception:
                continue
    return out


def _max_delay_ms(params: dict) -> int:
    largest = int(params.get("delay_ms", 0) or 0)
    behavior = params.get("behavior") or {}
    if isinstance(behavior, dict):
        for stage in behavior.get("stages") or []:
            if isinstance(stage, dict):
                d = int(stage.get("delay_ms", 0) or 0)
                if d > largest:
                    largest = d
        for key in ("p99_ms", "p95_ms", "p50_ms", "slow_ms"):
            d = int(behavior.get(key, 0) or 0)
            if d > largest:
                largest = d
    return largest


@pytest.mark.parametrize("variant_path", _gmail_rh_variants(), ids=lambda p: p.name)
def test_network_delay_within_budget(variant_path: Path) -> None:
    """`delay_ms` for any single network call ≤ 35% of task time_limit."""
    time_limits = _task_time_limits()
    with open(variant_path) as f:
        data = yaml.safe_load(f)
    base_task_id = (data or {}).get("base_task_id", "")
    if base_task_id not in time_limits:
        pytest.skip(f"no time_limit for base_task_id={base_task_id!r}")
    budget_ms = time_limits[base_task_id] * 1000
    max_allowed = int(budget_ms * 0.35)
    for inj in (data or {}).get("injections") or []:
        params = (inj or {}).get("params") or {}
        if params.get("action") != "delay":
            continue
        worst = _max_delay_ms(params)
        assert worst <= max_allowed, (
            f"{variant_path.name}: delay_ms {worst} exceeds 35% of "
            f"time_limit ({budget_ms} ms → cap {max_allowed} ms)"
        )
