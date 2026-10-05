#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# LMS + Patient Portal benchmark sweep
#
# Runs a model against all 65 LMS + 70 Patient Portal tasks (135 total)
# using the browser-use harness with N parallel workers on a single
# shared FastAPI server.
#
# Usage:
#   ./scripts/run_lms_pp_sweep.sh                   # defaults (gpt-5, 6 workers)
#   WORKERS=8 ./scripts/run_lms_pp_sweep.sh         # push concurrency
#   MODEL=gpt-5.4 ./scripts/run_lms_pp_sweep.sh     # different model
#   SMOKE_ONLY=1 ./scripts/run_lms_pp_sweep.sh      # 2-task smoke only
#
# Monitor (from another terminal):
#   tail -f results/breakingweb/<run_tag>/progress.log
#   watch -n5 cat results/breakingweb/<run_tag>/scoreboard.txt
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_sweep_common.sh
source "$(dirname "$0")/_sweep_common.sh"

# ── Config ───────────────────────────────────────────────────────────
MODEL="${MODEL:-gpt-5}"
PROVIDER="${PROVIDER:-openai}"
WORKERS="${WORKERS:-6}"
PORT="${PORT:-8080}"
SEED="${SEED:-42}"
MAX_STEPS="${MAX_STEPS:-30}"
TIMEOUT="${TIMEOUT:-300}"
SMOKE_ONLY="${SMOKE_ONLY:-0}"
REASONING="${REASONING:-medium}"
HARNESS="${HARNESS:-browser-use}"
ENVIRONMENTS=(lms patient_portal)
OUTDIR="results/breakingweb"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_TAG="${MODEL//\//_}_lms_pp_${TIMESTAMP}"
RUNDIR="$OUTDIR/$RUN_TAG"
PROGRESS="$RUNDIR/progress.log"
SCOREBOARD="$RUNDIR/scoreboard.txt"

# ── Pre-flight ───────────────────────────────────────────────────────
sweep_preflight

mkdir -p "$RUNDIR"

cat > "$PROGRESS" <<EOF
═══════════════════════════════════════════════════════════
  LMS + Patient Portal Benchmark Sweep
  Model: $MODEL | Workers: $WORKERS | Harness: $HARNESS
  Reasoning: $REASONING | Seed: $SEED
  Started: $(date)

  Monitor:  tail -f $PROGRESS
  Scores:   watch -n5 cat $SCOREBOARD
═══════════════════════════════════════════════════════════

EOF

echo "SCOREBOARD — $MODEL — $(date +%H:%M:%S)" > "$SCOREBOARD"
echo "─────────────────────────────────────────" >> "$SCOREBOARD"
echo "(waiting for results...)" >> "$SCOREBOARD"

echo "═══════════════════════════════════════════════════════════"
echo "  LMS + Patient Portal Benchmark Sweep"
echo "  Model: $MODEL | Workers: $WORKERS | Harness: $HARNESS"
echo "  Reasoning: $REASONING | Run dir: $RUNDIR"
echo ""
echo "  Monitor from another terminal:"
echo "    tail -f $PROGRESS"
echo "    watch -n5 cat $SCOREBOARD"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ── Caffeinate ───────────────────────────────────────────────────────
caffeinate -d -i -s &
CAFF_PID=$!
trap "kill $CAFF_PID 2>/dev/null" EXIT
echo "caffeinate PID: $CAFF_PID" | tee -a "$PROGRESS"

# ── Start server if not running ──────────────────────────────────────
sweep_start_server "$PORT" "$PROGRESS"
if [[ -n "$SERVER_PID" ]]; then
    trap "kill $CAFF_PID $SERVER_PID 2>/dev/null" EXIT
fi

# ── Smoke test ───────────────────────────────────────────────────────
SMOKE_TASKS=(lms_drop_course pp_mark_all_read)
SMOKE_OUT="$RUNDIR/smoke.json"

echo "" | tee -a "$PROGRESS"
echo "SMOKE TEST: ${SMOKE_TASKS[*]}" | tee -a "$PROGRESS"
echo "" | tee -a "$PROGRESS"

REASONING_FLAG=""
if [[ -n "$REASONING" && "$REASONING" != "none" ]]; then
    REASONING_FLAG="--reasoning-effort $REASONING"
fi

HARNESS_FLAG=""
if [[ -n "$HARNESS" && "$HARNESS" != "browsergym" ]]; then
    HARNESS_FLAG="--harness $HARNESS"
fi

