#!/usr/bin/env bash
#SBATCH --job-name=stock-sweep
#SBATCH --partition=compsci
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=20G
#SBATCH --time=24:00:00
#SBATCH --output=/usr/xtmp/%u/wab-logs/stock-sweep-%j.out
#SBATCH --error=/usr/xtmp/%u/wab-logs/stock-sweep-%j.err

# Generic stock browser-use sweep template. Pass model + provider + picks
# via env vars. Examples in breakingweb/docs/RUNNING_SWEEPS.md.
#
# Required env vars:
#   MODEL    — model id (provider-specific, e.g. us.anthropic.claude-opus-4-7)
#   PROVIDER — bedrock | anthropic | anthropic_bedrock | openai | openrouter | gemini
#   PICKS    — path to picks JSON
# Optional:
#   OUTNAME      — output dir suffix; defaults to a slug of MODEL_PROVIDER
#   CONCURRENCY  — parallel episodes (default 4)

set -euo pipefail
: "${MODEL:?MODEL env var required (e.g. us.anthropic.claude-opus-4-7)}"
: "${PROVIDER:?PROVIDER env var required (e.g. bedrock)}"
: "${PICKS:?PICKS env var required (path to picks JSON)}"
[ -f "$PICKS" ] || { echo "ERROR: picks file not found: $PICKS"; exit 1; }

CONCURRENCY="${CONCURRENCY:-4}"
SLUG="$(echo "${MODEL}_${PROVIDER}" | tr '/.:' '___' | tr ' ' '_')"
OUTNAME="${OUTNAME:-$SLUG}"

export HF_HOME=/usr/xtmp/$USER/.cache/huggingface
export TORCH_HOME=/usr/xtmp/$USER/.cache/torch
export PIP_CACHE_DIR=/usr/xtmp/$USER/.cache/pip
mkdir -p /usr/xtmp/$USER/wab-logs "$HF_HOME" "$PIP_CACHE_DIR"

ROOT="${BREAKINGWEB_ROOT-${WEBSTRESS_ROOT:-$HOME/projects/BreakingWeb}}"
cd "$ROOT"
source .venv/bin/activate
set -a; source breakingweb/.env; set +a

BACKEND_PORT=$(( 9400 + (SLURM_JOB_ID % 600) ))
N_PICKS=$(python3 -c "import json; print(len(json.load(open('$PICKS'))))")
echo "=== Stock-BU sweep: $MODEL via $PROVIDER × $N_PICKS picks ==="
echo "Job $SLURM_JOB_ID on $(hostname), backend :$BACKEND_PORT"
echo "Picks: $PICKS"
echo "Output: /usr/xtmp/$USER/wab-runs/stock-${OUTNAME}-${SLURM_JOB_ID}"

export BREAKINGWEB_AUTO_BUILD_FRONTENDS=0

python -m uvicorn breakingweb.app:app \
  --host 127.0.0.1 --port "$BACKEND_PORT" --log-level warning \
  > /usr/xtmp/$USER/wab-logs/backend-${SLURM_JOB_ID}.log 2>&1 &
BPID=$!
trap "kill $BPID 2>/dev/null || true" EXIT INT TERM

READY=0
for i in $(seq 1 120); do
  curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 && { READY=1; echo "backend ready after ${i}s"; break; }
  sleep 1
done
[ "$READY" = "0" ] && { echo "ERROR: backend /health never came up"; tail -40 /usr/xtmp/$USER/wab-logs/backend-${SLURM_JOB_ID}.log; exit 1; }

OUT_DIR="/usr/xtmp/$USER/wab-runs/stock-${OUTNAME}-${SLURM_JOB_ID}"

export PYTHONUNBUFFERED=1
# Defaults: --timeout 1200 --step-timeout 240 --max-steps 40 (commit dbc59360)
python -u scripts/run_picks.py \
  --picks "$PICKS" \
  --model "$MODEL" \
  --provider "$PROVIDER" \
  --backend-port "$BACKEND_PORT" \
  --frontend-port "$BACKEND_PORT" \
  --concurrency "$CONCURRENCY" \
  --output-dir "$OUT_DIR"

echo
echo "=== Complete ($(date)) ==="
echo "Results: $OUT_DIR"
