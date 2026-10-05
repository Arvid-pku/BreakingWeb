from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi import HTTPException

from breakingweb.agent_eval import run_episode
from breakingweb.app import MANIFEST_FINGERPRINT
from breakingweb.backend.routes.gmail import SessionCreateRequest, create_session
from breakingweb.backend.state import SessionManager
from breakingweb.injector.middleware import (
    _normalize_progressive_stages,
    _progressive_delay_ms,
)
from breakingweb.injector.seed import apply_seed_injection
from breakingweb.injector.server import apply_server_injection
from breakingweb.runner import controller_headers, ensure_controller_secret
from breakingweb.task_rendering import render_template
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._schema import Check, EvalConfig, NegativeCheck
from breakingweb.tasks._registry import get_task

try:
    from breakingweb.browsergym_task import BreakingWebTask
except ModuleNotFoundError as exc:
    BreakingWebTask = None
    _BROWSERGYM_IMPORT_ERROR = exc
else:
    _BROWSERGYM_IMPORT_ERROR = None


def test_create_session_rejects_variant_task_mismatch() -> None:
    session_manager = SessionManager()

    with pytest.raises(HTTPException) as exc:
        create_session(
            SessionCreateRequest(
                task_id="gmail_board_briefing_prep",
                variant_filename="gmail_compliance_settings__patience.yaml",
            ),
            session_manager=session_manager,
        )

    assert exc.value.status_code == 400


def test_create_session_stores_seed_and_degradation_metadata() -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id="gmail_board_briefing_prep",
            seed=42,
            variant_filename="gmail_board_briefing_prep__label_trap.yaml",
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])

    assert state.seed == 42
    assert state.degradation["variant_id"] == "gmail_board_briefing_prep__label_trap"
    assert state.degradation["base_task_id"] == "gmail_board_briefing_prep"
    assert state.degradation["variant_filename"] == "gmail_board_briefing_prep__label_trap.yaml"


def test_create_session_accepts_string_based_confusing_decoys_variants() -> None:
    session_manager = SessionManager()

    for task_id, variant_filename in [
        ("gmail_thread_version_conflict", "gmail_thread_version_conflict__recap_trap.yaml"),
        ("gmail_thread_detective", "gmail_thread_detective__exploration.yaml"),
    ]:
        payload = create_session(
            SessionCreateRequest(
                task_id=task_id,
                seed=42,
                variant_filename=variant_filename,
            ),
            session_manager=session_manager,
        )

        state = session_manager.get(payload["session_id"])
        assert state.degradation["variant_filename"] == variant_filename


def test_render_template_preserves_exact_target_types() -> None:
    targets = {"email_ids": ["email_1", "email_2"], "count": 2}

    rendered = render_template(
        {
            "email_ids": "{target.email_ids}",
            "summary": "Need {target.count} emails",
        },
        targets,
    )

    assert rendered == {
        "email_ids": ["email_1", "email_2"],
        "summary": "Need 2 emails",
    }


def test_create_session_renders_degradation_target_params_before_seed_injection() -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id="gmail_thread_detective",
            seed=42,
            degradation={
                "variant_id": "test_hide_calendar_email",
                "base_task_id": "gmail_thread_detective",
                "target_primitive": "exploration",
                "description": "test",
                "injections": [
                    {
                        "layer": "seed",
                        "params": {
                            "action": "hide_in_non_obvious_location",
                            "email_id": "{target.calendar_email_id}",
                            "move_to_label": "updates",
                        },
                    }
                ],
            },
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])
    assert state.degradation["injections"][0]["params"]["email_id"] == state.resolved_targets["calendar_email_id"]
    assert state.get_email(state.resolved_targets["calendar_email_id"]).labels == ["updates"]


def test_thread_detective_exploration_variant_hides_calendar_email() -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id="gmail_thread_detective",
            seed=42,
            variant_filename="gmail_thread_detective__exploration.yaml",
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])
    calendar_email = state.get_email(state.resolved_targets["calendar_email_id"])
    assert calendar_email.labels == ["updates"]

def test_incident_postmortem_exploration_variant_hides_corrected_email() -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id="gmail_incident_postmortem_assembly",
            seed=42,
            variant_filename="gmail_incident_postmortem_assembly__exploration.yaml",
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])
    corrected_email = state.get_email(state.resolved_targets["corrected_email_id"])
    assert corrected_email.labels == ["updates"]


