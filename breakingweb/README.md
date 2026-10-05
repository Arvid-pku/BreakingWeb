# BreakingWeb

BreakingWeb constructs challenging browser-use tasks through controlled, recoverable environment interventions. A clean/intervention pair preserves the user instruction, latent target, and backend success criterion while changing seeded content, server state, network responses, or client-side interaction. A variant's primary cognitive-primitive label describes the recovery behavior it primarily demands; several primitives can contribute to the same recovery.

This checkout contains the active benchmark runtime, 519 base tasks, 535 intervention variants, evaluator stack, trajectory tooling, and React frontends for the seven environments exposed by `manifest.json`. The paper reports a 519-pair evaluation selection.

Task definitions live under `tasks/<env>/`, benchmark frontends live under `environments/<env>/`, and the FastAPI backend mounts environment APIs under `/api/env/<env>`.

## Current Scope

- `manifest.json` defines benchmark-level metadata and the exposed environments.
- `tasks/<env>/*.yaml` defines task instructions, seeded targets, and evaluation checks per environment.
- `injector/variants/*.yaml` defines environment interventions annotated by their primary recovery demand.
- `backend/`, `browsergym_task.py`, `browseruse_eval.py`, and `agent_eval.py` provide runtime, harness integration, and evaluation flow.

## Evaluation Model

Current tasks are primarily outcome-validated:

- Success criteria are expressed as `canonical_diff` blocks in each task YAML — declarative `create`/`update`/`delete`/`invariant` entries plus optional `constraints` and `named_invariants`. The evaluator (`eval_core/`) computes the state diff between initial and final snapshots and matches it against the canonical diff via augmenting-path bipartite matching for bijections.
- Selected tasks can additionally require client-side `benchmark_state` evidence when the interaction itself matters. For example, `gmail_search_and_star` requires a recorded search event.
- The benchmark is therefore not a general DOM-evidence benchmark. It is a state-grounded interaction benchmark with optional client-event checks where needed.

## Task Authoring

Task definitions specify public instructions, seeded state, positive obligations, and protected-state invariants. Validate new tasks against the schema and evaluator tests below.

Core implementation and validation files:

- `tasks/_schema.py` — task YAML pydantic schema
- `tasks/canonical_diff.py` — `canonical_diff` block grammar
- `eval_core/` — canonical_diff evaluator (orchestrator, matcher, predicates, safe_eval, diff, access, types)
- `backend/seeders/`
- `tasks/_evaluator.py` — thin shim that delegates to `eval_core.evaluate`
- `tests/test_task_linter.py`
- `tests/test_scoring_audit.py`
- `tests/test_gmail_seed_stability.py`


## Testing

Python benchmark and integrity suite:

```bash
python -m pytest -q tests
```

If you run tests from the workspace root above `breakingweb/`, use:

```bash
python -m pytest -q breakingweb/tests
```

High-signal subsets:

```bash
python -m pytest -q tests/test_benchmark_integrity.py tests/test_e2e_integration.py tests/test_canary_trajectories.py
python -m pytest -q tests/test_task_linter.py tests/test_scoring_audit.py tests/test_axtree_audit.py
```

Frontend workspace:

```bash
./scripts/breakingweb.sh status
./scripts/breakingweb.sh build --clean
pnpm -C environments build
pnpm -C environments test
pnpm -C environments dev:amazon
pnpm -C environments dev:gmail
```

The built bundles are written to `static/envs/<env>/`. The FastAPI app marks an environment unavailable when its bundle is missing or stale relative to `environments/<env>/src/` and `environments/shared/src/`.

`./scripts/breakingweb.sh status` prints the current availability check per environment. `./scripts/breakingweb.sh build --clean` removes old static bundles and rebuilds every benchmark frontend in the workspace, excluding only `demo-site`.

## Running the Stock Browser-Use Harness

`breakingweb/stock_browseruse_eval.py` is a second evaluation harness built on
upstream `browser_use.Agent` with minimal customization (stock system prompt,
stock vision, stock planner, action registry minus a few
benchmark-incompatible actions). It runs alongside the custom harness in
`browseruse_eval.py` and is intended to give paper-grade comparability: the
two harnesses evaluate the same task set with different agent loops, so
readers can separate "model ability" from "harness choice".

### Prerequisites (one-time setup)

From a fresh clone on Python 3.11+ and Node 20+:

```bash
# 1. Python deps, including the optional browser-use extra
uv sync --extra browser-use

# 2. Headless Chromium for browser-use
uv run playwright install chromium

# 3. Environment frontends (React SPAs served by the backend)
pnpm -C breakingweb/environments install
./scripts/breakingweb.sh build     # re-run after any frontend source change

# 4. API keys — copy the template and fill in the providers you plan to use
cp breakingweb/.env.example breakingweb/.env
$EDITOR breakingweb/.env           # paste keys; file is gitignored
```