python -m breakingweb.agent_eval \
    --model "$MODEL" \
    --provider "$PROVIDER" \
    --api-key "$OPENAI_API_KEY" \
    --tasks "${SMOKE_TASKS[@]}" \
    --max-steps 15 \
    --timeout 180 \
    --seed "$SEED" \
    --server-port "$PORT" \
    $REASONING_FLAG \
    $HARNESS_FLAG \
    --output "$SMOKE_OUT" \
    2>&1 | tee -a "$PROGRESS"

SMOKE_CHECK=$(python3 -c "
import json, sys
data = json.load(open('$SMOKE_OUT'))
errors = [r['task_id'] for r in data['results'] if r['evaluation'].get('score', 0) == 0 and 'Error' in r['evaluation'].get('reasoning', '')]
if errors:
    print(f'SMOKE ERRORS: {errors}')
    sys.exit(1)
else:
    avg = data['summary']['average_score']
    print(f'Smoke OK — avg score: {avg:.3f}')
" 2>&1) || {
    echo "$SMOKE_CHECK" | tee -a "$PROGRESS"
    echo "Smoke test had infrastructure errors. Aborting." | tee -a "$PROGRESS"
    exit 1
}
echo "$SMOKE_CHECK" | tee -a "$PROGRESS"

if [[ "$SMOKE_ONLY" == "1" ]]; then
    echo "SMOKE_ONLY=1 — done." | tee -a "$PROGRESS"
    exit 0
fi

