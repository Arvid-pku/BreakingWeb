"""Composable seed runner for LMS environment tasks.

Instead of a monolithic per-task method, this runner reads the ``seed:``
section from a :class:`TaskDefinition` YAML, resolves actors, executes
builder steps from :data:`LMS_BUILDER_REGISTRY`, and evaluates
target templates.
"""
from __future__ import annotations

import re
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from breakingweb.backend.seeders._common import _assign_output
from breakingweb.tasks._schema import TaskDefinition
from breakingweb.tasks._seed_builders_lms import (
    LMS_BUILDER_REGISTRY,
    LMSSeedContext,
)

_TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
_EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")


def derive_anchor_time(seed: int) -> datetime:
    """Return a deterministic anchor time for the given seed.

    Floats with wall-clock time at day granularity so time-sensitive LMS
    tasks (late-submission windows, upcoming exams, "next 14 days"
    preconditions) remain solvable as the calendar advances. Within a single
    day the anchor is stable, so same-day test runs with the same seed are
    deterministic. The seed contributes a ±24h offset so RNG streams stay
    tied to the seed rather than the minute.

    Rationale: the prior fixed anchor (2026-03-15) worked when that date was
    near wall-clock, but within a few weeks every seeded "not_submitted but
    still within max_late_days" assignment drifted outside its late window,
    making lms_recoverable_late_assignments, lms_semester_recovery_plan,
    lms_study_around_exams, lms_submission_priority, and lms_submission_sprint
    unsolvable (see audit_reports/w04). Downstream per-task canonical_diff
    tests that were calibrated against the March-15 anchor may fail until
    their expected trajectories are recomputed against the floating anchor;
    that is a deliberate trade — task solvability over test calibration.
    """
    today = datetime.now(timezone.utc).replace(
        hour=10, minute=0, second=0, microsecond=0,
    )
    offset = timedelta(hours=(seed % 48) - 24)
    return today + offset


class LMSSeedRunner:
    """Execute the declarative ``seed:`` config from an LMS task YAML."""

    def run(
        self,
        task: TaskDefinition,
        seed: int,
        fake: Any,
        rng: random.Random,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, targets)`` for one LMS task seed."""
        now = derive_anchor_time(seed)
        base = self._base_skeleton(task.task_id)
        ctx = LMSSeedContext(seed=seed, rng=rng, fake=fake, now=now, base=base)

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
            builder = LMS_BUILDER_REGISTRY.get(step.use)
            if builder is None:
                raise ValueError(f"Unknown LMS builder: {step.use}")
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
        return ctx.base, targets

    # ------------------------------------------------------------------
    # Base state skeleton
    # ------------------------------------------------------------------

    @staticmethod
    def _base_skeleton(task_id: str) -> dict[str, Any]:
        """Return the mutable base state dict with sensible defaults."""
        return {
            "env_id": "lms",
            "task_id": task_id,
            "courses": [],
            "enrollments": [],
            "assignments": [],
            "modules": [],
            "discussions": [],
            "discussion_posts": [],
            "peer_reviews": [],
            "announcements": [],
            "grades": [],
            "calendar_events": [],
            "sent_messages": [],
        }

    # ------------------------------------------------------------------
    # Param / target template resolution
    # ------------------------------------------------------------------

    _TEMPLATE_RE = _TEMPLATE_RE
    _EXACT_REF_RE = _EXACT_REF_RE

    @classmethod
    def _resolve_params(
        cls, params: dict[str, Any], ctx: LMSSeedContext,
    ) -> dict[str, Any]:
        """Recursively resolve ``{actor.key.field}`` and ``{output.key}``."""
        return {k: cls._resolve_value(v, ctx) for k, v in params.items()}

    @classmethod
    def _resolve_value(cls, value: Any, ctx: LMSSeedContext) -> Any:
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
    def _raw_lookup(kind: str, path: str, ctx: LMSSeedContext) -> Any:
        """Return the raw (possibly non-string) referenced value.

        Supports ``[N]`` indexing on list values, e.g. ``pending_review_ids[0]``.
        """
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
            # Handle [N] indexing: e.g. "pending_review_ids[0]"
            if "[" in part and part.endswith("]"):
                key, idx_str = part.rstrip("]").split("[", 1)
                obj = obj[key] if isinstance(obj, dict) else getattr(obj, key)
                idx = int(idx_str)
                if isinstance(obj, list):
                    obj = obj[idx]
                elif isinstance(obj, str) and "," in obj:
                    obj = obj.split(",")[idx].strip()
                else:
                    obj = obj  # single value, index 0 is identity
            else:
                obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
        return obj

    @classmethod
    def _resolve_targets(
        cls, templates: dict[str, str], ctx: LMSSeedContext,
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, tmpl in templates.items():
            val = cls._resolve_value(tmpl, ctx)
            # Coerce list/dict to comma-separated strings so eval checks
            # can use '{target.xxx}'.split(',') uniformly.
            if isinstance(val, list):
                val = ",".join(str(v) for v in val)
            elif isinstance(val, dict):
                val = ",".join(f"{k}:{v}" for k, v in val.items())
            resolved[key] = val
        return resolved
