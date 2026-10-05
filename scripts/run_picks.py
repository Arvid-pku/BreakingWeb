"""Run a list of (task_id, variant_filename) picks through stock_browseruse_eval.

Input: JSON array of ``{"task_id", "variant_filename", "env", "diff", "cond"}``
as produced by ``scripts/gen_picks.py``.

Output layout (under ``--output-dir``):

    <output-dir>/
    ├── summary.json         top-level aggregation (score/pass/avg/trajectory_path)
    ├── run_manifest.json    reproducibility metadata (model, provider, picks file, git sha)
    └── tasks/
        ├── <task_id>__clean/
        │   ├── trajectory.json
        │   └── screenshots/step01.png, step02.png, ...
        ├── <task_id>__intervention/
        │   └── ...

Per-task artifacts are written *as each task completes* (atomic write), so a
mid-run crash still leaves the completed tasks inspectable.

By default picks are run sequentially; set ``--concurrency N`` to run up to N
episodes in parallel — each episode owns its own Browser + temp dir, so the
only shared resource is the backend. Budget ~400 MB RAM and ~1 CPU core per
concurrent episode.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from breakingweb.stock_browseruse_eval import (  # noqa: E402
    _task_slug,
    run_episode,
    write_run_artifacts,
)


def _format_row(idx: int, total: int, pick: dict) -> str:
    tag = f" (+{pick['variant_filename']})" if pick.get("variant_filename") else ""
    return f"[{idx}/{total}] {pick['task_id']}{tag}"


def _error_stub(pick: dict, model: str, provider: str, exc: BaseException) -> dict:
    return {
        "task_id": pick["task_id"],
        "variant_filename": pick.get("variant_filename"),
        "evaluation": {"score": 0.0, "success": False, "reasoning": f"harness error: {exc}"},
        "agent": {"model": model, "provider": provider, "steps": 0, "elapsed_seconds": 0},
        "pick_metadata": pick,
    }


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


async def _run_one(
    idx: int,
    total: int,
    pick: dict,
    *,
    args: argparse.Namespace,
    sem: asyncio.Semaphore,
    out_dir: Path,
) -> tuple[dict, str | None]:
    async with sem:
        header = _format_row(idx, total, pick)
        print(header, flush=True)
        # Condition label: picks from gen_picks.py always carry it; fall back
        # to a best-guess based on presence of variant_filename.
        cond = pick.get("cond") or ("intervention" if pick.get("variant_filename") else "clean")
        slug = _task_slug(pick["task_id"], pick.get("variant_filename"), cond)
        task_dir = out_dir / "tasks" / slug
        try:
            ep = await run_episode(
                task_id=pick["task_id"],
                model=args.model,
                provider=args.provider,
                variant_filename=pick.get("variant_filename"),
                env_seed=pick.get("seed"),
                server_host=args.server_host,
                backend_port=args.backend_port,
                frontend_port=args.frontend_port,
                max_steps=args.max_steps,
                timeout_seconds=args.timeout,
                step_timeout=args.step_timeout,
                max_actions_per_step=args.max_actions_per_step,
                verbose=False,
                record_trajectory=args.record_trajectory,
                trajectory_screenshots=args.trajectory_screenshots,
                trajectory_dir=task_dir if args.record_trajectory else None,
            )
            traj_path: str | None = (
                f"tasks/{slug}/trajectory.json" if args.record_trajectory else None
            )
        except Exception as exc:
            print(f"  EXCEPTION ({header}): {exc}", flush=True)
            traceback.print_exc(limit=3)
            return _error_stub(pick, args.model, args.provider, exc), None

        ep["variant_filename"] = pick.get("variant_filename")
        ep.setdefault("pick_metadata", pick)
        score = ep.get("evaluation", {}).get("score", 0.0)
        ok = "PASS" if ep.get("evaluation", {}).get("success") else "FAIL"
        elapsed = ep.get("agent", {}).get("elapsed_seconds", 0)
        print(f"  [{ok}] [{idx}/{total}] score={score:.2f}  ({elapsed}s)", flush=True)
        return ep, traj_path


async def _main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--picks", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--provider", default="bedrock")
    p.add_argument("--backend-port", type=int, default=8080)
    p.add_argument("--frontend-port", type=int, default=8080)
    p.add_argument("--server-host", default="127.0.0.1")
    p.add_argument("--max-steps", type=int, default=40)
    p.add_argument("--timeout", type=int, default=1200,
                   help="per-task wall-clock timeout (default 1200s)")
    p.add_argument("--step-timeout", type=int, default=240,
                   help="per-step LLM+action timeout in browser-use (default 240s, "
                        "covers Bedrock-routed Claude at ~40s/step)")
    p.add_argument("--max-actions-per-step", type=int, default=4)
    p.add_argument(
        "--output-dir",
        default="breakingweb/results/run_picks_out",
        help="directory for run artifacts: summary.json, run_manifest.json, "
             "tasks/<task_id>__<cond>/trajectory.json + screenshots/ "
             "(default: breakingweb/results/run_picks_out)",
    )
    p.add_argument("--limit", type=int, default=None)
    p.add_argument(
        "--concurrency", type=int, default=1,
        help="run up to N episodes in parallel (default 1 = sequential). "
             "Each concurrent episode uses ~400MB RAM + ~1 CPU core.",
    )
    p.add_argument(
        "--no-trajectory", dest="record_trajectory",
        action="store_false", default=True,
        help="don't write per-task trajectory.json or screenshots (smaller output)",
    )
    p.add_argument(
        "--no-trajectory-screenshots", dest="trajectory_screenshots",
        action="store_false", default=True,
        help="record trajectory but skip PNG screenshots (~10MB/task saved)",
    )
    args = p.parse_args()

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")

    picks = json.loads(Path(args.picks).read_text())
    if args.limit:
        picks = picks[: args.limit]
    total = len(picks)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tasks").mkdir(exist_ok=True)

    mode = "sequential" if args.concurrency == 1 else f"concurrency={args.concurrency}"
    print(f"Running {total} tasks, model={args.model} provider={args.provider} ({mode})", flush=True)
    print(f"Writing: {out_dir}/", flush=True)

    started_at = datetime.now(timezone.utc).isoformat()
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()
    tasks = [
        asyncio.create_task(_run_one(i, total, pick, args=args, sem=sem, out_dir=out_dir))
        for i, pick in enumerate(picks, 1)
    ]
    pairs = await asyncio.gather(*tasks)
    results = [p[0] for p in pairs]
    trajectory_paths = [p[1] for p in pairs]
    wall = time.time() - t0
    ended_at = datetime.now(timezone.utc).isoformat()

    write_run_artifacts(
        out_dir,
        model=args.model,
        provider=args.provider,
        results=results,
        trajectory_paths=trajectory_paths,
        wall_seconds=wall,
        started_at=started_at,
        ended_at=ended_at,
        extra_manifest={
            "picks_file": str(Path(args.picks).resolve()),
            "concurrency": args.concurrency,
            "max_steps": args.max_steps,
            "timeout": args.timeout,
            "git_sha": _git_sha(),
        },
    )

    passed = sum(1 for r in results if r.get("evaluation", {}).get("success"))
    avg = sum(r.get("evaluation", {}).get("score", 0.0) for r in results) / max(1, total)
    print(f"\nSUMMARY: {passed}/{total} passed, avg={avg:.3f}, wall={wall:.1f}s", flush=True)
    print(f"Wrote {out_dir}/summary.json", flush=True)


if __name__ == "__main__":
    asyncio.run(_main())
