from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from breakingweb.backend.models.base import BaseEnvState
from breakingweb.backend.state import materialize_task_state
from breakingweb.task_rendering import render_template
from breakingweb.tasks._schema import TaskDefinition


@dataclass(frozen=True, slots=True)
class MaterializedTask:
    task: TaskDefinition
    state: BaseEnvState
    resolved_targets: dict[str, Any]
    seed: int
    instruction: str
    start_path: str


def materialize_task(env_id: str, task_id: str, seed: int | None = None) -> MaterializedTask:
    """Build the canonical seeded task artifact used by benchmark exporters."""
    task, state, resolved_targets, actual_seed = materialize_task_state(
        env_id, task_id, seed
    )
    instruction = render_template(
        task.instruction_template or task.instruction or "",
        resolved_targets,
    )
    return MaterializedTask(
        task=task,
        state=state,
        resolved_targets=resolved_targets,
        seed=actual_seed,
        instruction=instruction,
        start_path=task.start_path or "/",
    )
