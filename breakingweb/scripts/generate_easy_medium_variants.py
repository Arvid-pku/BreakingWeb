#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"
VARIANTS_DIR = ROOT / "injector" / "variants"

TARGET_ENVS = ("amazon", "booking", "gmail", "reddit", "robinhood")
TARGET_DIFFICULTIES = {"easy", "medium"}


def load_target_tasks() -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for env in TARGET_ENVS:
        for path in sorted((TASKS_DIR / env).glob("*.yaml")):
            raw = yaml.safe_load(path.read_text()) or {}
            if raw.get("difficulty") not in TARGET_DIFFICULTIES:
                continue
            raw["_path"] = path
            tasks[raw["task_id"]] = raw
    return tasks


def target_ref(task: dict[str, Any], *keys: str, fallback: str = "") -> str:
    targets = task.get("targets") or {}
    for key in keys:
        if key in targets:
            return f"{{target.{key}}}"
    return fallback


def first_step_param(
    task: dict[str, Any],
    key: str,
    *,
    uses: set[str] | None = None,
    default: Any = None,
) -> Any:
    for step in task.get("seed", {}).get("steps", []):
        if uses is not None and step.get("use") not in uses:
            continue
        params = step.get("params") or {}
        if key in params:
            return params[key]
    return default


def first_room_name(task: dict[str, Any], default: str = "Deluxe Room") -> str:
    for step in task.get("seed", {}).get("steps", []):
        params = step.get("params") or {}
        rooms = params.get("rooms")
        if isinstance(rooms, list):
            for room in rooms:
                if isinstance(room, dict) and room.get("name"):
                    return str(room["name"])
        if params.get("room_name"):
            return str(params["room_name"])
    return default


def property_names(task: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for step in task.get("seed", {}).get("steps", []):
        params = step.get("params") or {}
        name = params.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def reservation_params(task: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in task.get("seed", {}).get("steps", []):
        if step.get("use") == "create_reservation":
            rows.append(dict(step.get("params") or {}))
    return rows


def extract_symbols(task: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for step in task.get("seed", {}).get("steps", []):
        params = step.get("params") or {}
        for key in ("must_include", "symbols", "stocks"):
            value = params.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        candidates.append(item)
        value = params.get("symbol")
        if isinstance(value, str):
            candidates.append(value)
    if not candidates:
        text = task.get("instruction_template") or task.get("instruction") or ""
        candidates.extend(re.findall(r"\b[A-Z]{1,5}\b", text))
    stopwords = {"USD", "GTC", "CEO", "CFO", "Q1", "Q2", "Q3", "Q4"}
    seen: set[str] = set()
    symbols: list[str] = []
    for item in candidates:
        token = item.strip().upper()
        if (
            not token
            or token in stopwords
            or len(token) > 5
            or not token.isalpha()
            or token in seen
        ):
            continue
        seen.add(token)
        symbols.append(token)
    return symbols


def variant(
    task_id: str,
    suffix: str,
    primitive: str,
    description: str,
    injections: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "variant_id": f"{task_id}__{suffix}",
        "base_task_id": task_id,
        "target_primitive": primitive,
        "description": description,
        "injections": injections,
    }


def seed_injection(action: str, **params: Any) -> dict[str, Any]:
    return {"layer": "seed", "params": {"action": action, **params}}


def network_error(
    url_pattern: str,
    *,
    methods: list[str],
    error_count: int = 1,
    error_status: int = 503,
    error_message: str = "Temporary failure. Retry the request.",
) -> dict[str, Any]:
    return {
        "layer": "network",
        "params": {
            "action": "error_then_success",
            "url_pattern": url_pattern,
            "methods": methods,
            "error_count": error_count,
            "error_status": error_status,
            "error_message": error_message,
            "behavior": {"mode": "once"},
        },
    }


def network_delay(url_pattern: str, *, delay_ms: int = 2500) -> dict[str, Any]:
    return {
        "layer": "network",
        "params": {
            "action": "delay",
            "url_pattern": url_pattern,
            "delay_ms": delay_ms,
            "behavior": {
                "mode": "progressive",
                "stages": [
                    {"after_call": 0, "delay_ms": delay_ms // 2},
                    {"after_call": 3, "delay_ms": delay_ms},
                ],
            },
        },
    }


def network_stale(url_pattern: str, stale_body: dict[str, Any]) -> dict[str, Any]:
    return {
        "layer": "network",
        "params": {
            "action": "stale_data",
            "url_pattern": url_pattern,
            "stale_body": stale_body,
            "stale_count": 1,
            "behavior": {"mode": "once"},
        },
    }


def brand_suffix(brand: str, suffix: str) -> str:
    brand = brand.strip()
    return f"{brand} {suffix}".strip() if brand else suffix


def amazon_product_info(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": target_ref(task, "product_name", "best_value_name", fallback=str(first_step_param(
            task,
            "name",
            uses={"featured_product"},
            default="Target Product",
        ))),
        "brand": str(first_step_param(task, "brand", uses={"featured_product"}, default="Brand")),
        "category": target_ref(task, "category", fallback=str(first_step_param(
            task,
            "category",
            uses={"featured_product", "product_catalog"},
            default="Electronics",
        ))),
        "price": float(first_step_param(task, "price", uses={"featured_product"}, default=49.99)),
        "rating": float(first_step_param(task, "rating", uses={"featured_product"}, default=4.7)),
    }


def booking_property_info(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": target_ref(task, "property_name", "hotel_name", fallback=str(first_step_param(
            task,
            "name",
            uses={"featured_property", "decoy_property"},
            default="Target Property",
        ))),
        "city": target_ref(task, "city", fallback=str(first_step_param(
            task,
            "city",
            uses={"featured_property", "decoy_property"},
            default="Paris",
        ))),
        "country": str(first_step_param(
            task,
            "country",
            uses={"featured_property", "decoy_property"},
            default="France",
        )),
        "property_type": str(first_step_param(
            task,
            "property_type",
            uses={"featured_property", "decoy_property"},
            default="Hotel",
        )),
        "star_rating": int(first_step_param(
            task,
            "star_rating",
            uses={"featured_property", "decoy_property"},
            default=4,
        )),
        "review_score": float(first_step_param(
            task,
            "review_score",
            uses={"featured_property", "decoy_property"},
            default=8.7,
        )),
        "price": float(first_step_param(
            task,
            "price",
            uses={"featured_property", "decoy_property"},
            default=240.0,
        )),
        "room_name": target_ref(task, "room_name", fallback=first_room_name(task)),
    }


