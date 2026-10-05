"""Audit instruction ↔ canonical_diff alignment across all tasks.

Heuristics (cheap, designed for high recall, low false-negative rate):

1. NUMBER DRIFT — extract numeric tokens (with unit/symbol context) from the
   instruction; extract numeric tokens from canonical_diff desc/expr text.
   Flag when an instruction number doesn't appear (textually or as a close
   match) anywhere in canonical_diff, especially for $, %, share count,
   day/week count.

2. VERB ↔ PRESERVE CONFLICT — instruction uses an action verb (buy, sell,
   transfer, deposit, withdraw, place an order, fill, archive, delete,
   schedule, cancel, book, refund, etc.) AND canonical_diff has
   `preserve: ALL` on a collection that verb would naturally mutate.

3. RH FILL SIDE-EFFECT GAP — task creates an `orders` entity AND instruction
   uses fill/execute/wait-for-fill language AND canonical_diff is missing
   `create` entries for positions / transactions / notifications.

4. DESC ↔ INSTRUCTION DRIFT — canonical_diff `desc:` text contains a
   threshold (≤X%, ≥X%, $X, X shares, etc.) that doesn't appear in the
   instruction text.

Output: ranked list of suspect tasks with the specific reason.
"""

from __future__ import annotations

import re
import sys
import yaml
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TASKS = REPO / "breakingweb" / "tasks"

# ── Heuristic helpers ─────────────────────────────────────────────────────

NUM_RE = re.compile(r"(?:\$\s*)?(\d+(?:\.\d+)?)\s*(%|shares?|emails?|messages?|days?|weeks?|hours?|minutes?|miles?|orders?|labels?|posts?|threads?|appointments?|stars?)?", re.IGNORECASE)
DOLLAR_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
SHARES_RE = re.compile(r"(\d+(?:\.\d+)?)\s*shares?", re.IGNORECASE)

ACTION_VERBS = {
    # General
    "buy": {"orders", "positions", "transactions", "notifications", "cash_balance", "buying_power"},
    "sell": {"orders", "positions", "transactions", "notifications", "cash_balance", "buying_power"},
    "purchase": {"orders", "positions", "transactions", "cart", "checkout"},
    "place": {"orders"},  # place an order
    "execute": {"orders", "positions", "transactions"},
    "fill": {"orders", "positions", "transactions", "notifications"},
    "transfer": {"transfers", "linked_banks", "cash_balance", "transactions", "notifications"},
    "deposit": {"transfers", "cash_balance", "buying_power"},
    "withdraw": {"transfers", "cash_balance", "buying_power"},
    "archive": {"emails", "threads", "messages"},
    "delete": {"*"},  # any
    "schedule": {"appointments", "events", "tasks"},
    "cancel": {"appointments", "orders", "subscriptions"},
    "book": {"appointments", "reservations"},
    "refund": {"transactions", "orders"},
    "send": {"sent", "emails", "messages"},
    "reply": {"sent", "emails", "messages"},
    "forward": {"sent", "emails", "messages"},
    "compose": {"sent", "drafts"},
    "subscribe": {"subscriptions"},
    "unsubscribe": {"subscriptions"},
    "follow": {"subscriptions", "follows"},
    "label": {"emails", "labels"},
    "star": {"emails", "starred"},
    "checkout": {"orders", "cart"},
    "submit": {"orders", "assignments", "submissions"},
    "complete": {"assignments", "submissions"},
    "rate": {"reviews", "ratings"},
    "review": {"reviews"},
    "post": {"posts", "comments"},
    "comment": {"comments"},
    "upvote": {"posts", "comments"},
    "downvote": {"posts", "comments"},
    "reset": {"settings"},
    "update": {"settings", "profile", "addresses"},
    "set": {"settings", "profile"},
    "save": {"saved", "wishlists", "saved_items"},
    "wishlist": {"wishlists"},
}

PRESERVE_COLLECTIONS_RE = re.compile(r"collection:\s*state\.([\w_]+).*?preserve:\s*ALL", re.DOTALL)


def _extract_thresholds(text: str) -> dict[str, list[str]]:
    """Pick out dollar/%/share thresholds from a string."""
    return {
        "dollars": [m.group(1) for m in DOLLAR_RE.finditer(text)],
        "percents": [m.group(1) for m in PCT_RE.finditer(text)],
        "shares": [m.group(1) for m in SHARES_RE.finditer(text)],
    }


def _normalize_number(s: str) -> str:
    """Drop trailing zeros so '180' and '180.0' compare equal."""
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
        return str(f).rstrip("0").rstrip(".")
    except ValueError:
        return s


def _serialize_canonical_diff(diff: dict) -> str:
    """Flatten canonical_diff to a single string for substring searches."""
    return yaml.safe_dump(diff or {}, default_flow_style=False, sort_keys=False)


# ── Heuristic checks ──────────────────────────────────────────────────────


