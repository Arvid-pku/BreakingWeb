"""Register all BreakingWeb tasks with BrowserGym.

After importing this module, tasks are available as:
    env = gym.make("browsergym/breakingweb.gmail_board_briefing_prep")
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


_registered = False


def register_all() -> int:
    """Register all BreakingWeb tasks with BrowserGym. Returns count. Idempotent."""
    global _registered
    if _registered:
        return 0
    _registered = True

    from browsergym.core.registration import register_task

    from .browsergym_task import BreakingWebTask
    from .tasks._registry import load_all_tasks

    count = 0
    for task_id in load_all_tasks():
        try:
            register_task(
                id=f"breakingweb.{task_id}",
                task_class=BreakingWebTask,
                task_kwargs={"task_id": task_id},
            )
            count += 1
        except Exception as e:
            logger.debug("Failed to register %s: %s", task_id, e)

    return count


# Auto-register on import
try:
    count = register_all()
    if count:
        logger.info("Registered %d BreakingWeb tasks with BrowserGym", count)
except Exception:
    pass
