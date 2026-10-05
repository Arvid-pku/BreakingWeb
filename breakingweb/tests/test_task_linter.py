"""Task linter — catches benchmark construction bugs before any model run.

Checks every task YAML and variant YAML for:
  1. Answer leakage (hardcoded answers in instruction_template)
  2. Open-ended qualifier guardrails for instruction templates
  3. Actor name determinism (actors referenced in instructions need explicit names)
  4. Forward-task identity grounding when a task asks to forward one specific
     email (asserts canonical_diff binds forwarded_from_id to the target).
  5. Variant response_body schema validity (fake responses must match real API)
  6. Filter silent-fail payload completeness
  7. Variant base_task_id validity (must reference an existing task)

The legacy `eval:` schema is gone — every task uses canonical_diff for runtime
evaluation. Lint rules that operated on `eval.checks` / `eval.negative_checks`
were deleted alongside the schema (commit 14c33751); per-predicate validity
checks now belong to the canonical_diff matcher tests.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

TASKS_DIR = Path(__file__).parent.parent / "tasks"
VARIANTS_DIR = Path(__file__).parent.parent / "injector" / "variants"
ACTOR_REF_RE = re.compile(r"\{actor\.(\w+)")


# ── helpers ──────────────────────────────────────────────────────────────

def _load_all_tasks() -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for path in sorted(TASKS_DIR.rglob("*.yaml")):
        if path.name.startswith("_"):
            continue
        raw = yaml.safe_load(path.read_text())
        if raw and "task_id" in raw:
            tasks[raw["task_id"]] = raw
    return tasks


def _load_all_variants() -> list[tuple[str, dict[str, Any]]]:
    variants: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(VARIANTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text())
        if raw:
            variants.append((path.name, raw))
    return variants


def _canonical_create_properties(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every canonical_diff create-property map, including oneof blocks."""
    canonical = task.get("canonical_diff") or {}
    blocks = [canonical]
    blocks.extend(canonical.get("oneof") or [])
    properties: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for entry in block.get("create") or []:
            if isinstance(entry, dict):
                props = entry.get("properties") or {}
                if isinstance(props, dict):
                    properties.append(props)
    return properties


def _predicate_mentions_target(predicate: Any, target_name: str) -> bool:
    return target_name in str(predicate)


def _instruction_text(task: dict[str, Any]) -> str:
    """Return the user-visible instruction text for a task."""
    return task.get("instruction_template", "") or task.get("instruction", "") or ""


ALL_TASKS = _load_all_tasks()
ALL_VARIANTS = _load_all_variants()


# ── 1. Answer leakage in instructions ────────────────────────────────────

def test_no_answer_leakage_in_instructions() -> None:
    """Target values that are actual answers must not appear in instruction_template.

    Targets defined as literal values (not ``{output.X}`` or ``{actor.X}`` refs)
    are answer data. If they appear verbatim in the instruction, the agent
    doesn't need to do the task — the answer is given.
    """
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        instr = _instruction_text(task)
        targets = (task.get("seed") or {}).get("targets") or {}
        for tkey, tval in targets.items():
            if not isinstance(tval, str):
                continue
            # Skip template references — those are not literal values
            if tval.startswith("{"):
                continue
            # Skip very short values (1-2 chars) — too prone to false-positive
            # substring matches (e.g., '2' matching inside '4242')
            if len(tval) <= 2:
                continue
            if tval in instr:
                violations.append(
                    f"[{tid}] literal target '{tkey}' = '{tval}' "
                    f"appears in instruction_template"
                )
    assert not violations, "\n".join(violations)


