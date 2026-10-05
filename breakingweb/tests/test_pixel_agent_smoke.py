"""Smoke tests for the pixel-mode VLM agent.

These tests stub the OpenAI client so no network calls or API keys are needed.
We verify:
  1. The agent instantiates without an API key.
  2. `act(obs)` returns a valid BrowserGym coord-action string.
  3. <think>...</think> reasoning is captured into `_last_thought`.
  4. Normalized 0-1000 coords get transformed to pixel coords when normalize=True.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np

from breakingweb.pixel_agent import (
    PixelLLMAgent,
    VALID_COORD_ACTIONS,
    _extract_thinking_and_action,
    _transform_normalized_to_pixel,
    _try_parse_single_action,
)


# -----------------------------------------------------------------------------
# Pure-function tests (no agent, no client)
# -----------------------------------------------------------------------------

def test_extract_thinking_with_think_tags():
    raw = "<think>I see a Save button at center.</think>\nmouse_click(500, 300)"
    th, act = _extract_thinking_and_action(raw)
    assert th == "I see a Save button at center."
    assert act == "mouse_click(500, 300)"


def test_extract_action_no_think_tags():
    raw = "I'll click the button.\nmouse_click(640, 360)"
    _, act = _extract_thinking_and_action(raw)
    assert act == "mouse_click(640, 360)"


def test_extract_action_inside_code_fence():
    raw = "Reasoning here.\n```\nkeyboard_type('hello')\n```"
    _, act = _extract_thinking_and_action(raw)
    assert act == "keyboard_type('hello')"


def test_extract_rejects_invalid_action_name():
    """Functions outside VALID_COORD_ACTIONS shouldn't be returned."""
    raw = "around(500, 500)"
    _, act = _extract_thinking_and_action(raw)
    assert act is None


def test_try_parse_single_action_clean():
    assert _try_parse_single_action("mouse_click(500, 300)") == "mouse_click(500, 300)"
    assert _try_parse_single_action("noop(1000)") == "noop(1000)"
    assert _try_parse_single_action("send_msg_to_user('done')") == "send_msg_to_user('done')"
    assert _try_parse_single_action("not_a_real_action(1)") is None


def test_transform_normalized_to_pixel_2coord():
    out = _transform_normalized_to_pixel("mouse_click(500, 500)", 1280, 720)
    assert out == "mouse_click(640, 360)"


def test_transform_normalized_to_pixel_4coord():
    out = _transform_normalized_to_pixel(
        "mouse_drag_and_drop(100, 100, 900, 500)", 1000, 1000
    )
    assert out == "mouse_drag_and_drop(100, 100, 900, 500)"


def test_transform_keeps_non_coord_actions():
    """Actions like scroll(0, 300) shouldn't be transformed (delta in pixels)."""
    out = _transform_normalized_to_pixel("scroll(0, 300)", 1280, 720)
    assert out == "scroll(0, 300)"


def test_valid_coord_actions_includes_essentials():
    for fn in ("mouse_click", "keyboard_type", "send_msg_to_user", "noop", "scroll"):
        assert fn in VALID_COORD_ACTIONS


# -----------------------------------------------------------------------------
# Agent-level tests with a mocked OpenAI client
# -----------------------------------------------------------------------------

class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeChatCompletions:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._response_text)


class _FakeChat:
    def __init__(self, response_text: str):
        self.completions = _FakeChatCompletions(response_text)


class _FakeOpenAIClient:
    def __init__(self, response_text: str):
        self.chat = _FakeChat(response_text)


def _fake_screenshot(w: int = 1280, h: int = 720) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _build_agent(response_text: str, normalize: bool = True) -> PixelLLMAgent:
    # Skip the live API probe — _build_agent installs a fake client immediately
    # afterward, so we can't reach the real Gemini service from this test.
    os.environ["WAB_PIXEL_SKIP_PROBE"] = "1"
    agent = PixelLLMAgent(
        model="dummy-model",
        provider="gemini",
        normalize_coordinates=normalize,
    )
    agent.client = _FakeOpenAIClient(response_text)
    return agent


def test_agent_act_basic_normalized():
    """Agent receives screenshot, returns transformed pixel-coord action."""
    agent = _build_agent(
        "<think>Center button looks right.</think>\nmouse_click(500, 500)",
        normalize=True,
    )
    obs = {"goal": "click center", "screenshot": _fake_screenshot(1280, 720)}
    action = agent.act(obs)
    # 0-1000 → pixels at 1280x720 → (640, 360)
    assert action == "mouse_click(640, 360)"
    assert agent._last_thought == "Center button looks right."
    assert len(agent.action_history) == 1


def test_agent_act_pixel_mode_no_transform():
    """When normalize_coordinates=False, the model's pixel output is kept as-is."""
    agent = _build_agent("mouse_click(640, 360)", normalize=False)
    obs = {"goal": "pixel mode", "screenshot": _fake_screenshot(1280, 720)}
    action = agent.act(obs)
    assert action == "mouse_click(640, 360)"


def test_agent_act_invalid_then_noop():
    """If the model never outputs a valid action across retries, fall back to noop."""
    agent = _build_agent("around(500, 500)", normalize=True)
    obs = {"goal": "x", "screenshot": _fake_screenshot()}
    action = agent.act(obs)
    assert action == "noop(1000)"


def test_agent_reset_clears_history():
    agent = _build_agent("mouse_click(500, 500)", normalize=True)
    obs = {"goal": "x", "screenshot": _fake_screenshot()}
    agent.act(obs)
    assert len(agent.action_history) == 1
    agent.reset()
    assert agent.action_history == []
    assert agent.thinking_history == []
    assert agent._last_thought == ""


def test_agent_conversation_property():
    agent = _build_agent("mouse_click(500, 500)", normalize=True)
    obs = {"goal": "x", "screenshot": _fake_screenshot()}
    agent.act(obs)
    convo = agent.conversation
    assert any(m.get("role") == "assistant" for m in convo)


def test_loop_detection_aborts_after_repeated_actions():
    """When the agent emits the same action 5x in a row, act() should swap in
    a send_msg_to_user('infeasible: ...') call so the episode terminates
    without burning the full max_steps budget on a stuck loop.
    """
    os.environ["WAB_PIXEL_LOOP_THRESHOLD"] = "5"
    agent = _build_agent("mouse_click(500, 500)", normalize=True)
    obs = {"goal": "x", "screenshot": _fake_screenshot()}
    # First 4 calls return the normal action
    for _ in range(4):
        action = agent.act(obs)
        assert "send_msg_to_user" not in action
    # 5th call still returns the normal action (it gets appended, then
    # detected on the *next* call once the tail is uniform)
    action5 = agent.act(obs)
    # 6th call: tail of last 5 is identical → loop detected → abort
    action6 = agent.act(obs)
    assert "send_msg_to_user" in action6 and "infeasible" in action6, action6
    del os.environ["WAB_PIXEL_LOOP_THRESHOLD"]
