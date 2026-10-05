#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"
VARIANTS_DIR = ROOT / "injector" / "variants"

TARGET_DIFFICULTIES = {"hard", "expert", "frontier"}

AMAZON_MANAGED = {
    "amazon_complete_gift_setup",
    "amazon_diagnose_cart",
    "amazon_full_account_setup",
    "amazon_recover_cancelled_order",
}
BOOKING_MANAGED = {"booking_diagnose_wrong_dates"}
GMAIL_MANAGED = {
    "gmail_ambiguous_inbox_cleanup",
    "gmail_diagnose_missing_reply",
    "gmail_recover_deleted_draft",
}
REDDIT_NOTIFICATION_TASKS = {
    "reddit_notification_cascade",
    "reddit_notification_driven_workflow",
    "reddit_notification_message_settings",
}
REDDIT_USER_TASKS = {
    "reddit_block_and_cleanup",
    "reddit_full_inbox_management",
    "reddit_inbox_driven_engagement",
    "reddit_inbox_triage_and_engage",
    "reddit_message_blast_and_settings",
    "reddit_messaging_workflow",
    "reddit_profile_engage_message",
}
REDDIT_THREAD_TASKS = {
    "reddit_comment_chain_analysis",
    "reddit_comment_save_settings",
    "reddit_multi_vote_comment",
    "reddit_reconstruct_post",
    "reddit_research_respond",
    "reddit_selective_vote_save",
    "reddit_thread_participation",
}
REDDIT_POST_TASKS = {
    "reddit_content_creation_sprint",
    "reddit_content_curation",
    "reddit_content_management",
    "reddit_curate_and_engage",
    "reddit_research_and_create",
    "reddit_saved_audit_cleanup",
    "reddit_settings_and_content_creation",
}
REDDIT_SUBREDDIT_TASKS = {
    "reddit_account_cleanup",
    "reddit_community_builder",
    "reddit_community_engagement",
    "reddit_complete_account_setup",
    "reddit_complete_engagement_cycle",
    "reddit_cross_platform_workflow",
    "reddit_deep_thread_engagement",
    "reddit_discover_subscribe_post",
    "reddit_edit_delete_subscribe",
    "reddit_end_to_end_workflow",
    "reddit_feed_curation_expert",
    "reddit_full_account_audit",
    "reddit_full_community_manager",
    "reddit_full_platform_overhaul",
    "reddit_full_profile_engagement",
    "reddit_mass_engagement_workflow",
    "reddit_multi_action_settings",
    "reddit_multi_community_outreach",
    "reddit_multi_sub_engagement",
    "reddit_platform_migration",
    "reddit_post_edit_settings",
    "reddit_targeted_engagement_campaign",
}
REDDIT_MANAGED = (
    REDDIT_NOTIFICATION_TASKS
    | REDDIT_USER_TASKS
    | REDDIT_THREAD_TASKS
    | REDDIT_POST_TASKS
    | REDDIT_SUBREDDIT_TASKS
)
ROBINHOOD_MANAGED = {
    "rh_diagnose_portfolio_drop",
    "rh_fix_duplicate_orders",
    "rh_options_covered_call",
    "rh_tax_loss_harvest",
}

MANAGED_TASK_IDS = (
    AMAZON_MANAGED
    | BOOKING_MANAGED
    | GMAIL_MANAGED
    | REDDIT_MANAGED
    | ROBINHOOD_MANAGED
)


def load_managed_tasks() -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for env_dir in TASKS_DIR.iterdir():
        if not env_dir.is_dir():
            continue
        for path in sorted(env_dir.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text()) or {}
            task_id = raw.get("task_id")
            if task_id not in MANAGED_TASK_IDS:
                continue
            if raw.get("difficulty") not in TARGET_DIFFICULTIES:
                raise SystemExit(f"{task_id} is not hard/expert/frontier")
            raw["_path"] = path
            tasks[task_id] = raw
    if set(tasks) != MANAGED_TASK_IDS:
        missing = sorted(MANAGED_TASK_IDS - set(tasks))
        extra = sorted(set(tasks) - MANAGED_TASK_IDS)
        raise SystemExit(f"Managed task mismatch. missing={missing} extra={extra}")
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


