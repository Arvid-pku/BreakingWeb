"""Helpers for task-oriented BreakingWeb result artifacts.

The active benchmark is environment/task based, but older result files may
still use page-era field names such as ``page_id`` or ``page_meta``.  This
module keeps backwards-compatible readers in one place so the active runtime
can write task-centric artifacts without duplicating fallback logic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def result_task_id(result: Mapping[str, Any]) -> str:
    """Return the canonical task id from a result object."""
    task_id = result.get("task_id") or result.get("page_id")
    if not isinstance(task_id, str) or not task_id:
        raise KeyError("Result is missing task_id")
    return task_id


def summary_total_tasks(summary: Mapping[str, Any]) -> int:
    """Return the total task count, supporting legacy result artifacts."""
    total = summary.get("total_tasks", summary.get("total_pages", 0))
    return int(total) if total is not None else 0


def build_manifest_task_meta(manifest: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Extract per-task metadata from a manifest."""
    task_meta: dict[str, dict[str, Any]] = {}
    if manifest is None:
        return task_meta

    for env in manifest.get("environments", []):
        if not isinstance(env, Mapping):
            continue
        env_meta = {key: value for key, value in env.items() if key != "tasks"}
        for task in env.get("tasks", []):
            if not isinstance(task, Mapping):
                continue
            task_id = task.get("task_id")
            if isinstance(task_id, str) and task_id:
                task_meta[task_id] = {**env_meta, **task}
    return task_meta


def load_embedded_task_meta(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Load task metadata from either new or legacy result payload keys."""
    raw_meta = data.get("task_meta") or data.get("page_meta") or {}
    if not isinstance(raw_meta, Mapping):
        return {}

    task_meta: dict[str, dict[str, Any]] = {}
    for task_id, meta in raw_meta.items():
        if isinstance(task_id, str) and isinstance(meta, Mapping):
            task_meta[task_id] = dict(meta)
    return task_meta


def merge_result_task_meta(
    base_meta: Mapping[str, dict[str, Any]] | None,
    results: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Overlay result-local metadata onto manifest-derived task metadata."""
    merged = {task_id: dict(meta) for task_id, meta in (base_meta or {}).items()}

    for result in results:
        task_id = result_task_id(result)
        merged[task_id] = {
            **merged.get(task_id, {}),
            "task_id": result.get("task_id", task_id),
            "task_type": result.get("task_type", "env"),
            "title": result.get("title"),
            "instruction": result.get("instruction"),
            "difficulty": result.get("difficulty"),
            "env_id": result.get("env_id"),
            "base_url": result.get("base_url") or result.get("replay", {}).get("base_url"),
            "start_path": result.get("replay", {}).get("start_path"),
            "replay": result.get("replay"),
        }

    return merged
