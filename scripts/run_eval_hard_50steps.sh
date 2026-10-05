#!/usr/bin/env bash
# Rerun 20 hard tasks with max-steps 50 (was 25)
set -euo pipefail
cd "$(dirname "$0")/.."
export OPENSSL_CONF="${OPENSSL_CONF:-}"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

TASKS=(
  gmail_board_briefing_prep gmail_compliance_settings_audit
  gmail_action_item_extraction gmail_budget_reconciliation
  gmail_client_handoff gmail_contact_enrichment
  gmail_filter_repair_chain gmail_invoice_verification
  gmail_social_engineering_triage gmail_delegation_handoff
  gmail_cross_team_filter_audit gmail_contract_negotiation_tracker
  gmail_purchase_order_reconciliation gmail_vendor_renewal_decision
  gmail_travel_itinerary_resolution gmail_credential_leak_response
  gmail_contact_audit gmail_workspace_standardization
  gmail_inbox_zero_automation gmail_label_hierarchy_reorg
)

UV_CACHE_DIR=/tmp/uv-cache uv run python -m breakingweb.agent_eval \
  --model gpt-5.4 \
  --provider openai \
  --api-key "${OPENAI_API_KEY:-}" \
  --tasks "${TASKS[@]}" \
  --max-steps 50 \
  --timeout 300 \
  --seed 42 \
  --server-port 8080 \
  --output results/breakingweb/gpt54_hard_50steps.json \
  2>&1 | tee results/breakingweb/gpt54_hard_50steps.log
