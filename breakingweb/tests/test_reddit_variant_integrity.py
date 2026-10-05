from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.reddit import list_variants
from breakingweb.eval_core import compute_diff
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.tasks._registry import env_tasks, get_task


VARIANTS_DIR = Path(__file__).resolve().parents[1] / "injector" / "variants"
REDDIT_TASK_IDS = {task.task_id for task in env_tasks("reddit")}


@pytest.fixture(autouse=True)
def _reset_reddit_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _variant_paths() -> list[Path]:
    return sorted(VARIANTS_DIR.glob("reddit_*.yaml"))


def _load_variant(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    assert isinstance(raw, dict), f"{path.name} must parse to a mapping"
    return raw


def _create_session(client: TestClient, task_id: str, variant_filename: str) -> str:
    response = client.post(
        "/api/env/reddit/session",
        json={"task_id": task_id, "seed": 42, "variant_filename": variant_filename},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["degradation_active"] is True
    return payload["session_id"]


def test_reddit_variant_inventory_is_bound_and_creatable(client: TestClient) -> None:
    route_variants = list_variants()
    disk_paths = _variant_paths()

    assert len(route_variants) == len(disk_paths) == len(REDDIT_TASK_IDS)
    assert {variant["filename"] for variant in route_variants} == {path.name for path in disk_paths}

    for path in disk_paths:
        variant = _load_variant(path)
        task = get_task(variant["base_task_id"])
        primitive_set = set(task.primary_primitives or []) | set(task.secondary_primitives or [])

        assert variant["base_task_id"] in REDDIT_TASK_IDS
        assert variant["variant_id"] == path.stem
        assert path.stem.startswith(f"{variant['base_task_id']}__")
        assert variant["target_primitive"] in primitive_set
        assert variant.get("injections"), f"{path.name} must define injections"

        session_id = _create_session(client, variant["base_task_id"], path.name)
        state = app.state.session_manager.get(session_id)
        try:
            assert state.degradation["variant_filename"] == path.name
            assert state.degradation["variant_id"] == variant["variant_id"]
            assert state.degradation["target_primitive"] == variant["target_primitive"]
            assert not compute_diff(state._initial_state_copy, state), (
                f"{path.name} seed/server injections leaked as post-baseline diff"
            )
        finally:
            app.state.session_manager.destroy(session_id)


def test_reddit_subscribe_silent_fail_looks_successful_but_requires_retry(client: TestClient) -> None:
    session_id = _create_session(
        client,
        "reddit_discover_subscribe_post",
        "reddit_discover_subscribe_post__subreddit_collision.yaml",
    )
    state = app.state.session_manager.get(session_id)
    subreddit = state.get_subreddit_by_name("MachineLearning")
    assert subreddit is not None
    assert subreddit.is_subscribed is False

    # Hardened variant uses silent_fail fail_count:2 to defeat the agent's
    # navigate-back-and-retry loop. First two calls fake; third persists.
    first = client.post(
        "/api/env/reddit/r/MachineLearning/subscribe",
        json={"session_id": session_id, "action": "subscribe"},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["subreddit"]["name"] == "MachineLearning"
    assert first_body["subreddit"]["is_subscribed"] is True
    assert subreddit.is_subscribed is False

    second = client.post(
        "/api/env/reddit/r/MachineLearning/subscribe",
        json={"session_id": session_id, "action": "subscribe"},
    )
    assert second.status_code == 200, second.text
    assert subreddit.is_subscribed is False

    third = client.post(
        "/api/env/reddit/r/MachineLearning/subscribe",
        json={"session_id": session_id, "action": "subscribe"},
    )
    assert third.status_code == 200, third.text
    assert subreddit.is_subscribed is True


def test_reddit_settings_silent_fail_returns_full_settings_schema(client: TestClient) -> None:
    session_id = _create_session(
        client,
        "reddit_switch_dark_mode",
        "reddit_switch_dark_mode__settings_retry.yaml",
    )
    state = app.state.session_manager.get(session_id)
    assert state.settings.theme == "light"

    # Hardened variant uses fail_count:2 to defeat reflexive retry.
    first = client.put(
        "/api/env/reddit/settings",
        json={"session_id": session_id, "theme": "dark"},
    )
    assert first.status_code == 200, first.text
    first_settings = first.json()["settings"]
    assert first_settings["theme"] == "dark"
    assert first_settings["default_feed_sort"] == "hot"
    assert first_settings["show_online_status"] is True
    assert state.settings.theme == "light"

    second = client.put(
        "/api/env/reddit/settings",
        json={"session_id": session_id, "theme": "dark"},
    )
    assert second.status_code == 200, second.text
    assert state.settings.theme == "light"

    third = client.put(
        "/api/env/reddit/settings",
        json={"session_id": session_id, "theme": "dark"},
    )
    assert third.status_code == 200, third.text
    assert state.settings.theme == "dark"


def test_reddit_edit_silent_fail_returns_post_schema_but_does_not_persist(client: TestClient) -> None:
    session_id = _create_session(
        client,
        "reddit_edit_then_comment",
        "reddit_edit_then_comment__edit_retry.yaml",
    )
    state = app.state.session_manager.get(session_id)
    post_id = state.resolved_targets["edit_post_id"]
    new_body = state.resolved_targets["new_body"]
    post = state.get_post(post_id)
    assert post is not None
    assert post.body != new_body

    # Hardened variant uses fail_count:2.
    first = client.put(
        f"/api/env/reddit/posts/{post_id}",
        json={"session_id": session_id, "body": new_body},
    )
    assert first.status_code == 200, first.text
    first_post = first.json()["post"]
    assert first_post["id"] == post_id
    assert first_post["body"] == new_body
    assert post.body != new_body

    second = client.put(
        f"/api/env/reddit/posts/{post_id}",
        json={"session_id": session_id, "body": new_body},
    )
    assert second.status_code == 200, second.text
    assert post.body != new_body

    third = client.put(
        f"/api/env/reddit/posts/{post_id}",
        json={"session_id": session_id, "body": new_body},
    )
    assert third.status_code == 200, third.text
    assert post.body == new_body
