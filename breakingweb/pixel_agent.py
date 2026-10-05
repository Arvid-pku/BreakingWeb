"""Vision-only (pixel) VLM agent for BreakingWeb BrowserGym environments.

This is a lightweight port of InterfaceGym's `OpenRouterAgent` adapted to the
BreakingWeb `LLMAgent` interface (act(obs) -> str). The agent:

  * reads ONLY `obs["screenshot"]` plus task goal and chat history
  * IGNORES `obs["axtree_txt"]`, `obs["dom_object"]`, etc.
  * outputs BrowserGym `coord` action_space strings, e.g. `mouse_click(640, 360)`,
    `keyboard_type('Hello')`, `scroll(0, 300)`, `send_msg_to_user('done')`.
  * supports 4 providers via OpenAI-compatible chat endpoints:
      - gemini      → https://generativelanguage.googleapis.com/v1beta/openai/
      - openrouter  → https://openrouter.ai/api/v1
      - anthropic   → https://api.anthropic.com/v1
      - bedrock     → https://bedrock-runtime.<region>.amazonaws.com/openai/v1

For coordinate handling we follow InterfaceGym/ComponentBench's convention:
some VLMs (Qwen3-VL, Gemini-3-Flash) emit normalized 0-1000 coords, GPT/Claude
emit pixel coords. `normalize_coordinates` controls whether we transform
output 0-1000 → pixel before returning the action.

Designed to slot in to `breakingweb/agent_eval.py`'s `run_episode()` in
place of `breakingweb.agent.LLMAgent`.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


# =============================================================================
# Valid BrowserGym coord-mode actions
# =============================================================================

VALID_COORD_ACTIONS = {
    "mouse_click", "mouse_move", "mouse_up", "mouse_dblclick", "mouse_drag_and_drop",
    "keyboard_type", "keyboard_press", "keyboard_down", "keyboard_up", "keyboard_insert_text",
    "send_msg_to_user", "report_infeasible", "noop",
    "scroll", "go_back", "go_forward", "goto", "new_tab", "tab_focus", "close_tab",
}


# =============================================================================
# Provider routing
# =============================================================================

def _resolve_endpoint(provider: str) -> tuple[str, str]:
    """Return (base_url, api_key) for an OpenAI-compatible provider."""
    p = provider.lower()
    if p in ("gemini", "google"):
        url = os.environ.get(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "dummy"
        return url, key
    if p == "openrouter":
        url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        key = os.environ.get("OPENROUTER_API_KEY") or "dummy"
        return url, key
    if p in ("anthropic", "anthropic_direct"):
        url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
        key = os.environ.get("ANTHROPIC_API_KEY") or "dummy"
        return url, key
    if p in ("bedrock", "anthropic_bedrock"):
        region = os.environ.get("AWS_BEDROCK_REGION", "us-east-1")
        url = os.environ.get(
            "BEDROCK_BASE_URL",
            f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1",
        )
        key = os.environ.get("AWS_BEDROCK_API_KEY") or "dummy"
        return url, key
    if p in ("openai", "vllm"):
        url = os.environ.get("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        key = os.environ.get("OPENAI_API_KEY") or "dummy"
        return url, key
    raise ValueError(f"Unknown pixel-agent provider: {provider!r}")


# =============================================================================
# Image encoding
# =============================================================================

def _image_to_png_data_url(img: np.ndarray | Image.Image) -> str:
    if isinstance(img, np.ndarray):
        img = Image.fromarray(img)
    if img.mode in ("LA",):
        img = img.convert("RGBA")
    elif img.mode == "RGBA":
        img = img.convert("RGB")
    with io.BytesIO() as buf:
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _data_url_to_bytes(data_url: str) -> tuple[bytes | None, str]:
    """Decode a `data:image/<fmt>;base64,...` URL into (bytes, format).

    Returns (None, "") if the URL isn't a base64 data URL we can parse.
    """
    if not data_url or not data_url.startswith("data:"):
        return None, ""
    # data:image/png;base64,XXXX
    try:
        header, b64 = data_url.split(",", 1)
    except ValueError:
        return None, ""
    fmt = "png"
    if "image/" in header:
        fmt = header.split("image/", 1)[1].split(";", 1)[0].lower()
        if fmt == "jpg":
            fmt = "jpeg"
    try:
        return base64.b64decode(b64), fmt
    except Exception:
        return None, ""


def _screenshot_dims(screenshot: Any) -> tuple[int, int]:
    """(width, height) of the screenshot, defaulting to 1280x720 if unknown."""
    if screenshot is None:
        return 1280, 720
    if isinstance(screenshot, np.ndarray):
        h, w = screenshot.shape[:2]
        return int(w), int(h)
    if isinstance(screenshot, Image.Image):
        return int(screenshot.size[0]), int(screenshot.size[1])
    return 1280, 720


# =============================================================================
# Coordinate transform
# =============================================================================

_COORD_PATTERN_2 = re.compile(
    r"(mouse_click|mouse_move|mouse_drag_to|mouse_dblclick|mouse_up|mouse_down)"
    r"\s*\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)"
)
_COORD_PATTERN_4 = re.compile(
    r"mouse_drag_and_drop\s*\(\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,"
    r"\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)"
)


def _transform_normalized_to_pixel(action: str, screen_width: int, screen_height: int) -> str:
    """Convert 0-1000 normalized coords in the action string to pixel coords."""

    def n2p(nx: float, ny: float) -> tuple[int, int]:
        return int(nx / 1000 * screen_width), int(ny / 1000 * screen_height)

    def rep2(m: re.Match) -> str:
        fn = m.group(1)
        px, py = n2p(float(m.group(2)), float(m.group(3)))
        return f"{fn}({px}, {py})"

    def rep4(m: re.Match) -> str:
        fx, fy = n2p(float(m.group(1)), float(m.group(2)))
        tx, ty = n2p(float(m.group(3)), float(m.group(4)))
        return f"mouse_drag_and_drop({fx}, {fy}, {tx}, {ty})"

    transformed = _COORD_PATTERN_4.sub(rep4, action)
    transformed = _COORD_PATTERN_2.sub(rep2, transformed)
    if transformed != action:
        logger.debug("Coord transform: %s -> %s", action, transformed)
    return transformed


# =============================================================================
# Response parsing — <think>...</think> + action
# =============================================================================

_FENCE_RE = re.compile(r"^```\w*\s*\n?|\n?```$")
_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_ACTION_HEAD_RE = re.compile(r"^(\w+)\s*\(")


def _strip_code_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def _try_parse_single_action(raw: str) -> str | None:
    """Return raw if it is exactly one valid coord-mode action, else None."""
    raw = raw.strip()
    m = _ACTION_HEAD_RE.match(raw)
    if not m:
        return None
    if m.group(1) not in VALID_COORD_ACTIONS:
        return None
    # Must end with `)`. Tolerate trailing whitespace / single semicolon.
    end = raw.rstrip().rstrip(";").rstrip()
    if not end.endswith(")"):
        return None
    return end


def _find_last_valid_action_in(text: str) -> str | None:
    """Scan text for the LAST occurrence of a valid coord action call.

    We accept any function in VALID_COORD_ACTIONS followed by `(...)`.
    """
    found: str | None = None
    # Match `name(...args...)` allowing nested parens minimally.
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(n) for n in VALID_COORD_ACTIONS) + r")\s*\(([^()]*)\)"
    )
    for m in pattern.finditer(text):
        candidate = m.group(0).strip()
        found = candidate
    return found


def _extract_thinking_and_action(raw: str) -> tuple[str | None, str | None]:
    """Parse model output → (thinking, action) for coord action_space."""
    thinking: str | None = None
    action: str | None = None

    think_match = _THINK_RE.search(raw)
    if think_match:
        thinking = think_match.group(1).strip()
        candidate = raw[think_match.end():].strip()
    else:
        candidate = raw

    candidate = _strip_code_fences(candidate)

    # Try clean single-action parse first.
    direct = _try_parse_single_action(candidate)
    if direct:
        action = direct
    else:
        action = _find_last_valid_action_in(candidate)

    if action is None and not think_match:
        # Fall back to scanning the entire raw response.
        action = _find_last_valid_action_in(raw)

    # If we have an action but no <think>, capture leading prose as thinking.
    if thinking is None and action:
        head = action.split("(", 1)[0]
        head_re = re.compile(re.escape(head) + r"\s*\(")
        last = None
        for m in head_re.finditer(raw):
            last = m
        if last and last.start() > 10:
            prose = raw[: last.start()].strip()
            prose = _strip_code_fences(prose)
            if len(prose) > 10:
                thinking = prose

    return thinking, action


# =============================================================================
# Prompt
# =============================================================================

_INSTRUCTIONS_NORMALIZED = """\
You are a web agent driving a real browser by looking at screenshots only.