def amazon_product_info(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": target_ref(
            task,
            "gift_product",
            "product_name",
            fallback=str(first_step_param(task, "name", uses={"featured_product"}, default="Target Product")),
        ),
        "brand": str(first_step_param(task, "brand", uses={"featured_product"}, default="Amazon")),
        "category": str(
            first_step_param(
                task,
                "category",
                uses={"featured_product", "product_catalog"},
                default="Electronics",
            )
        ),
        "price": float(first_step_param(task, "price", uses={"featured_product"}, default=49.99)),
        "rating": float(first_step_param(task, "rating", uses={"featured_product"}, default=4.7)),
    }


def reddit_primary_subreddit(task: dict[str, Any]) -> str:
    return target_ref(
        task,
        "join",
        "j1",
        "subreddit_name",
        "user_sub",
        "comment_sub",
        "save_sub",
        "save_subreddit",
        "hide_sub",
        "sub1",
        "leave_sub",
        fallback=str(first_step_param(task, "subreddit", default="MachineLearning")),
    )


def reddit_primary_title(task: dict[str, Any]) -> str:
    return target_ref(
        task,
        "post_title",
        "target_post_title",
        "user_post",
        "save_title",
        "save2_title",
        "wn_title",
        "prog_title",
        "comment_post_title",
        "hide_title",
        "create_title",
        "vote_title",
        "comment_title",
        "ct",
        fallback="Interesting discussion thread",
    )


def reddit_primary_user(task: dict[str, Any]) -> str:
    return target_ref(
        task,
        "from_user",
        "reply1_from",
        "reply2_from",
        "block_user",
        "user",
        "msg_to",
        "new_to",
        "reply_author",
        fallback="NeuralNexus",
    )


def reddit_primary_subject(task: dict[str, Any]) -> str:
    return target_ref(
        task,
        "message_subject",
        "reply1_sub",
        "reply2_sub",
        "delete_subject",
        "delete_sub",
        "msg_sub",
        "new_subject",
        fallback="Community message",
    )


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
    text = task.get("instruction_template") or task.get("instruction") or ""
    candidates.extend(re.findall(r"\b[A-Z]{1,5}\b", text))

    seen: set[str] = set()
    symbols: list[str] = []
    for item in candidates:
        token = item.strip().upper()
        if not token or len(token) > 5 or not token.isalpha() or token in seen:
            continue
        seen.add(token)
        symbols.append(token)
    return symbols


TICKER_LOOKALIKES: dict[str, list[dict[str, Any]]] = {
    "AAPL": [
        {"symbol": "AAPLX", "name": "Apple Holdings Trust", "price": 189.40},
        {"symbol": "APLE", "name": "Apple Hospitality REIT", "price": 16.90},
    ],
    "VOO": [
        {"symbol": "VOOG", "name": "Vanguard S&P 500 Growth ETF", "price": 298.15},
        {"symbol": "VOOV", "name": "Vanguard S&P 500 Value ETF", "price": 164.30},
    ],
}


def ticker_decoys(symbols: list[str]) -> list[dict[str, Any]]:
    decoys: list[dict[str, Any]] = []
    for symbol in symbols:
        specs = TICKER_LOOKALIKES.get(symbol) or [
            {"symbol": f"{symbol}X", "name": f"{symbol} Extended Trust", "price": 92.40},
            {"symbol": f"{symbol}Q", "name": f"{symbol} Income Notes", "price": 37.60},
        ]
        decoys.extend(specs[:2])
    return decoys[:4]


