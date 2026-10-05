#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# LMS + Patient Portal FULL sweep — baseline + all degradation variants
#
# Runs all 135 base tasks + all 136 LMS/PP degradation variants
# (271 work items total) via the browser-use harness with N parallel
# workers on a single shared FastAPI server.
#
# Usage:
#   ./scripts/run_lms_pp_full_sweep.sh                 # defaults (gpt-5, 8 workers)
#   WORKERS=10 ./scripts/run_lms_pp_full_sweep.sh      # push concurrency
#   MODEL=gpt-5.4 ./scripts/run_lms_pp_full_sweep.sh   # different model
#   BASELINE_ONLY=1 ./...                              # skip degradations
#   DEGRADATIONS_ONLY=1 ./...                          # skip baseline
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_sweep_common.sh
source "$(dirname "$0")/_sweep_common.sh"

MODEL="${MODEL:-gpt-5}"
PROVIDER="${PROVIDER:-openai}"
WORKERS="${WORKERS:-8}"
PORT="${PORT:-8080}"
SEED="${SEED:-42}"
MAX_STEPS="${MAX_STEPS:-30}"
TIMEOUT="${TIMEOUT:-300}"
REASONING="${REASONING:-medium}"
HARNESS="${HARNESS:-browser-use}"
BASELINE_ONLY="${BASELINE_ONLY:-0}"
DEGRADATIONS_ONLY="${DEGRADATIONS_ONLY:-0}"
OUTDIR="results/breakingweb"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_TAG="${MODEL//\//_}_lms_pp_full_${TIMESTAMP}"
RUNDIR="$OUTDIR/$RUN_TAG"
PROGRESS="$RUNDIR/progress.log"
SCOREBOARD="$RUNDIR/scoreboard.txt"

sweep_preflight

mkdir -p "$RUNDIR"

cat > "$PROGRESS" <<EOF
═══════════════════════════════════════════════════════════
  LMS + PP FULL Sweep (baseline + degradations)
  Model: $MODEL | Workers: $WORKERS | Harness: $HARNESS
  Reasoning: $REASONING | Seed: $SEED
  Started: $(date)
═══════════════════════════════════════════════════════════

EOF
echo "SCOREBOARD — $MODEL — $(date +%H:%M:%S)" > "$SCOREBOARD"
echo "(waiting for results...)" >> "$SCOREBOARD"

echo "═══════════════════════════════════════════════════════════"
echo "  LMS + PP FULL Sweep (baseline + degradations)"
echo "  Model: $MODEL | Workers: $WORKERS | Harness: $HARNESS"
echo "  Run dir: $RUNDIR"
echo "  Monitor: tail -f $PROGRESS"
echo "           cat $SCOREBOARD"
echo "═══════════════════════════════════════════════════════════"

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

# ── Build work list: tasks + variants ────────────────────────────────
python3 - "$WORKERS" "$RUNDIR" "$MODEL" "$PROVIDER" "$SEED" "$MAX_STEPS" "$TIMEOUT" "$PORT" "$REASONING" "$HARNESS" "$BASELINE_ONLY" "$DEGRADATIONS_ONLY" << 'PYSPLIT'
import sys, yaml, shlex
from pathlib import Path

workers = int(sys.argv[1])
rundir = sys.argv[2]
model, provider, seed = sys.argv[3], sys.argv[4], sys.argv[5]
max_steps, timeout, port = sys.argv[6], sys.argv[7], sys.argv[8]
reasoning, harness = sys.argv[9], sys.argv[10]
baseline_only = sys.argv[11] == "1"
degradations_only = sys.argv[12] == "1"

diff_order = {"easy": 0, "medium": 1, "hard": 2, "expert": 3, "frontier": 4}

# Collect base tasks
base_tasks = []
if not degradations_only:
    for env in ["lms", "patient_portal"]:
        for f in sorted(Path(f"breakingweb/tasks/{env}").glob("*.yaml")):
            if f.name.startswith("_"): continue
            data = yaml.safe_load(f.read_text())
            base_tasks.append((
                diff_order.get(data.get("difficulty", "hard"), 3),
                "task",
                data["task_id"],
                None,  # no variant path
            ))

