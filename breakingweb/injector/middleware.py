"""Server-side network degradation middleware.

Applies network-layer degradation effects (delays, errors, silent failures)
on the server side so they work for BOTH Playwright agents AND human browsers.

When a session has network degradations configured, this middleware intercepts
matching API requests and applies the effects before the real handler runs.

Supported actions (used by `params.action` in a variant's network injection):
    delay               — sleep before forwarding (modes: once, intermittent,
                          progressive, tail_latency, correlated_window,
                          write_only_slow)
    error_then_success  — return N HTTP errors then let the request through
    silent_fail         — fake a 200 response without forwarding to the handler
    misleading_success  — like silent_fail, but the body advertises success
                          ("toast: Saved.") so the agent must verify the
                          backing state to detect the lie
    stale_data          — return cached or pre-canned body for first N GETs
    concurrent_modification — return 409 with an optional latest snapshot
    rate_limit          — allow burst_limit calls then return 429 for
                          cooldown_calls more
    session_expiry      — after expire_after_calls calls return 401 until
                          a request to reauth_path clears it
    slow_responses / stale_cache / modify_response — legacy Booking-era
                          shapes kept for back-compat. Prefer the modern
                          equivalents above for new variants.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# Per-session stores
_SESSION_NETWORK: dict[str, list[dict]] = {}   # session_id → network injections
_SESSION_CLIENT: dict[str, list[dict]] = {}    # session_id → client injections
_CALL_COUNTERS: dict[str, dict[str, int]] = {} # session_id → per-pattern counters
_EXPIRED_SESSIONS: dict[str, set[int]] = {}    # session_id → expired inj indices
_RATE_LIMITED: dict[str, dict[int, float]] = {}  # session_id → {inj_idx: cooldown_until_call}
_STALE_CACHE: dict[str, dict[str, tuple[float, int, Any]]] = {}
_STALE_DATA: dict[str, dict[str, tuple[int, Any]]] = {}

_REQUEST_TIME_LEGACY_ACTIONS = {"slow_responses", "stale_cache", "modify_response"}
_BENCHMARK_API_PREFIXES = ("/api/control", "/api/human")
_BENCHMARK_ENV_ENDPOINTS = {"degradation", "evaluate", "session", "trajectory"}


def register_session_degradation(session_id: str, injections: list[dict]) -> None:
    """Store degradation config for a session (network + client)."""
    unregister_session_degradation(session_id)
    network = [
        inj for inj in injections
        if inj.get("layer") == "network"
        or (inj.get("params", {}).get("action") in _REQUEST_TIME_LEGACY_ACTIONS)
    ]
    client = [inj for inj in injections if inj.get("layer") == "client"]
    if network:
        _SESSION_NETWORK[session_id] = network
        _CALL_COUNTERS[session_id] = {}
    if client:
        _SESSION_CLIENT[session_id] = client
    if network or client:
        logger.info(
            "Registered %d network + %d client degradation(s) for session %s",
            len(network), len(client), session_id,
        )


def unregister_session_degradation(session_id: str) -> None:
    """Remove degradation config when session is destroyed."""
    _SESSION_NETWORK.pop(session_id, None)
    _SESSION_CLIENT.pop(session_id, None)
    _CALL_COUNTERS.pop(session_id, None)
    _EXPIRED_SESSIONS.pop(session_id, None)
    _RATE_LIMITED.pop(session_id, None)
    _STALE_CACHE.pop(session_id, None)
    _STALE_DATA.pop(session_id, None)


def clear_all_degradations() -> None:
    """Reset all degradation state. Useful for test teardown and server restart."""
    _SESSION_NETWORK.clear()
    _SESSION_CLIENT.clear()
    _CALL_COUNTERS.clear()
    _EXPIRED_SESSIONS.clear()
    _RATE_LIMITED.clear()


def get_client_injections(session_id: str) -> list[dict]:
    """Return client injections for a session (used by the JS endpoint)."""
    return _SESSION_CLIENT.get(session_id, [])


def _seeded_should_fire(seed: int, call_index: int, probability: float) -> bool:
    """Deterministic coin flip using md5 hash."""
    h = hashlib.md5(f"{seed}:{call_index}".encode()).hexdigest()
    return (int(h[:8], 16) / 0x100000000) < probability


def _glob_to_regex(pattern: str) -> str:
    """Convert a glob pattern to regex, escaping literal characters."""
    parts = re.split(r'(\*\*|\*)', pattern)
    result = []
    for part in parts:
        if part == '**':
            result.append('.*')
        elif part == '*':
            result.append('[^/]*')
        else:
            result.append(re.escape(part))
    return ''.join(result)


_REQ_PLACEHOLDER = re.compile(r"\{request\.([a-zA-Z_][a-zA-Z0-9_.]*)\}")


def _resolve_request_path(body: Any, path: str) -> Any:
    """Walk a dot-delimited path through a parsed JSON body. Returns None if any
    segment is missing. Lists are addressable by integer index segment."""
    cur = body
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


def _render_request_template(value: Any, request_body: Any) -> Any:
    """Recursively substitute ``{request.<path>}`` placeholders in a JSON-serializable
    value using fields from ``request_body``.

    - Dict / list values are walked recursively.
    - Whole-string placeholders (``"{request.quantity}"``) preserve the source's type
      (so an int request field becomes an int in the rendered body).
    - Inline placeholders (``"cart_{request.product_id}"``) stringify each resolution.
    - Unresolvable paths render as ``null`` for whole-string placeholders and empty
      string for inline ones — keeping raw ``{request.X}`` tokens would leak into
      user-visible UI when a variant echoes the client request back as a fake success.
    - When ``request_body`` is None or not a mapping, the value is returned unchanged.
    """
    if request_body is None or not isinstance(request_body, (dict, list)):
        return value
    if isinstance(value, dict):
        return {k: _render_request_template(v, request_body) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_request_template(item, request_body) for item in value]
    if not isinstance(value, str):
        return value
    matches = list(_REQ_PLACEHOLDER.finditer(value))
    if not matches:
        return value
    if len(matches) == 1 and matches[0].group(0) == value:
        # Whole-string placeholder → preserve resolved type, or None if unresolved.
        return _resolve_request_path(request_body, matches[0].group(1))
    out: list[str] = []
    cursor = 0
    for m in matches:
        out.append(value[cursor:m.start()])
        resolved = _resolve_request_path(request_body, m.group(1))
        out.append("" if resolved is None else str(resolved))
        cursor = m.end()
    out.append(value[cursor:])
    return "".join(out)


def _url_matches_pattern(url: str, pattern: str) -> bool:
    """Check if URL matches a glob-like pattern (** = any path).

    For ``**/`` prefixed patterns, anchors the suffix to a path boundary
    so ``**/emails`` won't accidentally match ``/emails/e001/star``.
    Query strings and fragments are stripped before matching.
    """
    # Strip query string and fragment for matching
    clean = url.split("?")[0].split("#")[0]
    if pattern.startswith("**/"):
        suffix = pattern[3:]
        regex = _glob_to_regex(suffix)
        # Anchor: must appear after a '/' and reach end-of-path
        return bool(re.search(r"/" + regex + r"$", clean))
    regex = "^" + _glob_to_regex(pattern) + "$"
    return bool(re.match(regex, clean))


def _legacy_endpoint_match(url: str, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Return the matching legacy endpoint spec for Booking-era variants."""
    clean = url.split("?")[0].split("#")[0]
    for endpoint in params.get("endpoints", []) or []:
        wanted_method = endpoint.get("method")
        if wanted_method and method != wanted_method:
            continue
        pattern = str(endpoint.get("path_pattern", ".*"))
        try:
            if re.search(pattern, clean):
                return endpoint
        except re.error:
            if pattern in clean:
                return endpoint
    return None


