#!/usr/bin/env bash
#SBATCH --job-name=pixel-sweep
#SBATCH --partition=compsci
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=10G
#SBATCH --time=24:00:00
#SBATCH --output=/usr/xtmp/%u/wab-logs/pixel-sweep-%j.out
#SBATCH --error=/usr/xtmp/%u/wab-logs/pixel-sweep-%j.err

# Generic pixel-mode (BrowserGym + PixelLLMAgent) sweep template. Pass
# model + provider + picks via env vars. Examples in
# breakingweb/docs/RUNNING_SWEEPS.md.
#
# Per-model viewport is auto-applied:
#   Claude  → 1024 × 768 (Anthropic XGA recommendation)
#   GPT     → 1600 × 900 (OpenAI CUA recommendation)
#   Gemini  → 1280 × 720 (default)
#
# Pixel mode rejects in-process concurrency (Playwright sync API isn't
# thread-safe). Real parallelism: launch as a slurm array job, e.g.
#   sbatch --array=0-7 ... pixel_sweep.sbatch
# Each array task is one shard; output lands in shard_NN/. Merge the
# per-shard summary.json files into a single summary by concatenating the
# `results` arrays (each entry already has its own task_id + cond).
#
# Required env vars:
#   MODEL    — model id (provider-specific)
#   PROVIDER — anthropic | openai | gemini | openrouter | bedrock
#   PICKS    — path to picks JSON
# Optional:
#   OUTNAME — output dir suffix; defaults to a slug of MODEL_PROVIDER

set -euo pipefail
: "${MODEL:?MODEL env var required (e.g. claude-opus-4-7)}"
: "${PROVIDER:?PROVIDER env var required (e.g. anthropic)}"
: "${PICKS:?PICKS env var required (path to picks JSON)}"
[ -f "$PICKS" ] || { echo "ERROR: picks file not found: $PICKS"; exit 1; }

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
echo "=== Pixel-VLM sweep: $MODEL via $PROVIDER × $N_PICKS picks ==="
echo "Job $SLURM_JOB_ID on $(hostname), backend :$BACKEND_PORT"
echo "Picks: $PICKS"
echo "Output: /usr/xtmp/$USER/wab-runs/pixel-${OUTNAME}-${SLURM_JOB_ID}"

# Pixel mode goes through BrowserGym _ensure_server() which requires
# BREAKINGWEB_CONTROLLER_SECRET when an externally-managed server is
# detected (anti-collision guard).
export BREAKINGWEB_CONTROLLER_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
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

OUT_DIR="/usr/xtmp/$USER/wab-runs/pixel-${OUTNAME}-${SLURM_JOB_ID}"

export PYTHONUNBUFFERED=1
# Slurm array → shard plumbing. SLURM_ARRAY_TASK_ID is automatically set
# when launched as `sbatch --array=0-N`; pixel_run_picks already reads it
# as the default for --shard-id, so we just need to pass --shard-of when
# arrayed.
SHARD_ARGS=""
if [ -n "${SLURM_ARRAY_TASK_COUNT:-}" ]; then
  SHARD_ARGS="--shard-of $SLURM_ARRAY_TASK_COUNT --shard-id $SLURM_ARRAY_TASK_ID"
  echo "Sharding: this is shard $SLURM_ARRAY_TASK_ID of $SLURM_ARRAY_TASK_COUNT"
fi

# Defaults: --timeout 1200 --max-steps 60 (commit dbc59360)
python -u scripts/pixel_run_picks.py \
  --picks "$PICKS" \
  --model "$MODEL" \
  --provider "$PROVIDER" \
  --backend-port "$BACKEND_PORT" \
  --output-dir "$OUT_DIR" \
  $SHARD_ARGS

echo
echo "=== Complete ($(date)) ==="
echo "Results: $OUT_DIR"
