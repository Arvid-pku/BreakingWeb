from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from breakingweb.backend.models.amazon import PromoCode
from breakingweb.backend.routes.amazon import (
    ApplyPromoRequest,
    ClearPromoRequest,
    PlaceOrderRequest,
    SessionCreateRequest,
    apply_promo,
    clear_promo,
    create_session,
    get_cart,
    get_order,
    place_order,
)
from breakingweb.backend.state import SessionManager
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import env_tasks, get_task


_AMAZON_TASK_IDS = [task.task_id for task in env_tasks("amazon")]


@pytest.mark.parametrize("task_id", _AMAZON_TASK_IDS)
def test_amazon_session_create_succeeds(task_id: str) -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(task_id=task_id, seed=42),
        session_manager=session_manager,
    )

    assert payload["session_id"]
    assert "{output." not in payload["instruction"]
    assert "task_id" not in payload
    assert "seed" not in payload


# Errors that canonical_diff's match_diff surfaces when a check fails on the
# initial (empty-trajectory) state. These are logical mismatches, not Python
# exceptions — the evaluator ran cleanly, the seeded state simply doesn't
# satisfy the create/update/delete predicates. Distinguishing these from real
# expression-level errors keeps the test honest about what it's guarding.
_CANONICAL_DIFF_LOGICAL_ERRORS = (
    "no candidate satisfied predicates",
    "no Update entry matched both where and changes predicates",
    "no Delete entry matched the where selector",
)


def _is_real_expression_error(error: str | None) -> bool:
    if not error:
        return False
    if error in _CANONICAL_DIFF_LOGICAL_ERRORS:
        return False
    # Bijection partial match is a logical outcome, not a crash.
    if error.startswith("matched ") and " of " in error:
        return False
    return True


@pytest.mark.parametrize("task_id", _AMAZON_TASK_IDS)
def test_amazon_seeded_evaluator_has_no_expression_errors(task_id: str) -> None:
    session_manager = SessionManager()
    payload = create_session(
        SessionCreateRequest(task_id=task_id, seed=42),
        session_manager=session_manager,
    )
    state = session_manager.get(payload["session_id"])

    result = evaluate(
        get_task(task_id),
        server_state=state,
        targets=state.resolved_targets,
        trajectory=[],
    )

    assert not [
        check for check in result["checks"]
        if _is_real_expression_error(check.get("error"))
    ]
    assert not [
        check for check in result["negative_checks"]
        if _is_real_expression_error(check.get("error"))
    ]



def test_amazon_promo_apply_clear_and_checkout_are_consistent() -> None:
    session_manager = SessionManager()
    payload = create_session(
        SessionCreateRequest(task_id="amazon_checkout_with_new_address", seed=42),
        session_manager=session_manager,
    )
    session_id = payload["session_id"]
    state = session_manager.get(session_id)
    state.promo_codes.append(
        PromoCode(
            id="promo_1",
            code="SAVE10",
            discount_type="percentage",
            discount_value=10.0,
            min_order_amount=0.0,
            max_uses=5,
            used_count=0,
            valid_until=datetime.now(timezone.utc) + timedelta(days=7),
            active=True,
        )
    )

    before = get_cart(session_id=session_id, session_manager=session_manager)
    apply_promo(
        ApplyPromoRequest(session_id=session_id, code="SAVE10"),
        session_manager=session_manager,
    )
    after_apply = get_cart(session_id=session_id, session_manager=session_manager)

    assert before["totals"]["discount"] == 0.0
    assert after_apply["totals"]["discount"] > 0.0
    assert state.applied_promo_code == "SAVE10"
    assert state.get_promo_code("SAVE10").used_count == 0

    clear_promo(
        ClearPromoRequest(session_id=session_id),
        session_manager=session_manager,
    )
    after_clear = get_cart(session_id=session_id, session_manager=session_manager)

    assert after_clear["totals"]["discount"] == 0.0
    assert state.applied_promo_code is None

    apply_promo(
        ApplyPromoRequest(session_id=session_id, code="SAVE10"),
        session_manager=session_manager,
    )
    order = place_order(
        PlaceOrderRequest(
            session_id=session_id,
            shipping_address_id=state.addresses[0].id,
            payment_method_id=state.payment_methods[0].id,
            promo_code="SAVE10",
        ),
        session_manager=session_manager,
    )["order"]

    assert order["discount"] > 0.0
    assert order["promo_code"] == "SAVE10"
    assert state.get_promo_code("SAVE10").used_count == 1
    assert state.applied_promo_code is None
