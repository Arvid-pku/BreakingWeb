"""Composable seed runner for Robinhood environment tasks.

Instead of a monolithic per-task method, this runner reads the ``seed:``
section from a :class:`TaskDefinition` YAML, resolves actors, executes
builder steps from :data:`ROBINHOOD_BUILDER_REGISTRY`, and evaluates
target templates.
"""

from __future__ import annotations

import re
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from breakingweb.backend.models.robinhood import AccountSettings
from breakingweb.backend.seeders._common import _assign_output
from breakingweb.tasks._schema import TaskDefinition
from breakingweb.tasks._seed_builders_robinhood import (
    ROBINHOOD_BUILDER_REGISTRY,
    RobinhoodSeedContext,
)

_TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
_EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")


def derive_anchor_time(seed: int) -> datetime:
    """Return a deterministic anchor time anchored to today's UTC date.

    Using today keeps future-dated data (option expirations, upcoming events)
    actually in the future regardless of when the benchmark is run. The seed
    provides per-seed jitter so different seeds don't collide, but the jitter
    is constrained to keep ``anchor.date()`` equal to today's UTC date — a
    ±24h jitter could otherwise push the anchor onto yesterday or tomorrow,
    shifting "in the next N days" boundaries by a full day relative to what
    the human annotator sees on the wall clock (the bug behind seeing
    "5.10 is 7 days after 5.2").
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Jitter only within the same UTC day: 0..23 hours plus 0..59 minutes.
    offset = timedelta(hours=seed % 24, minutes=(seed // 24) % 60)
    return today + offset


class RobinhoodSeedRunner:
    """Execute the declarative ``seed:`` config from a Robinhood task YAML."""

    def run(
        self,
        task: TaskDefinition,
        seed: int,
        fake: Any,
        rng: random.Random,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, targets)`` for one Robinhood task seed."""
        now = derive_anchor_time(seed)
        base = self._base_skeleton(task.task_id)
        ctx = RobinhoodSeedContext(seed=seed, rng=rng, fake=fake, now=now, base=base)

        seed_cfg = task.seed
        if seed_cfg is None:
            return base, {}

        # 1. Resolve actors
        for key, actor_spec in seed_cfg.actors.items():
            ctx.resolve_actor(
                key,
                domain=actor_spec.domain,
                is_vip=actor_spec.is_vip,
                name=actor_spec.name,
            )

        # 2. Execute steps in order
        for step in seed_cfg.steps:
            builder = ROBINHOOD_BUILDER_REGISTRY.get(step.use)
            if builder is None:
                raise ValueError(f"Unknown Robinhood builder: {step.use}")
            resolved_params = self._resolve_params(step.params, ctx)
            result = builder(ctx, resolved_params)
            for out_key in step.outputs:
                if out_key in result:
                    _assign_output(
                        ctx.outputs, out_key, result[out_key],
                        task_id=task.task_id, builder_name=step.use,
                    )

        # 3. Resolve target templates
        targets = self._resolve_targets(seed_cfg.targets, ctx)
        return base, targets

    # ------------------------------------------------------------------
    # Base state skeleton
    # ------------------------------------------------------------------

    @staticmethod
    def _base_skeleton(task_id: str) -> dict[str, Any]:
        """Return the mutable base state dict with sensible defaults."""
        return {
            "env_id": "robinhood",
            "task_id": task_id,
            "owner_name": "Alex Thompson",
            "owner_email": "alex.thompson@thornton.com",
            "account_type": "individual",
            "cash_balance": Decimal("5000.00"),
            "buying_power": Decimal("5000.00"),
            "portfolio_value": Decimal("0"),
            "gold_subscription": False,
            "instant_deposits_limit": Decimal("1000"),
            "day_trade_count": 0,
            "margin_maintenance": Decimal("0"),
            "account_created_at": datetime(2024, 6, 1, tzinfo=timezone.utc),
            "positions": [],
            "orders": [],
            "options_positions": [],
            "options_orders": [],
            "stocks": [],
            "options_chains": {},
            "watchlists": [],
            "transactions": [],
            "transfers": [],
            "linked_banks": [],
            "recurring_investments": [],
            "tax_documents": [],
            "price_alerts": [],
            "notifications": [],
            "earnings_events": [],
            "dividend_schedule": [],
            "settings": AccountSettings(
                id="settings_1",
                display_theme="light",
                default_order_type="market",
                reinvest_dividends=True,
                extended_hours_enabled=False,
                biometric_login=False,
                two_factor_method="none",
                notification_prefs={},
            ),
            "security_log": [],
            "referral_history": [],
        }

    # ------------------------------------------------------------------
    # Param / target template resolution
    # ------------------------------------------------------------------

    _TEMPLATE_RE = _TEMPLATE_RE
    _EXACT_REF_RE = _EXACT_REF_RE

    @classmethod
    def _resolve_params(
        cls, params: dict[str, Any], ctx: RobinhoodSeedContext
    ) -> dict[str, Any]:
        """Recursively resolve ``{actor.key.field}`` and ``{output.key}``."""
        return {k: cls._resolve_value(v, ctx) for k, v in params.items()}

    @classmethod
    def _resolve_value(cls, value: Any, ctx: RobinhoodSeedContext) -> Any:
        if isinstance(value, str):
            exact = cls._EXACT_REF_RE.match(value)
            if exact:
                return cls._raw_lookup(exact.group(1), exact.group(2), ctx)
            return cls._TEMPLATE_RE.sub(
                lambda m: str(cls._raw_lookup(m.group(1), m.group(2), ctx)),
                value,
            )
        if isinstance(value, list):
            return [cls._resolve_value(v, ctx) for v in value]
        if isinstance(value, dict):
            return {k: cls._resolve_value(v, ctx) for k, v in value.items()}
        return value

    @staticmethod
    def _raw_lookup(kind: str, path: str, ctx: RobinhoodSeedContext) -> Any:
        """Return the raw (possibly non-string) referenced value."""
        if kind == "actor":
            parts = path.split(".", 1)
            actor = ctx.actors[parts[0]]
            if len(parts) == 1:
                return actor.name
            return getattr(actor, parts[1])
        # kind == "output"
        parts = path.split(".")
        obj: Any = ctx.outputs
        for part in parts:
            obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
        return obj

    @classmethod
    def _resolve_targets(
        cls, templates: dict[str, str], ctx: RobinhoodSeedContext
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, tmpl in templates.items():
            resolved[key] = cls._resolve_value(tmpl, ctx)
        return resolved
