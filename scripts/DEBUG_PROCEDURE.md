# Task Debugging Procedure

Tool: `scripts/debug.py`  
Principle: **observe** via browser screenshot, **act** via API, **verify** via eval checks.  
Environments: Gmail, Robinhood (auto-detected from task_id prefix).

## Prerequisites

```bash
# Server must be running (restart to pick up YAML/Python changes)
lsof -i :8080 -t | xargs kill 2>/dev/null; sleep 1
python -m breakingweb.app --host 127.0.0.1 --port 8080 &
sleep 3

# Frontend must be built (only after editing React source)
cd breakingweb/environments/gmail && npx vite build && cd -
cd breakingweb/environments/robinhood && npx vite build && cd -
```

## Phase 1: Batch Smoke Test

Run the task set in parallel to catch crashes and vacuous checks:

```bash
# Auto-discovers all environments with task directories
python scripts/debug.py batch                            # all envs, all tasks, 8 workers
python scripts/debug.py batch -w 16                      # more workers
python scripts/debug.py batch gmail_star_email gmail_compose_new  # specific tasks
python scripts/debug.py batch --include-variants         # tasks + variants
python scripts/debug.py batch --variants-only -w 24      # variants only

# Force a specific environment
python scripts/debug.py --env robinhood batch
python scripts/debug.py --env gmail batch --variants-only
```

Flags:
- **ERROR**: a check expression crashed (missing method, type error, etc.)
- **VACUOUS**: task scored 1.0 with no agent action (`all()` over empty set)
- **CRASH**: session creation failed (bad seed config, missing builder, etc.)

Fix all errors before proceeding to Phase 2.

## Phase 2: Per-Task Live Testing

### Step 1: Start session + observe

```bash
python scripts/debug.py start gmail_compose_new
python scripts/debug.py start rh_check_buying_power      # auto-detects Robinhood
```

This creates the session, screenshots the home page, and prints the a11y tree.  
Read the screenshot: `scripts/debug_screenshots/<env>_session_current.png`

### Step 2: Navigate and observe key pages

**Gmail pages:**
```bash
python scripts/debug.py see /inbox
python scripts/debug.py see /sent
python scripts/debug.py see /archived
python scripts/debug.py see /trash
python scripts/debug.py see /compose
python scripts/debug.py see '/inbox?label=Work'
```

**Robinhood pages:**
```bash
python scripts/debug.py see /stocks/AAPL
python scripts/debug.py see /orders
python scripts/debug.py see /notifications
python scripts/debug.py see /alerts
python scripts/debug.py see /account
python scripts/debug.py see /options/positions
python scripts/debug.py see /recurring
python scripts/debug.py see /transfers
python scripts/debug.py see /tax
```

Check for:
- Empty pages where data should exist (seed not generating expected state)
- Broken layouts or missing UI elements
- "Not found" errors (missing seed data)

### Step 3: Dump server state

```bash
python scripts/debug.py state
```

Fetches all environment-specific endpoints in parallel. Verify seeded state matches expectations.

### Step 4: Perform task actions via API

**Gmail examples:**
```bash
# Send an email
python scripts/debug.py act send '{"to":"alice@company.test","subject":"Hello","body":"Hi Alice"}'

# Star an email
python scripts/debug.py act emails/email_1/star '{}'

# Mark as read
python scripts/debug.py act emails/email_1/read '{"is_read":true}'

# Add label
python scripts/debug.py act emails/email_1/label '{"label":"Work","action":"add"}'

# Archive
python scripts/debug.py act emails/email_1/archive '{}'

# Create label
python scripts/debug.py act labels '{"name":"Urgent","color":"red"}'

# Create filter
python scripts/debug.py act filters '{"criteria":{"from":"boss@company.test"},"action":{"label":"Urgent"}}'

# Delete a label (DELETE method)
python scripts/debug.py act labels/label_1 '{}' --method DELETE

# Update settings (PUT method)
python scripts/debug.py act settings '{"signature":"Best regards"}' --method PUT
```

**Robinhood examples:**
```bash
# Place a market buy order
python scripts/debug.py act orders '{"symbol":"AAPL","side":"buy","order_type":"market","quantity":12}'

# Set a price alert
python scripts/debug.py act alerts '{"symbol":"AAPL","condition":"below","target_price":"175.00"}'

# Create a watchlist
python scripts/debug.py act watchlists '{"name":"My List","symbols":["AAPL","MSFT"]}'

# Cancel an order
python scripts/debug.py act orders/ord_1/cancel '{}'

# Delete a price alert (DELETE method)
python scripts/debug.py act alerts/alert_1 '{}' --method DELETE
```

### Step 5: Verify with eval checks

```bash
python scripts/debug.py check
```

Each check shows `>` (pass) or `X` (fail). If a check fails after correct actions:
- The check expression has a bug
- The API response format doesn't match what the check expects
- The state mutation path is wrong

### Step 6: Verify UI reflects changes

```bash
python scripts/debug.py see /inbox    # Should show updated emails
python scripts/debug.py see /orders   # Should show the order you placed
```

## Parallel Agent Execution

Sessions are server-side isolated. `start` auto-generates a task-scoped session file
(`scripts/.debug_<task_id>.json`) so parallel starts never collide:

```bash
# Agent 1 — session file auto-created at scripts/.debug_gmail_compose_new.json
python scripts/debug.py start gmail_compose_new
python scripts/debug.py -s scripts/.debug_gmail_compose_new.json act send '{"to":"alice@company.test",...}'
python scripts/debug.py -s scripts/.debug_gmail_compose_new.json check

# Agent 2 (runs concurrently) — scripts/.debug_rh_check_buying_power.json
python scripts/debug.py start rh_check_buying_power
python scripts/debug.py -s scripts/.debug_rh_check_buying_power.json check
```

The `-s` flag (or `DEBUG_SESSION_FILE` env var) tells follow-up commands which session to use.
Without `-s`, commands pick the most recently modified session file — convenient for
single-operator use but ambiguous with multiple agents.

For Claude Code subagents, set `DEBUG_SESSION_FILE` in the agent's environment:
```bash
DEBUG_SESSION_FILE=/tmp/agent_1.json python scripts/debug.py start gmail_compose_new
DEBUG_SESSION_FILE=/tmp/agent_1.json python scripts/debug.py check
```

## Common Issues Checklist

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Score 1.0 with no actions | `all(... for x in [])` vacuous truth | Add precondition check or ensure seed overlaps |
| Check crashes with AttributeError | Eval references nonexistent method/field | Verify field exists on state model |
| Negative check penalizes correct behavior | Guard condition fails when state empty | Add `is None or not any(...)` guard |
| Empty page in UI | Seed step missing or wrong params | Check seed builder accepts those params |
| API returns 422 | Missing required field in payload | Check endpoint schema in routes |
| "Stock not found" on detail page | `stock_universe` missing `must_include` | Add `must_include: [X]` to seed |

## After Fixes

```bash
# Always restart server after editing Python or YAML
lsof -i :8080 -t | xargs kill 2>/dev/null; sleep 1
python -m breakingweb.app --host 127.0.0.1 --port 8080 &
sleep 3

# Re-run batch to confirm
python scripts/debug.py batch
python scripts/debug.py batch --variants-only -w 24
```
