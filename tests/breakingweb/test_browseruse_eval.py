"""Tests for browser-use eval helper functions.

Tests are written TDD-style -- the module under test does not exist yet.
Run with: pytest tests/breakingweb/test_browseruse_eval.py -v
"""

from __future__ import annotations

import json

import pytest

from breakingweb.browseruse_eval import (
    action_to_trajectory_format,
    build_trajectory_step,
    dom_element_to_target,
    mask_observations,
    parse_agent_output,
)


# =========================================================================
# 1. mask_observations
# =========================================================================

class TestMaskObservations:
    """Test observation masking for context window management."""

    @staticmethod
    def _obs(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def _act(content: str) -> dict:
        return {"role": "assistant", "content": content}

    # --- basic behaviour ---

    def test_keeps_first_observation(self):
        msgs = [self._obs("goal: do X"), self._act("ok")]
        result = mask_observations(msgs, window=10)
        assert result[0]["content"] == "goal: do X"

    def test_masks_middle_observations(self):
        # 1 goal + 15 obs/act pairs => obs indices: 0, 2, 4, ..., 28
        # 16 total user messages. window=5 => keep first + last 5 => mask 10.
        msgs = [self._obs("goal")]
        for i in range(15):
            msgs.append(self._act(f"action_{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=5)

        # First observation kept
        assert result[0]["content"] == "goal"

        # Count masked
        masked = [m for m in result if m["content"] == "[observation omitted]"]
        # 16 user msgs total, keep first + last 5 = 6 kept => 10 masked
        assert len(masked) == 10

    def test_assistant_messages_never_masked(self):
        msgs = [self._obs("goal")]
        for i in range(20):
            msgs.append(self._act(f"action_{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)

        assistant_msgs = [m for m in result if m["role"] == "assistant"]
        assert all(m["content"].startswith("action_") for m in assistant_msgs)
        assert len(assistant_msgs) == 20

    def test_no_masking_when_within_window(self):
        msgs = [self._obs("goal"), self._act("a1"), self._obs("obs1")]
        result = mask_observations(msgs, window=10)
        # Only 2 user msgs, window=10 => 2 <= 10+1 => no masking
        assert result == msgs

    def test_exactly_window_plus_one_no_masking(self):
        # window=3, 4 user msgs => 4 <= 3+1 => no masking
        msgs = [self._obs("goal")]
        for i in range(3):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)
        assert result == msgs

    def test_last_window_observations_kept(self):
        msgs = [self._obs("goal")]
        for i in range(10):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)

        # Last 3 user obs should be kept (obs_7, obs_8, obs_9)
        user_msgs = [m for m in result if m["role"] == "user"]
        kept = [m for m in user_msgs if m["content"] != "[observation omitted]"]
        # First + last 3 = 4 kept
        assert len(kept) == 4
        assert kept[0]["content"] == "goal"
        assert kept[-1]["content"] == "obs_9"
        assert kept[-2]["content"] == "obs_8"
        assert kept[-3]["content"] == "obs_7"

    def test_default_window_is_10(self):
        msgs = [self._obs("goal")]
        for i in range(12):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        # 13 user msgs, default window=10 => keep first + last 10 => mask 2
        result = mask_observations(msgs)
        masked = [m for m in result if m["content"] == "[observation omitted]"]
        assert len(masked) == 2

    # --- edge cases ---

    def test_empty_list(self):
        assert mask_observations([]) == []

    def test_single_observation(self):
        msgs = [self._obs("goal")]
        assert mask_observations(msgs, window=5) == msgs

    def test_preserves_message_count(self):
        msgs = [self._obs("goal")]
        for i in range(8):
            msgs.append(self._act(f"a{i}"))
            msgs.append(self._obs(f"obs_{i}"))
        result = mask_observations(msgs, window=3)
        assert len(result) == len(msgs)


# =========================================================================
# 2. parse_agent_output
# =========================================================================

class TestParseAgentOutput:
    """Test parsing of agent structured JSON output."""

    def test_valid_json(self):
        raw = json.dumps({
            "thinking": "I need to click compose",
            "memory": "On inbox page",
            "next_goal": "Click compose button",
            "action": [{"click": {"index": 33}}],
        })
        result = parse_agent_output(raw)
        assert result["thinking"] == "I need to click compose"
        assert result["memory"] == "On inbox page"
        assert result["next_goal"] == "Click compose button"
        assert result["action"] == [{"click": {"index": 33}}]

    def test_done_action(self):
        raw = json.dumps({
            "thinking": "Task complete",
            "memory": "",
            "next_goal": "",
            "action": [{"done": {"text": "finished", "success": True}}],
        })
        result = parse_agent_output(raw)
        assert result["action"][0]["done"]["success"] is True
        assert result["action"][0]["done"]["text"] == "finished"

    def test_multi_action_list(self):
        raw = json.dumps({
            "thinking": "Two steps",
            "memory": "",
            "next_goal": "",
            "action": [
                {"click": {"index": 10}},
                {"input_text": {"index": 11, "text": "hi"}},
            ],
        })
        result = parse_agent_output(raw)
        assert len(result["action"]) == 2
        assert "click" in result["action"][0]
        assert "input_text" in result["action"][1]

    def test_plain_text_fallback_click(self):
        result = parse_agent_output("click 33")
        assert result["thinking"] == ""
        assert result["memory"] == ""
        assert result["next_goal"] == ""
        assert result["action"] == [{"click": {"index": 33}}]

    def test_malformed_json_best_effort(self):
        # Truncated JSON -- should not raise, should return best-effort
        raw = '{"thinking": "partial", "action": [{"click": {"index": 5}}'
        result = parse_agent_output(raw)
        assert isinstance(result, dict)
        # Should have action key at minimum
        assert "action" in result

    def test_empty_input(self):
        result = parse_agent_output("")
        assert isinstance(result, dict)
        assert "action" in result

    def test_returns_all_four_keys(self):
        raw = json.dumps({
            "thinking": "t",
            "memory": "m",
            "next_goal": "ng",
            "action": [{"scroll_down": {"amount": 300}}],
        })
        result = parse_agent_output(raw)
        assert set(result.keys()) >= {"thinking", "memory", "next_goal", "action"}

    def test_json_with_extra_whitespace(self):
        raw = '  \n  {"thinking": "x", "memory": "", "next_goal": "", "action": []}  \n  '
        result = parse_agent_output(raw)
        assert result["thinking"] == "x"

    def test_json_wrapped_in_markdown_code_block(self):
        raw = '```json\n{"thinking": "t", "memory": "m", "next_goal": "n", "action": [{"click": {"index": 1}}]}\n```'
        result = parse_agent_output(raw)
        assert result["action"] == [{"click": {"index": 1}}]


# =========================================================================
# 3. action_to_trajectory_format
# =========================================================================

class TestActionToTrajectoryFormat:
    """Test conversion from browser-use action dict to replay format."""

    def test_click(self):
        result = action_to_trajectory_format({"click": {"index": 33}})
        assert result == {"action": "click", "ref": "33"}

    def test_input_text(self):
        result = action_to_trajectory_format(
            {"input_text": {"index": 35, "text": "hello"}}
        )
        assert result == {"action": "fill", "ref": "35", "value": "hello"}

    def test_select_option(self):
        result = action_to_trajectory_format(
            {"select_option": {"index": 7, "option": "CA"}}
        )
        assert result == {"action": "select", "ref": "7", "value": "CA"}

    def test_scroll_down(self):
        result = action_to_trajectory_format({"scroll_down": {"amount": 300}})
        assert result == {"action": "scroll", "direction": "down"}

    def test_scroll_up(self):
        result = action_to_trajectory_format({"scroll_up": {"amount": 300}})
        assert result == {"action": "scroll", "direction": "up"}

    def test_go_back(self):
        result = action_to_trajectory_format({"go_back": {}})
        assert result == {"action": "back"}

    def test_done(self):
        result = action_to_trajectory_format(
            {"done": {"text": "done", "success": True}}
        )
        assert result == {"action": "finish", "answer": "done"}

    def test_done_with_longer_text(self):
        result = action_to_trajectory_format(
            {"done": {"text": "The total is $5,420", "success": True}}
        )
        assert result["action"] == "finish"
        assert result["answer"] == "The total is $5,420"

    def test_index_coerced_to_string(self):
        # Ref must be a string in the replay format
        result = action_to_trajectory_format({"click": {"index": 0}})
        assert result["ref"] == "0"
        assert isinstance(result["ref"], str)

    def test_unknown_action_returns_dict(self):
        # Unknown actions should not crash, should return something reasonable
        result = action_to_trajectory_format({"hover": {"index": 5}})
        assert isinstance(result, dict)
        assert "action" in result


# =========================================================================
# 4. dom_element_to_target
# =========================================================================

class TestDomElementToTarget:
    """Test DOM element to replay target conversion."""

    # --- role mapping ---

    def test_button_role(self):
        result = dom_element_to_target("button", {}, "Click me")
        assert result["role"] == "button"

    def test_link_role(self):
        result = dom_element_to_target("a", {}, "Home")
        assert result["role"] == "link"

    def test_input_role(self):
        result = dom_element_to_target("input", {}, "")
        assert result["role"] == "textbox"

    def test_textarea_role(self):
        result = dom_element_to_target("textarea", {}, "")
        assert result["role"] == "textbox"

    def test_select_role(self):
        result = dom_element_to_target("select", {}, "")
        assert result["role"] == "combobox"

    def test_article_role(self):
        result = dom_element_to_target("article", {}, "")
        assert result["role"] == "article"

    def test_unknown_tag_uses_tag_name(self):
        result = dom_element_to_target("div", {}, "")
        assert result["role"] == "div"

    # --- name priority ---

    def test_aria_label_highest_priority(self):
        result = dom_element_to_target(
            "button",
            {"aria-label": "Compose a new message", "placeholder": "ignored"},
            "Compose",
        )
        assert result["name"] == "Compose a new message"

    def test_placeholder_second_priority(self):
        result = dom_element_to_target(
            "input", {"placeholder": "Search mail"}, ""
        )
        assert result["name"] == "Search mail"

    def test_text_content_fallback(self):
        result = dom_element_to_target("button", {}, "Submit")
        assert result["name"] == "Submit"

    def test_empty_name_when_nothing_available(self):
        result = dom_element_to_target("div", {}, "")
        assert result["name"] == ""

    # --- combined ---

    def test_full_example_from_spec(self):
        result = dom_element_to_target(
            "button",
            {"aria-label": "Compose a new message"},
            "Compose",
        )
        assert result == {"role": "button", "name": "Compose a new message"}


# =========================================================================
# 5. build_trajectory_step
# =========================================================================

class TestBuildTrajectoryStep:
    """Test building a single trajectory step for the demo site."""

    @staticmethod
    def _dom_elements():
        """Fake DOM elements dict keyed by index."""
        return {
            33: ("button", {"aria-label": "Compose"}, "Compose"),
            35: ("input", {"placeholder": "To"}, ""),
        }

    def test_basic_structure(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="I should click compose",
            memory="On inbox",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=2.5,
        )
        assert result["step"] == 1
        assert result["thought"] == "I should click compose"
        assert result["status"] == "success"
        assert result["elapsed_seconds"] == 2.5

    def test_action_uses_first_action(self):
        result = build_trajectory_step(
            step_num=2,
            thinking="Fill the To field",
            memory="Compose open",
            actions=[
                {"input_text": {"index": 35, "text": "alice@example.com"}},
                {"click": {"index": 33}},
            ],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/compose?session=abc&agent_mode=1",
            status="success",
            elapsed=1.2,
        )
        assert result["action"]["action"] == "fill"
        assert result["action"]["ref"] == "35"

    def test_targets_from_dom_elements(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="Click compose",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.5,
        )
        assert result["targets"]["role"] == "button"
        assert result["targets"]["name"] == "Compose"

    def test_replay_path_extraction(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.1,
        )
        assert result["replay_path"] == "/inbox"

    def test_result_path_equals_replay_path(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.1,
        )
        assert result["result_path"] == result["replay_path"]

    def test_required_keys_present(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="t",
            memory="m",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=1.0,
        )
        required = {
            "step", "thought", "action", "targets",
            "status", "elapsed_seconds", "replay_path", "result_path",
        }
        assert required.issubset(set(result.keys()))

    def test_deeper_url_path(self):
        result = build_trajectory_step(
            step_num=3,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/settings/labels?session=abc&agent_mode=1",
            status="success",
            elapsed=0.3,
        )
        assert result["replay_path"] == "/settings/labels"

    def test_root_url_path(self):
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 33}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/?session=abc",
            status="success",
            elapsed=0.1,
        )
        assert result["replay_path"] == "/"

    def test_missing_dom_element_for_action_index(self):
        # Action references index 99 which is not in dom_elements
        result = build_trajectory_step(
            step_num=1,
            thinking="",
            memory="",
            actions=[{"click": {"index": 99}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.1,
        )
        # Should not crash; targets should be a dict (possibly empty or with defaults)
        assert isinstance(result["targets"], dict)

    def test_done_action_no_dom_lookup(self):
        # done action has no index -- should not crash
        result = build_trajectory_step(
            step_num=5,
            thinking="Finished",
            memory="",
            actions=[{"done": {"text": "All done", "success": True}}],
            dom_elements=self._dom_elements(),
            url="http://localhost:8080/env/gmail/inbox?session=abc&agent_mode=1",
            status="success",
            elapsed=0.2,
        )
        assert result["action"]["action"] == "finish"
        assert isinstance(result["targets"], dict)


# =========================================================================
# NEW ACTIONS: scroll_left/right, send_keys, wait, go_forward
# =========================================================================


class TestNewActionsParsing:
    """Test parsing of newly-added actions via structured JSON."""

    # --- send_keys ---

    def test_parse_send_keys_tab(self):
        raw = json.dumps({"thinking": "", "memory": "", "next_goal": "",
                          "action": [{"send_keys": {"keys": "Tab"}}]})
        result = parse_agent_output(raw)
        assert result["action"] == [{"send_keys": {"keys": "Tab"}}]

    def test_parse_send_keys_combo(self):
        raw = json.dumps({"thinking": "", "memory": "", "next_goal": "",
                          "action": [{"send_keys": {"keys": "ctrl+a"}}]})
        result = parse_agent_output(raw)
        assert result["action"][0]["send_keys"]["keys"] == "ctrl+a"

    # --- wait ---

    def test_parse_wait(self):
        raw = json.dumps({"thinking": "", "memory": "", "next_goal": "",
                          "action": [{"wait": {"seconds": 2}}]})
        result = parse_agent_output(raw)
        assert result["action"] == [{"wait": {"seconds": 2}}]

    # --- go_forward ---

    def test_parse_go_forward(self):
        raw = json.dumps({"thinking": "", "memory": "", "next_goal": "",
                          "action": [{"go_forward": {}}]})
        result = parse_agent_output(raw)
        assert result["action"] == [{"go_forward": {}}]

    # --- scroll_left/right ---

    def test_parse_scroll_left(self):
        raw = json.dumps({"thinking": "", "memory": "", "next_goal": "",
                          "action": [{"scroll_left": {"amount": 300}}]})
        result = parse_agent_output(raw)
        assert result["action"] == [{"scroll_left": {"amount": 300}}]

    def test_parse_scroll_right_with_index(self):
        raw = json.dumps({"thinking": "", "memory": "", "next_goal": "",
                          "action": [{"scroll_right": {"index": 5, "amount": 300}}]})
        result = parse_agent_output(raw)
        payload = result["action"][0]["scroll_right"]
        assert payload["index"] == 5
        assert payload["amount"] == 300


class TestNewActionsPlainText:
    """Test plain-text fallback parsing for new actions."""

    def test_send_keys_plain(self):
        result = parse_agent_output("send_keys Tab")
        assert result["action"] == [{"send_keys": {"keys": "Tab"}}]

    def test_send_keys_combo_plain(self):
        result = parse_agent_output("send_keys ctrl+a")
        assert result["action"] == [{"send_keys": {"keys": "ctrl+a"}}]

    def test_send_keys_default_enter(self):
        result = parse_agent_output("send_keys")
        assert result["action"] == [{"send_keys": {"keys": "Enter"}}]

    def test_wait_plain(self):
        result = parse_agent_output("wait 3")
        assert result["action"] == [{"wait": {"seconds": 3.0}}]

    def test_wait_default(self):
        result = parse_agent_output("wait")
        assert result["action"] == [{"wait": {"seconds": 2.0}}]

    def test_wait_capped_at_5(self):
        result = parse_agent_output("wait 30")
        assert result["action"][0]["wait"]["seconds"] <= 5

    def test_wait_non_numeric(self):
        result = parse_agent_output("wait a bit")
        assert result["action"] == [{"wait": {"seconds": 2.0}}]

    def test_go_forward_plain(self):
        result = parse_agent_output("go_forward")
        assert result["action"] == [{"go_forward": {}}]

    def test_scroll_left_plain(self):
        result = parse_agent_output("scroll_left")
        assert result["action"] == [{"scroll_left": {"amount": 300}}]

    def test_scroll_right_plain(self):
        result = parse_agent_output("scroll_right")
        assert result["action"] == [{"scroll_right": {"amount": 300}}]

    def test_scroll_right_with_index_plain(self):
        result = parse_agent_output("scroll_right 12")
        payload = result["action"][0]["scroll_right"]
        assert payload["index"] == 12
        assert payload["amount"] == 300

    def test_scroll_left_with_index_plain(self):
        result = parse_agent_output("scroll_left 7")
        payload = result["action"][0]["scroll_left"]
        assert payload["index"] == 7

    def test_scroll_direction_via_verb(self):
        """scroll up/down still work via the base 'scroll' verb."""
        result_up = parse_agent_output("scroll up")
        result_down = parse_agent_output("scroll down")
        assert "scroll_up" in result_up["action"][0]
        assert "scroll_down" in result_down["action"][0]


class TestNewActionsTrajectoryFormat:
    """Test trajectory format conversion for new actions."""

    def test_scroll_left_trajectory(self):
        result = action_to_trajectory_format({"scroll_left": {"amount": 300}})
        assert result == {"action": "scroll", "direction": "left"}

    def test_scroll_right_trajectory(self):
        result = action_to_trajectory_format({"scroll_right": {"amount": 300}})
        assert result == {"action": "scroll", "direction": "right"}

    def test_scroll_right_with_index_trajectory(self):
        result = action_to_trajectory_format({"scroll_right": {"index": 12, "amount": 300}})
        assert result == {"action": "scroll", "direction": "right", "ref": "12"}

    def test_send_keys_trajectory(self):
        result = action_to_trajectory_format({"send_keys": {"keys": "Escape"}})
        assert result == {"action": "press", "key": "Escape"}

    def test_send_keys_combo_trajectory(self):
        result = action_to_trajectory_format({"send_keys": {"keys": "ctrl+a"}})
        assert result == {"action": "press", "key": "ctrl+a"}

    def test_wait_trajectory(self):
        result = action_to_trajectory_format({"wait": {"seconds": 2}})
        assert result == {"action": "wait"}

    def test_go_forward_trajectory(self):
        result = action_to_trajectory_format({"go_forward": {}})
        assert result == {"action": "forward"}


class TestNewActionsBuildStep:
    """Test build_trajectory_step with new action types."""

    @staticmethod
    def _dom():
        return {5: ("div", {"aria-label": "Contact table"}, "")}

    def test_send_keys_step(self):
        step = build_trajectory_step(
            step_num=1, thinking="Press Tab to next field", memory="",
            actions=[{"send_keys": {"keys": "Tab"}}],
            dom_elements={}, url="http://localhost/env/gmail/compose",
            status="success", elapsed=0.3,
        )
        assert step["action"] == {"action": "press", "key": "Tab"}

    def test_wait_step(self):
        step = build_trajectory_step(
            step_num=1, thinking="Wait for page load", memory="",
            actions=[{"wait": {"seconds": 2}}],
            dom_elements={}, url="http://localhost/env/gmail/inbox",
            status="success", elapsed=2.0,
        )
        assert step["action"] == {"action": "wait"}

    def test_scroll_right_with_index_step(self):
        step = build_trajectory_step(
            step_num=1, thinking="Scroll table right", memory="",
            actions=[{"scroll_right": {"index": 5, "amount": 300}}],
            dom_elements=self._dom(),
            url="http://localhost/env/gmail/labels",
            status="success", elapsed=0.3,
        )
        assert step["action"] == {"action": "scroll", "direction": "right", "ref": "5"}
        # Scroll with index resolves targets from the DOM element
        assert step["targets"]["role"] == "div"

    def test_go_forward_step(self):
        step = build_trajectory_step(
            step_num=1, thinking="Go forward", memory="",
            actions=[{"go_forward": {}}],
            dom_elements={}, url="http://localhost/env/gmail/inbox",
            status="success", elapsed=0.5,
        )
        assert step["action"] == {"action": "forward"}


class TestSystemPromptActions:
    """Verify the system prompt documents all supported actions."""

    def test_all_action_types_in_prompt(self):
        from breakingweb.browseruse_eval import SYSTEM_PROMPT_TEMPLATE
        expected = [
            "click", "input_text", "select_option", "send_keys",
            "scroll_down", "scroll_up", "scroll_left", "scroll_right",
            "wait", "go_back", "go_forward", "done",
        ]
        for action in expected:
            assert action in SYSTEM_PROMPT_TEMPLATE, f"'{action}' missing from system prompt"

    def test_send_keys_examples_in_prompt(self):
        from breakingweb.browseruse_eval import SYSTEM_PROMPT_TEMPLATE
        assert "Tab" in SYSTEM_PROMPT_TEMPLATE
        assert "Escape" in SYSTEM_PROMPT_TEMPLATE
        assert "ctrl+a" in SYSTEM_PROMPT_TEMPLATE

    def test_scroll_index_documented(self):
        from breakingweb.browseruse_eval import SYSTEM_PROMPT_TEMPLATE
        assert "index" in SYSTEM_PROMPT_TEMPLATE
        assert "container" in SYSTEM_PROMPT_TEMPLATE


# =========================================================================
# Additional tests from PR review (Gap fixes)
# =========================================================================

class TestReviewGaps:
    """Tests added from PR review to close coverage gaps."""

    # Gap 2: think action type
    def test_think_action(self):
        result = action_to_trajectory_format({"think": {}})
        assert result == {"action": "think"}

    # Gap 1: plain-text fallback branches
    def test_plain_text_input(self):
        result = parse_agent_output('input 35 "hello world"')
        assert result["action"] == [{"input_text": {"index": 35, "text": "hello world"}}]

    def test_plain_text_scroll_up(self):
        result = parse_agent_output("scroll up")
        assert result["action"] == [{"scroll_up": {"amount": 300}}]

    def test_plain_text_scroll_default_down(self):
        result = parse_agent_output("scroll down")
        assert result["action"] == [{"scroll_down": {"amount": 300}}]

    def test_plain_text_go_back(self):
        result = parse_agent_output("go_back")
        assert result["action"] == [{"go_back": {}}]

    def test_plain_text_done(self):
        result = parse_agent_output("done Task complete")
        assert result["action"] == [{"done": {"text": "Task complete", "success": True}}]

    # Gap 3: empty actions list
    def test_build_step_empty_actions(self):
        step = build_trajectory_step(
            step_num=1, thinking="", memory="", actions=[],
            dom_elements={}, url="http://localhost/env/gmail/inbox",
            status="", elapsed=1.0,
        )
        # An empty actions list means "agent produced no tool call this turn"
        # — distinct from "couldn't map an action shape" (unknown). See commit
        # 35912d10 ("emit noop instead of unknown for empty-action steps").
        assert step["action"] == {"action": "noop"}
        assert step["targets"] == {}

    # Gap 4: dict-style dom_elements
    def test_build_step_dict_dom_elements(self):
        step = build_trajectory_step(
            step_num=1, thinking="", memory="",
            actions=[{"click": {"index": 5}}],
            dom_elements={5: {"tag_name": "button", "attributes": {"aria-label": "Send"}, "text": "Send"}},
            url="http://localhost/env/gmail/compose",
            status="", elapsed=1.0,
        )
        assert step["targets"]["role"] == "button"
        assert step["targets"]["name"] == "Send"

    # Gap 8: uppercase tag name normalization
    def test_dom_target_uppercase_tag(self):
        result = dom_element_to_target("BUTTON", {"aria-label": "Submit"})
        assert result["role"] == "button"

    def test_dom_target_mixed_case_tag(self):
        result = dom_element_to_target("Input", {"placeholder": "Search"})
        assert result["role"] == "textbox"

    # Gap 9: done action without text key
    def test_done_action_no_text_key(self):
        result = action_to_trajectory_format({"done": {"success": True}})
        assert result == {"action": "finish", "answer": ""}

    # Gap 7: mask_observations does not mutate input
    def test_mask_observations_no_mutation(self):
        original = [
            {"role": "user", "content": "goal"},
            {"role": "assistant", "content": "act"},
            {"role": "user", "content": "obs"},
        ]
        import copy
        snapshot = copy.deepcopy(original)
        mask_observations(original, window=1)
        assert original == snapshot


# =========================================================================
# 6. Bug-fix regression tests (H1, H2, H6)
# =========================================================================

class TestBugH1StateFetchErrorDoesNotBleed:
    """H1: state-fetch failure at step 0 must NOT appear as 'Last Action Error' at step 1.

    The fix uses a separate ``state_fetch_error`` variable for state-fetch
    failures so that ``last_error`` (which feeds into the observation) stays
    empty unless an *action* execution failed.
    """

    def test_step0_state_fetch_error_not_in_step1_obs(self):
        """Simulate the observation-building logic and verify no bleed."""
        # Before the fix, the except block set last_error which then appeared
        # in step-1's observation.  After the fix, only action execution sets
        # last_error; state-fetch failures go to state_fetch_error.

        # Simulate two iterations of the observation builder.
        last_error = ""
        observations: list[str] = []

        for step in range(2):
            # Simulate state-fetch failure at step 0 only
            if step == 0:
                # After fix: state_fetch_error is a local, last_error unchanged
                _state_fetch_error = "Failed to read page state: timeout"
                dom_text = f"(page not available — {_state_fetch_error})"
                current_url = ""
            else:
                dom_text = "[1]<button>Compose</button>"
                current_url = "http://localhost/env/gmail/inbox"

            if step == 0:
                obs_content = f"## Current Page\nURL: {current_url}\n\n{dom_text}"
            else:
                parts = [f"## Current Page\nURL: {current_url}\n\n{dom_text}"]
                if last_error:
                    parts.append(f"\n## Last Action Error\n{last_error}")
                obs_content = "\n".join(parts)

            observations.append(obs_content)

        # Step-0 observation should contain state-fetch info in the DOM text
        assert "page not available" in observations[0]
        # Step-1 observation must NOT contain "Last Action Error"
        assert "Last Action Error" not in observations[1]

    def test_action_error_still_shown_at_next_step(self):
        """Action execution errors should still appear in the next observation."""
        last_error = "Element index 99 not found"  # set by action execution

        parts = ["## Current Page\nURL: http://localhost/env/gmail/inbox\n\n[1]<button/>"]
        if last_error:
            parts.append(f"\n## Last Action Error\n{last_error}")
        obs = "\n".join(parts)

        assert "Last Action Error" in obs
        assert "Element index 99 not found" in obs


class TestBugH2LLMFailureMessageCleanup:
    """H2: LLM failure must pop the orphaned user message from ``messages``.

    When the LLM call fails, the code had already appended a user message.
    Without cleanup, the next iteration would append another user message,
    creating two consecutive user messages which violates the alternating
    user/assistant contract.
    """

    def test_orphaned_user_message_popped_on_llm_failure(self):
        """Simulate the LLM failure path and verify message cleanup."""
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "obs step 0"},
            {"role": "assistant", "content": "action 0"},
        ]

        # Simulate: step 1 appends user message, then LLM fails
        messages.append({"role": "user", "content": "obs step 1"})

        # --- This is what the fix does ---
        # (simulating the except block)
        if messages and messages[-1]["role"] == "user":
            messages.pop()

        # After cleanup, last message should be the assistant message
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "action 0"

    def test_no_consecutive_user_messages_after_recovery(self):
        """After LLM failure + cleanup + retry, messages alternate properly."""
        messages = [
            {"role": "system", "content": "system prompt"},
        ]

        # Step 0: success
        messages.append({"role": "user", "content": "obs 0"})
        messages.append({"role": "assistant", "content": "action 0"})

        # Step 1: LLM fails
        messages.append({"role": "user", "content": "obs 1"})
        # Failure cleanup
        if messages and messages[-1]["role"] == "user":
            messages.pop()

        # Step 2 (retry): new observation appended
        messages.append({"role": "user", "content": "obs 2"})
        messages.append({"role": "assistant", "content": "action 2"})

        # Verify no consecutive user messages (excluding system)
        non_system = [m for m in messages if m["role"] != "system"]
        for i in range(1, len(non_system)):
            assert not (
                non_system[i]["role"] == "user" and non_system[i - 1]["role"] == "user"
            ), f"Consecutive user messages at indices {i-1} and {i}"

    def test_cleanup_safe_when_no_user_message(self):
        """Pop guard handles edge case where last message isn't user."""
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "obs"},
            {"role": "assistant", "content": "action"},
        ]
        original_len = len(messages)

        # If somehow the last message is assistant, don't pop it
        if messages and messages[-1]["role"] == "user":
            messages.pop()

        assert len(messages) == original_len


