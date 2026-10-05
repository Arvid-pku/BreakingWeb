"""Network injection layer: HTTP interception via Playwright page.route().

Design principles:
  1. FILTER not WALL — task remains solvable with the target primitive.
  2. DISTRIBUTED not ONE-SHOT — degradations persist throughout the task.
  3. DETERMINISTIC — same seed produces same challenge sequence every run.

Behavior modes (set via `behavior.mode` in params):
  once         — fail first N requests, then pass (current default)
  intermittent — fail with probability P, seeded for determinism
  progressive  — escalate difficulty over time (stages)

Targets Patience and Verification primitives.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any


def _seeded_should_fire(seed: int, call_index: int, probability: float) -> bool:
    """Deterministic coin flip: given seed + call index, return True with `probability`.

    Same seed + index always returns the same result across runs.
    """
    h = hashlib.md5(f"{seed}:{call_index}".encode()).hexdigest()
    return (int(h[:8], 16) / 0x100000000) < probability


def _seeded_quantile(seed: int, call_index: int) -> float:
    h = hashlib.md5(f"{seed}:q:{call_index}".encode()).hexdigest()
    return int(h[:8], 16) / 0x100000000


def _tail_latency_ms(seed: int, call_index: int, p50: int, p95: int, p99: int) -> int:
    q = _seeded_quantile(seed, call_index)
    anchors = [(0.0, 0), (0.5, p50), (0.95, p95), (0.99, p99), (1.0, int(p99 * 1.5))]
    for i in range(1, len(anchors)):
        q0, v0 = anchors[i - 1]
        q1, v1 = anchors[i]
        if q < q1:
            span = q1 - q0 or 1e-9
            return int(v0 + (v1 - v0) * ((q - q0) / span))
    return int(p99 * 1.5)


async def apply_network_injection(page: Any, params: dict[str, Any]) -> None:
    """Register a network injection on a Playwright page."""
    url_pattern = params.get("url_pattern", "**/*")
    action = params.get("action", "")
    behavior = params.get("behavior", {})
    mode = behavior.get("mode", "once")
    behavior_seed = behavior.get("seed", 42)

    if action == "delay":
        # Patience: adds latency. Agent with patience waits; without acts prematurely.
        if mode == "progressive":
            stages = behavior.get("stages", [{"after_call": 0, "delay_ms": params.get("delay_ms", 3000)}])
            call_counter = {"n": 0}

            async def progressive_delay_handler(route):
                call_counter["n"] += 1
                # Find the current stage
                current_delay = 0
                for stage in stages:
                    if call_counter["n"] >= stage.get("after_call", 0):
                        current_delay = stage.get("delay_ms", 0)
                if current_delay > 0:
                    await asyncio.sleep(current_delay / 1000)
                await route.continue_()

            await page.route(url_pattern, progressive_delay_handler)

        elif mode == "intermittent":
            probability = behavior.get("probability", 0.3)
            delay_ms = params.get("delay_ms", 3000)
            call_counter = {"n": 0}

            async def intermittent_delay_handler(route):
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    await asyncio.sleep(delay_ms / 1000)
                await route.continue_()

            await page.route(url_pattern, intermittent_delay_handler)

        elif mode == "tail_latency":
            p50 = int(behavior.get("p50_ms", 100))
            p95 = int(behavior.get("p95_ms", 2000))
            p99 = int(behavior.get("p99_ms", 5000))
            call_counter = {"n": 0}

            async def tail_latency_handler(route):
                call_counter["n"] += 1
                sampled = _tail_latency_ms(behavior_seed, call_counter["n"], p50, p95, p99)
                if sampled > 0:
                    await asyncio.sleep(sampled / 1000)
                await route.continue_()

            await page.route(url_pattern, tail_latency_handler)

        elif mode == "correlated_window":
            start = int(behavior.get("window_start_call", 3))
            duration = int(behavior.get("window_duration_calls", 4))
            slow_ms = int(behavior.get("slow_ms", params.get("delay_ms", 3000)))
            call_counter = {"n": 0}

            async def correlated_window_handler(route):
                call_counter["n"] += 1
                if start < call_counter["n"] <= start + duration:
                    await asyncio.sleep(slow_ms / 1000)
                await route.continue_()

            await page.route(url_pattern, correlated_window_handler)

        elif mode == "write_only_slow":
            delay_ms = int(params.get("delay_ms", 2500))
            methods = set(str(m).upper() for m in params.get("methods", ["POST", "PUT", "PATCH", "DELETE"]))

            async def write_only_handler(route):
                if route.request.method.upper() in methods:
                    await asyncio.sleep(delay_ms / 1000)
                await route.continue_()

            await page.route(url_pattern, write_only_handler)

        else:  # mode == "once" or default
            delay_ms = params.get("delay_ms", 3000)

            async def delay_handler(route):
                await asyncio.sleep(delay_ms / 1000)
                await route.continue_()

            await page.route(url_pattern, delay_handler)

    elif action == "transient_flash":
        # Patience: briefly shows wrong content before real content.
        flash_html = params.get("html", "<div>Loading...</div>")
        duration_ms = params.get("duration_ms", 3000)

        if mode == "intermittent":
            probability = behavior.get("probability", 0.4)
            call_counter = {"n": 0}

            async def intermittent_flash_handler(route):
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    response = await route.fetch()
                    body = await response.text()
                    injected = (
                        f'<div id="__flash_{call_counter["n"]}">{flash_html}</div>'
                        f'<div id="__real_{call_counter["n"]}" style="display:none">{body}</div>'
                        f"<script>setTimeout(()=>{{"
                        f"document.getElementById('__flash_{call_counter['n']}')?.remove();"
                        f"const r=document.getElementById('__real_{call_counter['n']}');"
                        f"if(r)r.style.display='';}},{duration_ms});</script>"
                    )
                    await route.fulfill(status=200, body=injected, headers=dict(response.headers))
                else:
                    await route.continue_()

            await page.route(url_pattern, intermittent_flash_handler)
        else:
            async def flash_handler(route):
                response = await route.fetch()
                body = await response.text()
                injected = (
                    f'<div id="__transient_flash">{flash_html}</div>'
                    f'<div id="__real_content" style="display:none">{body}</div>'
                    f"<script>setTimeout(()=>{{"
                    f"document.getElementById('__transient_flash')?.remove();"
                    f"const r=document.getElementById('__real_content');"
                    f"if(r)r.style.display='';}},{duration_ms});</script>"
                )
                await route.fulfill(status=200, body=injected, headers=dict(response.headers))

            await page.route(url_pattern, flash_handler)

    elif action == "silent_fail":
        # Verification: writes silently fail — agent must check and retry.
        fake_body = params.get("response_body", {"success": True})
        methods = set(params.get("methods", ["POST", "PUT"]))

        if mode == "intermittent":
            # Randomly fail writes with probability P — agent must verify EVERY action
            probability = behavior.get("probability", 0.3)
            call_counter = {"n": 0}

            async def intermittent_silent_handler(route):
                if route.request.method in methods:
                    call_counter["n"] += 1
                    if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                        await route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(fake_body),
                        )
                        return
                await route.continue_()

            await page.route(url_pattern, intermittent_silent_handler)

        else:  # mode == "once"
            # First N writes fail, rest succeed
            fail_count = params.get("fail_count", 1)
            write_counter: dict[str, int] = {}

            async def silent_handler(route):
                if route.request.method in methods:
                    req_url = route.request.url
                    write_counter.setdefault(req_url, 0)
                    write_counter[req_url] += 1
                    if write_counter[req_url] <= fail_count:
                        await route.fulfill(
                            status=200,
                            content_type="application/json",
                            body=json.dumps(fake_body),
                        )
                        return
                await route.continue_()

            await page.route(url_pattern, silent_handler)

    elif action == "stale_data":
        # Verification: first N reads return stale data, then real data.
        stale_body = params.get("stale_body", {})
        stale_count = params.get("stale_count", 1)

        if mode == "intermittent":
            probability = behavior.get("probability", 0.3)
            call_counter = {"n": 0}

            async def intermittent_stale_handler(route):
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(stale_body),
                    )
                else:
                    await route.continue_()

            await page.route(url_pattern, intermittent_stale_handler)
        else:
            call_counter = {"n": 0}

            async def stale_handler(route):
                call_counter["n"] += 1
                if call_counter["n"] <= stale_count:
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(stale_body),
                    )
                else:
                    await route.continue_()

            await page.route(url_pattern, stale_handler)

    elif action == "error_then_success":
        # Patience: transient errors that resolve on retry.
        error_status = params.get("error_status", 500)
        methods_raw = params.get("methods")
        methods = (
            {str(method).upper() for method in methods_raw}
            if isinstance(methods_raw, list) and methods_raw
            else None
        )
        error_body = params.get("error_body")
        error_message = params.get("error_message", "Server Error")

        async def _fulfill_error(route: Any) -> None:
            if isinstance(error_body, (dict, list)):
                await route.fulfill(
                    status=error_status,
                    content_type="application/json",
                    body=json.dumps(error_body),
                )
                return
            await route.fulfill(
                status=error_status,
                body=str(error_body if error_body is not None else error_message),
            )

        if mode == "intermittent":
            probability = behavior.get("probability", 0.2)
            call_counter = {"n": 0}

            async def intermittent_error_handler(route):
                if methods is not None and route.request.method.upper() not in methods:
                    await route.continue_()
                    return
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    await _fulfill_error(route)
                else:
                    await route.continue_()

            await page.route(url_pattern, intermittent_error_handler)
        else:
            error_count = params.get("error_count", 2)
            call_counter = {"n": 0}

            async def error_handler(route):
                if methods is not None and route.request.method.upper() not in methods:
                    await route.continue_()
                    return
                call_counter["n"] += 1
                if call_counter["n"] <= error_count:
                    await _fulfill_error(route)
                else:
                    await route.continue_()

            await page.route(url_pattern, error_handler)

    elif action == "misleading_success":
        success_body = params.get("success_body", {"success": True})
        ms_methods = {str(m).upper() for m in params.get("methods", ["POST", "PUT"])}
        call_counter = {"n": 0}

        if mode == "intermittent":
            probability = behavior.get("probability", 0.3)

            async def ms_intermittent_handler(route):
                if route.request.method.upper() not in ms_methods:
                    await route.continue_()
                    return
                call_counter["n"] += 1
                if _seeded_should_fire(behavior_seed, call_counter["n"], probability):
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(success_body),
                    )
                else:
                    await route.continue_()

            await page.route(url_pattern, ms_intermittent_handler)
        else:
            fail_count = params.get("fail_count", 1)

            async def ms_handler(route):
                if route.request.method.upper() not in ms_methods:
                    await route.continue_()
                    return
                call_counter["n"] += 1
                if call_counter["n"] <= fail_count:
                    await route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(success_body),
                    )
                else:
                    await route.continue_()

            await page.route(url_pattern, ms_handler)

    elif action == "concurrent_modification":
        conflict_count = int(params.get("conflict_count", 1))
        cm_methods = {str(m).upper() for m in params.get("methods", ["PUT", "PATCH", "POST"])}
        conflict_message = params.get(
            "conflict_message",
            "This record was modified by another session. Reload and retry.",
        )
        snapshot = params.get("latest_snapshot")
        call_counter = {"n": 0}

        async def cm_handler(route):
            if route.request.method.upper() not in cm_methods:
                await route.continue_()
                return
            call_counter["n"] += 1
            if call_counter["n"] <= conflict_count:
                body: dict[str, Any] = {
                    "error": conflict_message,
                    "status": 409,
                    "retryable": True,
                }
                if snapshot is not None:
                    body["latest"] = snapshot
                await route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps(body),
                )
            else:
                await route.continue_()

        await page.route(url_pattern, cm_handler)

    elif action == "rate_limit":
        burst_limit = int(params.get("burst_limit", 3))
        retry_after = int(params.get("retry_after_seconds", 5))
        cooldown_calls = int(params.get("cooldown_calls", 3))
        rl_methods_raw = params.get("methods")
        rl_methods = (
            {str(m).upper() for m in rl_methods_raw} if rl_methods_raw else None
        )
        error_message = params.get(
            "error_message",
            "Rate limit exceeded. Please wait before retrying.",
        )
        state = {"n": 0, "cooldown_until": 0}

        async def rl_handler(route):
            if rl_methods is not None and route.request.method.upper() not in rl_methods:
                await route.continue_()
                return
            state["n"] += 1
            if state["n"] <= burst_limit:
                state["cooldown_until"] = state["n"] + cooldown_calls
                await route.continue_()
                return
            if state["n"] <= state["cooldown_until"]:
                await route.fulfill(
                    status=429,
                    content_type="application/json",
                    body=json.dumps(
                        {"error": error_message, "status": 429, "retryable": True}
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
                return
            await route.continue_()

        await page.route(url_pattern, rl_handler)

    elif action == "session_expiry":
        expire_after = int(params.get("expire_after_calls", 5))
        reauth_pattern = params.get("reauth_path")
        se_methods_raw = params.get("methods")
        se_methods = (
            {str(m).upper() for m in se_methods_raw} if se_methods_raw else None
        )
        error_message = params.get(
            "error_message", "Session expired. Please re-authenticate."
        )
        state = {"n": 0, "expired": False}

        # Pattern helper: rough glob → regex using Python's fnmatch on path only
        import re as _re
        def _matches(url: str, pattern: str | None) -> bool:
            if not pattern:
                return False
            clean = url.split("?")[0].split("#")[0]
            parts = _re.split(r"(\*\*|\*)", pattern)
            rx_parts: list[str] = []
            for part in parts:
                if part == "**":
                    rx_parts.append(".*")
                elif part == "*":
                    rx_parts.append("[^/]*")
                else:
                    rx_parts.append(_re.escape(part))
            rx = "".join(rx_parts)
            if pattern.startswith("**/"):
                return bool(_re.search(r"/" + rx[2:] + r"$", clean))
            return bool(_re.match("^" + rx + "$", clean))

        async def se_handler(route):
            url_now = route.request.url
            if reauth_pattern and _matches(url_now, reauth_pattern):
                state["expired"] = False
                await route.continue_()
                return
            if se_methods is not None and route.request.method.upper() not in se_methods:
                await route.continue_()
                return
            state["n"] += 1
            if state["n"] > expire_after:
                state["expired"] = True
            if state["expired"]:
                await route.fulfill(
                    status=401,
                    content_type="application/json",
                    body=json.dumps(
                        {"error": error_message, "status": 401, "retryable": True}
                    ),
                )
                return
            await route.continue_()

        await page.route(url_pattern, se_handler)
