from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.injector.middleware import clear_all_degradations


@pytest.fixture(autouse=True)
def _reset_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _create_session(client: TestClient, task_id: str, seed: int = 42) -> str:
    resp = client.post(
        "/api/env/patient_portal/session",
        json={"task_id": task_id, "seed": seed},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


def test_reset_returns_fresh_session_that_is_reachable(client: TestClient) -> None:
    """The /reset endpoint must return a new session_id that the server
    immediately recognizes on every subsequent endpoint.

    Regression guard for w06 audit: "Reset button generates a new session ID
    that is immediately Unknown to the server (404 on all API calls)."
    """
    old_sid = _create_session(client, "pp_check_interactions", seed=42)

    reset = client.post(f"/api/env/patient_portal/session/{old_sid}/reset")
    assert reset.status_code == 200, reset.text
    new_payload = reset.json()
    new_sid = new_payload["session_id"]
    assert new_sid, "reset response missing session_id"
    assert new_sid != old_sid, "reset must mint a fresh session_id"

    info = client.get(f"/api/env/patient_portal/session/{new_sid}")
    assert info.status_code == 200, info.text
    assert info.json().get("session_id") == new_sid

    deg = client.get(f"/api/env/patient_portal/degradation/{new_sid}")
    assert deg.status_code == 200, deg.text

    old_info = client.get(f"/api/env/patient_portal/session/{old_sid}")
    assert old_info.status_code == 404


def test_reset_preserves_task_and_seed(client: TestClient) -> None:
    """Reset must recreate a session bound to the same task_id and seed so
    the agent resumes with a reproducible environment. The public summary
    intentionally hides task_id/seed, so we compare the rendered title/
    instruction across old and new sessions — identical task+seed means
    identical resolved targets and therefore identical rendered text."""
    old_sid = _create_session(client, "pp_check_interactions", seed=4242)
    old_info = client.get(f"/api/env/patient_portal/session/{old_sid}").json()

    reset = client.post(f"/api/env/patient_portal/session/{old_sid}/reset")
    assert reset.status_code == 200, reset.text
    new_sid = reset.json()["session_id"]

    new_info = client.get(f"/api/env/patient_portal/session/{new_sid}").json()
    assert new_info["title"] == old_info["title"]
    assert new_info["instruction"] == old_info["instruction"]


def test_reset_with_variant_preserves_degradation(client: TestClient) -> None:
    """When the session has an active degradation variant, reset must carry
    it into the new session so the stress variant continues to apply."""
    resp = client.post(
        "/api/env/patient_portal/session",
        json={
            "task_id": "pp_check_interactions",
            "seed": 42,
            "variant_filename": "pp_check_interactions__medication_shadow_v1.yaml",
        },
    )
    if resp.status_code == 404:
        pytest.skip("variant file not present in this tree")
    assert resp.status_code == 200, resp.text
    old_sid = resp.json()["session_id"]

    reset = client.post(f"/api/env/patient_portal/session/{old_sid}/reset")
    assert reset.status_code == 200, reset.text
    new_sid = reset.json()["session_id"]

    deg = client.get(f"/api/env/patient_portal/degradation/{new_sid}")
    assert deg.status_code == 200, deg.text
    assert deg.json().get("client_injections") is not None
