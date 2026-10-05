"""BreakingWeb evaluation using BrowserGym environments.

Runs an LLM agent against BreakingWeb tasks using the standard BrowserGym
observation and action format — identical to WebArena, WorkArena, etc.

Usage:
    python -m breakingweb.agent_eval --model gpt-4o --provider openai
    python -m breakingweb.agent_eval --model gpt-4o --provider openai --tasks gmail_board_briefing_prep
    python -m breakingweb.agent_eval --model gpt-4o --provider openai --degradation gmail_compliance_settings__patience.yaml
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import getenv

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent
_MANIFEST = json.loads((BASE_DIR / "manifest.json").read_text())

# Load local secrets (OPENAI_API_KEY, AWS_BEDROCK_API_KEY, GEMINI_API_KEY, ...)
# from breakingweb/.env if present. .env is gitignored.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(BASE_DIR / ".env", override=False)
except Exception:
    pass

_DEFAULT_MAX_STEPS = 30
_DEFAULT_TIMEOUT = 300

_TRANSIENT_ERROR_CODES = ("429", "500", "502", "503", "504")
_MAX_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF_SECONDS = 30


# =============================================================================
# Episode runner
# =============================================================================

def _literal_from_ast(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
        operand = node.operand.value
        if isinstance(operand, (int, float)) and not isinstance(operand, bool):
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return operand
    raise ValueError("non-literal action argument")


def _parse_action_string(raw_action: str) -> dict[str, Any]:
    """Convert a BrowserGym function-call string into structured action metadata."""
    action_text = (raw_action or "").strip()
    if not action_text:
        return {"action": "unknown"}

    try:
        expr = ast.parse(action_text, mode="eval").body
    except SyntaxError:
        # Fallback: regex parse for common patterns like fill("ref", "value with \"quotes\"")
        m = re.match(r'(\w+)\s*\(\s*["\'](\d+)["\']\s*(?:,\s*["\'](.*)["\']\s*)?\)', action_text, re.DOTALL)
        if m:
            func, ref, value = m.group(1), m.group(2), m.group(3) or ""
            if func in ("fill", "select_option"):
                return {"action": func, "ref": ref, "value": value}
            return {"action": func, "ref": ref}
        return {"action": action_text}

    if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name):
        return {"action": action_text}
    if expr.keywords:
        return {"action": expr.func.id, "raw": action_text}

    try:
        args = [_literal_from_ast(node) for node in expr.args]
    except ValueError:
        return {"action": expr.func.id, "raw": action_text}

    func_name = expr.func.id
    if func_name in {"click", "dblclick", "hover", "clear", "focus"}:
        return {"action": func_name, "ref": args[0] if args else None}
    if func_name in {"fill", "select_option", "upload_file"}:
        return {
            "action": func_name,
            "ref": args[0] if len(args) > 0 else None,
            "value": args[1] if len(args) > 1 else None,
        }
    if func_name == "press":
        return {
            "action": func_name,
            "ref": args[0] if len(args) > 0 else None,
            "key": args[1] if len(args) > 1 else None,
        }
    if func_name == "scroll":
        delta_x = args[0] if len(args) > 0 else 0
        delta_y = args[1] if len(args) > 1 else 0
        return {
            "action": "scroll",
            "delta_x": delta_x,
            "delta_y": delta_y,
            "direction": "down" if (delta_y or 0) >= 0 else "up",
        }
    if func_name == "drag_and_drop":
        return {
            "action": func_name,
            "from_ref": args[0] if len(args) > 0 else None,
            "to_ref": args[1] if len(args) > 1 else None,
        }
    if func_name == "send_msg_to_user":
        return {"action": "finish", "answer": args[0] if args else ""}
    if func_name == "report_infeasible":
        return {"action": "report_infeasible", "reason": args[0] if args else ""}
    if func_name == "noop":
        return {"action": "noop", "wait_ms": args[0] if args else 1000}
    return {"action": func_name, "args": args}


def _extract_targets(parsed_action: dict[str, Any], obs: dict | None) -> dict[str, Any]:
    """Extract ARIA role/name for the target element from the observation's a11y tree."""
    if not obs or not isinstance(obs, dict):
        return {}
    ref = parsed_action.get("ref")
    if ref is None:
        return {}
    bid = str(ref)
    # BrowserGym's axtree_object is an AXTree; search for the BID in the flattened text
    axtree = obs.get("axtree_object")
    if not axtree:
        return {"ref": bid}
    try:
        from browsergym.utils.obs import flatten_axtree_to_str
        # Mirror format_obs_for_llm's call signature. The bids live in
        # extra_element_properties; without it, filter_with_bid_only drops
        # every line and nothing matches.
        tree_text = flatten_axtree_to_str(
            axtree,
            extra_properties=obs.get("extra_element_properties", {}),
            with_clickable=True, with_visible=True,
            filter_visible_only=True, filter_with_bid_only=True,
        )
        # Find the line with this BID: e.g. [76] button 'Search'
        # BrowserGym's flatten_axtree uses single quotes; tolerate both.
        for line in tree_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith(f"[{bid}]"):
                # Parse: [76] role 'name' (or double quotes)
                m = re.match(r"""\[\d+\]\s+(\w+)\s+["']([^"']*)["']""", stripped)
                if m:
                    return {"ref": bid, "role": m.group(1), "name": m.group(2)}
                m2 = re.match(r"\[\d+\]\s+(\w+)", stripped)
                if m2:
                    return {"ref": bid, "role": m2.group(1), "name": ""}
                return {"ref": bid}
    except Exception:
        pass
    return {"ref": bid}


