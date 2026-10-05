"""End-to-end integration tests for the BreakingWeb stress-test pipeline.

Uses Starlette TestClient to run the full ASGI app (including middleware)
in-process.  No browser required — these tests cover the server-side path
that is common to both human play and Playwright agents.

Tests verify:
  1. Standard session lifecycle (create → mutate → evaluate)
  2. Network degradation middleware (error_then_success returns 503s)
  3. Network degradation middleware (delay actually delays)
  4. Network degradation middleware (silent_fail returns fake 200)
  5. Client injection registration and retrieval
  6. Seed/server injections mutate state
  7. Task/variant mismatch rejection
  8. Session isolation (degradation in one session doesn't leak)
  9. Evaluation scoring with negative penalty cap
"""

from __future__ import annotations

import time

import pytest
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.security import CONTROLLER_SECRET_HEADER
from breakingweb.backend.state import materialize_task_state
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.runner import controller_headers, ensure_controller_secret
from breakingweb.tasks._registry import env_tasks


@pytest.fixture(autouse=True)
def _clean_degradation_state():
    """Reset global degradation state between tests."""
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client():
    app.state.controller_secret = ensure_controller_secret()
    return TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────

def _controller_headers() -> dict[str, str]:
    return {CONTROLLER_SECRET_HEADER: app.state.controller_secret}


def _targets(task_id: str, seed: int) -> dict:
    _, _, resolved_targets, _ = materialize_task_state("gmail", task_id, seed)
    return resolved_targets

def _create_session(client: TestClient, task_id: str = "gmail_star_email",
                    seed: int = 42, **extra) -> dict:
    payload = {"task_id": task_id, "seed": seed, **extra}
    resp = client.post("/api/env/gmail/session", json=payload, headers=controller_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "session_id" in data
    data["resolved_targets"] = _targets(task_id, seed)
    return data


def _evaluate(client: TestClient, *, session_id: str, task_id: str, **extra) -> dict:
    payload = {"session_id": session_id, "task_id": task_id, **extra}
    resp = client.post("/api/env/gmail/evaluate", json=payload, headers=controller_headers())
    assert resp.status_code == 200, resp.text
    return resp.json()


def _referer(session_id: str) -> dict:
    """Build a Referer header the middleware can extract session from."""
    return {"Referer": f"http://testserver/env/gmail/inbox?session={session_id}"}


# ── 1. Standard session lifecycle ────────────────────────────────────────

_PUBLIC_SESSION_ENVS = ("gmail", "amazon", "booking", "reddit", "robinhood")

class TestStandardLifecycle:
    def test_create_list_evaluate_destroy(self, client: TestClient):
        session = _create_session(client)
        sid = session["session_id"]

        # List emails
        resp = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert resp.status_code == 200
        emails = resp.json()
        assert emails["total"] > 0

        # Star the target email
        target_id = session["resolved_targets"]["target_email_id"]
        resp = client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
        )
        assert resp.status_code == 200

        # Evaluate
        result = _evaluate(client, session_id=sid, task_id="gmail_star_email")
        assert result["success"] is True
        assert result["score"] > 0.5

        # Destroy
        resp = client.delete(f"/api/env/gmail/session/{sid}")
        assert resp.status_code == 200

    def test_evaluation_fails_when_task_not_done(self, client: TestClient):
        session = _create_session(client)
        result = _evaluate(client, session_id=session["session_id"], task_id="gmail_star_email")
        # Email is not starred → check fails
        assert result["success"] is False
        assert result["score"] < 1.0

    @pytest.mark.parametrize(
        ("env_id", "task_id"),
        [
            ("amazon", "amazon_add_single_item"),
            ("booking", "booking_change_phone"),
            ("gmail", "gmail_star_email"),
            ("reddit", "reddit_upvote_post"),
            ("robinhood", "rh_add_to_watchlist"),
        ],
    )
    def test_public_evaluate_allows_bound_session_task_without_controller_headers(
        self,
        client: TestClient,
        env_id: str,
        task_id: str,
    ) -> None:
        session_resp = client.post(
            f"/api/env/{env_id}/session",
            json={"task_id": task_id, "seed": 42},
            headers=controller_headers(),
        )
        assert session_resp.status_code == 200, session_resp.text
        session = session_resp.json()

        eval_resp = client.post(
            f"/api/env/{env_id}/evaluate",
            json={
                "session_id": session["session_id"],
                "task_id": None,
                "benchmark_state": {},
                "trajectory": [],
            },
        )
        assert eval_resp.status_code == 200, eval_resp.text
        result = eval_resp.json()
        assert "checks" in result
        assert "negative_checks" in result

    def test_public_evaluate_rejects_cross_task_override_without_controller_headers(self, client: TestClient) -> None:
        session = _create_session(client)
        resp = client.post(
            "/api/env/gmail/evaluate",
            json={
                "session_id": session["session_id"],
                "task_id": "gmail_reply_simple",
                "benchmark_state": {},
                "trajectory": [],
            },
        )
        assert resp.status_code == 403
        assert "Controller access required" in resp.json()["detail"]

    def test_booking_add_payment_can_evaluate_successfully_after_matching_mutation(
        self,
        client: TestClient,
    ) -> None:
        session_resp = client.post(
            "/api/env/booking/session",
            json={"task_id": "booking_add_payment", "seed": 42},
            headers=controller_headers(),
        )
        assert session_resp.status_code == 200, session_resp.text
        session = session_resp.json()

        add_resp = client.post(
            "/api/env/booking/payment-methods",
            json={
                "session_id": session["session_id"],
                "card_type": "Discover",
                "last_four": "7777",
                "expiry": "09/28",
                "holder_name": "Jordan Parker",
                "is_default": False,
            },
        )
        assert add_resp.status_code == 200, add_resp.text

        eval_resp = client.post(
            "/api/env/booking/evaluate",
            json={
                "session_id": session["session_id"],
                "task_id": None,
                "benchmark_state": {},
                "trajectory": [],
            },
        )
        assert eval_resp.status_code == 200, eval_resp.text
        result = eval_resp.json()
        assert result["success"] is True
        assert result["score"] == pytest.approx(1.0)