def test_instruction_templates_avoid_open_ended_qualifiers() -> None:
    """Instructions should be objectively executable, not judgment-based.

    These phrases invite subjective interpretation and weaken benchmark
    reproducibility. Keep the blocked list intentionally small and high-signal.
    """
    blocked_patterns = [
        r"\bappropriate\b",
        r"\breasonable\b",
        r"\bbest judgment\b",
        r"\buse your judgment\b",
        r"\buse your judgement\b",
        r"\bas needed\b",
        r"\bif needed\b",
        r"\bwhichever\b",
        r"\betc\.\b",
        r"\band so on\b",
        r"\bsuitable\b",
        r"\bproper\b",
    ]
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        instr = _instruction_text(task)
        lower_instr = instr.lower()
        for pattern in blocked_patterns:
            if re.search(pattern, lower_instr):
                violations.append(
                    f"[{tid}] instruction contains open-ended qualifier matching /{pattern}/"
                )
    assert not violations, "\n".join(violations)


# ── 2. Actor name determinism ────────────────────────────────────────────

def test_actors_referenced_in_instructions_have_explicit_names() -> None:
    """If an actor's name flows into the instruction, it must be explicit.

    Actors without ``name:`` get a random name from FakeDataGenerator,
    making the instruction non-deterministic across seeds.
    """
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        instr = _instruction_text(task)
        actors = (task.get("seed") or {}).get("actors") or {}
        targets = (task.get("seed") or {}).get("targets") or {}

        # Find which actor keys flow into the instruction via targets
        for tkey, tval in targets.items():
            if not isinstance(tval, str):
                continue
            m = ACTOR_REF_RE.search(tval)
            if not m:
                continue
            actor_key = m.group(1)
            # Check if this target is used in the instruction
            if f"{{target.{tkey}}}" not in instr:
                continue
            actor_spec = actors.get(actor_key, {})
            if isinstance(actor_spec, dict) and "name" not in actor_spec:
                violations.append(
                    f"[{tid}] instruction uses {{target.{tkey}}} → "
                    f"{{actor.{actor_key}}} but actor has no explicit name"
                )
    assert not violations, "\n".join(violations)


# ── 3. Forward-task identity grounding ───────────────────────────────────

def test_single_email_forward_tasks_check_original_email_identity() -> None:
    """Forwarding one specific email must be graded against that source email.

    Matching only on recipient or subject is too weak: the agent could send a new
    email or forward the wrong message and still score. When a task exposes a
    single concrete source email via ``target_email_id`` and asks the agent to
    forward that email, at least one canonical_diff create-entry must bind
    ``forwarded_from_id`` to ``{target.target_email_id}``.
    """
    violations: list[str] = []
    for tid, task in ALL_TASKS.items():
        instr = _instruction_text(task).lower()
        targets = ((task.get("seed") or {}).get("targets") or {})
        if "target_email_id" not in targets:
            continue
        if "forward it to" not in instr and "forward this email" not in instr and "forward the email" not in instr:
            continue
        canonical_grounded = any(
            _predicate_mentions_target(props.get("forwarded_from_id"), "target_email_id")
            for props in _canonical_create_properties(task)
        )
        if not canonical_grounded:
            violations.append(
                f"[{tid}] single-email forward task lacks a canonical_diff property "
                "binding forwarded_from_id to {target.target_email_id}"
            )
    assert not violations, "\n".join(violations)


# ── 4. Variant response_body schema validity ─────────────────────────────

def _expected_response_keys(url_pattern: str) -> set[str] | None:
    """Infer the real top-level response key for a Gmail mutation endpoint."""
    normalized = url_pattern.rstrip("*").rstrip("/")

    if "/api/env/amazon/cart" in normalized:
        return {"cart_item"}
    if "/api/env/amazon/products/" in normalized and "/reviews" in normalized:
        return {"review"}
    if "/api/env/amazon/returns" in normalized:
        return {"return"}
    if "/api/env/booking/notifications/read-all" in normalized:
        return {"ok", "marked_read"}
    if (
        "/api/env/booking/account" in normalized
        or "/api/env/booking/preferences" in normalized
        or "/api/env/booking/reviews" in normalized
        or "/api/env/booking/settings" in normalized
        or "/api/env/robinhood/settings" in normalized
        or "/api/env/robinhood/security/2fa" in normalized
    ):
        return None
    if "/api/env/lms/messages/send" in normalized:
        return {"message"}
    if normalized.endswith("/send"):
        return {"email"}
    if normalized.endswith("/settings"):
        return {"settings"}
    if "/emails/" in normalized and normalized.endswith(
        ("/read", "/star", "/label", "/archive", "/delete", "/forward")
    ):
        return {"email"}
    if normalized.endswith("/labels") or "/labels/" in normalized:
        return {"label"}
    if normalized.endswith("/filters") or "/filters/" in normalized:
        return {"filter"}
    if normalized.endswith("/contacts") or "/contacts/" in normalized:
        return {"contact"}
    return None


