"""Composable seed runner for Patient Portal environment tasks.

Instead of a monolithic per-task method, this runner reads the ``seed:``
section from a :class:`TaskDefinition` YAML, resolves actors, executes
builder steps from :data:`PATIENT_PORTAL_BUILDER_REGISTRY`, and evaluates
target templates.
"""

from __future__ import annotations

import re
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from breakingweb.backend.seeders._common import _assign_output
from breakingweb.tasks._schema import TaskDefinition
from breakingweb.tasks._seed_builders_patient_portal import (
    PATIENT_PORTAL_BUILDER_REGISTRY,
    PatientPortalSeedContext,
)

_TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
_EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")


def derive_anchor_time(seed: int) -> datetime:
    """Return a deterministic anchor time anchored to today's UTC date.

    Using today keeps future-dated appointments (upcoming_count) actually
    in the future regardless of when the benchmark is run.  The seed
    provides a ±24-hour jitter so different seeds don't collide.
    """
    today = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    offset = timedelta(hours=(seed % 48) - 24)
    return today + offset


class PatientPortalSeedRunner:
    """Execute the declarative ``seed:`` config from a Patient Portal task YAML."""

    def run(
        self,
        task: TaskDefinition,
        seed: int,
        fake: Any,
        rng: random.Random,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, targets)`` for one Patient Portal task seed."""
        now = derive_anchor_time(seed)
        base = self._base_skeleton(task.task_id)
        ctx = PatientPortalSeedContext(seed=seed, rng=rng, fake=fake, now=now, base=base)

        seed_cfg = task.seed
        if seed_cfg is None:
            return base, {}

        # 1. Resolve actors (if any)
        for key, actor_spec in seed_cfg.actors.items():
            ctx.resolve_actor(
                key,
                domain=actor_spec.domain,
                is_vip=actor_spec.is_vip,
                name=actor_spec.name,
            )

        # 2. Execute steps in dependency order
        for step in seed_cfg.steps:
            builder = PATIENT_PORTAL_BUILDER_REGISTRY.get(step.use)
            if builder is None:
                raise ValueError(f"Unknown Patient Portal builder: {step.use}")
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
            "env_id": "patient_portal",
            "task_id": task_id,
            "patient": {},
            "providers": [],
            "appointments": [],
            "prescriptions": [],
            "lab_results": [],
            "messages": [],
            "referrals": [],
            "claims": [],
            "immunizations": [],
            "pharmacies": [],
        }

    # ------------------------------------------------------------------
    # Param / target template resolution
    # ------------------------------------------------------------------

    _TEMPLATE_RE = _TEMPLATE_RE
    _EXACT_REF_RE = _EXACT_REF_RE

    @classmethod
    def _resolve_params(
        cls, params: dict[str, Any], ctx: PatientPortalSeedContext
    ) -> dict[str, Any]:
        """Recursively resolve ``{actor.key.field}`` and ``{output.key}``."""
        return {k: cls._resolve_value(v, ctx) for k, v in params.items()}

    @classmethod
    def _resolve_value(cls, value: Any, ctx: PatientPortalSeedContext) -> Any:
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
    def _raw_lookup(kind: str, path: str, ctx: PatientPortalSeedContext) -> Any:
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
            if isinstance(obj, dict):
                obj = obj[part]
            elif isinstance(obj, list) and part.isdigit():
                obj = obj[int(part)]
            else:
                obj = getattr(obj, part)
        return obj

    @classmethod
    def _resolve_targets(
        cls, templates: dict[str, str], ctx: PatientPortalSeedContext
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, tmpl in templates.items():
            resolved[key] = cls._resolve_value(tmpl, ctx)
        return resolved
