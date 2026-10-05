"""Regression audit for task-standard coverage on previously weak tasks.

These checks are intentionally high-signal and task-specific. They lock in
the outcome-grading and wrong-trajectory requirements from
``share_docs/TASK_GENERATION_STANDARD.md`` for tasks that previously allowed
partial or collateral completions to slip through.
"""

from __future__ import annotations

from typing import Any

from breakingweb.tasks._registry import load_all_tasks


def _task(task_id: str) -> Any:
    return load_all_tasks()[task_id]


def _exprs(task_id: str, phase: str | None = None) -> list[str]:
    task = _task(task_id)
    cd = getattr(task, "canonical_diff", None)
    if cd is not None:
        blocks = list(cd.oneof) if cd.oneof else [cd]
        chunks: list[str] = []
        for block in blocks:
            for entry in [*block.create, *block.update, *block.delete]:
                for pred_map in (
                    getattr(entry, "properties", None),
                    getattr(entry, "where", None),
                    getattr(entry, "changes", None),
                ):
                    if pred_map:
                        chunks.append(str(pred_map))
                bijection = getattr(entry, "bijection", None)
                if bijection is not None:
                    chunks.append(bijection.over)
            for inv in block.invariant:
                chunks.append(inv.collection)
                if inv.filter:
                    chunks.append(inv.filter)
            for constraint in block.constraints:
                chunks.append(constraint.expr)
        return chunks

    ev = getattr(task, "eval", None)
    if ev is None:
        return []

    if phase == "checks":
        items = getattr(ev, "checks", []) or []
    elif phase == "negative_checks":
        items = getattr(ev, "negative_checks", []) or []
    else:
        items = (getattr(ev, "checks", []) or []) + (getattr(ev, "negative_checks", []) or [])
    return [item.expr for item in items]


def _descs(task_id: str, phase: str | None = None) -> list[str]:
    task = _task(task_id)
    cd = getattr(task, "canonical_diff", None)
    if cd is not None:
        blocks = list(cd.oneof) if cd.oneof else [cd]
        chunks: list[str] = []
        for block in blocks:
            for entry in [*block.create, *block.update, *block.delete]:
                if getattr(entry, "desc", None):
                    chunks.append(entry.desc)
            for constraint in block.constraints:
                chunks.append(constraint.desc)
            for named in block.named_invariants:
                chunks.append(named.name)
        return chunks

    ev = getattr(task, "eval", None)
    if ev is None:
        return []

    if phase == "checks":
        items = getattr(ev, "checks", []) or []
    elif phase == "negative_checks":
        items = getattr(ev, "negative_checks", []) or []
    else:
        items = (getattr(ev, "checks", []) or []) + (getattr(ev, "negative_checks", []) or [])
    return [item.desc for item in items]


def _instruction(task_id: str) -> str:
    task = _task(task_id)
    return (
        getattr(task, "instruction_template", None)
        or getattr(task, "instruction", None)
        or ""
    ).lower()


def _has_canonical_diff_negative_coverage(task_id: str) -> bool:
    """canonical_diff tasks get negative coverage from invariant/constraint entries
    rather than from legacy ``eval.negative_checks``. An invariant on any populated
    collection (or a constraint expression) counts as an explicit negative guard."""
    cd = getattr(_task(task_id), "canonical_diff", None)
    if cd is None:
        return False
    blocks = list(cd.oneof) if cd.oneof else [cd]
    for block in blocks:
        if block.invariant or block.constraints or block.named_invariants:
            return True
    return False


def test_every_task_has_wrong_trajectory_coverage() -> None:
    """Every task should have at least one explicit negative guard.

    For legacy-eval tasks the guard lives in ``eval.negative_checks``. For
    migrated tasks with a ``canonical_diff`` block it lives in
    ``canonical_diff.invariant`` / ``constraints`` / ``named_invariants``.
    """
    for task_id in load_all_tasks():
        if _has_canonical_diff_negative_coverage(task_id):
            continue
        assert _exprs(task_id, "negative_checks"), f"{task_id} is missing negative coverage"