# Task Completion (READ FIRST)

The episode does NOT auto-terminate. You MUST call `send_msg_to_user('done')`
the moment the task goal is achieved. Without it, you will keep being prompted
even if the task was already done many steps ago, wasting your step budget.
If the task is genuinely impossible after honest effort, call
`report_infeasible('<short reason>')`.

# Response Format (BOTH parts are required, in this order)

1. A `<think>...</think>` block with your reasoning. NEVER skip this block.
2. Exactly ONE valid action call on a new line after the closing `</think>`.

Both parts are mandatory. A response with only an action and no `<think>`
block is treated as malformed and you will be re-prompted.

Example of a correct response:

<think>
The screenshot shows search history is now empty after my last delete-all
click. Goal was "clear search history". Verifying state — table is empty.
Task complete.
</think>
send_msg_to_user('done')

Inside `<think>` answer:
  1. What you observe on the current page
  2. What your previous action did
  3. Whether the task goal is satisfied (if YES → call send_msg_to_user('done'))
  4. Otherwise, what to do next and why

# Coordinate System (0-1000 normalized scale)

The image is treated as a 0-1000 grid:
  (0, 0)       = top-left corner
  (500, 500)   = center of the screen
  (1000, 1000) = bottom-right corner

Always output coordinates in the 0-1000 normalized range, NOT pixel values.
Examples:
  mouse_click(500, 500)   # center
  mouse_click(100, 100)   # top-left area
  mouse_click(900, 500)   # right edge, vertically centered

