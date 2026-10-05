"""Seed builders for 10 easy Gmail tasks.

Each builder creates a minimal, clear scenario that tests basic agent capabilities.
Easy tasks have few distractors, unambiguous instructions, and 1-3 required actions.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ._seed_builders import BUILDER_REGISTRY, SeedContext


def _register(name: str):
    def decorator(func):
        BUILDER_REGISTRY[name] = func
        return func
    return decorator


# ---------------------------------------------------------------------------
# 1. gmail_star_email (grounding)
# ---------------------------------------------------------------------------

@_register("star_email")
def build_star_email(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Star a specific email. One target email + a few others."""
    thread = ctx.next_id("thread")
    target = ctx.email(
        from_name="Alice Chen",
        from_addr="alice.chen@thornton.com",
        subject="Project Update — Q1 Milestones",
        body=ctx.format_email_body(
            "Hi team,",
            "Here's the latest update on our Q1 milestones. All deliverables are on track.",
            "Please review and let me know if you have questions.",
            signoff_name="Alice",
        ),
        timestamp=ctx.now - timedelta(hours=3),
        thread_id=thread,
        labels=["inbox"],
    )
    ctx.base["emails"].append(target)
    return {"target_email_id": target.id}


# ---------------------------------------------------------------------------
# 2. gmail_reply_simple (grounding, verification)
# ---------------------------------------------------------------------------