# Collect LMS/PP variants
variants = []
if not baseline_only:
    vdir = Path("breakingweb/injector/variants")
    for f in sorted(vdir.glob("*.yaml")):
        if not (f.name.startswith("lms_") or f.name.startswith("pp_")):
            continue
        try:
            v = yaml.safe_load(f.read_text())
        except Exception:
            continue
        base_id = v.get("base_task_id", "")
        # Difficulty of the base task
        base_env = "lms" if base_id.startswith("lms_") else "patient_portal"
        base_path = Path(f"breakingweb/tasks/{base_env}/{base_id}.yaml")
        base_diff = "hard"
        if base_path.exists():
            base_diff = yaml.safe_load(base_path.read_text()).get("difficulty", "hard")
        variants.append((
            diff_order.get(base_diff, 3),
            "variant",
            base_id,
            f.name,
        ))

# Partition round-robin by sorted difficulty
all_items = sorted(base_tasks + variants)
print(f"Total work items: {len(all_items)} ({len(base_tasks)} base tasks + {len(variants)} variants)")

for w in range(workers):
    w_items = [it for i, it in enumerate(all_items) if i % workers == w]
    # Build the command lines
    cmds = []
    reasoning_flag = f"--reasoning-effort {reasoning}" if reasoning and reasoning != "none" else ""
    harness_flag = f"--harness {harness}" if harness and harness != "browsergym" else ""
    for idx, (_, kind, task_id, variant_name) in enumerate(w_items):
        out = f"{rundir}/w{w}_item{idx:03d}.json"
        if kind == "task":
            cmds.append(
                f"PYTHONUNBUFFERED=1 python -m breakingweb.agent_eval "
                f"--model {shlex.quote(model)} --provider {shlex.quote(provider)} "
                f"--api-key \"${{OPENAI_API_KEY}}\" "
                f"--tasks {shlex.quote(task_id)} "
                f"--max-steps {max_steps} --timeout {timeout} "
                f"--seed {seed} --server-port {port} "
                f"{reasoning_flag} {harness_flag} "
                f"--output {shlex.quote(out)}"
            )
        else:  # variant
            cmds.append(
                f"PYTHONUNBUFFERED=1 python -m breakingweb.agent_eval "
                f"--model {shlex.quote(model)} --provider {shlex.quote(provider)} "
                f"--api-key \"${{OPENAI_API_KEY}}\" "
                f"--degradation {shlex.quote(variant_name)} "
                f"--max-steps {max_steps} --timeout {timeout} "
                f"--seed {seed} --server-port {port} "
                f"{reasoning_flag} {harness_flag} "
                f"--output {shlex.quote(out)}"
            )
    script_path = Path(rundir) / f"run_w{w}.sh"
    body = "#!/bin/bash\nset -a && source .env && set +a\nsource .venv/bin/activate 2>/dev/null || true\n\n"
    for cmd in cmds:
        body += cmd + " || true\n"
    script_path.write_text(body)
    script_path.chmod(0o755)
    n_task = sum(1 for it in w_items if it[1] == "task")
    n_var = sum(1 for it in w_items if it[1] == "variant")
    print(f"W{w}: {n_task} tasks + {n_var} variants = {len(w_items)}")
PYSPLIT

TOTAL=$(ls "$RUNDIR"/run_w*.sh | xargs grep -c "^PYTHONUNBUFFERED" | awk -F: '{s+=$2} END {print s}')
echo "" | tee -a "$PROGRESS"
echo "═══════════════════════════════════════════════════════════" | tee -a "$PROGRESS"
echo "  $TOTAL total work items across $WORKERS workers" | tee -a "$PROGRESS"
echo "═══════════════════════════════════════════════════════════" | tee -a "$PROGRESS"

