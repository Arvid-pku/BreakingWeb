#!/usr/bin/env bash
# Stress evaluation: 7 tasks, one degradation variant per primitive, with gpt-5.4
set -euo pipefail
cd "$(dirname "$0")/.."
export OPENSSL_CONF="${OPENSSL_CONF:-}"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

COMMON="--model gpt-5.4 --provider openai --api-key ${OPENAI_API_KEY:-} --max-steps 25 --timeout 180 --seed 42 --server-port 8081"

# One variant per primitive
VARIANTS=(
  "gmail_board_briefing__grounding.yaml"
  "gmail_budget_reconciliation__planning.yaml"
  "gmail_action_item_extraction__state_tracking.yaml"
  "gmail_client_handoff__backtracking.yaml"
  "gmail_compliance_settings__patience.yaml"
  "gmail_contact_enrichment__exploration.yaml"
  "gmail_contact_audit__verification_v3.yaml"
)

RESULTS_DIR="results/breakingweb/stress"
mkdir -p "$RESULTS_DIR"

for variant in "${VARIANTS[@]}"; do
  prim=$(echo "$variant" | sed 's/.*__//; s/\.yaml//')
  echo ""
  echo "================================================================"
  echo "STRESS TEST: $variant ($prim)"
  echo "================================================================"

  UV_CACHE_DIR=/tmp/uv-cache uv run python -m breakingweb.agent_eval \
    $COMMON \
    --degradation "$variant" \
    --output "$RESULTS_DIR/gpt54_stress_${prim}.json" \
    2>&1 | tee "$RESULTS_DIR/gpt54_stress_${prim}.log"
done

echo ""
echo "================================================================"
echo "ALL STRESS TESTS COMPLETE"
echo "================================================================"