# ── Full sweep ───────────────────────────────────────────────────────
TOTAL=$(python3 -c "
import yaml
from pathlib import Path
count = 0
for env in ['lms', 'patient_portal']:
    for f in sorted(Path(f'breakingweb/tasks/{env}').glob('*.yaml')):
        if f.name.startswith('_'): continue
        count += 1
print(count)
")

echo "" | tee -a "$PROGRESS"
echo "═══════════════════════════════════════════════════════════" | tee -a "$PROGRESS"
echo "  FULL SWEEP: $TOTAL tasks, $WORKERS workers" | tee -a "$PROGRESS"
echo "═══════════════════════════════════════════════════════════" | tee -a "$PROGRESS"
echo "" | tee -a "$PROGRESS"

# Generate per-worker task lists via Python (safe for zsh/bash)
python3 - "$WORKERS" "$RUNDIR" "$MODEL" "$PROVIDER" "$SEED" "$MAX_STEPS" "$TIMEOUT" "$PORT" "$REASONING" "$HARNESS" << 'SPLITEOF'
import sys, yaml, shlex
from pathlib import Path

workers = int(sys.argv[1])
rundir = sys.argv[2]
model, provider, seed = sys.argv[3], sys.argv[4], sys.argv[5]
max_steps, timeout, port = sys.argv[6], sys.argv[7], sys.argv[8]
reasoning, harness = sys.argv[9], sys.argv[10]

diff_order = {"easy": 0, "medium": 1, "hard": 2, "expert": 3, "frontier": 4}
tasks = []
for env in ["lms", "patient_portal"]:
    for f in sorted(Path(f"breakingweb/tasks/{env}").glob("*.yaml")):
        if f.name.startswith("_"): continue
        data = yaml.safe_load(f.read_text())
        tasks.append((diff_order.get(data.get("difficulty", "hard"), 3), data["task_id"]))
tasks.sort()  # easy first so short tasks finish early and free token budget

for w in range(workers):
    worker_tasks = [t[1] for i, t in enumerate(tasks) if i % workers == w]
    script_path = Path(rundir) / f"run_w{w}.sh"
    reasoning_flag = f"--reasoning-effort {reasoning}" if reasoning and reasoning != "none" else ""
    harness_flag = f"--harness {harness}" if harness and harness != "browsergym" else ""
    script_path.write_text(f"""#!/bin/bash
set -a && source .env && set +a
source .venv/bin/activate 2>/dev/null || true
PYTHONUNBUFFERED=1 python -m breakingweb.agent_eval \\
    --model {shlex.quote(model)} \\
    --provider {shlex.quote(provider)} \\
    --api-key "${{OPENAI_API_KEY}}" \\
    --tasks {' '.join(shlex.quote(t) for t in worker_tasks)} \\
    --max-steps {shlex.quote(str(max_steps))} \\
    --timeout {shlex.quote(str(timeout))} \\
    --seed {shlex.quote(str(seed))} \\
    --server-port {shlex.quote(str(port))} \\
    {reasoning_flag} \\
    {harness_flag} \\
    --output {shlex.quote(f'{rundir}/w{w}.json')}
""")
    script_path.chmod(0o755)
    print(f"W{w}: {len(worker_tasks)} tasks")
SPLITEOF

# Scoreboard updater — polls worker logs every 10s
(
    while true; do
        sleep 10
        {
            echo "SCOREBOARD — $MODEL — updated $(date +%H:%M:%S)"
            echo "═════════════════════════════════════════════════"

            total_done=0
            total_pass=0

            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                if [[ -f "$log" ]]; then
                    while IFS= read -r line; do
                        total_done=$((total_done + 1))
                        if echo "$line" | grep -q "PASS"; then
                            total_pass=$((total_pass + 1))
                        fi
                    done < <(grep -E '^\s*\[(PASS|FAIL)\]' "$log" | head -200)
                fi
            done

            echo "  Progress: $total_done / $TOTAL tasks completed"
            if (( total_done > 0 )); then
                echo "  Passed:   $total_pass / $total_done"
            fi
            echo ""

            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                if [[ -f "$log" ]]; then
                    done_w=$(grep -c '^\s*\[PASS\]\|^\s*\[FAIL\]' "$log" 2>/dev/null || echo 0)
                    pass_w=$(grep -c '^\s*\[PASS\]' "$log" 2>/dev/null || echo 0)
                    last=$(grep -oE '\[(lms|pp)_[a-z_0-9]+\]' "$log" | tail -1 || echo "starting")
                    echo "  W$w: $done_w done ($pass_w pass) — $last"
                else
                    echo "  W$w: waiting..."
                fi
            done
            echo ""

            echo "RESULTS SO FAR:"
            echo "─────────────────────────────────────────"
            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                if [[ -f "$log" ]]; then
                    grep -E '^\s*\[(PASS|FAIL)\] score=' "$log" 2>/dev/null | sed 's/^  //' || true
                fi
            done
        } > "$SCOREBOARD.tmp" 2>/dev/null
        mv "$SCOREBOARD.tmp" "$SCOREBOARD" 2>/dev/null || true
    done
) &
SCOREBOARD_PID=$!
trap "kill $CAFF_PID $SCOREBOARD_PID 2>/dev/null; ${SERVER_PID:+kill $SERVER_PID 2>/dev/null;} true" EXIT

# Launch workers
PIDS=()
for ((w=0; w<WORKERS; w++)); do
    WORKER_LOG="$RUNDIR/worker${w}.log"
    if (( w > 0 )); then
        sleep 3  # stagger to smooth initial TPM ramp
    fi
    bash "$RUNDIR/run_w${w}.sh" > "$WORKER_LOG" 2>&1 &
    W_PID=$!
    PIDS+=($W_PID)
    echo "  W$w: PID $W_PID → $WORKER_LOG" | tee -a "$PROGRESS"
done

echo "" | tee -a "$PROGRESS"
echo "All $WORKERS workers launched. PIDs: ${PIDS[*]}" | tee -a "$PROGRESS"
echo "" | tee -a "$PROGRESS"
echo "Monitor:" | tee -a "$PROGRESS"
echo "  tail -f $RUNDIR/worker0.log" | tee -a "$PROGRESS"
echo "  cat $SCOREBOARD" | tee -a "$PROGRESS"
echo "" | tee -a "$PROGRESS"

FAILED=0
for pid in "${PIDS[@]}"; do
    if ! wait "$pid"; then
        ((FAILED++))
    fi
done

if (( FAILED > 0 )); then
    echo "WARNING: $FAILED worker(s) exited with errors" | tee -a "$PROGRESS"
fi

kill $SCOREBOARD_PID 2>/dev/null || true

# ── Merge results ────────────────────────────────────────────────────
python3 - "$RUNDIR" "$MODEL" "$PROVIDER" "$SEED" "$WORKERS" "$MAX_STEPS" "$TIMEOUT" "$REASONING" << 'PYEOF'
import json, glob, sys
from datetime import datetime, timezone
from pathlib import Path

rundir, model, provider = sys.argv[1], sys.argv[2], sys.argv[3]
seed, workers, max_steps = int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
timeout, reasoning = int(sys.argv[7]), sys.argv[8]

files = sorted(glob.glob(f"{rundir}/w[0-9]*.json"))
all_results = []
for f in files:
    try:
        data = json.load(open(f))
        all_results.extend(data.get("results", []))
    except Exception as e:
        print(f"  WARNING: could not read {f}: {e}")

all_results.sort(key=lambda r: r["task_id"])
total = len(all_results)
passed = sum(1 for r in all_results if r["evaluation"].get("success"))
scores = [r["evaluation"].get("score", 0) for r in all_results]
times = [r.get("agent", {}).get("elapsed_seconds", 0) for r in all_results]
steps = [r.get("agent", {}).get("steps", 0) for r in all_results]
errors = [r for r in all_results if "Error" in r["evaluation"].get("reasoning", "")]

# Per-environment breakdown
by_env = {}
for r in all_results:
    env = r["task_id"].split("_")[0] if r["task_id"].startswith("pp_") else r["task_id"].split("_")[0]
    env = "patient_portal" if r["task_id"].startswith("pp_") else "lms"
    by_env.setdefault(env, []).append(r)

env_summary = {}
for env, rs in by_env.items():
    p = sum(1 for r in rs if r["evaluation"].get("success"))
    s = [r["evaluation"].get("score", 0) for r in rs]
    env_summary[env] = {
        "total": len(rs),
        "passed": p,
        "pass_rate": round(p / len(rs), 3) if rs else 0,
        "average_score": round(sum(s) / len(rs), 3) if rs else 0,
    }

output = {
    "benchmark": "BreakingWeb",
    "environments": ["lms", "patient_portal"],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "agent": {"model": model, "provider": provider},
    "config": {
        "seed": seed,
        "workers": workers,
        "max_steps": max_steps,
        "timeout": timeout,
        "reasoning_effort": reasoning,
    },
    "results": all_results,
    "summary": {
        "total_tasks": total,
        "passed": passed,
        "failed": total - passed,
        "errors": len(errors),
        "pass_rate": round(passed / total, 3) if total else 0,
        "average_score": round(sum(scores) / total, 3) if total else 0,
        "median_score": round(sorted(scores)[total // 2], 3) if total else 0,
        "average_steps": round(sum(steps) / total, 1) if total else 0,
        "average_elapsed_seconds": round(sum(times) / total, 1) if total else 0,
        "total_elapsed_seconds": round(sum(times), 1),
        "by_environment": env_summary,
    },
}

final_path = f"{rundir}/results.json"
with open(final_path, "w") as f:
    json.dump(output, f, indent=2)

print()
print("=" * 60)
print(f"FINAL: {passed}/{total} passed  |  avg score: {output['summary']['average_score']:.3f}")
print(f"  pass rate:     {output['summary']['pass_rate']:.1%}")
print(f"  median score:  {output['summary']['median_score']:.3f}")
print(f"  avg steps:     {output['summary']['average_steps']}")
print(f"  avg time:      {output['summary']['average_elapsed_seconds']}s")
print(f"  total time:    {output['summary']['total_elapsed_seconds']:.0f}s")
if errors:
    print(f"  errors:        {len(errors)}")
print()
print("By environment:")
for env, s in env_summary.items():
    print(f"  {env:<20} {s['passed']}/{s['total']} ({s['pass_rate']:.1%})  avg={s['average_score']:.3f}")
print(f"  output:        {final_path}")
print("=" * 60)
print()

print(f"{'STATUS':<6} {'SCORE':>5}  {'STEPS':>5}  {'TIME':>5}  TASK")
print("-" * 60)
for r in all_results:
    s = r["evaluation"].get("score", 0)
    ok = "PASS" if r["evaluation"].get("success") else "FAIL"
    st = r.get("agent", {}).get("steps", 0)
    t = r.get("agent", {}).get("elapsed_seconds", 0)
    err = " [ERROR]" if "Error" in r["evaluation"].get("reasoning", "") else ""
    print(f"{ok:<6} {s:>5.2f}  {st:>5}  {t:>5.0f}s  {r['task_id']}{err}")
PYEOF

# Final scoreboard
{
    echo "FINAL SCOREBOARD — $MODEL — $(date)"
    echo "═════════════════════════════════════════════════"
    python3 -c "
import json
data = json.load(open('$RUNDIR/results.json'))
s = data['summary']
print(f\"  {s['passed']}/{s['total_tasks']} passed | avg: {s['average_score']:.3f} | median: {s['median_score']:.3f}\")
print()
print('By env:')
for env, es in s.get('by_environment', {}).items():
    print(f\"  {env:<20} {es['passed']}/{es['total']} ({es['pass_rate']:.1%})  avg={es['average_score']:.3f}\")
print()
for r in data['results']:
    sc = r['evaluation'].get('score', 0)
    ok = 'PASS' if r['evaluation'].get('success') else 'FAIL'
    st = r.get('agent', {}).get('steps', 0)
    print(f'  {ok} {sc:.2f}  {r[\"task_id\"]}  ({st} steps)')
"
} > "$SCOREBOARD"

echo "" | tee -a "$PROGRESS"
echo "Done. $(date)" | tee -a "$PROGRESS"
echo "Results:    $RUNDIR/results.json" | tee -a "$PROGRESS"
echo "Scoreboard: $SCOREBOARD" | tee -a "$PROGRESS"
echo "Worker logs: $RUNDIR/worker*.log" | tee -a "$PROGRESS"
