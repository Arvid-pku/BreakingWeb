from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.lms import SessionCreateRequest, create_session, list_variants
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.tasks._registry import env_tasks


VARIANTS_DIR = Path(__file__).resolve().parents[1] / "injector" / "variants"
LMS_TASK_IDS = [task.task_id for task in env_tasks("lms")]


@pytest.fixture(autouse=True)
def _reset_lms_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _variant_paths() -> list[Path]:
    return sorted(VARIANTS_DIR.glob("lms_*.yaml"))


def _load_variant(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    assert isinstance(raw, dict), f"{path.name} must parse to a mapping"
    return raw


def _variant_signature(variant: dict[str, Any]) -> tuple[str, ...]:
    injections = variant.get("injections") or []
    return tuple(
        sorted(
            f"{inj.get('layer')}:{(inj.get('params') or {}).get('action', '')}"
            for inj in injections
            if isinstance(inj, dict)
        )
    )


def _contains_target_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "{target." in value
    if isinstance(value, dict):
        return any(_contains_target_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_target_placeholder(item) for item in value)
    return False


def test_lms_variant_inventory_covers_all_tasks(client: TestClient) -> None:
    response = client.get("/api/env/lms/variants")
    assert response.status_code == 200, response.text

    route_variants = response.json()
    disk_paths = _variant_paths()

    assert route_variants, "expected YAML-backed LMS variants"
    assert disk_paths, "expected LMS variant YAML files to exist"
    assert len(route_variants) == len(disk_paths), "route should expose every LMS YAML variant"
    assert list_variants() == route_variants

    by_filename = {variant["filename"]: variant for variant in route_variants}
    assert set(by_filename) == {path.name for path in disk_paths}
    assert all(variant.get("source") == "yaml" for variant in route_variants)
    assert all(str(variant.get("filename", "")).startswith("lms_") for variant in route_variants)

    base_task_counts = Counter(variant.get("base_task_id", "") for variant in route_variants)
    missing_tasks = sorted(task_id for task_id in LMS_TASK_IDS if task_id not in base_task_counts)
    assert not missing_tasks, f"missing LMS variant coverage for: {missing_tasks}"
    # One meaningful variant per task is the curated goal; extras remain only
    # when tests explicitly reference a second variant by filename.
    assert len(route_variants) >= len(LMS_TASK_IDS), "expected at least one variant per LMS task"
    undercovered = sorted(task_id for task_id, count in base_task_counts.items() if count < 1)
    assert not undercovered, f"expected at least one variant per LMS task, undercovered: {undercovered}"


@pytest.mark.parametrize("path", _variant_paths(), ids=lambda path: path.name)
def test_lms_variant_yaml_is_well_formed_and_creatable(path: Path, client: TestClient) -> None:
    variant = _load_variant(path)

    required_keys = {"variant_id", "base_task_id", "target_primitive", "injections"}
    missing = sorted(required_keys - set(variant))
    assert not missing, f"{path.name} is missing required keys: {missing}"

    assert variant["variant_id"], f"{path.name} must define a variant_id"
    assert variant["base_task_id"] in LMS_TASK_IDS, f"{path.name} must bind to a real LMS task"
    assert variant["target_primitive"], f"{path.name} must define a target primitive"

    injections = variant.get("injections")
    assert isinstance(injections, list) and injections, f"{path.name} must define at least one injection"
    for injection in injections:
        assert isinstance(injection, dict), f"{path.name} injections must be mappings"
        assert injection.get("layer") in {"seed", "server", "network", "client"}, (
            f"{path.name} has invalid injection layer: {injection.get('layer')!r}"
        )
        assert isinstance(injection.get("params", {}), dict), f"{path.name} injection params must be a mapping"
        assert injection.get("params", {}).get("action"), f"{path.name} injection must define an action"

    session = create_session(
        SessionCreateRequest(
            task_id=variant["base_task_id"],
            seed=42,
            variant_filename=path.name,
        ),
        session_manager=app.state.session_manager,
    )
    state = app.state.session_manager.get(session["session_id"])
    try:
        assert session["degradation_active"] is True
        assert state.degradation["variant_filename"] == path.name
        assert state.degradation["variant_id"] == variant["variant_id"]
        assert state.degradation["base_task_id"] == variant["base_task_id"]
        assert state.degradation["target_primitive"] == variant["target_primitive"]
        assert session["instruction"].strip()
        assert not _contains_target_placeholder(state.degradation), (
            f"{path.name} left an unresolved target placeholder in the applied degradation"
        )

        if any(injection.get("layer") == "client" for injection in injections):
            response = client.get(f"/api/env/lms/degradation/{session['session_id']}")
            assert response.status_code == 200, response.text
            assert response.json().get("client_injections"), (
                f"{path.name} defines a client injection but the LMS UI cannot fetch it"
            )
    finally:
        app.state.session_manager.destroy(session["session_id"])


def test_lms_variant_corpus_has_diversity_floor() -> None:
    variants = [_load_variant(path) for path in _variant_paths()]
    assert variants, "expected LMS variants before checking diversity"

    primitive_counts = Counter(variant["target_primitive"] for variant in variants)
    signature_counts = Counter(_variant_signature(variant) for variant in variants)
    layer_counts = Counter(
        injection.get("layer")
        for variant in variants
        for injection in variant.get("injections", [])
        if isinstance(injection, dict)
    )
    action_counts = Counter(
        injection.get("params", {}).get("action")
        for variant in variants
        for injection in variant.get("injections", [])
        if isinstance(injection, dict) and injection.get("params", {}).get("action")
    )

    assert len(primitive_counts) >= 5, "LMS variants are too concentrated in a small primitive set"
    assert len(signature_counts) >= 5, "LMS variants are too concentrated in a small injection signature set"
    assert len(action_counts) >= 5, "LMS variants should span multiple degradation actions"
    assert {"seed", "server", "network"}.issubset(layer_counts), "LMS variants should span seed, server, and network layers"
    assert any(
        len({inj.get("layer") for inj in variant.get("injections", []) if isinstance(inj, dict)}) >= 2
        for variant in variants
    ), "at least one LMS variant should combine multiple layers"

    total_variants = len(variants)
    total_actions = sum(action_counts.values())
    assert max(primitive_counts.values()) / total_variants <= 0.4, "one primitive dominates the LMS corpus"
    assert max(signature_counts.values()) / total_variants <= 0.3, "one degradation signature dominates the LMS corpus"
    assert max(action_counts.values()) / total_actions <= 0.6, "one action dominates the LMS corpus"


def test_lms_silent_fail_message_send_does_not_persist_message(client: TestClient) -> None:
    payload = create_session(
        SessionCreateRequest(
            task_id="lms_discussion_participation_verify",
            seed=42,
            degradation={
                "variant_id": "lms_discussion_participation_verify__message_silent_fail",
                "base_task_id": "lms_discussion_participation_verify",
                "target_primitive": "verification",
                "description": "test-only message send silent failure",
                "injections": [
                    {
                        "layer": "network",
                        "params": {
                            "action": "silent_fail",
                            "url_pattern": "**/api/env/lms/messages/send",
                            "methods": ["POST"],
                            "response_body": {
                                "message": {
                                    "to": "advisor@school.edu",
                                    "subject": "Question about next steps",
                                    "body": "Could you clarify the rubric?",
                                    "sent_at": "2026-01-01T00:00:00Z",
                                    "from": "student@example.edu",
                                },
                                "sent": False,
                            },
                            "fail_count": 1,
                            "behavior": {"mode": "once"},
                        },
                    }
                ],
            },
        ),
        session_manager=app.state.session_manager,
    )
    session_id = payload["session_id"]
    try:
        before = client.get("/api/env/lms/messages", params={"session_id": session_id})
        assert before.status_code == 200, before.text
        assert before.json() == {"items": []}

        response = client.post(
            "/api/env/lms/messages/send",
            json={
                "session_id": session_id,
                "to": "advisor@school.edu",
                "subject": "Question about next steps",
                "body": "Could you clarify the rubric?",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["sent"] is False
        assert body["message"]["subject"] == "Question about next steps"
        after = client.get("/api/env/lms/messages", params={"session_id": session_id})
        assert after.status_code == 200, after.text
        assert after.json() == {"items": []}
        assert app.state.session_manager.get(session_id).sent_messages == []
    finally:
        app.state.session_manager.destroy(session_id)


def test_generated_lms_seed_variant_adds_shadow_course() -> None:
    baseline = create_session(
        SessionCreateRequest(task_id="lms_drop_course", seed=42),
        session_manager=app.state.session_manager,
    )
    degraded = create_session(
        SessionCreateRequest(
            task_id="lms_drop_course",
            seed=42,
            variant_filename="lms_drop_course__course_shadow_v1.yaml",
        ),
        session_manager=app.state.session_manager,
    )
    try:
        baseline_state = app.state.session_manager.get(baseline["session_id"])
        degraded_state = app.state.session_manager.get(degraded["session_id"])
        assert len(degraded_state.courses) == len(baseline_state.courses) + 1
        assert any(course.course_code.endswith("-ALT") for course in degraded_state.courses)
    finally:
        app.state.session_manager.destroy(baseline["session_id"])
        app.state.session_manager.destroy(degraded["session_id"])


def test_generated_lms_peer_review_retry_variant_requires_retry(client: TestClient) -> None:
    payload = create_session(
        SessionCreateRequest(
            task_id="lms_complete_account_audit",
            seed=42,
            variant_filename="lms_complete_account_audit__peer_review_retry_v1.yaml",
        ),
        session_manager=app.state.session_manager,
    )
    session_id = payload["session_id"]
    try:
        state = app.state.session_manager.get(session_id)
        review = next((review for review in state.peer_reviews if review.status != "submitted"), None)
        assert review is not None, "expected at least one pending peer review for retry test"

        body = {
            "session_id": session_id,
            "rubric_scores": {"Clarity": 4},
            "comments": "Solid draft with one retry-required write.",
        }
        first = client.post(f"/api/env/lms/peer-reviews/{review.id}/submit", json=body)
        assert first.status_code == 503, first.text
        second = client.post(f"/api/env/lms/peer-reviews/{review.id}/submit", json=body)
        assert second.status_code == 200, second.text
        assert second.json()["peer_review"]["status"] == "submitted"
    finally:
        app.state.session_manager.destroy(session_id)
