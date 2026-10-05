from __future__ import annotations

from breakingweb.visualize import (
    _prepare_result_for_js,
    _truncate_messages,
    _normalize_step_targets,
    generate_html,
)


def test_truncate_messages_keeps_first_user_message_full() -> None:
    long_content = "x" * 800
    messages = [
        {"role": "user", "content": long_content},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": long_content},
    ]

    truncated = _truncate_messages(messages)

    assert truncated[0]["content"] == long_content
    assert truncated[2]["content"].endswith("[... observation truncated ...]")
    assert len(truncated[2]["content"]) < len(long_content)


def test_normalize_step_targets_nests_flat_ref_shape() -> None:
    step = {
        "step": 1,
        "targets": {
            "ref": "172",
            "role": "button",
            "name": "Save draft",
            "nth": 0,
        },
    }

    normalized = _normalize_step_targets(step)

    assert normalized["targets"] == {
        "ref": {
            "bid": "172",
            "role": "button",
            "name": "Save draft",
            "nth": 0,
        }
    }


def test_normalize_step_targets_preserves_nested_drag_refs() -> None:
    step = {
        "step": 2,
        "targets": {
            "from_ref": "src-1",
            "to_ref": {
                "role": "row",
                "name": "Done",
                "selector": "article:nth-of-type(2)",
            },
        },
    }

    normalized = _normalize_step_targets(step)

    assert normalized["targets"]["from_ref"] == {"bid": "src-1"}
    assert normalized["targets"]["to_ref"] == {
        "role": "row",
        "name": "Done",
        "selector": "article:nth-of-type(2)",
    }


def test_prepare_result_for_js_normalizes_targets_and_truncates_messages() -> None:
    long_content = "x" * 800
    result = {
        "task_id": "gmail_reply_simple",
        "agent": {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "initial"},
                {"role": "user", "content": long_content},
            ],
            "trajectory": [
                {
                    "step": 1,
                    "targets": {
                        "ref": "91",
                        "role": "link",
                        "name": "Open unread thread Hello",
                    },
                }
            ],
        },
    }

    prepared = _prepare_result_for_js(result)

    assert prepared["agent"]["trajectory"][0]["targets"] == {
        "ref": {
            "bid": "91",
            "role": "link",
            "name": "Open unread thread Hello",
        }
    }
    assert prepared["agent"]["messages"][2]["content"].endswith(
        "[... observation truncated ...]"
    )


def test_generate_html_embeds_replay_url_and_variant_helpers() -> None:
    data = {
        "agent": {"model": "test-model", "provider": "test-provider"},
        "summary": {"total_tasks": 1},
        "results": [
            {
                "task_id": "gmail_reply_simple",
                "title": "Reply Simple",
                "instruction": "Reply to the email.",
                "difficulty": "easy",
                "evaluation": {"score": 1.0, "success": True},
                "agent": {
                    "trajectory": [
                        {
                            "step": 1,
                            "targets": {
                                "ref": "91",
                                "role": "button",
                                "name": "Send reply",
                            },
                        }
                    ],
                    "messages": [],
                },
                "replay": {
                    "kind": "env",
                    "env_id": "gmail",
                    "task_id": "gmail_reply_simple",
                    "seed": 42,
                    "base_url": "/env/gmail",
                    "start_path": "/inbox?label=inbox",
                    "variant_filename": "gmail_reply_simple__retry.yaml",
                },
                "degradation": {
                    "variant_filename": "gmail_reply_simple__retry.yaml",
                },
            }
        ],
    }

    html = generate_html(data, "")

    assert "buildReplayRequestPayload" in html
    assert "buildReplayPageUrl" in html
    assert "searchParams.set('session', sessionId)" in html
    assert "payload.variant_filename = variantFilename;" in html
    assert '"bid": "91"' in html
