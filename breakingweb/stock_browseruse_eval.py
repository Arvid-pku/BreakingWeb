"""Stock browser-use harness for BreakingWeb.

Uses upstream `browser_use.Agent` without customization — stock system prompt,
vision, thinking (AgentBrain), and action registry minus a few dangerous or
irrelevant actions. This complements the custom WAB harness
(`browseruse_eval.py`) and gives paper-grade comparability: the two harnesses
evaluate the same task set with different agent loops, so readers can separate
"model ability" from "harness choice".

Banned actions (via Controller(exclude_actions=...)):
  - navigate, search, switch, close   — URL/tab tricks the benchmark forbids
  - evaluate                          — arbitrary JS (would read server state)
  - read_file, write_file, replace_file, upload_file  — filesystem escape
  - save_as_pdf                       — irrelevant

Defense in depth: Browser(allowed_domains=["127.0.0.1","localhost"]) blocks any
cross-origin attempts at the browser level.

CLI:
    python -m breakingweb.stock_browseruse_eval \\
        --model gemini-3-flash-preview --provider gemini \\
        --tasks booking_cancel_upcoming booking_budget_comparison \\
        --output-dir breakingweb/results/gemini_booking
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import getenv

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent

# Load GEMINI_API_KEY / OPENAI_API_KEY / etc. from breakingweb/.env.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BASE_DIR / ".env", override=False)
except Exception:
    pass

# Bump browser-use's Chrome-launch timeouts. Default is 30s per event, which
# reliably fails on contended slurm nodes, shared CI runners, or any machine
# where 2+ Chromes start in parallel. 180s gives Bedrock-routed Claude headroom
# while still failing fast on genuinely-stuck Chromes. These are read by
# browser_use/browser/events.py `_get_timeout(env, default)`, so explicit
# values in the environment still win.
os.environ.setdefault("TIMEOUT_BrowserStartEvent", "180")
os.environ.setdefault("TIMEOUT_BrowserLaunchEvent", "180")

# browser-use 0.12.6 also has a *separate* 30s timeout hardcoded inside
# `LocalBrowserWatchdog._wait_for_cdp_url` (no env-var hook): it polls
# `127.0.0.1:<debug_port>/json/version` for 30s and then raises
# `Browser did not start within 30 seconds`. Bumping the event-bus
# timeouts above doesn't help because the inner staticmethod uses its own
# default. Patch the staticmethod's default to 90s at import time so the
# inner and outer ceilings agree.
def _bump_chrome_inner_cdp_timeout() -> None:
    try:
        from browser_use.browser.watchdogs import local_browser_watchdog as _lbw
        _orig = _lbw.LocalBrowserWatchdog._wait_for_cdp_url

        async def _patched(port: int, timeout: float = 90) -> str:
            return await _orig(port, timeout)

        _lbw.LocalBrowserWatchdog._wait_for_cdp_url = staticmethod(_patched)
    except Exception:
        # Older / restructured browser-use: skip silently — outer event
        # timeouts still apply, just less generously.
        pass


_bump_chrome_inner_cdp_timeout()

# Stock browser-use exposes ~25 actions. We remove the ones that would let the
# agent escape the benchmark's UI-only contract.
_BANNED_ACTIONS: list[str] = [
    "navigate",
    "search",
    "switch",
    "close",
    "evaluate",
    "read_file",
    "write_file",
    "replace_file",
    "upload_file",
    "save_as_pdf",
]

# Extra actions dropped on the Claude-via-OpenRouter path. browser-use's stock
# schema (14 actions after _BANNED_ACTIONS, ~9.9k chars) triggers
# `compiled grammar is too large` on OR's Anthropic-family OAI-compat
# upstreams. Dropping these three shrinks the schema to ~8k chars which
# passes. See README "Claude via OpenRouter hits compiled grammar is too
# large" for measurements. Irrelevant on direct Anthropic / Bedrock Converse
# / GPT-via-OR paths.
_OPENROUTER_CLAUDE_EXTRA_BANNED: list[str] = [
    "screenshot",
    "find_text",
    "find_elements",
]


def _effective_banned(
    provider: str,
    model: str,
    extra_banned_actions: list[str] | None = None,
) -> list[str]:
    """Banned-action list actually applied to the Controller for this run.

    Order: start with `_BANNED_ACTIONS`, append CLI `--ban-action` args,
    append the Claude-via-OR extra set when applicable.
    """
    banned = list(_BANNED_ACTIONS)
    if extra_banned_actions:
        banned.extend(a for a in extra_banned_actions if a not in banned)
    if provider == "openrouter" and model.startswith("anthropic/"):
        for extra in _OPENROUTER_CLAUDE_EXTRA_BANNED:
            if extra not in banned:
                banned.append(extra)
    return banned


_DEFAULT_MAX_STEPS = 60
# 1200s task wall-clock + 240s/step covers Bedrock-routed Claude (≈40s/step
# observed on PrimBench v2). Faster providers finish well under this and don't
# pay any cost. PrimBench v2 used 600s/120s and clipped opus to ~14 effective
# steps — see scripts/aggregate_primbench_v2.py output for the analysis.
_DEFAULT_TIMEOUT = 1200
_DEFAULT_STEP_TIMEOUT = 240


# =============================================================================
# Bedrock Converse: toolChoice forcing (for third-party models)
# =============================================================================
#
# browser-use's stock ChatAWSBedrock never sets Converse's `toolChoice`, so
# models like Kimi / Qwen sometimes return plain-text reasoning instead of a
# structured tool_use block once context grows — causing "Expected structured
# output but no tool use found". This subclass injects toolChoice={'any': {}}
# into the Converse body. If the model provider refuses that field (some
# vendors accept only `auto`), we fall back to the unforced path so we never
# regress below upstream behavior.


def _make_bedrock_forced_class():
    """Lazy import so users without boto3 don't pay the import cost."""
    from dataclasses import dataclass
    from browser_use.llm.aws import ChatAWSBedrock
    from browser_use.llm.aws.serializer import AWSBedrockMessageSerializer
    from browser_use.llm.exceptions import ModelProviderError, ModelRateLimitError
    from browser_use.llm.views import ChatInvokeCompletion

    @dataclass
    class ChatAWSBedrockForced(ChatAWSBedrock):
        """ChatAWSBedrock + Converse `toolChoice: {any: {}}` when output_format given.

        The `toolChoice` field tells Bedrock's Converse API the model MUST call
        one of the provided tools (vs. just "may call them"). This plugs the
        hole that lets Kimi/Qwen return plain text at long context.
        """

        async def ainvoke(self, messages, output_format=None, **kwargs):
            # Non-structured path is unchanged — no tools, no toolChoice needed.
            if output_format is None:
                return await super().ainvoke(messages, output_format=None, **kwargs)

            try:
                from botocore.exceptions import ClientError
            except ImportError as e:
                raise ImportError("boto3/botocore required for Bedrock") from e

            bedrock_messages, system_message = AWSBedrockMessageSerializer.serialize_messages(messages)
            tools = self._format_tools_for_request(output_format)

            def _build_body(force_tool: bool) -> dict:
                body: dict[str, Any] = {}
                if system_message:
                    body["system"] = system_message
                inf = self._get_inference_config()
                if inf:
                    body["inferenceConfig"] = inf
                tool_config: dict[str, Any] = {"tools": tools}
                if force_tool:
                    tool_config["toolChoice"] = {"any": {}}
                body["toolConfig"] = tool_config
                if self.request_params:
                    body.update(self.request_params)
                return {k: v for k, v in body.items() if v is not None}

            client = self._get_client()

            # First attempt: forced. Fall back to unforced on ValidationException
            # caused by toolChoice rejection (vendor doesn't support it).
            for force_tool in (True, False):
                body = _build_body(force_tool=force_tool)
                try:
                    response = client.converse(modelId=self.model, messages=bedrock_messages, **body)
                    break
                except ClientError as e:
                    err = e.response.get("Error", {})
                    code = err.get("Code", "")
                    msg = err.get("Message", str(e))
                    if code in ("ThrottlingException", "TooManyRequestsException"):
                        raise ModelRateLimitError(message=msg, model=self.name) from e
                    is_toolchoice_reject = (
                        code == "ValidationException"
                        and ("toolChoice" in msg or "tool_choice" in msg or "toolConfig" in msg)
                    )
                    if force_tool and is_toolchoice_reject:
                        logger.warning(
                            "Bedrock model %r rejected toolChoice=any; retrying without force. (%s)",
                            self.model, msg,
                        )
                        continue
                    raise ModelProviderError(message=msg, model=self.name) from e
            else:
                raise ModelProviderError(message="converse failed after fallback", model=self.name)

            usage = self._get_usage(response)
            message = response.get("output", {}).get("message", {})
            content = message.get("content", [])

            for item in content:
                if "toolUse" in item:
                    tool_input = item["toolUse"].get("input", {})
                    try:
                        return ChatInvokeCompletion(
                            completion=output_format.model_validate(tool_input),
                            usage=usage,
                        )
                    except Exception as e:
                        if isinstance(tool_input, str):
                            try:
                                data = json.loads(tool_input)
                                return ChatInvokeCompletion(
                                    completion=output_format.model_validate(data),
                                    usage=usage,
                                )
                            except json.JSONDecodeError:
                                pass
                        raise ModelProviderError(
                            message=f"Failed to validate structured output: {e}",
                            model=self.name,
                        ) from e

            raise ModelProviderError(
                message="Expected structured output but no tool use found in response",
                model=self.name,
            )

    return ChatAWSBedrockForced


