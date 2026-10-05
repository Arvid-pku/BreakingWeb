"""Shared helpers used by environment seed runners."""

from __future__ import annotations

from typing import Any


def _assign_output(
    store: dict[str, Any],
    out_key: str,
    value: Any,
    *,
    task_id: str,
    builder_name: str,
) -> None:
    """Store a builder output, raising on silent overwrite with a different value.

    Two or more seed steps that declare the same output name are allowed only
    when every captured value is equal — the idiomatic example is a
    ``featured_property`` step followed by a ``create_reservation`` step that
    echoes the same ``property_id``. A collision with a *different* value
    almost always means the task author copy-pasted an output declaration and
    later ``{output.X}`` references silently resolve to the wrong step, which
    is a class of bug that produced unpassable tasks in the past.
    """
    if out_key in store and store[out_key] != value:
        existing = store[out_key]
        raise ValueError(
            f"Task '{task_id}': step '{builder_name}' declares output "
            f"{out_key!r}={value!r}, but an earlier step already captured "
            f"{out_key!r}={existing!r}. Rename this step's output to avoid "
            f"silently overwriting the earlier value."
        )
    store[out_key] = value