class TestPublicSessionSanitization:
    @pytest.mark.parametrize("env_id", _PUBLIC_SESSION_ENVS)
    def test_public_session_endpoints_omit_private_fields(self, client: TestClient, env_id: str):
        task_id = env_tasks(env_id)[0].task_id

        create_resp = client.post(f"/api/env/{env_id}/session", json={"task_id": task_id, "seed": 42})
        assert create_resp.status_code == 200, create_resp.text
        session = create_resp.json()

        assert "task_id" not in session
        assert "seed" not in session
        assert "resolved_targets" not in session

        summary_resp = client.get(f"/api/env/{env_id}/session/{session['session_id']}")
        assert summary_resp.status_code == 200, summary_resp.text
        summary = summary_resp.json()

        assert "task_id" not in summary
        assert "seed" not in summary
        assert "degradation" not in summary

        destroy_resp = client.delete(f"/api/env/{env_id}/session/{session['session_id']}")
        assert destroy_resp.status_code == 200, destroy_resp.text


# ── 2. Network degradation: error_then_success ──────────────────────────

class TestNetworkErrorThenSuccess:
    """Verify the middleware returns 503 for the first N calls, then passes."""

    def test_503_fires_then_succeeds(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_error_then_success",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "error_count": 2,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]

        # First 2 GET calls should return 503
        r1 = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r1.status_code == 503, f"Call 1 expected 503, got {r1.status_code}"

        r2 = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r2.status_code == 503, f"Call 2 expected 503, got {r2.status_code}"

        # Call 3 should succeed
        r3 = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r3.status_code == 200, f"Call 3 expected 200, got {r3.status_code}"
        assert r3.json()["total"] > 0

    def test_intermittent_mode_fires_probabilistically(self, client: TestClient):
        """With probability=1.0 and a fixed seed, every call should error."""
        session = _create_session(client, degradation={
            "variant_id": "test_intermittent_error",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "behavior": {"mode": "intermittent", "probability": 1.0, "seed": 7},
                },
            }],
        })
        sid = session["session_id"]

        for i in range(3):
            r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
            assert r.status_code == 503, f"Call {i+1} expected 503 with p=1.0"


# ── 3. Network degradation: delay ───────────────────────────────────────

