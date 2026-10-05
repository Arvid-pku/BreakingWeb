#!/usr/bin/env bash
# Normal (standard) evaluation: 30 tasks with gpt-5.4
set -euo pipefail
cd "$(dirname "$0")/.."
export OPENSSL_CONF="${OPENSSL_CONF:-}"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

TASKS=(
  gmail_star_email gmail_reply_simple gmail_create_label gmail_forward_email
  gmail_delete_spam gmail_search_and_star gmail_mark_all_read gmail_update_contact
  gmail_change_setting gmail_compose_new
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
  --max-steps 25 \
  --timeout 180 \
  --seed 42 \
  --server-port 8080 \
  --output results/breakingweb/gpt54_normal_30tasks.json \
  2>&1 | tee results/breakingweb/gpt54_normal_30tasks.log
