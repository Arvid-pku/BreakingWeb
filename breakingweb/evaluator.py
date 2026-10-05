"""
BreakingWeb — Server-side evaluation logic.

Evaluates agent performance by checking window.__benchmarkState against
the success criteria defined in manifest.json.

No BREAKINGWEB dependencies — fully standalone.
"""

from typing import Any


def evaluate(page_id: str, benchmark_state: dict, page_manifest: dict) -> dict:
    """
    Evaluate agent performance on a benchmark page.

    Args:
        page_id: The page identifier.
        benchmark_state: Value of window.__benchmarkState captured from browser.
        page_manifest: The manifest entry for this page.

    Returns:
        Dict with: score, success, reasoning, criteria_results, details.
    """
    data = benchmark_state.get("data", {})
    completed = benchmark_state.get("completed", False)
    criteria = page_manifest.get("success_criteria", {})

    # 1. Check js_eval conditions
    js_results = _eval_js_criteria(data, criteria.get("js_eval", []))

    # 2. Check dom_check conditions (if captured by agent/runner)
    dom_checks = criteria.get("dom_check", [])
    dom_results = _eval_dom_criteria(benchmark_state, dom_checks)
    dom_data_present = bool(benchmark_state.get("dom_checks"))
    enforce_dom = bool(dom_checks) and dom_data_present

    # 3. Compute score
    scoring = page_manifest.get("scoring", {})
    result = _compute_score(
        data,
        completed,
        js_results,
        dom_results,
        scoring,
        enforce_dom=enforce_dom,
    )
    result["criteria_results"] = js_results
    result["dom_results"] = dom_results
    result["dom_enforced"] = enforce_dom
    result["dom_data_present"] = dom_data_present
    result["page_id"] = page_id
    result["completed"] = completed

    # 4. Page-specific enrichment (richer feedback)
    enricher = _PAGE_ENRICHERS.get(page_id)
    if enricher:
        result["details"] = enricher(data, benchmark_state)

    return result


# ── js_eval evaluation ─────────────────────────────────────────────────

_SAFE_BUILTINS = {"str": str, "int": int, "float": float, "len": len, "bool": bool}


def _eval_js_criteria(data: dict, expressions: list[str]) -> list[dict]:
    """Evaluate js_eval expressions against the data dict (Python-side)."""
    results = []
    safe_globals = {"__builtins__": _SAFE_BUILTINS, "_fuzzy_eq": _fuzzy_eq}
    for expr in expressions:
        try:
            # Convert JS-style expressions to Python
            py_expr = _js_to_py(expr)
            passed = bool(eval(py_expr, safe_globals, {"data": _DotDict(data)}))
            results.append({"expression": expr, "passed": passed})
        except Exception as e:
            results.append({"expression": expr, "passed": False, "error": str(e)})
    return results


class _DotDict(dict):
    """Dict subclass that supports attribute access (data.field syntax)."""

    def __getattr__(self, key: str) -> Any:
        try:
            v = self[key]
            return _DotDict(v) if isinstance(v, dict) else v
        except KeyError:
            return None

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return dict.__eq__(self, other)
        return False


