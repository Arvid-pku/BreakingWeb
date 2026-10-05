"""Task discovery, loading, validation, and indexing.

All YAML files under this package directory are loaded and validated and
cached, with the cache invalidated whenever any task YAML's mtime changes —
so editing a task during a dev session reflects on the next session-create
without needing to restart uvicorn.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ._schema import TaskDefinition

TASKS_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)

_TASK_INDEX: dict[str, TaskDefinition] | None = None
_TASK_INDEX_MAX_MTIME: float = 0.0
_TASKS_BY_ENV: dict[str, list[TaskDefinition]] | None = None


def _yaml_max_mtime() -> float:
    """Largest mtime across all task YAMLs. Cheap (~5ms for 500 files)."""
    return max(
        (p.stat().st_mtime for p in TASKS_DIR.rglob("*.yaml") if not p.name.startswith("_")),
        default=0.0,
    )


def load_all_tasks() -> dict[str, TaskDefinition]:
    """Discover and load all YAML task files. Reloads if any YAML changed."""
    global _TASK_INDEX, _TASK_INDEX_MAX_MTIME, _TASKS_BY_ENV
    current_mtime = _yaml_max_mtime()
    if _TASK_INDEX is not None and current_mtime <= _TASK_INDEX_MAX_MTIME:
        return _TASK_INDEX

    index: dict[str, TaskDefinition] = {}
    sources: dict[str, Path] = {}

    for yaml_path in sorted(TASKS_DIR.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        try:
            raw = yaml.safe_load(yaml_path.read_text())
            if raw is None:
                continue
            task = TaskDefinition.model_validate(raw)
            if task.task_id in index:
                raise ValueError(
                    f"Duplicate task_id '{task.task_id}' in "
                    f"{yaml_path} (first seen in {sources[task.task_id]})"
                )
            index[task.task_id] = task
            sources[task.task_id] = yaml_path
        except Exception:
            logger.exception("Failed to load task from %s", yaml_path)
            raise

    _validate_builder_references(index, sources)
    for task in index.values():
        _validate_canonical_diff_refs(task)
    logger.info("Loaded %d tasks from %s", len(index), TASKS_DIR)
    _TASK_INDEX = index
    _TASK_INDEX_MAX_MTIME = current_mtime
    _TASKS_BY_ENV = None  # invalidate derived cache
    return index


def _validate_canonical_diff_refs(task) -> None:
    """Verify named_invariant refs resolve to existing diff entries.

    Also enforces spec §4 that positive-diff collections and invariant
    collections are disjoint (unless the invariant has a filter to scope it).

    Raises ValueError on out-of-range / malformed refs or on overlapping
    collections. Called for every task that has a canonical_diff block.
    """
    import re
    cd = getattr(task, "canonical_diff", None)
    if cd is None:
        return
    # Walk all blocks (including oneof alternatives).
    blocks = [cd]
    if cd.oneof:
        blocks.extend(cd.oneof)

    for block in blocks:
        # 1. Named-invariant ref resolution.
        for ni in block.named_invariants:
            m = re.match(r"(invariant|create|update|delete)\[(\d+)\]", ni.ref)
            if not m:
                raise ValueError(
                    f"{task.task_id}: named_invariants[...].ref '{ni.ref}' is malformed"
                )
            kind, idx = m.group(1), int(m.group(2))
            target_list = getattr(block, kind)
            if idx >= len(target_list):
                raise ValueError(
                    f"{task.task_id}: named_invariants[...].ref '{ni.ref}' "
                    f"references {kind}[{idx}] but only {len(target_list)} {kind}(s) exist"
                )

        # 2. Spec §4: a collection can't be both a positive target and an
        #    invariant target (unless the invariant narrows via filter).
        def _col_for(entity_type: str) -> str:
            lower = entity_type.lower()
            return lower if lower.endswith("s") else lower + "s"

        positive_cols: set[str] = set()
        for e in list(block.create) + list(block.update) + list(block.delete):
            # Honor explicit collection override on update entries
            # (Class 17: multi-collection-per-entity envs like Reddit).
            explicit = getattr(e, "collection", None)
            if explicit:
                positive_cols.add(explicit.removeprefix("state."))
            else:
                positive_cols.add(_col_for(e.entity))
        for inv in block.invariant:
            inv_col = inv.collection.removeprefix("state.")
            if inv_col in positive_cols and not inv.filter:
                raise ValueError(
                    f"{task.task_id}: invariant on '{inv.collection}' overlaps with positive "
                    f"diff target and has no filter — scope it with a filter: expression"
                )


def _validate_builder_references(
    index: dict[str, TaskDefinition],
    sources: dict[str, Path],
) -> None:
    """Verify every seed step references a registered builder.

    Importing registries here (not at module level) avoids circular
    imports while still catching missing builders at startup.
    """
    from ._seed_builders import BUILDER_REGISTRY
    from ._seed_builders_amazon import AMAZON_BUILDER_REGISTRY
    from ._seed_builders_booking import BOOKING_BUILDER_REGISTRY
    from ._seed_builders_lms import LMS_BUILDER_REGISTRY
    from ._seed_builders_patient_portal import PATIENT_PORTAL_BUILDER_REGISTRY
    from ._seed_builders_reddit import REDDIT_BUILDER_REGISTRY
    from ._seed_builders_robinhood import ROBINHOOD_BUILDER_REGISTRY

    # Combine registries so each task validates against its own env's builders
    combined_registries: dict[str, dict] = {
        "amazon": AMAZON_BUILDER_REGISTRY,
        "booking": BOOKING_BUILDER_REGISTRY,
        "gmail": BUILDER_REGISTRY,
        "lms": LMS_BUILDER_REGISTRY,
        "patient_portal": PATIENT_PORTAL_BUILDER_REGISTRY,
        "reddit": REDDIT_BUILDER_REGISTRY,
        "robinhood": ROBINHOOD_BUILDER_REGISTRY,
    }

    for task in index.values():
        if task.seed is None:
            continue
        registry = combined_registries.get(task.env_id, BUILDER_REGISTRY)
        for step in task.seed.steps:
            if step.use not in registry:
                raise ValueError(
                    f"Task '{task.task_id}' ({sources[task.task_id]}) "
                    f"references unknown builder '{step.use}'"
                )


def get_task(task_id: str) -> TaskDefinition:
    """Look up a single task by ID.  Raises ``KeyError`` if not found."""
    return load_all_tasks()[task_id]


def tasks_by_env() -> dict[str, list[TaskDefinition]]:
    """Group all tasks by ``env_id``."""
    global _TASKS_BY_ENV
    tasks = load_all_tasks()  # may invalidate _TASKS_BY_ENV if YAMLs changed
    if _TASKS_BY_ENV is not None:
        return _TASKS_BY_ENV
    groups: dict[str, list[TaskDefinition]] = {}
    for task in tasks.values():
        groups.setdefault(task.env_id, []).append(task)
    _TASKS_BY_ENV = groups
    return groups


def env_tasks(env_id: str) -> list[TaskDefinition]:
    """Return all tasks for a specific environment."""
    return tasks_by_env().get(env_id, [])