def test_exclusive_instructions_have_cardinality_or_exclusion_guards() -> None:
    """Tasks with exclusivity language should grade exclusivity explicitly."""
    keywords = (" exactly ", " only ", " none ", " do not ", " leave ", " no other ")
    guard_tokens = (
        "len(",
        "sum(",
        "count(",
        "not any",
        "not in",
        "!=",
        "id ==",
        "set(",
        "forwarded_from_id",
        "linked_entity_id",
        "decoy",
        "unchanged",
        "not accidentally",
        "not modified",
        "no extra",
        "wrong",
        "collateral",
    )
    for task_id, task in load_all_tasks().items():
        if getattr(task, "eval", None) is None:
            continue
        instruction = f" {_instruction(task_id)} "
        if not any(keyword in instruction for keyword in keywords):
            continue

        # canonical_diff tasks enforce cardinality through bijection counts and
        # scoped invariants; the named_invariants labels make the exclusivity
        # claims visible. Treat the presence of those structures as sufficient.
        if _has_canonical_diff_negative_coverage(task_id):
            continue

        exprs = _exprs(task_id)
        neg_exprs = _exprs(task_id, "negative_checks")
        blob = "\n".join(exprs + _descs(task_id)).lower()
        assert neg_exprs, f"{task_id} uses exclusivity language but has no negative coverage"
        assert len(exprs) >= 3 or any(token in blob for token in guard_tokens), (
            f"{task_id} uses exclusivity language but lacks explicit exclusion/cardinality grounding "
            "or enough independent checks"
        )


def test_reddit_frontier_workflows_have_specific_collateral_guards() -> None:
    """Large Reddit workflows must guard more than generic message/post counts."""
    task_ids = [
        "reddit_platform_migration",
        "reddit_full_platform_overhaul",
        "reddit_community_builder",
        "reddit_messaging_workflow",
        "reddit_search_and_engage",
        "reddit_thread_participation",
    ]
    for task_id in task_ids:
        neg_exprs = _exprs(task_id, "negative_checks")
        neg_blob = "\n".join(neg_exprs + _descs(task_id, "negative_checks")).lower()
        assert len(neg_exprs) >= 2, f"{task_id} should keep multiple negative guards"
        assert any(
            token in neg_blob
            for token in (
                "saved_post_ids",
                "is_subscribed",
                "vote_direction",
                "sent_messages",
                "state.messages",
                "to_user",
                "notifications",
                "comments",
            )
        ), f"{task_id} still lacks object-specific negative coverage"


def _canonical_diff_order_predicate_blob(task_id: str) -> str:
    """Render every ``Order`` create/update entry's properties and where clauses
    as a flat string so cardinality / item-membership assertions can grep it."""
    cd = getattr(_task(task_id), "canonical_diff", None)
    if cd is None:
        return ""
    blocks = list(cd.oneof) if cd.oneof else [cd]
    chunks: list[str] = []
    for block in blocks:
        for entry in block.create:
            if entry.entity != "Order":
                continue
            chunks.append(str(entry.properties))
        for entry in block.update:
            if entry.entity != "Order":
                continue
            chunks.append(str(entry.where))
            chunks.append(str(entry.changes))
        for c in block.constraints:
            chunks.append(c.expr)
    return "\n".join(chunks).lower()


def test_amazon_order_integrity_tasks_require_exact_order_contents() -> None:
    """Purchase workflows must reject collateral items riding along in the order.

    Legacy tasks do this via ``order.items`` / ``len(order.items)`` eval exprs.
    Migrated canonical_diff tasks express it via the Order create entry's
    ``items`` predicate (e.g. ``{expr: "any(it['product_id'] == ... for it in x)"}``
    plus cardinality constraints). Accept either shape.
    """
    task_ids = [
        "amazon_compare_and_buy_cheapest",
        "amazon_wishlist_to_cart",
        "amazon_multi_order_workflow",
        "amazon_account_overhaul_and_shop",
    ]
    for task_id in task_ids:
        cd_blob = _canonical_diff_order_predicate_blob(task_id)
        legacy_blob = "\n".join(_exprs(task_id)).lower()
        blob = cd_blob + "\n" + legacy_blob
        assert (
            "order.items" in blob
            or "o.items" in blob
            or "'items'" in cd_blob
            or "items:" in cd_blob
            or "for it in x" in cd_blob        # iterate Order.items via `x`
            or "x[0][" in cd_blob              # indexed Order.items access
        ), f"{task_id} should inspect order item membership directly"
        exact_contents_tokens = (
            "len(order.items)",
            "len(o.items)",
            "set(item.product_id",
            "sorted(item.product_id",
            "'length':",          # canonical_diff length predicate
            "'set_eq':",          # canonical_diff set_eq predicate
            "len(x) ==",          # tight cardinality on Order.items
            "len(x)==",
        )
        assert any(tok in blob for tok in exact_contents_tokens), (
            f"{task_id} should enforce exact order contents, not supersets"
        )


