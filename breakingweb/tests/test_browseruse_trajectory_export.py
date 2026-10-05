from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from breakingweb.browseruse_eval import (
    _extract_replay_path,
    action_to_trajectory_format,
    build_trajectory_step,
)


def test_stock_browser_use_actions_convert_to_trajectory_actions() -> None:
    assert action_to_trajectory_format({"input": {"index": 7, "text": "hello", "clear": True}}) == {
        "action": "fill",
        "ref": "7",
        "value": "hello",
        "clear": True,
    }
    assert action_to_trajectory_format({"select_dropdown": {"index": 8, "text": "Blue"}}) == {
        "action": "select",
        "ref": "8",
        "value": "Blue",
    }
    assert action_to_trajectory_format({"scroll": {"down": False, "pages": 0.5, "index": 9}}) == {
        "action": "scroll",
        "direction": "up",
        "pages": 0.5,
        "ref": "9",
    }
    assert action_to_trajectory_format({"dropdown_options": {"index": 8}}) == {
        "action": "dropdown_options",
        "ref": "8",
    }
    assert action_to_trajectory_format({"search_page": {"pattern": "invoice"}}) == {
        "action": "search_page",
        "value": "invoice",
    }


def test_build_trajectory_step_preserves_full_action_batch_and_targets() -> None:
    actions = [
        {"click": {"index": 4}},
        {"input": {"index": 5, "text": "alice@example.com", "clear": True}},
        {"select_dropdown": {"index": 6, "text": "Urgent"}},
    ]
    dom_elements = {
        4: {"tag_name": "button", "attributes": {"aria-label": "Compose"}, "text": ""},
        5: {"tag_name": "input", "attributes": {"placeholder": "To"}, "text": ""},
        6: {"tag_name": "select", "attributes": {"aria-label": "Priority"}, "text": ""},
    }

    step = build_trajectory_step(
        step_num=1,
        thinking="Compose and classify",
        memory="",
        actions=actions,
        dom_elements=dom_elements,
        url="http://127.0.0.1:8110/env/gmail/inbox?session=s1",
        status="success",
        elapsed=1.2,
        action_results=[{"status": "success"}, {"status": "success"}, {"status": "success"}],
    )

    assert step["action"] == {"action": "click", "ref": "4"}
    assert step["actions"] == [
        {"action": "click", "ref": "4"},
        {"action": "fill", "ref": "5", "value": "alice@example.com", "clear": True},
        {"action": "select", "ref": "6", "value": "Urgent"},
    ]
    assert step["raw_actions"] == actions
    assert step["action_results"] == [{"status": "success"}, {"status": "success"}, {"status": "success"}]
    assert step["targets"] == {"role": "button", "name": "Compose"}
    assert step["action_targets"][1] == {"role": "textbox", "name": "To"}
    assert step["action_targets"][2] == {"role": "combobox", "name": "Priority"}


@pytest.mark.parametrize(
    ("env", "path"),
    [
        ("amazon", "/orders"),
        ("booking", "/search/results"),
        ("gmail", "/thread/email_1"),
        ("lms", "/courses/course_1"),
        ("patient_portal", "/profile"),
        ("reddit", "/r/python/comments/post_1"),
        ("robinhood", "/portfolio"),
    ],
)
def test_replay_path_extraction_supports_all_environments(env: str, path: str) -> None:
    assert _extract_replay_path(f"http://host/env/{env}{path}?session=s") == path


def test_replay_path_extraction_defaults_env_root_to_slash() -> None:
    assert _extract_replay_path("http://host/env/reddit?session=s") == "/"


def test_demo_site_prepare_results_preserves_exported_paths_and_targets() -> None:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "environments"
        / "demo-site"
        / "scripts"
        / "prepare-results.py"
    )
    spec = importlib.util.spec_from_file_location("prepare_results", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    step = {
        "step": 1,
        "thought": "Open portfolio",
        "action": {"action": "click", "ref": "4"},
        "actions": [{"action": "click", "ref": "4"}],
        "raw_actions": [{"click": {"index": 4}}],
        "targets": {"role": "link", "name": "Portfolio"},
        "action_targets": [{"role": "link", "name": "Portfolio"}],
        "action_results": [{"status": "success"}],
        "status": "success",
        "elapsed_seconds": 0.4,
        "replay_path": "/portfolio",
        "result_path": "/orders",
    }

    simplified = module.simplify_step(step)

    assert simplified["replay_path"] == "/portfolio"
    assert simplified["result_path"] == "/orders"
    assert simplified["targets"] == {
        "ref": {"role": "link", "name": "Portfolio", "nth": None, "selector": None, "bbox": None}
    }
    assert simplified["actions"] == [{"action": "click", "ref": "4"}]
    assert simplified["raw_actions"] == [{"click": {"index": 4}}]
    assert simplified["action_results"] == [{"status": "success"}]