TICKER_LOOKALIKES: dict[str, list[dict[str, Any]]] = {
    "AAPL": [
        {"symbol": "AAPLX", "name": "Apple Holdings Trust", "price": 189.40},
        {"symbol": "APLE", "name": "Apple Hospitality REIT", "price": 16.90},
    ],
    "AMZN": [
        {"symbol": "AMZX", "name": "Amazon Extended Trust", "price": 168.20},
        {"symbol": "AMZD", "name": "Amazon Income Notes", "price": 43.10},
    ],
    "GOOGL": [
        {"symbol": "GOOGX", "name": "Alphabet Growth Trust", "price": 182.50},
        {"symbol": "GOOGQ", "name": "Alphabet Income Notes", "price": 51.30},
    ],
    "JNJ": [
        {"symbol": "JNJX", "name": "Johnson & Johnson Select", "price": 152.30},
        {"symbol": "JNJS", "name": "J&J Dividend Select", "price": 47.20},
    ],
    "KO": [
        {"symbol": "KOF", "name": "Coca-Cola Femsa", "price": 88.15},
        {"symbol": "KOX", "name": "Coca-Cola Income Trust", "price": 41.05},
    ],
    "META": [
        {"symbol": "METX", "name": "Meta Innovation Trust", "price": 512.80},
        {"symbol": "METAQ", "name": "Meta Income Notes", "price": 62.70},
    ],
    "MSFT": [
        {"symbol": "MSFY", "name": "Microsoft Yield Trust", "price": 96.10},
        {"symbol": "MSFX", "name": "Microsoft Extended Class", "price": 428.40},
    ],
    "NVDA": [
        {"symbol": "NVDL", "name": "NVIDIA 2x Leveraged ETF", "price": 72.40},
        {"symbol": "NVDS", "name": "NVIDIA Short Strategy ETF", "price": 16.30},
    ],
    "PEP": [
        {"symbol": "PEPX", "name": "PepsiCo Income Trust", "price": 55.20},
        {"symbol": "PEPG", "name": "PepsiCo Growth Notes", "price": 61.90},
    ],
    "PG": [
        {"symbol": "PGX", "name": "Invesco Preferred ETF", "price": 11.85},
        {"symbol": "PGY", "name": "Pagaya Technologies", "price": 15.40},
    ],
    "SCHD": [
        {"symbol": "SCHDX", "name": "Schwab Dividend Extended Trust", "price": 41.70},
        {"symbol": "SCHG", "name": "Schwab U.S. Large-Cap Growth ETF", "price": 103.50},
    ],
    "TSLA": [
        {"symbol": "TSLQ", "name": "Tesla Short Strategy ETF", "price": 18.10},
        {"symbol": "TSLL", "name": "Tesla 1.5x Long ETF", "price": 22.80},
    ],
    "VOO": [
        {"symbol": "VOOG", "name": "Vanguard S&P 500 Growth ETF", "price": 298.15},
        {"symbol": "VOOV", "name": "Vanguard S&P 500 Value ETF", "price": 164.30},
    ],
    "VTI": [
        {"symbol": "VTIQ", "name": "Legacy Total Market Acquisition", "price": 12.40},
        {"symbol": "VTWG", "name": "Vanguard Russell 2000 Growth ETF", "price": 157.10},
    ],
}


def ticker_decoys(symbols: list[str]) -> list[dict[str, Any]]:
    decoys: list[dict[str, Any]] = []
    for symbol in symbols:
        specs = TICKER_LOOKALIKES.get(symbol)
        if specs is None:
            specs = [
                {"symbol": f"{symbol}X", "name": f"{symbol} Extended Trust", "price": 92.40},
                {"symbol": f"{symbol}Q", "name": f"{symbol} Income Notes", "price": 37.60},
            ]
        decoys.extend(specs[:2])
    return decoys[:4]


def empty_page(*, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"items": [], "page": 1, "page_size": 25, "total": 0, "pages": 1}
    if extra:
        payload.update(extra)
    return payload


def amazon_product_twin(task: dict[str, Any]) -> dict[str, Any]:
    info = amazon_product_info(task)
    return variant(
        task["task_id"],
        "product_twin",
        "grounding",
        "Renewed and plus listings with nearly identical names sit beside the target item. The agent must match the exact product before acting.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "product",
                        "name": f"{info['name']} Plus",
                        "brand": brand_suffix(info["brand"], "Direct"),
                        "category": info["category"],
                        "price": round(info["price"] * 1.15, 2),
                        "rating": round(max(info["rating"] - 0.1, 4.0), 1),
                        "description": "Lookalike listing with slightly different packaging and model copy.",
                    },
                    {
                        "type": "product",
                        "name": f"{info['name']} (Renewed)",
                        "brand": brand_suffix(info["brand"], "Outlet"),
                        "category": info["category"],
                        "price": round(max(info["price"] * 0.82, 1.0), 2),
                        "rating": round(max(info["rating"] - 0.4, 3.8), 1),
                        "description": "Refurbished lookalike listing that is not the exact requested item.",
                    },
                ],
            )
        ],
    )


def amazon_cheapest_decoy(task: dict[str, Any]) -> dict[str, Any]:
    info = amazon_product_info(task)
    return variant(
        task["task_id"],
        "cheapest_decoy",
        "grounding",
        "Several low-priced lookalikes sit just above the real cheapest item. The agent must compare exact prices instead of trusting badges or visual prominence.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "product",
                        "name": f"{info['category']} Daily Pick",
                        "brand": "Amazon Choice",
                        "category": info["category"],
                        "price": round(info["price"] + 0.50, 2),
                        "rating": 4.8,
                        "description": "Highlighted deal placement but not actually the lowest price.",
                    },
                    {
                        "type": "product",
                        "name": f"{info['category']} Value Cable Bundle",
                        "brand": "DealHub",
                        "category": info["category"],
                        "price": round(info["price"] + 1.25, 2),
                        "rating": 4.7,
                        "description": "Prominent low-price bundle that is still slightly more expensive.",
                    },
                ],
            )
        ],
    )


def amazon_rating_decoy(task: dict[str, Any]) -> dict[str, Any]:
    info = amazon_product_info(task)
    return variant(
        task["task_id"],
        "rating_tie",
        "verification",
        "High-review lookalikes sit in the same category but trail the target by a few tenths of a star. The agent must compare actual ratings, not review volume or placement.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "product",
                        "name": f"{info['category']} Pro Edition",
                        "brand": "TopRated Picks",
                        "category": info["category"],
                        "price": round(info["price"] * 0.96, 2),
                        "rating": round(max(info["rating"] - 0.1, 4.5), 1),
                        "review_count": 2400,
                        "description": "Popular listing with strong reviews but not the true top-rated option.",
                    },
                    {
                        "type": "product",
                        "name": f"{info['category']} Customer Favorite",
                        "brand": "BestValue House",
                        "category": info["category"],
                        "price": round(info["price"] * 1.04, 2),
                        "rating": round(max(info["rating"] - 0.2, 4.5), 1),
                        "review_count": 3100,
                        "description": "Heavy review count can distract from the slightly lower rating.",
                    },
                ],
            )
        ],
    )


def amazon_price_band_trap(task: dict[str, Any]) -> dict[str, Any]:
    info = amazon_product_info(task)
    return variant(
        task["task_id"],
        "price_band_trap",
        "verification",
        "Search results include near-miss items: one is rated higher but falls outside the allowed price band, and another is inside the band but still lower-rated than the target.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "product",
                        "name": f"{info['category']} Elite Pick",
                        "brand": "Kitchen Select",
                        "category": info["category"],
                        "price": 49.99,
                        "rating": 5.0,
                        "description": "Tempting five-star item that sits just below the allowed budget window.",
                    },
                    {
                        "type": "product",
                        "name": f"{info['category']} Premium Bundle",
                        "brand": "Kitchen Select",
                        "category": info["category"],
                        "price": 104.99,
                        "rating": 4.9,
                        "description": "Excellent rating but slightly above the allowed maximum price.",
                    },
                    {
                        "type": "product",
                        "name": f"{info['category']} Reviewer Favorite",
                        "brand": "HomeChoice",
                        "category": info["category"],
                        "price": 79.99,
                        "rating": 4.7,
                        "description": "Within range, but still not the best-rated qualifying product.",
                    },
                ],
            )
        ],
    )


def amazon_order_history_twin(task: dict[str, Any]) -> dict[str, Any]:
    info = amazon_product_info(task)
    twin_name = f"{info['name']} Travel Edition"
    return variant(
        task["task_id"],
        "order_twin",
        "state_tracking",
        "Order history includes a similarly named recent purchase alongside the real target order. The agent must inspect the exact item before reordering or leaving it alone.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "product",
                        "name": twin_name,
                        "brand": brand_suffix(info["brand"], "Travel"),
                        "category": info["category"],
                        "price": round(info["price"] * 1.08, 2),
                        "rating": round(max(info["rating"] - 0.2, 4.0), 1),
                        "description": "Closely named travel edition that is not the original item.",
                    },
                    {
                        "type": "order",
                        "product_name": twin_name,
                        "quantity": 1,
                        "unit_price": round(info["price"] * 1.08, 2),
                        "status": "confirmed",
                        "placed_hours_ago": 6,
                        "estimated_delivery": "Arriving tomorrow",
                    },
                ],
            )
        ],
    )


