"""Degradation configuration schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


@dataclass
class Injection:
    """A single injection to apply to one layer.

    Layers:
        client  — DOM / interaction mutations (React BenchmarkToolbar).
                  Actions: swap_labels, add_decoy, scramble_aria, hide_affordance,
                  false_banner, set_feature_flag (legacy); click_swallow,
                  adjacent_selection, input_corruption, save_drift,
                  double_submit_trap, restrict_affordance_set,
                  intercepting_overlay, skeleton_never_resolves,
                  distractor_modal, label_input_misalignment.
                  Targets Grounding, Exploration, Verification, Patience.
        network — HTTP interception (middleware + Playwright). Actions: delay
                  (modes: once, intermittent, progressive, tail_latency,
                  correlated_window, write_only_slow), error_then_success,
                  silent_fail, stale_data, misleading_success,
                  concurrent_modification, rate_limit, session_expiry.
                  Targets Patience, Verification, Backtracking.
        server  — State mutations post-seed (Planning, Backtracking).
        seed    — Data-level changes during seeding. Actions include
                  add_confusing_decoys, alias_entities, inject_distractor_emails
                  (legacy) plus env-agnostic inject_adversarial_content and
                  inflate_target_content. Targets State Tracking, Grounding,
                  Planning.
    """

    layer: Literal["client", "network", "server", "seed"]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DegradationConfig:
    """Configuration for a degraded task variant."""

    variant_id: str
    base_task_id: str
    target_primitive: str
    description: str = ""
    injections: list[Injection] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> DegradationConfig:
        with open(path) as f:
            raw = yaml.safe_load(f)
        injections = [
            Injection(layer=inj["layer"], params=inj.get("params", {}))
            for inj in raw.pop("injections", [])
        ]
        return cls(**raw, injections=injections)

    @classmethod
    def default_for_primitive(cls, task_id: str, primitive: str) -> DegradationConfig | None:
        """Return a generic degradation config for a primitive.

        Used when a task has no hand-written variant YAML. The injections are
        task-agnostic network/server actions that stress the target primitive.
        Returns ``None`` for unknown primitives.
        """
        template = _DEFAULT_TEMPLATES.get(primitive)
        if template is None:
            return None
        return cls(
            variant_id=f"{task_id}__{primitive}_auto",
            base_task_id=task_id,
            target_primitive=primitive,
            description=template["description"],
            injections=[
                Injection(layer=inj["layer"], params=dict(inj["params"]))
                for inj in template["injections"]
            ],
        )


# Task-agnostic injection templates per primitive.
# Network-layer actions use URL glob patterns that match any Gmail API route.
_DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "patience": {
        "description": "Progressive API delays (500ms to 4s) plus first email-list call returns 503.",
        "injections": [
            {"layer": "network", "params": {
                "action": "error_then_success",
                "url_pattern": "**/api/env/gmail/emails",
                "methods": ["POST", "PUT", "PATCH", "DELETE"],
                "error_status": 503, "error_count": 1,
                "error_message": "Service temporarily unavailable. The mail server is experiencing high load. Please retry your request in a few seconds.",
                "behavior": {"mode": "once"}}},
            {"layer": "network", "params": {
                "action": "delay",
                "url_pattern": "**/api/env/gmail/**",
                "delay_ms": 2000,
                "behavior": {"mode": "progressive", "stages": [
                    {"after_call": 0, "delay_ms": 500},
                    {"after_call": 5, "delay_ms": 2000},
                    {"after_call": 10, "delay_ms": 4000}]}}},
        ],
    },
    "verification": {
        "description": "First send and first star silently fail (fake 200). Agent must verify outcomes.",
        "injections": [
            {"layer": "network", "params": {
                "action": "silent_fail",
                "url_pattern": "**/api/env/gmail/send",
                "methods": ["POST"],
                "response_body": {"success": True, "email": {"id": "fake", "subject": "sent"}},
                "fail_count": 1,
                "behavior": {"mode": "once"}}},
            {"layer": "network", "params": {
                "action": "silent_fail",
                "url_pattern": "**/api/env/gmail/emails/*/star",
                "methods": ["POST"],
                "response_body": {"email": {"id": "fake", "is_starred": True}},
                "fail_count": 1,
                "behavior": {"mode": "once"}}},
        ],
    },
    "backtracking": {
        "description": "First 2 sends and first label-create return 503. Agent must detect failure and retry.",
        "injections": [
            {"layer": "network", "params": {
                "action": "error_then_success",
                "url_pattern": "**/api/env/gmail/send",
                "methods": ["POST"],
                "error_status": 503, "error_count": 2,
                "error_message": "Failed to send email. The outgoing mail queue is temporarily full. Please retry.",
                "behavior": {"mode": "once"}}},
            {"layer": "network", "params": {
                "action": "error_then_success",
                "url_pattern": "**/api/env/gmail/labels",
                "methods": ["POST"],
                "error_status": 503, "error_count": 1,
                "error_message": "Failed to create label. The label service is temporarily unavailable. Please retry.",
                "behavior": {"mode": "once"}}},
        ],
    },
    "grounding": {
        "description": "First label-create silently fails plus 5 urgent distractor emails in inbox.",
        "injections": [
            {"layer": "network", "params": {
                "action": "silent_fail",
                "url_pattern": "**/api/env/gmail/labels",
                "methods": ["POST"],
                "response_body": {"label": {"id": "fake", "name": "created"}},
                "fail_count": 1,
                "behavior": {"mode": "once"}}},
            {"layer": "server", "params": {
                "action": "inject_distractor_emails",
                "count": 5, "subject_prefix": "URGENT: "}},
        ],
    },
    "state_tracking": {
        "description": "5 distractor emails from same sender plus contacts shuffled.",
        "injections": [
            {"layer": "server", "params": {
                "action": "inject_distractor_emails",
                "count": 5, "subject_prefix": "Re: "}},
            {"layer": "server", "params": {
                "action": "shuffle_contacts", "seed": 42}},
        ],
    },
    "exploration": {
        "description": "First 2 deletes silently fail plus 3 distractor emails.",
        "injections": [
            {"layer": "network", "params": {
                "action": "silent_fail",
                "url_pattern": "**/api/env/gmail/emails/*/delete",
                "methods": ["POST"],
                "response_body": {"email": {"id": "fake", "subject": "deleted"}},
                "fail_count": 2,
                "behavior": {"mode": "once"}}},
            {"layer": "server", "params": {
                "action": "inject_distractor_emails",
                "count": 3, "subject_prefix": "IMPORTANT: "}},
        ],
    },
    "planning": {
        "description": "Scrambled timestamps plus first search returns empty results.",
        "injections": [
            {"layer": "server", "params": {
                "action": "scramble_timestamps", "seed": 77}},
            {"layer": "network", "params": {
                "action": "stale_data",
                "url_pattern": "**/api/env/gmail/search**",
                "stale_body": {"items": [], "total": 0, "page": 1, "page_size": 25, "pages": 1, "query": ""},
                "stale_count": 1,
                "behavior": {"mode": "once"}}},
        ],
    },
}
