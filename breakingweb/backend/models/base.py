from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def diff_dict_of_dicts(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    id_label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return added, removed, and modified records for two dict-of-dicts snapshots."""
    before = before or {}
    after = after or {}

    added = [
        {id_label: key, **after[key]}
        for key in sorted(set(after) - set(before))
    ]
    removed = [
        {id_label: key, **before[key]}
        for key in sorted(set(before) - set(after))
    ]

    modified: list[dict[str, Any]] = []
    for key in sorted(set(before) & set(after)):
        before_item = before[key]
        after_item = after[key]
        changes = {
            field: {"before": before_item.get(field), "after": after_item.get(field)}
            for field in sorted(set(before_item) | set(after_item))
            if before_item.get(field) != after_item.get(field)
        }
        if changes:
            modified.append({id_label: key, "changes": changes})

    return added, removed, modified


class BaseEntity(BaseModel):
    id: str

    model_config = ConfigDict(extra="forbid")


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ChatMessage(BaseModel):
    """An agent-produced chat message recorded in state.chat.

    Role is typically 'assistant' (send_msg_to_user) or 'infeasible'
    (report_infeasible). Content is the raw message string.
    """
    role: str
    content: str
    timestamp: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(extra="forbid")


class BaseEnvState(BaseModel):
    # Top-level fields the canonical_diff system should NOT walk: framework
    # bookkeeping (env/task ids, timestamps), event logs (audit, chat), and
    # other metadata that mutates on every request. Subclasses extend this
    # tuple to silence env-specific noise (id_counters, password_hash, etc.).
    DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]] = (
        "env_id", "task_id", "created_at", "updated_at",
        "audit_log", "benchmark_state", "chat",
    )

    env_id: str
    task_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    audit_log: list[AuditEntry] = Field(default_factory=list)
    benchmark_state: dict[str, Any] = Field(default_factory=dict)
    chat: list[ChatMessage] = Field(default_factory=list)
    _resolved_targets: dict[str, Any] = PrivateAttr(default_factory=dict)
    _seed: int | None = PrivateAttr(default=None)
    _degradation: dict[str, Any] = PrivateAttr(default_factory=dict)
    _initial_snapshot: dict[str, Any] | None = PrivateAttr(default=None)
    # Post-seed deep-copy of this state (for canonical_diff evaluation).
    # Set by ``SessionManager.create_session``. Distinct from the legacy
    # ``_initial_snapshot`` dict which is populated at eval-time via
    # ``state_snapshot()`` for collateral-damage detection.
    _initial_state_copy: "BaseEnvState | None" = PrivateAttr(default=None)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def set_benchmark_state(self, benchmark_state: dict[str, Any]) -> None:
        self.benchmark_state = benchmark_state
        self.touch()

    @property
    def resolved_targets(self) -> dict[str, Any]:
        return dict(self._resolved_targets)

    @property
    def seed(self) -> int | None:
        return self._seed

    @property
    def degradation(self) -> dict[str, Any]:
        return dict(self._degradation)

    @property
    def initial_snapshot(self) -> dict[str, Any] | None:
        return self._initial_snapshot