def build_amazon_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    info = amazon_product_info(task)
    if tid == "amazon_complete_gift_setup":
        recipient = target_ref(task, "recipient_name", fallback="Maria Chen")
        street = target_ref(task, "street", fallback="500 Oak Ave")
        city = target_ref(task, "city", fallback="Portland")
        state_code = target_ref(task, "state_code", fallback="OR")
        zip_code = target_ref(task, "zip", fallback="97201")
        return variant(
            tid,
            "recipient_address_twin",
            "grounding",
            "Search results and saved addresses include near-matches for both the gift item and recipient address. The agent must purchase the exact product for the exact recipient record it just added.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "product",
                            "name": f"{info['name']} Bundle",
                            "brand": info["brand"],
                            "category": info["category"],
                            "price": round(info["price"] * 1.08, 2),
                            "rating": max(info["rating"] - 0.2, 4.1),
                            "description": "A gift bundle with a nearly identical name but different contents.",
                        },
                        {
                            "type": "address",
                            "full_name": recipient,
                            "street_address": f"{street} Apt 2",
                            "city": city,
                            "state": state_code,
                            "zip_code": zip_code,
                        },
                        {
                            "type": "address",
                            "full_name": recipient,
                            "street_address": f"{street} Suite B",
                            "city": city,
                            "state": state_code,
                            "zip_code": zip_code,
                        },
                    ],
                )
            ],
        )
    if tid == "amazon_diagnose_cart":
        return variant(
            tid,
            "cart_item_twin",
            "grounding",
            "The cart already contains a near-identical speaker variant at the correct quantity, while the real target still has the wrong count. The agent must fix the exact item, not the lookalike.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "product",
                            "name": f"{info['name']} Mini",
                            "brand": info["brand"],
                            "category": info["category"],
                            "price": round(info["price"] * 0.84, 2),
                            "rating": max(info["rating"] - 0.1, 4.2),
                            "description": "Nearly identical speaker variant already sitting at the desired quantity.",
                        },
                        {
                            "type": "cart_item",
                            "product_name": f"{info['name']} Mini",
                            "quantity": "{target.correct_qty}",
                            "unit_price": round(info["price"] * 0.84, 2),
                        },
                    ],
                )
            ],
        )
    if tid == "amazon_full_account_setup":
        return variant(
            tid,
            "office_address_collision",
            "grounding",
            "The account already has old Home and Office entries with nearly identical names. The agent must still add the new addresses, then check out to the exact new Office address rather than the stale twin.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "address",
                            "full_name": "Home",
                            "street_address": "200 Pine Street Apt 2",
                            "city": "Seattle",
                            "state": "WA",
                            "zip_code": "98101",
                        },
                        {
                            "type": "address",
                            "full_name": "Office",
                            "street_address": "80 Corporate Blvd",
                            "city": "Bellevue",
                            "state": "WA",
                            "zip_code": "98004",
                        },
                        {
                            "type": "product",
                            "name": f"{info['name']} Pro",
                            "brand": info["brand"],
                            "category": info["category"],
                            "price": round(info["price"] * 1.12, 2),
                            "rating": max(info["rating"] - 0.1, 4.1),
                            "description": "A similarly named monitor model that is not the requested first purchase.",
                        },
                    ],
                )
            ],
        )
    if tid == "amazon_recover_cancelled_order":
        twin_name = f"{info['name']} TKL"
        return variant(
            tid,
            "cancelled_order_twin",
            "state_tracking",
            "Order history contains another recently cancelled keyboard with a nearly identical name. The agent must reorder the exact cancelled item, not the sibling model.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "type": "product",
                            "name": twin_name,
                            "brand": info["brand"],
                            "category": info["category"],
                            "price": round(info["price"] * 0.94, 2),
                            "rating": max(info["rating"] - 0.2, 4.0),
                            "description": "Tenkeyless sibling model that looks almost identical in search and order history.",
                        },
                        {
                            "type": "order",
                            "product_name": twin_name,
                            "quantity": 1,
                            "unit_price": round(info["price"] * 0.94, 2),
                            "status": "cancelled",
                            "placed_hours_ago": 28,
                            "estimated_delivery": "Cancelled before shipping",
                        },
                    ],
                )
            ],
        )
    raise KeyError(f"Unhandled Amazon task: {tid}")


def build_booking_variant(task: dict[str, Any]) -> dict[str, Any]:
    if task["task_id"] != "booking_diagnose_wrong_dates":
        raise KeyError(task["task_id"])
    hotel_name = target_ref(task, "hotel_name", fallback="The Savoy London")
    return variant(
        task["task_id"],
        "same_hotel_twin",
        "state_tracking",
        "Trips already contain another reservation at the same hotel with nearby dates. The agent must cancel and rebook the actual wrong reservation, not the similar same-hotel twin.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "reservation",
                        "property_name": hotel_name,
                        "check_in": "{target.correct_check_in}",
                        "check_out": "2026-07-17",
                        "status": "confirmed",
                        "booked_days_ago": 2,
                        "confirmation_number": "SAVOY-ALT-715",
                    }
                ],
            )
        ],
    )