> **AWS Bedrock users:** an `AWS_BEDROCK_API_KEY` alone is not enough. Go to
> AWS Console → **Bedrock** → **Model access** → **Manage model access** and
> request access to each model family you plan to use (Claude, Qwen, etc.).
> Some Anthropic models also require a short use-case form. Without this,
> every LLM call returns `permission_error: ... is not available for this
> account`.

Sanity check the frontend build and the `.env`:

```bash
./scripts/breakingweb.sh status    # all 7 envs should report "ready"
grep -E '^[A-Z_]+=' breakingweb/.env | grep -v '=$'   # keys you've filled
```

### Zero-to-first-PASS smoke (copy-paste)

Two terminals in the repo root:

```bash
# Terminal 1 — backend
source .venv/bin/activate            # or:  uv shell
set -a; source breakingweb/.env; set +a
export BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
python -m uvicorn breakingweb.app:app --host 127.0.0.1 --port 8080
# Leave this running. Wait for: "Uvicorn running on http://127.0.0.1:8080".
```

```bash
# Terminal 2 — run one task end-to-end (~90 seconds)
source .venv/bin/activate
set -a; source breakingweb/.env; set +a
python -m breakingweb.stock_browseruse_eval \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --tasks amazon_browse_category \
    --backend-port 8080 --frontend-port 8080 \
    --output-dir breakingweb/results/smoke
# Expect: "SUMMARY: 1/1 passed | avg score: 1.000"
# Artifacts written under breakingweb/results/smoke/:
#   summary.json, run_manifest.json, tasks/amazon_browse_category/{trajectory.json,screenshots/*.png}
```

If the smoke PASSes you are set up end-to-end. The rest of this section
scales that command up to the full benchmark.

> **Hit `permission_error: ... is not available for this account`?** The model
> is live on Bedrock but not authorized for your account. Revisit
> **Model access** in the Bedrock console and confirm the row is `Access
> granted`, not `Available to request`.

### Supported providers

```
gemini              GEMINI_API_KEY
openai              OPENAI_API_KEY [+ OPENAI_API_BASE_URL]
bedrock             AWS_BEDROCK_API_KEY + AWS_BEDROCK_REGION (Converse API)
anthropic_bedrock   same env as bedrock; Anthropic-native Messages API path
anthropic           ANTHROPIC_API_KEY
openrouter          OPENROUTER_API_KEY
vllm                BREAKINGWEB_API_BASE_URL + BREAKINGWEB_API_KEY
```

The `bedrock` provider uses `ChatAWSBedrock` under the hood but injects
`toolConfig.toolChoice={'any': {}}` into each Converse request, which forces
third-party Bedrock models (Qwen, Mistral, etc.) to emit a structured
`toolUse` block instead of silently returning plain text once context grows.
If the vendor rejects `toolChoice`, the harness logs a warning and retries
without it — so behavior never regresses below upstream.

### Single task (smoke)

```bash
python -m breakingweb.stock_browseruse_eval \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --tasks amazon_browse_category \
    --backend-port 8080 --frontend-port 8080 \
    --output-dir breakingweb/results/single_task
```

### Batch run via `run_picks.py`

`scripts/gen_picks.py` generates a picks JSON from
one of two sources:

- `--subset all` — **the agent benchmark default.** Enumerates every task
  under `breakingweb/tasks/<env>/*.yaml` (519 base tasks) plus every
  intervention variant under `breakingweb/injector/variants/*.yaml`
  (535 variants). Produces **519 clean + 535 intervention = 1054 picks**.
  This full checkout inventory includes variants beyond the paper's 519-pair evaluation.
- `--subset primary / duplicate / both` — subsets curated for the *human*
  annotator study in `breakingweb/human/assignments_v1.yaml`. These are
  for reproducing the human-study slice, **not the agent sweep.**

`scripts/run_picks.py` then consumes the picks JSON and runs the tasks
against a live backend (sequentially or in parallel).

Each pick must be uniquely identified by the tuple `(task_id, cond)` — the
per-task output directory is `tasks/<task_id>__<cond>/`, so two picks with
the same `(task_id, cond)` will overwrite each other's trajectory.
`gen_picks.py` satisfies this by construction; watch out only when hand-
crafting picks JSON.

**1. Generate a picks JSON:**

```bash
# Full checkout inventory (519 clean + 535 intervention = 1054 runs)
python scripts/gen_picks.py --subset all -o picks_all.json

# Filters work on any subset:
python scripts/gen_picks.py --subset all --env amazon --cond clean -o picks_amazon_clean.json
python scripts/gen_picks.py --subset all --diff easy medium -o picks_easy_medium.json

# Human-study subsets (not the agent sweep):
python scripts/gen_picks.py --subset primary   -o picks_primary.json    # 140 × 2 = 280
python scripts/gen_picks.py --subset duplicate -o picks_duplicate.json  # 35  × 2 = 70
```