def _trajectory_status(
    parsed_action: dict[str, Any],
    last_action_error: str,
    terminated: bool,
) -> str:
    if last_action_error:
        return f"ERROR: {last_action_error}"
    if terminated:
        action_name = parsed_action.get("action")
        if action_name == "finish":
            return "FINISH"
        if action_name == "report_infeasible":
            return "INFEASIBLE"
    return ""

_STEP_TIMEOUT_SECONDS = 120


def _save_step_screenshot(
    screenshot: Any, screenshots_dir: Path, step_number: int
) -> str | None:
    """Persist a pre-action screenshot to ``step_NN.png``.

    Accepts numpy arrays (from BrowserGym), bytes, or PIL Images.
    Returns the relative filename ("step_03.png") for inclusion in trajectory,
    or None on failure.
    """
    if screenshot is None:
        return None
    # Match stock_browseruse_eval naming: `step01.png`, `step02.png`, ...
    # so downstream replay/visualize tools work the same on both harnesses.
    fname = f"step{step_number:02d}.png"
    out = screenshots_dir / fname
    try:
        if hasattr(screenshot, "save"):  # PIL.Image
            screenshot.save(out)
        else:
            import io
            from PIL import Image
            if isinstance(screenshot, (bytes, bytearray)):
                img = Image.open(io.BytesIO(bytes(screenshot)))
            else:
                # numpy array (H, W, 3) uint8
                img = Image.fromarray(screenshot)
            img.save(out)
    except Exception as exc:
        logger.warning("Failed to save screenshot for step %d: %s", step_number, exc)
        return None
    return f"screenshots/{fname}"