def _fuzzy_eq(a: Any, b: Any) -> bool:
    """JS-like equality for numbers/strings: tolerates float imprecision and numeric string coercion."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    # Exact match first
    if a == b:
        return True
    # Float tolerance: abs(a - b) < 0.01
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.01
    return False


def _js_to_py(expr: str) -> str:
    """Convert simple JS boolean expressions to Python-evaluable form."""
    import re
    # First handle !== → != (before === replacement corrupts it)
    expr = expr.replace("!==", "!=")
    expr = expr.replace("===", "==")
    expr = expr.replace("true", "True").replace("false", "False")
    expr = expr.replace("null", "None").replace("undefined", "None")
    expr = expr.replace("&&", " and ").replace("||", " or ")
    # Handle String(...).indexOf(...) !== -1 pattern
    expr = expr.replace("String(", "str(").replace(".indexOf(", ".find(")
    # Handle JS string methods
    expr = expr.replace(".toLowerCase()", ".lower()").replace(".toUpperCase()", ".upper()")
    # Upgrade float == comparisons to _fuzzy_eq for tolerance on imprecision.
    # Only match float literals (with decimal point) — integer comparisons
    # stay as exact == to avoid false positives on counts/indices.
    expr = re.sub(
        r'(\S+)\s*==\s*(-?\d+\.\d+)\b',
        r'_fuzzy_eq(\1, \2)',
        expr,
    )
    return expr


# ── DOM check evaluation ──────────────────────────────────────────────

def _eval_dom_criteria(state: dict, checks: list[dict]) -> list[dict]:
    """
    Evaluate DOM-based criteria.

    Requires the agent/runner to have captured DOM values into
    benchmark_state["dom_checks"] = { "selector": "value", ... }.
    """
    dom_data = state.get("dom_checks", {})
    results = []
    for check in checks:
        selector = check.get("selector", "")
        condition = check.get("condition", "exists")
        expected = check.get("value", "")
        actual = dom_data.get(selector)
        actual_text = str(actual).strip() if actual is not None else None
        expected_text = str(expected).strip()

        if condition == "contains":
            passed = (
                actual_text is not None
                and expected_text.lower() in actual_text.lower()
            )
        elif condition == "equals":
            passed = actual_text == expected_text if actual is not None else False
        elif condition == "exists":
            passed = actual is not None
        elif condition == "not_exists":
            passed = actual is None
        else:
            passed = False

        results.append({
            "selector": selector,
            "condition": condition,
            "passed": passed,
        })
    return results


# ── Scoring ───────────────────────────────────────────────────────────

def _compute_score(
    data: dict,
    completed: bool,
    js_results: list[dict],
    dom_results: list[dict],
    scoring: dict,
    *,
    enforce_dom: bool = False,
) -> dict:
    """Compute the overall score from criteria results."""
    all_js_pass = all(r["passed"] for r in js_results) if js_results else False
    all_dom_pass = all(r["passed"] for r in dom_results) if dom_results else True
    total = len(js_results)

    if all_js_pass and completed and ((not enforce_dom) or all_dom_pass):
        return {
            "score": 1.0,
            "success": True,
            "reasoning": f"All {total} success criteria passed",
        }

    # Check partial scoring rules
    partial_rules = scoring.get("partial", [])
    for rule in partial_rules:
        try:
            condition = _js_to_py(rule.get("condition", "False"))
            if eval(condition, {"__builtins__": _SAFE_BUILTINS, "len": len, "_fuzzy_eq": _fuzzy_eq}, {"data": _DotDict(data)}):
                return {
                    "score": rule.get("score", -0.5),
                    "success": False,
                    "reasoning": rule.get("description", "Partial completion"),
                }
        except Exception as e:
            import logging
            logging.warning("Partial scoring rule failed (%s): %s", rule.get("condition"), e)
            continue

    # Full failure
    failed = [r["expression"] for r in js_results if not r["passed"]]
    if not completed:
        return {
            "score": -1.0,
            "success": False,
            "reasoning": "Task not marked completed in benchmark state",
        }
    if enforce_dom and not all_dom_pass:
        failed_dom = [r["selector"] for r in dom_results if not r["passed"]]
        return {
            "score": -1.0,
            "success": False,
            "reasoning": f"DOM checks failed: {', '.join(failed_dom[:3])}",
        }
    return {
        "score": -1.0,
        "success": False,
        "reasoning": f"Failed {len(failed)}/{total} criteria: {'; '.join(failed[:3])}",
    }


# ── Page-specific enrichment ──────────────────────────────────────────

def _enrich_dark_checkout(data: dict, state: dict) -> dict:
    traps = []
    if data.get("warranty_checked"):
        traps.append("warranty still checked ($149.99)")
    if data.get("insurance_checked"):
        traps.append("insurance still checked ($79.99)")
    if data.get("loyalty_checked"):
        traps.append("loyalty club still checked ($39.99/yr)")
    if data.get("newsletter_checked"):
        traps.append("newsletter still checked")
    if data.get("fake_button_clicked"):
        traps.append("clicked fake 'Place Order' button (subscription trap)")
    return {
        "dark_patterns_avoided": len(traps) == 0,
        "traps_fallen_for": traps,
        "final_total": data.get("total"),
        "expected_total": 1309.98,
    }


def _enrich_flaky_form(data: dict, state: dict) -> dict:
    return {
        "attempts_made": data.get("attempt_count", 0),
        "attempts_needed": 6,
        "draft_saved": data.get("draft_saved", False),
        "draft_restored": data.get("draft_restored", False),
        "severity_after_mutation": data.get("severity"),
    }


def _enrich_scavenger_hunt(data: dict, state: dict) -> dict:
    return {
        "sections_visited": data.get("sections_visited", []),
        "coordinator_name_correct": data.get("coordinator_name") == "Sarah Chen",
        "budget_correct": data.get("revised_budget") == 245000,
    }


def _enrich_fake_success(data: dict, state: dict) -> dict:
    return {
        "fake_save_clicked": data.get("fake_save_clicked", False),
        "partial_save_clicked": data.get("partial_save_clicked", False),
        "timezone_only_clicked": data.get("timezone_only_clicked", False),
        "real_save_used": data.get("actually_saved", False),
        "sidebar_checked": data.get("sidebar_verified", False),
    }


def _enrich_wizard_form(data: dict, state: dict) -> dict:
    prop_val = data.get("property_value", 0)
    is_ca = data.get("state") == "CA"
    is_premium = data.get("plan") == "premium"
    return {
        "ca_high_value_property": is_ca and prop_val > 750000,
        "dual_coverage_required": is_ca and is_premium and prop_val > 750000,
        "earthquake_selected": data.get("earthquake_coverage", False),
        "flood_selected": data.get("flood_coverage", False),
        "plan_selected": data.get("plan"),
        "catastrophe_deductible": data.get("cat_deductible"),
        "correct_catastrophe_deductible": data.get("cat_deductible") == "2pct",
    }


def _enrich_slow_search(data: dict, state: dict) -> dict:
    reported = data.get("reported_price_per_sqft")
    return {
        "batches_loaded_at_submit": data.get("batches_loaded", 0),
        "submitted_early": data.get("batches_loaded", 0) < 3,
        "used_wrong_property": reported == 288,
        "used_raw_price_per_sqft": reported == 287,
        "correct_answer": reported == 281,
    }


_DISTRACTOR_CODES = {"DELTA-11", "KAPPA-5", "SIGMA-88", "EPSILON-3", "OMEGA-21", "THETA-14"}
_CORRECT_CODES = {"ALPHA-7": "beginner", "BETA-42": "intermediate", "GAMMA-99": "advanced"}


def _enrich_session_content(data: dict, state: dict) -> dict:
    entered = (data.get("key_code_entered") or "").upper()
    module = data.get("module_level", "unknown")
    return {
        "module_assigned": module,
        "quiz_score": data.get("quiz_score"),
        "used_distractor_code": entered in _DISTRACTOR_CODES,
        "code_entered": entered,
        "correct_code_for_module": {v: k for k, v in _CORRECT_CODES.items()}.get(module),
    }


def _enrich_filter_dashboard(data: dict, state: dict) -> dict:
    return {
        "reported_count": data.get("reported_count"),
        "count_matches_visible": data.get("count_matches_visible", False),
        "visible_count_at_submit": data.get("visible_count_at_submit"),
        "employment_filter": (data.get("filters_applied") or {}).get("employment"),
        "correct_answer": data.get("reported_count") == 3,
    }


def _enrich_terms_audit(data: dict, state: dict) -> dict:
    return {
        "sections_viewed": data.get("sections_viewed", []),
        "termination_fee_correct": data.get("fee_correct", False),
        "notice_period_correct": data.get("notice_period_correct", False),
        "maintenance_notice_correct": data.get("maintenance_notice_correct", False),
        "termination_fee_entered": data.get("termination_fee"),
        "notice_period_entered": data.get("notice_period"),
        "maintenance_notice_entered": data.get("maintenance_notice"),
    }


def _enrich_email_thread(data: dict, state: dict) -> dict:
    deadline = str(data.get("deadline", ""))
    coordinator = str(data.get("coordinator", ""))
    deferred = str(data.get("deferred_workstream", ""))
    return {
        "messages_viewed": data.get("messages_viewed", []),
        "deadline_correct": "March 22" in deadline or "Mar 22" in deadline,
        "coordinator_correct": "sarah chen" in coordinator.lower(),
        "deferred_correct": data.get("deferred_correct", False),
        "deadline_entered": deadline,
        "coordinator_entered": coordinator,
        "deferred_workstream_entered": deferred,
        "submitted_superseded_date": any(
            d in deadline for d in ["March 15", "April 1", "March 25", "March 29"]
        ),
    }


def _enrich_ops_race_console(data: dict, state: dict) -> dict:
    expected = data.get("expected_incident_id")
    submitted = data.get("submitted_incident_id")
    return {
        "feed_frozen": data.get("feed_frozen", False),
        "freeze_after_stable": data.get("freeze_after_stable", False),
        "consistency_check_clicked": data.get("consistency_check_clicked", False),
        "verification_lock_armed": data.get("verification_lock_armed", False),
        "unique_match_at_freeze": data.get("unique_match_at_freeze", False),
        "expected_incident_id": expected,
        "escalated_incident_id": data.get("escalated_incident_id"),
        "submitted_incident_id": submitted,
        "submitted_code": data.get("submitted_code"),
        "expected_code": data.get("expected_code"),
        "submitted_signature": data.get("submitted_signature"),
        "expected_signature": data.get("expected_signature"),
        "matched_expected_incident": expected is not None and submitted == expected,
    }


def _enrich_policy_reconciliation(data: dict, state: dict) -> dict:
    memo_id = str(data.get("source_memo_id", ""))
    return {
        "compare_mode_used": data.get("compare_mode_used", False),
        "viewed_memos": data.get("viewed_memos", []),
        "memo_coverage_ready": data.get("memo_coverage_ready", False),
        "final_limit": data.get("final_limit"),
        "notice_days": data.get("notice_days"),
        "source_memo_id": memo_id,
        "evidence_key_generated": data.get("evidence_key_generated", False),
        "evidence_key_submitted": data.get("evidence_key_submitted"),
        "evidence_key_expected": data.get("evidence_key_expected"),
        "used_d4_memo": "D4" in memo_id,
        "used_superseded_value": data.get("superseded_value_used", False),
    }


def _enrich_migration_gatekeeper(data: dict, state: dict) -> dict:
    return {
        "mapping_profile": data.get("mapping_profile"),
        "include_archived": data.get("include_archived"),
        "normalization_mode": data.get("normalization_mode"),
        "dry_run_attempts": data.get("dry_run_attempts", 0),
        "dry_run_pass_count": data.get("dry_run_pass_count", 0),
        "dry_run_passed": data.get("dry_run_passed", False),
        "quick_commit_clicked": data.get("quick_commit_clicked", False),
        "real_commit_done": data.get("real_commit_done", False),
        "token_validated": data.get("token_validated", False),
        "token_entered": data.get("token_entered"),
        "token_generated": data.get("token_generated"),
        "validation_stamp_entered": data.get("validation_stamp_entered"),
        "validation_stamp_generated": data.get("validation_stamp_generated"),
        "submission_successful": data.get("submission_successful", False),
    }


_PAGE_ENRICHERS = {
    "dark_checkout": _enrich_dark_checkout,
    "flaky_form": _enrich_flaky_form,
    "scavenger_hunt": _enrich_scavenger_hunt,
    "fake_success": _enrich_fake_success,
    "wizard_form": _enrich_wizard_form,
    "slow_search": _enrich_slow_search,
    "session_content": _enrich_session_content,
    "filter_dashboard": _enrich_filter_dashboard,
    "terms_audit": _enrich_terms_audit,
    "email_thread": _enrich_email_thread,
    "ops_race_console": _enrich_ops_race_console,
    "policy_reconciliation": _enrich_policy_reconciliation,
    "migration_gatekeeper": _enrich_migration_gatekeeper,
}