# =============================================================================
# OpenRouter: strip numeric bounds from the JSON schema sent with
# response_format=json_schema. Several OpenRouter upstreams for Claude
# (Anthropic direct, Amazon Bedrock, Azure) reject schemas containing
# `{"type": "integer"|"number", "minimum"|"maximum": N}` with:
#     output_config.format.schema: For 'integer' type,
#     property 'minimum' is not supported
# browser-use emits these on element-index fields (int) and on scroll
# pages (float). Removing the bounds from numeric nodes makes the request
# acceptable on every provider we've tested. The bound validation is still
# enforced on the client side via Pydantic's model_validate on the returned
# tool input — we're only loosening the wire schema, not the final accept
# gate.
# =============================================================================


# Default OpenRouter upstream-provider ignore list. Each entry has been shown
# to break a request that other providers accept cleanly via OR's gateway:
#   - Amazon Bedrock: rejects `json_schema.name` as `Extra inputs are not
#     permitted` (see `_make_openrouter_stripped_class` for the full story).
#   - Novita: returns `model features structured outputs not support` for
#     models other providers (Alibaba, DeepInfra, Fireworks, etc.) handle —
#     Novita just hasn't implemented strict `response_format=json_schema`.
# This is the default applied when `BREAKINGWEB_OPENROUTER_IGNORE` env var
# is unset. Users can override via env (see `_openrouter_provider_pref`).
# Direct providers (`--provider bedrock` etc.) are unaffected — Bedrock's
# native Converse API has no such issue, only its OAI-compat endpoint does.
_OPENROUTER_DEFAULT_IGNORE: list[str] = [
    "Amazon Bedrock",
    "Novita",
]


def _openrouter_provider_pref() -> dict[str, Any]:
    """Build the OpenRouter `provider` routing object from env vars.

    Default (no env vars set):
        {"ignore": ["Amazon Bedrock", "Novita"]}

    Env vars (all optional):
        BREAKINGWEB_OPENROUTER_IGNORE              csv, replaces default
        BREAKINGWEB_OPENROUTER_ONLY                csv, optional allowlist
        BREAKINGWEB_OPENROUTER_ORDER               csv, optional ordering
        BREAKINGWEB_OPENROUTER_ALLOW_FALLBACKS     bool, default true (omitted)
        BREAKINGWEB_OPENROUTER_REQUIRE_PARAMETERS  bool, default false (omitted)

    Empty / unset env vars are omitted from the result so OpenRouter never
    sees `provider.only=[]` etc. (which would be invalid). `IGNORE` is the
    one exception: setting it to empty string explicitly clears the default
    (allows all upstreams).
    """
    def _csv(name: str) -> list[str] | None:
        v = getenv(name)
        if v is None:
            return None
        return [s.strip() for s in v.split(",") if s.strip()]

    def _bool(name: str) -> bool | None:
        v = getenv(name)
        if v is None:
            return None
        return v.strip().lower() in ("1", "true", "yes", "y", "on")

    pref: dict[str, Any] = {}

    ignore = _csv("BREAKINGWEB_OPENROUTER_IGNORE")
    if ignore is None:
        ignore = list(_OPENROUTER_DEFAULT_IGNORE)
    if ignore:
        pref["ignore"] = ignore

    only = _csv("BREAKINGWEB_OPENROUTER_ONLY")
    if only:
        pref["only"] = only

    order = _csv("BREAKINGWEB_OPENROUTER_ORDER")
    if order:
        pref["order"] = order

    allow_fb = _bool("BREAKINGWEB_OPENROUTER_ALLOW_FALLBACKS")
    if allow_fb is not None:
        pref["allow_fallbacks"] = allow_fb

    if _bool("BREAKINGWEB_OPENROUTER_REQUIRE_PARAMETERS"):
        pref["require_parameters"] = True

    return pref