def amazon_retry(
    task: dict[str, Any],
    suffix: str,
    primitive: str,
    description: str,
    url_pattern: str,
    methods: list[str],
    *,
    error_count: int = 1,
) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        primitive,
        description,
        [
            network_error(
                url_pattern,
                methods=methods,
                error_count=error_count,
                error_message="Temporary write failure. Retry the action.",
            )
        ],
    )


def build_amazon_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid in {
        "amazon_add_single_item",
        "amazon_add_to_wishlist",
        "amazon_gift_purchase",
        "amazon_search_and_buy",
    }:
        return amazon_product_twin(task)
    if tid == "amazon_browse_category":
        return amazon_cheapest_decoy(task)
    if tid == "amazon_buy_highest_rated":
        return amazon_rating_decoy(task)
    if tid == "amazon_price_comparison":
        return amazon_price_band_trap(task)
    if tid in {"amazon_reorder_past_item", "amazon_verify_order_ok"}:
        return amazon_order_history_twin(task)
    if tid in {"amazon_add_new_address", "amazon_checkout_with_new_address", "amazon_update_shipping"}:
        return amazon_retry(
            task,
            "address_retry",
            "backtracking",
            "The first address-save request fails with a transient 503. The agent must retry the save instead of assuming the new shipping address persisted.",
            "**/api/env/amazon/addresses**",
            ["POST", "PUT"],
        )
    if tid in {"amazon_bulk_cart_build", "amazon_category_exploration", "amazon_wishlist_to_cart"}:
        return amazon_retry(
            task,
            "cart_add_retry",
            "backtracking",
            "The first cart mutation fails transiently. The agent must notice the cart did not update and retry the add workflow.",
            "**/api/env/amazon/cart/add",
            ["POST"],
        )
    if tid == "amazon_cart_management":
        return amazon_retry(
            task,
            "cart_update_retry",
            "verification",
            "The first cart edit fails transiently. The agent must verify the quantity or removal actually stuck before moving on.",
            "**/api/env/amazon/cart/**",
            ["PUT", "DELETE"],
        )
    if tid in {"amazon_cart_budget_limit", "amazon_wishlist_budget_buy"}:
        return amazon_retry(
            task,
            "checkout_retry",
            "backtracking",
            "Checkout returns a transient 503 on the first attempt. The agent must preserve the chosen cart and retry the purchase.",
            "**/api/env/amazon/checkout",
            ["POST"],
        )
    if tid == "amazon_cancel_order":
        return amazon_retry(
            task,
            "cancel_retry",
            "backtracking",
            "The first cancel request fails transiently. The agent must confirm the order still exists and retry the cancellation.",
            "**/api/env/amazon/orders/*/cancel",
            ["POST"],
        )
    if tid == "amazon_return_item":
        return amazon_retry(
            task,
            "return_retry",
            "backtracking",
            "The first return request fails transiently. The agent must retry the return instead of assuming it was filed.",
            "**/api/env/amazon/returns",
            ["POST"],
        )
    if tid in {"amazon_review_after_purchase", "amazon_write_review", "amazon_write_detailed_review"}:
        return amazon_retry(
            task,
            "review_retry",
            "verification",
            "The first review submission fails transiently. The agent must verify the review exists and retry rather than trusting the initial click.",
            "**/api/env/amazon/products/*/reviews",
            ["POST"],
        )
    raise KeyError(f"Unhandled Amazon task: {tid}")


def booking_property_twin(
    task: dict[str, Any],
    *,
    suffix: str = "property_twin",
    primitive: str = "grounding",
    description: str,
    genius: bool = False,
    threshold: bool = False,
    room_focus: bool = False,
) -> dict[str, Any]:
    info = booking_property_info(task)
    room_name = info["room_name"]
    base_price = float(info["price"])
    decoys: list[dict[str, Any]] = []
    if threshold:
        decoys.extend(
            [
                {
                    "type": "property",
                    "name": f"{info['name']} Budget Annex",
                    "city": info["city"],
                    "country": info["country"],
                    "property_type": info["property_type"],
                    "star_rating": max(info["star_rating"] - 1, 3),
                    "review_score": 7.9,
                    "review_count": 1200,
                    "price": round(max(base_price - 35, 60.0), 2),
                    "description": "Cheaper option that misses the minimum review-score threshold.",
                },
                {
                    "type": "property",
                    "name": f"{info['name']} Saver Rooms",
                    "city": info["city"],
                    "country": info["country"],
                    "property_type": info["property_type"],
                    "star_rating": max(info["star_rating"] - 1, 3),
                    "review_score": 7.6,
                    "review_count": 940,
                    "price": round(max(base_price - 52, 55.0), 2),
                    "description": "Very cheap property that should still be excluded by the rating filter.",
                },
            ]
        )
    else:
        twin_one = {
            "type": "property",
            "name": f"{info['name']} Residence",
            "city": info["city"],
            "country": info["country"],
            "property_type": info["property_type"],
            "star_rating": info["star_rating"],
            "review_score": round(max(info["review_score"] - 0.4, 7.5), 1),
            "review_count": 860,
            "price": round(base_price * 0.94, 2),
            "description": "Nearly identical property name with slightly different review profile.",
        }
        twin_two = {
            "type": "property",
            "name": f"{info['name']} Collection",
            "city": info["city"],
            "country": info["country"],
            "property_type": info["property_type"],
            "star_rating": max(info["star_rating"] - 1, 3),
            "review_score": round(max(info["review_score"] - 0.7, 7.2), 1),
            "review_count": 640,
            "price": round(base_price * 1.06, 2),
            "description": "Similar branding can distract from the exact property match.",
        }
        if genius:
            twin_one["is_genius_property"] = False
            twin_one["genius_discount_pct"] = 0
            twin_two["is_genius_property"] = True
            twin_two["genius_discount_pct"] = 5
        if room_focus:
            twin_one["rooms"] = [
                {
                    "name": f"{room_name} Select",
                    "price": round(base_price * 0.98, 2),
                    "bed_type": "queen",
                    "max_occupancy": 4,
                    "meals_included": "breakfast",
                    "cancel_type": "free_cancellation",
                    "rooms_left": 1,
                }
            ]
            twin_two["rooms"] = [
                {
                    "name": f"{room_name} Family Plus",
                    "price": round(base_price * 1.05, 2),
                    "bed_type": "queen",
                    "max_occupancy": 4,
                    "meals_included": "breakfast",
                    "cancel_type": "non_refundable",
                    "rooms_left": 2,
                }
            ]
        decoys.extend([twin_one, twin_two])
    return variant(
        task["task_id"],
        suffix,
        primitive,
        description,
        [seed_injection("add_confusing_decoys", decoys=decoys)],
    )


