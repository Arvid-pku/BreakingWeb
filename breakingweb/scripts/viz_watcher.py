"""Incremental trajectory visualizer.

Watches results/bedrock_subset/ for per-task result JSONs written by
run_bedrock_subset.py, merges whatever has completed so far into one envelope,
and regenerates breakingweb/static/bedrock_subset_viz.html every ``interval``
seconds. Open http://127.0.0.1:8080/static/bedrock_subset_viz.html (or the
/trajectories page) at any point to see current progress — no need to wait
for the full 112-task run to finish.

Usage:
    python -m breakingweb.scripts.viz_watcher
    python -m breakingweb.scripts.viz_watcher --interval 10
    python -m breakingweb.scripts.viz_watcher --once    # single pass
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _env_from_task(task_id: str) -> str:
    prefix = task_id.split("_", 1)[0]
    return {"rh": "robinhood", "pp": "patient_portal"}.get(prefix, prefix)


_TASK_REPLAY_CACHE: dict[str, tuple[str, str]] = {}


def _task_replay_info(root: Path, task_id: str) -> tuple[str, str]:
    """Return (env_id, start_path) for a task by reading its YAML."""
    if task_id in _TASK_REPLAY_CACHE:
        return _TASK_REPLAY_CACHE[task_id]
    import yaml
    env_id = _env_from_task(task_id)
    start_path = "/"
    p = root / "tasks" / env_id / f"{task_id}.yaml"
    if p.is_file():
        try:
            d = yaml.safe_load(p.read_text()) or {}
            env_id = d.get("env_id", env_id) or env_id
            start_path = d.get("start_path", start_path) or start_path
        except Exception:
            pass
    _TASK_REPLAY_CACHE[task_id] = (env_id, start_path)
    return env_id, start_path


def _reshape_step_targets(step: dict) -> dict:
    """visualize.py's executeAction expects `targets.ref` to be an object with
    `.role/.name/.selector/.nth`, but agent_eval writes a flat
    {ref, role, name}. Nest role+name under ref so the JS finds elements.
    Also copies from_ref/to_ref for drag_and_drop."""
    targets = dict(step.get("targets") or {})
    ref = targets.get("ref")
    role = targets.get("role") or ""
    name = targets.get("name") or ""
    if isinstance(ref, str):
        # Flat shape — nest. Note bid selectors don't survive across sessions,
        # so we leave selector empty and rely on findByRole.
        targets["ref"] = {"bid": ref, "role": role, "name": name, "nth": 0}
    for key in ("from_ref", "to_ref"):
        v = targets.get(key)
        if isinstance(v, str):
            targets[key] = {"bid": v, "role": "", "name": "", "nth": 0}
    step = dict(step)
    step["targets"] = targets
    return step


def _tag(result: dict, *, configuration: str, variant_filename: str | None,
         root: Path, seed: int = 42) -> dict:
    """Tag a per-task result with configuration + attach a `replay` block so
    visualize.py's iframe can spin up a live session for playback."""
    tagged = dict(result)
    base = tagged.get("task_id", "")
    env_id, start_path = _task_replay_info(root, base)
    base_url = f"/env/{env_id}"

    tagged["task_id"] = f"{base}__{configuration}"
    tagged["base_task_id"] = base
    tagged["configuration"] = configuration
    tagged.setdefault("env_id", env_id)
    tagged.setdefault("task_type", "env")
    tagged.setdefault("base_url", base_url)
    tagged.setdefault("replay", {
        "kind": "env",
        "env_id": env_id,
        "task_id": base,
        "seed": seed,
        "base_url": base_url,
        "start_path": start_path,
        "variant_filename": variant_filename,
    })
    if variant_filename:
        tagged.setdefault("degradation", {})
        tagged["degradation"].setdefault("variant_filename", variant_filename)

    # Reshape trajectory targets so the viz's action-replay JS can locate
    # elements via role+name (bids don't survive across sessions).
    agent = dict(tagged.get("agent") or {})
    traj = agent.get("trajectory") or []
    agent["trajectory"] = [_reshape_step_targets(s) for s in traj]
    tagged["agent"] = agent
    return tagged