@_register("reply_simple")
def build_reply_simple(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Reply to a specific email with a given message."""
    thread = ctx.next_id("thread")
    target = ctx.email(
        from_name="Bob Martinez",
        from_addr="bob.martinez@thornton.com",
        subject="Meeting Tomorrow at 2pm",
        body=ctx.format_email_body(
            "Hi,",
            "Just confirming — are you available for the team sync tomorrow at 2pm?",
            "Let me know if the time works.",
            signoff_name="Bob",
        ),
        timestamp=ctx.now - timedelta(hours=2),
        thread_id=thread,
        labels=["inbox"],
    )
    ctx.base["emails"].append(target)
    return {"target_email_id": target.id, "target_thread_id": thread}


# ---------------------------------------------------------------------------
# 3. gmail_create_label (planning)
# ---------------------------------------------------------------------------

@_register("create_label")
def build_create_label(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """No special seeding needed — just create a label."""
    return {}


# ---------------------------------------------------------------------------
# 4. gmail_forward_email (grounding, planning)
# ---------------------------------------------------------------------------

@_register("forward_email")
def build_forward_email(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Forward a specific email to a colleague."""
    thread = ctx.next_id("thread")
    target = ctx.email(
        from_name="Carol Wang",
        from_addr="carol.wang@bluespark.io",
        subject="Invoice #1234 — March Services",
        body=ctx.format_email_body(
            "Hi,",
            "Attached is invoice #1234 for March consulting services.",
            "Total: $4,500.00. Net 30 terms.",
            signoff_name="Carol Wang\nAccounts Receivable, VendorCo",
        ),
        timestamp=ctx.now - timedelta(hours=5),
        thread_id=thread,
        labels=["inbox"],
    )
    ctx.base["emails"].append(target)
    return {"target_email_id": target.id}


# ---------------------------------------------------------------------------
# 5. gmail_delete_spam (grounding)
# ---------------------------------------------------------------------------

@_register("delete_spam")
def build_delete_spam(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed one obvious spam email among normal emails."""
    thread = ctx.next_id("thread")
    spam = ctx.email(
        from_name="Loyalty Program",
        from_addr="winner@prizecentral.net",
        subject="You Won $1,000,000!!! Click NOW!!!",
        body="Congratulations! You have been selected as a winner! Click the link to claim.",
        timestamp=ctx.now - timedelta(hours=1),
        thread_id=thread,
        labels=["inbox"],
    )
    # Also add a normal email so agent doesn't just delete everything
    normal_thread = ctx.next_id("thread")
    normal = ctx.email(
        from_name="IT Support",
        from_addr="it@thornton.com",
        subject="System maintenance this weekend",
        body="Planned maintenance window: Saturday 2am-6am. No action needed.",
        timestamp=ctx.now - timedelta(hours=4),
        thread_id=normal_thread,
        labels=["inbox"],
        is_read=True,
    )
    ctx.base["emails"].extend([spam, normal])
    return {"spam_email_id": spam.id, "normal_email_id": normal.id}


# ---------------------------------------------------------------------------
# 6. gmail_search_and_star (exploration, grounding)
# ---------------------------------------------------------------------------

@_register("search_and_star")
def build_search_and_star(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Target email starts off the first inbox page so search is the shortest path."""
    # Add enough primary-category emails that the target is not visible on the
    # initial 16-thread inbox page, even before generic distractors are added.
    _filler_subjects = [
        "Re: Updated project timeline",
        "Team lunch this Friday?",
        "Quick question on the PR",
        "Feedback on the design mockup",
        "Sync notes from this morning",
        "Out of office next Monday",
        "New onboarding doc — please review",
        "Re: Client call follow-up",
        "Parking lot changes starting next week",
        "Sprint retro action items",
        "Invitation: product roadmap review",
        "Re: Office supply order",
        "Candidate interview — your availability",
        "Monthly security training reminder",
        "Re: Shared drive access",
        "Vendor contract renewal",
        "Holiday schedule — final version",
        "Conference room booking conflict",
        "Performance review self-assessment due",
        "Build pipeline fix deployed",
    ]
    _filler_domains = ["team.thornton.com", "ops.thornton.com", "eng.co", "hr.thornton.com", "infra.thornton.com"]
    for i in range(20):
        t = ctx.next_id("thread")
        sender_name = ctx.fake.name()
        ctx.base["emails"].append(ctx.email(
            from_name=sender_name,
            from_addr=ctx.email_for_name(sender_name, domain=ctx.rng.choice(_filler_domains)),
            subject=_filler_subjects[i % len(_filler_subjects)],
            body=ctx.generic_email_body(sender_name),
            timestamp=ctx.now - timedelta(hours=i + 1),
            thread_id=t,
            labels=["inbox"],
            is_read=True,
        ))

    target_thread = ctx.next_id("thread")
    target = ctx.email(
        from_name="Finance Team",
        from_addr="finance@thornton.com",
        subject="Q4 Budget Summary — Final Numbers",
        body=ctx.format_email_body(
            "Hi all,",
            "The final Q4 budget numbers are in. Total spend: $1.2M against $1.3M forecast.",
            "We came in 8% under budget. Great work everyone.",
            signoff_name="Finance Team",
        ),
        timestamp=ctx.now - timedelta(days=5),
        thread_id=target_thread,
        labels=["inbox"],
    )
    ctx.base["emails"].append(target)
    return {"target_email_id": target.id}


# ---------------------------------------------------------------------------
# 7. gmail_mark_all_read (patience, state_tracking)
# ---------------------------------------------------------------------------

@_register("mark_all_read")
def build_mark_all_read(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed 5 unread emails that need to be marked as read.

    Forces all pre-existing and distractor emails to is_read=True so that
    only the 5 seeded emails are unread, preventing false invariant violations
    when the agent uses the mark-all-read button.
    """
    for em in ctx.base.get("emails", []):
        em.is_read = True
    ctx.base["_force_distractor_emails_read"] = True
    ids = []
    for i in range(5):
        t = ctx.next_id("thread")
        email = ctx.email(
            from_name=f"Colleague {i + 1}",
            from_addr=f"colleague{i + 1}@thornton.com",
            subject=f"FYI: Update on item {i + 1}",
            body=f"Just a quick heads-up about item {i + 1}. No action needed.",
            timestamp=ctx.now - timedelta(hours=i + 1),
            thread_id=t,
            labels=["inbox"],
            is_read=False,
        )
        ctx.base["emails"].append(email)
        ids.append(email.id)
    return {"unread_email_ids": ids, "unread_count": len(ids)}


# ---------------------------------------------------------------------------
# 8. gmail_update_contact (exploration, verification)
# ---------------------------------------------------------------------------

@_register("update_contact")
def build_update_contact(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed a contact that needs its note updated."""
    from breakingweb.backend.models.gmail import Contact
    contact = Contact(
        id=ctx.next_id("contact"),
        name="Alice Chen",
        email="alice.chen@thornton.com",
        note="Engineering team",
    )
    ctx.base["contacts"].append(contact)
    return {"contact_id": contact.id, "contact_name": contact.name}


# ---------------------------------------------------------------------------
# 9. gmail_change_setting (exploration, verification)
# ---------------------------------------------------------------------------

@_register("change_setting")
def build_change_setting(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Pre-set undo_send to 5s — agent must change it to 30s."""
    ctx.base["settings"].undo_send_seconds = 5
    return {}


# ---------------------------------------------------------------------------
# 10. gmail_compose_new (planning, verification)
# ---------------------------------------------------------------------------

@_register("compose_new")
def build_compose_new(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """No special seeding — agent just composes and sends a new email."""
    return {}