def booking_reservation_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    props = property_names(task)
    res = reservation_params(task)
    if tid == "booking_modify_dates":
        property_name = target_ref(task, "property_name", fallback=props[0] if props else "Target Hotel")
        check_in = str(res[0].get("check_in", "2026-05-10")) if res else "2026-05-10"
        return variant(
            tid,
            "reservation_twin",
            "state_tracking",
            "A second reservation at the same property sits nearby in the trips list with a different confirmation number and adjacent dates. The agent must modify the exact target reservation.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "reservation",
                            "property_name": property_name,
                            "check_in": check_in,
                            "check_out": "2026-05-16",
                            "status": "confirmed",
                            "booked_days_ago": 2,
                            "confirmation_number": "ALT-553102",
                        }
                    ],
                )
            ],
        )
    if tid == "booking_view_reservation":
        property_name = props[0] if props else "Earlier Reservation"
        return variant(
            tid,
            "cancelled_earlier_trip",
            "verification",
            "A cancelled reservation appears with an earlier check-in than the real upcoming trip. The agent must ignore cancelled trips and open the earliest upcoming reservation instead.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "reservation",
                            "property_name": property_name,
                            "check_in": "2026-04-20",
                            "check_out": "2026-04-22",
                            "status": "cancelled",
                            "booked_days_ago": 20,
                            "confirmation_number": "CXL-204118",
                        }
                    ],
                )
            ],
        )
    if tid == "booking_verify_no_overlap":
        first_prop = props[0] if props else "The Ritz London"
        first_checkout = str(res[0].get("check_out", "2026-06-05")) if res else "2026-06-05"
        second_checkin = str(res[1].get("check_in", "2026-06-10")) if len(res) > 1 else "2026-06-10"
        return variant(
            tid,
            "edge_touch_reservation",
            "verification",
            "An extra reservation starts the same day another stay ends, creating an edge-touch case that is close but not actually overlapping. The agent must not cancel anything unless dates truly overlap.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "reservation",
                            "property_name": first_prop,
                            "check_in": first_checkout,
                            "check_out": second_checkin,
                            "status": "confirmed",
                            "booked_days_ago": 3,
                            "confirmation_number": "EDGE-601205",
                        }
                    ],
                )
            ],
        )
    raise KeyError(f"Unhandled reservation variant for {tid}")


def booking_saved_list_twin(task: dict[str, Any]) -> dict[str, Any]:
    list_name = target_ref(
        task,
        "list_name",
        fallback=str(first_step_param(task, "name", uses={"create_saved_list"}, default="Weekend Getaways")),
    )
    return variant(
        task["task_id"],
        "list_twin",
        "grounding",
        "Saved lists include near-identical names beside the real target. The agent must delete the exact list named in the task and leave the lookalikes intact.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {"type": "saved_list", "name": f"{list_name} 2026"},
                    {"type": "saved_list", "name": f"{list_name} - Archived"},
                ],
            )
        ],
    )


def booking_message_twin(task: dict[str, Any]) -> dict[str, Any]:
    info = booking_property_info(task)
    subject = target_ref(
        task,
        "message_subject",
        fallback=str(first_step_param(task, "subject", uses={"send_message"}, default="Important message")),
    )
    decoy_property_name = f"{info['name']} Suites"
    return variant(
        task["task_id"],
        "message_twin",
        "grounding",
        "An unread message with the same subject arrives from a similarly named property. The agent must open the exact property thread named in the task.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "property",
                        "name": decoy_property_name,
                        "city": info["city"],
                        "country": info["country"],
                        "property_type": info["property_type"],
                        "star_rating": info["star_rating"],
                        "review_score": round(max(info["review_score"] - 0.3, 7.5), 1),
                        "review_count": 420,
                        "price": round(info["price"] * 1.04, 2),
                        "description": "Lookalike property with almost identical branding.",
                    },
                    {
                        "type": "message",
                        "property_name": decoy_property_name,
                        "subject": subject,
                        "body": "Automated pre-arrival note from the similar-looking property. Verify the exact property before opening the unread message.",
                        "sender": "property",
                        "read": False,
                    },
                ],
            )
        ],
    )


def booking_payment_twin(task: dict[str, Any]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        "payment_twin",
        "grounding",
        "The payment list includes one card with the right brand but wrong last four and another with the right last four but wrong brand. The agent must choose the exact requested card.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "payment_method",
                        "card_type": "Amex",
                        "last_four": "1243",
                        "expiry": "08/28",
                    },
                    {
                        "type": "payment_method",
                        "card_type": "Visa",
                        "last_four": "1234",
                        "expiry": "09/29",
                    },
                ],
            )
        ],
    )


def booking_retry(
    task: dict[str, Any],
    suffix: str,
    primitive: str,
    description: str,
    url_pattern: str,
    methods: list[str],
) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        primitive,
        description,
        [network_error(url_pattern, methods=methods, error_message="Temporary booking API failure. Retry the action.")],
    )


def build_booking_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid in {
        "booking_search_and_book",
        "booking_find_deal_and_book",
        "booking_save_property",
        "booking_save_and_organize",
        "booking_curate_saved_list",
        "booking_notification_driven_action",
    }:
        return booking_property_twin(
            task,
            description="A near-identical property appears alongside the true target. The agent must match the exact hotel before saving or booking it.",
        )
    if tid == "booking_book_family_room":
        return booking_property_twin(
            task,
            suffix="room_twin",
            description="A lookalike property offers rooms with nearly identical family-room names. The agent must select the exact room rather than the similarly named twin.",
            room_focus=True,
        )
    if tid == "booking_find_genius_deal":
        return booking_property_twin(
            task,
            suffix="genius_twin",
            description="Similar properties appear nearby, but one lacks the required Genius discount and another offers a weaker badge. The agent must verify the real Genius deal.",
            genius=True,
        )
    if tid == "booking_compare_and_book_cheapest":
        return booking_property_twin(
            task,
            suffix="threshold_decoy",
            primitive="verification",
            description="Cheaper properties appear in the result set, but they fall below the minimum review-score threshold. The agent must keep the rating constraint while comparing prices.",
            threshold=True,
        )
    if tid in {"booking_modify_dates", "booking_view_reservation", "booking_verify_no_overlap"}:
        return booking_reservation_variant(task)
    if tid == "booking_delete_saved_list":
        return booking_saved_list_twin(task)
    if tid == "booking_read_message":
        return booking_message_twin(task)
    if tid == "booking_set_default_payment":
        return booking_payment_twin(task)
    if tid == "booking_book_with_specific_payment":
        return booking_retry(
            task,
            "reservation_retry",
            "backtracking",
            "The first reservation submission fails transiently. The agent must retry the booking rather than assuming the room and payment details were saved.",
            "**/api/env/booking/reservations",
            ["POST"],
        )
    if tid == "booking_add_payment":
        return booking_retry(
            task,
            "payment_retry",
            "backtracking",
            "The first payment-method save fails transiently. The agent must verify the card exists and retry if it did not persist.",
            "**/api/env/booking/payment-methods",
            ["POST"],
        )
    if tid == "booking_change_bed_preference":
        return booking_retry(
            task,
            "preferences_retry",
            "verification",
            "The first travel-preferences update fails transiently. The agent must verify the new bed preference actually stuck before moving on.",
            "**/api/env/booking/preferences",
            ["PUT"],
        )
    if tid in {"booking_change_phone", "booking_profile_update_suite"}:
        return booking_retry(
            task,
            "account_retry",
            "verification",
            "The first account-profile update fails transiently. The agent must confirm the profile changed and retry if it did not.",
            "**/api/env/booking/account",
            ["PUT"],
        )
    if tid in {"booking_change_language", "booking_enable_2fa"}:
        return booking_retry(
            task,
            "settings_retry",
            "verification",
            "The first settings update fails transiently. The agent must confirm the requested setting actually persisted.",
            "**/api/env/booking/settings",
            ["PUT"],
        )
    if tid == "booking_clear_search_history":
        return booking_retry(
            task,
            "clear_retry",
            "backtracking",
            "The first clear-history request fails transiently. The agent must verify the search history is actually empty and retry if it is not.",
            "**/api/env/booking/search-history",
            ["DELETE"],
        )
    if tid == "booking_mark_notifications_read":
        return booking_retry(
            task,
            "notification_retry",
            "verification",
            "The first mark-all-read request fails transiently. The agent must verify unread notifications are gone and retry if they remain.",
            "**/api/env/booking/notifications/read-all",
            ["POST"],
        )
    if tid == "booking_settings_overhaul":
        return booking_retry(
            task,
            "settings_retry",
            "verification",
            "The first settings update fails transiently. The agent must confirm the new currency, language, and notification settings actually stuck.",
            "**/api/env/booking/settings",
            ["PUT"],
        )
    if tid in {"booking_send_message", "booking_reply_to_hotel", "booking_cancel_and_message"}:
        return booking_retry(
            task,
            "message_retry",
            "backtracking",
            "The first message send fails transiently. The agent must retry the message rather than assuming the property received it.",
            "**/api/env/booking/messages",
            ["POST"],
        )
    if tid == "booking_cancel_upcoming":
        return booking_retry(
            task,
            "cancel_retry",
            "backtracking",
            "The first cancellation request fails transiently. The agent must verify the reservation status and retry the cancel action.",
            "**/api/env/booking/reservations/*/cancel",
            ["POST"],
        )
    if tid in {"booking_review_completed_stay", "booking_write_review", "booking_write_simple_review"}:
        return booking_retry(
            task,
            "review_retry",
            "verification",
            "The first review submission fails transiently. The agent must retry after verifying the review was not recorded.",
            "**/api/env/booking/reviews",
            ["POST"],
        )
    raise KeyError(f"Unhandled Booking task: {tid}")