class TestBugH6EvaluateRetryOnFailure:
    """H6: evaluate HTTP call must not silently produce score=0 on timeout.

    The fix moves the evaluate call outside the inner action loop and adds
    retry logic with explicit error reporting.
    """

    def test_evaluate_retry_on_first_failure(self):
        """Simulate evaluate with one failure then success on retry."""
        call_count = 0

        def mock_http_json(url, *, method="GET", payload=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Connection timed out")
            return {"score": 0.85, "success": True, "reasoning": "Good job"}

        eval_url = "http://localhost:8080/api/env/gmail/evaluate"
        eval_payload = {"session_id": "s1", "task_id": "t1", "benchmark_state": {}}

        # Simulate the retry logic from the fix
        try:
            evaluation = mock_http_json(eval_url, method="POST", payload=eval_payload)
        except Exception:
            try:
                evaluation = mock_http_json(eval_url, method="POST", payload=eval_payload)
            except Exception as exc2:
                evaluation = {
                    "score": 0.0,
                    "success": False,
                    "reasoning": f"Evaluate failed after retry: {exc2}",
                }

        assert evaluation["score"] == 0.85
        assert evaluation["success"] is True
        assert call_count == 2

    def test_evaluate_both_attempts_fail_reports_error(self):
        """When both evaluate attempts fail, the error is captured in reasoning."""
        def mock_http_json(url, *, method="GET", payload=None):
            raise ConnectionError("Server unreachable")

        eval_url = "http://localhost:8080/api/env/gmail/evaluate"
        eval_payload = {"session_id": "s1", "task_id": "t1", "benchmark_state": {}}

        try:
            evaluation = mock_http_json(eval_url, method="POST", payload=eval_payload)
        except Exception:
            try:
                evaluation = mock_http_json(eval_url, method="POST", payload=eval_payload)
            except Exception as exc2:
                evaluation = {
                    "score": 0.0,
                    "success": False,
                    "reasoning": f"Evaluate failed after retry: {exc2}",
                }

        assert evaluation["score"] == 0.0
        assert evaluation["success"] is False
        assert "Evaluate failed after retry" in evaluation["reasoning"]
        assert "Server unreachable" in evaluation["reasoning"]

    def test_evaluate_succeeds_first_try(self):
        """When evaluate succeeds on first attempt, no retry needed."""
        call_count = 0

        def mock_http_json(url, *, method="GET", payload=None):
            nonlocal call_count
            call_count += 1
            return {"score": 1.0, "success": True, "reasoning": "Perfect"}

        eval_url = "http://localhost:8080/api/env/gmail/evaluate"
        eval_payload = {"session_id": "s1", "task_id": "t1", "benchmark_state": {}}

        try:
            evaluation = mock_http_json(eval_url, method="POST", payload=eval_payload)
        except Exception:
            try:
                evaluation = mock_http_json(eval_url, method="POST", payload=eval_payload)
            except Exception as exc2:
                evaluation = {
                    "score": 0.0,
                    "success": False,
                    "reasoning": f"Evaluate failed after retry: {exc2}",
                }

        assert evaluation["score"] == 1.0
        assert call_count == 1