def _collect(results_dir: Path, *, root: Path, seed: int) -> list[dict]:
    """Read every standard_*.json and stress_*.json that exists, produce a
    uniformly-tagged list of result entries."""
    aggregated: list[dict] = []

    for path in sorted(results_dir.glob("standard_*.json")):
        try:
            envelope = json.loads(path.read_text())
        except Exception:
            continue
        for r in envelope.get("results", []):
            aggregated.append(_tag(r, configuration="standard", variant_filename=None,
                                   root=root, seed=seed))

    for path in sorted(results_dir.glob("stress_*.json")):
        try:
            envelope = json.loads(path.read_text())
        except Exception:
            continue
        for r in envelope.get("results", []):
            variant_filename = None
            deg = r.get("degradation") or envelope.get("degradation") or {}
            if isinstance(deg, dict):
                variant_filename = deg.get("variant_filename")
            if not variant_filename:
                variant_filename = f"{path.stem.removeprefix('stress_')}.yaml"
            aggregated.append(_tag(r, configuration="degraded", variant_filename=variant_filename,
                                   root=root, seed=seed))

    return aggregated


def _envelope(results: list[dict], model: str, provider: str, manifest_version: str) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.get("evaluation", {}).get("success"))
    scores = [r.get("evaluation", {}).get("score", r.get("evaluation", {}).get("final_score", 0.0)) for r in results]
    steps = [r.get("agent", {}).get("steps", 0) for r in results]
    times = [r.get("agent", {}).get("elapsed_seconds", 0) for r in results]
    return {
        "benchmark": "BreakingWeb",
        "version": manifest_version,
        "format": "browsergym",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": {"model": model, "provider": provider},
        "results": results,
        "summary": {
            "total_tasks": total,
            "passed": passed,
            "failed": total - passed,
            "average_score": round(sum(scores) / total, 3) if total else 0,
            "average_steps": round(sum(steps) / total, 1) if total else 0,
            "average_elapsed_seconds": round(sum(times) / total, 1) if total else 0,
            "in_progress": True,
        },
    }


def _rebuild(results_dir: Path, *, model: str, provider: str,
             root: Path, expected_total: int, seed: int) -> tuple[int, int, Path]:
    """One regeneration pass. Returns (count, passed, viz_path)."""
    from breakingweb.result_utils import build_manifest_task_meta, load_embedded_task_meta
    from breakingweb.visualize import generate_html

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    results = _collect(results_dir, root=root, seed=seed)
    envelope = _envelope(results, model, provider, manifest.get("version", ""))

    # Attach task_meta for the viz
    task_meta = load_embedded_task_meta(envelope)
    envelope["task_meta"] = {**build_manifest_task_meta(manifest), **task_meta}

    # Write merged.json snapshot + viz HTML.
    # Use a relative SERVER_URL ("") so the viz's fetches + iframe src resolve
    # against whichever origin serves the HTML (the launcher on :9090 or the
    # benchmark's internal :8080). Avoids cross-origin mismatches when both
    # are up simultaneously.
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "merged.json").write_text(json.dumps(envelope, indent=2, default=str))
    static_path = root / "static" / "bedrock_subset_viz.html"
    results_viz = results_dir / "viz.html"
    viz_html = generate_html(envelope, "")
    static_path.write_text(viz_html)
    results_viz.write_text(viz_html)

    passed = envelope["summary"]["passed"]
    return len(results), passed, static_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=int, default=20, help="seconds between regenerations")
    parser.add_argument("--once", action="store_true", help="rebuild once and exit")
    parser.add_argument("--model", default="us.anthropic.claude-sonnet-4-6")
    parser.add_argument("--provider", default="bedrock")
    parser.add_argument("--expected", type=int, default=112, help="total trajectories expected")
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed to embed in replay blocks so the viz can spin up matching sessions")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    results_dir = root.parent / "results" / "bedrock_subset"

    if not results_dir.is_dir():
        print(f"Waiting for {results_dir} to appear...", flush=True)

    last_count = -1
    while True:
        try:
            count, passed, viz_path = _rebuild(
                results_dir,
                model=args.model, provider=args.provider, root=root,
                expected_total=args.expected, seed=args.seed,
            )
        except FileNotFoundError:
            count, passed, viz_path = 0, 0, root / "static" / "bedrock_subset_viz.html"
        if count != last_count:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {count}/{args.expected} trajectories  |  {passed} passed  |  {viz_path}",
                  flush=True)
            last_count = count
        if args.once or count >= args.expected:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
