# shellcheck shell=bash
# Shared helpers for LMS/PP/Gmail sweep scripts.
# Source via:  source "$(dirname "$0")/_sweep_common.sh"

# Load .env, verify OPENAI_API_KEY, activate .venv.
# Usage:  sweep_preflight
sweep_preflight() {
    if [[ -f .env ]]; then
        set -a; source .env; set +a
    fi
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
        echo "ERROR: OPENAI_API_KEY not set." >&2
        echo "  Add it to .env or export it:  export OPENAI_API_KEY=sk-..." >&2
        return 1
    fi
    if [[ -d .venv ]]; then
        source .venv/bin/activate
    fi
}

# Kill any existing server on $1=port, then start a fresh uvicorn instance.
# Always restarts to avoid stale sessions from prior runs that accumulate
# in memory and cause OOM/404 failures under parallel load.
# On success, sets SERVER_PID.
# Usage:  sweep_start_server "$PORT" "$PROGRESS"
sweep_start_server() {
    local port="$1"
    local progress="$2"
    SERVER_PID=""

    # lsof hangs on some macOS socket-table configurations — use pkill instead
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
        echo "Killing existing server on port $port..." | tee -a "$progress"
        pkill -f "uvicorn.*breakingweb" 2>/dev/null || true
        sleep 2
        pkill -9 -f "uvicorn.*breakingweb" 2>/dev/null || true
        sleep 1
    fi

    echo "Starting fresh server on port $port..." | tee -a "$progress"
    python -m uvicorn breakingweb.app:app \
        --host 0.0.0.0 --port "$port" --log-level warning &
    SERVER_PID=$!
    local i
    for i in $(seq 1 30); do
        if nc -z 127.0.0.1 "$port" 2>/dev/null; then break; fi
        sleep 1
    done
    if ! nc -z 127.0.0.1 "$port" 2>/dev/null; then
        echo "ERROR: Server failed to start within 30s" | tee -a "$progress"
        return 1
    fi
    echo "Server started (PID $SERVER_PID) after ${i}s" | tee -a "$progress"
}
