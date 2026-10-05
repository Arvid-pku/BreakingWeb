"""Pixel-mode (vision-only) BreakingWeb harness.

Drives WAB tasks through a BrowserGym env using a coord-action VLM agent
(`PixelLLMAgent`). Exposes an `async run_episode()` with the same shape as
`stock_browseruse_eval.run_episode` so the existing `scripts/pixel_run_picks.py`
runner can dispatch picks to it.

Compared to `agent_eval.py` (text-only, BID actions, AXTree input):
  - action_set:  ["coord", "chat", "tab", "nav", "infeas"]
  - obs filter:  uses obs["screenshot"] only; ignores axtree_txt / dom_object
  - normalize_coordinates: per-model mapping (Gemini/Qwen=True, GPT/Claude=False)

Usage (single task, programmatic):

    import asyncio
    from breakingweb.pixel_eval import run_episode

    result = asyncio.run(run_episode(
        task_id="booking_save_property",
        variant_filename="booking_save_property__property_twin.yaml",
        model="gemini-3-flash-preview",
        provider="gemini",
        backend_port=8080,
        max_steps=20,
        timeout_seconds=300,
    ))
    print(result["evaluation"])
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent

# Load .env so GEMINI_API_KEY / OPENROUTER_API_KEY / AWS_BEDROCK_API_KEY surface.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BASE_DIR / ".env", override=False)
except Exception:
    pass


_DEFAULT_MAX_STEPS = 60
# Doubled from the original 600s — pixel mode also runs Bedrock-routed Claude
# at ~40s/step, which clipped opus to ~14 effective steps in PrimBench v2.
# Faster providers finish well under this and don't pay any cost.
_DEFAULT_TIMEOUT = 1200


# =============================================================================
# Provider-/model-aware coordinate-mode mapping
# =============================================================================

def _normalize_for_model(provider: str, model: str) -> bool:
    """Whether this VLM emits 0-1000 normalized coords (True) or raw pixels (False).

    Mirrors ComponentBench/InterfaceGym's table:
      - GPT-5.4* / GPT-4o*           → raw pixels (False)
      - Claude (Opus / Sonnet / Haiku) → XGA-scaled pixels (False)
      - Gemini 3 Flash / Qwen3-VL    → 0-1000 normalized (True)
    """
    p = (provider or "").lower()
    m = (model or "").lower()
    if "qwen" in m:
        return True
    if "gemini" in m or p in ("gemini", "google"):
        return True
    if "gpt" in m or p == "openai":
        return False
    if "claude" in m or "anthropic" in p or p == "bedrock":
        return False
    # Default to normalized (matches InterfaceGym's `normalize_coordinates: True`).
    return True


def _viewport_for_model(provider: str, model: str) -> tuple[int, int]:
    """Recommended viewport (w, h) per model family.

    Each VLM has a sweet-spot resolution from its training. Running outside
    that range reduces grounding quality (Anthropic downsamples >XGA, OpenAI's
    CUA was trained at 1600×900). PrimBench v2 used 1280×720 for all models;
    follow-up sweeps (commit f2*) can use per-model viewports for fairness.

    - Claude (Anthropic computer-use docs):     1024 × 768
    - GPT-5.x / GPT-4o (OpenAI CUA docs):       1600 × 900
    - Gemini / Qwen / default:                  1280 × 720
    """
    p = (provider or "").lower()
    m = (model or "").lower()
    # Order matters: qwen runs on Bedrock too — match it BEFORE the
    # "p == 'bedrock'" branch claims it.
    if "qwen" in m:
        return (1280, 720)
    if "claude" in m or "anthropic" in p or p == "bedrock":
        return (1024, 768)
    if "gpt" in m or p == "openai":
        return (1600, 900)
    return (1280, 720)


# =============================================================================
# Variant path resolution
# =============================================================================

def _resolve_variant_path(variant_filename: str | None) -> str | None:
    if not variant_filename:
        return None
    candidates = [
        Path(variant_filename),
        BASE_DIR / variant_filename,
        BASE_DIR / "injector" / "variants" / variant_filename,
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    raise FileNotFoundError(f"Variant not found: {variant_filename}")


# =============================================================================
# Episode runner
# =============================================================================

def _run_episode_sync(
    task_id: str,
    *,
    model: str,
    provider: str,
    variant_filename: str | None,
    server_host: str,
    backend_port: int,
    max_steps: int,
    timeout_seconds: int,
    headless: bool,
    verbose: bool,
    trajectory_dir: Path | None,
) -> dict[str, Any]:
    """Synchronous core. The async wrapper offloads via asyncio.to_thread."""
    from .agent_eval import run_episode as run_browsergym_episode
    from .browsergym_env import make_env
    from .pixel_agent import PixelLLMAgent

    variant_path = _resolve_variant_path(variant_filename)
    normalize = _normalize_for_model(provider, model)
    viewport = _viewport_for_model(provider, model)

    env = make_env(
        task_id=task_id,
        degradation=variant_path,
        headless=headless,
        server_host=server_host,
        server_port=backend_port,
        # Pixel-mode action subsets: include navigation + chat + infeasible reporting.
        action_subsets=["coord", "chat", "tab", "nav", "infeas"],
        viewport=viewport,
    )

    agent = PixelLLMAgent(
        model=model,
        provider=provider,
        normalize_coordinates=normalize,
    )

    start = time.time()
    completed = False
    error: str | None = None
    episode: dict[str, Any] = {
        "task_id": task_id,
        "goal": "",
        "steps": 0,
        "elapsed_seconds": 0.0,
        "completed": False,
        "trajectory": [],
        "evaluation": {"score": 0.0, "success": False, "reasoning": "not run"},
        "messages": [],
        "task_info": {},
    }

    screenshots_dir = (
        Path(trajectory_dir) / "screenshots" if trajectory_dir is not None else None
    )

    try:
        episode = run_browsergym_episode(
            env,
            agent,
            max_steps=max_steps,
            timeout_seconds=timeout_seconds,
            verbose=verbose,
            screenshots_dir=screenshots_dir,
        )
        completed = episode.get("completed", False)
    except Exception as exc:
        logger.exception("pixel_eval run_episode failed for %s: %s", task_id, exc)
        error = f"{type(exc).__name__}: {exc}"
        episode["evaluation"] = {
            "score": 0.0,
            "success": False,
            "reasoning": f"harness error: {error}",
        }
    finally:
        try:
            env.close()
        except Exception as close_exc:
            logger.warning("env.close() failed for %s: %s", task_id, close_exc)

    elapsed = round(time.time() - start, 1)

    # Shape: same as stock_browseruse_eval.run_episode result
    result: dict[str, Any] = {
        "task_id": task_id,
        "session_id": episode.get("task_info", {}).get("session_id", ""),
        "goal": episode.get("goal", ""),
        "evaluation": episode.get("evaluation", {"score": 0.0, "success": False}),
        "agent": {
            "model": model,
            "provider": provider,
            "harness": "pixel-vlm",
            "normalize_coordinates": normalize,
            "viewport": list(viewport),
            "elapsed_seconds": elapsed,
            "completed": completed,
            "steps": episode.get("steps", 0),
            "trajectory": episode.get("trajectory", []),
        },
        "variant_filename": variant_filename,
    }
    if error:
        result["agent"]["error"] = error

    # Write trajectory.json + screenshots if asked. Trajectory is ALREADY in the
    # WAB shape from agent_eval.run_episode — just dump it.
    if trajectory_dir is not None:
        trajectory_dir = Path(trajectory_dir)
        trajectory_dir.mkdir(parents=True, exist_ok=True)
        traj_path = trajectory_dir / "trajectory.json"
        try:
            traj_path.write_text(json.dumps(result, indent=2, default=str))
        except Exception as write_exc:
            logger.warning("Failed to write %s: %s", traj_path, write_exc)

    return result


async def run_episode(
    task_id: str,
    *,
    model: str,
    provider: str = "gemini",
    variant_filename: str | None = None,
    server_host: str = "127.0.0.1",
    backend_port: int = 8080,
    frontend_port: int = 8084,  # accepted for API parity with stock harness; unused
    max_steps: int = _DEFAULT_MAX_STEPS,
    timeout_seconds: int = _DEFAULT_TIMEOUT,
    max_actions_per_step: int = 1,  # accepted for parity; pixel agent always emits 1
    verbose: bool = True,
    record_trajectory: bool = True,
    trajectory_screenshots: bool = True,  # accepted for parity; not used in pixel mode
    trajectory_dir: Path | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Async entrypoint, matching `stock_browseruse_eval.run_episode` shape."""
    return await asyncio.to_thread(
        _run_episode_sync,
        task_id,
        model=model,
        provider=provider,
        variant_filename=variant_filename,
        server_host=server_host,
        backend_port=backend_port,
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
        headless=headless,
        verbose=verbose,
        trajectory_dir=trajectory_dir if record_trajectory else None,
    )


