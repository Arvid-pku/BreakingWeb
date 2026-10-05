#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Gmail benchmark sweep: gpt-5.4 against all 80 tasks
#
# Features:
#   - caffeinate (prevents sleep during run)
#   - 3-task smoke test before full sweep
#   - parallel workers (default: 3) on same server
#   - rate-limit-safe spacing between workers
#   - live progress file you can tail from another terminal
#   - auto-merges partial results into final JSON with trajectories
#
# Usage:
#   ./scripts/run_gmail_sweep.sh                    # defaults
#   WORKERS=4 ./scripts/run_gmail_sweep.sh          # 4 parallel
#   SMOKE_ONLY=1 ./scripts/run_gmail_sweep.sh       # smoke test only
#   MODEL=gpt-4o ./scripts/run_gmail_sweep.sh       # different model
#
# Monitor progress (from another terminal):
#   tail -f results/breakingweb/<run_tag>_progress.log
#   watch -n5 cat results/breakingweb/<run_tag>_scoreboard.txt
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

# ── Config ───────────────────────────────────────────────────────────
MODEL="${MODEL:-gpt-5.4}"
PROVIDER="${PROVIDER:-openai}"
WORKERS="${WORKERS:-3}"
PORT="${PORT:-8080}"
SEED="${SEED:-42}"
MAX_STEPS="${MAX_STEPS:-30}"
TIMEOUT="${TIMEOUT:-300}"
SMOKE_ONLY="${SMOKE_ONLY:-0}"
REASONING="${REASONING:-medium}"
HARNESS="${HARNESS:-browsergym}"
OUTDIR="results/breakingweb"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_TAG="${MODEL//\//_}_gmail_${TIMESTAMP}"
RUNDIR="$OUTDIR/$RUN_TAG"
PROGRESS="$RUNDIR/progress.log"
SCOREBOARD="$RUNDIR/scoreboard.txt"

# ── Pre-flight ───────────────────────────────────────────────────────
if [[ -f .env ]]; then
    set -a; source .env; set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "ERROR: OPENAI_API_KEY not set."
    echo "  Add it to .env or export it:  export OPENAI_API_KEY=sk-..."
    exit 1
fi

if [[ -d .venv ]]; then
    source .venv/bin/activate
fi

mkdir -p "$RUNDIR"

# Initialize progress file
cat > "$PROGRESS" <<EOF
═══════════════════════════════════════════════════════════
  Gmail Benchmark Sweep
  Model: $MODEL | Workers: $WORKERS | Seed: $SEED
  Reasoning: $REASONING
  Started: $(date)

  Monitor:  tail -f $PROGRESS
  Scores:   watch -n5 cat $SCOREBOARD
═══════════════════════════════════════════════════════════

EOF

# Initialize scoreboard
echo "SCOREBOARD — $MODEL — $(date +%H:%M:%S)" > "$SCOREBOARD"
echo "─────────────────────────────────────────" >> "$SCOREBOARD"
echo "(waiting for results...)" >> "$SCOREBOARD"

echo "═══════════════════════════════════════════════════════════"
echo "  Gmail Benchmark Sweep"
echo "  Model: $MODEL | Workers: $WORKERS | Seed: $SEED"
echo "  Reasoning: $REASONING"
echo "  Run dir: $RUNDIR"
echo ""
echo "  Monitor progress from another terminal:"
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
if ! lsof -i ":$PORT" -sTCP:LISTEN &>/dev/null; then
    echo "Starting server on port $PORT..." | tee -a "$PROGRESS"
    python -m uvicorn breakingweb.app:app \
        --host 0.0.0.0 --port "$PORT" \
        --log-level warning &
    SERVER_PID=$!
    trap "kill $CAFF_PID $SERVER_PID 2>/dev/null" EXIT
    sleep 4
    if ! lsof -i ":$PORT" -sTCP:LISTEN &>/dev/null; then
        echo "ERROR: Server failed to start" | tee -a "$PROGRESS"
        exit 1
    fi
    echo "Server started (PID $SERVER_PID)" | tee -a "$PROGRESS"
