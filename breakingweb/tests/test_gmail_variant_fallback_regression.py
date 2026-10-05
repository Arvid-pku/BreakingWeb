from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.gmail import SessionCreateRequest, create_session, list_variants
from breakingweb.backend.state import SessionManager
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.tasks._registry import load_all_tasks


VARIANTS_DIR = Path(__file__).resolve().parents[1] / "injector" / "variants"


def _gmail_variant_paths() -> list[Path]:
    return sorted(VARIANTS_DIR.glob("gmail_*.yaml"))


def _load_variant(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) or {}


def _assert_unique_ids(state: Any, path: Path) -> None:
    for attr in ("emails", "sent", "deleted", "drafts", "contacts", "labels", "filters"):
        values = [
            getattr(item, "id", None)
            for item in getattr(state, attr, [])
            if getattr(item, "id", None)
        ]
        assert len(values) == len(set(values)), f"{path.name} produced duplicate ids in {attr}"


@pytest.fixture(autouse=True)
def _reset_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_variants_endpoint_only_exposes_yaml_backed_variants(client: TestClient) -> None:
    response = client.get("/api/env/gmail/variants")
    assert response.status_code == 200, response.text

    variants = response.json()
    assert isinstance(variants, list)
    assert variants, "expected at least one YAML-backed Gmail variant"

    assert all(v.get("source") == "yaml" for v in variants)
    assert not any(str(v.get("filename", "")).startswith("__auto__") for v in variants)
    assert any(
        v.get("filename") == "gmail_change_setting__exploration.yaml"
        and v.get("base_task_id") == "gmail_change_setting"
        and v.get("target_primitive") == "exploration"
        for v in variants
    )

    api_variants = list_variants()
    assert api_variants == variants


def test_new_yaml_variant_can_create_session() -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id="gmail_change_setting",
            variant_filename="gmail_change_setting__exploration.yaml",
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])
    assert state.degradation["variant_filename"] == "gmail_change_setting__exploration.yaml"
    assert state.degradation["base_task_id"] == "gmail_change_setting"
    assert state.degradation["target_primitive"] == "exploration"


@pytest.mark.parametrize("path", _gmail_variant_paths(), ids=lambda path: path.name)
def test_all_gmail_variants_are_task_aligned_and_creatable(path: Path) -> None:
    variant = _load_variant(path)
    tasks = load_all_tasks()

    task_id = variant.get("base_task_id")
    assert task_id in tasks, f"{path.name} must bind to a real task"
    task = tasks[task_id]
    assert task.env_id == "gmail", f"{path.name} must bind to a Gmail task"

    primitives = set(task.primary_primitives or []) | set(task.secondary_primitives or [])
    assert variant.get("target_primitive") in primitives, (
        f"{path.name} target_primitive={variant.get('target_primitive')!r} "
        f"must match one of {sorted(primitives)}"
    )

    injections = variant.get("injections")
    assert isinstance(injections, list) and injections, f"{path.name} must define injections"
    for injection in injections:
        assert isinstance(injection, dict), f"{path.name} injections must be mappings"
        assert injection.get("layer") in {"seed", "server", "client", "network"}
        assert isinstance(injection.get("params"), dict)
        assert injection["params"].get("action"), f"{path.name} injection must name an action"

    session_manager = SessionManager()
    payload = create_session(
        SessionCreateRequest(
            task_id=task_id,
            seed=42,
            variant_filename=path.name,
        ),
        session_manager=session_manager,
    )
    state = session_manager.get(payload["session_id"])

    assert state.degradation["variant_filename"] == path.name
    assert state.degradation["base_task_id"] == task_id
    assert state._initial_snapshot == state.state_snapshot()
    _assert_unique_ids(state, path)