def test_lms_reporting_tasks_bind_recipient_and_required_facts() -> None:
    """LMS reporting tasks must prove the message went to the right recipient."""
    recipient_bound = {
        "lms_check_assignment_grade": ("score_below_70", "unsubmitted_hw_id", "announcement"),
        "lms_check_course_grade": ("grade_below_80", "unsubmitted_hw_id", "announcement"),
        "lms_calculate_weighted_grade": ("has_discrepancy", "most_recent_graded_id", "announcement"),
        "lms_compare_course_grades": ("lower_grade_enrollment_id", "dropped"),
        "lms_find_next_deadline": ("next_deadline_assignment_id", "early_draft"),
        "lms_grade_with_curve": ("curve_changes_letter", "exam_assignment_id", "curve"),
    }
    for task_id, required_tokens in recipient_bound.items():
        blob = "\n".join(_exprs(task_id)).lower()
        for token in required_tokens:
            assert token.lower() in blob, f"{task_id} is missing required eval grounding token: {token}"


def test_booking_rebooking_tasks_bind_exact_reservation_identity() -> None:
    """Booking workflows must lock onto the exact room/cardinality outcome.

    Obsolete post canonical_diff migration: both tasks now use canonical_diff
    bindings (room_type_name / payment_method_id / reservation cardinality)
    enforced by their per-task canonical_diff tests + the adversarial battery.
    Retained as a skip so git blame still surfaces the original intent.
    """
    for task_id in ("booking_cancel_rebook_cheaper", "booking_find_genius_deal"):
        assert _task(task_id).eval is None, (
            f"{task_id} still has legacy eval — this audit should be re-enabled"
        )


def test_robinhood_alert_and_limit_tasks_bind_trigger_math_and_order_timing() -> None:
    """Robinhood evaluators must prove the requested price math and sequence."""
    checks = {
            "rh_limit_order_with_check": ("limit_price", "decimal('0.95')", "exactly one amzn"),
            "rh_find_earnings_and_alert": ("portfolio_symbols_with_earnings_within(7)", "0.95"),
            "rh_live_alert_and_buy": ("triggered_at", "created_at > a.triggered_at"),
            "rh_live_alert_and_sell": ("triggered_at",),
            "rh_live_alert_chain": ("sector_pct('technology')", "nvda"),
            "rh_live_cross_stock_alert": ("triggered_at", "max(a.triggered_at"),
            "rh_live_watch_portfolio": ("decimal('14700')", "get_position(target['best_symbol']) is none"),
            "rh_live_buy_the_dip": ("filled_tick", "filled_price is not none and o.filled_price <= decimal('180')"),
            "rh_live_watch_and_buy": ("filled_tick", "price_at_tick('aapl', o.filled_tick) < decimal('182')"),
        "rh_live_watch_spread": ("filled_tick", "price_at_tick('tsla',", "decimal('255')"),
        "rh_live_intraday_reversal": ("filled_tick", "price_at_tick('nvda',", "decimal('845')"),
        }
    for task_id, required_tokens in checks.items():
        blob = "\n".join(_exprs(task_id) + _descs(task_id)).lower()
        for token in required_tokens:
            assert token.lower() in blob, f"{task_id} is missing trigger/timing token: {token}"


def test_patient_portal_claim_and_screening_tasks_bind_exact_target_sets() -> None:
    """Patient portal tasks must reject partial or wrong-claim completions."""
    checks = {
        "pp_pay_claim": ("initial.get_claim", "approved_claim_ids"),
        "pp_dispute_claim": ("initial.get_claim", "denied_claim_ids"),
        "pp_reconcile_billing": ("billing_provider_ids", "missing claim review"),
        "pp_preventive_screening_review": ("overdue_screening_names", "messages"),
    }
    for task_id, required_tokens in checks.items():
        blob = "\n".join(_exprs(task_id)).lower()
        for token in required_tokens:
            assert token.lower() in blob, f"{task_id} is missing target-set coverage token: {token}"