# ── Scoreboard updater (polls worker logs every 15s) ────────────────
(
    while true; do
        sleep 15
        {
            echo "SCOREBOARD — $MODEL — $(date +%H:%M:%S)"
            echo "═════════════════════════════════════════════════"
            total_done=0; total_pass=0
            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                [[ -f "$log" ]] || continue
                d=$(grep -cE '^\s*\[(PASS|FAIL)\] score=' "$log" 2>/dev/null || echo 0)
                p=$(grep -cE '^\s*\[PASS\] score=' "$log" 2>/dev/null || echo 0)
                total_done=$((total_done + d))
                total_pass=$((total_pass + p))
            done
            pct=0
            if (( TOTAL > 0 )); then pct=$(( 100 * total_done / TOTAL )); fi
            echo "  Progress: $total_done / $TOTAL  ($pct%)"
            if (( total_done > 0 )); then
                echo "  Passed:   $total_pass / $total_done  ($((100 * total_pass / total_done))%)"
            fi
            echo ""
            for ((w=0; w<WORKERS; w++)); do
                log="$RUNDIR/worker${w}.log"
                [[ -f "$log" ]] || { echo "  W$w: waiting..."; continue; }
                d=$(grep -cE '^\s*\[(PASS|FAIL)\] score=' "$log" 2>/dev/null || echo 0)
                p=$(grep -cE '^\s*\[PASS\] score=' "$log" 2>/dev/null || echo 0)
                last=$(grep -oE '\[(lms|pp)_[a-z_0-9]+\](\s\(|$)' "$log" | tail -1 | sed 's/[][ (]//g' || true)
                [[ -z "$last" ]] && last="starting"
                echo "  W$w: $d done ($p pass) — $last"
            done
        } > "$SCOREBOARD.tmp" 2>/dev/null
        mv "$SCOREBOARD.tmp" "$SCOREBOARD" 2>/dev/null || true
    done
) &
SCOREBOARD_PID=$!
trap "kill $CAFF_PID $SCOREBOARD_PID 2>/dev/null; ${SERVER_PID:+kill $SERVER_PID 2>/dev/null;} true" EXIT

# ── Launch workers ──────────────────────────────────────────────────
PIDS=()
for ((w=0; w<WORKERS; w++)); do
    WORKER_LOG="$RUNDIR/worker${w}.log"
    (( w > 0 )) && sleep 3
    bash "$RUNDIR/run_w${w}.sh" > "$WORKER_LOG" 2>&1 &
    W_PID=$!
    PIDS+=($W_PID)
    echo "  W$w: PID $W_PID → $WORKER_LOG" | tee -a "$PROGRESS"
done
echo "" | tee -a "$PROGRESS"
echo "All $WORKERS workers launched. PIDs: ${PIDS[*]}" | tee -a "$PROGRESS"

FAILED=0
for pid in "${PIDS[@]}"; do
    wait "$pid" || ((FAILED++))
done
kill $SCOREBOARD_PID 2>/dev/null || true

# ── Merge per-item JSONs ────────────────────────────────────────────
python3 - "$RUNDIR" "$MODEL" "$PROVIDER" "$SEED" "$WORKERS" "$MAX_STEPS" "$TIMEOUT" "$REASONING" << 'PYMERGE'
import json, glob, sys
from datetime import datetime, timezone
from pathlib import Path

rundir, model, provider = sys.argv[1], sys.argv[2], sys.argv[3]
seed, workers = int(sys.argv[4]), int(sys.argv[5])
max_steps, timeout = int(sys.argv[6]), int(sys.argv[7])
reasoning = sys.argv[8]

files = sorted(glob.glob(f"{rundir}/w*_item*.json"))
all_results = []
for f in files:
    try:
        data = json.load(open(f))
        all_results.extend(data.get("results", []))
    except Exception as e:
        print(f"WARN: {f}: {e}")

# Deduplicate: (task_id, variant_id) is the key
def key(r):
    deg = r.get("degradation") or {}
    return (r.get("task_id", ""), deg.get("variant_id") if deg else "")

seen = {}
for r in all_results:
    seen[key(r)] = r
all_results = list(seen.values())
all_results.sort(key=lambda r: (r.get("task_id", ""), (r.get("degradation") or {}).get("variant_id", "")))

total = len(all_results)
passed = sum(1 for r in all_results if r["evaluation"].get("success"))
scores = [r["evaluation"].get("score", 0) for r in all_results]

# Split baseline vs degradation
base_results = [r for r in all_results if not r.get("degradation")]
deg_results = [r for r in all_results if r.get("degradation")]

def _summary(rs):
    if not rs: return {}
    p = sum(1 for r in rs if r["evaluation"].get("success"))
    s = [r["evaluation"].get("score", 0) for r in rs]
    return {
        "total": len(rs),
        "passed": p,
        "pass_rate": round(p / len(rs), 3),
        "average_score": round(sum(s) / len(rs), 3),
    }