def _strip_numeric_bounds(schema: "Any") -> "Any":
    """Recursively drop min/max constraints from integer/number-typed nodes."""
    if isinstance(schema, dict):
        if schema.get("type") in ("integer", "number"):
            for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                schema.pop(key, None)
        for value in schema.values():
            _strip_numeric_bounds(value)
    elif isinstance(schema, list):
        for item in schema:
            _strip_numeric_bounds(item)
    return schema


def _make_openrouter_stripped_class():
    """ChatOpenRouter subclass that reimplements the structured-output path
    with two surgical local fixes.

    1. Numeric-bounds strip on the outbound JSON schema (see
       `_strip_numeric_bounds`) — Anthropic-family OAI-compat upstreams
       reject `minimum`/`maximum` on integer/number fields.

    2. Tolerant JSON parse on the inbound response — GPT-5 reasoning models
       on OR occasionally emit two concatenated AgentOutput JSONs in a
       single `message.content` (first turn + eagerly predicted next turn).
       If the strict parse fails, fall back to `json.JSONDecoder().raw_decode`
       to keep only the first valid JSON object; Pydantic still enforces
       the full AgentOutput schema on that object.

    Implementation: reimplement ChatOpenRouter.ainvoke's structured branch
    inline (~40 lines copied from browser-use 0.12.6) so both fixes are
    local to this subclass and there is **no global monkey-patching**. This
    matters: an earlier version patched `BaseModel.model_validate_json`
    globally and — because classmethod save/restore through `__func__` is
    fragile and the global attribute leaks under async concurrency —
    caused `BaseModel cannot be instantiated directly` errors in the
    Agent's retry path. Keeping state local to the instance avoids that.
    """
    import json as _json
    from dataclasses import dataclass
    from openai import APIConnectionError, APIStatusError, RateLimitError
    from openai.types.shared_params.response_format_json_schema import (
        JSONSchema,
        ResponseFormatJSONSchema,
    )
    from browser_use.llm.exceptions import ModelProviderError, ModelRateLimitError
    from browser_use.llm.openrouter.chat import ChatOpenRouter
    from browser_use.llm.openrouter.serializer import OpenRouterMessageSerializer
    from browser_use.llm.schema import SchemaOptimizer
    from browser_use.llm.views import ChatInvokeCompletion

    @dataclass
    class ChatOpenRouterStripped(ChatOpenRouter):
        async def ainvoke(self, messages, output_format=None, **kwargs):
            # Non-structured path: delegate unchanged.
            if output_format is None:
                return await super().ainvoke(messages, output_format=None, **kwargs)

            # Structured-output path: inline reimplementation of browser-use
            # ChatOpenRouter.ainvoke (lines 163-201 in 0.12.6), with schema
            # strip and tolerant JSON parse applied locally.
            openrouter_messages = OpenRouterMessageSerializer.serialize_messages(messages)

            extra_headers: dict[str, str] = {}
            if self.http_referer:
                extra_headers["HTTP-Referer"] = self.http_referer

            try:
                schema = _strip_numeric_bounds(
                    SchemaOptimizer.create_optimized_json_schema(output_format)
                )
                response_format_schema: JSONSchema = {
                    "name": "agent_output",
                    "strict": True,
                    "schema": schema,
                }
                # `self.extra_body` is set by `_build_llm` to the env-derived
                # OpenRouter provider routing pref (defaults: ignore Amazon
                # Bedrock + Novita, see `_openrouter_provider_pref`). It's
                # double-wrapped (`{"extra_body": {"provider": {...}}}`) so
                # that the parent class's `**self.extra_body` kwarg-unpack
                # lands the inner dict on the OpenAI SDK's `extra_body=`
                # request-body parameter.
                response = await self.get_client().chat.completions.create(
                    model=self.model,
                    messages=openrouter_messages,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    seed=self.seed,
                    response_format=ResponseFormatJSONSchema(
                        json_schema=response_format_schema,
                        type="json_schema",
                    ),
                    extra_headers=extra_headers,
                    **(self.extra_body or {}),
                )
                content = response.choices[0].message.content
                if content is None:
                    raise ModelProviderError(
                        message="Failed to parse structured output from model response",
                        status_code=500,
                        model=self.name,
                    )
                usage = self._get_usage(response)
                try:
                    parsed = output_format.model_validate_json(content)
                except Exception as parse_exc:
                    try:
                        obj, _end = _json.JSONDecoder().raw_decode(content.lstrip())
                    except _json.JSONDecodeError:
                        raise parse_exc from None
                    parsed = output_format.model_validate(obj)
                return ChatInvokeCompletion(completion=parsed, usage=usage)

            except RateLimitError as e:
                raise ModelRateLimitError(message=e.message, model=self.name) from e
            except APIConnectionError as e:
                raise ModelProviderError(message=str(e), model=self.name) from e
            except APIStatusError as e:
                # Surface OR's `metadata.provider_name` so failure logs make
                # it obvious which upstream actually rejected the request.
                upstream = None
                try:
                    body = e.body if isinstance(e.body, dict) else {}
                    md = (body.get("error") or {}).get("metadata") or {}
                    upstream = md.get("provider_name")
                except Exception:
                    pass
                msg = e.message
                if upstream:
                    msg = f"[upstream={upstream}] {msg}"
                raise ModelProviderError(
                    message=msg, status_code=e.status_code, model=self.name
                ) from e
            except ModelProviderError:
                raise
            except Exception as e:
                raise ModelProviderError(message=str(e), model=self.name) from e

    return ChatOpenRouterStripped


