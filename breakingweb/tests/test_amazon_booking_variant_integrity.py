from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from breakingweb.tasks._registry import env_tasks, get_task


VARIANTS_DIR = Path(__file__).resolve().parents[1] / "injector" / "variants"
ENV_TASK_IDS = {
    "amazon": {task.task_id for task in env_tasks("amazon")},
    "booking": {task.task_id for task in env_tasks("booking")},
}


def _variant_paths() -> list[Path]:
    return sorted(VARIANTS_DIR.glob("amazon_*.yaml")) + sorted(VARIANTS_DIR.glob("booking_*.yaml"))


def _load_variant(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    assert isinstance(raw, dict), f"{path.name} must parse to a mapping"
    return raw


def _env_for_path(path: Path) -> str:
    if path.name.startswith("amazon_"):
        return "amazon"
    if path.name.startswith("booking_"):
        return "booking"
    raise AssertionError(f"unexpected variant path: {path.name}")


def test_amazon_booking_variants_bind_real_tasks_and_declared_primitives() -> None:
    violations: list[str] = []
    for path in _variant_paths():
        env = _env_for_path(path)
        variant = _load_variant(path)
        base_task_id = variant.get("base_task_id")
        if base_task_id not in ENV_TASK_IDS[env]:
            violations.append(f"[{path.name}] base_task_id {base_task_id!r} is not a real {env} task")
            continue

        task = get_task(base_task_id)
        primitive_set = set(task.primary_primitives or []) | set(task.secondary_primitives or [])
        target_primitive = variant.get("target_primitive")
        if target_primitive not in primitive_set:
            violations.append(
                f"[{path.name}] target_primitive {target_primitive!r} is not declared by {base_task_id}: "
                f"{sorted(primitive_set)}"
            )
        if not variant.get("injections"):
            violations.append(f"[{path.name}] must define at least one degradation injection")

    assert not violations, "\n".join(violations)


def _assert_mapping_keys(path: Path, payload: Any, required: set[str], label: str) -> None:
    assert isinstance(payload, dict), f"[{path.name}] {label} must be a mapping"
    missing = sorted(required - set(payload))
    assert not missing, f"[{path.name}] {label} missing required keys: {missing}"


def test_amazon_booking_silent_fail_responses_match_api_shapes() -> None:
    review_scores = {"staff", "facilities", "cleanliness", "comfort", "value_for_money", "location", "free_wifi"}
    booking_review = {
        "id",
        "property_id",
        "reservation_id",
        "author_name",
        "author_country",
        "overall_score",
        "scores",
        "title",
        "positive",
        "negative",
        "room_type",
        "travel_purpose",
        "traveled_with",
        "stay_date",
        "created_at",
        "helpful_count",
        "property_response",
    }
    booking_settings = {
        "id",
        "default_payment_id",
        "email_notifications",
        "deal_alerts",
        "review_reminders",
        "price_alerts",
        "newsletter",
        "sms_notifications",
        "language",
        "currency",
        "country",
        "two_factor_enabled",
    }
    booking_account = {"name", "email", "phone", "nationality", "date_of_birth", "gender", "address", "genius", "wallet"}
    booking_preferences = {
        "smoking",
        "preferred_bed_type",
        "floor_preference",
        "accessibility_needs",
        "preferred_room_type",
        "dietary_restrictions",
        "preferred_language",
        "preferred_currency",
    }
    amazon_cart_item = {"id", "product_id", "product_name", "quantity", "unit_price", "variant_selections", "added_at"}
    amazon_review = {
        "id",
        "product_id",
        "author_name",
        "rating",
        "title",
        "body",
        "created_at",
        "verified_purchase",
        "helpful_count",
    }
    amazon_return = {
        "id",
        "order_id",
        "order_item_index",
        "product_id",
        "product_name",
        "reason",
        "status",
        "refund_amount",
        "created_at",
        "resolution_note",
    }

    for path in _variant_paths():
        variant = _load_variant(path)
        for injection in variant.get("injections") or []:
            if injection.get("layer") != "network":
                continue
            params = injection.get("params") or {}
            if params.get("action") != "silent_fail":
                continue

            response_body = params.get("response_body")
            url_pattern = str(params.get("url_pattern", ""))
            assert isinstance(response_body, dict), f"[{path.name}] silent_fail on {url_pattern} needs response_body"

            if "/api/env/amazon/cart" in url_pattern:
                _assert_mapping_keys(path, response_body, {"cart_item"}, "response_body")
                _assert_mapping_keys(path, response_body["cart_item"], amazon_cart_item, "response_body.cart_item")
            elif "/api/env/amazon/products/" in url_pattern and "/reviews" in url_pattern:
                _assert_mapping_keys(path, response_body, {"review"}, "response_body")
                _assert_mapping_keys(path, response_body["review"], amazon_review, "response_body.review")
            elif "/api/env/amazon/returns" in url_pattern:
                _assert_mapping_keys(path, response_body, {"return"}, "response_body")
                _assert_mapping_keys(path, response_body["return"], amazon_return, "response_body.return")
            elif "/api/env/booking/reviews" in url_pattern:
                _assert_mapping_keys(path, response_body, booking_review, "response_body")
                _assert_mapping_keys(path, response_body["scores"], review_scores, "response_body.scores")
            elif "/api/env/booking/settings" in url_pattern:
                _assert_mapping_keys(path, response_body, booking_settings, "response_body")
            elif "/api/env/booking/preferences" in url_pattern:
                _assert_mapping_keys(path, response_body, booking_preferences, "response_body")
            elif "/api/env/booking/account" in url_pattern:
                _assert_mapping_keys(path, response_body, booking_account, "response_body")
                _assert_mapping_keys(
                    path,
                    response_body["genius"],
                    {"level", "total_bookings", "bookings_needed_for_next", "benefits"},
                    "response_body.genius",
                )
                _assert_mapping_keys(path, response_body["wallet"], {"balance", "currency", "transactions"}, "response_body.wallet")
            elif "/api/env/booking/notifications/read-all" in url_pattern:
                _assert_mapping_keys(path, response_body, {"ok", "marked_read"}, "response_body")