# Per-env breakdown
by_env_base = {}
for r in base_results:
    env = "patient_portal" if r["task_id"].startswith("pp_") else "lms"
    by_env_base.setdefault(env, []).append(r)
by_env_deg = {}
for r in deg_results:
    env = "patient_portal" if r["task_id"].startswith("pp_") else "lms"
    by_env_deg.setdefault(env, []).append(r)

output = {
    "benchmark": "BreakingWeb (LMS+PP full: baseline + degradations)",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "agent": {"model": model, "provider": provider},
    "config": {"seed": seed, "workers": workers, "max_steps": max_steps,
               "timeout": timeout, "reasoning_effort": reasoning},
    "results": all_results,
    "summary": {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0,
        "average_score": round(sum(scores) / total, 3) if total else 0,
        "baseline": _summary(base_results),
        "degradation": _summary(deg_results),
        "baseline_by_env": {env: _summary(rs) for env, rs in by_env_base.items()},
        "degradation_by_env": {env: _summary(rs) for env, rs in by_env_deg.items()},
    },
}
final = f"{rundir}/results.json"
with open(final, "w") as f: json.dump(output, f, indent=2)

print("=" * 60)
print(f"FINAL: {passed}/{total} passed | avg {output['summary']['average_score']:.3f}")
for label, rs in [("BASELINE", base_results), ("DEGRADATIONS", deg_results)]:
    if not rs: continue
    p = sum(1 for r in rs if r["evaluation"].get("success"))
    s = [r["evaluation"].get("score", 0) for r in rs]
    print(f"  {label:<14} {p}/{len(rs)}  avg={sum(s)/len(rs):.3f}")
for label, mp in [("  baseline/env", by_env_base), ("  degradation/env", by_env_deg)]:
    for env, rs in mp.items():
        p = sum(1 for r in rs if r["evaluation"].get("success"))
        s = [r["evaluation"].get("score", 0) for r in rs]
        print(f"  {label} {env:<16} {p}/{len(rs)}  avg={sum(s)/len(rs):.3f}")
print(f"  output: {final}")
print("=" * 60)
PYMERGE

{
    echo "FINAL SCOREBOARD — $MODEL — $(date)"
    echo "═════════════════════════════════════════════════"
    python3 -c "
import json
d = json.load(open('$RUNDIR/results.json'))
s = d['summary']
print(f\"  {s['passed']}/{s['total']} passed | avg: {s['average_score']:.3f}\")
print()
for label, key in [('Baseline', 'baseline'), ('Degradations', 'degradation')]:
    b = s.get(key, {})
    if b:
        print(f\"  {label:<14} {b['passed']}/{b['total']} ({b['pass_rate']:.1%}) avg={b['average_score']:.3f}\")
print()
print('Baseline by env:')
for env, es in s.get('baseline_by_env', {}).items():
    print(f\"  {env:<20} {es['passed']}/{es['total']} ({es['pass_rate']:.1%}) avg={es['average_score']:.3f}\")
print()
print('Degradation by env:')
for env, es in s.get('degradation_by_env', {}).items():
    print(f\"  {env:<20} {es['passed']}/{es['total']} ({es['pass_rate']:.1%}) avg={es['average_score']:.3f}\")
print()
for r in d['results']:
    sc = r['evaluation'].get('score', 0)
    ok = 'PASS' if r['evaluation'].get('success') else 'FAIL'
    vid = (r.get('degradation') or {}).get('variant_id', '')
    label = f\"{r['task_id']}/{vid}\" if vid else r['task_id']
    st = r.get('agent', {}).get('steps', 0)
    print(f'  {ok} {sc:.2f}  {label}  ({st} steps)')
"
} > "$SCOREBOARD"

(( FAILED > 0 )) && echo "WARNING: $FAILED worker(s) exited with errors" | tee -a "$PROGRESS"
echo "" | tee -a "$PROGRESS"
echo "Done. $(date)" | tee -a "$PROGRESS"
echo "Results:    $RUNDIR/results.json" | tee -a "$PROGRESS"
echo "Scoreboard: $SCOREBOARD" | tee -a "$PROGRESS"