def build_gmail_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid == "gmail_ambiguous_inbox_cleanup":
        project = target_ref(task, "project_name", fallback="Nightingale")
        return variant(
            tid,
            "label_name_collision",
            "grounding",
            "The mailbox already contains near-match project labels and a promotional email that reuses the project name. The agent must create and apply the exact project label rather than relying on the wrong lookalike.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {"type": "label", "name": f"Project/{project}-Archive"},
                        {"type": "label", "name": f"Projects/{project}"},
                        {
                            "from_name": "Thornton Digest",
                            "from": "digest@newsletter.thornton.com",
                            "subject": f"{project} partner roundup and sponsor offers",
                            "body": f"Promotional partner roundup for anyone following {project}. This is not an internal project thread.",
                            "labels": ["inbox", "promotions"],
                        },
                    ],
                )
            ],
        )
    if tid == "gmail_diagnose_missing_reply":
        return variant(
            tid,
            "wrong_thread_recap",
            "backtracking",
            "A recap email confidently claims the wrong client thread is still unanswered. The agent must inspect the actual thread history instead of trusting the shortcut summary.",
            [
                seed_injection(
                    "plant_wrong_answer",
                    from_name="Client Ops Tracker",
                    **{"from": "ops-tracker@company.internal"},
                    subject="Outstanding client replies summary",
                    body="Current summary: only the onboarding paperwork thread still needs a response. The API integration timeline thread was already handled, so no action is required there.",
                    labels=["inbox"],
                )
            ],
        )
    if tid == "gmail_recover_deleted_draft":
        return variant(
            tid,
            "trash_draft_twin",
            "grounding",
            "Trash contains another near-match deleted thread with the same subject line but the wrong recipient and incomplete talking points. The agent must reconstruct the real deleted draft, not the decoy.",
            [
                seed_injection(
                    "add_confusing_decoys",
                    decoys=[
                        {
                            "from_name": "Julia Fontaine",
                            "from": "{target.recipient_email}",
                            "to": ["me@thornton.com"],
                            "subject": "{target.draft_subject}",
                            "body": "Following up on the roadmap. I only saw the mobile SDK launch and dashboard redesign notes, but not the final API throughput details.",
                            "labels": ["trash"],
                            "deleted": True,
                        },
                        {
                            "from_name": "Avery Stone",
                            "from": "avery.stone@innovate-labs.com",
                            "to": ["me@thornton.com"],
                            "subject": "{target.draft_subject}",
                            "body": "Old draft copy for a different stakeholder. It mentions only the August SDK milestone and a generic timeline.",
                            "labels": ["trash"],
                            "deleted": True,
                        },
                    ],
                )
            ],
        )
    raise KeyError(f"Unhandled Gmail task: {tid}")


def reddit_subreddit_collision(task: dict[str, Any]) -> dict[str, Any]:
    subreddit = reddit_primary_subreddit(task)
    title = reddit_primary_title(task)
    return variant(
        task["task_id"],
        "subreddit_collision",
        "grounding",
        "A twin subreddit with a nearly identical name appears beside the real community, including a same-title post in the wrong place. The agent must act in the exact subreddit named in the task.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "subreddit",
                        "name": f"{subreddit}_",
                        "display_name": f"r/{subreddit}_",
                        "description": "Lookalike community with nearly identical branding.",
                        "subscribers": 185000,
                    },
                    {
                        "type": "subreddit",
                        "name": f"{subreddit}hub",
                        "display_name": f"r/{subreddit}hub",
                        "description": "Companion community that often appears next to the real one in search.",
                        "subscribers": 74000,
                    },
                    {
                        "type": "post",
                        "subreddit": f"{subreddit}_",
                        "title": title,
                        "author": "shadow_mod",
                        "score": 144,
                        "comments": 21,
                        "body": "Same headline posted into the wrong, lookalike subreddit.",
                    },
                ],
            )
        ],
    )


