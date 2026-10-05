"""BrowserGym-native environment for BreakingWeb.

Creates a standard BrowserGym ``BrowserEnv`` backed by
``BreakingWebTask``. Agents interact using BrowserGym's observation
dict and Python function-call action strings — identical to WebArena,
WorkArena, and other BrowserGym benchmarks.

Usage:
    # Via gymnasium (after importing registration)
    import gymnasium as gym
    import breakingweb.browsergym_register  # auto-registers tasks
    env = gym.make("browsergym/breakingweb.gmail_board_briefing_prep")
    obs, info = env.reset()
    obs, reward, terminated, truncated, info = env.step("click('a51')")
    env.close()

    # Via convenience function
    from breakingweb.browsergym_env import make_env
    env = make_env("gmail_board_briefing_prep")

Observation dict keys (standard BrowserGym):
    goal, goal_object, chat_messages, url, screenshot, dom_object,
    axtree_object, extra_element_properties, focused_element_bid,
    open_pages_urls, open_pages_titles, active_page_index,
    last_action, last_action_error, elapsed_time

Action format (standard BrowserGym):
    click('bid')
    fill('bid', 'value')
    select_option('bid', 'option')
    hover('bid')
    press('bid', 'Enter')
    scroll(0, 300)
    dblclick('bid')
    drag_and_drop('bid1', 'bid2')
    send_msg_to_user('answer')      # = finish the task
    report_infeasible('reason')     # = declare task impossible
"""

from __future__ import annotations

from typing import Any

from browsergym.core.action.highlevel import HighLevelActionSet
from browsergym.core.env import BrowserEnv

from .browsergym_task import BreakingWebTask


def make_env(
    task_id: str,
    degradation: str | None = None,
    headless: bool = True,
    server_host: str = "127.0.0.1",
    server_port: int = 8080,
    action_subsets: list[str] | None = None,
    viewport: tuple[int, int] | None = None,
    **kwargs: Any,
) -> BrowserEnv:
    """Create a BrowserGym environment for a BreakingWeb task.

    Args:
        task_id: Gmail task ID (e.g. "gmail_board_briefing_prep").
        degradation: Path to degradation variant YAML (stress-test mode).
        headless: Run browser in headless mode.
        server_host: BreakingWeb server host.
        server_port: BreakingWeb server port.
        action_subsets: BrowserGym action subsets. Default: ["bid", "chat", "infeas"].
        **kwargs: Additional kwargs passed to BrowserEnv.

    Returns:
        A standard BrowserGym BrowserEnv instance.
    """
    if action_subsets is None:
        action_subsets = ["bid", "chat", "infeas"]

    action_set = HighLevelActionSet(subsets=action_subsets, multiaction=False)

    task_kwargs: dict[str, Any] = {
        "task_id": task_id,
        "degradation": degradation,
        "server_host": server_host,
        "server_port": server_port,
    }
    if viewport is not None:
        task_kwargs["viewport"] = viewport

    return BrowserEnv(
        task_entrypoint=BreakingWebTask,
        task_kwargs=task_kwargs,
        headless=headless,
        action_mapping=action_set.to_python_code,
        **kwargs,
    )