def gmail_retry(
    task: dict[str, Any],
    suffix: str,
    primitive: str,
    description: str,
    url_pattern: str,
    methods: list[str],
) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        primitive,
        description,
        [network_error(url_pattern, methods=methods, error_message="Temporary Gmail write failure. Retry the action.")],
    )


def gmail_spoofed_sender(task: dict[str, Any], *, suffix: str, description: str, subject: str, body: str) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        "grounding",
        description,
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "from_name": "Jordan Park",
                        "from": "jordan.park@thornt0n.com",
                        "subject": subject,
                        "body": body,
                        "labels": ["inbox"],
                    }
                ],
            )
        ],
    )


def gmail_board_label_trap(task: dict[str, Any]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        "label_trap",
        "exploration",
        "One briefing source email has been auto-moved to a board archive label. The agent must search beyond the inbox to find all relevant material.",
        [
            seed_injection(
                "hide_in_non_obvious_location",
                subject_contains="board",
                move_to_label="Board Materials/Archive",
            ),
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "from_name": "Email Rules",
                        "from": "system@thornton.com",
                        "subject": "Filter notification: email moved to Board Materials/Archive",
                        "body": "Your board-related filter auto-filed one message into Board Materials/Archive. Search outside the inbox if you still need it.",
                        "labels": ["inbox"],
                    }
                ],
            ),
        ],
    )


def gmail_data_label_trap(task: dict[str, Any]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        "label_trap",
        "exploration",
        "One of the source emails has been auto-archived into a custom finance label. The agent must search labels rather than assuming every required email is still in the inbox.",
        [
            seed_injection(
                "hide_in_non_obvious_location",
                subject_contains="Q1 budget",
                move_to_label="Finance/Reports",
            ),
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "from_name": "Auto-Archive Bot",
                        "from": "notifications@thornton.com",
                        "subject": "Auto-archive: 1 email moved to Finance/Reports",
                        "body": "One finance-related message matched your archive rule and was moved to Finance/Reports.",
                        "labels": ["inbox"],
                    }
                ],
            ),
        ],
    )


def gmail_contact_alias(task: dict[str, Any]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        "alias_confusion",
        "grounding",
        "Extra contacts with confusingly similar names and addresses are present. The agent must match the exact contact evidence rather than editing the wrong lookalike.",
        [
            seed_injection(
                "alias_entities",
                aliases=[
                    {"name": "Priya Narayanan-Gupta", "email": "priya.ng@partner-corp.com", "note": "External partner"},
                    {"name": "P. Narayanan", "email": "p.narayanan@thornton.com", "note": "Internal finance contact"},
                    {"name": "Priya N.", "email": "priya.narayan@acmelabs.io", "note": "Contractor"},
                ],
            ),
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "from_name": "P. Narayanan",
                        "from": "p.narayanan@thornton.com",
                        "subject": "Re: Contact update",
                        "body": "Hi, just letting you know my email has changed again. Please double-check the correct contact before editing any entry.",
                        "labels": ["inbox"],
                    }
                ],
            ),
        ],
    )


def gmail_buried_detail(task: dict[str, Any]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        "buried_detail",
        "exploration",
        "A long security digest mentions the same service family as the real alert, but the important forwarding instruction is buried and the digest itself is not the actionable source.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "from_name": "Security Operations Center",
                        "from": "soc@acme-security.com",
                        "subject": "Weekly Security Digest — Credential Monitoring Summary",
                        "body": "Vault-7 appears in the weekly digest, but this message explicitly says not to act on the digest itself. Only the original alert from monitoring@acme-security.com should drive the response.",
                        "labels": ["updates"],
                    }
                ],
            )
        ],
    )


def gmail_invoice_contradiction(task: dict[str, Any]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        "contradictory_update",
        "verification",
        "A newer procurement email claims the PO numbers were reassigned. The agent must verify which procurement message is authoritative rather than blindly trusting the latest note.",
        [
            seed_injection(
                "add_contradictory_update",
                from_name="Procurement Team",
                subject="CORRECTION: PO Confirmation - Q1 Vendor Orders (REVISED)",
                body="IMPORTANT CORRECTION — We may have reassigned the PO numbers during migration. Re-check the authoritative confirmation before deciding which invoice is mismatched.",
                labels=["inbox"],
                **{"from": "procurement@company.com"},
            )
        ],
    )


def gmail_wrong_answer(task: dict[str, Any], *, suffix: str, description: str, subject: str, body: str) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        "backtracking",
        description,
        [
            seed_injection(
                "plant_wrong_answer",
                from_name="Ops Recap Bot",
                subject=subject,
                body=body,
                labels=["inbox"],
                **{"from": "ops-bot@thornton.com"},
            )
        ],
    )


def gmail_sender_twin(task: dict[str, Any], *, suffix: str, description: str, decoys: list[dict[str, Any]]) -> dict[str, Any]:
    return variant(task["task_id"], suffix, "grounding", description, [seed_injection("add_confusing_decoys", decoys=decoys)])