def check_number_drift(task: dict, finding: list) -> None:
    """Flag instruction numbers (especially $/%/shares) absent from canonical_diff."""
    instruction = task.get("instruction_template") or task.get("instruction") or ""
    diff = task.get("canonical_diff") or {}
    diff_text = _serialize_canonical_diff(diff)

    for kind in ("dollars", "percents", "shares"):
        instr_nums = [_normalize_number(n) for n in _extract_thresholds(instruction)[kind]]
        diff_nums = set(_normalize_number(n) for n in _extract_thresholds(diff_text)[kind])
        # Also accept the raw number anywhere in the diff text (for `eq: 10` style).
        for n in instr_nums:
            if n in diff_nums:
                continue
            if re.search(rf"(?<!\d){re.escape(n)}(?!\d)", diff_text):
                continue
            unit = {"dollars": "$", "percents": "%", "shares": " shares"}[kind]
            finding.append((
                "NUMBER_DRIFT",
                f"instruction has {n}{unit} but canonical_diff doesn't reference it",
            ))


def _entity_to_collection(entity: str) -> str:
    """Map a create/update/delete entity name to its collection name.

    Entity names in canonical_diff entries are typically capitalized singular
    (``Message``, ``Order``); collection names are lowercase plural
    (``messages``, ``orders``). Strip case and trailing pluralization to make
    them comparable.
    """
    e = (entity or "").strip().lower()
    return e.rstrip("s") if e.endswith("s") else e


def _collections_covered_by_diff(diff: dict) -> set[str]:
    """Return collection names (singular, lowercase) covered by any positive entry."""
    covered: set[str] = set()
    for kind in ("create", "update", "delete"):
        for entry in (diff.get(kind) or []):
            entity = (entry or {}).get("entity") or ""
            collection = (entry or {}).get("collection") or ""
            covered.add(_entity_to_collection(entity))
            if collection:
                covered.add(collection.removeprefix("state.").rstrip("s"))
    return covered


def check_verb_preserve_conflict(task: dict, finding: list) -> None:
    instruction = (task.get("instruction_template") or "").lower()
    diff = task.get("canonical_diff") or {}
    diff_text = _serialize_canonical_diff(diff)

    preserved = set(PRESERVE_COLLECTIONS_RE.findall(diff_text))
    if not preserved:
        return

    covered = _collections_covered_by_diff(diff)

    for verb, expected_mutations in ACTION_VERBS.items():
        if not re.search(rf"\b{verb}(?:s|es|ed|ing)?\b", instruction):
            continue
        for collection in expected_mutations:
            if collection == "*":
                continue
            if collection not in preserved:
                continue
            # Filter on the preserve invariant means it's intentional.
            pattern = rf"collection:\s*state\.{re.escape(collection)}\s*\n\s*filter:.*?preserve:\s*ALL"
            if re.search(pattern, diff_text, re.DOTALL):
                continue
            # The preserve is shadowed by a create/update/delete on the same
            # collection (matcher subtracts matched entries before invariant
            # check at matcher.py:376).
            if collection.rstrip("s") in covered:
                continue
            finding.append((
                "VERB_PRESERVE_CONFLICT",
                f"instruction uses '{verb}' but canonical_diff preserves "
                f"state.{collection} with no filter or matching positive entry",
            ))


def check_rh_fill_side_effects(task: dict, finding: list) -> None:
    if task.get("env_id") != "robinhood":
        return
    instruction = (task.get("instruction_template") or "").lower()
    diff = task.get("canonical_diff") or {}
    creates = diff.get("create") or []
    create_entities = {(c or {}).get("entity") for c in creates}

    # Only fire if the task creates an order AND implies it should fill.
    if "orders" not in create_entities:
        return

    fill_implied = any(kw in instruction for kw in [
        "wait for it to fill", "wait for fill", "until it fills", "and confirm",
        " fills", " filled", "executed", "fill the ", "fills the ",
        "execute", "buy ", "sell ", "purchase ",
    ])
    # Also: if the order explicitly is `time_in_force: gtc` and price trajectory
    # crosses the limit, fill is mathematically guaranteed.
    seed = task.get("seed") or {}
    has_price_traj = "price_trajectory" in seed
    if not (fill_implied or has_price_traj):
        return

    # Check for an `orders` create whose status predicate explicitly forbids fill.
    forbids_fill = False
    for c in creates:
        if (c or {}).get("entity") != "orders":
            continue
        props = (c.get("properties") or {})
        status = props.get("status") or {}
        if isinstance(status, dict):
            # eq: open/pending → forbids fill
            eq = status.get("eq")
            if isinstance(eq, str) and eq in {"open", "pending", "queued"}:
                forbids_fill = True
            neq = status.get("neq")
            if isinstance(neq, str) and neq == "filled":
                forbids_fill = True
    if forbids_fill:
        return

    # Now check side-effect coverage.
    diff_text = _serialize_canonical_diff(diff)
    preserved = set(PRESERVE_COLLECTIONS_RE.findall(diff_text))
    missing: list[str] = []
    for col in ("positions", "transactions", "notifications"):
        if col in create_entities:
            continue
        # Filter on preserve invariant counts as opt-out (intentional).
        pattern = rf"collection:\s*state\.{re.escape(col)}\s*\n\s*filter:.*?preserve:\s*ALL"
        if re.search(pattern, diff_text, re.DOTALL):
            continue
        if col in preserved:
            missing.append(f"{col} (preserved unconditionally)")
        else:
            # If the entity is neither in creates nor in preserves, the
            # fallback collateral sweep will still penalize it.
            missing.append(f"{col} (unaccounted)")
    if missing:
        finding.append((
            "RH_FILL_SIDE_EFFECT_GAP",
            f"order create implies fill but canonical_diff missing: {', '.join(missing)}",
        ))