**2. Start the backend, then run the picks:**

```bash
# Terminal 1 — backend (frontends must already be built; see Prerequisites above)
export BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
python -m uvicorn breakingweb.app:app --host 127.0.0.1 --port 8080

# Terminal 2 — agent (sequential, one episode at a time)
python scripts/run_picks.py \
    --picks picks_all.json \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --backend-port 8080 --frontend-port 8080 \
    --max-steps 40 --timeout 600 \
    --output-dir breakingweb/results/sonnet_duplicate
```

**Parallel execution with `--concurrency N`** (default `1` = sequential). Each
episode owns its own Browser + temp dir, so the only shared resource is the
backend. Budget **~400 MB RAM and ~1 CPU core per concurrent episode**:

```bash
# Run 4 episodes in parallel (good default for a 16 GB / 8-core laptop)
python scripts/run_picks.py \
    --picks picks_all.json \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --backend-port 8080 --frontend-port 8080 \
    --concurrency 4 \
    --max-steps 40 --timeout 600 \
    --output-dir breakingweb/results/sonnet_full
```

Wall-time scales close to linearly with `--concurrency` until the backend or
the model API becomes the bottleneck (Bedrock throttling typically kicks in
around `--concurrency 8`+; OpenAI and OpenRouter tolerate more). Per-task
trajectory files are written **atomically as each task finishes** — a crash
or timeout mid-sweep still leaves every completed task inspectable on disk.

### Slurm example (Duke CS `compsci` partition)

```bash
#!/usr/bin/env bash
#SBATCH --job-name=wab-stock-bu
#SBATCH --partition=compsci
#SBATCH --nodes=1 --cpus-per-task=4 --mem=10G
#SBATCH --time=04:00:00
#SBATCH --output=/usr/xtmp/%u/wab-logs/%x-%j.out
#SBATCH --error=/usr/xtmp/%u/wab-logs/%x-%j.err

set -euo pipefail
cd "${BREAKINGWEB_ROOT:?Set BREAKINGWEB_ROOT to your checkout}"
source .venv/bin/activate
set -a; source breakingweb/.env; set +a

BACKEND_PORT=$(( 9400 + (SLURM_JOB_ID % 600) ))
export BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
python -m uvicorn breakingweb.app:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" --log-level warning \
    > /usr/xtmp/$USER/wab-logs/backend-${SLURM_JOB_ID}.log 2>&1 &
BPID=$!
trap "kill $BPID 2>/dev/null || true" EXIT INT TERM

for i in $(seq 1 120); do
    curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 && break
    sleep 1
done

export PYTHONUNBUFFERED=1
python -u scripts/run_picks.py \
    --picks picks_all.json \
    --model us.anthropic.claude-sonnet-4-6 --provider bedrock \
    --backend-port "$BACKEND_PORT" --frontend-port "$BACKEND_PORT" \
    --concurrency 4 \
    --max-steps 40 --timeout 600 \
    --output-dir /usr/xtmp/$USER/wab-runs/sonnet-${SLURM_JOB_ID}
```

Match `--concurrency` to the slurm `--cpus-per-task` allocation for best
throughput.

### Trajectory replay

Every run produces a directory with the following layout:

```
breakingweb/results/<run_name>/
├── summary.json            top-level aggregation (score/pass/avg + trajectory_path per task)
├── run_manifest.json       reproducibility metadata (model, provider, picks file, git SHA, timestamps)
└── tasks/
    ├── <task_id>__clean/
    │   ├── trajectory.json        per-step thought/action/targets/status (+ screenshot pointer)
    │   └── screenshots/
    │       ├── step01.png
    │       ├── step02.png
    │       └── ...
    ├── <task_id>__intervention/
    │   └── ...
    └── ...
```

`summary.json` is the single file you need for analysis (grid building,
cross-model comparison). Each per-task `trajectory.json` mirrors the schema
used by `browseruse_eval.py` (same `{step, thought, action, targets, status,
elapsed_seconds, replay_path, result_path}`), with one stock-harness-only
addition: `screenshot` points to the relative path of the PNG under the
per-task `screenshots/` directory. Per-task files are written **atomically
as each task finishes**, so a crash-mid-sweep still leaves completed tasks
fully inspectable.