else
    echo "Server already running on port $PORT" | tee -a "$PROGRESS"
fi

# ── Smoke test ───────────────────────────────────────────────────────
SMOKE_TASKS=(gmail_star_email gmail_reply_simple gmail_compose_new)
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
    --timeout 120 \
    --seed "$SEED" \
    --server-port "$PORT" \
    $REASONING_FLAG \
    $HARNESS_FLAG \
    --output "$SMOKE_OUT" \
    2>&1 | tee -a "$PROGRESS"

# Check smoke results
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
# Use Python for ALL task splitting to avoid bash/zsh array incompatibilities.
# Generate per-worker launcher scripts that have task lists baked in.

TOTAL=$(python3 -c "
import yaml
from pathlib import Path
count = 0
for f in sorted(Path('breakingweb/tasks/gmail').glob('*.yaml')):
    if f.name.startswith('_'): continue
    count += 1
print(count)
")

echo "" | tee -a "$PROGRESS"
echo "═══════════════════════════════════════════════════════════" | tee -a "$PROGRESS"
echo "  FULL SWEEP: $TOTAL tasks, $WORKERS workers" | tee -a "$PROGRESS"
echo "═══════════════════════════════════════════════════════════" | tee -a "$PROGRESS"
echo "" | tee -a "$PROGRESS"

# Generate per-worker task lists via Python (zsh/bash safe)
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
for f in sorted(Path("breakingweb/tasks/gmail").glob("*.yaml")):
    if f.name.startswith("_"): continue
    data = yaml.safe_load(f.read_text())
    tasks.append((diff_order.get(data.get("difficulty", "hard"), 3), data["task_id"]))
tasks.sort()  # easy first

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

# Background scoreboard updater — polls worker logs every 10s
(
    while true; do
        sleep 10
        {
            echo "SCOREBOARD — $MODEL — updated $(date +%H:%M:%S)"
            echo "═════════════════════════════════════════════════"

            total_done=0
            total_pass=0
            total_score=0

            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                if [[ -f "$log" ]]; then
                    # Extract completed task results
                    while IFS= read -r line; do
                        total_done=$((total_done + 1))
                        if echo "$line" | grep -q "PASS"; then
                            total_pass=$((total_pass + 1))
                        fi
                    done < <(grep -E '^\s*\[(PASS|FAIL)\]' "$log" | head -100)
                fi
            done

            echo "  Progress: $total_done / $TOTAL tasks completed"
            if (( total_done > 0 )); then
                echo "  Passed:   $total_pass / $total_done"
            fi
            echo ""

            # Show per-worker status
            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                if [[ -f "$log" ]]; then
                    done_w=$(grep -c '^\s*\[PASS\]\|^\s*\[FAIL\]' "$log" 2>/dev/null || echo 0)
                    pass_w=$(grep -c '^\s*\[PASS\]' "$log" 2>/dev/null || echo 0)
                    last=$(grep -oP '\[gmail_\w+\]' "$log" | tail -1 || echo "starting")
                    echo "  W$w: $done_w done ($pass_w pass) — $last"
                else
                    echo "  W$w: waiting..."
                fi
            done
            echo ""

            # Show individual results so far
            echo "RESULTS SO FAR:"
            echo "─────────────────────────────────────────"
            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                if [[ -f "$log" ]]; then
                    grep -E '^\s*\[(PASS|FAIL)\] score=' "$log" 2>/dev/null | \
                        sed 's/^  //' || true
                fi
            done
        } > "$SCOREBOARD.tmp" 2>/dev/null
        mv "$SCOREBOARD.tmp" "$SCOREBOARD" 2>/dev/null || true
    done
) &
SCOREBOARD_PID=$!
trap "kill $CAFF_PID $SCOREBOARD_PID 2>/dev/null; ${SERVER_PID:+kill $SERVER_PID 2>/dev/null;} true" EXIT

# Launch workers using generated scripts (no shell array indexing)
PIDS=()
for ((w=0; w<WORKERS; w++)); do
    WORKER_LOG="$RUNDIR/worker${w}.log"

    # Stagger start by 3s per worker
    if (( w > 0 )); then
        sleep 3
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
echo "  tail -f $RUNDIR/worker0.log     # follow worker 0" | tee -a "$PROGRESS"
echo "  cat $SCOREBOARD                 # live scoreboard" | tee -a "$PROGRESS"
echo "" | tee -a "$PROGRESS"

# Wait for all workers, stream their output to progress
FAILED=0
for pid in "${PIDS[@]}"; do
    if ! wait "$pid"; then
        ((FAILED++))
    fi
done

if (( FAILED > 0 )); then
    echo "WARNING: $FAILED worker(s) exited with errors" | tee -a "$PROGRESS"
fi

# Kill scoreboard updater
kill $SCOREBOARD_PID 2>/dev/null || true

# ── Merge results ────────────────────────────────────────────────────
FINAL_OUT="$RUNDIR/results.json"

python3 - "$RUNDIR" << 'PYEOF'
import json, glob, sys
from datetime import datetime, timezone
from pathlib import Path

rundir = sys.argv[1] if len(sys.argv) > 1 else "RUNDIR"
files = sorted(glob.glob(f"{rundir}/w[0-9]*.json"))
all_results = []
for f in files:
    try:
        data = json.load(open(f))
        all_results.extend(data.get("results", []))
    except Exception as e:
        print(f"  WARNING: Could not read {f}: {e}")

all_results.sort(key=lambda r: r["task_id"])
total = len(all_results)
passed = sum(1 for r in all_results if r["evaluation"].get("success"))
scores = [r["evaluation"].get("score", 0) for r in all_results]
times = [r.get("agent", {}).get("elapsed_seconds", 0) for r in all_results]
steps = [r.get("agent", {}).get("steps", 0) for r in all_results]
errors = [r for r in all_results if "Error" in r["evaluation"].get("reasoning", "")]

output = {
    "benchmark": "BreakingWeb",
    "environment": "gmail",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "agent": {"model": "PLACEHOLDER_MODEL", "provider": "PLACEHOLDER_PROVIDER"},
    "config": {"seed": 42, "workers": len(files)},
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
    },
}