def reddit_post_collision(task: dict[str, Any]) -> dict[str, Any]:
    title = reddit_primary_title(task)
    subreddit = reddit_primary_subreddit(task)
    saved_like = "saved" in task["task_id"] or "curate" in task["task_id"]
    return variant(
        task["task_id"],
        "post_collision",
        "grounding",
        "Feed and search results include near-duplicate posts with overlapping titles across similar communities. The agent must engage with the exact target thread rather than the twin.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "post",
                        "subreddit": subreddit,
                        "title": f"{title} [Update]",
                        "author": "lookalike_helper",
                        "score": 205,
                        "comments": 33,
                        "is_saved": saved_like,
                        "body": "Follow-up thread with overlapping keywords but not the task target.",
                    },
                    {
                        "type": "subreddit",
                        "name": f"{subreddit}_",
                        "display_name": f"r/{subreddit}_",
                        "description": "Twin community used for crossposts.",
                        "subscribers": 66000,
                    },
                    {
                        "type": "post",
                        "subreddit": f"{subreddit}_",
                        "title": title,
                        "author": "crosspost_helper",
                        "score": 178,
                        "comments": 12,
                        "is_saved": saved_like,
                        "body": "Same title in a different, lookalike community.",
                    },
                ],
            )
        ],
    )


def reddit_thread_collision(task: dict[str, Any]) -> dict[str, Any]:
    post_title = reddit_primary_title(task)
    author = reddit_primary_user(task)
    return variant(
        task["task_id"],
        "thread_branch_collision",
        "grounding",
        "The relevant thread contains comments from nearly identical usernames in adjacent branches. The agent must target the exact author and branch instead of the lookalike reply.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "comment",
                        "post_title": post_title,
                        "author": f"{author}_",
                        "body": "Similar-looking advice from a near-match username in a sibling branch.",
                        "score": 18,
                        "depth": 1,
                    },
                    {
                        "type": "comment",
                        "post_title": post_title,
                        "author": f"{author}.alt",
                        "body": "A follow-up that looks related but belongs to a different branch.",
                        "score": 9,
                        "depth": 2,
                    },
                ],
            )
        ],
    )


def reddit_user_impersonation(task: dict[str, Any]) -> dict[str, Any]:
    user = reddit_primary_user(task)
    subject = reddit_primary_subject(task)
    return variant(
        task["task_id"],
        "user_impersonation",
        "grounding",
        "Messages and user cards include usernames that differ from the real target by a single character. The agent must verify the exact user before blocking, replying, or messaging.",
        [
            seed_injection(
                "alias_entities",
                entities=[
                    {
                        "type": "user",
                        "original_name": user,
                        "alias_name": f"{user}_",
                        "message_subject": subject,
                        "message_body": "Following up from a lookalike account. Please verify the exact username before acting.",
                    },
                    {
                        "type": "user",
                        "original_name": user,
                        "alias_name": f"{user}.mod",
                        "message_subject": f"Re: {subject}",
                        "message_body": "One more message from a similarly named account.",
                    },
                ],
            )
        ],
    )


def reddit_notification_shadow(task: dict[str, Any]) -> dict[str, Any]:
    subreddit = reddit_primary_subreddit(task)
    title = reddit_primary_title(task)
    user = reddit_primary_user(task)
    return variant(
        task["task_id"],
        "notification_shadow",
        "state_tracking",
        "Unread notifications emphasize lookalike activity in nearby communities and threads. The agent must verify which alerts actually correspond to the task-relevant post or user.",
        [
            seed_injection(
                "add_confusing_decoys",
                decoys=[
                    {
                        "type": "notification",
                        "title": f"New activity in r/{subreddit}_",
                        "body": f'u/{user}_ commented on "{title}" in the lookalike community.',
                        "subreddit_name": f"{subreddit}_",
                        "from_user": f"{user}_",
                        "is_read": False,
                    },
                    {
                        "type": "notification",
                        "title": f'Update on "{title}"',
                        "body": f'u/{user} replied in a nearby thread, but not the exact target branch.',
                        "subreddit_name": subreddit,
                        "from_user": user,
                        "is_read": False,
                    },
                ],
            )
        ],
    )