Inspect a run with the existing visualizer (pass either the top-level
`summary.json` or a single task's `trajectory.json`):

```bash
python -m breakingweb.visualize breakingweb/results/<run_name>/summary.json
# opens an HTML viewer: iframe of the live WAB page on the left, step-by-step
# timeline on the right. Each step has "Thought" and (for stock harness)
# "Screenshot" <details> you can expand. Screenshots are re-encoded from the
# per-task PNG files into the generated HTML, so the HTML is self-contained.
```

Two knobs to trade disk for replay fidelity:

```
--no-trajectory                 skip per-task trajectory.json entirely (only summary.json)
--no-trajectory-screenshots     write trajectory.json but skip PNGs (~10 MB/task saved)
```

Rough size: **~50 KB per step** of PNG + a few hundred bytes of JSON. A
30-step expert task with screenshots is ~1.5 MB; a 280-task primary sweep is
~200 MB on disk (most of which is PNGs on the filesystem, not inside any
JSON). Defaults are on.

### Known environment quirks

- **Ubuntu 24.04+ AppArmor blocks Chrome's sandbox** — symptom:
  `BrowserStartEvent timed out after 30.0s` + `ConnectionRefusedError on
  127.0.0.1:<random>/json/version` during `browser.start()`. Ubuntu 24.04
  introduced `kernel.apparmor_restrict_unprivileged_userns=1` which breaks
  Chrome's zygote process; the Chromium subprocess launches but dies silently
  before opening its CDP port. The harness ships with `chromium_sandbox=False`
  on `Browser(...)` so this is handled out of the box — no `IN_DOCKER=true`
  env var needed. If you're running browser-use *outside* this harness on
  Ubuntu 24.04 and hit the same timeout, either `export IN_DOCKER=true`
  before launching or `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`.

- **`BrowserStartEvent timed out after 30s` on contended machines** —
  different symptom from the AppArmor case above: Chrome does eventually
  open its CDP port, but takes longer than browser-use's default 30s
  ceiling when several browsers start in parallel (shared slurm nodes,
  CI runners, laptops under load). The harness bumps
  `TIMEOUT_BrowserStartEvent` and `TIMEOUT_BrowserLaunchEvent` to 90s at
  import time via `os.environ.setdefault`, which eliminates the flake in
  our 6-way parallel smokes. Override by exporting either env var to a
  smaller value if you want to fail faster.

- **OpenRouter is a gateway over multiple upstreams; some are bad for
  structured outputs** — OR forwards each request to one of several
  upstream providers (Anthropic native, Azure, Bedrock OAI-compat,
  Alibaba, DeepInfra, Novita, Fireworks, etc.) depending on price /
  latency / account routing. Their support for the strict
  `response_format=json_schema` payload that browser-use sends is **not
  uniform**. Two confirmed bad upstreams:
  - **Amazon Bedrock** (OAI-compat endpoint) — rejects `json_schema.name`
    as `output_config.format: Extra inputs are not permitted`. Dropping
    `name` would silently disable OR's strict-mode enforcement, so the
    harness routes around Bedrock instead.
  - **Novita** — returns `model features structured outputs not support`
    for models other providers (Alibaba / DeepInfra / Fireworks)
    handle fine; Novita just hasn't implemented strict
    `response_format`.

  By default the harness sets
  `extra_body={"provider":{"ignore":["Amazon Bedrock","Novita"]}}` on
  every OpenRouter request. **This only affects `--provider openrouter`
  — direct `--provider bedrock` / `--provider anthropic` / etc. are
  untouched** (Bedrock's native Converse API has no such issue, only its
  OAI-compat endpoint does). 400-level errors from OR also have the
  upstream name surfaced into the exception (`[upstream=Novita] ...`)
  so failures are easy to diagnose.

  Override the routing via env vars (all optional):

  | Env var | Type | Default | Purpose |
  |---|---|---|---|
  | `BREAKINGWEB_OPENROUTER_IGNORE` | csv | `Amazon Bedrock,Novita` | Replace the ignore list. Empty string allows all upstreams. |
  | `BREAKINGWEB_OPENROUTER_ONLY` | csv | _(unset)_ | Force-restrict to these upstreams. |
  | `BREAKINGWEB_OPENROUTER_ORDER` | csv | _(unset)_ | Preferred upstream ordering. |
  | `BREAKINGWEB_OPENROUTER_ALLOW_FALLBACKS` | bool | true | Allow OR to fall back if preferred upstream is unavailable. |
  | `BREAKINGWEB_OPENROUTER_REQUIRE_PARAMETERS` | bool | false | Strict-match upstream parameters. **Off by default** — turning it on can return `404 No endpoints found` for models like `qwen3-vl-235b-a22b-thinking` whose OR pool has no perfect parameter match. |

  Users who want Bedrock as the actual model host should pass
  `--provider bedrock` directly (native Converse API, no OAI-compat
  layer).

- **Claude via OpenRouter hits `compiled grammar is too large`** — symptom:
  `400 Provider returned error: "The compiled grammar is too large, which
  would cause performance issues. Simplify your tool schemas..."`
  (`provider_name: Azure | Anthropic | Amazon Bedrock`).

  **Root cause**: `browser_use.ChatOpenRouter` uses OpenAI-compat
  `response_format={"type":"json_schema","strict":true}`. When OpenRouter
  routes a Claude request to an upstream that honors strict mode (Azure,
  Bedrock's OAI-compat endpoint, or Anthropic's OAI-compat proxy), the
  upstream compiles the JSON schema to a grammar for constrained decoding
  and enforces a size limit. Anthropic's **native** Messages API
  (`tools=[{input_schema}]` tool_use) has no such limit — verified live at
  16k-char schema 2026-04-24.

  **Empirical thresholds** (browser-use 0.12.6, Sonnet 4.6 via OR, single
  probe each — real limits may vary with model/upstream):

  | schema chars | actions | via OR | direct Anthropic |
  |---|---|---|---|
  | 7,952 | 11 | ✅ | ✅ |
  | 9,057 | 12 | ❌ grammar too large | ✅ |
  | 9,933 | 14 (WAB default exclude) | ❌ grammar too large | ✅ |
  | 15,889 | 24 (full default) | ❌ grammar too large | ✅ |

  GPT via OR passes 9k chars cleanly — so the limit is specific to the
  Anthropic family's strict implementation, not OR or WAB.

  **Separate Layer-1 issue**: Azure / Bedrock's OAI-compat endpoints also
  reject numeric bounds — `400 ... For 'integer'|'number' type, property
  'minimum' is not supported`. browser-use emits these on element-index
  (`int, ge=0`) and scroll pages (`float, ge=0.5, le=10`) fields. The
  harness strips them at wire time via `_strip_numeric_bounds` in
  `stock_browseruse_eval.py`; pydantic validation on the returned tool
  input still enforces the original bounds client-side.

  **Recommended**: run Claude with `--provider anthropic` (native Messages
  API) or `--provider bedrock` (native Converse API) — neither path triggers
  grammar compilation, so any schema size works. Keep OR for GPT / Qwen /
  Kimi where the upstream's strict implementation is fine. If you must run
  Claude via OR, cap the action set at ≤ 11 actions (`_BANNED_ACTIONS` plus
  `screenshot, find_text, find_elements`).

- **GPT-5 reasoning models on OpenRouter emit double JSON** — symptom:
  `Invalid JSON: trailing characters at line 3 column 1` on `openai/gpt-5.4`
  (the full reasoning model, not `-mini` or `gpt-4o`). The raw
  `message.content` is two back-to-back valid AgentOutput JSONs separated
  by `\n\n` — GPT-5 agentic mode occasionally predicts the next turn
  eagerly in the same response. OR's strict `json_schema` mode validates
  *each* JSON's shape but doesn't enforce "exactly one JSON object", so
  it slips through. The harness recovers by tolerant-parsing via
  `json.JSONDecoder().raw_decode()` inside the `ChatOpenRouterStripped`
  wrapper — only the first valid JSON is used; Pydantic still enforces
  the full AgentOutput schema on it. `openai/gpt-5.4-mini`,
  `openai/gpt-4o`, and `openai/gpt-4o-mini` via OR are clean and don't
  exercise the fallback.

### Known model quirks

- **Claude (Sonnet / Opus) on Bedrock** — clean. Daily TPD quota is per-model;
  long sweeps can exhaust Opus's cap in ~3 expert-tier tasks. Sonnet 4.6 has
  a larger quota and is the recommended default. For the full 280-run primary
  sweep on Opus, file a TPD quota-increase request via AWS Service Quotas
  (24–48 h lead time); for exploration runs, start with `--limit 5` to check
  headroom before committing to a long sweep.
- **Qwen3-VL-235B (`qwen.qwen3-vl-235b-a22b`)** — works once the harness's
  `toolChoice` forcing is applied (already wired in this repo). Without it,
  the model returns flat JSON (`{"click": 45}`) that fails Pydantic validation.
  Separately, Qwen tends to **over-act** (do steps the task didn't ask for,
  e.g. check grade → then also submit homework) and miss fine recipient/body
  constraints — these show up as low eval scores even though the agent says
  it succeeded. This is a model-capability gap, not a harness bug.
- **Kimi K2.5 (`moonshotai.kimi-k2.5`)** — Bedrock silently ignores
  `toolChoice` for this vendor, so the model still drops to plain-text
  reasoning at long context (~step 4+). Kimi K2.5 via Bedrock is not
  recommended; use the native Moonshot API if Kimi is required.
- **Kimi K2 Thinking (`moonshot.kimi-k2-thinking`)** — text-only on Bedrock
  (`inputModalities: [TEXT]`), incompatible with `use_vision=True`.

## Running the Pixel Harness (vision-only ablation)

In addition to the stock browser-use harness (text + vision) and the
BrowserGym text harness (`agent_eval.py`), there is a third entry point that
drives tasks **with screenshots only** — no DOM, no AXTree, no HTML. Useful
for benchmarking VLMs in the same regime as ComponentBench / InterfaceGym
`--mode pixel` runs.

Files:

* [`pixel_agent.py`](pixel_agent.py) — vision-only `PixelLLMAgent`. Reads
  `obs["screenshot"]`, outputs BrowserGym `coord` actions like
  `mouse_click(640, 360)` / `keyboard_type('hello')`. Supports four
  providers via OpenAI-compatible chat (Gemini-native, OpenRouter,
  Anthropic-direct) plus AWS Bedrock via the boto3 Converse API (so
  `us.anthropic.claude-sonnet-4-6` works — Bedrock's OAI-compat endpoint
  doesn't currently serve that model).
* [`pixel_eval.py`](pixel_eval.py) — single-task runner with the same async
  signature as `stock_browseruse_eval.run_episode`.
* [`scripts/pixel_run_picks.py`](../scripts/pixel_run_picks.py) — picks-file
  runner; same JSON format as `scripts/run_picks.py`.
* [`scripts/pixel_aggregate.py`](../scripts/pixel_aggregate.py) — merges
  shard outputs from a slurm-array sweep into one `summary.json`.

### Zero-to-first-PASS smoke (copy-paste, mirrors the browser-use quickstart)

Two terminals in the repo root. Assumes `breakingweb/.env` is filled,
frontends are built, and `.venv` is set up — see the [Prerequisites][prereq]
section above (the same steps apply to both harnesses).

[prereq]: #prerequisites-one-time-setup

```bash
# Terminal 1 — backend (same as browser-use mode)
source .venv/bin/activate
set -a; source breakingweb/.env; set +a
export BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
python -m uvicorn breakingweb.app:app --host 127.0.0.1 --port 8080
# Wait for: "Uvicorn running on http://127.0.0.1:8080"
```

```bash
# Terminal 2 — single pixel-mode task (~90s, costs ~$0.05 on Gemini Flash)
source .venv/bin/activate
set -a; source breakingweb/.env; set +a
python -m breakingweb.pixel_eval \
    --task booking_clear_search_history \
    --model gemini-3-flash-preview --provider gemini \
    --backend-port 8080 \
    --max-steps 25 --timeout 600 \
    --output-dir breakingweb/results/pixel-smoke
# Expect a JSON dump with score=1.0 / success=True.
# Per-step screenshots: breakingweb/results/pixel-smoke/screenshots/stepNN.png
```

### Pre-flight: validate credentials in <10s before launching anything

The agent runs a 1-token probe at init (`PixelLLMAgent.__init__`) to confirm
the API key + model are valid **before** the BrowserGym backend boots. A bad
key fails fast with a clear `RuntimeError` rather than wasting 30-60s of
cluster time and partial API charges per pick. To dry-run all four providers
locally before submitting any sbatch:

```bash
source .venv/bin/activate
set -a; source breakingweb/.env; set +a

python -c "
from breakingweb.pixel_agent import PixelLLMAgent
for model, prov in [
    ('gemini-3-flash-preview', 'gemini'),
    ('anthropic/claude-opus-4.6', 'openrouter'),
    ('qwen/qwen3-vl-235b-a22b-instruct', 'openrouter'),
    ('us.anthropic.claude-sonnet-4-6', 'bedrock'),
]:
    PixelLLMAgent(model=model, provider=prov)
    print(f'OK {prov:11s} {model}')
"
# Skip the probe (e.g. air-gapped CI) with WAB_PIXEL_SKIP_PROBE=1.
```

### Single-task smoke

```bash
source .venv/bin/activate
set -a; source breakingweb/.env; set +a

python -m breakingweb.pixel_eval \
    --task booking_save_property \
    --variant booking_save_property__property_twin.yaml \
    --model gemini-3-flash-preview \
    --provider gemini \
    --backend-port 8080 \
    --max-steps 40 --timeout 600 \
    --output-dir breakingweb/results/pixel-smoke
```

### Running a sweep — sequential (any machine, no slurm needed)

The simplest scaling pattern: one backend, one runner process, picks are
processed one at a time. Wall time = `sum(pick_time)` (~5-10 min/pick at
`max_steps=40`), so 10 picks = roughly an hour. Suitable for smoke tests
and small sweeps on any laptop / dev box.

```bash
# Build a picks JSON. Same shape as scripts/run_picks.py — see the
# browser-use section for `gen_picks.py`, or hand-write a list:
cat > picks.json <<'EOF'
[
  {"task_id":"booking_save_property","cond":"clean"},
  {"task_id":"booking_save_property","variant_filename":"booking_save_property__property_twin.yaml","cond":"intervention"},
  {"task_id":"booking_clear_search_history","cond":"clean"}
]
EOF

# Terminal 1 — backend on any free port
python -m uvicorn breakingweb.app:app --host 127.0.0.1 --port 8080

# Terminal 2 — sequential runner
python scripts/pixel_run_picks.py \
    --picks picks.json \
    --model gemini-3-flash-preview --provider gemini \
    --backend-port 8080 \
    --max-steps 40 --timeout 600 \
    --output-dir breakingweb/results/pixel-sweep
```

Per-task trajectories (with `screenshots/stepNN.png`) are written
**atomically as each pick finishes** — interrupting the runner mid-sweep
still leaves every completed pick fully inspectable.

### Running a sweep — parallel without slurm (multi-process)

`--concurrency > 1` is hard-capped: Playwright's sync API can't share a
BrowserEnv across threads, and the runner errors out fast if you try.
**Real parallelism comes from running multiple PROCESSES, each handling a
shard of the picks.** A single backend can serve them all (FastAPI is
multi-tenant; each session gets its own UUID). Pattern:

```bash
# Terminal 1 — single backend, any free port
python -m uvicorn breakingweb.app:app --host 127.0.0.1 --port 8080

# Terminal 2 — fan out N runner processes
N=4   # how many parallel processes; tune to your CPU/RAM
mkdir -p breakingweb/results/pixel-sweep
for i in $(seq 0 $((N-1))); do
    python scripts/pixel_run_picks.py \
        --picks picks.json \
        --model gemini-3-flash-preview --provider gemini \
        --backend-port 8080 \
        --max-steps 40 --timeout 600 \
        --shard-of $N --shard-id $i \
        --output-dir breakingweb/results/pixel-sweep &
done
wait

# Aggregate the N shard outputs into one summary
python scripts/pixel_aggregate.py breakingweb/results/pixel-sweep
```

Each shard writes to `<output-dir>/shard_NN/`; `pixel_aggregate.py`
symlinks them into one unified `tasks/` tree plus merged `summary.json`.

**Resource budgeting:**

* ~400 MB RAM + ~1 CPU core per runner process (Playwright + browser).
* Backend uses ~200 MB regardless of how many runners hit it.
* 4 parallel runners on a 16 GB / 8-core box is comfortable; 8 is the
  practical ceiling before the backend becomes the bottleneck.

**Port collisions:** if you want to test two different sweeps in parallel
(e.g. two providers), give each its own backend port (`--port 8081`,
`--port 8082`, etc.) and pass the matching `--backend-port` to that
runner. The default `8080` only works if a single backend is running.

### Running a sweep in parallel via slurm array jobs

**The picks runner is built around slurm array jobs.** Playwright's sync API
can't share threads, so in-process `--concurrency` is hard-capped at 1; the
only way to scale is to fan out across processes. The runner accepts
`--shard-of N --shard-id i` and writes to `<output-dir>/shard_NN/`. Pair
this with `#SBATCH --array=0-(N-1)` and you get **one slurm task per pick**,
each with its own backend process. Wall time becomes ~`max(pick_time)`
instead of `sum(pick_time)`. `scripts/pixel_aggregate.py` then symlinks the
shard subdirs into one merged sweep dir.

`SLURM_ARRAY_TASK_ID` is auto-detected — the runner overrides any
`--shard-id` flag with the env var when running under slurm.

**Step 1.** Build a picks file. Same JSON shape as `scripts/run_picks.py`
(see *Batch run via `run_picks.py`* under the browser-use section above).
Either generate one with `scripts/gen_picks.py` or hand-write a list, e.g.:

```json
[
  {"task_id":"booking_save_property","cond":"clean"},
  {"task_id":"booking_save_property","variant_filename":"booking_save_property__property_twin.yaml","cond":"intervention"},
  {"task_id":"booking_clear_search_history","cond":"clean"}
]
```

**Step 2.** Drop this template under `scripts/slurm/` (gitignored). Set
`#SBATCH --array=0-(N-1)` to the number of picks you have, edit
`--partition`, the model/provider, and the picks-file path:

```bash
#!/usr/bin/env bash
#SBATCH --job-name=pixel-sweep
#SBATCH --partition=compsci
#SBATCH --nodes=1 --cpus-per-task=4 --mem=10G --time=01:30:00
#SBATCH --output=/usr/xtmp/%u/wab-logs/pixel-%A_%a.out
#SBATCH --error=/usr/xtmp/%u/wab-logs/pixel-%A_%a.err
#SBATCH --array=0-2          # ← N-1 where N = picks in your JSON

set -euo pipefail
cd "${BREAKINGWEB_ROOT:?Set BREAKINGWEB_ROOT to your checkout}"
source .venv/bin/activate
set -a; source breakingweb/.env; set +a

# Each array task gets a unique backend port (SLURM_JOB_ID is per-task)
BACKEND_PORT=$(( 9400 + (SLURM_JOB_ID % 600) ))
export BREAKINGWEB_AUTO_BUILD_FRONTENDS=0
export BREAKINGWEB_CONTROLLER_SECRET="pixel-${SLURM_JOB_ID}"

python -m uvicorn breakingweb.app:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" --log-level warning \
    > /usr/xtmp/$USER/wab-logs/backend-${SLURM_JOB_ID}.log 2>&1 &
BPID=$!
trap "kill $BPID 2>/dev/null || true" EXIT INT TERM
for i in $(seq 1 120); do
    curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 && break
    sleep 1
done

OUT_DIR=/usr/xtmp/$USER/wab-runs/pixel-${SLURM_ARRAY_JOB_ID}
export PYTHONUNBUFFERED=1
python -u scripts/pixel_run_picks.py \
    --picks /path/to/your_picks.json \
    --model gemini-3-flash-preview --provider gemini \
    --backend-port "$BACKEND_PORT" --frontend-port "$BACKEND_PORT" \
    --max-steps 40 --timeout 600 \
    --shard-of "$SLURM_ARRAY_TASK_COUNT" \
    --shard-id "$SLURM_ARRAY_TASK_ID" \
    --output-dir "$OUT_DIR"
```

**Step 3.** Submit, then aggregate when all shards finish:

```bash
sbatch scripts/slurm/your_pixel_sweep.sbatch
# When all array tasks have completed:
python scripts/pixel_aggregate.py /usr/xtmp/$USER/wab-runs/pixel-<arrayjobid>
# Writes merged summary.json + run_manifest.json + symlinked tasks/ tree.
```

To run multiple providers in parallel, copy the template and change
`--model` / `--provider` / `--picks` for each. Each sbatch fans out into
its own array independently; total wall time is still bounded by the
slowest single pick.

### Cost & failure-mode guardrails

Pixel mode tasks are coord-action VLM calls; cost scales linearly with
`max_steps × n_tasks`. Approximate per-task cost at `max_steps=40` (one image
per step, ~1500 input tokens, ~80 output tokens):

| Provider / model | $ per task (40 steps) | Notes |
|---|---|---|
| Gemini 3 Flash native (`gemini`) | ~$0.05 | Cheapest; thinking tokens hidden in `thought_signature` |
| Qwen3-VL-235B via OpenRouter | ~$0.10 | Outputs visible `<think>` reasoning |
| Bedrock Claude Sonnet 4.6 (`bedrock`) | ~$0.50 | Converse API; bearer-token auth |
| OpenRouter Claude Opus 4.6 | ~$2.00 | Most expensive; richest reasoning |

Built-in safeguards (each saves ≥$1 / picks file when something is wrong):

* **Credential probe** — agent init makes 1 chat call (~$0.0001) to fail
  fast on bad API keys / model names.
* **Loop detection** — if the same exact action is emitted ≥5 times in a row
  (`WAB_PIXEL_LOOP_THRESHOLD`), `PixelLLMAgent.act()` swaps in
  `send_msg_to_user('infeasible: stuck in 5-action loop')` so BrowserGym
  terminates the episode early instead of burning the full `max_steps`
  budget. Typical save: 25-35 wasted steps per stuck pick.
* **Per-step timeout** — 120s in `agent_eval.run_episode`; kills runaway API
  retries.
* **Wall-clock timeout** — `--timeout 600` (10 min) per pick by default.
* **Per-step screenshots** — `<task_dir>/screenshots/stepNN.png` saved
  before each agent action so you can replay/debug any failure post-hoc
  without re-running. Same naming as the stock browser-use harness.

### Bedrock model availability gotcha

`us.anthropic.claude-sonnet-4-6` works through Bedrock's **Converse API**
(boto3, what `pixel_agent.py` uses for `provider=bedrock`) but **NOT**
through Bedrock's OpenAI-compat endpoint at
`bedrock-runtime.<region>.amazonaws.com/openai/v1/chat/completions` —
that path returns `404 model_not_found` for cross-region inference profiles
as of this writing. Auth uses the long-term API key
(`AWS_BEDROCK_API_KEY` in `.env`) which `pixel_agent.py` mirrors into
`AWS_BEARER_TOKEN_BEDROCK` (the env var boto3 reads).

## Running sweeps

The workspace provides [text](../scripts/sweep_templates/stock_sweep.sbatch) and [pixel](../scripts/sweep_templates/pixel_sweep.sbatch) Slurm templates. Set `MODEL`, `PROVIDER`, `PICKS`, and `BREAKINGWEB_ROOT` to match your model, task selection, and checkout. Adapt the Slurm account, partition, and storage settings to your cluster.

## Evaluation artifacts

Evaluation runs write `run_manifest.json`, `summary.json`, and per-task trajectory files. Published artifacts are available in [breakingweb-results-v2](https://huggingface.co/datasets/BreakingWeb/breakingweb-results-v2) and [breakingweb-results-v3](https://huggingface.co/datasets/BreakingWeb/breakingweb-results-v3).
