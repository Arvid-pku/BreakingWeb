"""Composable seed runner for Gmail environment tasks.

Instead of a monolithic per-task method, this runner reads the ``seed:``
section from a :class:`TaskDefinition` YAML, resolves actors, executes
builder steps from :data:`BUILDER_REGISTRY`, adds distractors, and
evaluates target templates.
"""

from __future__ import annotations

import re
import random
from datetime import timedelta
from typing import Any

from breakingweb.backend.models.gmail import GmailSettings, Label
from breakingweb.backend.seeder import derive_anchor_time
from breakingweb.backend.seeders._common import _assign_output
from breakingweb.tasks._schema import TaskDefinition
from breakingweb.tasks._seed_builders import (
    BUILDER_REGISTRY,
    SeedContext,
)


class GmailSeedRunner:
    """Execute the declarative ``seed:`` config from a Gmail task YAML."""

    def run(
        self, task: TaskDefinition, seed: int, fake: Any, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, targets)`` for one Gmail task seed."""
        now = derive_anchor_time(seed)

        # Build the skeleton base state (labels, settings, empty lists).
        base = self._base_skeleton(task.task_id)

        # Create the context before generating base contacts so fake / rng
        # draws stay stable for deterministic seeds.
        ctx = SeedContext(
            seed=seed,
            rng=rng,
            fake=fake,
            now=now,
            base=base,
        )

        # 10 generic contacts for the baseline mailbox state.
        base["contacts"] = [ctx.contact(is_vip=False) for _ in range(10)]

        seed_cfg = task.seed
        if seed_cfg is None:
            raise ValueError(
                f"Task {task.task_id} has no seed config — cannot run builder pipeline"
            )

        # 1. Resolve actors (order matches YAML dict order → deterministic)
        for key, actor_spec in seed_cfg.actors.items():
            ctx.resolve_actor(
                key,
                domain=actor_spec.domain,
                is_vip=actor_spec.is_vip,
                name=actor_spec.name,
            )

        # 2. Execute steps in order
        for step in seed_cfg.steps:
            builder = BUILDER_REGISTRY.get(step.use)
            if builder is None:
                raise KeyError(
                    f"No builder registered for '{step.use}' "
                    f"(task {task.task_id})"
                )
            resolved_params = self._resolve_params(step.params, ctx)
            result = builder(ctx, resolved_params)
            # Store named outputs
            for out_key in step.outputs:
                if out_key in result:
                    _assign_output(
                        ctx.outputs, out_key, result[out_key],
                        task_id=task.task_id, builder_name=step.use,
                    )

        # 3. Add generic distractors
        self._add_generic_distractors(ctx, count=seed_cfg.distractors)

        # 4. Sort
        base["emails"] = sorted(
            base["emails"], key=lambda e: e.timestamp, reverse=True
        )
        base["contacts"] = sorted(
            base["contacts"], key=lambda c: c.name.lower()
        )

        # 5. Resolve target templates
        targets = self._resolve_targets(seed_cfg.targets, ctx)

        # Remove internal control keys set by seed builders (e.g. _force_distractor_emails_read)
        # that must not reach model_validate since GmailState uses extra="forbid".
        base.pop("_force_distractor_emails_read", None)

        return base, targets

    # ------------------------------------------------------------------
    # Base state skeleton
    # ------------------------------------------------------------------

    @staticmethod
    def _base_skeleton(task_id: str) -> dict[str, Any]:
        """Return the mutable base state dict with system labels and settings.

        Contacts are *not* included here — they are generated later via the
        shared :class:`SeedContext` so that ``fake`` / ``rng`` draws remain
        stable across runs.
        """
        labels = [
            Label(id="label_inbox", name="inbox", color="#202124", system=True),
            Label(id="label_starred", name="starred", color="#fbbc04", system=True),
            Label(id="label_snoozed", name="snoozed", color="#5f6368", system=True),
            Label(id="label_important", name="important", color="#d93025", system=True),
            Label(id="label_sent", name="sent", color="#188038", system=True),
            Label(
                id="label_scheduled",
                name="scheduled",
                color="#5f6368",
                system=True,
                show_in_label_list="show_if_unread",
            ),
            Label(id="label_drafts", name="drafts", color="#5f6368", system=True),
            Label(
                id="label_allmail",
                name="all mail",
                color="#5f6368",
                system=True,
                show_in_label_list="hide",
            ),
            Label(
                id="label_spam",
                name="spam",
                color="#5f6368",
                system=True,
                show_in_label_list="hide",
            ),
            Label(id="label_trash", name="trash", color="#d93025", system=True),
            Label(
                id="label_promotions",
                name="promotions",
                color="#f9ab00",
                system=True,
            ),
            Label(
                id="label_updates",
                name="updates",
                color="#1a73e8",
                system=True,
            ),
            Label(id="label_vip", name="VIP", color="#e37400"),
        ]
        return {
            "env_id": "gmail",
            "task_id": task_id,
            "owner_name": "Avery Quinn",
            "owner_email": "avery.quinn@thornton.com",
            "emails": [],
            "drafts": [],
            "sent": [],
            "deleted": [],
            "contacts": [],
            "labels": labels,
            "filters": [],
            "settings": GmailSettings(
                id="settings_gmail",
                signature="Avery Quinn\nOperations Lead",
                forwarding_address="",
                display_density="comfortable",
                vacation_responder_enabled=False,
                auto_advance="newer",
                language="English (US)",
                input_tools_enabled=True,
                right_to_left=False,
                max_page_size=50,
                undo_send_seconds=5,
                default_reply_behavior="reply",
                hover_actions_enabled=True,
                send_and_archive=False,
                default_text_style="Sans Serif",
            ),
        }

    # ------------------------------------------------------------------
    # Generic distractors for the baseline mailbox state.
    # ------------------------------------------------------------------

    @staticmethod
    def _add_generic_distractors(ctx: SeedContext, count: int) -> None:
        domains = [
            "updates.thornton.com",
            "partners.co",
            "community.io",
            "metrics.thornton.com",
        ]
        subjects = [
            "Agenda draft for Monday check-in",
            "Customer feedback from pilot cohort",
            "Reminder on document review timing",
            "Quarterly metrics recap",
            "Notes from the partner sync",
            "Updated rollout checklist",
            "Follow-up on venue estimate",
            "Revised budget worksheet",
        ]
        for _ in range(count):
            sender_name = ctx.fake.name()
            sender_email = ctx.email_for_name(
                sender_name, domain=ctx.rng.choice(domains)
            )
            subject = ctx.rng.choice(subjects)
            labels = ["inbox"]
            if ctx.rng.random() < 0.25:
                labels.append("updates")
            if ctx.rng.random() < 0.15:
                labels.append("promotions")
            ctx.base["emails"].append(
                ctx.email(
                    from_name=sender_name,
                    from_addr=sender_email,
                    subject=subject,
                    body=ctx.generic_email_body(sender_name),
                    timestamp=ctx.now
                    - timedelta(
                        days=ctx.rng.randint(1, 20),
                        hours=ctx.rng.randint(0, 22),
                    ),
                    thread_id=ctx.next_id("thread"),
                    labels=labels,
                    is_read=True if ctx.base.get("_force_distractor_emails_read") else ctx.rng.random() < 0.5,
                    attachments=(
                        [
                            ctx.attachment(
                                ctx.rng.choice(
                                    ["notes.txt", "summary.txt", "agenda.txt"]
                                ),
                                "text/plain",
                                "text",
                            )
                        ]
                        if ctx.rng.random() < 0.2
                        else []
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Param / target template resolution
    # ------------------------------------------------------------------

    _TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
    # Matches templates that are *exactly* one placeholder with no surrounding text.
    _EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")

    @classmethod
    def _resolve_params(
        cls, params: dict[str, Any], ctx: SeedContext
    ) -> dict[str, Any]:
        """Recursively resolve ``{actor.key.field}`` and ``{output.key}``."""
        return {k: cls._resolve_value(v, ctx) for k, v in params.items()}

    @classmethod
    def _resolve_value(cls, value: Any, ctx: SeedContext) -> Any:
        if isinstance(value, str):
            # If the entire string is exactly one reference, return the raw
            # (possibly non-string) value so lists/dicts survive.
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
    def _raw_lookup(kind: str, path: str, ctx: SeedContext) -> Any:
        """Return the raw (possibly non-string) referenced value."""
        if kind == "actor":
            parts = path.split(".", 1)
            actor = ctx.actors[parts[0]]
            if len(parts) == 1:
                return actor.name
            return getattr(actor, parts[1])
        # kind == "output"
        return ctx.outputs[path]

    @classmethod
    def _resolve_targets(
        cls, templates: dict[str, str], ctx: SeedContext
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, tmpl in templates.items():
            resolved[key] = cls._resolve_value(tmpl, ctx)
        return resolved