def run_episode(
    env,
    agent,
    *,
    episode_seed: int | None = None,
    max_steps: int = 50,
    timeout_seconds: int = 300,
    verbose: bool = True,
    screenshots_dir: Path | None = None,
) -> dict:
    """Run one agent episode on a BrowserGym environment.

    Args:
        env: A BrowserGym BrowserEnv instance (not yet reset).
        agent: An LLMAgent instance.
        max_steps: Max steps before truncation.
        timeout_seconds: Wall-clock timeout.
        screenshots_dir: If set, save pre-action screenshot per step as
            ``step_NN.png`` (only applies when obs has a ``screenshot`` field —
            pixel-mode runs).
    """
    start_time = time.time()
    trajectory: list[dict] = []
    if screenshots_dir is not None:
        screenshots_dir = Path(screenshots_dir)
        screenshots_dir.mkdir(parents=True, exist_ok=True)

    if episode_seed is None:
        obs, info = env.reset()
    else:
        obs, info = env.reset(seed=episode_seed)
    task_info = info.get("task_info", {})
    task_id = task_info.get("task_id", "")
    goal = obs.get("goal", "") if isinstance(obs, dict) else ""

    agent.reset(obs)

    if verbose:
        print(f"  Goal: {goal[:120]}{'...' if len(goal) > 120 else ''}")

    completed = False
    evaluation = {"score": 0.0, "success": False, "reasoning": "Agent did not finish"}

    for step in range(max_steps):
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            if verbose:
                print(f"    Step {step + 1}: TIMEOUT ({elapsed:.0f}s)")
            break

        pre_action_obs = obs
        screenshot_path: str | None = None
        if screenshots_dir is not None and isinstance(pre_action_obs, dict):
            screenshot_path = _save_step_screenshot(
                pre_action_obs.get("screenshot"), screenshots_dir, step + 1
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(agent.act, obs)
            try:
                action = _fut.result(timeout=_STEP_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                if verbose:
                    step_elapsed = round(time.time() - start_time, 1)
                    print(f"    Step {step + 1}: STEP TIMEOUT ({_STEP_TIMEOUT_SECONDS}s, total {step_elapsed}s)")
                break

        if verbose:
            print(f"    Step {step + 1}: {action[:80]}{'...' if len(action) > 80 else ''}")

        obs, reward, terminated, truncated, step_info = env.step(action)
        last_action_error = obs.get("last_action_error", "") if isinstance(obs, dict) else ""
        parsed_action = _parse_action_string(action)

        # Extract thought from agent's reasoning (gpt-5.x reasoning_content or text before action)
        thought = getattr(agent, "_last_thought", "") or ""
        raw_response = getattr(agent, "_last_raw_response", "") or ""

        # Extract ARIA targets from the pre-action observation
        targets = _extract_targets(parsed_action, pre_action_obs)

        entry: dict[str, Any] = {
            "step": step + 1,
            "thought": thought,
            "action": parsed_action,
            "raw_action": action,
            "targets": targets,
            "status": _trajectory_status(parsed_action, last_action_error, terminated),
            "reward": reward,
            "elapsed_seconds": round(time.time() - start_time, 1),
            "last_action_error": last_action_error,
        }
        if raw_response:
            entry["raw_response"] = raw_response
        if screenshot_path:
            entry["screenshot"] = screenshot_path
        trajectory.append(entry)

        if terminated:
            completed = True
            task_eval = step_info.get("task_info", {}).get("evaluation", {})
            if task_eval:
                evaluation = task_eval
            elif reward != 0:
                evaluation = {"score": reward, "success": reward > 0.5, "reasoning": f"Reward: {reward}"}
            if verbose:
                print(f"    Agent finished at step {step + 1}")
            break

        if truncated:
            if verbose:
                print(f"    Truncated at step {step + 1}")
            break

    # Force a final state-based evaluation, regardless of how the loop ended
    # (terminated / truncated / max_steps / timeout). WAB evaluators are
    # state-based — the agent's send_msg_to_user('done') is only a BrowserGym
    # signaling convention, not a precondition for scoring. Without this,
    # pixel-mode agents (which often skip the done declaration) silently
    # score 0 even when they completed the task correctly.
    forced_eval: dict[str, Any] = {}
    try:
        task = getattr(env, "task", None) or getattr(getattr(env, "unwrapped", None), "task", None)
        page = getattr(env, "page", None) or getattr(getattr(env, "unwrapped", None), "page", None)
        if task is not None and page is not None and hasattr(task, "force_evaluate"):
            forced_eval = task.force_evaluate(page) or {}
    except Exception as exc:
        logger.warning("force_evaluate at end-of-episode failed: %s", exc)

    if forced_eval and float(forced_eval.get("score", 0.0)) > float(evaluation.get("score", 0.0)):
        # Prefer the forced eval — the in-loop evaluation only ran if the
        # agent declared done, so the state-based score is the canonical truth.
        evaluation = forced_eval
        if verbose:
            print(f"    [force_evaluate] score={evaluation.get('score', 0.0)} success={evaluation.get('success', False)}")

    return {
        "task_id": task_id,
        "goal": goal,
        "steps": len(trajectory),
        "elapsed_seconds": round(time.time() - start_time, 1),
        "completed": completed,
        "trajectory": trajectory,
        "evaluation": evaluation,
        "messages": agent.conversation,
        "task_info": task_info,
    }


# =============================================================================
# Multi-task evaluation
# =============================================================================

def resolve_task_ids(
    task_filter: list[str] | None = None,
    environments_filter: list[str] | None = None,
) -> list[str]:
    from .tasks._registry import load_all_tasks, tasks_by_env
    if task_filter:
        all_tasks = load_all_tasks()
        for tid in task_filter:
            if tid not in all_tasks:
                raise ValueError(f"Unknown task_id: {tid}")
        return list(task_filter)
    if environments_filter:
        groups = tasks_by_env()
        ids = []
        for env_id in environments_filter:
            if env_id not in groups:
                raise ValueError(f"Unknown environment: {env_id}")
            ids.extend(t.task_id for t in groups[env_id])
        return ids
    return list(load_all_tasks().keys())


def _run_single_task(args: tuple) -> dict:
    """Run one task in its own process (process-safe). Args passed as a tuple for pickling."""
    (task_id, model, provider, base_url, api_key, temperature, reasoning_effort,
     use_per_task_budget, max_steps, timeout_per_task, headless,
     server_host, server_port, seed, deg_path, verbose) = args

    from .agent import LLMAgent
    from .browsergym_env import make_env
    from .tasks._registry import get_task as _get_task

    agent = LLMAgent(
        model=model, provider=provider, base_url=base_url, api_key=api_key,
        temperature=temperature, reasoning_effort=reasoning_effort,
    )

    task_def = _get_task(task_id)
    if use_per_task_budget:
        task_max_steps = int((task_def.expected_steps or _DEFAULT_MAX_STEPS) * 1.5)
        task_timeout = task_def.time_limit_seconds or _DEFAULT_TIMEOUT
    else:
        task_max_steps = max_steps
        task_timeout = timeout_per_task

    if verbose:
        print(f"[{task_id}] (steps<={task_max_steps}, timeout={task_timeout}s)", flush=True)

    env = make_env(
        task_id=task_id,
        degradation=deg_path,
        headless=headless,
        server_host=server_host,
        server_port=server_port,
    )

    try:
        for _attempt in range(_MAX_RETRY_ATTEMPTS):
            try:
                episode = run_episode(
                    env, agent,
                    episode_seed=seed,
                    max_steps=task_max_steps,
                    timeout_seconds=task_timeout,
                    verbose=verbose,
                )
                break
            except Exception as exc:
                exc_str = str(exc)
                is_transient = (
                    isinstance(exc, (ConnectionError, TimeoutError))
                    or any(code in exc_str for code in _TRANSIENT_ERROR_CODES)
                )
                if not is_transient or _attempt >= _MAX_RETRY_ATTEMPTS - 1:
                    raise
                logger.warning(
                    "Transient error on task %s (attempt %d/%d), retrying in %ds: %s",
                    task_id, _attempt + 1, _MAX_RETRY_ATTEMPTS, _RETRY_BACKOFF_SECONDS, exc,
                )
                if verbose:
                    print(f"  [{task_id}] [RETRY] retrying in {_RETRY_BACKOFF_SECONDS}s: {exc}", flush=True)
                env.close()
                time.sleep(_RETRY_BACKOFF_SECONDS)
                env = make_env(
                    task_id=task_id,
                    degradation=deg_path,
                    headless=headless,
                    server_host=server_host,
                    server_port=server_port,
                )

        evaluation = episode["evaluation"]
        score = evaluation.get("score", evaluation.get("final_score", 0.0))
        icon = "PASS" if evaluation.get("success") else "FAIL"
        if verbose:
            print(f"  [{icon}] [{task_id}] score={score:.2f} ({episode['steps']} steps, {episode['elapsed_seconds']:.0f}s)", flush=True)
            print(f"  {str(evaluation.get('reasoning', ''))[:120]}", flush=True)

        return {
            "task_id": task_id,
            "evaluation": evaluation,
            "agent": {
                "model": model, "provider": provider,
                "steps": episode["steps"],
                "elapsed_seconds": episode["elapsed_seconds"],
                "completed": episode["completed"],
                "trajectory": episode["trajectory"],
                "messages": episode["messages"],
            },
        }

    except Exception as exc:
        logger.error("Error on task %s: %s", task_id, exc, exc_info=True)
        if verbose:
            print(f"  [ERROR] [{task_id}] {exc}", flush=True)
        return {
            "task_id": task_id,
            "evaluation": {"score": 0.0, "success": False, "reasoning": f"Error: {exc}"},
            "agent": {"model": model, "provider": provider, "steps": 0, "elapsed_seconds": 0, "completed": False, "trajectory": [], "messages": []},
        }
    finally:
        env.close()


def _resolve_all_variants(environments_filter: list[str] | None) -> list[tuple[str, str]]:
    """Return (task_id, variant_path_str) pairs for all variant files matching the env filter."""
    from .injector.config import DegradationConfig
    variants_dir = BASE_DIR / "injector" / "variants"
    pairs: list[tuple[str, str]] = []
    task_ids = set(resolve_task_ids(None, environments_filter))
    for path in sorted(variants_dir.glob("*.yaml")):
        try:
            cfg = DegradationConfig.from_yaml(path)
        except Exception:
            continue
        if cfg.base_task_id and cfg.base_task_id in task_ids:
            pairs.append((cfg.base_task_id, str(path)))
    return pairs


def run_evaluation(
    model: str,
    provider: str = "openai",
    base_url: str | None = None,
    api_key: str | None = None,
    task_filter: list[str] | None = None,
    environments_filter: list[str] | None = None,
    max_steps: int = 30,
    timeout_per_task: int = 300,
    headless: bool = True,
    verbose: bool = True,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    server_host: str = "127.0.0.1",
    server_port: int = 8080,
    output_path: str = "results/breakingweb/results.json",
    seed: int | None = None,
    degradation: str | None = None,
    all_variants: bool = False,
    workers: int = 1,
) -> list[dict]:
    """Run evaluation using BrowserGym environments."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    # Build per-task (task_id, deg_path_str) pairs
    if all_variants:
        variant_pairs = _resolve_all_variants(environments_filter)
        if not variant_pairs:
            print("No variant files found for the given environments.", file=sys.stderr)
            return []
        task_ids = [t for t, _ in variant_pairs]
        deg_path_strs = [d for _, d in variant_pairs]
        deg_config = None
    else:
        task_ids = resolve_task_ids(task_filter, environments_filter)
        deg_config = None
        deg_path_str: str | None = None
        if degradation:
            from .injector.config import DegradationConfig
            deg_path = Path(degradation)
            for candidate in [deg_path, BASE_DIR / degradation, BASE_DIR / "injector" / "variants" / degradation]:
                if candidate.exists():
                    deg_path = candidate
                    break
            if not deg_path.exists():
                print(f"ERROR: Degradation config not found: {degradation}", file=sys.stderr)
                return []
            deg_config = DegradationConfig.from_yaml(deg_path)
            deg_path_str = str(deg_path)
            if deg_config.base_task_id:
                task_ids = [t for t in task_ids if t == deg_config.base_task_id]
        deg_path_strs = [deg_path_str] * len(task_ids)

    if not task_ids:
        print("No tasks to evaluate.", file=sys.stderr)
        return []

    use_per_task_budget = (max_steps == _DEFAULT_MAX_STEPS and timeout_per_task == _DEFAULT_TIMEOUT)
    effective_workers = min(workers, len(task_ids))

    if verbose:
        print(f"Agent: {model} (via {provider})")
        print(f"Tasks: {len(task_ids)} | Workers: {effective_workers}")
        if all_variants:
            print(f"Mode: all-variants ({len(task_ids)} intervention tasks)")
        elif deg_config:
            print(f"Degradation: {deg_config.variant_id} ({deg_config.target_primitive})")
        budget_mode = "per-task (from YAML)" if use_per_task_budget else f"fixed (steps={max_steps}, timeout={timeout_per_task}s)"
        print(f"Budget: {budget_mode}")
        print(f"Environment: BrowserGym (bid actions, multimodal obs)")
        print(f"{'=' * 60}\n")

    # For parallel workers, start the server once in the parent process so all
    # child processes inherit BREAKINGWEB_CONTROLLER_SECRET and share it.
    _server_proc = None
    if effective_workers > 1:
        from .runner import ensure_controller_secret, start_server, wait_for_server
        if not wait_for_server(server_host, server_port, timeout=2):
            ensure_controller_secret()
            _server_proc = start_server(server_host, server_port)
            if not wait_for_server(server_host, server_port):
                raise RuntimeError("BreakingWeb server failed to start")
        elif not getenv("BREAKINGWEB_CONTROLLER_SECRET"):
            raise RuntimeError(
                "A BreakingWeb server is already running but BREAKINGWEB_CONTROLLER_SECRET "
                "is not set. Export the same secret or use a free port."
            )

    # Build picklable arg tuples — deg_path_str varies per task in all-variants mode
    base_common = (model, provider, base_url, api_key, temperature, reasoning_effort,
                   use_per_task_budget, max_steps, timeout_per_task, headless,
                   server_host, server_port, seed)
    task_args = [
        (tid,) + base_common + (deg, verbose)
        for tid, deg in zip(task_ids, deg_path_strs)
    ]

    results: list[dict] = []

    try:
        if effective_workers == 1:
            for args in task_args:
                try:
                    results.append(_run_single_task(args))
                except Exception as exc:
                    task_id = args[0]
                    print(f"  [ERROR] [{task_id}] worker exception: {exc}", flush=True)
                    results.append({"task_id": task_id, "evaluation": {"score": 0.0, "success": False}, "error": str(exc)})
        else:
            with ProcessPoolExecutor(max_workers=effective_workers) as pool:
                futures = {pool.submit(_run_single_task, args): args[0] for args in task_args}
                try:
                    for fut in as_completed(futures):
                        task_id = futures[fut]
                        try:
                            results.append(fut.result())
                        except Exception as exc:
                            print(f"  [ERROR] [{task_id}] worker exception: {exc}", flush=True)
                            results.append({"task_id": task_id, "evaluation": {"score": 0.0, "success": False}, "error": str(exc)})
                except Exception as pool_exc:
                    print(f"  [ERROR] process pool error: {pool_exc}", flush=True)
                    for fut, task_id in futures.items():
                        if not fut.done():
                            results.append({"task_id": task_id, "evaluation": {"score": 0.0, "success": False}, "error": str(pool_exc)})
    finally:
        if _server_proc is not None:
            _server_proc.terminate()

    results.sort(key=lambda r: r["task_id"])
    _write_results(results, model, provider, output_path, degradation=deg_config)
    if verbose:
        _print_summary(results)
    return results


def _write_results(results, model, provider, output_path, degradation=None):
    total = len(results)
    if not total:
        return
    passed = sum(1 for r in results if r["evaluation"].get("success"))
    scores = [r["evaluation"].get("score", r["evaluation"].get("final_score", 0.0)) for r in results]
    times = [r.get("agent", {}).get("elapsed_seconds", 0) for r in results]
    steps = [r.get("agent", {}).get("steps", 0) for r in results]
    output: dict[str, Any] = {
        "benchmark": "BreakingWeb",
        "version": _MANIFEST["version"],
        "format": "browsergym",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": {"model": model, "provider": provider},
        "results": results,
        "summary": {
            "total_tasks": total, "passed": passed, "failed": total - passed,
            "average_score": round(sum(scores) / total, 3),
            "average_steps": round(sum(steps) / total, 1),
            "average_elapsed_seconds": round(sum(times) / total, 1),
        },
    }
    if degradation:
        output["degradation"] = {"variant_id": degradation.variant_id, "target_primitive": degradation.target_primitive}
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {out_file}")


def _print_summary(results):
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"].get("success"))
    scores = [r["evaluation"].get("score", r["evaluation"].get("final_score", 0.0)) for r in results]
    avg = sum(scores) / total if total else 0
    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {passed}/{total} passed  |  avg score: {avg:+.3f}")
    print(f"{'=' * 60}")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="BreakingWeb Evaluation (BrowserGym)", epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--provider", default="openai", choices=["vllm", "openai", "gemini", "bedrock"])
    parser.add_argument("--api-base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--reasoning-effort", default=None, choices=["none", "minimal", "low", "medium", "high", "xhigh"])
    parser.add_argument("--tasks", nargs="*")
    parser.add_argument("--environments", nargs="*")
    parser.add_argument("--degradation", default=None)
    parser.add_argument("--all-variants", action="store_true", default=False,
                        help="Run all intervention variants for the given environments")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=_DEFAULT_MAX_STEPS,
                        help=f"Max steps per task (default: {_DEFAULT_MAX_STEPS}, uses per-task YAML budget when unchanged)")
    parser.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT,
                        help=f"Timeout per task in seconds (default: {_DEFAULT_TIMEOUT}, uses per-task YAML budget when unchanged)")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_false", dest="headless")
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=8080)
    parser.add_argument("--output", default="results/breakingweb/results.json")
    parser.add_argument("--workers", type=int, default=1, help="Parallel worker threads (default: 1)")
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument(
        "--harness", choices=["browsergym", "browser-use"], default="browsergym",
        help="Agent harness to use (default: browsergym)",
    )
    args = parser.parse_args()

    if args.harness == "browser-use":
        import asyncio

        from .browseruse_eval import run_evaluation as bu_run_evaluation

        asyncio.run(bu_run_evaluation(
            model=args.model,
            provider=args.provider,
            base_url=args.api_base_url,
            api_key=args.api_key,
            task_filter=args.tasks,
            environments_filter=args.environments,
            max_steps=args.max_steps,
            timeout_per_task=args.timeout,
            headless=args.headless,
            verbose=not args.quiet,
            temperature=args.temperature,
            reasoning_effort=args.reasoning_effort,
            server_host=args.server_host,
            server_port=args.server_port,
            output_path=args.output,
            seed=args.seed,
            degradation=args.degradation,
        ))
        return

    run_evaluation(
        model=args.model, provider=args.provider, base_url=args.api_base_url,
        api_key=args.api_key, task_filter=args.tasks, environments_filter=args.environments,
        max_steps=args.max_steps, timeout_per_task=args.timeout, headless=args.headless,
        verbose=not args.quiet, temperature=args.temperature, reasoning_effort=args.reasoning_effort,
        server_host=args.server_host, server_port=args.server_port, output_path=args.output,
        seed=args.seed, degradation=args.degradation,
        all_variants=args.all_variants, workers=args.workers,
    )


if __name__ == "__main__":
    main()