final_path = f"{rundir}/results.json"
with open(final_path, "w") as f:
    json.dump(output, f, indent=2)

# Print report
print()
print("=" * 60)
print(f"FINAL RESULTS: {passed}/{total} passed  |  avg score: {output['summary']['average_score']:.3f}")
print(f"  pass rate:     {output['summary']['pass_rate']:.1%}")
print(f"  median score:  {output['summary']['median_score']:.3f}")
print(f"  avg steps:     {output['summary']['average_steps']}")
print(f"  avg time:      {output['summary']['average_elapsed_seconds']}s")
print(f"  total time:    {output['summary']['total_elapsed_seconds']:.0f}s")
if errors:
    print(f"  errors:        {len(errors)}")
print(f"  output:        {final_path}")
print("=" * 60)
print()

# Per-task table
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
RUNDIR_ESC="$RUNDIR" python3 -c "
import json, sys, os
rundir = os.environ['RUNDIR_ESC']
# Fix placeholders in merged output
path = f'{rundir}/results.json'
data = json.load(open(path))
data['agent'] = {'model': '$MODEL', 'provider': '$PROVIDER'}
data['config'] = {'seed': $SEED, 'workers': $WORKERS, 'max_steps': $MAX_STEPS, 'timeout': $TIMEOUT, 'reasoning_effort': '$REASONING'}
json.dump(data, open(path, 'w'), indent=2)
" "$RUNDIR"

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