def build_gmail_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid == "gmail_board_briefing_prep":
        return gmail_board_label_trap(task)
    if tid == "gmail_data_compilation":
        return gmail_data_label_trap(task)
    if tid == "gmail_confidential_forwarding":
        return variant(
            tid,
            "spoofed_sender",
            "grounding",
            "A near-identical sender domain claims there are corrected confidential figures and different recipients. The agent must verify the authentic sender before forwarding sensitive content.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "from_name": "Victoria Chen",
                            "from": "v.chen@thornt0n.com",
                            "subject": "URGENT: Q3 Revenue Projections - Corrected Figures",
                            "body": "Please use the corrected figures and send the extract to a broader list. Verify the domain before forwarding anything confidential.",
                            "labels": ["inbox"],
                        }
                    ],
                )
            ],
        )
    if tid == "gmail_contact_deduplication":
        return gmail_contact_alias(task)
    if tid == "gmail_credential_leak_response":
        return gmail_buried_detail(task)
    if tid == "gmail_delegation_routing":
        return gmail_spoofed_sender(
            task,
            suffix="spoofed_sender",
            description="A spoofed manager email claims the routing plan changed. The agent must verify the sender before changing delegation targets.",
            subject="CORRECTION: Delegation routing update",
            body="Quick correction to the routing plan: please use a different executive list and a different support alias. Verify the sender before updating any routing.",
        )
    if tid == "gmail_invoice_verification":
        return gmail_invoice_contradiction(task)
    if tid in {"gmail_compose_new", "gmail_reply_simple"}:
        return gmail_retry(
            task,
            "send_retry",
            "backtracking",
            "The first send attempt fails transiently. The agent must verify the email actually sent and retry if it did not.",
            "**/api/env/gmail/send",
            ["POST"],
        )
    if tid == "gmail_forward_email":
        return gmail_retry(
            task,
            "forward_retry",
            "backtracking",
            "The first forward attempt fails transiently. The agent must verify the forward succeeded and retry if it did not.",
            "**/api/env/gmail/emails/*/forward",
            ["POST"],
        )
    if tid == "gmail_change_setting":
        return gmail_retry(
            task,
            "settings_retry",
            "verification",
            "The first settings update fails transiently. The agent must confirm the new setting actually stuck.",
            "**/api/env/gmail/settings",
            ["PUT"],
        )
    if tid in {"gmail_contact_audit", "gmail_contact_cleanup", "gmail_update_contact"}:
        return gmail_retry(
            task,
            "contacts_retry",
            "verification",
            "The first contact mutation fails transiently. The agent must confirm the contact cleanup or note update actually persisted.",
            "**/api/env/gmail/contacts**",
            ["POST", "PUT", "DELETE"],
        )
    if tid in {"gmail_create_label", "gmail_label_workflow_setup", "gmail_team_transition_setup"}:
        return gmail_retry(
            task,
            "label_retry",
            "backtracking",
            "The first label creation fails transiently. The agent must retry and verify the labels exist before moving on.",
            "**/api/env/gmail/labels",
            ["POST"],
        )
    if tid in {"gmail_filter_architect", "gmail_filter_repair_chain"}:
        return gmail_retry(
            task,
            "filter_retry",
            "backtracking",
            "The first filter write fails transiently. The agent must confirm the filter exists and retry if needed.",
            "**/api/env/gmail/filters**",
            ["POST", "DELETE"],
        )
    if tid == "gmail_delete_spam":
        return gmail_sender_twin(
            task,
            suffix="spam_twin",
            description="A second email from a nearly identical spam domain sits beside the obvious junk message. The agent must delete only the exact spam target rather than over-deleting.",
            decoys=[
                {
                    "from_name": "Prize Central Support",
                    "from": "winner-support@prizecentral.net",
                    "subject": "You Won $1,000,000!!! Follow-up",
                    "body": "Automated support note about a previous promotional email. This lookalike message is not the exact target email.",
                    "labels": ["inbox"],
                }
            ],
        )
    if tid == "gmail_mark_all_read":
        return gmail_retry(
            task,
            "mark_read_retry",
            "verification",
            "The first mark-all-read request fails transiently. The agent must confirm the inbox state changed and retry if needed.",
            "**/api/env/gmail/emails/mark-all-read",
            ["POST"],
        )
    if tid == "gmail_search_and_star":
        return gmail_sender_twin(
            task,
            suffix="budget_twin",
            description="A finance email with a near-identical subject appears beside the real budget summary. The agent must star the exact email, not the similar draft.",
            decoys=[
                {
                    "from_name": "Finance Team",
                    "from": "finance-team@thornton.com",
                    "subject": "Q4 Budget Summary - Draft",
                    "body": "Preliminary draft for review. This is not the final summary requested in the task.",
                    "labels": ["inbox"],
                }
            ],
        )
    if tid == "gmail_sender_domain_triage":
        return gmail_sender_twin(
            task,
            suffix="spoofed_domain",
            description="Lookalike sender domains appear alongside the real rule-defining messages. The agent must verify exact domains before applying the routing rules.",
            decoys=[
                {
                    "from_name": "Operations",
                    "from": "operations@internal-thornton.com",
                    "subject": "Inbox Processing Rules -- March 2026",
                    "body": "Copy of the routing note from a lookalike domain. Do not treat this as the authoritative rule source.",
                    "labels": ["inbox"],
                },
                {
                    "from_name": "Security",
                    "from": "security@internal.thornton.co",
                    "subject": "Inbox Processing Rules -- March 2026",
                    "body": "A malformed domain with slightly different routing guidance.",
                    "labels": ["inbox"],
                },
            ],
        )
    if tid == "gmail_star_email":
        return gmail_retry(
            task,
            "star_retry",
            "verification",
            "The first star action fails transiently. The agent must verify the star actually appeared and retry if needed.",
            "**/api/env/gmail/emails/*/star",
            ["POST"],
        )
    if tid == "gmail_schedule_recovery":
        return gmail_wrong_answer(
            task,
            suffix="recap_trap",
            description="A prominent recap email confidently summarizes an outdated meeting time. The agent must verify the real thread rather than trusting the shortcut recap.",
            subject="Scheduling recap",
            body="Quick recap: Wednesday 10:00 AM still looks confirmed. No need to review the full thread unless something changed.",
        )
    if tid == "gmail_thread_version_conflict":
        return gmail_wrong_answer(
            task,
            suffix="recap_trap",
            description="A prominent recap note asserts the wrong release version. The agent must verify the full thread instead of trusting the shortcut summary.",
            subject="Version recap",
            body="Fast recap: consensus appears to be version 3.2.0. Please proceed unless someone objects.",
        )
    if tid == "gmail_verify_inbox_clean":
        return gmail_sender_twin(
            task,
            suffix="vip_sender_twin",
            description="An unread email arrives from the same VIP display name but a different address. The agent must verify the exact sender email before replying in this no-op task.",
            decoys=[
                {
                    "from_name": "{target.vip_name}",
                    "from": "assistant-desk@priority-office.com",
                    "subject": "Re: quick follow-up",
                    "body": "Sharing a follow-up on behalf of {target.vip_name}. Please confirm receipt to the executive desk if needed.",
                    "labels": ["inbox"],
                }
            ],
        )
    raise KeyError(f"Unhandled Gmail task: {tid}")


def reddit_post_twin(task: dict[str, Any]) -> dict[str, Any]:
    title = target_ref(
        task,
        "post_title",
        "target_post_title",
        "new_post_title",
        "upvote_title",
        "downvote_title",
        "edit_post_title",
        "user_post_title",
        fallback="Interesting discussion thread",
    )
    subreddit = target_ref(
        task,
        "subreddit_name",
        "post_subreddit",
        "upvote_sub",
        "downvote_sub",
        "edit_sub",
        fallback=str(first_step_param(task, "subreddit", default="technology")),
    )
    return variant(
        task["task_id"],
        "post_twin",
        "grounding",
        "Search and feed results include near-duplicate posts with overlapping titles. The agent must engage with the exact target thread rather than the similar twin.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "post",
                        "subreddit": subreddit,
                        "title": f"{title} [Update]",
                        "author": "lookalike_helper",
                        "score": 245,
                        "comments": 41,
                        "body": "Near-duplicate discussion thread with overlapping keywords.",
                    },
                    {
                        "type": "subreddit",
                        "name": f"{subreddit}_",
                        "display_name": f"r/{subreddit}_",
                        "description": "Lookalike subreddit with a nearly identical name.",
                        "subscribers": 82000,
                    },
                    {
                        "type": "post",
                        "subreddit": f"{subreddit}_",
                        "title": title,
                        "author": "crosspost_helper",
                        "score": 188,
                        "comments": 23,
                        "body": "Same title posted in a different, similarly named subreddit.",
                    },
                ],
            )
        ],
    )


