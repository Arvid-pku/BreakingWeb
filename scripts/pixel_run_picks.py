"""Pixel-mode (vision-only) picks runner — clone of `run_picks.py`.

Same JSON picks-file format as `run_picks.py`. Difference: dispatches to
`breakingweb.pixel_eval.run_episode` (BrowserGym + PixelLLMAgent, coord
action_space, screenshot-only obs) instead of the stock browser-use harness.

See `scripts/run_picks.py` for the picks-file shape and output layout —
identical here.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from breakingweb.pixel_eval import (  # noqa: E402
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
        "agent": {"model": model, "provider": provider, "harness": "pixel-vlm",
                  "steps": 0, "elapsed_seconds": 0},
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
        cond = pick.get("cond") or ("intervention" if pick.get("variant_filename") else "clean")
        slug = _task_slug(pick["task_id"], pick.get("variant_filename"), cond)
        task_dir = out_dir / "tasks" / slug
        try:
            ep = await run_episode(
                task_id=pick["task_id"],
                model=args.model,
                provider=args.provider,
                variant_filename=pick.get("variant_filename"),
                server_host=args.server_host,
                backend_port=args.backend_port,
                frontend_port=args.frontend_port,
                max_steps=args.max_steps,
                timeout_seconds=args.timeout,
                verbose=False,
                record_trajectory=args.record_trajectory,
                trajectory_dir=task_dir if args.record_trajectory else None,
                headless=True,
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
    p.add_argument("--provider", default="gemini")
    p.add_argument("--backend-port", type=int, default=8080)
    p.add_argument("--frontend-port", type=int, default=8080)
    p.add_argument("--server-host", default="127.0.0.1")
    p.add_argument("--max-steps", type=int, default=60)
    p.add_argument("--timeout", type=int, default=1200)
    p.add_argument(
        "--output-dir",
        default="breakingweb/results/pixel_run_picks_out",
    )
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--concurrency", type=int, default=1)
    # Sharding: split the picks file across N parallel processes (e.g. one
    # slurm array task per shard). Each shard runs picks where idx % shard-of
    # == shard-id. Output is written to `<output-dir>/shard_<id>/...`.
    p.add_argument(
        "--shard-of", type=int, default=None,
        help="Total number of shards; split picks evenly across this many parallel "
             "runs. Combine with --shard-id and slurm --array.",
    )
    p.add_argument(
        "--shard-id", type=int, default=0,
        help="Zero-based shard index (defaults to SLURM_ARRAY_TASK_ID env var if set).",
    )
    p.add_argument(
        "--no-trajectory", dest="record_trajectory",
        action="store_false", default=True,
    )
    args = p.parse_args()

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")
    if args.concurrency > 1:
        # Playwright's sync API isn't thread-safe — sharing a BrowserEnv
        # across asyncio.to_thread workers reliably raises
        # "Cannot switch to a different thread". The only way to parallelize
        # pixel-mode is fan-out across PROCESSES. See README's sweep section
        # for the multi-process patterns (slurm array OR plain shell loop
        # with --shard-of/--shard-id).
        raise SystemExit(
            f"--concurrency={args.concurrency} is not supported for pixel mode "
            "(Playwright sync API can't share a BrowserEnv across threads). "
            "Run multiple PROCESSES instead — each with --shard-of N --shard-id i. "
            "See README 'Running a sweep — parallel without slurm' for an example."
        )

    picks = json.loads(Path(args.picks).read_text())

    # Resolve shard-id from CLI or SLURM_ARRAY_TASK_ID env var
    shard_id = args.shard_id
    if "SLURM_ARRAY_TASK_ID" in os.environ:
        try:
            shard_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
        except ValueError:
            pass

    if args.shard_of and args.shard_of > 1:
        if shard_id < 0 or shard_id >= args.shard_of:
            raise SystemExit(
                f"--shard-id {shard_id} out of range for --shard-of {args.shard_of}"
            )
        picks = [pk for i, pk in enumerate(picks) if i % args.shard_of == shard_id]
        # Sharded runs each get their own subdir so they don't trample one another.
        out_dir = Path(args.output_dir) / f"shard_{shard_id:02d}"
    else:
        out_dir = Path(args.output_dir)

    if args.limit:
        picks = picks[: args.limit]
    total = len(picks)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tasks").mkdir(exist_ok=True)

    mode = "sequential" if args.concurrency == 1 else f"concurrency={args.concurrency}"
    if args.shard_of and args.shard_of > 1:
        mode = f"shard {shard_id+1}/{args.shard_of}, {mode}"
    print(f"Running {total} pixel-mode tasks, model={args.model} provider={args.provider} ({mode})", flush=True)
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