# =============================================================================
# Backend communication
# =============================================================================


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _build_llm(
    provider: str,
    model: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
):
    """Return a browser-use LLM wrapper for the chosen provider.

    Supported providers:
      gemini              — Google Gemini (ChatGoogle). Env: GEMINI_API_KEY
      openai              — OpenAI chat completions. Env: OPENAI_API_KEY [+ OPENAI_API_BASE_URL]
      bedrock             — AWS Bedrock Converse API via boto3. Env: AWS_BEDROCK_API_KEY
                              (mapped to AWS_BEARER_TOKEN_BEDROCK) + AWS_BEDROCK_REGION.
                              Covers any Bedrock model (Claude / Nova / Llama / Titan...).
      anthropic_bedrock   — Claude via AnthropicBedrock SDK (same auth as bedrock).
      anthropic           — Direct Anthropic API. Env: ANTHROPIC_API_KEY
      openrouter          — OpenRouter (meta-provider). Env: OPENROUTER_API_KEY
      vllm                — Local vLLM endpoint. Env: BREAKINGWEB_API_BASE_URL + _API_KEY
    """
    common: dict[str, Any] = {}
    if temperature is not None:
        common["temperature"] = temperature
    if max_tokens is not None:
        common["max_tokens"] = max_tokens

    if provider == "gemini":
        from browser_use import ChatGoogle
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("GEMINI_API_KEY not set (add to breakingweb/.env)")
        return ChatGoogle(model=model, api_key=key, **common)

    if provider == "openai":
        from browser_use.llm.openai.chat import ChatOpenAI as BUChatOpenAI
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        base_url = os.environ.get("OPENAI_API_BASE_URL") or None
        return BUChatOpenAI(model=model, api_key=key, base_url=base_url, **common)

    if provider in ("bedrock", "anthropic_bedrock"):
        # Map WAB-style AWS_BEDROCK_API_KEY → boto3's AWS_BEARER_TOKEN_BEDROCK env var.
        key = os.environ.get("AWS_BEDROCK_API_KEY", "") or os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
        if key:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = key
        region = os.environ.get("AWS_BEDROCK_REGION", "us-east-1")
        # browser-use's ChatAWSBedrock hard-checks for AWS_ACCESS_KEY_ID +
        # AWS_SECRET_ACCESS_KEY and ignores AWS_BEARER_TOKEN_BEDROCK. Passing
        # an explicit boto3 Session bypasses that check — modern boto3 picks
        # up the bearer token automatically when the env var is set.
        import boto3
        sess = boto3.Session(region_name=region)
        if provider == "anthropic_bedrock":
            from browser_use.llm.aws import ChatAnthropicBedrock
            return ChatAnthropicBedrock(model=model, aws_region=region, session=sess, **common)
        # Use the forced-toolChoice subclass so Kimi/Qwen can't silently
        # return plain text instead of a structured tool_use block.
        ChatAWSBedrockForced = _make_bedrock_forced_class()
        return ChatAWSBedrockForced(model=model, aws_region=region, session=sess, **common)

    if provider == "anthropic":
        from browser_use.llm.anthropic.chat import ChatAnthropic
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatAnthropic(model=model, api_key=key, **common)

    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set")
        # Compute the OR provider routing pref (env vars + defaults). Pass
        # it via the wrapper's `extra_body` field, which browser-use's
        # parent class kwarg-unpacks into chat.completions.create() — the
        # double-wrap (`{"extra_body": {...}}`) lands our payload in the
        # OpenAI SDK's `extra_body=` request-body parameter.
        pref = _openrouter_provider_pref()
        logger.info(
            "openrouter routing for %s: %s",
            model,
            pref or "(no provider routing — all upstreams allowed)",
        )
        or_extra_body = {"extra_body": {"provider": pref}} if pref else None
        return _make_openrouter_stripped_class()(
            model=model, api_key=key, extra_body=or_extra_body, **common,
        )

    if provider == "vllm":
        from browser_use.llm.openai.chat import ChatOpenAI as BUChatOpenAI
        base_url = getenv("BREAKINGWEB_API_BASE_URL", "http://localhost:8000/v1")
        key = getenv("BREAKINGWEB_API_KEY", "dummy")
        return BUChatOpenAI(model=model, api_key=key, base_url=base_url, **common)

    raise ValueError(
        f"provider {provider!r} not supported. Valid: "
        "gemini, openai, bedrock, anthropic_bedrock, anthropic, openrouter, vllm."
    )


# =============================================================================
# Trajectory construction (ports browseruse_eval.py's format so the same
# visualize.py + demo-site replay works for both harnesses)
# =============================================================================