def check_desc_drift(task: dict, finding: list) -> None:
    instruction = (task.get("instruction_template") or "")
    diff = task.get("canonical_diff") or {}
    creates = (diff.get("create") or []) + (diff.get("update") or []) + (diff.get("delete") or [])
    instr_thresholds = _extract_thresholds(instruction)
    instr_nums = {_normalize_number(n) for vals in instr_thresholds.values() for n in vals}

    for entry in creates:
        desc = (entry or {}).get("desc") or ""
        if not desc:
            continue
        desc_thresholds = _extract_thresholds(desc)
        for kind, vals in desc_thresholds.items():
            for n in vals:
                norm = _normalize_number(n)
                if norm in instr_nums:
                    continue
                # Allow the number if it appears anywhere in instruction text.
                if re.search(rf"(?<!\d){re.escape(norm)}(?!\d)", instruction):
                    continue
                unit = {"dollars": "$", "percents": "%", "shares": " shares"}[kind]
                finding.append((
                    "DESC_DRIFT",
                    f"canonical_diff desc says '{n}{unit}' but instruction never mentions it",
                ))


# ── Driver ────────────────────────────────────────────────────────────────


def main():
    findings: list[tuple[str, str, str, str]] = []  # (env, task_id, kind, detail)
    by_kind: dict[str, int] = defaultdict(int)
    by_env: dict[str, int] = defaultdict(int)

    paths = sorted(TASKS.rglob("*.yaml"))
    paths = [p for p in paths if not p.name.startswith("_")]

    for path in paths:
        try:
            task = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            print(f"yaml error: {path}: {e}", file=sys.stderr)
            continue
        if not isinstance(task, dict):
            continue
        env = task.get("env_id") or path.parent.name
        tid = task.get("task_id") or path.stem
        local_findings: list[tuple[str, str]] = []
        check_number_drift(task, local_findings)
        check_verb_preserve_conflict(task, local_findings)
        check_rh_fill_side_effects(task, local_findings)
        check_desc_drift(task, local_findings)
        for kind, detail in local_findings:
            findings.append((env, tid, kind, detail))
            by_kind[kind] += 1
            by_env[env] += 1

    # Print summary
    print("=" * 72)
    print(f"INSTRUCTION ↔ CANONICAL_DIFF ALIGNMENT AUDIT")
    print(f"  scanned: {len(paths)} tasks")
    print(f"  total findings: {len(findings)}")
    print("=" * 72)
    print()
    print("Findings by kind:")
    for k, n in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"  {n:4}  {k}")
    print()
    print("Findings by env:")
    for e, n in sorted(by_env.items(), key=lambda x: -x[1]):
        print(f"  {n:4}  {e}")
    print()

    # Group findings by (env, task) for readability
    grouped: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for env, tid, kind, detail in findings:
        grouped[(env, tid)].append((kind, detail))

    print(f"Tasks with findings: {len(grouped)}")
    print()
    # Sort by severity: RH_FILL_SIDE_EFFECT_GAP first (most damaging), then VERB_PRESERVE_CONFLICT,
    # then NUMBER_DRIFT, then DESC_DRIFT.
    severity = {"RH_FILL_SIDE_EFFECT_GAP": 0, "VERB_PRESERVE_CONFLICT": 1,
                "NUMBER_DRIFT": 2, "DESC_DRIFT": 3}

    def task_severity(items):
        return min(severity.get(k, 99) for k, _ in items), -len(items)

    sorted_tasks = sorted(grouped.items(), key=lambda kv: task_severity(kv[1]))

    for (env, tid), items in sorted_tasks:
        kinds = sorted({k for k, _ in items}, key=lambda k: severity.get(k, 99))
        print(f"[{env}] {tid}    ({', '.join(kinds)})")
        for kind, detail in items:
            print(f"    • {kind}: {detail}")


if __name__ == "__main__":
    main()