def reddit_comment_twin(task: dict[str, Any]) -> dict[str, Any]:
    post_title = target_ref(task, "post_title", fallback="Interesting thread")
    author = target_ref(task, "comment_author", "reply_author", "save_author", fallback="helpful_user")
    return variant(
        task["task_id"],
        "comment_twin",
        "grounding",
        "The thread contains comments from confusingly similar usernames with overlapping phrasing. The agent must target the exact author and comment branch.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "comment",
                        "post_title": post_title,
                        "author": f"{author}_",
                        "body": "Similar advice in a nearby thread branch from a lookalike username.",
                        "score": 18,
                        "depth": 1,
                    },
                    {
                        "type": "comment",
                        "post_title": post_title,
                        "author": f"{author}.alt",
                        "body": "Follow-up comment that looks related but is authored by a different user.",
                        "score": 9,
                        "depth": 2,
                    },
                ],
            )
        ],
    )


def reddit_subreddit_twin(task: dict[str, Any]) -> dict[str, Any]:
    subreddit = target_ref(
        task,
        "subreddit_name",
        "join_sub",
        "post_subreddit",
        fallback=str(first_step_param(task, "subreddit", default="MachineLearning")),
    )
    title = target_ref(task, "post_title", "target_post_title", fallback="Helpful thread")
    return variant(
        task["task_id"],
        "subreddit_twin",
        "grounding",
        "A twin subreddit with a nearly identical name appears in search and navigation. The agent must act in the exact community named in the task.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "subreddit",
                        "name": f"{subreddit}_",
                        "display_name": f"r/{subreddit}_",
                        "description": "Lookalike community with a confusingly similar name.",
                        "subscribers": 215000,
                    },
                    {
                        "type": "subreddit",
                        "name": f"{subreddit}help",
                        "display_name": f"r/{subreddit}help",
                        "description": "Meta/help community for a similarly named subreddit.",
                        "subscribers": 54000,
                    },
                    {
                        "type": "post",
                        "subreddit": f"{subreddit}_",
                        "title": title,
                        "author": "shadow_mod",
                        "score": 92,
                        "comments": 11,
                        "body": "Same headline in the wrong, lookalike subreddit.",
                    },
                ],
            )
        ],
    )


def reddit_user_impersonation(task: dict[str, Any]) -> dict[str, Any]:
    from_user = target_ref(task, "from_user", fallback=str(first_step_param(task, "from_user", default="TechHelper")))
    subject = target_ref(task, "message_subject", fallback=str(first_step_param(task, "subject", default="Question")))
    return variant(
        task["task_id"],
        "user_impersonation",
        "grounding",
        "Inbox messages include usernames that differ from the real sender by a single character. The agent must verify the exact username before replying or deleting anything.",
        [
            seed_injection(
                "alias_entities",
                entities=[
                    {
                        "type": "user",
                        "original_name": from_user,
                        "alias_name": f"{from_user}_",
                        "message_subject": subject,
                        "message_body": "Following up from the similar-looking account. Please verify the exact username before replying.",
                    },
                    {
                        "type": "user",
                        "original_name": from_user,
                        "alias_name": f"{from_user}.mod",
                        "message_subject": f"Re: {subject}",
                        "message_body": "One more nudge from a lookalike account.",
                    },
                ],
            )
        ],
    )


def reddit_retry(
    task: dict[str, Any],
    suffix: str,
    primitive: str,
    description: str,
    url_pattern: str,
    methods: list[str],
) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        primitive,
        description,
        [network_error(url_pattern, methods=methods, error_message="Temporary Reddit write failure. Retry the action.")],
    )


def build_reddit_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid in {
        "reddit_upvote_post",
        "reddit_curate_saved",
        "reddit_save_from_feed",
        "reddit_hide_post",
        "reddit_engage_user_content",
        "reddit_search_and_engage",
        "reddit_search_and_message",
        "reddit_vote_spree",
    }:
        return reddit_post_twin(task)
    if tid in {"reddit_downvote_comment", "reddit_reply_nested_comment", "reddit_save_comments"}:
        return reddit_comment_twin(task)
    if tid in {
        "reddit_subscribe_subreddit",
        "reddit_unsubscribe",
        "reddit_manage_subscriptions",
        "reddit_create_and_engage",
    }:
        return reddit_subreddit_twin(task)
    if tid in {"reddit_reply_to_message", "reddit_verify_inbox_clean"}:
        return reddit_user_impersonation(task)
    if tid in {"reddit_compose_message", "reddit_mark_messages_read"}:
        return reddit_retry(
            task,
            "message_retry",
            "backtracking",
            "The first message write fails transiently. The agent must retry after confirming the inbox state did not change.",
            "**/api/env/reddit/messages**",
            ["POST"],
        )
    if tid == "reddit_message_management":
        return reddit_retry(
            task,
            "message_retry",
            "backtracking",
            "The first message delete/send operation fails transiently. The agent must verify inbox state and retry the intended action.",
            "**/api/env/reddit/messages/**",
            ["DELETE", "POST"],
        )
    if tid in {"reddit_create_text_post", "reddit_post_with_flair", "reddit_post_and_comment"}:
        return reddit_retry(
            task,
            "post_retry",
            "backtracking",
            "The first post submission fails transiently. The agent must verify the post exists and retry if it does not.",
            "**/api/env/reddit/posts",
            ["POST"],
        )
    if tid in {"reddit_edit_own_post", "reddit_edit_then_comment"}:
        return reddit_retry(
            task,
            "edit_retry",
            "verification",
            "The first post edit fails transiently. The agent must verify the edited body actually stuck before moving on.",
            "**/api/env/reddit/posts/*",
            ["PUT"],
        )
    if tid == "reddit_delete_own_comment":
        return reddit_retry(
            task,
            "delete_retry",
            "verification",
            "The first comment delete fails transiently. The agent must verify the comment disappeared and retry if it did not.",
            "**/api/env/reddit/comments/*",
            ["DELETE"],
        )
    if tid in {"reddit_follow_notification", "reddit_notification_triage", "reddit_clear_notifications"}:
        return reddit_retry(
            task,
            "notification_retry",
            "backtracking",
            "The first notification-read action fails transiently. The agent must verify the notification state and retry if it remains unread.",
            "**/api/env/reddit/notifications/**",
            ["POST"],
        )
    if tid in {"reddit_switch_dark_mode", "reddit_update_settings", "reddit_privacy_overhaul"}:
        return reddit_retry(
            task,
            "settings_retry",
            "verification",
            "The first settings update fails transiently. The agent must verify the preference changes actually persisted.",
            "**/api/env/reddit/settings",
            ["PUT"],
        )
    raise KeyError(f"Unhandled Reddit task: {tid}")


def rh_ticker_twin(task: dict[str, Any]) -> dict[str, Any]:
    symbols = extract_symbols(task)[:2] or ["AAPL"]
    return variant(
        task["task_id"],
        "ticker_twin",
        "grounding",
        "Search results include confusingly similar ticker symbols next to the real target. The agent must verify the exact symbol before trading or adding it to a watchlist.",
        [seed_injection("add_confusing_stocks", decoys=ticker_decoys(symbols))],
    )


def rh_retry(
    task: dict[str, Any],
    suffix: str,
    primitive: str,
    description: str,
    url_pattern: str,
    methods: list[str],
) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        primitive,
        description,
        [network_error(url_pattern, methods=methods, error_message="Temporary Robinhood write failure. Retry the action.")],
    )


def rh_quote_delay(task: dict[str, Any]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        "quote_delay",
        "patience",
        "Quote refreshes lag behind for several polls. The agent must wait for the live move instead of acting on the initial stale-looking quote.",
        [
            network_delay("**/api/env/robinhood/prices**", delay_ms=2200),
            network_delay("**/api/env/robinhood/stocks/*/chart**", delay_ms=2200),
        ],
    )