# Valid Actions (use EXACTLY these names)

mouse_click(x, y)              click at (x, y)
mouse_dblclick(x, y)           double-click
mouse_move(x, y)               move pointer
mouse_drag_and_drop(x1, y1, x2, y2)
keyboard_type('text')          type text into the focused element
keyboard_press('Enter')        press a single key
scroll(dx, dy)                 scroll by pixels (positive dy = down)
send_msg_to_user('answer')     report the final answer / declare done
report_infeasible('reason')    declare task is impossible
noop(1000)                     wait 1000ms
go_back / go_forward           browser back / forward

INVALID — DO NOT USE:
  click(x, y), at(x, y), around(x, y), approximately(x, y), coordinates(x, y)

Always use mouse_click(x, y) for clicking.
"""

_INSTRUCTIONS_PIXEL_TMPL = """\
You are a web agent driving a real browser by looking at screenshots only.

# Task Completion (READ FIRST)

The episode does NOT auto-terminate. You MUST call `send_msg_to_user('done')`
the moment the task goal is achieved. Without it, you will keep being prompted
even if the task was already done many steps ago, wasting your step budget.
If the task is genuinely impossible after honest effort, call
`report_infeasible('<short reason>')`.

# Response Format (BOTH parts are required, in this order)

1. A `<think>...</think>` block with your reasoning. NEVER skip this block.
2. Exactly ONE valid action call on a new line after the closing `</think>`.

Both parts are mandatory. A response with only an action and no `<think>`
block is treated as malformed and you will be re-prompted.

Example of a correct response:

<think>
The screenshot shows search history is now empty after my last delete-all
click. Goal was "clear search history". Verifying state — table is empty.
Task complete.
</think>
send_msg_to_user('done')

Inside `<think>` answer:
  1. What you observe on the current page
  2. What your previous action did
  3. Whether the task goal is satisfied (if YES → call send_msg_to_user('done'))
  4. Otherwise, what to do next and why

