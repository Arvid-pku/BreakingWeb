"""Unified task definition framework for BreakingWeb.

All active tasks are defined as YAML files, validated by Pydantic models,
and loaded into a cached registry at startup.
"""

from ._registry import env_tasks, get_task, load_all_tasks, tasks_by_env
from ._schema import (
    Check,
    EvalConfig,
    NegativeCheck,
    SeedActor,
    SeedConfig,
    SeedStep,
    TaskDefinition,
)

__all__ = [
    "Check",
    "EvalConfig",
    "NegativeCheck",
    "SeedActor",
    "SeedConfig",
    "SeedStep",
    "TaskDefinition",
    "env_tasks",
    "get_task",
    "load_all_tasks",
    "tasks_by_env",
]
