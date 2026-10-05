"""Economic validation for Robinhood price trajectory configs."""

from __future__ import annotations

from breakingweb.backend.price_engine import TrajectoryConfig


_MAX_PER_TICK_CHANGE_PCT = 2.0
_MAX_NOISE_PCT = 1.0


def validate_trajectory(config: TrajectoryConfig) -> list[str]:
    """Validate a TrajectoryConfig against economic plausibility rules.

    Returns a list of human-readable error strings (empty means valid).
    """
    errors: list[str] = []

    for symbol, traj in config.stocks.items():
        keyframes = traj.keyframes

        # 1. Must have at least one keyframe
        if not keyframes:
            errors.append(f"{symbol}: must have at least one keyframe")
            continue

        # 2. Monotonic ticks & 3. No negative/zero prices
        prev_tick: float | None = None
        for kf in keyframes:
            tick, price = kf[0], kf[1]
            if price <= 0:
                errors.append(
                    f"{symbol}: keyframe at tick {tick} has non-positive "
                    f"price {price}"
                )
            if prev_tick is not None and tick <= prev_tick:
                errors.append(
                    f"{symbol}: tick {tick} is not strictly increasing "
                    f"after tick {prev_tick}"
                )
            prev_tick = tick

        # 4. Max per-tick change <= 2%
        for i in range(1, len(keyframes)):
            t0, p0 = keyframes[i - 1]
            t1, p1 = keyframes[i]
            dt = t1 - t0
            if dt <= 0 or p0 <= 0:
                continue  # already reported above
            per_tick_pct = abs(p1 - p0) / p0 * 100.0 / dt
            if per_tick_pct > _MAX_PER_TICK_CHANGE_PCT:
                errors.append(
                    f"{symbol}: per-tick change between tick {t0} and "
                    f"tick {t1} is {per_tick_pct:.2f}% (max {_MAX_PER_TICK_CHANGE_PCT}%)"
                )

        # 5. Noise bound <= 1.0%
        if traj.noise_pct > _MAX_NOISE_PCT:
            errors.append(
                f"{symbol}: noise_pct is {traj.noise_pct}% "
                f"(max {_MAX_NOISE_PCT}%)"
            )

    return errors
