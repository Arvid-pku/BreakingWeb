"""BrowserGym AbstractBrowserTask implementation for BreakingWeb.

Each Gmail task is an AbstractBrowserTask that:
  1. Starts the BreakingWeb FastAPI server
  2. Creates a session with seeded state (+ optional degradation)
  3. Navigates the Playwright page to the Gmail SPA
  4. Validates by calling the server-side evaluator
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Tuple

from .config import getenv

import playwright.sync_api
from browsergym.core.task import AbstractBrowserTask

from .runner import controller_headers

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    with urllib.request.urlopen(req) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text else {}


def _assert_server_matches_local_manifest(base_url: str, host: str, port: int) -> None:
    from .app import MANIFEST_FINGERPRINT

    try:
        health = _http_json(f"{base_url}/health")
    except Exception as exc:  # pragma: no cover - defensive guard for non-benchmark servers
        raise RuntimeError(
            f"Service already running on {host}:{port} did not return a valid BreakingWeb health response. "
            "Choose a free port or restart the benchmark server."
        ) from exc

    remote_fingerprint = health.get("manifest_fingerprint")
    if remote_fingerprint != MANIFEST_FINGERPRINT:
        raise RuntimeError(
            f"BreakingWeb server already running on {host}:{port} does not match the local benchmark manifest "
            f"({remote_fingerprint or 'missing'} != {MANIFEST_FINGERPRINT}). "
            "Choose a free port or restart the benchmark server."
        )


class BreakingWebTask(AbstractBrowserTask):
    """A single BreakingWeb task, compatible with BrowserGym's BrowserEnv."""

    @classmethod
    def get_task_id(cls):
        return "breakingweb"

    def __init__(
        self,
        seed: int,
        task_id: str,
        degradation: str | None = None,
        server_host: str = _DEFAULT_HOST,
        server_port: int = _DEFAULT_PORT,
        viewport: tuple[int, int] | None = None,
    ):
        super().__init__(seed)
        self._wab_seed = seed  # preserve the actual seed for session creation
        self.task_id = task_id
        self.degradation = degradation
        self.server_host = server_host
        self.server_port = server_port
        self._bench_url = f"http://{server_host}:{server_port}"
        self._server_proc = None
        self._session_id: str | None = None
        self._env_id: str | None = None
        self._instruction: str = ""
        self._degradation_config = None
        self._evaluated = False
        self._initial_chat_count = -1  # track initial chat messages to avoid false termination
        self._forwarded_chat_count = 0  # number of agent chat messages already pushed to state.chat

        # BrowserGym task properties — viewport is per-model when caller passes one
        # (Anthropic recommends 1024×768; OpenAI recommends 1600×900; Gemini/Qwen
        # are flexible at 1280×720). pixel_eval._viewport_for_model() picks per
        # provider/model.
        vw, vh = viewport if viewport else (1280, 720)
        self.viewport = {"width": vw, "height": vh}
        self.slow_mo = 0
        self.timeout = 10000

        # Load degradation config if provided
        if degradation:
            from .injector.config import DegradationConfig
            deg_path = Path(degradation)
            if not deg_path.exists():
                deg_path = Path(__file__).parent / degradation
            if not deg_path.exists():
                deg_path = Path(__file__).parent / "injector" / "variants" / degradation
            if deg_path.exists():
                self._degradation_config = DegradationConfig.from_yaml(deg_path)

    def _ensure_server(self) -> None:
        from .runner import ensure_controller_secret, start_server, wait_for_server
        if wait_for_server(self.server_host, self.server_port, timeout=2):
            if not getenv("BREAKINGWEB_CONTROLLER_SECRET"):
                raise RuntimeError(
                    "A BreakingWeb server is already running, but BREAKINGWEB_CONTROLLER_SECRET "
                    "is not set in this process. Export the same secret or use a free port."
                )
            _assert_server_matches_local_manifest(self._bench_url, self.server_host, self.server_port)
            return
        ensure_controller_secret()
        self._server_proc = start_server(self.server_host, self.server_port)
        if not wait_for_server(self.server_host, self.server_port):
            raise RuntimeError("BreakingWeb server failed to start")
        _assert_server_matches_local_manifest(self._bench_url, self.server_host, self.server_port)

    def setup(self, page: playwright.sync_api.Page) -> tuple[str, dict]:
        """Start server, create session, navigate page, apply degradations."""
        self._ensure_server()
        try:
            return self._setup_session(page)
        except Exception:
            # Clean up server process if we started it, since BrowserGym
            # only calls teardown() after a successful setup().
            self.teardown()
            raise

    def _setup_session(self, page: playwright.sync_api.Page) -> tuple[str, dict]:
        """Internal setup logic, separated so setup() can catch and clean up."""
        self._evaluated = False

        # Resolve task metadata
        from .tasks._registry import get_task
        task_def = get_task(self.task_id)
        self._env_id = task_def.env_id

        # Create session
        session_payload: dict[str, Any] = {
            "task_id": self.task_id,
            "seed": self._wab_seed,
        }

        # Deliver the full degradation config so the server can apply seed/server
        # injections and register network/client behavior for the live browser.
        if self._degradation_config:
            session_payload["degradation"] = {
                "variant_id": self._degradation_config.variant_id,
                "base_task_id": self._degradation_config.base_task_id,
                "target_primitive": self._degradation_config.target_primitive,
                "description": self._degradation_config.description,
                "injections": [
                    {"layer": inj.layer, "params": inj.params}
                    for inj in self._degradation_config.injections
                ],
            }

        created = _http_json(
            f"{self._bench_url}/api/env/{self._env_id}/session",
            method="POST",
            payload=session_payload,
        )
        self._session_id = created["session_id"]
        start_path = created.get("start_path", task_def.start_path or "/")
        self._instruction = created["instruction"]

        # Navigate to the Gmail SPA
        base_url = f"/env/{self._env_id}"
        session_url = (
            f"{self._bench_url}{base_url}{start_path}"
            f"?session={urllib.parse.quote(self._session_id)}&agent_mode=1"
        )
        page.goto(session_url)
        page.wait_for_load_state("networkidle")

        # BrowserGym seeds initial chat messages (greeting + goal).
        # We must ignore these when checking for agent-initiated termination.
        # Use a sentinel to distinguish "not yet set" from "set to 0".
        self._initial_chat_count = -1

        info: dict[str, Any] = {
            "task_id": self.task_id,
            "session_id": self._session_id,
            "env_id": self._env_id,
            "difficulty": task_def.difficulty,
            "primitives": task_def.primary_primitives,
        }
        if self._degradation_config:
            info["degradation"] = {
                "variant_id": self._degradation_config.variant_id,
                "target_primitive": self._degradation_config.target_primitive,
            }

        return self._instruction, info

    def validate(
        self, page: playwright.sync_api.Page, chat_messages: list[str]
    ) -> Tuple[float, bool, str, dict]:
        """Check if the agent finished (via send_msg_to_user) and evaluate."""
        # On the first call, snapshot how many chat messages already exist
        # (BrowserGym adds an initial greeting + goal before any agent action).
        # BrowserGym calls validate() AFTER processing the action, so on the
        # first call chat_messages may already include the agent's first message.
        # We snapshot only the non-assistant messages as the baseline.
        if self._initial_chat_count == -1:
            self._initial_chat_count = sum(
                1 for m in chat_messages if m.get("role") != "assistant" and m.get("role") != "infeasible"
            )

        # The agent is "done" when NEW chat messages appear beyond the initial set.
        # This happens when the agent calls send_msg_to_user() or report_infeasible().
        done = False
        new_messages = chat_messages[self._initial_chat_count:]
        for msg in new_messages:
            if msg.get("role") == "assistant" and not self._evaluated:
                done = True
                break
            if msg.get("role") == "infeasible":
                done = True
                break

        # Forward newly-seen agent chat messages to state.chat (best-effort).
        # BrowserGym stores the text under the "message" key for assistant and
        # infeasible entries; we normalize to the role/content schema expected
        # by the /chat endpoint. Failure here must never abort validate().
        if self._session_id and self._env_id:
            agent_messages = [
                m for m in new_messages
                if m.get("role") in ("assistant", "infeasible")
            ]
            unpushed = agent_messages[self._forwarded_chat_count:]
            for msg in unpushed:
                try:
                    _http_json(
                        f"{self._bench_url}/api/env/{self._env_id}"
                        f"/session/{urllib.parse.quote(self._session_id)}/chat",
                        method="POST",
                        payload={
                            "role": msg.get("role", "assistant"),
                            "content": msg.get("message", ""),
                        },
                        headers=controller_headers(),
                    )
                except Exception:
                    # Chat forwarding is best-effort; never block evaluation.
                    pass
                self._forwarded_chat_count += 1

        if not done:
            return 0.0, False, "", {}

        # Evaluate via server
        if not self._evaluated and self._session_id and self._env_id:
            self._evaluated = True
            try:
                try:
                    benchmark_state = page.evaluate("() => window.__benchmarkState || {}")
                except Exception:
                    benchmark_state = {}
                result = _http_json(
                    f"{self._bench_url}/api/env/{self._env_id}/evaluate",
                    method="POST",
                    payload={
                        "session_id": self._session_id,
                        "task_id": self.task_id,
                        "benchmark_state": benchmark_state,
                    },
                    headers=controller_headers(),
                )
                reward = float(result.get("score", result.get("final_score", 0.0)))
                return reward, True, "", {"evaluation": result}
            except Exception as e:
                logger.error("Evaluation failed: %s", e)
                return 0.0, True, "", {"evaluation_error": str(e)}

        return 0.0, True, "", {}

    def force_evaluate(self, page: playwright.sync_api.Page) -> dict:
        """Run the server-side evaluator on the current state, regardless of
        whether the agent has called ``send_msg_to_user``.

        WAB evaluators are state-based — agent's "done" declaration is only a
        BrowserGym signaling convention, not a precondition for scoring. After
        an episode ends (max_steps / timeout / termination), the harness should
        call this to capture the actual outcome. Otherwise pixel/coord agents
        that complete the task without declaring done will silently score 0.

        Idempotent against ``validate()`` — if validate already evaluated this
        session, the cached call is returned (the evaluator endpoint itself is
        also idempotent / pure-read against server state).
        """
        if not (self._session_id and self._env_id):
            return {}
        try:
            try:
                benchmark_state = page.evaluate("() => window.__benchmarkState || {}")
            except Exception:
                benchmark_state = {}
            result = _http_json(
                f"{self._bench_url}/api/env/{self._env_id}/evaluate",
                method="POST",
                payload={
                    "session_id": self._session_id,
                    "task_id": self.task_id,
                    "benchmark_state": benchmark_state,
                },
                headers=controller_headers(),
            )
            self._evaluated = True
            return result
        except Exception as e:
            logger.warning("force_evaluate failed: %s", e)
            return {"score": 0.0, "success": False, "reasoning": f"force_evaluate error: {e}"}

    def teardown(self) -> None:
        """Destroy session and stop server if we started it."""
        if self._session_id and self._env_id:
            try:
                _http_json(
                    f"{self._bench_url}/api/env/{self._env_id}/session/{urllib.parse.quote(self._session_id)}",
                    method="DELETE",
                )
            except Exception:
                pass
            self._session_id = None

        if self._server_proc:
            self._server_proc.terminate()
            try:
                self._server_proc.wait(timeout=5)
            except Exception:
                self._server_proc.kill()
            self._server_proc = None