class TestNetworkDelay:
    def test_delay_adds_latency(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_delay",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "delay",
                    "url_pattern": "**/api/env/gmail/emails",
                    "delay_ms": 500,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]

        t0 = time.monotonic()
        r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed >= 0.4, f"Expected >=400ms delay, got {elapsed*1000:.0f}ms"

    def test_benchmark_control_polling_is_not_delayed_by_env_referer(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_legacy_broad_delay",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "server",
                "params": {
                    "action": "slow_responses",
                    "endpoints": [{
                        "path_pattern": ".*",
                        "delay_ms": 500,
                    }],
                },
            }],
        })
        sid = session["session_id"]

        t0 = time.monotonic()
        r = client.get(f"/api/control/{sid}/record-state", headers=_referer(sid))
        elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed < 0.2, f"Control polling should bypass env delay, got {elapsed*1000:.0f}ms"


# ── 4. Network degradation: silent_fail ─────────────────────────────────

class TestNetworkSilentFail:
    def test_silent_fail_returns_fake_200(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_silent_fail",
            "base_task_id": "gmail_star_email",
            "target_primitive": "verification",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "silent_fail",
                    "url_pattern": "**/api/env/gmail/emails/*/star",
                    "methods": ["POST"],
                    "response_body": {"success": True, "fake": True},
                    "fail_count": 1,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]
        target_id = session["resolved_targets"]["target_email_id"]

        # First POST → silent fail (fake 200)
        r1 = client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
            headers=_referer(sid),
        )
        assert r1.status_code == 200
        assert r1.json().get("fake") is True  # got the fake body, not real

        # Second POST → real handler
        r2 = client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
            headers=_referer(sid),
        )
        assert r2.status_code == 200
        assert "email" in r2.json()  # real response has "email" key

    def test_silent_fail_post_budget_is_not_consumed_by_matching_get(self, client: TestClient):
        session = _create_session(
            client,
            task_id="gmail_create_label",
            degradation={
                "variant_id": "test_silent_fail_labels",
                "base_task_id": "gmail_create_label",
                "target_primitive": "verification",
                "description": "test",
                "injections": [{
                    "layer": "network",
                    "params": {
                        "action": "silent_fail",
                        "url_pattern": "**/api/env/gmail/labels",
                        "methods": ["POST"],
                        "response_body": {"label": {"id": "fake_label", "name": "Important Projects"}},
                        "fail_count": 1,
                        "behavior": {"mode": "once"},
                    },
                }],
            },
        )
        sid = session["session_id"]

        # Matching GET should not consume the one-shot POST failure.
        list_resp = client.get(
            f"/api/env/gmail/labels?session_id={sid}",
            headers=_referer(sid),
        )
        assert list_resp.status_code == 200

        first_post = client.post(
            "/api/env/gmail/labels",
            json={"session_id": sid, "name": "Important Projects", "color": "#1a73e8"},
            headers=_referer(sid),
        )
        assert first_post.status_code == 200
        assert first_post.json()["label"]["id"] == "fake_label"

        second_post = client.post(
            "/api/env/gmail/labels",
            json={"session_id": sid, "name": "Important Projects Real", "color": "#1a73e8"},
            headers=_referer(sid),
        )
        assert second_post.status_code == 200
        assert second_post.json()["label"]["id"] != "fake_label"


# ── 5. Client injection registration + retrieval ────────────────────────

class TestClientInjections:
    def test_client_injections_served_via_api(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_client",
            "base_task_id": "gmail_star_email",
            "target_primitive": "grounding",
            "description": "test",
            "injections": [{
                "layer": "client",
                "params": {
                    "action": "scramble_aria",
                    "selector": "[role='listitem'] [aria-label]",
                    "behavior": {"mode": "persistent"},
                },
            }],
        })
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/degradation/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        injections = data["client_injections"]
        assert len(injections) == 1
        assert injections[0]["params"]["action"] == "scramble_aria"

    def test_no_client_injections_for_standard_session(self, client: TestClient):
        session = _create_session(client)
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/degradation/{sid}")
        assert resp.status_code == 200
        assert resp.json()["client_injections"] == []


# ── 6. Seed/server injections mutate state ───────────────────────────────