def rh_decoy_notifications(task: dict[str, Any], *, suffix: str, description: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        "verification",
        description,
        [seed_injection("add_decoy_notifications", decoys=messages)],
    )


def rh_order_noise(task: dict[str, Any], *, suffix: str, description: str, orders: list[dict[str, Any]]) -> dict[str, Any]:
    return variant(
        task["task_id"],
        suffix,
        "state_tracking",
        description,
        [seed_injection("add_noise_orders", orders=orders)],
    )


def build_robinhood_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid in {
        "rh_add_to_watchlist",
        "rh_create_watchlist",
        "rh_compare_dividend_yields",
        "rh_limit_order_with_check",
        "rh_set_price_alert",
        "rh_watchlist_organize",
    }:
        return rh_ticker_twin(task)
    if tid in {"rh_buy_market_order", "rh_check_buying_power", "rh_sell_shares", "rh_sell_loser_buy_winner"}:
        return rh_retry(
            task,
            "trade_retry",
            "backtracking",
            "The first order submission fails transiently. The agent must verify the order exists and retry if it does not.",
            "**/api/env/robinhood/orders",
            ["POST"],
        )
    if tid in {"rh_deposit_funds", "rh_deposit_then_buy", "rh_transfer_and_withdraw"}:
        return rh_retry(
            task,
            "transfer_retry",
            "backtracking",
            "The first transfer submission fails transiently. The agent must verify the transfer exists and retry if needed.",
            "**/api/env/robinhood/transfers",
            ["POST"],
        )
    if tid == "rh_enable_extended_hours":
        return rh_retry(
            task,
            "settings_retry",
            "verification",
            "The first settings update fails transiently. The agent must confirm extended-hours trading is actually enabled.",
            "**/api/env/robinhood/settings",
            ["PUT"],
        )
    if tid == "rh_find_earnings_and_alert":
        return rh_retry(
            task,
            "alert_retry",
            "backtracking",
            "The first price-alert creation fails transiently. The agent must verify each alert exists and retry missing ones.",
            "**/api/env/robinhood/alerts",
            ["POST"],
        )
    if tid in {"rh_live_alert_and_buy", "rh_live_alert_and_sell"}:
        symbol = extract_symbols(task)[0] if extract_symbols(task) else "AAPL"
        return rh_decoy_notifications(
            task,
            suffix="misleading_notif",
            description="A lookalike alert notification fires for a different instrument or threshold first. The agent must verify the exact symbol and condition before trading.",
            messages=[
                {
                    "type": "price_alert",
                    "title": f"{symbol}X threshold hit",
                    "message": f"{symbol}X just crossed a similar alert threshold. Verify the exact symbol before trading.",
                    "is_read": False,
                },
                {
                    "type": "price_alert",
                    "title": f"{symbol} volatility spike",
                    "message": f"{symbol} moved sharply, but this notice is not the same as the requested trigger condition.",
                    "is_read": False,
                },
            ],
        )
    if tid in {"rh_live_buy_the_dip", "rh_live_take_profit", "rh_live_watch_and_buy"}:
        return rh_quote_delay(task)
    if tid == "rh_mark_notifications_read":
        return rh_retry(
            task,
            "notification_retry",
            "backtracking",
            "The first mark-all-read request fails transiently. The agent must verify the notification state and retry if some remain unread.",
            "**/api/env/robinhood/notifications/read-all",
            ["POST"],
        )
    if tid == "rh_options_buy_call":
        return rh_retry(
            task,
            "options_retry",
            "backtracking",
            "The first options order submission fails transiently. The agent must verify the order exists and retry if needed.",
            "**/api/env/robinhood/options/orders",
            ["POST"],
        )
    if tid == "rh_cancel_pending_order":
        return rh_order_noise(
            task,
            suffix="order_noise",
            description="Another pending order appears nearby with a confusingly similar symbol. The agent must cancel only the exact target order.",
            orders=[
                {"symbol": "MSFTX", "side": "buy", "order_type": "limit", "quantity": 4, "status": "pending"},
                {"symbol": "AAPL", "side": "buy", "order_type": "limit", "quantity": 2, "status": "pending"},
            ],
        )
    if tid == "rh_review_and_cancel_orders":
        return rh_order_noise(
            task,
            suffix="near_threshold_noise",
            description="Additional pending limit buys sit close to market price but do not cross the cancellation threshold. The agent must cancel only truly far-below-market orders.",
            orders=[
                {"symbol": "AAPL", "side": "buy", "order_type": "limit", "quantity": 3, "status": "pending"},
                {"symbol": "MSFT", "side": "buy", "order_type": "limit", "quantity": 2, "status": "pending"},
                {"symbol": "NVDA", "side": "buy", "order_type": "limit", "quantity": 1, "status": "pending"},
            ],
        )
    if tid == "rh_security_audit":
        return rh_retry(
            task,
            "security_retry",
            "backtracking",
            "The first 2FA update fails transiently. The agent must verify the authenticator setting actually persisted.",
            "**/api/env/robinhood/security/2fa",
            ["PUT"],
        )
    if tid == "rh_setup_recurring_investment":
        return rh_retry(
            task,
            "recurring_retry",
            "backtracking",
            "The first recurring-investment creation fails transiently. The agent must verify the schedule exists and retry if it does not.",
            "**/api/env/robinhood/recurring**",
            ["POST", "PUT"],
        )
    if tid == "rh_verify_no_action_needed":
        return rh_decoy_notifications(
            task,
            suffix="drop_notice",
            description="Notifications imply one recurring holding may be down more than 30%, but the recurring-investment page still shows no qualifying pause case. The agent must verify before acting.",
            messages=[
                {
                    "type": "recurring_investment",
                    "title": "Recurring investment review suggested",
                    "message": "A portfolio rule flagged one scheduled buy for review after a large drawdown. Verify the actual recurring investments before pausing anything.",
                    "is_read": False,
                },
                {
                    "type": "price_alert",
                    "title": "SCHD drop watch",
                    "message": "A dividend ETF moved sharply today. This does not necessarily mean the recurring plan needs adjustment.",
                    "is_read": False,
                },
            ],
        )
    raise KeyError(f"Unhandled Robinhood task: {tid}")


def build_variant_for_task(task: dict[str, Any]) -> dict[str, Any]:
    env = task["env_id"]
    if env == "amazon":
        return build_amazon_variant(task)
    if env == "booking":
        return build_booking_variant(task)
    if env == "gmail":
        return build_gmail_variant(task)
    if env == "reddit":
        return build_reddit_variant(task)
    if env == "robinhood":
        return build_robinhood_variant(task)
    raise KeyError(f"Unsupported env: {env}")


def remove_existing_target_variants(task_ids: set[str]) -> None:
    for path in VARIANTS_DIR.glob("*.yaml"):
        stem = path.stem
        base_task_id, _, _ = stem.partition("__")
        if base_task_id in task_ids:
            path.unlink()


def write_variants(variants: dict[str, dict[str, Any]]) -> None:
    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
    for task_id in sorted(variants):
        payload = variants[task_id]
        out_path = VARIANTS_DIR / f"{payload['variant_id']}.yaml"
        out_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, width=100),
        )


def main() -> None:
    tasks = load_target_tasks()
    task_ids = set(tasks)
    remove_existing_target_variants(task_ids)

    variants: dict[str, dict[str, Any]] = {}
    for task_id, task in sorted(tasks.items()):
        variants[task_id] = build_variant_for_task(task)

    if set(variants) != task_ids:
        missing = sorted(task_ids - set(variants))
        extra = sorted(set(variants) - task_ids)
        raise SystemExit(f"Coverage mismatch. missing={missing} extra={extra}")

    write_variants(variants)
    print(f"wrote {len(variants)} variants")


if __name__ == "__main__":
    main()