def _history_to_trajectory(
    history,
    *,
    include_screenshots: bool,
    screenshots_dir: "Path | None" = None,
) -> list[dict]:
    """Convert a browser_use.AgentHistoryList into the WAB trajectory format.

    Step shape matches `browseruse_eval.build_trajectory_step`'s output, so
    `breakingweb.visualize` can render trajectories from either harness.

    Screenshot handling (stock-harness-only; custom harness doesn't set this):
      - If `include_screenshots` is False: `screenshot` field is omitted.
      - If `screenshots_dir` is given and the directory exists: each step's
        PNG is written as `<screenshots_dir>/step{N:02d}.png` and the step's
        `screenshot` field is set to the relative path "screenshots/step{N:02d}.png"
        (relative to the per-task trajectory.json that will reference it).
      - If `screenshots_dir` is None: the `screenshot` field holds a base64
        data URI inline (legacy single-file fallback).
    """
    from pathlib import Path
    import base64
    from breakingweb.browseruse_eval import _get_action_index, build_trajectory_step

    if history is None or not hasattr(history, "history"):
        return []

    screenshots: list[str | None]
    try:
        screenshots = list(history.screenshots()) if include_screenshots else []
    except Exception as exc:  # pragma: no cover — defensive against upstream breakage
        logger.warning("history.screenshots() failed: %s", exc)
        screenshots = []

    if include_screenshots and screenshots_dir is not None:
        Path(screenshots_dir).mkdir(parents=True, exist_ok=True)

    trajectory: list[dict] = []
    for i, item in enumerate(history.history):
        # Defensive per-step build: if any single step raises (e.g. a
        # browser-use schema variant our property accessors don't handle),
        # log + emit a minimal error placeholder rather than aborting the
        # whole trajectory. Without this, two intervention runs in the
        # sonnet_4_6_full_openrouter3 sweep ended up with steps=38 but
        # trajectory=[] because step ~36 raised and the partial 35-step
        # work was discarded by the outer try/except in the caller.
        try:
            mo = getattr(item, "model_output", None)
            state = getattr(item, "state", None)

            # When model_output is None (e.g. an LLM parse failure or a step
            # dropped by browser-use), we still emit a placeholder so that
            # trajectory.json stays aligned with screenshots/ — otherwise
            # downstream replay/visualize sees a gap (32 of 1038 trajectories
            # in the sonnet_4_6_full_openrouter3 sweep had this misalignment).
            if mo is None:
                status = "model_output_missing"
                for r in getattr(item, "result", None) or []:
                    if getattr(r, "error", None):
                        status = f"ERROR: {r.error}"
                        break
                placeholder_meta = getattr(item, "metadata", None)
                placeholder_elapsed = 0.0
                if placeholder_meta is not None:
                    placeholder_elapsed = float(
                        getattr(placeholder_meta, "duration_seconds", None)
                        or getattr(placeholder_meta, "elapsed", None)
                        or 0.0
                    )
                placeholder_step = build_trajectory_step(
                    step_num=i + 1,
                    thinking="",
                    memory="",
                    actions=[],
                    dom_elements={},
                    url=getattr(state, "url", "") or "",
                    status=status,
                    elapsed=round(placeholder_elapsed, 1),
                    action_results=[],
                )
                if include_screenshots and i < len(screenshots) and screenshots[i] and screenshots_dir is not None:
                    b64 = screenshots[i]
                    if b64.startswith("data:"):
                        b64 = b64.split(",", 1)[1]
                    png_path = Path(screenshots_dir) / f"step{i + 1:02d}.png"
                    try:
                        png_path.write_bytes(base64.b64decode(b64))
                        placeholder_step["screenshot"] = f"screenshots/{png_path.name}"
                    except Exception as exc:
                        logger.warning("failed to write %s: %s", png_path, exc)
                trajectory.append(placeholder_step)
                continue

            thinking = (getattr(mo, "thinking", None) or "") or (
                getattr(mo, "evaluation_previous_goal", None) or ""
            )
            memory = getattr(mo, "memory", None) or ""

            actions_raw = getattr(mo, "action", None) or []
            actions = []
            for a in actions_raw:
                try:
                    actions.append(a.model_dump(exclude_unset=True, exclude_none=True))
                except Exception:
                    # ActionModel variants sometimes fail exclude_unset; fall back.
                    actions.append(a.model_dump(exclude_none=True))

            # interacted_element is list-parallel-to-actions. Map it to a
            # {index: elem_info} dict keyed by the action's own target index so
            # build_trajectory_step's target lookup works.
            dom_elements: dict[int, dict] = {}
            interacted = getattr(state, "interacted_element", None) or []
            for act_idx, elem in enumerate(interacted):
                if elem is None:
                    continue
                action_target_idx = None
                if act_idx < len(actions):
                    action_target_idx = _get_action_index(actions[act_idx])
                if action_target_idx is None:
                    continue
                dom_elements[action_target_idx] = {
                    "tag_name": getattr(elem, "node_name", "") or "",
                    "attributes": getattr(elem, "attributes", None) or {},
                    "text": getattr(elem, "node_value", "") or "",
                }

            url = getattr(state, "url", "") or ""

            # Status: "success" unless any ActionResult in this step carried an error.
            status = "success"
            action_results: list[dict[str, Any]] = []
            for r in getattr(item, "result", None) or []:
                try:
                    result_data = r.model_dump(exclude_unset=True, exclude_none=True)
                except Exception:
                    result_data = {}
                    for attr in ("error", "extracted_content", "include_in_memory", "is_done", "success"):
                        value = getattr(r, attr, None)
                        if value is not None:
                            result_data[attr] = value
                result_data["status"] = "error" if getattr(r, "error", None) else "success"
                action_results.append(result_data)
                if getattr(r, "error", None):
                    status = f"ERROR: {r.error}"

            metadata = getattr(item, "metadata", None)
            elapsed = 0.0
            if metadata is not None:
                elapsed = float(
                    getattr(metadata, "duration_seconds", None)
                    or getattr(metadata, "elapsed", None)
                    or 0.0
                )

            step = build_trajectory_step(
                step_num=i + 1,
                thinking=thinking,
                memory=memory,
                actions=actions,
                dom_elements=dom_elements,
                url=url,
                status=status,
                elapsed=round(elapsed, 1),
                action_results=action_results,
            )
            if include_screenshots and i < len(screenshots) and screenshots[i]:
                b64 = screenshots[i]
                # Strip any incoming data: prefix to recover bare base64 bytes.
                if b64.startswith("data:"):
                    b64 = b64.split(",", 1)[1]
                if screenshots_dir is not None:
                    # Externalize: write PNG file, reference by relative path.
                    png_path = Path(screenshots_dir) / f"step{i + 1:02d}.png"
                    try:
                        png_path.write_bytes(base64.b64decode(b64))
                        step["screenshot"] = f"screenshots/{png_path.name}"
                    except Exception as exc:
                        logger.warning("failed to write %s: %s", png_path, exc)
                        step["screenshot"] = f"data:image/png;base64,{b64}"
                else:
                    # No dir provided → fallback inline (legacy / programmatic use).
                    step["screenshot"] = f"data:image/png;base64,{b64}"
            trajectory.append(step)
        except Exception as exc:
            logger.warning(
                "trajectory step %d build failed: %s: %s",
                i + 1, type(exc).__name__, exc,
            )
            try:
                err_step = build_trajectory_step(
                    step_num=i + 1,
                    thinking="",
                    memory="",
                    actions=[],
                    dom_elements={},
                    url="",
                    status=f"ERROR: trajectory build failed: {type(exc).__name__}: {exc}",
                    elapsed=0.0,
                    action_results=[],
                )
            except Exception:
                err_step = {
                    "step": i + 1,
                    "thought": "",
                    "action": [],
                    "targets": {},
                    "status": f"ERROR: {type(exc).__name__}: {exc}",
                    "elapsed_seconds": 0.0,
                }
            trajectory.append(err_step)

    return trajectory


# =============================================================================
# Single-task runner
# =============================================================================