class TestSeedServerInjections:
    def test_server_scramble_timestamps(self, client: TestClient):
        """Create two sessions: one standard, one with scrambled timestamps."""
        std = _create_session(client, seed=100)
        deg = _create_session(client, seed=100, degradation={
            "variant_id": "test_scramble",
            "base_task_id": "gmail_star_email",
            "target_primitive": "planning",
            "description": "test",
            "injections": [{
                "layer": "server",
                "params": {"action": "scramble_timestamps", "seed": 42},
            }],
        })

        # Fetch emails from both
        std_emails = client.get(
            f"/api/env/gmail/emails?session_id={std['session_id']}&label=inbox"
        ).json()["items"]
        deg_emails = client.get(
            f"/api/env/gmail/emails?session_id={deg['session_id']}&label=inbox"
        ).json()["items"]

        # Same task/seed should produce same emails, but timestamps differ
        assert len(std_emails) == len(deg_emails)
        if std_emails and deg_emails:
            std_ts = std_emails[0].get("timestamp")
            deg_ts = deg_emails[0].get("timestamp")
            assert std_ts != deg_ts, "Timestamps should differ after scramble"

    def test_server_inject_distractor_emails(self, client: TestClient):
        std = _create_session(client, seed=200)
        deg = _create_session(client, seed=200, degradation={
            "variant_id": "test_distractor",
            "base_task_id": "gmail_star_email",
            "target_primitive": "grounding",
            "description": "test",
            "injections": [{
                "layer": "server",
                "params": {
                    "action": "inject_distractor_emails",
                    "count": 3,
                    "subject_prefix": "URGENT: ",
                },
            }],
        })

        std_count = client.get(
            f"/api/env/gmail/emails?session_id={std['session_id']}&label=inbox"
        ).json()["total"]
        deg_count = client.get(
            f"/api/env/gmail/emails?session_id={deg['session_id']}&label=inbox"
        ).json()["total"]

        assert deg_count == std_count + 3


# ── 7. Task/variant mismatch rejection ──────────────────────────────────

class TestVariantMismatch:
    def test_rejects_wrong_base_task(self, client: TestClient):
        resp = client.post("/api/env/gmail/session", json={
            "task_id": "gmail_star_email",
            "degradation": {
                "variant_id": "wrong",
                "base_task_id": "gmail_board_briefing_prep",
                "target_primitive": "grounding",
                "description": "wrong task",
                "injections": [],
            },
        })
        assert resp.status_code == 400
        assert "bound to task" in resp.json()["detail"]

    def test_accepts_matching_base_task(self, client: TestClient):
        resp = client.post("/api/env/gmail/session", json={
            "task_id": "gmail_star_email",
            "degradation": {
                "variant_id": "ok",
                "base_task_id": "gmail_star_email",
                "target_primitive": "patience",
                "description": "test",
                "injections": [],
            },
        })
        assert resp.status_code == 200


# ── 8. Session isolation ────────────────────────────────────────────────