def test_hide_prerequisite_variants_always_specify_a_target() -> None:
    """Each hide_prerequisite injection must declare what to remove.

    Two valid shapes (see breakingweb/injector/server.py):
        legacy: label_name: "Foo"
        multi:  prerequisites: [{kind, name|email|key, ...}, ...]
    """
    variants_dir = Path(__file__).resolve().parents[1] / "injector" / "variants"

    for path in variants_dir.glob("*.yaml"):
        data = yaml.safe_load(path.read_text()) or {}
        for injection in data.get("injections", []):
            params = injection.get("params", {})
            if params.get("action") != "hide_prerequisite":
                continue
            has_legacy = bool(params.get("label_name"))
            prereqs = params.get("prerequisites") or []
            has_multi = isinstance(prereqs, list) and any(
                isinstance(p, dict) and (p.get("name") or p.get("email") or p.get("key"))
                for p in prereqs
            )
            assert has_legacy or has_multi, (
                f"{path.name} is missing label_name or prerequisites"
            )


def test_gmail_stale_email_and_search_variants_use_paginated_items_schema() -> None:
    variants_dir = Path(__file__).resolve().parents[1] / "injector" / "variants"
    required_page_keys = {"items", "page", "page_size", "pages", "total"}

    for path in sorted(variants_dir.glob("gmail_*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        for injection in data.get("injections", []):
            params = injection.get("params", {})
            if params.get("action") != "stale_data":
                continue

            url_pattern = str(params.get("url_pattern", ""))
            stale_body = params.get("stale_body")
            assert isinstance(stale_body, dict), f"{path.name} must define stale_body as a mapping"

            if "/api/env/gmail/contacts" in url_pattern:
                assert "contacts" not in stale_body, f"{path.name} must use items, not contacts"
                assert "items" in stale_body, f"{path.name} contacts stale_body must include items"
                assert isinstance(stale_body["items"], list), f"{path.name} items must be a list"
                continue

            if "/api/env/gmail/emails" not in url_pattern and "/api/env/gmail/search" not in url_pattern:
                continue

            assert "emails" not in stale_body, f"{path.name} must use items, not emails"
            assert required_page_keys.issubset(stale_body), (
                f"{path.name} must include paginated keys {sorted(required_page_keys)}"
            )
            assert isinstance(stale_body["items"], list), f"{path.name} items must be a list"

            if "/api/env/gmail/search" in url_pattern:
                assert "query" in stale_body, f"{path.name} search stale_body must include query"


def test_board_briefing_state_tracking_uses_email_decoys_not_contact_shuffle() -> None:
    variants_dir = Path(__file__).resolve().parents[1] / "injector" / "variants"
    data = yaml.safe_load((variants_dir / "gmail_board_briefing_prep__label_trap.yaml").read_text()) or {}
    actions = [injection.get("params", {}).get("action") for injection in data.get("injections", [])]

    assert "shuffle_contacts" not in actions
    assert "add_confusing_decoys" in actions


def test_seed_increase_distractors_anchor_to_task_recency() -> None:
    base_timestamp = datetime(2026, 7, 7, 11, 5, tzinfo=timezone.utc)
    state = SimpleNamespace(emails=[SimpleNamespace(timestamp=base_timestamp)])

    apply_seed_injection(state, {"action": "increase_distractors", "count": 5, "topical_count": 0})

    added = state.emails[1:]
    assert len(added) == 5
    assert min(email.timestamp for email in added) > datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_seed_plant_wrong_answer_defaults_to_recent_prominent_timestamp() -> None:
    base_timestamp = datetime(2026, 7, 7, 11, 5, tzinfo=timezone.utc)
    state = SimpleNamespace(emails=[SimpleNamespace(timestamp=base_timestamp)])

    apply_seed_injection(
        state,
        {
            "action": "plant_wrong_answer",
            "subject": "Wrong answer",
            "body": "Use the wrong setting.",
        },
    )

    planted = state.emails[0]
    assert planted.timestamp > base_timestamp
    assert planted.is_starred is True


def test_hide_in_non_obvious_location_can_match_subject_substrings() -> None:
    state = SimpleNamespace(
        emails=[
            SimpleNamespace(id="email_1", subject="Signal launch review action items", labels=["inbox"]),
            SimpleNamespace(id="email_2", subject="Unrelated topic", labels=["inbox"]),
        ]
    )

    apply_seed_injection(
        state,
        {
            "action": "hide_in_non_obvious_location",
            "subject_contains": "signal launch review action items",
            "move_to_label": "updates",
        },
    )

    assert state.emails[0].labels == ["updates"]
    assert state.emails[1].labels == ["inbox"]


class _TimestampState:
    def __init__(self) -> None:
        self.emails = [
            SimpleNamespace(
                timestamp=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
            )
        ]
        self.touched = False

    def touch(self) -> None:
        self.touched = True


def test_scramble_timestamps_preserves_datetime_values() -> None:
    state = _TimestampState()

    apply_server_injection(state, {"action": "scramble_timestamps", "seed": 7})

    assert isinstance(state.emails[0].timestamp, datetime)
    assert state.touched is True


class _LegacyEvalOnlyTask:
    eval = EvalConfig(
        checks=[Check(expr="True", desc="positive passes")],
        negative_checks=[
            NegativeCheck(expr="False", desc="penalty A", penalty=0.7),
            NegativeCheck(expr="False", desc="penalty B", penalty=0.6),
        ],
    )


def test_evaluator_rejects_legacy_eval_only_tasks() -> None:
    result = evaluate(
        _LegacyEvalOnlyTask(),
        server_state=SimpleNamespace(),
        targets={},
        trajectory=[],
    )

    assert result["success"] is False
    assert result["score"] == pytest.approx(0.0)
    assert "Legacy eval.checks are no longer supported" in result["reasoning"]


class _BenchmarkStateTask:
    canonical_diff = {
        "constraints": [
            {
                "desc": "search event recorded",
                "expr": (
                    "any(event.get('type') == 'search_submit' and 'budget' in "
                    "str(event.get('detail', {}).get('query', '')).lower() "
                    "for event in state.benchmark_state.get('events', []))"
                ),
                "severity": "critical",
            }
        ],
    }


def test_evaluator_can_check_client_benchmark_state_events() -> None:
    result = evaluate(
        _BenchmarkStateTask(),
        server_state=SimpleNamespace(
            benchmark_state={
                "events": [
                    {
                        "type": "search_submit",
                        "detail": {"query": 'subject:"Q4 Budget Summary"'},
                    }
                ]
            }
        ),
        targets={},
        trajectory=[],
    )

    assert result["success"] is True
    assert result["score"] == pytest.approx(1.0)


def test_search_and_star_passes_when_target_starred() -> None:
    session_manager = SessionManager()
    payload = create_session(
        SessionCreateRequest(task_id="gmail_search_and_star", seed=42),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])
    task = get_task("gmail_search_and_star")

    # Before starring: should fail
    before = evaluate(
        task,
        server_state=state,
        targets=state.resolved_targets,
        trajectory=[],
    )
    assert before["success"] is False

    # After starring: should pass (no search event required)
    state.toggle_star(state.resolved_targets["target_email_id"], True)
    after = evaluate(
        task,
        server_state=state,
        targets=state.resolved_targets,
        trajectory=[],
    )
    assert after["success"] is True


@pytest.mark.skipif(BreakingWebTask is None, reason="browsergym is not installed")
def test_browsergym_task_rejects_stale_server_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    task = BreakingWebTask(seed=42, task_id="gmail_search_and_star", server_port=8099)
    monkeypatch.setenv("BREAKINGWEB_CONTROLLER_SECRET", "test-controller-secret")

    monkeypatch.setattr("breakingweb.runner.wait_for_server", lambda host, port, timeout=2: True)
    monkeypatch.setattr(
        "breakingweb.browsergym_task._http_json",
        lambda url, **kwargs: {
            "status": "ok",
            "manifest_fingerprint": "stale-server",
        },
    )

    with pytest.raises(RuntimeError, match="does not match the local benchmark manifest"):
        task._ensure_server()

    monkeypatch.setattr(
        "breakingweb.browsergym_task._http_json",
        lambda url, **kwargs: {
            "status": "ok",
            "manifest_fingerprint": MANIFEST_FINGERPRINT,
        },
    )

    task._ensure_server()


def test_controller_secret_helpers_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREAKINGWEB_CONTROLLER_SECRET", raising=False)

    assert controller_headers() == {}

    secret = ensure_controller_secret()

    assert secret
    assert controller_headers() == {"X-WAB-Controller-Secret": secret}


def test_thread_detective_ignores_quoted_conflicting_times() -> None:
    server_state = SimpleNamespace(
        sent=[
            SimpleNamespace(
                id="sent_1",
                to=["sofia.rivera@vertexlab.io"],
                cc=[],
                body=(
                    "11:00 AM works on my side, so let's confirm that.\n\n"
                    "On 3/2/2026, 3:20:00 AM, Sofia Rivera wrote:\n"
                    "Could we use 4:00 PM for the Cedar policy review?"
                ),
                in_reply_to="email_123",
                thread_id="thread_456",
                forwarded_from_id=None,
            )
        ],
        _initial_state_copy=SimpleNamespace(sent=[]),
    )
    server_state.get_email = lambda _email_id: SimpleNamespace(is_read=True)

    result = evaluate(
        get_task("gmail_thread_detective"),
        server_state=server_state,
        targets={
            "sender_email": "sofia.rivera@vertexlab.io",
            "calendar_email_id": "email_calendar",
            "correct_time": "11:00 AM",
            "wrong_times": ["4:00 PM", "2:30 PM"],
            "most_recent_thread_id": "thread_456",
        },
        trajectory=[],
    )

    assert result["success"] is True
    assert result["score"] == pytest.approx(1.0)


def test_progressive_delay_respects_after_call_thresholds() -> None:
    stages = [
        {"after_call": 0, "delay_ms": 1000},
        {"after_call": 3, "delay_ms": 3000},
        {"after_call": 8, "delay_ms": 5000},
    ]

    assert _progressive_delay_ms(1, stages, 0) == 1000
    assert _progressive_delay_ms(3, stages, 0) == 1000
    assert _progressive_delay_ms(4, stages, 0) == 3000
    assert _progressive_delay_ms(8, stages, 0) == 3000
    assert _progressive_delay_ms(9, stages, 0) == 5000


def test_progressive_stage_aliases_normalize_to_after_call_thresholds() -> None:
    assert _normalize_progressive_stages(
        [
            {"requests": 2, "delay_ms": 2000},
            {"requests": 3, "delay_ms": 4000},
        ],
        0,
    ) == [
        {"after_call": 0, "delay_ms": 2000},
        {"after_call": 2, "delay_ms": 4000},
    ]

    assert _normalize_progressive_stages(
        [
            {"call_number": 1, "delay_ms": 1000},
            {"call_number": 2, "delay_ms": 2000},
            {"call_number": 3, "delay_ms": 3000},
        ],
        0,
    ) == [
        {"after_call": 0, "delay_ms": 1000},
        {"after_call": 1, "delay_ms": 2000},
        {"after_call": 2, "delay_ms": 3000},
    ]

    assert _normalize_progressive_stages(
        [
            {"until_count": 2, "delay_ms": 1000},
            {"until_count": 4, "delay_ms": 3000},
            {"delay_ms": 2000},
        ],
        0,
    ) == [
        {"after_call": 0, "delay_ms": 1000},
        {"after_call": 2, "delay_ms": 3000},
        {"after_call": 4, "delay_ms": 2000},
    ]


class _SeedAwareEnv:
    def __init__(self) -> None:
        self.seen_seed = None

    def reset(self, seed=None):
        self.seen_seed = seed
        return {"goal": "Test goal"}, {"task_info": {"task_id": "dummy"}}

    def step(self, action):
        return (
            {"last_action_error": ""},
            0.0,
            True,
            False,
            {"task_info": {"evaluation": {"score": 0.0, "success": False, "reasoning": "done"}}},
        )


class _OneShotAgent:
    conversation: list[dict] = []

    def reset(self, obs):
        self.conversation = [{"role": "user", "content": str(obs)}]

    def act(self, obs):
        return "send_msg_to_user('done')"


def test_run_episode_passes_seed_and_marks_terminated_run_completed() -> None:
    env = _SeedAwareEnv()
    episode = run_episode(
        env,
        _OneShotAgent(),
        episode_seed=123,
        max_steps=1,
        verbose=False,
    )

    assert env.seen_seed == 123
    assert episode["completed"] is True
    assert episode["trajectory"][0]["raw_action"] == "send_msg_to_user('done')"
    assert episode["trajectory"][0]["action"] == {"action": "finish", "answer": "done"}
    assert episode["trajectory"][0]["status"] == "FINISH"