def build_reddit_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid in REDDIT_NOTIFICATION_TASKS:
        return reddit_notification_shadow(task)
    if tid in REDDIT_USER_TASKS:
        return reddit_user_impersonation(task)
    if tid in REDDIT_THREAD_TASKS:
        return reddit_thread_collision(task)
    if tid in REDDIT_POST_TASKS:
        return reddit_post_collision(task)
    if tid in REDDIT_SUBREDDIT_TASKS:
        return reddit_subreddit_collision(task)
    raise KeyError(f"Unhandled Reddit task: {tid}")


def build_robinhood_variant(task: dict[str, Any]) -> dict[str, Any]:
    tid = task["task_id"]
    if tid == "rh_diagnose_portfolio_drop":
        return variant(
            tid,
            "market_notice_shadow",
            "verification",
            "Notifications overemphasize a broad market move and a non-critical ticker. The agent must still identify the actual losing positions before creating protective alerts.",
            [
                seed_injection(
                    "add_decoy_notifications",
                    decoys=[
                        {
                            "type": "price_alert",
                            "title": "SPY market stress alert",
                            "message": "The S&P 500 is sliding faster than usual today. Broad market noise may not explain your portfolio-specific drop.",
                            "is_read": False,
                        },
                        {
                            "type": "price_alert",
                            "title": "{target.worst_symbol} watchlist headline",
                            "message": "Headline move detected on a watchlist symbol. Confirm portfolio losses directly before placing alerts.",
                            "is_read": False,
                        },
                    ],
                )
            ],
        )
    if tid == "rh_fix_duplicate_orders":
        return variant(
            tid,
            "same_symbol_different_qty",
            "state_tracking",
            "Pending orders include same-symbol orders that are not true duplicates because the quantity or side differs. The agent must cancel only the real duplicates and keep the distinct orders.",
            [
                seed_injection(
                    "add_noise_orders",
                    orders=[
                        {"symbol": "AAPL", "side": "buy", "order_type": "limit", "quantity": 7, "status": "pending"},
                        {"symbol": "AAPL", "side": "sell", "order_type": "limit", "quantity": 1, "status": "pending"},
                        {"symbol": "MSFT", "side": "buy", "order_type": "limit", "quantity": 9, "status": "pending"},
                    ],
                )
            ],
        )
    if tid == "rh_options_covered_call":
        return variant(
            tid,
            "ticker_twin",
            "grounding",
            "Ticker search includes lookalikes next to the covered-call underlying. The agent must open the exact stock before selecting the options chain and selling the call.",
            [seed_injection("add_confusing_stocks", decoys=ticker_decoys(["AAPL"]))],
        )
    if tid == "rh_tax_loss_harvest":
        return variant(
            tid,
            "replacement_etf_twin",
            "grounding",
            "Replacement ETF search includes near-match Vanguard funds and a warning notification about a different symbol. The agent must still buy the exact replacement ETF after harvesting losses.",
            [
                seed_injection("add_confusing_stocks", decoys=ticker_decoys(["VOO"])),
                seed_injection(
                    "add_decoy_notifications",
                    decoys=[
                        {
                            "type": "tax_document",
                            "title": "Wash-sale review suggested",
                            "message": "One recent activity item needs review, but confirm the actual recent-buy list before deciding what is ineligible to sell.",
                            "is_read": False,
                        }
                    ],
                ),
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


def remove_existing_managed_variants(task_ids: set[str]) -> None:
    for path in VARIANTS_DIR.glob("*.yaml"):
        stem = path.stem
        base_task_id, _, _ = stem.partition("__")
        if base_task_id in task_ids:
            path.unlink()
            continue
        raw = yaml.safe_load(path.read_text()) or {}
        if raw.get("base_task_id") in task_ids:
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
    tasks = load_managed_tasks()
    remove_existing_managed_variants(set(tasks))
    variants = {task_id: build_variant_for_task(task) for task_id, task in sorted(tasks.items())}
    write_variants(variants)
    print(f"wrote {len(variants)} variants")


if __name__ == "__main__":
    main()
