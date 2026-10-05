# Robinhood Task Debugging Procedure

Tool: `scripts/rh_debug.py`  
Principle: **observe** via browser screenshot, **act** via API, **verify** via eval checks.

## Prerequisites

```bash
# Server must be running (restart to pick up YAML changes)
lsof -i :8080 -t | xargs kill 2>/dev/null; sleep 1
python -m breakingweb.app --host 127.0.0.1 --port 8080 &
sleep 3

# Frontend must be built (only after editing React source)
cd breakingweb/environments/robinhood && npx vite build && cd -
```

## Phase 1: Batch Smoke Test

Run the Robinhood task set and/or the RH variants in parallel to catch crashes and vacuous checks:

```bash
python scripts/rh_debug.py batch                # all tasks, 8 workers (default)
python scripts/rh_debug.py batch -w 16          # more workers for faster runs
python scripts/rh_debug.py batch rh_foo rh_bar  # specific tasks only
python scripts/rh_debug.py batch --include-variants
python scripts/rh_debug.py batch --variants-only -w 24
```

This creates a session for each task, runs eval checks, and flags:
- **ERROR**: a check expression crashed (missing method, type error, etc.)
- **VACUOUS**: task scored 1.0 with no agent action (`all()` over empty set)
- **CRASH**: session creation failed (bad seed config, missing builder, etc.)

Fix all errors before proceeding to Phase 2.

## Phase 2: Per-Task Live Testing

For each task (or just the ones that need attention):

### Step 1: Start session + observe

```bash
python scripts/rh_debug.py start rh_check_buying_power
```

This creates the session, screenshots the home page, and prints the a11y tree.
Read the screenshot (`scripts/debug_screenshots/<session_file_stem>_current.png`) to verify the UI renders.

### Step 2: Navigate and observe key pages

```bash
python scripts/rh_debug.py see /stocks/AAPL        # Stock detail
python scripts/rh_debug.py see /orders              # Orders page
python scripts/rh_debug.py see /notifications       # Notifications
python scripts/rh_debug.py see /alerts              # Price alerts
python scripts/rh_debug.py see /account             # Settings
python scripts/rh_debug.py see /options/positions    # Options positions
python scripts/rh_debug.py see /recurring            # Recurring investments
python scripts/rh_debug.py see /transfers            # Transfers
python scripts/rh_debug.py see /tax                  # Tax center
python scripts/rh_debug.py see '/alerts?symbol=AAPL' # Query-string paths also work
```

Check for:
- "Stock not found" errors (missing `must_include` in stock_universe seed)
- Empty pages where data should exist (seed not generating expected state)
- Broken layouts or missing UI elements

### Step 3: Dump server state

```bash
python scripts/rh_debug.py state
```

Fetches all 10 API endpoints in parallel. Verify the seeded state matches expectations:
- Positions exist with correct quantities
- Alerts/watchlists/recurring are seeded as expected
- Options chains/positions exist if needed

### Step 4: Perform task actions via API

Use `act` to call API endpoints as the agent would:

```bash
# Place a market buy order
python scripts/rh_debug.py act orders '{"symbol":"AAPL","side":"buy","order_type":"market","quantity":12}'

# Set a price alert
python scripts/rh_debug.py act alerts '{"symbol":"AAPL","condition":"below","target_price":"175.00"}'

# Create a watchlist
python scripts/rh_debug.py act watchlists '{"name":"My List","symbols":["AAPL","MSFT"]}'

# Deposit funds
python scripts/rh_debug.py act transfers '{"direction":"deposit","amount":"5000","bank_account_id":"bank_1"}'

# Mark notification as read
python scripts/rh_debug.py act notifications/notif_1/read '{}'

# Create recurring investment
python scripts/rh_debug.py act recurring '{"symbol":"VTI","amount":"200","frequency":"weekly"}'

# Cancel an order
python scripts/rh_debug.py act orders/ord_1/cancel '{}'

# Delete a price alert
python scripts/rh_debug.py act alerts/alert_1 '{}' --method DELETE

# Update settings (e.g. enable 2FA)
python scripts/rh_debug.py act settings '{"two_factor_method":"authenticator"}' --method PUT
```

### Step 5: Verify with eval checks

```bash
python scripts/rh_debug.py check
```

Each check shows `>` (pass) or `X` (fail). If a check fails after correct actions:
- The check expression has a bug
- The API response format doesn't match what the check expects
- The state mutation path is wrong

### Step 6: Verify UI reflects changes

```bash
python scripts/rh_debug.py see /orders    # Should show the order you placed
python scripts/rh_debug.py see /           # Should show updated portfolio
```

## Parallel Agent Execution

Multiple agents can test tasks simultaneously. Each agent needs its own session file:

```bash
# Agent 1
RH_SESSION_FILE=/tmp/agent_1.json python scripts/rh_debug.py start rh_check_buying_power
RH_SESSION_FILE=/tmp/agent_1.json python scripts/rh_debug.py act orders '{"symbol":"AAPL",...}'
RH_SESSION_FILE=/tmp/agent_1.json python scripts/rh_debug.py check

# Agent 2 (runs concurrently)
RH_SESSION_FILE=/tmp/agent_2.json python scripts/rh_debug.py start rh_earnings_play_setup
RH_SESSION_FILE=/tmp/agent_2.json python scripts/rh_debug.py act orders '{"symbol":"AAPL",...}'
RH_SESSION_FILE=/tmp/agent_2.json python scripts/rh_debug.py check
```

Sessions are server-side isolated — each `start` creates an independent session with its own state. The `RH_SESSION_FILE` env var just controls where the *client* stores the session ID locally.

## Common Issues Checklist

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| "Stock not found: X" on detail page | `stock_universe` missing `must_include` for X | Add `must_include: [X]` to seed |
| Score 1.0 with no actions | `all(... for x in [])` vacuous truth | Add precondition check or ensure seed overlaps |
| Check crashes with AttributeError | Eval references nonexistent method | Check method exists on RobinhoodState |
| Decimal vs int comparison | `o.quantity == int(...)` | Python Decimal == int works, but verify |
| Negative check penalizes correct behavior | Guard condition fails when state is empty | Add `is not None` guard |
| Empty page in UI | Seed step missing or wrong params | Check seed builder accepts those params |
| API returns 422 | Missing required field in payload | Check endpoint schema in routes/robinhood.py |

## After Fixes

```bash
# Always restart server after editing Python or YAML
lsof -i :8080 -t | xargs kill 2>/dev/null; sleep 1
python -m breakingweb.app --host 127.0.0.1 --port 8080 &
sleep 3

# Re-run the relevant sweep to confirm
python scripts/rh_debug.py batch
python scripts/rh_debug.py batch --variants-only -w 24

# Commit
git add -A && git commit -m "fix(robinhood): ..."
```
