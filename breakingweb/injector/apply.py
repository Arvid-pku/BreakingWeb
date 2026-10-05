"""Orchestrate injection application across all three layers."""

from __future__ import annotations

from typing import Any

from .config import DegradationConfig


def apply_seed_degradations(
    config: DegradationConfig,
    server_state: Any,
    *,
    rng: Any = None,
) -> None:
    """Apply seed-layer injections (synchronous, called during session creation).

    This modifies the *data* the agent will read — email content, contacts,
    information distribution. Must be called after normal seeding but before
    the agent starts.
    """
    for injection in config.injections:
        if injection.layer == "seed":
            from .seed import apply_seed_injection

            apply_seed_injection(server_state, injection.params, rng=rng)
        elif injection.layer == "server":
            from .server import apply_server_injection

            apply_server_injection(server_state, injection.params)


async def apply_degradation(
    config: DegradationConfig,
    *,
    page: Any = None,
    server_state: Any = None,
    rng: Any = None,
) -> None:
    """Apply all injections from a degradation config.

    Args:
        config: The degradation configuration.
        page: Playwright page (required for client/network injections).
        server_state: Environment state (required for server/seed injections).
        rng: Random number generator for seed injections.

    Seed and server injections are applied synchronously.
    Client and network injections are applied via async Playwright APIs.
    """
    for injection in config.injections:
        if injection.layer == "seed" and server_state is not None:
            from .seed import apply_seed_injection

            apply_seed_injection(server_state, injection.params, rng=rng)
        elif injection.layer == "client" and page is not None:
            from .client import apply_client_injection

            await apply_client_injection(page, injection.params)
        elif injection.layer == "network" and page is not None:
            from .network import apply_network_injection

            await apply_network_injection(page, injection.params)
        elif injection.layer == "server" and server_state is not None:
            from .server import apply_server_injection

            apply_server_injection(server_state, injection.params)