def test_variant_silent_fail_response_has_correct_top_level_key() -> None:
    """Silent-fail response_body must use the same top-level key as the real API.

    E.g. a fake /send response needs ``{"email": {...}}``, not ``{"success": true}``.
    If the SPA parses the response for state updates, a wrong key means the
    fake response is structurally broken (SPA ignores it = no-op variant).
    """
    warnings: list[str] = []
    for fname, variant in ALL_VARIANTS:
        vid = variant.get("variant_id", fname)
        for inj in variant.get("injections", []):
            if inj.get("layer") != "network":
                continue
            params = inj.get("params", {})
            if params.get("action") != "silent_fail":
                continue
            url_pat = params.get("url_pattern", "")
            resp = params.get("response_body", {})
            if not isinstance(resp, dict):
                continue

            expected = _expected_response_keys(url_pat)
            if expected:
                actual = set(resp.keys())
                if not expected.intersection(actual):
                    warnings.append(
                        f"[{vid}] silent_fail on {url_pat}: response keys "
                        f"{actual} don't include expected {expected}"
                    )
    assert not warnings, "\n".join(warnings)


def test_filter_silent_fail_payloads_include_required_filter_fields() -> None:
    """Fake filter responses must be structurally valid for the Settings UI.

    The Settings page renders created filters immediately and expects arrays
    like ``add_labels`` to exist. Returning ``{"filter": {"id": ...}}`` can
    break the page after a silent-fail instead of testing verification.
    """
    required_keys = {
        "id",
        "name",
        "query",
        "from_addresses",
        "subject_keywords",
        "label_requirements",
        "add_labels",
        "archive",
        "mark_read",
        "forward_to",
        "star",
        "never_spam",
    }
    violations: list[str] = []
    for fname, variant in ALL_VARIANTS:
        vid = variant.get("variant_id", fname)
        for inj in variant.get("injections", []):
            if inj.get("layer") != "network":
                continue
            params = inj.get("params", {})
            if params.get("action") != "silent_fail":
                continue
            if "/filters" not in str(params.get("url_pattern", "")):
                continue

            response_body = params.get("response_body", {})
            if not isinstance(response_body, dict):
                continue
            fake_filter = response_body.get("filter")
            if not isinstance(fake_filter, dict):
                violations.append(f"[{vid}] missing filter object in fake filter response")
                continue

            missing = sorted(required_keys - set(fake_filter.keys()))
            if missing:
                violations.append(f"[{vid}] fake filter payload missing keys: {missing}")
                continue

            for key in ("from_addresses", "subject_keywords", "label_requirements", "add_labels"):
                if not isinstance(fake_filter.get(key), list):
                    violations.append(f"[{vid}] fake filter payload field '{key}' must be a list")
    assert not violations, "\n".join(violations)


# ── 5. Variant base_task_id references valid tasks ───────────────────────

def test_variant_base_task_ids_exist() -> None:
    """Every variant's base_task_id must reference an actual task."""
    violations: list[str] = []
    for fname, variant in ALL_VARIANTS:
        btid = variant.get("base_task_id", "")
        if btid and btid not in ALL_TASKS:
            violations.append(f"[{fname}] base_task_id '{btid}' not found in tasks")
    assert not violations, "\n".join(violations)
