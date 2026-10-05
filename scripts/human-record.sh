#!/usr/bin/env bash
# One-liner launcher for annotators doing the BreakingWeb-Human-140 study.
#
# Usage:
#   ./scripts/human-record.sh <annotator> [--env <id>|all]
#
# Examples:
#   ./scripts/human-record.sh P1              # all 7 envs
#   ./scripts/human-record.sh P1 --env booking  # just booking
#
# What it does:
#   1. Validates the annotator name against the assignment YAML.
#   2. Activates the Python venv.
#   3. Launches the FastAPI backend + vite dev servers for all assigned envs.
#   4. Opens the browser to /static/human.html?annotator=<name>.

set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ $# -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  cat <<EOF
Usage:
  ./scripts/human-record.sh <annotator> [--env <id>|all]

<annotator> must be one of: P1, P2, P3, P4,
                            D1, D2, D3, D4
EOF
  exit 1
fi

ANNOTATOR="$1"
shift

ENV_FLAG="all"
while [ $# -gt 0 ]; do
  case "$1" in
    --env)
      if [ $# -lt 2 ]; then
        echo "ERROR: --env requires a value" >&2
        exit 1
      fi
      ENV_FLAG="$2"
      shift 2
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# --- Validate annotator against the assignment YAML ---
KNOWN="P1 P2 P3 P4 D1 D2 D3 D4"
if ! echo " $KNOWN " | grep -q " $ANNOTATOR "; then
  echo "ERROR: unknown annotator '$ANNOTATOR'" >&2
  echo "Must be one of: $KNOWN" >&2
  exit 1
fi

ASSIGN_YAML="$ROOT/breakingweb/human/assignments_v1.yaml"
if [ ! -f "$ASSIGN_YAML" ]; then
  echo "ERROR: missing $ASSIGN_YAML" >&2
  exit 1
fi

# --- Venv ---
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# --- Print summary so the annotator knows what's about to happen ---
if command -v python >/dev/null 2>&1; then
  python - "$ANNOTATOR" <<'PY'
import sys, yaml
from collections import Counter
annotator = sys.argv[1]
with open("breakingweb/human/assignments_v1.yaml") as f:
    data = yaml.safe_load(f)
primary = data.get("condition_assignments") or []
dup = data.get("duplicate_condition_assignments") or []
mine = [a for a in primary + dup if a["annotator"].lower() == annotator.lower()]
if not mine:
    sys.exit(f"No assignments for {annotator}")
envs = Counter(a["env"] for a in mine)
print(f"\n  Annotator:     {annotator}")
print(f"  Assignments:   {len(mine)} task-conditions (primary + duplicate)")
print(f"  Attempts:      {len(mine) * 2} (cold + warm each)")
print(f"  Env portfolio: {dict(envs)}")
print()
PY
fi

BROWSER_URL="http://localhost:${BREAKINGWEB_PORT-${WEBSTRESS_PORT:-8080}}/static/human.html?annotator=${ANNOTATOR}"
echo "  UI will be at:  ${BROWSER_URL}"
echo "  Traces go to:   breakingweb/human/traces/${ANNOTATOR}/"
echo "  Commit + PR:    git add breakingweb/human/traces/${ANNOTATOR}/"
echo

# --- Build --env args for breakingweb.sh ---
SUBARGS=(dev)
if [ "$ENV_FLAG" = "all" ]; then
  SUBARGS+=(--env all)
else
  SUBARGS+=(--env "$ENV_FLAG")
fi

# Delay browser-open until the backend is actually healthy; the inner
# breakingweb.sh already opens /launch, but we want /static/human.html.
(
  sleep 4
  for _ in 1 2 3 4 5; do
    if curl -sf "http://localhost:${BREAKINGWEB_PORT-${WEBSTRESS_PORT:-8080}}/health" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$BROWSER_URL" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$BROWSER_URL" >/dev/null 2>&1 || true
  fi
) &

# Prevent the inner script from launching the default /launch browser window
# since we already open /static/human.html above.
SUBARGS+=(--no-open)
exec ./scripts/breakingweb.sh "${SUBARGS[@]}"