# =============================================================================
# Reused helpers — re-exported from stock_browseruse_eval so pixel_run_picks.py
# can drop into the same path.
# =============================================================================

def _task_slug(task_id: str, variant_filename: str | None = None, cond: str | None = None) -> str:
    """Filesystem-safe per-task subdirectory name. Mirrors stock harness."""
    if cond:
        return f"{task_id}__{cond}"
    return task_id


def write_run_artifacts(
    out_dir: Path,
    *,
    model: str,
    provider: str,
    results: list[dict[str, Any]],
    trajectory_paths: list[str | None],
    wall_seconds: float,
    started_at: str,
    ended_at: str,
    extra_manifest: dict[str, Any] | None = None,
) -> None:
    """Write summary.json + run_manifest.json under out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n = len(results)
    passed = sum(1 for r in results if r.get("evaluation", {}).get("success"))
    avg = sum(r.get("evaluation", {}).get("score", 0.0) for r in results) / max(n, 1)

    summary = {
        "n_tasks": n,
        "passed": passed,
        "avg_score": round(avg, 4),
        "wall_seconds": round(wall_seconds, 1),
        "started_at": started_at,
        "ended_at": ended_at,
        "results": [
            {
                "task_id": r.get("task_id"),
                "variant_filename": r.get("variant_filename"),
                "score": r.get("evaluation", {}).get("score", 0.0),
                "success": r.get("evaluation", {}).get("success", False),
                "trajectory_path": tpath,
            }
            for r, tpath in zip(results, trajectory_paths)
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    manifest = {
        "model": model,
        "provider": provider,
        "harness": "pixel-vlm",
        "n_tasks": n,
        "started_at": started_at,
        "ended_at": ended_at,
        "wall_seconds": round(wall_seconds, 1),
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))


# =============================================================================
# Tiny CLI for single-task smoke testing
# =============================================================================

def _main_cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Single-task pixel smoke")
    p.add_argument("--task", required=True)
    p.add_argument("--variant", default=None,
                   help="variant filename (just the .yaml name, not full path)")
    p.add_argument("--model", required=True)
    p.add_argument("--provider", default="gemini")
    p.add_argument("--backend-port", type=int, default=8080)
    p.add_argument("--max-steps", type=int, default=_DEFAULT_MAX_STEPS)
    p.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT)
    p.add_argument("--output-dir", default=None)
    p.add_argument("--no-headless", action="store_true",
                   help="show browser window (useful when debugging interactively)")
    args = p.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else None
    result = asyncio.run(run_episode(
        task_id=args.task,
        variant_filename=args.variant,
        model=args.model,
        provider=args.provider,
        backend_port=args.backend_port,
        max_steps=args.max_steps,
        timeout_seconds=args.timeout,
        trajectory_dir=out_dir,
        headless=not args.no_headless,
        verbose=True,
    ))
    print(json.dumps({
        "task_id": result["task_id"],
        "score": result["evaluation"].get("score"),
        "success": result["evaluation"].get("success"),
        "steps": result["agent"]["steps"],
        "elapsed": result["agent"]["elapsed_seconds"],
    }, indent=2))


if __name__ == "__main__":
    _main_cli()
