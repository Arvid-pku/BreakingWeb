"""
BreakingWeb runtime utilities.

This module now contains only shared helpers for starting the benchmark
server, fetching the manifest, and printing aggregate result summaries for
advanced environment tasks.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .config import getenv
from .backend.security import CONTROLLER_SECRET_ENV, CONTROLLER_SECRET_HEADER


def ensure_controller_secret() -> str:
    """Ensure a controller secret exists for local harness-managed servers."""
    secret = getenv(CONTROLLER_SECRET_ENV)
    if isinstance(secret, str) and secret:
        return secret
    secret = secrets.token_urlsafe(32)
    os.environ[CONTROLLER_SECRET_ENV] = secret
    return secret


def controller_headers() -> dict[str, str]:
    """Return controller auth headers when this process has a shared secret."""
    secret = getenv(CONTROLLER_SECRET_ENV)
    if not isinstance(secret, str) or not secret:
        return {}
    return {CONTROLLER_SECRET_HEADER: secret}


def start_server(host: str, port: int) -> subprocess.Popen:
    """Start the FastAPI server in a subprocess."""
    env = os.environ.copy()
    env[CONTROLLER_SECRET_ENV] = ensure_controller_secret()
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "breakingweb.app:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_for_server(host: str, port: int, timeout: int = 15) -> bool:
    """Wait until the server health endpoint is responding."""
    url = f"http://{host}:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False


def get_manifest(base_url: str) -> dict:
    """Fetch the public manifest from the running server."""
    with urllib.request.urlopen(f"{base_url}/manifest") as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_summary(results: list[dict]) -> None:
    """Print an overall summary for environment-task evaluation results."""
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"]["success"])
    avg_score = sum(r["evaluation"]["score"] for r in results) / total if total else 0

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {passed}/{total} tasks passed  |  avg score: {avg_score:+.2f}")
    print(f"{'=' * 60}")

    prim_scores: dict[str, list[float]] = {}
    for result in results:
        for primitive in result.get("primitives", []):
            prim_scores.setdefault(primitive, []).append(result["evaluation"]["score"])

    if prim_scores:
        print("\nPrimitive Scores:")
        for primitive in sorted(prim_scores):
            scores = prim_scores[primitive]
            avg = sum(scores) / len(scores)
            print(f"  {primitive:30s}  avg={avg:+.2f}  (n={len(scores)})")