class TestSessionIsolation:
    def test_degradation_does_not_leak_across_sessions(self, client: TestClient):
        """Create one degraded session and one standard; standard must be clean."""
        degraded = _create_session(client, seed=300, degradation={
            "variant_id": "test_isolation",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "error_count": 99,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        standard = _create_session(client, seed=301)

        # Degraded session → 503
        r_deg = client.get(
            f"/api/env/gmail/emails?session_id={degraded['session_id']}&label=inbox"
        )
        assert r_deg.status_code == 503

        # Standard session → 200 (no leakage)
        r_std = client.get(
            f"/api/env/gmail/emails?session_id={standard['session_id']}&label=inbox"
        )
        assert r_std.status_code == 200

    def test_destroy_clears_degradation(self, client: TestClient):
        session = _create_session(client, degradation={
            "variant_id": "test_destroy",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "test",
            "injections": [{
                "layer": "network",
                "params": {
                    "action": "error_then_success",
                    "url_pattern": "**/api/env/gmail/emails",
                    "error_status": 503,
                    "error_count": 99,
                    "behavior": {"mode": "once"},
                },
            }],
        })
        sid = session["session_id"]

        # 503 while active
        assert client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox").status_code == 503

        # Destroy
        client.delete(f"/api/env/gmail/session/{sid}")

        # After destroy, no degradation (session also gone → 404 from handler)
        r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        assert r.status_code != 503  # either 200 (no middleware match) or 404 (session gone)


# ── 9. Real variant file integration ────────────────────────────────────

class TestRealVariantFiles:
    def test_patience_variant_delays_requests(self, client: TestClient):
        """Load the actual gmail_compliance_settings__patience.yaml variant."""
        session = _create_session(
            client,
            task_id="gmail_compliance_settings_audit",
            variant_filename="gmail_compliance_settings__patience.yaml",
        )
        sid = session["session_id"]
        assert session["degradation_active"] is True

        # The variant applies progressive delay: first 3 calls get 1000ms delay
        t0 = time.monotonic()
        r = client.get(f"/api/env/gmail/emails?session_id={sid}&label=inbox")
        elapsed = time.monotonic() - t0

        assert r.status_code == 200
        # 1000ms delay on first call
        assert elapsed >= 0.8, f"Expected >=800ms delay, got {elapsed*1000:.0f}ms"

    def test_grounding_variant_registers_client_injections(self, client: TestClient):
        """Load a real client-layer Gmail grounding variant."""
        session = _create_session(
            client,
            task_id="gmail_client_handoff",
            variant_filename="gmail_client_handoff__grounding.yaml",
        )
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/degradation/{sid}")
        injections = resp.json()["client_injections"]
        assert len(injections) >= 1
        assert injections[0]["params"]["action"] == "scramble_aria"


# ── 10. Evaluation scoring ──────────────────────────────────────────────

class TestEvaluationScoring:
    def test_full_pass_scores_1(self, client: TestClient):
        session = _create_session(client)
        sid = session["session_id"]
        target_id = session["resolved_targets"]["target_email_id"]

        # Do the task: star the target email
        client.post(
            f"/api/env/gmail/emails/{target_id}/star",
            json={"session_id": sid},
        )

        result = _evaluate(client, session_id=sid, task_id="gmail_star_email")

        assert result["success"] is True
        assert result["score"] >= 0.8  # 1.0 base - possible small negative penalty

    def test_session_metadata_persisted(self, client: TestClient):
        """Verify the public session summary exposes degradation, not internal seed."""
        session = _create_session(client, seed=42, degradation={
            "variant_id": "test_meta",
            "base_task_id": "gmail_star_email",
            "target_primitive": "patience",
            "description": "meta test",
            "injections": [],
        })
        sid = session["session_id"]

        resp = client.get(f"/api/env/gmail/session/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "seed" not in data
        assert data["session_id"] == sid
        assert data["title"] == "Star a Specific Email"
        assert data["degradation_active"] is True
        assert "degradation" not in data


@pytest.mark.parametrize(
    "env_id,task_id,variant_filename",
    [
        ("amazon", "amazon_account_overhaul_and_shop", "amazon_account_overhaul_and_shop__address_retry_v2.yaml"),
        ("booking", "booking_account_security_and_payment", "booking_account_security_and_payment__exploration.yaml"),
        ("gmail", "gmail_access_review_audit", "gmail_access_review_audit__state_tracking.yaml"),
        ("reddit", "reddit_account_cleanup", "reddit_account_cleanup__engagement_retry_v2.yaml"),
        ("robinhood", "rh_add_to_watchlist", "rh_add_to_watchlist__ticker_twin.yaml"),
    ],
)
def test_reset_endpoint_recreates_session_and_preserves_variant(
    client: TestClient,
    env_id: str,
    task_id: str,
    variant_filename: str,
) -> None:
    create = client.post(
        f"/api/env/{env_id}/session",
        json={
            "task_id": task_id,
            "seed": 42,
            "variant_filename": variant_filename,
        },
        headers=controller_headers(),
    )
    assert create.status_code == 200, create.text
    first = create.json()
    first_sid = first["session_id"]

    summary = client.get(f"/api/env/{env_id}/session/{first_sid}")
    assert summary.status_code == 200, summary.text
    # Public session summary omits the `degradation` dict by design; only the
    # boolean `degradation_active` flag is exposed. Variant preservation is
    # covered indirectly via the instruction/start_path equality below.
    assert summary.json().get("degradation_active") is True

    reset = client.post(
        f"/api/env/{env_id}/session/{first_sid}/reset",
        headers=controller_headers(),
    )
    assert reset.status_code == 200, reset.text
    second = reset.json()
    second_sid = second["session_id"]

    assert second_sid != first_sid
    assert second["start_path"] == first["start_path"]
    assert second["instruction"] == first["instruction"]

    old_summary = client.get(f"/api/env/{env_id}/session/{first_sid}")
    assert old_summary.status_code == 404

    new_summary = client.get(f"/api/env/{env_id}/session/{second_sid}")
    assert new_summary.status_code == 200, new_summary.text
    assert new_summary.json().get("degradation_active") is True