def _get_counter(session_id: str, key: str) -> int:
    """Increment and return per-session counter."""
    counters = _CALL_COUNTERS.setdefault(session_id, {})
    counters[key] = counters.get(key, 0) + 1
    return counters[key]


async def _json_response_from_downstream(response: Response) -> tuple[Response, Any | None]:
    """Read a JSON downstream response and return a reusable clone."""
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
        chunks.append(chunk)
    body = b"".join(chunks)
    try:
        content = json.loads(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response(
            content=body,
            status_code=response.status_code,
            headers={
                k: v for k, v in response.headers.items()
                if k.lower() != "content-length"
            },
        ), None
    headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in {"content-length", "content-type"}
    }
    clone: Response = JSONResponse(
        status_code=response.status_code,
        content=content,
        headers=headers or None,
    )
    return clone, content


def _apply_response_modifications(content: Any, modifications: dict[str, Any]) -> Any:
    """Apply small, deterministic response tweaks used by legacy variants."""
    if not isinstance(content, dict):
        return content
    out = dict(content)
    page_size = modifications.get("page_size_override")
    if page_size is not None and isinstance(out.get("results"), list):
        try:
            page_size_int = max(int(page_size), 1)
        except (TypeError, ValueError):
            page_size_int = 5
        out["results"] = out["results"][:page_size_int]
        out["page_size"] = page_size_int
        total = int(out.get("total", len(out["results"])) or 0)
        out["total_pages"] = max(1, (total + page_size_int - 1) // page_size_int)
    return out


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _normalize_progressive_stages(
    stages: list[dict[str, Any]],
    default_delay_ms: int,
) -> list[dict[str, int]]:
    """Normalize legacy stage syntaxes into ``after_call`` thresholds.

    ``after_call`` counts completed matching calls before a stage begins:
    ``after_call: 0`` applies on call 1, ``after_call: 3`` applies on call 4.
    """
    if not stages:
        return [{"after_call": 0, "delay_ms": _coerce_non_negative_int(default_delay_ms)}]

    if any("requests" in stage for stage in stages):
        normalized: list[dict[str, int]] = []
        after_call = 0
        for stage in stages:
            normalized.append({
                "after_call": after_call,
                "delay_ms": _coerce_non_negative_int(
                    stage.get("delay_ms"),
                    _coerce_non_negative_int(default_delay_ms),
                ),
            })
            after_call += _coerce_non_negative_int(stage.get("requests"), 0)
        return normalized

    if any("until_count" in stage for stage in stages):
        normalized = []
        after_call = 0
        for stage in stages:
            normalized.append({
                "after_call": after_call,
                "delay_ms": _coerce_non_negative_int(
                    stage.get("delay_ms"),
                    _coerce_non_negative_int(default_delay_ms),
                ),
            })
            if "until_count" in stage:
                after_call = _coerce_non_negative_int(stage.get("until_count"), after_call)
        return normalized

    if any("call_number" in stage for stage in stages):
        normalized = []
        for stage in stages:
            call_number = max(_coerce_non_negative_int(stage.get("call_number"), 1), 1)
            normalized.append({
                "after_call": call_number - 1,
                "delay_ms": _coerce_non_negative_int(
                    stage.get("delay_ms"),
                    _coerce_non_negative_int(default_delay_ms),
                ),
            })
        return sorted(normalized, key=lambda s: s["after_call"])

    normalized = [
        {
            "after_call": _coerce_non_negative_int(stage.get("after_call"), 0),
            "delay_ms": _coerce_non_negative_int(
                stage.get("delay_ms"),
                _coerce_non_negative_int(default_delay_ms),
            ),
        }
        for stage in stages
    ]
    return sorted(normalized, key=lambda s: s["after_call"])


def _progressive_delay_ms(
    call_num: int,
    stages: list[dict[str, Any]],
    default_delay_ms: int,
) -> int:
    """Return the active progressive delay for the current 1-indexed call."""
    current_delay = 0
    for stage in _normalize_progressive_stages(stages, default_delay_ms):
        if call_num > stage.get("after_call", 0):
            current_delay = stage.get("delay_ms", 0)
    return current_delay


def _seeded_quantile(seed: int, call_index: int) -> float:
    """Return a deterministic pseudo-uniform [0, 1) draw for (seed, call_index)."""
    h = hashlib.md5(f"{seed}:q:{call_index}".encode()).hexdigest()
    return int(h[:8], 16) / 0x100000000


def _tail_latency_ms(
    seed: int,
    call_index: int,
    p50_ms: int,
    p95_ms: int,
    p99_ms: int,
) -> int:
    """Sample a delay from a piecewise distribution anchored at (p50, p95, p99).

    Quantile q in [0, 1) maps linearly between (0, 0), (0.5, p50), (0.95, p95),
    (0.99, p99), (1.0, p99 * 1.5). Produces a right-skewed tail that mirrors
    real-world HTTP latency without any floating-point randomness.
    """
    q = _seeded_quantile(seed, call_index)
    anchors = [
        (0.0, 0),
        (0.5, p50_ms),
        (0.95, p95_ms),
        (0.99, p99_ms),
        (1.0, int(p99_ms * 1.5)),
    ]
    for i in range(1, len(anchors)):
        q0, v0 = anchors[i - 1]
        q1, v1 = anchors[i]
        if q < q1:
            span = q1 - q0 or 1e-9
            frac = (q - q0) / span
            return int(v0 + (v1 - v0) * frac)
    return int(p99_ms * 1.5)


def _in_correlated_window(call_num: int, start: int, duration: int) -> bool:
    """Is the 1-indexed call inside the slow window?"""
    if duration <= 0:
        return False
    return start < call_num <= start + duration


def _method_matches(method: str, allowed: Any) -> bool:
    """True if method matches any entry in ``allowed`` (or allowed is empty)."""
    if not allowed:
        return True
    return method.upper() in {str(m).upper() for m in allowed}


def _extract_session_from_referer(referer: str) -> str | None:
    """Extract session ID from the Referer header.

    The SPA page URL looks like: http://host/env/gmail/inbox?session=xxx
    All API calls from that page include this as the Referer.
    """
    if not referer:
        return None
    match = re.search(r'[?&]session=([^&]+)', referer)
    return match.group(1) if match else None


def _extract_session_from_cookie(cookies: str) -> str | None:
    """Extract session ID from the wab_session cookie."""
    if not cookies:
        return None
    for part in cookies.split(";"):
        part = part.strip()
        if part.startswith("wab_session="):
            return part[len("wab_session="):]
    return None


def _is_benchmark_control_plane_path(path: str) -> bool:
    """Return true for benchmark instrumentation APIs that must not be degraded."""
    if path in {"/manifest", "/health"}:
        return True
    if path.startswith(_BENCHMARK_API_PREFIXES):
        return True

    parts = [part for part in path.split("/") if part]
    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "env":
        return parts[3] in _BENCHMARK_ENV_ENDPOINTS
    return False


class DegradationMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that applies network degradation effects server-side.

    Session extraction strategy (without reading request body):
      1. Query param: ``?session_id=xxx`` or ``?session=xxx``
      2. Referer header: SPA page URL contains ``?session=xxx``
      3. Cookie: ``wab_session=xxx`` (set by session-create response)
      4. Brute-force: if only ONE session has degradation, use it
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _is_benchmark_control_plane_path(request.url.path):
            return await call_next(request)

        session_id = (
            request.query_params.get("session_id")
            or request.query_params.get("session")
            or _extract_session_from_referer(request.headers.get("referer", ""))
            or _extract_session_from_cookie(request.headers.get("cookie", ""))
        )

        # For POST/PUT/PATCH, parse the JSON body once so we can both extract a
        # missing session_id and feed request-body templates in silent_fail /
        # misleading_success response_body. Starlette caches the body bytes so
        # the downstream handler still receives them intact.
        request_body: Any = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    request_body = json.loads(body_bytes)
            except Exception:
                request_body = None
            if not session_id and isinstance(request_body, dict):
                session_id = request_body.get("session_id")

        if not session_id or session_id not in _SESSION_NETWORK:
            return await call_next(request)

        # Check each network injection
        url = str(request.url)
        method = request.method
        injections = _SESSION_NETWORK[session_id]

        # Pre-pass: clear session_expiry on reauth path matches.
        for inj_idx, inj in enumerate(injections):
            params = inj.get("params", {})
            if params.get("action") != "session_expiry":
                continue
            reauth = params.get("reauth_path")
            if reauth and _url_matches_pattern(url, reauth):
                expired = _EXPIRED_SESSIONS.get(session_id)
                if expired is not None:
                    expired.discard(inj_idx)

        for inj_idx, inj in enumerate(injections):
            params = inj.get("params", {})
            action = params.get("action", "")
            url_pattern = params.get("url_pattern", "**/*")
            legacy_endpoint = None

            if action in _REQUEST_TIME_LEGACY_ACTIONS:
                legacy_endpoint = _legacy_endpoint_match(url, method, params)
                if legacy_endpoint is None:
                    continue
            elif not _url_matches_pattern(url, url_pattern):
                continue

            # For method-filtered actions, check the method BEFORE
            # incrementing the counter so that non-matching methods
            # (e.g. a GET to load a page) don't consume the fail budget.
            if action == "silent_fail":
                methods = set(params.get("methods", ["POST", "PUT"]))
                if method not in methods:
                    continue
            elif action == "stale_data":
                if method not in ("GET",):
                    continue
            elif action == "error_then_success":
                ets_methods = params.get("methods")
                if ets_methods and method not in set(ets_methods):
                    continue
            elif action == "delay":
                delay_methods = params.get("methods")
                if delay_methods and method not in set(delay_methods):
                    continue
            elif action == "misleading_success":
                ms_methods = set(params.get("methods", ["POST", "PUT"]))
                if method not in ms_methods:
                    continue
            elif action == "concurrent_modification":
                cm_methods = set(params.get("methods", ["PUT", "PATCH", "POST"]))
                if method not in cm_methods:
                    continue
            elif action == "rate_limit":
                rl_methods = params.get("methods")
                if rl_methods and method not in set(rl_methods):
                    continue
            elif action == "session_expiry":
                se_methods = params.get("methods")
                if se_methods and method not in set(se_methods):
                    continue
            elif action in _REQUEST_TIME_LEGACY_ACTIONS:
                pass

            behavior = params.get("behavior", {})
            mode = behavior.get("mode", "once")
            beh_seed = behavior.get("seed", 42)
            counter_key = f"{action}:{url_pattern}:{inj_idx}"
            call_num = _get_counter(session_id, counter_key)

            if action == "delay":
                delay_ms = params.get("delay_ms", 3000)
                should_delay = False

                if mode == "progressive":
                    current_delay = _progressive_delay_ms(
                        call_num,
                        behavior.get("stages", []),
                        delay_ms,
                    )
                    if current_delay > 0:
                        delay_ms = current_delay
                        should_delay = True
                elif mode == "intermittent":
                    prob = behavior.get("probability", 0.3)
                    should_delay = _seeded_should_fire(beh_seed, call_num, prob)
                elif mode == "tail_latency":
                    sampled = _tail_latency_ms(
                        beh_seed,
                        call_num,
                        int(behavior.get("p50_ms", 100)),
                        int(behavior.get("p95_ms", 2000)),
                        int(behavior.get("p99_ms", 5000)),
                    )
                    if sampled > 0:
                        delay_ms = sampled
                        should_delay = True
                elif mode == "correlated_window":
                    start = int(behavior.get("window_start_call", 3))
                    duration = int(behavior.get("window_duration_calls", 4))
                    if _in_correlated_window(call_num, start, duration):
                        delay_ms = int(behavior.get("slow_ms", delay_ms))
                        should_delay = True
                elif mode == "write_only_slow":
                    # Already method-filtered above; always apply the delay.
                    should_delay = True
                else:  # once — always delay
                    should_delay = True

                if should_delay:
                    await asyncio.sleep(delay_ms / 1000)

            elif action == "slow_responses":
                endpoint_delay = int((legacy_endpoint or {}).get("delay_ms", params.get("delay_ms", 0)) or 0)
                if endpoint_delay > 0:
                    await asyncio.sleep(endpoint_delay / 1000)

            elif action == "error_then_success":
                error_status = params.get("error_status", 503)
                should_error = False

                if mode == "intermittent":
                    prob = behavior.get("probability", 0.2)
                    should_error = _seeded_should_fire(beh_seed, call_num, prob)
                else:
                    error_count = params.get("error_count", 2)
                    should_error = call_num <= error_count

                if should_error:
                    error_message = params.get("error_message")
                    retry_after = params.get("retry_after")
                    if not error_message:
                        error_messages = {
                            503: "Service temporarily unavailable. The server is under heavy load. Please retry your request.",
                            429: "Rate limit exceeded. Please wait before retrying.",
                            500: "Internal server error. An unexpected condition was encountered. Please retry.",
                            502: "Bad gateway. The upstream service did not respond. Please retry.",
                        }
                        error_message = error_messages.get(error_status, f"Request failed with status {error_status}. Please retry.")
                    headers: dict[str, str] = {}
                    if error_status == 429:
                        headers["Retry-After"] = str(retry_after or 30)
                    elif retry_after:
                        headers["Retry-After"] = str(retry_after)
                    return JSONResponse(
                        status_code=error_status,
                        content={
                            "error": error_message,
                            "status": error_status,
                            "retryable": True,
                        },
                        headers=headers or None,
                    )

            elif action == "silent_fail":
                fake_body = params.get("response_body", {"success": True})
                should_fail = False

                if mode == "intermittent":
                    prob = behavior.get("probability", 0.3)
                    should_fail = _seeded_should_fire(beh_seed, call_num, prob)
                else:
                    fail_count = params.get("fail_count", 1)
                    should_fail = call_num <= fail_count

                if should_fail:
                    return JSONResponse(
                        status_code=200,
                        content=_render_request_template(fake_body, request_body),
                    )

            elif action == "stale_data":
                stale_body = params.get("stale_body")
                should_stale = False

                if mode == "intermittent":
                    prob = behavior.get("probability", 0.3)
                    should_stale = _seeded_should_fire(beh_seed, call_num, prob)
                else:
                    stale_count = params.get("stale_count", 1)
                    should_stale = call_num <= stale_count

                if should_stale:
                    if stale_body is None:
                        stale_key = f"{inj_idx}:{url_pattern}"
                        cached_stale = _STALE_DATA.setdefault(session_id, {}).get(stale_key)
                        if cached_stale:
                            status_code, content = cached_stale
                            return JSONResponse(status_code=status_code, content=content)
                        response = await call_next(request)
                        cloned = await _json_response_from_downstream(response)
                        clone, content = cloned
                        if content is None:
                            return clone
                        _STALE_DATA.setdefault(session_id, {})[stale_key] = (clone.status_code, content)
                        return clone
                    return JSONResponse(
                        status_code=200,
                        content=stale_body,
                    )

            elif action == "stale_cache":
                duration_ms = int((legacy_endpoint or {}).get("stale_duration_ms", params.get("stale_duration_ms", 5000)) or 5000)
                cache_key = f"{inj_idx}:{(legacy_endpoint or {}).get('path_pattern', url_pattern)}"
                cached = _STALE_CACHE.setdefault(session_id, {}).get(cache_key)
                now = time.time()
                if cached and cached[0] > now:
                    _, status_code, content = cached
                    return JSONResponse(status_code=status_code, content=content)
                response = await call_next(request)
                cloned = await _json_response_from_downstream(response)
                clone, content = cloned
                if content is None:
                    return clone
                _STALE_CACHE.setdefault(session_id, {})[cache_key] = (
                    now + duration_ms / 1000,
                    clone.status_code,
                    content,
                )
                return clone

            elif action == "modify_response":
                response = await call_next(request)
                cloned = await _json_response_from_downstream(response)
                clone, content = cloned
                if content is None:
                    return clone
                modified = _apply_response_modifications(
                    content,
                    (legacy_endpoint or {}).get("modifications", params.get("modifications", {})) or {},
                )
                return JSONResponse(status_code=clone.status_code, content=modified)

            elif action == "misleading_success":
                # Server returns a louder lie: 200 with a body that claims the
                # write succeeded ("toast: Email sent") but the write is
                # skipped. Inverse of silent_fail: crueler because the toast
                # actively misleads.
                success_body = params.get(
                    "success_body",
                    {"success": True, "message": "Saved."},
                )
                should_mislead = False
                if mode == "intermittent":
                    prob = behavior.get("probability", 0.3)
                    should_mislead = _seeded_should_fire(beh_seed, call_num, prob)
                else:
                    fail_count = params.get("fail_count", 1)
                    should_mislead = call_num <= fail_count
                if should_mislead:
                    return JSONResponse(
                        status_code=200,
                        content=_render_request_template(success_body, request_body),
                    )

            elif action == "concurrent_modification":
                conflict_count = params.get("conflict_count", 1)
                if call_num <= conflict_count:
                    body: dict[str, Any] = {
                        "error": params.get(
                            "conflict_message",
                            "This record was modified by another session. Reload and retry.",
                        ),
                        "status": 409,
                        "retryable": True,
                    }
                    snapshot = params.get("latest_snapshot")
                    if snapshot is not None:
                        body["latest"] = snapshot
                    return JSONResponse(status_code=409, content=body)

            elif action == "rate_limit":
                burst_limit = int(params.get("burst_limit", 3))
                retry_after = int(params.get("retry_after_seconds", 5))
                cooldown_calls = int(params.get("cooldown_calls", 3))
                rl = _RATE_LIMITED.setdefault(session_id, {})
                cooldown_until_call = rl.get(inj_idx, 0)
                if call_num <= burst_limit:
                    # Let first N calls pass; record when the window closes.
                    rl[inj_idx] = call_num + cooldown_calls
                elif call_num <= cooldown_until_call:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": params.get(
                                "error_message",
                                "Rate limit exceeded. Please wait before retrying.",
                            ),
                            "status": 429,
                            "retryable": True,
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
                # If we're past the cooldown, allow through (silently reset).

            elif action == "session_expiry":
                expire_after = int(params.get("expire_after_calls", 5))
                expired = _EXPIRED_SESSIONS.setdefault(session_id, set())
                if call_num > expire_after:
                    expired.add(inj_idx)
                if inj_idx in expired:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": params.get(
                                "error_message",
                                "Session expired. Please re-authenticate.",
                            ),
                            "status": 401,
                            "retryable": True,
                        },
                    )

        return await call_next(request)
