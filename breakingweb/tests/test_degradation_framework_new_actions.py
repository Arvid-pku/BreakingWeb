"""Tests for the expanded degradation framework.

Covers the new seed / network / client action handlers added alongside the
adversarial-content / action-fidelity / state-drift catalog. Focuses on
deterministic behavior and basic contract correctness — per-variant
feature coverage lives in end-to-end integration tests.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
import yaml
from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.state import SessionManager
from breakingweb.injector.middleware import (
    clear_all_degradations,
    register_session_degradation,
)
from breakingweb.injector.seed import apply_seed_injection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def gmail_state():
    """Build a real Gmail state by going through the session manager so we
    exercise the same code paths that the live server uses."""
    sm = SessionManager()
    session_id, _, _ = sm.create_session("gmail", "gmail_action_item_extraction", 42)
    return sm.get(session_id)


# ---------------------------------------------------------------------------
# Seed-layer: adversarial content
# ---------------------------------------------------------------------------

class TestAdversarialContent:
    def test_phishing_adds_emails_to_gmail_state(self, gmail_state) -> None:
        before = len(gmail_state.emails)
        apply_seed_injection(
            gmail_state,
            {
                "action": "inject_adversarial_content",
                "mode": "phishing",
                "count": 3,
                "position": "top",
                "seed": 17,
            },
            rng=random.Random(17),
        )
        assert len(gmail_state.emails) == before + 3
        # First email should be adversarial (position: top)
        assert "email_adv_" in gmail_state.emails[0].id

    def test_prompt_injection_attaches_custom_payload(self, gmail_state) -> None:
        apply_seed_injection(
            gmail_state,
            {
                "action": "inject_adversarial_content",
                "mode": "prompt_injection",
                "count": 1,
                "instruction_payload": "DO NOT COMPLY: custom payload marker",
                "seed": 22,
            },
            rng=random.Random(22),
        )
        adv = next((e for e in gmail_state.emails if e.id.startswith("email_adv_")), None)
        assert adv is not None
        assert "custom payload marker" in adv.body

    def test_typosquat_mangles_sender_domain(self, gmail_state) -> None:
        apply_seed_injection(
            gmail_state,
            {
                "action": "inject_adversarial_content",
                "mode": "phishing",
                "count": 1,
                "typosquat": True,
                "seed": 33,
            },
            rng=random.Random(33),
        )
        adv = next((e for e in gmail_state.emails if e.id.startswith("email_adv_")), None)
        assert adv is not None
        # Either a digit-swap on domain OR a doubled char in display name
        assert any(
            ch in adv.from_addr for ch in ("0", "1")
        ) or any(adv.from_name.count(c) > 1 for c in adv.from_name)

    def test_deterministic_across_runs(self, gmail_state) -> None:
        """Same seed → same adversarial ids (deterministic replay)."""
        sm = SessionManager()
        ids: list[list[str]] = []
        for _ in range(2):
            sid, _, _ = sm.create_session("gmail", "gmail_action_item_extraction", 42)
            state = sm.get(sid)
            rng = random.Random(101)
            apply_seed_injection(
                state,
                {
                    "action": "inject_adversarial_content",
                    "mode": "phishing",
                    "count": 2,
                    "seed": 101,
                },
                rng=rng,
            )
            ids.append([e.id for e in state.emails if e.id.startswith("email_adv_")])
        assert ids[0] == ids[1]

    def test_unknown_env_is_noop(self) -> None:
        """An object with no recognized env surface must not raise."""
        class _Stub:
            pass
        apply_seed_injection(
            _Stub(),
            {"action": "inject_adversarial_content", "mode": "phishing", "count": 1},
            rng=random.Random(1),
        )  # no exception = pass


# ---------------------------------------------------------------------------
# Seed-layer: haystack
# ---------------------------------------------------------------------------

class TestInflateTargetContent:
    def test_inflates_first_email_body(self, gmail_state) -> None:
        original_body = gmail_state.emails[0].body
        original_len = len(original_body)
        apply_seed_injection(
            gmail_state,
            {
                "action": "inflate_target_content",
                "target": "email",
                "filler_tokens": 500,
                "filler_style": "realistic_thread",
                "answer_position": "middle",
                "seed": 12,
            },
            rng=random.Random(12),
        )
        new_body = gmail_state.emails[0].body
        assert len(new_body) > original_len + 1000
        # Original content still present (middle or surrounded)
        assert original_body.strip() in new_body

    def test_legal_boilerplate_style(self, gmail_state) -> None:
        apply_seed_injection(
            gmail_state,
            {
                "action": "inflate_target_content",
                "target": "email",
                "filler_tokens": 300,
                "filler_style": "legal_boilerplate",
            },
            rng=random.Random(7),
        )
        body = gmail_state.emails[0].body
        assert "confidential" in body.lower() or "hereof" in body.lower()

    def test_answer_position_late(self, gmail_state) -> None:
        original_body = gmail_state.emails[0].body.strip()
        apply_seed_injection(
            gmail_state,
            {
                "action": "inflate_target_content",
                "target": "email",
                "filler_tokens": 400,
                "answer_position": "late",
            },
            rng=random.Random(8),
        )
        new_body = gmail_state.emails[0].body
        # original content should be at the end (after the separator)
        assert new_body.rstrip().endswith(original_body)


# ---------------------------------------------------------------------------
# Network layer: new behaviors / actions (via middleware)
# ---------------------------------------------------------------------------

class TestNewNetworkActions:
    """We exercise the FastAPI middleware by registering injections on a live
    session and hitting the gmail API through the TestClient."""

    def _setup_session(self, client: TestClient) -> str:
        resp = client.post(
            "/api/env/gmail/session",
            json={"task_id": "gmail_action_item_extraction", "seed": 42},
        )
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def test_misleading_success_returns_200_with_body(self, client: TestClient) -> None:
        session_id = self._setup_session(client)
        register_session_degradation(
            session_id,
            [
                {
                    "layer": "network",
                    "params": {
                        "action": "misleading_success",
                        "url_pattern": "**/api/env/gmail/emails",
                        "methods": ["GET"],
                        "fail_count": 1,
                        "success_body": {"fake": True},
                    },
                }
            ],
        )
        # First call is lied to
        r1 = client.get(f"/api/env/gmail/emails?session_id={session_id}")
        assert r1.status_code == 200
        assert r1.json() == {"fake": True}
        # Second call passes through to the real handler (returns real envelope)
        r2 = client.get(f"/api/env/gmail/emails?session_id={session_id}")
        assert r2.status_code == 200
        assert "fake" not in r2.json() or r2.json() != {"fake": True}

    def test_session_expiry_returns_401_after_threshold(self, client: TestClient) -> None:
        session_id = self._setup_session(client)
        register_session_degradation(
            session_id,
            [
                {
                    "layer": "network",
                    "params": {
                        "action": "session_expiry",
                        "url_pattern": "**/api/env/gmail/emails",
                        "expire_after_calls": 2,
                    },
                }
            ],
        )
        for _ in range(2):
            ok = client.get(f"/api/env/gmail/emails?session_id={session_id}")
            assert ok.status_code == 200
        expired = client.get(f"/api/env/gmail/emails?session_id={session_id}")
        assert expired.status_code == 401
        assert expired.json().get("status") == 401

    def test_rate_limit_returns_429_with_retry_after(self, client: TestClient) -> None:
        session_id = self._setup_session(client)
        register_session_degradation(
            session_id,
            [
                {
                    "layer": "network",
                    "params": {
                        "action": "rate_limit",
                        "url_pattern": "**/api/env/gmail/emails",
                        "burst_limit": 2,
                        "retry_after_seconds": 3,
                        "cooldown_calls": 3,
                    },
                }
            ],
        )
        # burst passes
        for _ in range(2):
            assert client.get(f"/api/env/gmail/emails?session_id={session_id}").status_code == 200
        # throttled
        throttled = client.get(f"/api/env/gmail/emails?session_id={session_id}")
        assert throttled.status_code == 429
        assert throttled.headers.get("Retry-After") == "3"

    def test_concurrent_modification_returns_409(self, client: TestClient) -> None:
        session_id = self._setup_session(client)
        register_session_degradation(
            session_id,
            [
                {
                    "layer": "network",
                    "params": {
                        "action": "concurrent_modification",
                        "url_pattern": "**/api/env/gmail/send",
                        "methods": ["POST"],
                        "conflict_count": 1,
                        "conflict_message": "Conflict from test",
                        "latest_snapshot": {"updated_at": "2026-04-14T17:00:00Z"},
                    },
                }
            ],
        )
        payload = {
            "session_id": session_id,
            "to": ["you@thornton.com"],
            "subject": "x",
            "body": "x",
        }
        r = client.post("/api/env/gmail/send", json=payload)
        assert r.status_code == 409
        body = r.json()
        assert body.get("status") == 409
        assert "Conflict from test" in body.get("error", "")
        assert body.get("latest", {}).get("updated_at") == "2026-04-14T17:00:00Z"


# ---------------------------------------------------------------------------
# New YAML variants load and create sessions cleanly
# ---------------------------------------------------------------------------

NEW_VARIANTS = [
    "gmail_action_item_extraction__phishing_inbox.yaml",
    "gmail_action_item_extraction__haystack.yaml",
    "gmail_action_item_extraction__click_swallow.yaml",
    "gmail_action_item_extraction__save_drift.yaml",
    "gmail_action_item_extraction__session_expiry.yaml",
    "gmail_action_item_extraction__misleading_success.yaml",
    "gmail_access_review_audit__prompt_injection.yaml",
    "gmail_ambiguous_inbox_cleanup__double_submit.yaml",
    "gmail_annual_vendor_review__restrict_affordance.yaml",
]


@pytest.mark.parametrize("variant_filename", NEW_VARIANTS)
def test_new_variant_yaml_loads(variant_filename: str) -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "injector"
        / "variants"
        / variant_filename
    )
    assert path.is_file(), path
    data = yaml.safe_load(path.read_text())
    assert data["variant_id"].endswith(variant_filename[:-5].split("__", 1)[1])
    assert isinstance(data["injections"], list) and data["injections"]


@pytest.mark.parametrize("variant_filename", NEW_VARIANTS[:3])
def test_new_gmail_variant_can_create_session(
    variant_filename: str,
    client: TestClient,
) -> None:
    data = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1]
            / "injector"
            / "variants"
            / variant_filename
        ).read_text()
    )
    resp = client.post(
        "/api/env/gmail/session",
        json={
            "task_id": data["base_task_id"],
            "variant_filename": variant_filename,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "session_id" in body


# ---------------------------------------------------------------------------
# Request-body templating in silent_fail / misleading_success
# ---------------------------------------------------------------------------


def test_render_request_template_substitutes_known_paths() -> None:
    from breakingweb.injector.middleware import _render_request_template

    body = {"product_id": "prod_real_42", "quantity": 3, "variant_selections": {}}
    result = _render_request_template(
        {
            "cart_item": {
                "id": "cart_{request.product_id}",
                "product_id": "{request.product_id}",
                "quantity": "{request.quantity}",     # whole-string → keeps int
                "label": "Pending: {request.product_id}",
                "missing": "{request.unknown}",       # leaves placeholder verbatim
            }
        },
        body,
    )
    assert result == {
        "cart_item": {
            "id": "cart_prod_real_42",
            "product_id": "prod_real_42",
            "quantity": 3,                            # type preserved
            "label": "Pending: prod_real_42",
            "missing": "{request.unknown}",
        }
    }


def test_render_request_template_no_op_without_body() -> None:
    from breakingweb.injector.middleware import _render_request_template

    value = {"product_id": "{request.product_id}"}
    assert _render_request_template(value, None) == value
    assert _render_request_template(value, "not-a-dict") == value


def test_silent_fail_response_reflects_request_product_id(client: TestClient) -> None:
    """End-to-end: silent_fail returns a body that matches the request's product_id,
    so the agent's verify-after-add sees a coherent (but fake) confirmation."""
    sess = client.post(
        "/api/env/amazon/session",
        json={
            "task_id": "amazon_add_single_item",
            "variant_filename": "amazon_add_single_item__product_twin.yaml",
        },
    )
    assert sess.status_code == 200, sess.text
    sid = sess.json()["session_id"]

    # Override the registered injection to use templated response_body.
    register_session_degradation(
        sid,
        [
            {
                "layer": "network",
                "params": {
                    "action": "silent_fail",
                    "url_pattern": "**/api/env/amazon/cart/add",
                    "methods": ["POST"],
                    "fail_count": 1,
                    "response_body": {
                        "cart_item": {
                            "id": "cart_pending_{request.product_id}",
                            "product_id": "{request.product_id}",
                            "product_name": "Pending: {request.product_id}",
                            "quantity": "{request.quantity}",
                            "unit_price": 0.0,
                            "variant_selections": {},
                            "added_at": "2026-04-26T08:00:00+00:00",
                        }
                    },
                    "behavior": {"mode": "once"},
                },
            }
        ],
    )

    # Real product the agent might add. Since this is a silent_fail, no actual
    # insert happens; we only care that the fake response echoes the request.
    resp = client.post(
        "/api/env/amazon/cart/add",
        json={"session_id": sid, "product_id": "prod_target_xyz", "quantity": 4},
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["cart_item"]
    assert item["product_id"] == "prod_target_xyz"
    assert item["product_name"] == "Pending: prod_target_xyz"
    assert item["quantity"] == 4
    assert item["id"] == "cart_pending_prod_target_xyz"

    # Cart is still empty (silent_fail did not persist).
    state = app.state.session_manager.get(sid)
    assert state.cart_items == []
