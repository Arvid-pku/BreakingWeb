#!/usr/bin/env bash
# Stress v2: easy tasks (normal=1.0) + high-scoring hard tasks (normal>0.5)
set -euo pipefail
cd "$(dirname "$0")/.."
export OPENSSL_CONF="${OPENSSL_CONF:-}"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

COMMON="--model gpt-5.4 --provider openai --api-key ${OPENAI_API_KEY:-} --max-steps 50 --timeout 300 --seed 42 --server-port 8081"

# Easy task variants (normal score = 1.0, room for delta)
EASY_VARIANTS=(
  "gmail_star_email__patience.yaml"
  "gmail_reply_simple__verification.yaml"
  "gmail_create_label__grounding.yaml"
  "gmail_forward_email__state_tracking.yaml"
  "gmail_delete_spam__exploration.yaml"
  "gmail_search_and_star__planning.yaml"
  "gmail_compose_new__backtracking.yaml"
)

# Existing variants for high-scoring hard tasks (normal score > 0.5)
HIGH_SCORE_VARIANTS=(
  "gmail_compliance_settings__patience.yaml"
  "gmail_budget_reconciliation__planning.yaml"
  "gmail_action_item_extraction__state_tracking.yaml"
  "gmail_invoice_verification__grounding_v2.yaml"
)

RESULTS_DIR="results/breakingweb/stress_v2"
mkdir -p "$RESULTS_DIR"

ALL_VARIANTS=("${EASY_VARIANTS[@]}" "${HIGH_SCORE_VARIANTS[@]}")

for variant in "${ALL_VARIANTS[@]}"; do
  prim=$(echo "$variant" | sed 's/.*__//; s/\.yaml//; s/_v[0-9]*//')
  task=$(echo "$variant" | sed 's/__.*//; s/^gmail_/gmail_/')
  echo ""
  echo "================================================================"
  echo "STRESS: $variant ($prim)"
  echo "================================================================"

  UV_CACHE_DIR=/tmp/uv-cache uv run python -m breakingweb.agent_eval \
    $COMMON \
    --degradation "$variant" \
    --output "$RESULTS_DIR/gpt54_stress_${task}__${prim}.json" \
    2>&1 | tee "$RESULTS_DIR/gpt54_stress_${task}__${prim}.log"
done

echo ""
echo "================================================================"
echo "ALL STRESS V2 TESTS COMPLETE"
echo "================================================================"