# Coordinate System (PIXELS, viewport is {w} x {h})

  (0, 0)       = top-left corner
  ({cx}, {cy}) = center of the viewport
  ({w}, {h})   = bottom-right corner

Output coordinates in actual pixel values matching the screenshot dimensions.

# Valid Actions (use EXACTLY these names)

mouse_click(x, y)              click at pixel (x, y)
mouse_dblclick(x, y)           double-click
mouse_move(x, y)               move pointer
mouse_drag_and_drop(x1, y1, x2, y2)
keyboard_type('text')          type text into the focused element
keyboard_press('Enter')        press a single key
scroll(dx, dy)                 scroll by pixels (positive dy = down)
send_msg_to_user('answer')     report the final answer / declare done
report_infeasible('reason')    declare task is impossible
noop(1000)                     wait 1000ms

INVALID — DO NOT USE:
  click(x, y), at(x, y), around(x, y), approximately(x, y), coordinates(x, y)

Always use mouse_click(x, y) for clicking.
"""


# =============================================================================
# Agent
# =============================================================================

class PixelLLMAgent:
    """Vision-only VLM agent with coord-mode action output.

    Conforms to the same `act(obs) -> str` interface as
    `breakingweb.agent.LLMAgent`, so it slots into `agent_eval.run_episode`.
    """

    def __init__(
        self,
        model: str,
        provider: str = "gemini",
        base_url: str | None = None,
        api_key: str | None = None,
        # Default `None` so we don't break newer models that deprecate
        # the temperature param (claude-opus-4-7+, gpt-5.x). Pass an
        # explicit value when reproducibility is critical AND the model
        # still accepts it (e.g. gemini-3-flash, claude-opus-4-6).
        temperature: float | None = None,
        normalize_coordinates: bool = True,
        max_history_steps: int = 6,
        request_timeout: float = 120.0,
        # Unused, kept for compatibility with `LLMAgent.__init__` callers
        reasoning_effort: str | None = None,
        max_input_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.normalize_coordinates = normalize_coordinates
        self.max_history_steps = max_history_steps
        self.request_timeout = request_timeout

        prov = (provider or "").lower()
        # Bedrock takes a different code path: Converse API via boto3 (the
        # OAI-compat endpoint at bedrock-runtime/openai/v1 has a smaller model
        # whitelist and rejects e.g. us.anthropic.claude-sonnet-4-6 with 404).
        # Auth via AWS-issued bearer token (AWS_BEDROCK_API_KEY, mirrored to
        # AWS_BEARER_TOKEN_BEDROCK which is what boto3 reads).
        self._is_bedrock = prov in ("bedrock", "anthropic_bedrock")
        if self._is_bedrock:
            self._init_bedrock_client(api_key)
            self.client = None
        else:
            self._init_openai_client(base_url, api_key)

        # Per-episode state
        self.action_history: list[str] = []
        self.thinking_history: list[str] = []
        self.messages: list[dict] = []
        self._step_count = 0
        self._last_thought = ""
        self._last_raw_response = ""
        self._has_initial_obs = False

        # Verify credentials BEFORE the browser stack boots. Catches missing /
        # invalid API keys in <2s rather than wasting 30-60s of cluster time
        # per failed pick. Skip via WAB_PIXEL_SKIP_PROBE=1 if needed.
        if os.environ.get("WAB_PIXEL_SKIP_PROBE", "0") not in ("1", "true", "yes"):
            self._probe_api_credentials()

        logger.info("PixelLLMAgent ready: model=%s provider=%s bedrock=%s",
                    model, provider, self._is_bedrock)

    def _probe_api_credentials(self) -> None:
        """Send 1 trivial chat request to confirm API key + model are valid.

        Raises a clear error before the BrowserGym backend is touched. Cost is
        a few hundred input tokens (well under $0.001 for any provider).
        """
        probe_messages = [{"role": "user", "content": "ping"}]
        try:
            if self._is_bedrock:
                self._bedrock_converse(probe_messages)
            else:
                # GPT-5 family rejects `max_tokens` — must use `max_completion_tokens`.
                token_field = (
                    "max_completion_tokens"
                    if (self.model or "").startswith("gpt-5") or "/gpt-5" in (self.model or "")
                    else "max_tokens"
                )
                kwargs = {
                    "model": self.model,
                    "messages": probe_messages,
                    token_field: 8,
                }
                if self.temperature is not None:
                    kwargs["temperature"] = self.temperature
                self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"PixelLLMAgent credential probe FAILED for "
                f"provider={self.provider!r} model={self.model!r}: {type(exc).__name__}: {exc}. "
                "Fix the API key / model name BEFORE submitting more sbatch jobs — "
                "every failed task burns ~30-60s of cluster time + partial API charges."
            ) from exc

    # ---- Provider client init ---------------------------------------------

    def _init_openai_client(self, base_url: str | None, api_key: str | None) -> None:
        try:
            import openai  # noqa: WPS433
        except ImportError as e:
            raise ImportError("`openai` package required for PixelLLMAgent") from e
        resolved_url, resolved_key = _resolve_endpoint(self.provider)
        if base_url:
            resolved_url = base_url
        if api_key:
            resolved_key = api_key
        client_kwargs: dict[str, Any] = {
            "base_url": resolved_url,
            "api_key": resolved_key,
            "timeout": self.request_timeout,
        }
        if "openrouter.ai" in resolved_url:
            client_kwargs["default_headers"] = {
                "HTTP-Referer": "https://github.com/Arvid-pku/WebStress",
                "X-Title": "BreakingWeb Pixel Harness",
            }
        self.client = openai.OpenAI(**client_kwargs)
        self._openai_module = openai

    def _init_bedrock_client(self, api_key: str | None) -> None:
        try:
            import boto3  # noqa: WPS433
        except ImportError as e:
            raise ImportError(
                "`boto3` required for provider=bedrock. Install with `pip install boto3`."
            ) from e
        # Bedrock's bearer-token auth is read from AWS_BEARER_TOKEN_BEDROCK by
        # boto3. We mirror our project-standard AWS_BEDROCK_API_KEY into it
        # (idempotent, doesn't clobber if already set).
        bearer = api_key or os.environ.get("AWS_BEDROCK_API_KEY") or os.environ.get(
            "AWS_BEARER_TOKEN_BEDROCK"
        )
        if bearer:
            os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", bearer)
        elif not os.environ.get("AWS_PROFILE"):
            # No bearer token and no profile for boto3 to resolve SigV4 creds from.
            raise RuntimeError(
                "Bedrock pixel agent requires AWS_BEDROCK_API_KEY (a long-term "
                "bearer token issued via the Bedrock console), AWS_BEARER_TOKEN_BEDROCK, "
                "or an AWS_PROFILE boto3 can resolve SigV4 credentials from."
            )
        # With AWS_PROFILE set and no bearer token, fall through: boto3 resolves
        # SigV4 credentials from the profile exactly as the text harness does.
        region = os.environ.get("AWS_BEDROCK_REGION", "us-east-1")
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=region)
        self._boto3_module = boto3

    # ---- Episode lifecycle ---------------------------------------------------

    def reset(self, obs: dict | None = None) -> None:
        """Clear per-episode state. obs is accepted for API compatibility but unused."""
        self.action_history.clear()
        self.thinking_history.clear()
        self.messages = []
        self._step_count = 0
        self._last_thought = ""
        self._last_raw_response = ""
        self._has_initial_obs = obs is not None  # mirror LLMAgent flag

    @property
    def conversation(self) -> list[dict]:
        return list(self.messages)

    # ---- Core act() ----------------------------------------------------------

    def act(self, obs: dict | str) -> str:
        if not isinstance(obs, dict):
            raise TypeError("PixelLLMAgent expects a BrowserGym obs dict")
        screenshot = obs.get("screenshot")
        if screenshot is None:
            logger.warning("No screenshot in obs — pixel agent has no input. Returning noop.")
            return "noop(1000)"

        sw, sh = _screenshot_dims(screenshot)
        system_prompt = self._build_system_prompt(sw, sh)
        user_content = self._build_user_content(obs, screenshot)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        thinking: str | None = None
        action: str | None = None
        raw_response = ""

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                resp = self._chat_completion(messages)
            except Exception as exc:  # network / API error
                logger.warning("PixelLLMAgent API error (attempt %d/%d): %s",
                               attempt + 1, max_attempts, exc)
                if attempt + 1 == max_attempts:
                    raise
                time.sleep(min(2 ** attempt * 2, 30))
                continue

            choice = resp.choices[0].message
            raw_response = (choice.content or "").strip()
            thinking, action = _extract_thinking_and_action(raw_response)

            if action and self._is_valid_bg_action(action):
                break

            messages.append({"role": "assistant", "content": raw_response})
            example = "mouse_click(500, 500)" if self.normalize_coordinates else \
                      f"mouse_click({sw // 2}, {sh // 2})"
            messages.append({
                "role": "user",
                "content": (
                    f"Invalid action. Output EXACTLY ONE valid action call, "
                    f"e.g. {example}. Do not output prose after the action."
                ),
            })
            action = None

        if action is None:
            action = "noop(1000)"

        # Normalized → pixel transform if applicable
        if self.normalize_coordinates:
            action = _transform_normalized_to_pixel(action, sw, sh)

        # Update episode state
        self._last_raw_response = raw_response
        self._last_thought = thinking or ""
        self.messages.append({"role": "user", "content": "[screenshot]"})
        self.messages.append({"role": "assistant", "content": action})
        self.action_history.append(action)
        self.thinking_history.append(thinking or "")
        self._step_count += 1

        logger.info("PixelLLMAgent step %d: %s", self._step_count, action[:120])

        # Loop detection: if the SAME exact action was emitted N times in a
        # row, the agent is stuck. Bail out to send_msg_to_user so BrowserGym
        # terminates the episode instead of burning the full max_steps budget.
        # Threshold defaults to 5 (configurable via WAB_PIXEL_LOOP_THRESHOLD).
        try:
            loop_threshold = int(os.environ.get("WAB_PIXEL_LOOP_THRESHOLD", "5"))
        except ValueError:
            loop_threshold = 5
        if loop_threshold > 0 and len(self.action_history) >= loop_threshold:
            tail = self.action_history[-loop_threshold:]
            if all(a == tail[0] for a in tail):
                logger.warning(
                    "PixelLLMAgent: %d-action loop detected (%s) — aborting episode",
                    loop_threshold, tail[0][:80],
                )
                return f"send_msg_to_user('infeasible: stuck in {loop_threshold}-action loop')"

        return action

    # ---- Helpers -------------------------------------------------------------

    def _build_system_prompt(self, w: int, h: int) -> str:
        if self.normalize_coordinates:
            return _INSTRUCTIONS_NORMALIZED
        return _INSTRUCTIONS_PIXEL_TMPL.format(w=w, h=h, cx=w // 2, cy=h // 2)

    def _build_user_content(self, obs: dict, screenshot: Any) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []

        # Goal
        goal = obs.get("goal", "")
        goal_object = obs.get("goal_object", [])
        content.append({"type": "text", "text": "# Goal\n"})
        if goal_object:
            for part in goal_object:
                if isinstance(part, dict) and "type" in part:
                    content.append(part)
                else:
                    content.append({"type": "text", "text": str(part)})
        elif goal:
            content.append({"type": "text", "text": goal})

        # Open tabs context
        urls = obs.get("open_pages_urls") or []
        titles = obs.get("open_pages_titles") or []
        if urls:
            tab_lines = ["\n# Currently open tabs"]
            active = obs.get("active_page_index", 0)
            for i, (url, title) in enumerate(zip(urls, titles)):
                star = " (active)" if i == active else ""
                tab_lines.append(f"Tab {i}{star}\n  Title: {title}\n  URL: {url}")
            content.append({"type": "text", "text": "\n".join(tab_lines)})

        # Screenshot
        content.append({"type": "text", "text": "\n# Screenshot of current page"})
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_to_png_data_url(screenshot), "detail": "auto"},
        })

        # Recent action history (text-only, last N steps)
        if self.action_history:
            content.append({"type": "text", "text": "\n# Recent actions"})
            start = max(0, len(self.action_history) - self.max_history_steps)
            for i in range(start, len(self.action_history)):
                think = (self.thinking_history[i] or "")[:200]
                step_lines = [f"Step {i + 1}:"]
                if think:
                    step_lines.append(f"  Reasoning: {think}{'...' if len(self.thinking_history[i]) > 200 else ''}")
                step_lines.append(f"  Action: {self.action_history[i]}")
                content.append({"type": "text", "text": "\n".join(step_lines)})

        last_err = obs.get("last_action_error") or ""
        if last_err:
            content.append({
                "type": "text",
                "text": f"\n# Previous action error\n{last_err[:500]}",
            })

        return content

    def _chat_completion(self, messages: list[dict[str, Any]]) -> Any:
        if self._is_bedrock:
            return self._bedrock_converse(messages)
        # max_tokens=2048 is high enough for any single coord-action response
        # (typical: <100 tokens) but won't truncate reasoning when models
        # interleave a <think> block before the action.
        # GPT-5 family rejects `max_tokens` — they require `max_completion_tokens`.
        # OpenAI's other models still accept `max_tokens`. Detect by model id.
        token_field = (
            "max_completion_tokens"
            if (self.model or "").startswith("gpt-5") or "/gpt-5" in (self.model or "")
            else "max_tokens"
        )
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            token_field: 2048,
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        return self.client.chat.completions.create(**kwargs)

    # ---- Bedrock Converse adapter --------------------------------------------

    def _bedrock_converse(self, messages: list[dict[str, Any]]) -> Any:
        """Translate OpenAI-style messages to Bedrock Converse API and call it.

        Returns an OpenAI-compatible response object (duck-typed) so the
        upstream `act()` loop can read `.choices[0].message.content`.
        """
        system_blocks: list[dict[str, Any]] = []
        bedrock_messages: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                system_blocks.append({"text": content if isinstance(content, str) else self._coalesce_text(content)})
                continue
            blocks: list[dict[str, Any]] = []
            if isinstance(content, str):
                blocks.append({"text": content})
            else:
                for part in content:
                    if not isinstance(part, dict):
                        blocks.append({"text": str(part)})
                        continue
                    ptype = part.get("type")
                    if ptype == "text":
                        text = part.get("text", "")
                        if text:
                            blocks.append({"text": text})
                    elif ptype == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        img_bytes, img_format = _data_url_to_bytes(url)
                        if img_bytes is not None:
                            blocks.append({
                                "image": {
                                    "format": img_format,
                                    "source": {"bytes": img_bytes},
                                }
                            })
            if not blocks:
                blocks = [{"text": ""}]
            bedrock_messages.append({"role": role or "user", "content": blocks})

        infer_cfg: dict[str, Any] = {"maxTokens": 1024}
        if self.temperature is not None:
            infer_cfg["temperature"] = float(self.temperature)

        kwargs: dict[str, Any] = {
            "modelId": self.model,
            "messages": bedrock_messages,
            "inferenceConfig": infer_cfg,
        }
        if system_blocks:
            kwargs["system"] = system_blocks

        resp = self.bedrock_client.converse(**kwargs)
        text = ""
        for blk in resp.get("output", {}).get("message", {}).get("content", []) or []:
            if isinstance(blk, dict) and "text" in blk:
                text += blk["text"]
        # Duck-type as OpenAI ChatCompletion: .choices[0].message.content
        from types import SimpleNamespace
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

    @staticmethod
    def _coalesce_text(parts: list[Any]) -> str:
        out: list[str] = []
        for p in parts or []:
            if isinstance(p, dict) and p.get("type") == "text":
                out.append(p.get("text", ""))
            elif isinstance(p, str):
                out.append(p)
        return "\n".join(out)

    @staticmethod
    def _is_valid_bg_action(action: str) -> bool:
        m = _ACTION_HEAD_RE.match(action)
        return bool(m and m.group(1) in VALID_COORD_ACTIONS)