async def run_episode(
    task_id: str,
    *,
    model: str,
    provider: str = "gemini",
    variant_filename: str | None = None,
    env_seed: int | None = None,
    server_host: str = "127.0.0.1",
    backend_port: int = 8080,
    frontend_port: int = 8084,
    max_steps: int = _DEFAULT_MAX_STEPS,
    timeout_seconds: int = _DEFAULT_TIMEOUT,
    headless: bool = True,
    verbose: bool = True,
    # --- Stock browser-use tunables ---
    temperature: float | None = None,
    max_tokens: int | None = None,
    use_vision: bool = True,
    use_thinking: bool = True,
    max_actions_per_step: int = 4,
    max_failures: int = 3,
    step_timeout: int = _DEFAULT_STEP_TIMEOUT,
    extra_banned_actions: list[str] | None = None,
    # --- Trajectory output (on by default — same schema as browseruse_eval, plus `screenshot`) ---
    record_trajectory: bool = True,
    trajectory_screenshots: bool = True,
    # If set, PNG screenshots are written here (as step{N:02d}.png) and the
    # trajectory JSON references them by relative path; a self-contained
    # trajectory.json is also written alongside the screenshots/ directory.
    # If None, screenshots are embedded inline as base64 data URIs (legacy).
    trajectory_dir: "Path | None" = None,
) -> dict:
    """Run one BreakingWeb task through the stock browser-use agent."""
    from browser_use import Agent, Browser, Controller
    from .tasks._registry import get_task as _get_task

    task_def = _get_task(task_id)
    env_id = task_def.env_id

    # 1. Create a fresh session via the backend API. The response gives us
    #    the session id + rendered instruction + start path. Optionally apply
    #    a degradation variant by passing its filename (backend resolves it
    #    against breakingweb/injector/variants/).
    backend = f"http://{server_host}:{backend_port}"
    session_payload: dict[str, Any] = {"task_id": task_id}
    if variant_filename:
        session_payload["variant_filename"] = variant_filename
    # Omitted unless explicitly requested, so the backend keeps its own default
    # (42) and every existing sweep reproduces byte-for-byte.
    if env_seed is not None:
        session_payload["seed"] = env_seed
    created = _http_json(
        f"{backend}/api/env/{env_id}/session",
        method="POST",
        payload=session_payload,
    )
    session_id = created["session_id"]
    instruction = created["instruction"]
    start_path = created.get("start_path", "/home")

    # 2. Build the launch URL the agent will land on.
    launch_url = (
        f"http://{server_host}:{frontend_port}/env/{env_id}{start_path}"
        f"?session={urllib.parse.quote(session_id)}&agent_mode=1"
    )

    if verbose:
        print(f"[{task_id}] session={session_id}")
        print(f"  URL: {launch_url}")
        print(f"  Goal: {instruction[:120]}{'...' if len(instruction) > 120 else ''}")

    # 3. Compose the task text. The harness pre-navigates the browser to the
    #    task URL before agent.run() (see step 7); `directly_open_url=False`
    #    keeps browser-use from trying to queue a banned `navigate` action.
    goal_text = (
        "You are already on the BreakingWeb booking site. Complete the "
        f"following task on the current page.\n\n"
        f"TASK:\n{instruction}\n\n"
        "RULES:\n"
        "- Interact only with elements visible on the page. Do not try to navigate "
        "to external URLs or open new tabs.\n"
        "- If an action fails or seems stuck, read the page carefully and try an "
        "alternative UI path.\n"
        "- Call done(success=true) when the task is fully complete."
    )

    # 4. Per-task temp dirs so concurrent runs don't clobber each other.
    tmp_root = Path(tempfile.mkdtemp(prefix=f"stock-bu-{task_id}-"))
    downloads_path = tmp_root / "downloads"
    user_data_dir = tmp_root / "user-data"
    traces_dir = tmp_root / "traces"
    for p in (downloads_path, user_data_dir, traces_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Per-model viewport: Anthropic computer-use trained on 1024×768 (XGA);
    # OpenAI's CUA on 1600×900; Gemini/Qwen flexible at 1280×720.
    # _viewport_for_model lives in pixel_eval to avoid cross-import cycles —
    # we duplicate the dispatch here (small + branch-stable).
    pl = (provider or "").lower(); ml = (model or "").lower()
    # Order matters: qwen runs on Bedrock too — match it BEFORE the
    # "pl == 'bedrock'" branch claims it.
    if "qwen" in ml:
        vw, vh = 1280, 720
    elif "claude" in ml or "anthropic" in pl or pl == "bedrock":
        vw, vh = 1024, 768
    elif "gpt" in ml or pl == "openai":
        vw, vh = 1600, 900
    else:
        vw, vh = 1280, 720

    browser = Browser(
        headless=headless,
        viewport={"width": vw, "height": vh},
        highlight_elements=False,
        allowed_domains=[server_host, "localhost"],
        user_data_dir=user_data_dir,
        downloads_path=downloads_path,
        traces_dir=traces_dir,
        # Disable Chrome's sandbox. Safe here because allowed_domains already
        # confines navigation to our local WAB backend, and the renderer only
        # ever loads seeded benchmark pages. This also avoids the Ubuntu 24.04
        # regression where AppArmor's `unprivileged_userns` restriction breaks
        # Chrome's zygote → Chromium launches but the CDP port never opens →
        # browser-use times out with `BrowserStartEvent timed out after 30s`.
        # Equivalent to passing `--no-sandbox`; equivalent to setting the
        # `IN_DOCKER=true` env var that browser-use watches for.
        chromium_sandbox=False,
    )

    # 5. Restrict the action registry. This is the key integrity measure — the
    #    agent cannot call `navigate`, `evaluate`, `read_file`, etc. On the
    #    Claude-via-OR path, 3 more actions are dropped so the schema stays
    #    under Anthropic's strict-grammar size limit (see
    #    `_OPENROUTER_CLAUDE_EXTRA_BANNED`).
    banned = _effective_banned(provider, model, extra_banned_actions)
    controller = Controller(exclude_actions=banned)

    # 6. Stock configuration (tunable via kwargs).
    llm = _build_llm(provider, model, temperature=temperature, max_tokens=max_tokens)
    agent = Agent(
        task=goal_text,
        llm=llm,
        browser=browser,
        controller=controller,
        use_vision=use_vision,
        use_thinking=use_thinking,
        flash_mode=False,
        max_actions_per_step=max_actions_per_step,
        max_failures=max_failures,
        step_timeout=step_timeout,
        generate_gif=False,
        # Must be False — otherwise browser-use extracts the URL from the task
        # text and queues a `navigate` initial-action, which is banned.
        directly_open_url=False,
    )

    start_ts = time.time()
    completed = False
    # Pre-navigate to the task URL before handing control to the agent. The
    # Agent.run() internally starts the browser session if it isn't started,
    # so we open it explicitly here, navigate, then run.
    try:
        await browser.start()
        await browser.navigate_to(launch_url)
    except Exception as exc:
        logger.exception("Pre-navigation failed for %s: %s", task_id, exc)
        # Fall through to agent.run(); it will re-attempt startup and may
        # produce a clearer error in the resulting history.

    try:
        history = await asyncio.wait_for(
            agent.run(max_steps=max_steps),
            timeout=timeout_seconds,
        )
        completed = True
    except asyncio.TimeoutError:
        logger.error("Task %s timed out after %ds", task_id, timeout_seconds)
        history = getattr(agent, "history", None)
    except Exception as exc:
        logger.exception("Task %s raised: %s", task_id, exc)
        history = getattr(agent, "history", None)

    elapsed = round(time.time() - start_ts, 1)

    # 7. Ask the backend for the evaluation score. The endpoint is
    #    POST /api/env/<env>/evaluate with session_id in the body. Omitting
    #    task_id keeps us on the session's bound task, which require_evaluation_access
    #    permits without a controller secret.
    try:
        eval_resp = _http_json(
            f"{backend}/api/env/{env_id}/evaluate",
            method="POST",
            payload={"session_id": session_id},
        )
        score = float(eval_resp.get("score", 0.0))
        success = bool(eval_resp.get("success", False))
        reasoning = eval_resp.get("reasoning", "")
        checks = eval_resp.get("checks", [])
        negative_checks = eval_resp.get("negative_checks", [])
    except Exception as exc:
        logger.error("Evaluate endpoint failed for %s: %s", task_id, exc)
        score, success, reasoning = 0.0, False, f"evaluate failed: {exc}"
        checks, negative_checks = [], []

    # 8. Close browser. browser-use's Browser doesn't expose a public .close(),
    #    but the context manager / explicit kill handles it in practice.
    try:
        if hasattr(browser, "stop"):
            await browser.stop()
    except Exception:
        pass

    # 9. Build trajectory in the same schema as browseruse_eval.py so
    #    breakingweb.visualize can render runs from either harness. When a
    #    `trajectory_dir` is provided, PNG screenshots are externalized to
    #    `<trajectory_dir>/screenshots/` and the step's `screenshot` field
    #    becomes a relative path ("screenshots/stepNN.png") instead of a
    #    base64 data URI. A self-contained per-task trajectory.json is also
    #    written alongside the screenshots/ directory so each task folder
    #    can be inspected or shipped independently.
    trajectory: list[dict] = []
    screenshots_dir = None
    if record_trajectory and trajectory_dir is not None:
        trajectory_dir = Path(trajectory_dir)
        trajectory_dir.mkdir(parents=True, exist_ok=True)
        if trajectory_screenshots:
            screenshots_dir = trajectory_dir / "screenshots"
    if record_trajectory:
        try:
            trajectory = _history_to_trajectory(
                history,
                include_screenshots=trajectory_screenshots,
                screenshots_dir=screenshots_dir,
            )
        except Exception as exc:
            logger.warning("trajectory build failed for %s: %s", task_id, exc)

    # 10. Shape the result to match browseruse_eval.py's output so downstream
    #     aggregation scripts, visualize.py, and replay tooling work uniformly.
    n_steps = (
        len(history.model_dump()["history"])
        if (history and hasattr(history, "model_dump"))
        else 0
    )
    agent_block: dict[str, Any] = {
        "model": model,
        "provider": provider,
        "harness": "stock-browser-use",
        "viewport": [vw, vh],
        "elapsed_seconds": elapsed,
        "completed": completed,
        "steps": n_steps,
    }
    if record_trajectory:
        agent_block["trajectory"] = trajectory

    result = {
        "task_id": task_id,
        "session_id": session_id,
        "evaluation": {
            "score": score,
            "success": success,
            "reasoning": reasoning,
            "checks": checks,
            "negative_checks": negative_checks,
        },
        "agent": agent_block,
    }

    # 11. Write a self-contained per-task trajectory.json when a dir was given.
    #     Summary (many-task) and run_manifest files are written by the caller
    #     (run_picks.py or the CLI runner) so this function stays per-task.
    if record_trajectory and trajectory_dir is not None:
        traj_file = trajectory_dir / "trajectory.json"
        try:
            traj_file.write_text(json.dumps(result, indent=2, default=str))
        except Exception as exc:
            logger.warning("failed to write %s: %s", traj_file, exc)

    return result


# =============================================================================
# Multi-task runner
# =============================================================================


def _task_slug(task_id: str, variant_filename: str | None = None, cond: str | None = None) -> str:
    """Return a filesystem-safe subdirectory name for a task run.

    Format:
      "<task_id>__<cond>"  when condition is known (clean / intervention)
      "<task_id>"          otherwise
    """
    if cond:
        return f"{task_id}__{cond}"
    if variant_filename:
        return f"{task_id}__intervention"
    return task_id


def _summary_entry(result: dict, trajectory_path: str | None) -> dict:
    """Strip the full trajectory from a result and add a trajectory_path pointer.

    The summary is a one-stop file for grid analysis (score, pass, elapsed,
    steps) without carrying the per-step data. Users drill into a specific
    task via `<output-dir>/<trajectory_path>`.
    """
    agent = dict(result.get("agent", {}))
    agent.pop("trajectory", None)  # full trajectory lives in per-task file
    entry = {
        "task_id": result.get("task_id"),
        "session_id": result.get("session_id"),
        "evaluation": result.get("evaluation", {}),
        "agent": agent,
    }
    if trajectory_path is not None:
        entry["trajectory_path"] = trajectory_path
    for k in ("variant_filename", "pick_metadata"):
        if k in result:
            entry[k] = result[k]
    return entry


def write_run_artifacts(
    output_dir: "str | Path",
    *,
    model: str,
    provider: str,
    results: list[dict],
    trajectory_paths: list[str | None],
    wall_seconds: float,
    started_at: str,
    ended_at: str,
    extra_manifest: dict | None = None,
) -> Path:
    """Write summary.json + run_manifest.json for a completed run.

    Each per-task trajectory.json is expected to have already been written
    by run_episode() (via its `trajectory_dir` parameter). This function
    just produces the top-level aggregation pointing at them.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    passed = sum(1 for r in results if r.get("evaluation", {}).get("success"))
    avg = sum(r.get("evaluation", {}).get("score", 0.0) for r in results) / max(1, len(results))

    summary = {
        "model": model,
        "provider": provider,
        "harness": "stock-browser-use",
        "banned_actions": _effective_banned(provider, model),
        "n": len(results),
        "passed": passed,
        "avg_score": avg,
        "wall_seconds": wall_seconds,
        "started_at": started_at,
        "ended_at": ended_at,
        "results": [
            _summary_entry(r, tp) for r, tp in zip(results, trajectory_paths)
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    manifest = {
        "model": model,
        "provider": provider,
        "harness": "stock-browser-use",
        "n_tasks": len(results),
        "started_at": started_at,
        "ended_at": ended_at,
        "wall_seconds": wall_seconds,
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    return out


async def run_evaluation(
    *,
    model: str,
    provider: str = "gemini",
    task_filter: list[str] | None = None,
    environments_filter: list[str] | None = None,
    max_steps: int = _DEFAULT_MAX_STEPS,
    timeout_per_task: int = _DEFAULT_TIMEOUT,
    headless: bool = True,
    server_host: str = "127.0.0.1",
    backend_port: int = 8080,
    frontend_port: int = 8084,
    output_dir: str = "breakingweb/results/stock_bu_run",
    verbose: bool = True,
    # --- Stock browser-use tunables (threaded to run_episode) ---
    temperature: float | None = None,
    max_tokens: int | None = None,
    use_vision: bool = True,
    use_thinking: bool = True,
    max_actions_per_step: int = 4,
    max_failures: int = 3,
    step_timeout: int = _DEFAULT_STEP_TIMEOUT,
    extra_banned_actions: list[str] | None = None,
    record_trajectory: bool = True,
    trajectory_screenshots: bool = True,
) -> list[dict]:
    from .agent_eval import resolve_task_ids
    from datetime import datetime, timezone

    task_ids = resolve_task_ids(task_filter, environments_filter)
    if not task_ids:
        print("No tasks to evaluate.", file=sys.stderr)
        return []

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir = out_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)

    if verbose:
        print(f"Agent:    {model} (via {provider})")
        print(f"Harness:  stock browser-use")
        print(f"Tasks:    {len(task_ids)}")
        print(f"Budget:   steps={max_steps}, timeout={timeout_per_task}s")
        print(f"Banned:   {', '.join(_effective_banned(provider, model, extra_banned_actions))}")
        print(f"Writing:  {out_dir}/")
        print("=" * 60)

    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.time()

    results: list[dict] = []
    trajectory_paths: list[str | None] = []
    for tid in task_ids:
        slug = _task_slug(tid)
        task_dir = tasks_dir / slug
        try:
            res = await run_episode(
                tid,
                model=model,
                provider=provider,
                server_host=server_host,
                backend_port=backend_port,
                frontend_port=frontend_port,
                max_steps=max_steps,
                timeout_seconds=timeout_per_task,
                headless=headless,
                verbose=verbose,
                temperature=temperature,
                max_tokens=max_tokens,
                use_vision=use_vision,
                use_thinking=use_thinking,
                max_actions_per_step=max_actions_per_step,
                max_failures=max_failures,
                step_timeout=step_timeout,
                extra_banned_actions=extra_banned_actions,
                record_trajectory=record_trajectory,
                trajectory_screenshots=trajectory_screenshots,
                trajectory_dir=task_dir if record_trajectory else None,
            )
            trajectory_paths.append(f"tasks/{slug}/trajectory.json" if record_trajectory else None)
        except Exception as exc:
            logger.error("Fatal error on %s: %s", tid, exc, exc_info=True)
            res = {
                "task_id": tid,
                "evaluation": {"score": 0.0, "success": False, "reasoning": f"fatal: {exc}"},
                "agent": {"model": model, "provider": provider, "harness": "stock-browser-use", "steps": 0},
            }
            trajectory_paths.append(None)
        results.append(res)
        ev = res["evaluation"]
        if verbose:
            status = "PASS" if ev["success"] else "FAIL"
            print(f"  [{status}] {tid} score={ev['score']:.2f} ({res['agent'].get('elapsed_seconds', 0)}s)")

    wall = time.time() - t0
    ended_at = datetime.now(timezone.utc).isoformat()

    write_run_artifacts(
        out_dir,
        model=model,
        provider=provider,
        results=results,
        trajectory_paths=trajectory_paths,
        wall_seconds=wall,
        started_at=started_at,
        ended_at=ended_at,
        extra_manifest={"task_filter": task_filter, "environments_filter": environments_filter},
    )

    if verbose:
        n = len(results)
        p = sum(1 for r in results if r["evaluation"].get("success"))
        avg = sum(r["evaluation"].get("score", 0) for r in results) / max(n, 1)
        print("=" * 60)
        print(f"SUMMARY: {p}/{n} passed | avg score: {avg:.3f}")
        print(f"Summary: {out_dir}/summary.json")

    return results


# =============================================================================
# CLI
# =============================================================================


def main():
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(
        description="BreakingWeb evaluation via stock browser-use Agent",
    )
    p.add_argument("--model", required=True, help="e.g. gemini-3-flash-preview")
    p.add_argument("--provider", default="gemini",
                   choices=["gemini", "openai", "bedrock", "anthropic_bedrock",
                            "anthropic", "openrouter", "vllm"])
    p.add_argument("--tasks", nargs="*", help="task IDs to run (default: all)")
    p.add_argument("--environments", nargs="*", help="env filter (e.g. booking)")
    p.add_argument("--max-steps", type=int, default=_DEFAULT_MAX_STEPS)
    p.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT)
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--no-headless", action="store_false", dest="headless")
    p.add_argument("--server-host", default="127.0.0.1")
    p.add_argument("--backend-port", type=int, default=8080)
    p.add_argument("--frontend-port", type=int, default=8084)
    p.add_argument(
        "--output-dir",
        default="breakingweb/results/stock_bu_run",
        help="Directory for run artifacts: summary.json, run_manifest.json, "
             "tasks/<task_id>/trajectory.json, tasks/<task_id>/screenshots/*.png "
             "(default: breakingweb/results/stock_bu_run)",
    )
    p.add_argument("--quiet", "-q", action="store_true")

    # Stock-browser-use tunables
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--no-vision", dest="use_vision", action="store_false", default=True,
                   help="disable screenshots (DOM-only, cheaper)")
    p.add_argument("--no-thinking", dest="use_thinking", action="store_false", default=True,
                   help="disable AgentBrain planner step")
    p.add_argument("--max-actions-per-step", type=int, default=4)
    p.add_argument("--max-failures", type=int, default=3)
    p.add_argument("--step-timeout", type=int, default=_DEFAULT_STEP_TIMEOUT)
    p.add_argument("--ban-action", action="append", default=None,
                   metavar="NAME",
                   help="ban an additional action beyond the default list (repeatable)")
    p.add_argument("--no-trajectory", dest="record_trajectory",
                   action="store_false", default=True,
                   help="don't embed the per-step trajectory in the output JSON")
    p.add_argument("--no-trajectory-screenshots",
                   dest="trajectory_screenshots",
                   action="store_false", default=True,
                   help="record the trajectory but omit base64 PNG screenshots "
                        "(trades ~10MB/task of size for no visual replay)")

    args = p.parse_args()

    asyncio.run(run_evaluation(
        model=args.model,
        provider=args.provider,
        task_filter=args.tasks,
        environments_filter=args.environments,
        max_steps=args.max_steps,
        timeout_per_task=args.timeout,
        headless=args.headless,
        server_host=args.server_host,
        backend_port=args.backend_port,
        frontend_port=args.frontend_port,
        output_dir=args.output_dir,
        verbose=not args.quiet,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        use_vision=args.use_vision,
        use_thinking=args.use_thinking,
        max_actions_per_step=args.max_actions_per_step,
        max_failures=args.max_failures,
        step_timeout=args.step_timeout,
        extra_banned_actions=args.ban_action,
        record_trajectory=args.record_trajectory,
        trajectory_screenshots=args.trajectory_screenshots,
    ))


if __name__ == "__main__":
    main()
