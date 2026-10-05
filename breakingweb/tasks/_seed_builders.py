"""Composable seed builder framework for BreakingWeb.

Provides :class:`SeedContext` (the mutable accumulator threaded through every
builder step) and a registry of reusable builder functions that generate
deterministic test data for benchmark tasks.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from breakingweb.backend.models.gmail import Attachment, Contact, Email, FilterRule, Label


# ---------------------------------------------------------------------------
# ResolvedActor
# ---------------------------------------------------------------------------

@dataclass
class ResolvedActor:
    """A named person with a deterministically-generated email address."""

    name: str
    email: str
    first_name: str


# ---------------------------------------------------------------------------
# SeedContext
# ---------------------------------------------------------------------------

class SeedContext:
    """Mutable accumulator threaded through every seed builder step.

    Exposes shared helpers such as ``ctx.email()`` and ``ctx.contact()``
    so builders can operate against one deterministic state interface.
    """

    def __init__(
        self,
        seed: int,
        rng: random.Random,
        fake: Any,
        now: datetime,
        base: dict[str, Any],
    ) -> None:
        self.seed = seed
        self.rng = rng
        self.fake = fake
        self.now = now
        self.base = base
        self.actors: dict[str, ResolvedActor] = {}
        self.outputs: dict[str, Any] = {}
        self.counters: dict[str, int] = {}

        # Convenience aliases used throughout the builder set.
        self.owner_name: str = base.get("owner_name", "Avery Quinn")
        self.owner_email: str = base.get("owner_email", "avery.quinn@thornton.com")

    # -- ID generation -----------------------------------------------------

    def next_id(self, prefix: str) -> str:
        """Return a monotonically increasing id like ``thread_1``."""
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]}"

    # -- Name / email helpers ----------------------------------------------

    def email_for_name(self, name: str, domain: str | None = None) -> str:
        """Build an email address from a display name.

        When *domain* is ``None`` the method calls ``self.fake.domain_word()``
        so seed draws remain deterministic.
        """
        local = "".join(
            ch.lower() for ch in name if ch.isalnum() or ch == " "
        ).replace(" ", ".")
        local = ".".join(part for part in local.split(".") if part) or "contact"
        domain = domain or f"{self.fake.domain_word()}.com"
        return f"{local}@{domain}"

    @staticmethod
    def first_name(name: str) -> str:
        return name.split()[0]

    # -- Text formatting ---------------------------------------------------

    @staticmethod
    def format_email_body(
        *paragraphs: str, signoff_name: str | None = None
    ) -> str:
        body = "\n\n".join(
            paragraph.strip() for paragraph in paragraphs if paragraph.strip()
        )
        if signoff_name:
            body = f"{body}\n\nThanks,\n{signoff_name}"
        return body

    @staticmethod
    def bullet_lines(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    def initiative_name(self) -> str:
        prefixes = [
            "Atlas", "Northstar", "Summit", "Harbor",
            "Beacon", "Lattice", "Signal", "Cedar",
        ]
        nouns = [
            "launch review", "vendor recovery plan", "staffing sync",
            "operations readout", "forecast refresh", "policy review",
            "board prep", "customer rollout",
        ]
        return f"{self.rng.choice(prefixes)} {self.rng.choice(nouns)}"

    def generic_email_body(self, sender_name: str) -> str:
        first = self.first_name(sender_name)
        update_openers = [
            "Sharing the latest notes before tomorrow's check-in.",
            "Passing along the current draft so you have it in one place.",
            "Sending a quick status update from today's working session.",
            "I pulled the loose ends into one note for easier review.",
        ]
        middle_notes = [
            "The open items are mostly ownership questions rather than scope changes.",
            "Nothing looks blocked right now, but we still need one decision on timing.",
            "The team is aligned on the main path and only needs confirmation on the follow-up items.",
            "Most of the edits were minor, with one budget line still waiting on approval.",
        ]
        closers = [
            "No response needed unless you want anything reordered.",
            "If you want, I can turn this into a cleaner summary before the meeting.",
            "Happy to consolidate comments if more feedback comes in.",
            "Let me know if you want the spreadsheet version as well.",
        ]
        return self.format_email_body(
            self.rng.choice(update_openers),
            f"{self.rng.choice(middle_notes)} {self.rng.choice(closers)}",
            signoff_name=first,
        )

    # -- Model factories ---------------------------------------------------

    def contact(
        self,
        *,
        name: str | None = None,
        email: str | None = None,
        company: str | None = None,
        note: str | None = None,
        is_vip: bool = False,
        last_contacted_at: datetime | None = None,
    ) -> Contact:
        contact_name = name or self.fake.name()
        contact_email = email or self.email_for_name(contact_name)  # draws fake.domain_word()
        return Contact(
            id=self.next_id("contact"),
            name=contact_name,
            email=contact_email,
            company=company or self.fake.company(),
            note=note,
            is_vip=is_vip,
            source="seeded",
            last_contacted_at=last_contacted_at
            or (self.now - timedelta(days=self.rng.randint(1, 20))),
        )

    def email(
        self,
        *,
        from_name: str,
        from_addr: str,
        subject: str,
        body: str,
        timestamp: datetime,
        thread_id: str,
        labels: list[str] | None = None,
        is_read: bool = False,
        attachments: list[Attachment] | None = None,
        cc: list[str] | None = None,
    ) -> Email:
        return Email(
            id=self.next_id("email"),
            from_name=from_name,
            from_addr=from_addr,
            to=[self.owner_email],
            cc=cc or [],
            subject=subject,
            body=body,
            timestamp=timestamp,
            is_read=is_read,
            labels=labels or ["inbox"],
            thread_id=thread_id,
            attachments=attachments or [],
        )

    def attachment(
        self, filename: str, content_type: str, kind: str
    ) -> Attachment:
        return Attachment(
            id=self.next_id("attachment"),
            filename=filename,
            content_type=content_type,
            size_bytes=self.rng.randint(12_000, 120_000),
            kind=kind,
        )

    def ensure_contact(
        self,
        name: str,
        email: str,
        is_vip: bool = False,
    ) -> None:
        if any(
            c.email.lower() == email.lower() for c in self.base["contacts"]
        ):
            return
        self.base["contacts"].append(
            self.contact(
                name=name,
                email=email,
                is_vip=is_vip,
                last_contacted_at=self.now - timedelta(days=3),
            )
        )

    # -- Actor resolution --------------------------------------------------

    def resolve_actor(
        self,
        key: str,
        domain: str = "baseline.co",
        is_vip: bool = False,
        name: str | None = None,
    ) -> ResolvedActor:
        """Generate a deterministic actor and cache it under *key*."""
        if key in self.actors:
            return self.actors[key]
        name = name or self.fake.name()
        actor = ResolvedActor(
            name=name,
            email=self.email_for_name(name, domain=domain),
            first_name=self.first_name(name),
        )
        self.actors[key] = actor
        return actor

    # -- Output helpers ----------------------------------------------------

    def get_actor(self, key: str) -> ResolvedActor:
        """Return a previously resolved actor (raises KeyError if missing)."""
        return self.actors[key]


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------

BuilderFn = Callable[["SeedContext", dict[str, Any]], dict[str, Any]]

BUILDER_REGISTRY: dict[str, BuilderFn] = {}


def _register(name: str) -> Callable[[BuilderFn], BuilderFn]:
    def decorator(fn: BuilderFn) -> BuilderFn:
        BUILDER_REGISTRY[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Core builders
# ---------------------------------------------------------------------------

@_register("filler_emails")
def build_filler_emails(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate N generic / filler emails from an actor.

    Params
    ------
    actor : str          — actor key
    count : int          — number of emails (default 2)
    age_range : [lo, hi] — uniform-random day offset range (default [6, 12])
    is_read : bool       — default True
    labels : list[str]   — default ["inbox"]
    """
    actor = ctx.get_actor(params["actor"])
    count = params.get("count", 2)
    lo, hi = params.get("age_range", [6, 12])
    is_read = params.get("is_read", True)
    labels = params.get("labels", ["inbox"])

    email_ids: list[str] = []
    for _ in range(count):
        em = ctx.email(
            from_name=actor.name,
            from_addr=actor.email,
            subject=f"{ctx.initiative_name().title()} notes",
            body=ctx.generic_email_body(actor.name),
            timestamp=ctx.now - timedelta(days=ctx.rng.randint(lo, hi)),
            thread_id=ctx.next_id("thread"),
            labels=list(labels),
            is_read=is_read,
        )
        ctx.base["emails"].append(em)
        email_ids.append(em.id)
    return {"email_ids": email_ids}


@_register("email_thread")
def build_email_thread(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a multi-message email thread.

    Params
    ------
    actor : str                         — actor key for the sender
    subject_template : str              — subject with {time}, {initiative} placeholders
    messages : list[dict]               — list of {body: str} or {body_template: str}
    cc : list[str]                      — CC email addresses (default [])
    labels : list[str]                  — default ["inbox"]
    age_days_start : float              — offset for the first message
    age_days_step : float               — decrease per subsequent message
    """
    actor = ctx.get_actor(params["actor"])
    cc = params.get("cc", [])
    labels = params.get("labels", ["inbox"])
    messages = params["messages"]
    age_start = params.get("age_days_start", 6)
    age_step = params.get("age_days_step", 1)

    thread_id = ctx.next_id("thread")
    email_ids: list[str] = []
    for idx, msg in enumerate(messages):
        subject = msg.get("subject", params.get("subject", ""))
        body = msg["body"]
        ts = ctx.now - timedelta(
            days=age_start - idx * age_step,
            hours=2 * idx,
        )
        em = ctx.email(
            from_name=actor.name,
            from_addr=actor.email,
            subject=subject,
            body=body,
            timestamp=ts,
            thread_id=thread_id,
            labels=list(labels),
            cc=cc,
        )
        ctx.base["emails"].append(em)
        email_ids.append(em.id)
    return {"thread_id": thread_id, "email_ids": email_ids}


@_register("single_email")
def build_single_email(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create one email.

    Params
    ------
    actor : str
    subject : str
    body : str
    labels : list[str]
    is_read : bool
    age_days : float
    attachments : list[dict]    — [{filename, content_type, kind}]
    cc : list[str]
    """
    actor = ctx.get_actor(params["actor"])
    subject = params["subject"]
    body = params["body"]
    labels = params.get("labels", ["inbox"])
    is_read = params.get("is_read", False)
    age_days = params.get("age_days", 1)
    cc = params.get("cc", [])

    att_specs = params.get("attachments", [])
    attachments = [
        ctx.attachment(a["filename"], a["content_type"], a["kind"])
        for a in att_specs
    ]

    thread_id = ctx.next_id("thread")
    em = ctx.email(
        from_name=actor.name,
        from_addr=actor.email,
        subject=subject,
        body=body,
        timestamp=ctx.now - timedelta(days=age_days),
        thread_id=thread_id,
        labels=list(labels),
        is_read=is_read,
        attachments=attachments,
        cc=cc,
    )
    ctx.base["emails"].append(em)
    return {"email_id": em.id, "thread_id": thread_id}


@_register("contact_set")
def build_contact_set(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create contacts.

    Params
    ------
    count : int
    staleness_days : int    — last_contacted_at offset (default random 1-20)
    is_vip : bool           — default False
    """
    count = params.get("count", 5)
    is_vip = params.get("is_vip", False)
    staleness = params.get("staleness_days", None)

    contact_ids: list[str] = []
    for _ in range(count):
        lca = (
            (ctx.now - timedelta(days=staleness))
            if staleness is not None
            else None
        )
        c = ctx.contact(is_vip=is_vip, last_contacted_at=lca)
        ctx.base["contacts"].append(c)
        contact_ids.append(c.id)
    return {"contact_ids": contact_ids}


@_register("label_set")
def build_label_set(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create custom labels.

    Params
    ------
    names : list[dict]  — [{name, color}]
    """
    label_ids: list[str] = []
    for spec in params.get("names", []):
        name = spec if isinstance(spec, str) else spec["name"]
        color = spec.get("color", "#5f6368") if isinstance(spec, dict) else "#5f6368"
        lid = f"label_{name.lower().replace(' ', '_')}"
        ctx.base["labels"].append(
            Label(id=lid, name=name, color=color)
        )
        label_ids.append(lid)
    return {"label_ids": label_ids}


# ---------------------------------------------------------------------------
# Task-specific composite builders
# ---------------------------------------------------------------------------

@_register("scheduling_conflicts")
def build_scheduling_conflicts(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create the scheduling-thread + calendar-conflict puzzle.

    Generates 5 scheduling threads (one per meeting time), a real calendar
    conflict email listing 4 conflicts, a decoy calendar email with only 2,
    and emits all computed target values.

    Params
    ------
    sender : str            — actor key for the scheduling sender
    other_sender : str      — actor key for the calendar sender
    cc : str                — actor key for the CC recipient
    meeting_times : list    — e.g. ["9:00 AM", "10:00 AM", ...]
    """
    sender = ctx.get_actor(params["sender"])
    other = ctx.get_actor(params["other_sender"])
    cc_actor = ctx.get_actor(params["cc"])

    meeting_times: list[str] = params["meeting_times"]
    correct_index = ctx.rng.randrange(len(meeting_times))
    correct_time = meeting_times[correct_index]
    wrong_times = [t for i, t in enumerate(meeting_times) if i != correct_index]

    initiative = ctx.initiative_name()
    calendar_subject = f"Calendar conflicts for the {initiative}"

    option_notes = [
        "That slot would let us finalize the owner list before the design walkthrough starts.",
        "I can keep that window clear if we want to use it for the full agenda.",
        "That time works on my end and still leaves room for a short follow-up with finance.",
        "I could make that slot work if we want the review done before end-of-day wrap-up.",
        "That would give us a clean hour before the operations wrap-up at end of day.",
    ]
    conflict_reasons = ctx.rng.sample(
        [
            "standing finance review",
            "candidate interview panel",
            "facilities walkthrough",
            "vendor contract call",
            "customer escalation sync",
            "legal review hold",
            "quarterly planning block",
            "executive budget sync",
        ],
        k=len(wrong_times),
    )

    # 5 scheduling threads — one per meeting time
    thread_ids: list[str] = []
    for index, meeting_time in enumerate(meeting_times):
        thread_id = ctx.next_id("thread")
        thread_ids.append(thread_id)
        sent_at = ctx.now - timedelta(days=6 - index, hours=2 * index)
        ctx.base["emails"].append(
            ctx.email(
                from_name=sender.name,
                from_addr=sender.email,
                subject=f"Could we hold {meeting_time} for the {initiative}?",
                body=ctx.format_email_body(
                    (
                        f"Hi Avery, could we use {meeting_time} for the {initiative}? "
                        f"{option_notes[index]}"
                    ),
                    (
                        "If that time is difficult on your side, I can keep circulating options, "
                        "but I wanted to send the cleanest windows first."
                    ),
                    signoff_name=sender.first_name,
                ),
                timestamp=sent_at,
                thread_id=thread_id,
                labels=["inbox", "VIP"],
                cc=[cc_actor.email],
            )
        )

    most_recent_thread_id = thread_ids[-1]
    conflict_lines = [
        f"{mt}: already blocked by the {reason}"
        for mt, reason in zip(wrong_times, conflict_reasons, strict=False)
    ]

    # Real calendar email (pushed to page 2 / Updates tab)
    calendar_email = ctx.email(
        from_name=other.name,
        from_addr=other.email,
        subject=calendar_subject,
        body=ctx.format_email_body(
            (
                f"I checked the proposed times from {sender.first_name} against the operating calendar "
                f"for the {initiative}. The following options already have immovable holds:"
            ),
            ctx.bullet_lines(conflict_lines),
            (
                "I have not placed anything on your calendar yet because I wanted to send the "
                "conflicts first."
            ),
            signoff_name=other.first_name,
        ),
        timestamp=ctx.now - timedelta(days=7),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "updates", "important"],
    )
    ctx.base["emails"].append(calendar_email)

    # Decoy calendar email (outdated, only 2 conflicts)
    decoy_conflict_lines = ctx.rng.sample(conflict_lines, k=2)
    ctx.base["emails"].append(
        ctx.email(
            from_name=other.name,
            from_addr=other.email,
            subject=f"Preliminary calendar notes for the {initiative}",
            body=ctx.format_email_body(
                (
                    f"Quick preliminary note — I saw a couple of possible conflicts on the operating "
                    f"calendar for the {initiative}:"
                ),
                ctx.bullet_lines(decoy_conflict_lines),
                (
                    "I will send a full conflict check once I can verify the rest. This is only "
                    "an early heads-up."
                ),
                signoff_name=other.first_name,
            ),
            timestamp=ctx.now - timedelta(days=9),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
            is_read=True,
        )
    )

    # Ensure contacts
    ctx.ensure_contact(sender.name, sender.email, is_vip=True)
    ctx.ensure_contact(other.name, other.email)
    ctx.ensure_contact(cc_actor.name, cc_actor.email)

    return {
        "sender_name": sender.name,
        "sender_email": sender.email,
        "other_sender_name": other.name,
        "other_sender_email": other.email,
        "calendar_subject": calendar_subject,
        "calendar_email_id": calendar_email.id,
        "correct_time": correct_time,
        "wrong_times": wrong_times,
        "most_recent_thread_id": most_recent_thread_id,
    }


# ---------------------------------------------------------------------------
# Gmail: Label Workflow Setup (Task 12)
# ---------------------------------------------------------------------------

@_register("label_workflow_setup")
def build_label_workflow_setup(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create the label-workflow puzzle: client emails, review emails, and a wrong-review decoy.

    Params
    ------
    client_domain : str  — domain for the two client senders (default "meridiangroup.com")
    """
    client_domain = params.get("client_domain", "meridiangroup.com")

    client_a_name = ctx.fake.name()
    client_b_name = ctx.fake.name()
    client_a_email = ctx.email_for_name(client_a_name, domain=client_domain)
    client_b_email = ctx.email_for_name(client_b_name, domain=client_domain)

    # 2 client emails
    client_email_a = ctx.email(
        from_name=client_a_name,
        from_addr=client_a_email,
        subject="Client deliverable feedback",
        body=ctx.format_email_body(
            "We reviewed the latest deliverable and have a few notes.",
            "Overall the direction looks good. A couple of items need adjustment before sign-off.",
            signoff_name=ctx.first_name(client_a_name),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=3),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )
    client_email_b = ctx.email(
        from_name=client_b_name,
        from_addr=client_b_email,
        subject="Client contract renewal",
        body=ctx.format_email_body(
            "Sending the updated contract terms for review.",
            "Please confirm the revised pricing before end of week.",
            signoff_name=ctx.first_name(client_b_name),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=5),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # 3 emails with "review" in subject (2 legit, 1 wrong)
    review_a_name = ctx.fake.name()
    review_a_email = ctx.email_for_name(review_a_name, domain="internal.thornton.com")
    review_email_a = ctx.email(
        from_name=review_a_name,
        from_addr=review_a_email,
        subject="Code review for sprint 12",
        body=ctx.format_email_body(
            "The code review for sprint 12 is ready.",
            "Please take a look at the pull requests when you have a chance.",
            signoff_name=ctx.first_name(review_a_name),
        ),
        timestamp=ctx.now - timedelta(days=3, hours=1),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    review_b_name = ctx.fake.name()
    review_b_email = ctx.email_for_name(review_b_name, domain="internal.thornton.com")
    review_email_b = ctx.email(
        from_name=review_b_name,
        from_addr=review_b_email,
        subject="Design review notes",
        body=ctx.format_email_body(
            "Sharing the design review notes from yesterday's session.",
            "The team agreed on the main layout changes and the color palette.",
            signoff_name=ctx.first_name(review_b_name),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=7),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # Wrong review — leisure book review, should NOT keep Needs Review
    wrong_review_name = ctx.fake.name()
    wrong_review_email = ctx.email_for_name(wrong_review_name, domain="gmail.com")
    wrong_review_subject = "Book review for leisure reading club"
    wrong_review_email_obj = ctx.email(
        from_name=wrong_review_name,
        from_addr=wrong_review_email,
        subject=wrong_review_subject,
        body=ctx.format_email_body(
            "Here is my review of the book we discussed at the leisure reading club.",
            "I thought the narrative arc was strong but the ending felt rushed.",
            signoff_name=ctx.first_name(wrong_review_name),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # A non-review email that should never get Needs Review label
    non_review_name = ctx.fake.name()
    non_review_email_addr = ctx.email_for_name(non_review_name, domain="logistics.co")
    non_review_email_obj = ctx.email(
        from_name=non_review_name,
        from_addr=non_review_email_addr,
        subject="Shipping schedule update",
        body=ctx.format_email_body(
            "The shipping schedule has been updated for next week.",
            "All items are on track for delivery by Friday.",
            signoff_name=ctx.first_name(non_review_name),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        client_email_a, client_email_b,
        review_email_a, review_email_b, wrong_review_email_obj,
        non_review_email_obj,
    ])

    client_email_ids = [client_email_a.id, client_email_b.id]
    review_email_ids = [review_email_a.id, review_email_b.id]
    project_email_ids = client_email_ids + review_email_ids

    return {
        "client_domain": client_domain,
        "client_email_ids": client_email_ids,
        "review_email_ids": review_email_ids,
        "wrong_review_subject": wrong_review_subject,
        "wrong_review_id": wrong_review_email_obj.id,
        "correct_non_review_id": non_review_email_obj.id,
        "project_email_ids": project_email_ids,
    }


# ---------------------------------------------------------------------------
# Gmail: Phishing Investigation (Task 13)
# ---------------------------------------------------------------------------

@_register("phishing_investigation")
def build_phishing_investigation(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create phishing vs. legitimate email puzzle.

    Params
    ------
    security_team_email : str  — address to report phishing to (default "security-team@thornton.com")
    phishing_domain : str      — domain for phishing senders (default "secure-acme.net")
    """
    security_team_email = params.get("security_team_email", "security-team@thornton.com")
    phishing_domain = params.get("phishing_domain", "secure-acme.net")

    # Legit A
    legit_a = ctx.email(
        from_name="IT Department",
        from_addr="it-support@thornton.com",
        subject="Security patch ready for deployment",
        body=ctx.format_email_body(
            "The latest security patch is ready for deployment. Please review the attached documentation.",
            "We will proceed with the rollout on Monday unless there are objections.",
            signoff_name="IT Department",
        ),
        timestamp=ctx.now - timedelta(days=1, hours=6),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        is_read=False,
        attachments=[ctx.attachment("security-update.pdf", "application/pdf", "pdf")],
    )

    # Legit B
    legit_b = ctx.email(
        from_name="HR Team",
        from_addr="hr@thornton.com",
        subject="Updated benefits guide for Q2",
        body=ctx.format_email_body(
            "Please find the updated benefits guide for Q2 attached.",
            "The main changes are to the dental and vision plans. Open enrollment closes Friday.",
            signoff_name="HR Team",
        ),
        timestamp=ctx.now - timedelta(days=1, hours=4),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        is_read=False,
        attachments=[ctx.attachment("benefits-guide.pdf", "application/pdf", "pdf")],
    )

    # Phishing A — name says "IT Department" but address is phishing domain
    phishing_subject_a = "URGENT: Critical security update required"
    phishing_a = ctx.email(
        from_name="IT Department",
        from_addr=f"it.support@{phishing_domain}",
        subject=phishing_subject_a,
        body=ctx.format_email_body(
            "Your account has been flagged for a critical security vulnerability.",
            "Please download and run the attached update immediately to secure your workstation.",
            signoff_name="IT Support Team",
        ),
        timestamp=ctx.now - timedelta(hours=8),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        is_read=False,
        attachments=[ctx.attachment("urgent-update.exe", "application/octet-stream", "executable")],
    )

    # Phishing B — name says "Payroll" but address is phishing domain
    phishing_subject_b = "Your salary review is ready"
    phishing_b = ctx.email(
        from_name="Payroll",
        from_addr=f"payroll@{phishing_domain}",
        subject=phishing_subject_b,
        body=ctx.format_email_body(
            "Your annual salary review has been completed. Please open the attached file to see the details.",
            "This is a time-sensitive document. Respond within 24 hours to confirm.",
            signoff_name="Payroll Department",
        ),
        timestamp=ctx.now - timedelta(hours=6),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        is_read=False,
        attachments=[ctx.attachment("salary-review.zip", "application/zip", "archive")],
    )

    ctx.base["emails"].extend([legit_a, legit_b, phishing_a, phishing_b])

    phishing_ids = [phishing_a.id, phishing_b.id]
    legit_ids = [legit_a.id, legit_b.id]

    return {
        "phishing_ids": phishing_ids,
        "legit_ids": legit_ids,
        "security_team_email": security_team_email,
        "phishing_subject_a": phishing_subject_a,
        "phishing_subject_b": phishing_subject_b,
        "phishing_domain": phishing_domain,
    }


# ---------------------------------------------------------------------------
# Gmail: New Hire Setup (Task 14)
# ---------------------------------------------------------------------------

@_register("new_hire_setup")
def build_new_hire_setup(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create the new-hire onboarding puzzle: welcome emails, settings overrides, contacts.

    Params
    ------
    team_list_email : str           — team mailing list (default "eng-team@thornton.com")
    manager_email : str             — manager address (default "manager@thornton.com")
    hiring_manager_email : str      — hiring manager address (default "hiring-manager@thornton.com")
    intro_phrase : str              — phrase to include in reply
    company_name : str              — company name used in welcome bodies (default "Northwind Labs")
    team_cc : list[str]             — CC addresses on the main welcome email
    """
    team_list_email = params.get("team_list_email", "eng-team@thornton.com")
    manager_email = params.get("manager_email", "manager@thornton.com")
    hiring_manager_email = params.get("hiring_manager_email", "hiring-manager@thornton.com")
    intro_phrase = params.get(
        "intro_phrase",
        "Thanks for the warm welcome! Looking forward to working with the team.",
    )
    company_name = params.get("company_name", "Northwind Labs")
    team_cc = params.get("team_cc", [
        "dev-a@thornton.com",
        "dev-b@thornton.com",
        "dev-c@thornton.com",
        "dev-d@thornton.com",
        "dev-e@thornton.com",
    ])

    # 3 welcome emails from team leads
    eng_lead_name = ctx.fake.name()
    eng_lead_email = ctx.email_for_name(eng_lead_name, domain="thornton.com")
    design_lead_name = ctx.fake.name()
    design_lead_email = ctx.email_for_name(design_lead_name, domain="thornton.com")
    product_lead_name = ctx.fake.name()
    product_lead_email = ctx.email_for_name(product_lead_name, domain="thornton.com")

    # The main welcome email (from eng lead) — CC'd to entire team
    welcome_email = ctx.email(
        from_name=eng_lead_name,
        from_addr=eng_lead_email,
        subject="Welcome to the team!",
        body=ctx.format_email_body(
            f"Welcome! I'm {eng_lead_name}, leading engineering at {company_name}.",
            "We are excited to have you on board. Please do not hesitate to reach out if you have any questions.",
            "Looking forward to working together on the upcoming sprint.",
            signoff_name=ctx.first_name(eng_lead_name),
        ),
        timestamp=ctx.now - timedelta(hours=6),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        cc=team_cc,
    )

    design_welcome = ctx.email(
        from_name=design_lead_name,
        from_addr=design_lead_email,
        subject="Welcome from Design",
        body=ctx.format_email_body(
            f"Hi there! I'm {design_lead_name}, the design lead at {company_name}.",
            "Feel free to stop by the design studio on the 3rd floor anytime.",
            "We have a team lunch every Thursday — you are welcome to join.",
            signoff_name=ctx.first_name(design_lead_name),
        ),
        timestamp=ctx.now - timedelta(hours=5),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    product_welcome = ctx.email(
        from_name=product_lead_name,
        from_addr=product_lead_email,
        subject="Welcome from Product",
        body=ctx.format_email_body(
            f"Welcome aboard! I'm {product_lead_name}, heading product at {company_name}.",
            "I will set up a 1:1 with you later this week to walk you through our roadmap.",
            "In the meantime, check out the product wiki for context on our current priorities.",
            signoff_name=ctx.first_name(product_lead_name),
        ),
        timestamp=ctx.now - timedelta(hours=4),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    ctx.base["emails"].extend([welcome_email, design_welcome, product_welcome])

    new_contact_emails = [eng_lead_email, design_lead_email, product_lead_email]

    # Set display density to something other than "comfortable" so the agent has to change it
    ctx.base["settings"].display_density = "default"
    # Undo send starts at 5, agent must set to 30
    # default_reply_behavior — change it so agent must set it
    ctx.base["settings"].default_reply_behavior = "reply_all"
    # send_and_archive already False, agent must enable

    return {
        "team_list_email": team_list_email,
        "manager_email": manager_email,
        "hiring_manager_email": hiring_manager_email,
        "intro_phrase": intro_phrase,
        "welcome_sender_name": eng_lead_name,
        "welcome_id": welcome_email.id,
        "new_contact_emails": new_contact_emails,
    }


# ---------------------------------------------------------------------------
# Gmail: Quarterly Closeout (Task 15)
# ---------------------------------------------------------------------------

@_register("quarterly_closeout")
def build_quarterly_closeout(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create the quarterly-closeout puzzle: stars, archives, forwards, contacts, filters.

    Params
    ------
    star_keyword_a : str        — keyword in the first star-worthy email (default "board presentation")
    star_keyword_b : str        — keyword in the second star-worthy email (default "renewal deadline")
    update_topic : str          — topic for the update-tab emails (default "infrastructure migration")
    team_digest_email : str     — forwarding target (default "team-digest@thornton.com")
    vendor_domain : str         — domain for the vendor filter (default "brightleaf.io")
    vendor_label : str          — label name for vendor filter (default "Vendor Invoices")
    new_note : str              — note to set on a contact (default "Key contact for Q2 planning.")
    """
    star_keyword_a = params.get("star_keyword_a", "board presentation")
    star_keyword_b = params.get("star_keyword_b", "renewal deadline")
    fyi_sender_name = ctx.fake.name()
    fyi_sender_email = ctx.email_for_name(fyi_sender_name, domain="internal.thornton.com")
    update_topic = params.get("update_topic", "infrastructure migration")
    team_digest_email = params.get("team_digest_email", "team-digest@thornton.com")
    vendor_domain = params.get("vendor_domain", "brightleaf.io")
    vendor_label = params.get("vendor_label", "Vendor Invoices")
    new_note = params.get("new_note", "Key contact for Q2 planning.")

    # --- Primary tab: 2 important + 3 FYI ---
    star_a = ctx.email(
        from_name=ctx.fake.name(),
        from_addr=ctx.email_for_name("star-a", domain="summitview.co"),
        subject="Preparation for the board presentation",
        body=ctx.format_email_body(
            "We need to finalize the board presentation materials before Thursday.",
            "Please review the attached deck and send your comments by end of day.",
            signoff_name="Leadership",
        ),
        timestamp=ctx.now - timedelta(days=1, hours=3),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )
    star_b = ctx.email(
        from_name=ctx.fake.name(),
        from_addr=ctx.email_for_name("star-b", domain="contracts.co"),
        subject="Upcoming renewal deadline for enterprise license",
        body=ctx.format_email_body(
            "Reminder: the enterprise license renewal deadline is next Friday.",
            "We need to confirm the renewal terms and budget allocation.",
            signoff_name="Contracts",
        ),
        timestamp=ctx.now - timedelta(days=1, hours=1),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    fyi_emails = []
    for i in range(3):
        fyi = ctx.email(
            from_name=fyi_sender_name,
            from_addr=fyi_sender_email,
            subject=f"FYI: Weekly status update #{i + 1}",
            body=ctx.format_email_body(
                f"FYI — sharing the weekly status update #{i + 1}.",
                "No action needed on your end. Just keeping you in the loop.",
                signoff_name=ctx.first_name(fyi_sender_name),
            ),
            timestamp=ctx.now - timedelta(days=8 + i, hours=2),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        )
        fyi_emails.append(fyi)

    # --- Promotions tab: 3 newsletters + 1 spam ---
    promo_emails = []
    for i in range(3):
        newsletter = ctx.email(
            from_name=f"Newsletter {chr(65 + i)}",
            from_addr=f"news{i + 1}@newsletters.substack.com",
            subject=f"Weekly digest #{i + 1}",
            body=ctx.format_email_body(
                f"Here is your weekly digest #{i + 1}.",
                "Top stories, product updates, and community highlights.",
            ),
            timestamp=ctx.now - timedelta(days=2 + i, hours=5),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "promotions"],
        )
        promo_emails.append(newsletter)

    spam_subject = "Exclusive prize giveaway"
    spam_email = ctx.email(
        from_name="Prize Center",
        from_addr="noreply@megasale.net",
        subject=spam_subject,
        body=ctx.format_email_body(
            "Congratulations! You have been selected for an exclusive prize giveaway!",
            "Click below to claim your reward. Offer expires in 24 hours.",
        ),
        timestamp=ctx.now - timedelta(days=1, hours=8),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "promotions"],
    )

    # --- Updates tab: 2 update emails ---
    update_emails = []
    for i in range(2):
        update = ctx.email(
            from_name="DevOps Team",
            from_addr=f"devops{i + 1}@infra.thornton.com",
            subject=f"Infrastructure migration update — phase {i + 1}",
            body=ctx.format_email_body(
                f"Update on the infrastructure migration: phase {i + 1} is complete.",
                "All services have been migrated successfully with no downtime reported.",
            ),
            timestamp=ctx.now - timedelta(days=3 + i, hours=4),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
        )
        update_emails.append(update)

    # --- Vendor email for filter domain discovery ---
    vendor_email = ctx.email(
        from_name="Acme Vendor Support",
        from_addr=f"support@{vendor_domain}",
        subject="Invoice #4421 — monthly service fee",
        body=ctx.format_email_body(
            "Please find invoice #4421 attached for the monthly service fee.",
            "Payment is due within 30 days.",
            signoff_name="Acme Vendor Support",
        ),
        timestamp=ctx.now - timedelta(days=5, hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        star_a, star_b, *fyi_emails, *promo_emails, spam_email,
        *update_emails, vendor_email,
    ])

    # --- Contacts ---
    stale_a = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="pinevalley.co"),
        last_contacted_at=ctx.now - timedelta(days=45),
    )
    stale_b = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="millbrook.co"),
        last_contacted_at=ctx.now - timedelta(days=60),
    )
    active_contact = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="active.io"),
        last_contacted_at=ctx.now - timedelta(days=5),
    )
    update_contact_name = ctx.fake.name()
    update_contact_email_addr = ctx.email_for_name(update_contact_name, domain="planning.co")
    update_contact = ctx.contact(
        name=update_contact_name,
        email=update_contact_email_addr,
        last_contacted_at=ctx.now - timedelta(days=10),
    )

    ctx.base["contacts"].extend([stale_a, stale_b, active_contact, update_contact])

    fyi_ids = [e.id for e in fyi_emails]
    promo_ids = [e.id for e in promo_emails]
    update_ids = [e.id for e in update_emails]

    return {
        "star_a_id": star_a.id,
        "star_b_id": star_b.id,
        "star_keyword_a": star_keyword_a,
        "star_keyword_b": star_keyword_b,
        "fyi_ids": fyi_ids,
        "fyi_sender_name": fyi_sender_name,
        "promo_ids": promo_ids,
        "spam_id": spam_email.id,
        "spam_subject": spam_subject,
        "update_ids": update_ids,
        "update_topic": update_topic,
        "team_digest_email": team_digest_email,
        "stale_a_id": stale_a.id,
        "stale_b_id": stale_b.id,
        "update_contact_name": update_contact_name,
        "update_contact_email": update_contact_email_addr,
        "new_note": new_note,
        "vendor_domain": vendor_domain,
        "vendor_label": vendor_label,
        "active_contact_id": active_contact.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Vacation Preparation (Task 7)
# ---------------------------------------------------------------------------

@_register("vacation_preparation")
def build_vacation_preparation(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Set up vacation-prep scenario with OOO settings and pending emails.

    Creates three pending emails (vendor proposal, project timeline, attendance
    confirmation). Two of them mention "follow up when you're back" and should
    be starred on return.

    Params
    ------
    (none -- all names / addresses are generated internally)
    """
    vacation_message = "I am out of office until March 21. For urgent matters, contact my backup."
    ooo_note = "OOO until March 21"
    boss_name = ctx.fake.name()
    boss_email = ctx.email_for_name(boss_name, domain="silverpeak.co")
    backup_name = ctx.fake.name()
    backup_email = ctx.email_for_name(backup_name, domain="ops-backup.com")

    # Pending A: vendor proposal
    pending_a_sender = ctx.fake.name()
    pending_a_email = ctx.email_for_name(pending_a_sender, domain="vendors.co")
    pending_a = ctx.email(
        from_name=pending_a_sender,
        from_addr=pending_a_email,
        subject="Vendor proposal for Q2 office supplies",
        body=ctx.format_email_body(
            "Attached is the vendor proposal for Q2 office supplies. Could you review the pricing and "
            "confirm whether we should move forward?",
            "Please follow up when you're back — I know you have a lot on your plate before vacation.",
            signoff_name=ctx.first_name(pending_a_sender),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=3),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # Pending B: timeline email with CC (Reply All trap)
    pending_b_sender = ctx.fake.name()
    pending_b_email = ctx.email_for_name(pending_b_sender, domain="pm.thornton.com")
    cc_b1 = ctx.email_for_name(ctx.fake.name(), domain="pm.thornton.com")
    cc_b2 = ctx.email_for_name(ctx.fake.name(), domain="pm.thornton.com")
    pending_b = ctx.email(
        from_name=pending_b_sender,
        from_addr=pending_b_email,
        subject="Project timeline for the infrastructure rollout",
        body=ctx.format_email_body(
            "Here is the updated timeline for the infrastructure rollout. Can you confirm you are "
            "aligned on the milestones?",
            "I need to follow up when you're back on the resource allocation for phase 2.",
            signoff_name=ctx.first_name(pending_b_sender),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=6),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        cc=[cc_b1, cc_b2],
    )

    # Pending C: attendance confirmation
    pending_c_sender = ctx.fake.name()
    pending_c_email = ctx.email_for_name(pending_c_sender, domain="events.io")
    pending_c = ctx.email(
        from_name=pending_c_sender,
        from_addr=pending_c_email,
        subject="Confirm attendance for the leadership retreat",
        body=ctx.format_email_body(
            "Please confirm whether you will attend the leadership retreat on March 25.",
            "We need final headcounts by end of week.",
            signoff_name=ctx.first_name(pending_c_sender),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # The return_ids are pending_a and pending_b (they mention "follow up when you're back")
    return_ids = [pending_a.id, pending_b.id]

    ctx.base["emails"].extend([pending_a, pending_b, pending_c])
    ctx.ensure_contact(pending_a_sender, pending_a_email)
    ctx.ensure_contact(pending_b_sender, pending_b_email)
    ctx.ensure_contact(pending_c_sender, pending_c_email)
    ctx.ensure_contact(boss_name, boss_email, is_vip=True)
    ctx.ensure_contact(backup_name, backup_email)

    return {
        "vacation_message": vacation_message,
        "ooo_note": ooo_note,
        "boss_email": boss_email,
        "backup_email": backup_email,
        "pending_a_sender": pending_a_sender,
        "pending_a_id": pending_a.id,
        "pending_b_sender": pending_b_sender,
        "pending_b_id": pending_b.id,
        "pending_c_sender": pending_c_sender,
        "pending_c_id": pending_c.id,
        "return_ids": return_ids,
    }


# ---------------------------------------------------------------------------
# Gmail: Contact Audit (Task 8)
# ---------------------------------------------------------------------------

@_register("contact_audit")
def build_contact_audit(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create stale, near-threshold, and keep contacts plus new-contact emails.

    Params
    ------
    (none -- all names / addresses are generated internally)
    """
    # 4 stale contacts (35-60 days since last contact)
    stale_contacts = []
    stale_days = [35, 42, 50, 60]
    for days in stale_days:
        contact = ctx.contact(
            name=ctx.fake.name(),
            email=ctx.fake.email(domain="tannerfield.io"),
            last_contacted_at=ctx.now - timedelta(days=days),
        )
        stale_contacts.append(contact)

    # 2 near-threshold contacts (22-28 days, should NOT be deleted)
    near_threshold_a = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="coastline.co"),
        last_contacted_at=ctx.now - timedelta(days=22),
    )
    near_threshold_b = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="greyzone.co"),
        last_contacted_at=ctx.now - timedelta(days=28),
    )

    # 1 keep contact (5 days, explicitly named in instruction)
    keep_contact = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="activeteam.thornton.com"),
        last_contacted_at=ctx.now - timedelta(days=5),
    )

    ctx.base["contacts"].extend(
        stale_contacts + [near_threshold_a, near_threshold_b, keep_contact]
    )

    # 2 emails from people NOT in contacts
    new_contact_a_name = ctx.fake.name()
    new_a_email = ctx.email_for_name(new_contact_a_name, domain="brighthorizon.co")
    new_contact_b_name = ctx.fake.name()
    new_b_email = ctx.email_for_name(new_contact_b_name, domain="consultant.co")

    ctx.base["emails"].extend([
        ctx.email(
            from_name=new_contact_a_name,
            from_addr=new_a_email,
            subject="Partnership opportunity — Q2 logistics",
            body=ctx.format_email_body(
                f"Hi Avery, my name is {new_contact_a_name} and I work at NewPartner Logistics. "
                "I would love to discuss a potential partnership for Q2.",
                f"You can reach me at {new_a_email} or on my direct line.",
                signoff_name=ctx.first_name(new_contact_a_name),
            ),
            timestamp=ctx.now - timedelta(days=1, hours=3),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        ),
        ctx.email(
            from_name=new_contact_b_name,
            from_addr=new_b_email,
            subject="Consulting engagement follow-up",
            body=ctx.format_email_body(
                f"Hi Avery, this is {new_contact_b_name} from the consulting engagement last month. "
                "I wanted to follow up on the deliverables we discussed.",
                f"My email is {new_b_email} — feel free to add me to your contacts for future correspondence.",
                signoff_name=ctx.first_name(new_contact_b_name),
            ),
            timestamp=ctx.now - timedelta(days=2, hours=5),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        ),
    ])

    return {
        "stale_1_id": stale_contacts[0].id,
        "stale_2_id": stale_contacts[1].id,
        "stale_3_id": stale_contacts[2].id,
        "stale_4_id": stale_contacts[3].id,
        "near_id": near_threshold_a.id,
        "near_b_id": near_threshold_b.id,
        "keep_contact_name": keep_contact.name,
        "keep_contact_id": keep_contact.id,
        "new_contact_a_name": new_contact_a_name,
        "new_contact_b_name": new_contact_b_name,
        "new_a_email": new_a_email,
        "new_b_email": new_b_email,
    }


# ---------------------------------------------------------------------------
# Gmail: Thread Archaeology (Task 9)
# ---------------------------------------------------------------------------

@_register("thread_archaeology")
def build_thread_archaeology(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a 6-message thread with buried action-item assignment and deadline.

    The key info (assignee, deadline, manager) is in the middle messages, not
    the latest one.  A wrong-person confuser is also included.

    Params
    ------
    (none -- all names / addresses are generated internally)
    """
    thread_subject = f"{ctx.initiative_name()} action items"
    thread_id = ctx.next_id("thread")
    assignee_name = ctx.fake.name()
    assignee_email = ctx.email_for_name(assignee_name, domain="teamlead.com")
    manager_name = ctx.fake.name()
    manager_email = ctx.email_for_name(manager_name, domain="management.com")
    wrong_person_name = ctx.fake.name()
    wrong_person_email = ctx.email_for_name(wrong_person_name, domain="crossteam.thornton.com")
    deadline = "March 20"

    # Generate 5 different senders for the thread messages
    sender_names = [ctx.fake.name() for _ in range(5)]
    sender_emails = [
        ctx.email_for_name(n, domain="projectteam.thornton.com") for n in sender_names
    ]

    # Message 1 (oldest): initial discussion
    msg_1 = ctx.email(
        from_name=sender_names[0],
        from_addr=sender_emails[0],
        subject=thread_subject,
        body=ctx.format_email_body(
            f"Kicking off the discussion on the {thread_subject}. We need to identify owners for "
            "each deliverable and set clear deadlines.",
            "I will send a follow-up once we hear back from everyone.",
            signoff_name=ctx.first_name(sender_names[0]),
        ),
        timestamp=ctx.now - timedelta(days=5, hours=10),
        thread_id=thread_id,
        labels=["inbox"],
    )

    # Message 2: mentions the deadline
    msg_2 = ctx.email(
        from_name=sender_names[1],
        from_addr=sender_emails[1],
        subject=f"Re: {thread_subject}",
        body=ctx.format_email_body(
            f"The key deliverable needs to be completed by {deadline}. That is our hard deadline "
            "from the steering committee.",
            "We should make sure whoever owns this has enough runway to finish on time.",
            signoff_name=ctx.first_name(sender_names[1]),
        ),
        timestamp=ctx.now - timedelta(days=4, hours=8),
        thread_id=thread_id,
        labels=["inbox"],
    )

    # Message 3: assigns action item to assignee
    msg_3 = ctx.email(
        from_name=sender_names[2],
        from_addr=sender_emails[2],
        subject=f"Re: {thread_subject}",
        body=ctx.format_email_body(
            f"I think {assignee_name} should take point on this. They have the most context on the "
            "integration work and can coordinate with the vendor directly.",
            f"Their email is {assignee_email} if you need to reach out.",
            signoff_name=ctx.first_name(sender_names[2]),
        ),
        timestamp=ctx.now - timedelta(days=3, hours=6),
        thread_id=thread_id,
        labels=["inbox"],
    )

    # Message 4: mentions manager for visibility
    msg_4 = ctx.email(
        from_name=sender_names[3],
        from_addr=sender_emails[3],
        subject=f"Re: {thread_subject}",
        body=ctx.format_email_body(
            f"Loop in {manager_name} for visibility — they should be aware of the timeline and "
            "resource commitment.",
            f"Their address is {manager_email}.",
            signoff_name=ctx.first_name(sender_names[3]),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=4),
        thread_id=thread_id,
        labels=["inbox"],
    )

    # Message 5: side discussion with WRONG person mentioned (confuser)
    msg_5 = ctx.email(
        from_name=sender_names[4],
        from_addr=sender_emails[4],
        subject=f"Re: {thread_subject}",
        body=ctx.format_email_body(
            f"By the way, {wrong_person_name} mentioned they might have bandwidth to help with "
            "the secondary tasks, but I do not think they should own the main action item.",
            f"Their address is {wrong_person_email} if needed for the side tasks.",
            signoff_name=ctx.first_name(sender_names[4]),
        ),
        timestamp=ctx.now - timedelta(days=1, hours=8),
        thread_id=thread_id,
        labels=["inbox"],
    )

    # Message 6 (newest, auto-expanded): general follow-up, no critical info
    msg_6 = ctx.email(
        from_name=sender_names[0],
        from_addr=sender_emails[0],
        subject=f"Re: {thread_subject}",
        body=ctx.format_email_body(
            "Just bumping this thread to keep it visible. Can someone confirm ownership and next "
            "steps so we can close the planning phase?",
            "I will check back at the end of the week if I do not hear anything.",
            signoff_name=ctx.first_name(sender_names[0]),
        ),
        timestamp=ctx.now - timedelta(hours=6),
        thread_id=thread_id,
        labels=["inbox"],
    )

    ctx.base["emails"].extend([msg_1, msg_2, msg_3, msg_4, msg_5, msg_6])
    for name, email_addr in zip(sender_names, sender_emails):
        ctx.ensure_contact(name, email_addr)
    ctx.ensure_contact(assignee_name, assignee_email)
    ctx.ensure_contact(manager_name, manager_email)
    ctx.ensure_contact(wrong_person_name, wrong_person_email)

    return {
        "thread_subject": thread_subject,
        "thread_email_id": msg_6.id,
        "assignee_email": assignee_email,
        "assignee_name": assignee_name,
        "manager_email": manager_email,
        "manager_name": manager_name,
        "deadline": deadline,
        "wrong_person_email": wrong_person_email,
    }


# ---------------------------------------------------------------------------
# Gmail: Filter Overhaul (Task 10)
# ---------------------------------------------------------------------------

@_register("filter_overhaul")
def build_filter_overhaul(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create broken/good filters and matching emails for filter-overhaul task.

    Pre-seeds 3 existing filters (one broken, two good) and 6 emails that
    match the patterns the agent needs to create new filters for.

    Params
    ------
    (none -- all names / addresses are generated internally)
    """
    correct_domain = "billing-services.com"
    wrong_domain = "wrong-billing.com"
    billing_label = "Billing"
    keyword = "Security Advisory"
    keyword_label = "Security"
    archive_domain = "marketing-blasts.com"
    forward_sender_name = ctx.fake.name()
    forward_sender = ctx.email_for_name(forward_sender_name, domain="silverpeak.co")
    forward_to = "chief-of-staff@thornton.com"

    # Pre-seed 3 existing filters
    broken_filter = FilterRule(
        id=ctx.next_id("filter"),
        name="Billing auto-archive",
        query=f"from:@{wrong_domain}",
        from_addresses=[f"*@{wrong_domain}"],
        archive=True,
        add_labels=["Billing"],
    )
    good_filter_a = FilterRule(
        id=ctx.next_id("filter"),
        name="Newsletter archive",
        query="from:@newsletters.substack.com",
        from_addresses=["*@newsletters.substack.com"],
        archive=True,
        mark_read=True,
    )
    good_filter_b = FilterRule(
        id=ctx.next_id("filter"),
        name="Team notifications star",
        query="from:@notify.thornton.com",
        from_addresses=["*@notify.thornton.com"],
        star=True,
    )
    ctx.base["filters"].extend([broken_filter, good_filter_a, good_filter_b])

    # Emails in inbox matching the patterns the new filters should catch
    ctx.base["emails"].extend([
        # Billing email from the correct domain
        ctx.email(
            from_name="Billing Services",
            from_addr=f"invoices@{correct_domain}",
            subject="March invoice batch ready for review",
            body=ctx.format_email_body(
                "The March invoice batch is ready. Please review and approve before end of week.",
                signoff_name="Billing Services",
            ),
            timestamp=ctx.now - timedelta(days=1, hours=3),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
        ),
        # Another billing email from correct domain
        ctx.email(
            from_name="Billing Services",
            from_addr=f"statements@{correct_domain}",
            subject="Q1 billing statement",
            body=ctx.format_email_body(
                "Your Q1 billing statement is attached for your records.",
                signoff_name="Billing Services",
            ),
            timestamp=ctx.now - timedelta(days=3, hours=2),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
        ),
        # Security advisory email
        ctx.email(
            from_name="Security Team",
            from_addr="security@infosec.thornton.com",
            subject=f"{keyword}: Critical vulnerability in authentication module",
            body=ctx.format_email_body(
                "A critical vulnerability has been identified in the authentication module. "
                "Please review the attached advisory and apply patches within 48 hours.",
                signoff_name="Security Team",
            ),
            timestamp=ctx.now - timedelta(hours=8),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        ),
        # Marketing blast emails
        ctx.email(
            from_name="Marketing Automation",
            from_addr=f"campaigns@{archive_domain}",
            subject="Spring campaign results — weekly digest",
            body=ctx.format_email_body(
                "Here is the weekly digest of spring campaign performance metrics.",
                signoff_name="Marketing Automation",
            ),
            timestamp=ctx.now - timedelta(days=1, hours=7),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "promotions"],
        ),
        ctx.email(
            from_name="Marketing Automation",
            from_addr=f"updates@{archive_domain}",
            subject="New lead scoring model deployed",
            body=ctx.format_email_body(
                "The updated lead scoring model is now live in the CRM dashboard.",
                signoff_name="Marketing Automation",
            ),
            timestamp=ctx.now - timedelta(days=2, hours=5),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "promotions"],
        ),
        # Email from the executive to forward
        ctx.email(
            from_name=forward_sender_name,
            from_addr=forward_sender,
            subject="Board prep materials — confidential",
            body=ctx.format_email_body(
                "Sharing the board prep materials ahead of next week's meeting. Please keep these "
                "confidential and route through my chief of staff.",
                signoff_name=ctx.first_name(forward_sender_name),
            ),
            timestamp=ctx.now - timedelta(hours=4),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        ),
    ])

    ctx.ensure_contact(forward_sender_name, forward_sender, is_vip=True)

    return {
        "broken_filter_id": broken_filter.id,
        "correct_domain": correct_domain,
        "wrong_domain": wrong_domain,
        "billing_label": billing_label,
        "keyword": keyword,
        "keyword_label": keyword_label,
        "archive_domain": archive_domain,
        "forward_sender": forward_sender,
        "forward_to": forward_to,
        "good_filter_a_id": good_filter_a.id,
        "good_filter_b_id": good_filter_b.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Budget Reconciliation (Task 11)
# ---------------------------------------------------------------------------

@_register("budget_reconciliation")
def build_budget_reconciliation(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create department budget emails and a summary with two wrong numbers.

    Params
    ------
    (none -- all names / addresses are generated internally)
    """
    dept_a_name = ctx.fake.name()
    dept_b_name = ctx.fake.name()
    dept_c_name = ctx.fake.name()
    summary_author_name = ctx.fake.name()

    dept_a_email = ctx.email_for_name(dept_a_name, domain="eng.thornton.com")
    dept_b_email = ctx.email_for_name(dept_b_name, domain="mktg.thornton.com")
    dept_c_email = ctx.email_for_name(dept_c_name, domain="operations.thornton.com")
    summary_author_email = ctx.email_for_name(summary_author_name, domain="fin.thornton.com")

    cfo_email = "cfo@silverpeak.co"
    board_cc = [cfo_email, "board-a@silverpeak.co", "board-b@silverpeak.co"]

    dept_a_dept = "Engineering"
    dept_b_dept = "Marketing"
    dept_c_dept = "Operations"

    # Department emails with correct figures
    dept_a_email_obj = ctx.email(
        from_name=dept_a_name,
        from_addr=dept_a_email,
        subject=f"Q1 {dept_a_dept} budget figures",
        body=ctx.format_email_body(
            f"Here are the final Q1 numbers for {dept_a_dept}.",
            f"Total spend: $142,500. This covers salaries, tooling, and infrastructure.",
            signoff_name=ctx.first_name(dept_a_name),
        ),
        timestamp=ctx.now - timedelta(days=3, hours=4),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )
    dept_b_email_obj = ctx.email(
        from_name=dept_b_name,
        from_addr=dept_b_email,
        subject=f"Q1 {dept_b_dept} budget figures",
        body=ctx.format_email_body(
            f"Attached are the Q1 {dept_b_dept} figures as requested.",
            f"Our total for the quarter: $89,000. Includes campaign spend, events, and agency fees.",
            signoff_name=ctx.first_name(dept_b_name),
        ),
        timestamp=ctx.now - timedelta(days=3, hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )
    dept_c_email_obj = ctx.email(
        from_name=dept_c_name,
        from_addr=dept_c_email,
        subject=f"Q1 {dept_c_dept} budget figures",
        body=ctx.format_email_body(
            f"Q1 {dept_c_dept} numbers below.",
            f"Total: $215,750. Covers facilities, logistics, and vendor contracts.",
            signoff_name=ctx.first_name(dept_c_name),
        ),
        timestamp=ctx.now - timedelta(days=3, hours=1),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # Summary email with 2 wrong numbers (Reply All trap via CC)
    summary_email = ctx.email(
        from_name=summary_author_name,
        from_addr=summary_author_email,
        subject="Q1 Budget Summary — please verify",
        body=ctx.format_email_body(
            "I compiled the Q1 figures from all three departments. Please review:",
            (
                f"- {dept_a_dept}: $142,500\n"
                f"- {dept_b_dept}: $98,000\n"
                f"- {dept_c_dept}: $205,750"
            ),
            "Let me know if anything looks off before I send the final version to the board.",
            signoff_name=ctx.first_name(summary_author_name),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=6),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        cc=board_cc,
    )

    ctx.base["emails"].extend([
        dept_a_email_obj, dept_b_email_obj, dept_c_email_obj, summary_email,
    ])
    ctx.ensure_contact(dept_a_name, dept_a_email)
    ctx.ensure_contact(dept_b_name, dept_b_email)
    ctx.ensure_contact(dept_c_name, dept_c_email)
    ctx.ensure_contact(summary_author_name, summary_author_email)

    dept_ids = [dept_a_email_obj.id, dept_b_email_obj.id, dept_c_email_obj.id]
    all_budget_ids = dept_ids + [summary_email.id]

    return {
        "dept_a_name": dept_a_name,
        "dept_a_dept": dept_a_dept,
        "dept_b_name": dept_b_name,
        "dept_b_dept": dept_b_dept,
        "dept_c_name": dept_c_name,
        "dept_c_dept": dept_c_dept,
        "summary_author_name": summary_author_name,
        "summary_author_email": summary_author_email,
        "summary_id": summary_email.id,
        "dept_ids": dept_ids,
        "all_budget_ids": all_budget_ids,
        "correct_value_1": "$89,000",
        "correct_value_2": "$215,750",
        "wrong_values": ["$98,000", "$205,750"],
    }


# ---------------------------------------------------------------------------
# Gmail: Inbox Triage Protocol
# ---------------------------------------------------------------------------

@_register("inbox_triage_protocol")
def build_inbox_triage_protocol(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create the inbox triage protocol puzzle with invoice, promo, security,
    travel, and onboarding emails plus decoys for each category."""

    invoice_sender_name = ctx.fake.name()
    invoice_sender_email = ctx.email_for_name(invoice_sender_name, domain="billing.thornton.com")
    invoice_decoy_sender_name = ctx.fake.name()
    invoice_decoy_sender_email = ctx.email_for_name(invoice_decoy_sender_name, domain="billing.thornton.com")
    promo_sender_name = ctx.fake.company()
    promo_sender_email = ctx.email_for_name(promo_sender_name, domain="promooffers.com")
    security_sender_name = "Security Operations"
    security_sender_email = "alerts@secops.thornton.com"
    travel_sender_name = ctx.fake.name()
    travel_sender_email = ctx.email_for_name(travel_sender_name, domain="traveldesk.thornton.com")
    travel_decoy_sender_name = ctx.fake.name()
    travel_decoy_sender_email = ctx.email_for_name(travel_decoy_sender_name, domain="traveldesk.thornton.com")
    onboarding_sender_name = "People Operations"
    onboarding_sender_email = "onboarding@people.thornton.com"
    escalation_email = "sec-escalations@thornton.com"
    confirmation_phrase = "I have completed the onboarding checklist."

    invoice_email = ctx.email(
        from_name=invoice_sender_name,
        from_addr=invoice_sender_email,
        subject="Invoice 8842 needs approval",
        body=ctx.format_email_body(
            (
                "Attached is invoice 8842 covering the Denver freight overage, badge reprints, "
                "and on-site support from last week's event."
            ),
            (
                "Accounts payable asked whether you can review it before Friday so the vendor stays "
                "on normal payment terms."
            ),
            signoff_name=ctx.first_name(invoice_sender_name),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=4),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        attachments=[ctx.attachment("invoice-8842.pdf", "application/pdf", "pdf")],
    )
    promo_email = ctx.email(
        from_name=promo_sender_name,
        from_addr=promo_sender_email,
        subject="Weekend bundle discount ends tonight",
        body=ctx.format_email_body(
            (
                "This weekend only: bundle pricing on office seating, monitor arms, and conference "
                "room accessories."
            ),
            (
                "The storefront discount expires at midnight and includes free shipping on any order "
                "above the corporate minimum."
            ),
            signoff_name=promo_sender_name,
        ),
        timestamp=ctx.now - timedelta(days=1, hours=3),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "promotions"],
    )
    security_email = ctx.email(
        from_name=security_sender_name,
        from_addr=security_sender_email,
        subject="Security alert: suspicious OAuth token",
        body=ctx.format_email_body(
            (
                "A new OAuth token labeled 'Calendar Bridge' was issued from an unrecognized macOS "
                "device at 03:14 UTC."
            ),
            (
                "We have not revoked it yet because the workflow owner may still confirm it as valid, "
                "but the activity should go through the normal incident path if it is unexpected."
            ),
            signoff_name="Security Operations",
        ),
        timestamp=ctx.now - timedelta(hours=11),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "important"],
    )
    travel_email = ctx.email(
        from_name=travel_sender_name,
        from_addr=travel_sender_email,
        subject="Travel request for Denver leadership offsite",
        body=ctx.format_email_body(
            (
                "Can you confirm the hotel block and flight cap for next week's Denver leadership "
                "offsite?"
            ),
            (
                "The venue needs the rooming list on Monday, and finance asked whether ground "
                "transportation should stay under the same trip code."
            ),
            signoff_name=ctx.first_name(travel_sender_name),
        ),
        timestamp=ctx.now - timedelta(days=6, hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )
    # CC HR team on onboarding email to create Reply All trap (IR-4)
    hr_cc_email = "hr-team@people.thornton.com"
    onboarding_email = ctx.email(
        from_name=onboarding_sender_name,
        from_addr=onboarding_sender_email,
        subject="Complete your onboarding checklist",
        body=ctx.format_email_body(
            (
                "Reply once your laptop setup, MFA enrollment, payroll forms, and badge pickup are "
                "all complete so I can close the onboarding ticket."
            ),
            "If anything is still blocked, include the missing item in your response.",
            signoff_name="People Operations",
        ),
        timestamp=ctx.now - timedelta(days=7, hours=1),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "important"],
        cc=[hr_cc_email],
    )
    invoice_decoy_email = ctx.email(
        from_name=invoice_decoy_sender_name,
        from_addr=invoice_decoy_sender_email,
        subject="Invoice 8842 cover sheet and remittance note",
        body=ctx.format_email_body(
            (
                "Sharing the remittance note and cover sheet for invoice 8842 before we close the "
                "weekly vendor packet."
            ),
            (
                "No approval needed on this one yet. I mainly wanted you to have the support file "
                "in case finance asks for the remittance address."
            ),
            signoff_name=ctx.first_name(invoice_decoy_sender_name),
        ),
        timestamp=ctx.now - timedelta(days=2, hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        attachments=[ctx.attachment("invoice-8842-cover.pdf", "application/pdf", "pdf")],
    )
    security_followup_email = ctx.email(
        from_name=security_sender_name,
        from_addr=security_sender_email,
        subject="Security alert follow-up: Calendar Bridge token already revoked",
        body=ctx.format_email_body(
            (
                "Following up on the earlier Calendar Bridge token alert. The token has already been "
                "revoked on our side and the issuing device was removed from the allow list."
            ),
            "No additional incident routing is needed unless the device reappears in the audit log.",
            signoff_name="Security Operations",
        ),
        timestamp=ctx.now - timedelta(hours=5),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "updates"],
        is_read=True,
    )
    travel_decoy_email = ctx.email(
        from_name=travel_decoy_sender_name,
        from_addr=travel_decoy_sender_email,
        subject="Travel request for Denver leadership dinner",
        body=ctx.format_email_body(
            (
                "Can you confirm whether the Denver dinner guest list should use the same travel code "
                "as the leadership offsite?"
            ),
            "The restaurant needs the final count before I send the transportation confirmation.",
            signoff_name=ctx.first_name(travel_decoy_sender_name),
        ),
        timestamp=ctx.now - timedelta(days=3, hours=1),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        invoice_email, promo_email, security_email, travel_email,
        onboarding_email, invoice_decoy_email, security_followup_email,
        travel_decoy_email,
    ])
    ctx.ensure_contact(invoice_sender_name, invoice_sender_email)
    ctx.ensure_contact(travel_sender_name, travel_sender_email)
    ctx.ensure_contact(onboarding_sender_name, onboarding_sender_email)
    ctx.ensure_contact(security_sender_name, security_sender_email, is_vip=True)

    return {
        "escalation_email": escalation_email,
        "confirmation_phrase": confirmation_phrase,
        "invoice_email_id": invoice_email.id,
        "promo_email_id": promo_email.id,
        "security_email_id": security_email.id,
        "travel_email_id": travel_email.id,
        "onboarding_email_id": onboarding_email.id,
        "invoice_decoy_email_id": invoice_decoy_email.id,
        "security_followup_email_id": security_followup_email.id,
        "travel_decoy_email_id": travel_decoy_email.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Filter Architect
# ---------------------------------------------------------------------------

@_register("filter_architect")
def build_filter_architect(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create emails and a pre-existing filter for the filter architect task."""

    billing_domain = "billing-vendors.com"
    billing_label = "Billing Vendors"
    payroll_keyword = "Payroll Exception"
    payroll_label = "Payroll"
    exec_sender_name = ctx.fake.name()
    exec_sender_email = ctx.email_for_name(exec_sender_name, domain="boardoffice.com")
    exec_forward_email = "chief-of-staff@thornton.com"

    # Pre-existing filter that must not be deleted (SW-3.1)
    existing_filter = FilterRule(
        id=ctx.next_id("filter"),
        name="Newsletter archive",
        query="from:@newsletters.substack.com",
        from_addresses=["*@newsletters.substack.com"],
        archive=True,
        mark_read=True,
    )
    ctx.base["filters"].append(existing_filter)

    ctx.base["emails"].extend([
        # Billing email in Updates tab (IR-1)
        ctx.email(
            from_name="Northwind Billing Operations",
            from_addr=f"accounts@{billing_domain}",
            subject="Invoice packet for March freight reconciliation",
            body=ctx.format_email_body(
                (
                    "Sending the March freight reconciliation packet for the warehouse transfer "
                    "and rush shipping charges."
                ),
                (
                    "The supporting worksheet is attached on our side; I can resend line-item "
                    "detail if you need it."
                ),
                signoff_name="Northwind Billing",
            ),
            timestamp=ctx.now - timedelta(days=2),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
        ),
        ctx.email(
            from_name="Payroll Systems",
            from_addr="payroll@operations.thornton.com",
            subject=f"{payroll_keyword} for March cycle",
            body=ctx.format_email_body(
                (
                    "The March payroll run flagged a withholding mismatch that still needs manual "
                    "review before payroll closes."
                ),
                (
                    "I left the exception open until someone confirms whether the state code should "
                    "be corrected or overridden."
                ),
                signoff_name="Payroll Systems",
            ),
            timestamp=ctx.now - timedelta(days=1, hours=5),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "important"],
        ),
        ctx.email(
            from_name=exec_sender_name,
            from_addr=exec_sender_email,
            subject="Board packet follow-up",
            body=ctx.format_email_body(
                (
                    "Sending a marked-up board packet draft with a few notes on sequencing for the "
                    "Monday prep."
                ),
                (
                    "I may continue sending revisions from this address over the next week, so keep "
                    "an eye on anything related to the prep memo."
                ),
                signoff_name=ctx.first_name(exec_sender_name),
            ),
            timestamp=ctx.now - timedelta(hours=9),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        ),
    ])
    ctx.ensure_contact(exec_sender_name, exec_sender_email, is_vip=True)

    return {
        "billing_domain": billing_domain,
        "billing_label": billing_label,
        "payroll_keyword": payroll_keyword,
        "payroll_label": payroll_label,
        "exec_sender_name": exec_sender_name,
        "exec_sender_email": exec_sender_email,
        "exec_forward_email": exec_forward_email,
        "existing_filter_id": existing_filter.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Contact Cleanup
# ---------------------------------------------------------------------------

@_register("contact_cleanup")
def build_contact_cleanup(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create stale, active, near-threshold contacts and missing-contact emails."""

    stale_contact_a = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="pinevalley.co"),
        last_contacted_at=ctx.now - timedelta(days=45),
    )
    stale_contact_b = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="millbrook.co"),
        last_contacted_at=ctx.now - timedelta(days=61),
    )
    keep_contact = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="cedarpoint.co"),
        last_contacted_at=ctx.now - timedelta(days=5),
    )
    missing_contact_name = ctx.fake.name()
    missing_contact_legacy_email = ctx.email_for_name(missing_contact_name, domain="herald.co")
    missing_contact_email = ctx.email_for_name(missing_contact_name, domain="recentmailer.com")
    missing_contact_subject = "March planning follow-up"
    contact_note = "Added after March planning thread."

    # Near-threshold decoys: 20-29 days, should NOT be deleted (SW-2.2)
    near_threshold_contact = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="nearthreshold.io"),
        last_contacted_at=ctx.now - timedelta(days=25),
    )
    near_threshold_contact_b = ctx.contact(
        name=ctx.fake.name(),
        email=ctx.fake.email(domain="greyzone.co"),
        last_contacted_at=ctx.now - timedelta(days=28),
    )
    ctx.base["contacts"].extend([
        stale_contact_a, stale_contact_b, keep_contact,
        near_threshold_contact, near_threshold_contact_b,
    ])
    ctx.base["emails"].extend([
        ctx.email(
            from_name=missing_contact_name,
            from_addr=missing_contact_legacy_email,
            subject="Alias check before March planning",
            body=ctx.format_email_body(
                (
                    "This older alias is still forwarding for now, but I am moving contract and "
                    "planning notes over to the newer mailbox this week."
                ),
                "You can ignore this one once the March thread is wrapped.",
                signoff_name=ctx.first_name(missing_contact_name),
            ),
            timestamp=ctx.now - timedelta(days=6, hours=2),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
            is_read=True,
        ),
        ctx.email(
            from_name=missing_contact_name,
            from_addr=missing_contact_email,
            subject=missing_contact_subject,
            body=ctx.format_email_body(
                (
                    "Good talking during the March planning thread. Could you add this address to "
                    "the vendor planning loop going forward?"
                ),
                (
                    "I usually send contract redlines from here, so it would help to have it saved "
                    "instead of relying on the older alias."
                ),
                signoff_name=ctx.first_name(missing_contact_name),
            ),
            timestamp=ctx.now - timedelta(days=1, hours=4),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        ),
        ctx.email(
            from_name=keep_contact.name,
            from_addr=keep_contact.email,
            subject="Weekly checkpoint",
            body=ctx.format_email_body(
                (
                    "Sending the weekly checkpoint and revised venue shortlist from today's ops "
                    "review."
                ),
                (
                    "The timeline still looks fine on my side, but I wanted to keep the thread warm "
                    "before next week's decision meeting."
                ),
                signoff_name=ctx.first_name(keep_contact.name),
            ),
            timestamp=ctx.now - timedelta(days=3),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        ),
    ])

    return {
        "stale_contact_id_a": stale_contact_a.id,
        "stale_contact_id_b": stale_contact_b.id,
        "missing_contact_name": missing_contact_name,
        "missing_contact_email": missing_contact_email,
        "missing_contact_subject": missing_contact_subject,
        "contact_note": contact_note,
        "keep_contact_name": keep_contact.name,
        "keep_contact_id": keep_contact.id,
        "near_threshold_contact_id": near_threshold_contact.id,
        "near_threshold_contact_b_id": near_threshold_contact_b.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Priority Escalation
# ---------------------------------------------------------------------------

@_register("priority_escalation")
def build_priority_escalation(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create VIP contacts/emails with decoys for the priority escalation task."""

    vip_contacts = [
        ctx.contact(is_vip=True, company="Executive Office"),
        ctx.contact(is_vip=True, company="Executive Office"),
        ctx.contact(is_vip=True, company="Executive Office"),
    ]
    future_vip_name = ctx.fake.name()
    future_vip_email = ctx.email_for_name(future_vip_name, domain="vipfuture.com")
    status_phrase = "Status update: I am actively on it."
    vip_email_ids: list[str] = []
    urgency_topics = [
        "vendor recovery timeline",
        "board deck edits",
        "staffing backfill status",
        "budget reforecast",
        "customer launch blocker",
    ]

    # Target VIP emails pushed further back for pagination (SW-5.2)
    for offset, contact in enumerate(vip_contacts):
        ctx.base["contacts"].append(contact)
        topic = urgency_topics[offset]
        email = ctx.email(
            from_name=contact.name,
            from_addr=contact.email,
            subject=f"Need an update on the {topic}",
            body=ctx.format_email_body(
                (
                    f"Can you send me a short status note on the {topic}? I want to know whether "
                    "anything is blocked before close of business."
                ),
                (
                    "A concise reply is fine. I mainly need to know whether the work is moving and "
                    "where the next dependency sits."
                ),
                signoff_name=ctx.first_name(contact.name),
            ),
            timestamp=ctx.now - timedelta(days=12 - offset, hours=offset),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "VIP"],
            is_read=False,
        )
        vip_email_ids.append(email.id)
        ctx.base["emails"].append(email)

    # NEWER unread VIP email from first VIP contact — agent must find OLDEST (SW-5.1)
    ctx.base["emails"].append(
        ctx.email(
            from_name=vip_contacts[0].name,
            from_addr=vip_contacts[0].email,
            subject="Quick follow-up on the vendor recovery timeline",
            body=ctx.format_email_body(
                "One more question on the vendor recovery timeline before tomorrow's exec sync.",
                "If the risk posture changed after the last draft, I need to know whether procurement has already been looped in.",
                signoff_name=ctx.first_name(vip_contacts[0].name),
            ),
            timestamp=ctx.now - timedelta(days=2, hours=2),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "VIP"],
            is_read=False,
        )
    )
    # Read VIP email — should NOT be starred or replied to
    ctx.base["emails"].append(
        ctx.email(
            from_name=vip_contacts[0].name,
            from_addr=vip_contacts[0].email,
            subject="Circling back on last week's board prep",
            body=ctx.format_email_body(
                "Thanks for the earlier notes. The revised draft looks cleaner now.",
                "No action needed from you on this one unless the numbers move again.",
                signoff_name=ctx.first_name(vip_contacts[0].name),
            ),
            timestamp=ctx.now - timedelta(days=1, hours=6),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "VIP"],
            is_read=True,
        )
    )
    # Name confuser: similar name to first VIP, NOT a VIP, has unread email (SW-5.3)
    confuser_first = ctx.first_name(vip_contacts[0].name)
    confuser_name = f"{confuser_first} {ctx.fake.name().split()[-1]}"
    confuser_email = ctx.email_for_name(confuser_name, domain="confuser.io")
    confuser_contact = ctx.contact(
        name=confuser_name,
        email=confuser_email,
        is_vip=False,
        company="External Vendor",
    )
    ctx.base["contacts"].append(confuser_contact)
    ctx.base["emails"].append(
        ctx.email(
            from_name=confuser_name,
            from_addr=confuser_email,
            subject="Update on the vendor timeline",
            body=ctx.format_email_body(
                "Wanted to share the latest vendor timeline revision before the review.",
                "Let me know if anything looks off on your side.",
                signoff_name=confuser_first,
            ),
            timestamp=ctx.now - timedelta(days=3),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
            is_read=False,
        )
    )
    # Future VIP email
    ctx.base["emails"].append(
        ctx.email(
            from_name=future_vip_name,
            from_addr=future_vip_email,
            subject="Future priority escalation",
            body=ctx.format_email_body(
                (
                    "I will be stepping into the executive sponsor role next quarter and will likely "
                    "send a few requests directly once the transition starts."
                ),
                "No action needed yet. I just wanted to introduce the address early.",
                signoff_name=ctx.first_name(future_vip_name),
            ),
            timestamp=ctx.now - timedelta(days=1, hours=1),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        )
    )

    return {
        "vip_count": len(vip_email_ids),
        "vip_email_ids": vip_email_ids,
        "status_phrase": status_phrase,
        "future_vip_email": future_vip_email,
    }


# ---------------------------------------------------------------------------
# Gmail: Morning Triage Extended
# ---------------------------------------------------------------------------

@_register("morning_triage_extended")
def build_morning_triage_extended(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create morning triage emails: urgents, FYI decoy, promo, FYI,
    forward target, reply-all trap, and confirmation request."""

    # --- Urgent A: end-of-day deadline ---
    urgent_a_name = ctx.fake.name()
    urgent_a_email = ctx.email_for_name(urgent_a_name, domain="vertexlab.io")
    urgent_a = ctx.email(
        from_name=urgent_a_name,
        from_addr=urgent_a_email,
        subject="Contract review before close of business",
        body=ctx.format_email_body(
            "I need this reviewed before end of day. The vendor is expecting our sign-back by tomorrow morning.",
            "Please prioritize this over the other items on your plate today.",
            signoff_name=ctx.first_name(urgent_a_name),
        ),
        timestamp=ctx.now - timedelta(hours=3),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # --- Urgent B: needs sign-off ---
    urgent_b_name = ctx.fake.name()
    urgent_b_email = ctx.email_for_name(urgent_b_name, domain="procurement.co")
    urgent_b = ctx.email(
        from_name=urgent_b_name,
        from_addr=urgent_b_email,
        subject="Procurement approval — needs your sign-off",
        body=ctx.format_email_body(
            "The procurement order is ready to go but needs your sign-off before we proceed.",
            "Finance will not release the PO without your confirmation on file.",
            signoff_name=ctx.first_name(urgent_b_name),
        ),
        timestamp=ctx.now - timedelta(hours=5),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # --- FYI decoy: looks urgent but is FYI only ---
    fyi_decoy_name = ctx.fake.name()
    fyi_decoy_email = ctx.email_for_name(fyi_decoy_name, domain="vertexlab.io")
    fyi_decoy = ctx.email(
        from_name=fyi_decoy_name,
        from_addr=fyi_decoy_email,
        subject="Urgent: Updated project timeline",
        body=ctx.format_email_body(
            "FYI only — no action needed from you. The project timeline was updated yesterday and I wanted you to have the latest version.",
            "Everything is on track and the team is handling the remaining items.",
            signoff_name=ctx.first_name(fyi_decoy_name),
        ),
        timestamp=ctx.now - timedelta(hours=4),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # --- Promo: newsletter in Promotions tab ---
    promo_name = ctx.fake.company()
    promo_email_addr = ctx.email_for_name(promo_name, domain="newsletters.substack.com")
    promo = ctx.email(
        from_name=promo_name,
        from_addr=promo_email_addr,
        subject="Weekly industry digest — top stories this week",
        body=ctx.format_email_body(
            "This week's top stories in operations and supply chain management.",
            "Unsubscribe at any time by clicking the link at the bottom of this email.",
            signoff_name=promo_name,
        ),
        timestamp=ctx.now - timedelta(hours=6),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "promotions"],
    )

    # --- FYI: general update in Primary ---
    fyi_name = ctx.fake.name()
    fyi_email_addr = ctx.email_for_name(fyi_name, domain="teamupdates.com")
    fyi = ctx.email(
        from_name=fyi_name,
        from_addr=fyi_email_addr,
        subject="Facilities update — no action needed",
        body=ctx.format_email_body(
            "Quick update: the office HVAC maintenance has been completed ahead of schedule.",
            "No action needed on your end. Just keeping you in the loop.",
            signoff_name=ctx.first_name(fyi_name),
        ),
        timestamp=ctx.now - timedelta(hours=7),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # --- Forward target: loop in a colleague ---
    forward_sender_name = ctx.fake.name()
    forward_sender_email = ctx.email_for_name(forward_sender_name, domain="bridgeway.co")
    colleague_name = ctx.fake.name()
    colleague_email = ctx.email_for_name(colleague_name, domain="eng.thornton.com")
    forward_target = ctx.email(
        from_name=forward_sender_name,
        from_addr=forward_sender_email,
        subject="Integration spec needs engineering input",
        body=ctx.format_email_body(
            f"Could you please loop in {colleague_name} ({colleague_email}) from engineering? They worked on the original integration spec and would know the current constraints.",
            "I think we can finalize the API contract once they weigh in on the rate limits.",
            signoff_name=ctx.first_name(forward_sender_name),
        ),
        timestamp=ctx.now - timedelta(hours=8),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # --- Reply A: project update with CC (Reply All trap) ---
    reply_sender_name = ctx.fake.name()
    reply_sender_email = ctx.email_for_name(reply_sender_name, domain="pm.thornton.com")
    cc_a1 = ctx.email_for_name(ctx.fake.name(), domain="pm.thornton.com")
    cc_a2 = ctx.email_for_name(ctx.fake.name(), domain="pm.thornton.com")
    reply_phrase_a = "project update"
    reply_a = ctx.email(
        from_name=reply_sender_name,
        from_addr=reply_sender_email,
        subject=f"{ctx.initiative_name()} — project update",
        body=ctx.format_email_body(
            "Here is the latest project update. We are on track for the milestone next week.",
            "Let me know if any of the deliverables need to be reprioritized.",
            signoff_name=ctx.first_name(reply_sender_name),
        ),
        timestamp=ctx.now - timedelta(hours=9),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
        cc=[cc_a1, cc_a2],
    )

    # --- Reply B: confirmation request ---
    reply_b_sender_name = ctx.fake.name()
    reply_b_sender_email = ctx.email_for_name(reply_b_sender_name, domain="logistics.co")
    reply_b = ctx.email(
        from_name=reply_b_sender_name,
        from_addr=reply_b_sender_email,
        subject="Shipment confirmation needed",
        body=ctx.format_email_body(
            "Could you confirm receipt of the Q1 shipment manifest?",
            "The warehouse team needs your acknowledgment before they release the next batch.",
            signoff_name=ctx.first_name(reply_b_sender_name),
        ),
        timestamp=ctx.now - timedelta(hours=10),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    ctx.base["emails"].extend([
        urgent_a, urgent_b, fyi_decoy, promo, fyi,
        forward_target, reply_a, reply_b,
    ])
    ctx.ensure_contact(urgent_a_name, urgent_a_email)
    ctx.ensure_contact(urgent_b_name, urgent_b_email)
    ctx.ensure_contact(forward_sender_name, forward_sender_email)
    ctx.ensure_contact(reply_sender_name, reply_sender_email)
    ctx.ensure_contact(reply_b_sender_name, reply_b_sender_email)
    ctx.ensure_contact(colleague_name, colleague_email)

    return {
        "urgent_a_id": urgent_a.id,
        "urgent_b_id": urgent_b.id,
        "fyi_decoy_id": fyi_decoy.id,
        "promo_id": promo.id,
        "fyi_id": fyi.id,
        "forward_id": forward_target.id,
        "forward_to_email": colleague_email,
        "reply_a_id": reply_a.id,
        "reply_sender_name": reply_sender_name,
        "reply_phrase_a": reply_phrase_a,
        "reply_b_id": reply_b.id,
        "reply_b_sender_name": reply_b_sender_name,
    }


# ---------------------------------------------------------------------------
# Gmail: Meeting Negotiation
# ---------------------------------------------------------------------------

@_register("meeting_negotiation")
def build_meeting_negotiation(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create 5 attendee availability emails plus a venue email for meeting scheduling.

    Picks one time slot that all attendees share, generates availability
    emails for each, and adds a venue coordinator message in the Updates tab.
    """
    meeting_name = ctx.initiative_name()
    organizer_name = ctx.fake.name()
    organizer_email = ctx.email_for_name(organizer_name, domain="silverpeak.co")

    all_time_slots = [
        "Monday 9:00 AM", "Monday 2:00 PM",
        "Tuesday 10:00 AM", "Tuesday 3:00 PM",
        "Wednesday 11:00 AM", "Wednesday 1:00 PM",
        "Thursday 9:30 AM", "Thursday 2:30 PM",
        "Friday 10:00 AM", "Friday 4:00 PM",
    ]
    correct_time = ctx.rng.choice(all_time_slots)
    other_slots = [s for s in all_time_slots if s != correct_time]

    attendee_names: list[str] = []
    attendee_emails: list[str] = []
    domains = ["sales.thornton.com", "mktg.thornton.com", "fin.thornton.com", "ops.thornton.com", "product.thornton.com"]

    for i in range(5):
        name = ctx.fake.name()
        email = ctx.email_for_name(name, domain=domains[i])
        attendee_names.append(name)
        attendee_emails.append(email)

        # Each attendee has the correct_time plus 2-3 other random slots
        personal_others = ctx.rng.sample(other_slots, k=ctx.rng.randint(2, 3))
        available_slots = [correct_time] + personal_others
        ctx.rng.shuffle(available_slots)

        slot_lines = [f"{slot}" for slot in available_slots]
        ctx.base["emails"].append(
            ctx.email(
                from_name=name,
                from_addr=email,
                subject=f"Re: {meeting_name} — my availability",
                body=ctx.format_email_body(
                    f"Here are the times that work for me for the {meeting_name} meeting:",
                    ctx.bullet_lines(slot_lines),
                    "Let me know once a time is confirmed.",
                    signoff_name=ctx.first_name(name),
                ),
                timestamp=ctx.now - timedelta(days=2, hours=i * 2),
                thread_id=ctx.next_id("thread"),
                labels=["inbox"],
            )
        )
        ctx.ensure_contact(name, email)

    # Venue email — in Updates tab
    room_name = ctx.rng.choice(["Cascade Room", "Summit Hall", "Harbor Suite", "Cedar Boardroom"])
    venue_coordinator_name = ctx.fake.name()
    venue_coordinator_email = ctx.email_for_name(venue_coordinator_name, domain="facilities.thornton.com")

    # Room available at the correct_time plus one other slot
    venue_other_slot = ctx.rng.choice(other_slots)
    venue_availability = [correct_time, venue_other_slot]
    ctx.rng.shuffle(venue_availability)

    ctx.base["emails"].append(
        ctx.email(
            from_name=venue_coordinator_name,
            from_addr=venue_coordinator_email,
            subject=f"Room availability for {meeting_name}",
            body=ctx.format_email_body(
                f"The {room_name} is available at the following times next week:",
                ctx.bullet_lines(venue_availability),
                "Please confirm which slot you would like to reserve and I will block the calendar.",
                signoff_name=ctx.first_name(venue_coordinator_name),
            ),
            timestamp=ctx.now - timedelta(days=1, hours=6),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
        )
    )
    ctx.ensure_contact(venue_coordinator_name, venue_coordinator_email)
    ctx.ensure_contact(organizer_name, organizer_email)

    return {
        "meeting_name": meeting_name,
        "organizer_email": organizer_email,
        "attendee_emails": attendee_emails,
        "correct_time": correct_time,
        "room_name": room_name,
    }


# ---------------------------------------------------------------------------
# Gmail: Incident Escalation
# ---------------------------------------------------------------------------

@_register("incident_escalation")
def build_incident_escalation(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create an incident alert thread, resolved follow-up, and manager status-check email.

    Generates a 3-message alert thread (system alert, engineer with error code,
    team member naming on-call), a resolved alert in a separate thread, and a
    manager email asking for status with leadership CC'd.
    """
    alert_system_name = "System Alerts"
    alert_system_email = "alerts@monitoring.thornton.com"
    error_code = "ERR-5021"
    oncall_name = ctx.fake.name()
    oncall_email = ctx.email_for_name(oncall_name, domain="eng.thornton.com")
    status_phrase = "I am actively triaging the incident."

    # Alert thread — 3 messages in same thread
    alert_thread_id = ctx.next_id("thread")
    alert_subject = "CRITICAL: Service degradation on payment gateway"

    # Message 1: initial alert (oldest)
    alert_msg_1 = ctx.email(
        from_name=alert_system_name,
        from_addr=alert_system_email,
        subject=alert_subject,
        body=ctx.format_email_body(
            "Automated alert: Payment gateway latency has exceeded 5000ms threshold.",
            "Multiple transaction failures detected across regions US-East and EU-West. Immediate investigation required.",
            signoff_name="Monitoring System",
        ),
        timestamp=ctx.now - timedelta(hours=4),
        thread_id=alert_thread_id,
        labels=["inbox", "updates"],
    )

    # Message 2: engineer mentions error code
    engineer_name = ctx.fake.name()
    engineer_email = ctx.email_for_name(engineer_name, domain="eng.thornton.com")
    alert_msg_2 = ctx.email(
        from_name=engineer_name,
        from_addr=engineer_email,
        subject=f"Re: {alert_subject}",
        body=ctx.format_email_body(
            f"I checked the logs and the root cause appears to be error code {error_code} from the payment processor API.",
            "The circuit breaker tripped after the third consecutive timeout. We need to coordinate with the on-call engineer.",
            signoff_name=ctx.first_name(engineer_name),
        ),
        timestamp=ctx.now - timedelta(hours=3, minutes=30),
        thread_id=alert_thread_id,
        labels=["inbox", "updates"],
    )

    # Message 3: team member mentions on-call
    team_member_name = ctx.fake.name()
    team_member_email = ctx.email_for_name(team_member_name, domain="eng.thornton.com")
    alert_msg_3 = ctx.email(
        from_name=team_member_name,
        from_addr=team_member_email,
        subject=f"Re: {alert_subject}",
        body=ctx.format_email_body(
            f"The on-call engineer for this rotation is {oncall_name} at {oncall_email}.",
            "They should have pager access and can roll back the gateway config if needed.",
            signoff_name=ctx.first_name(team_member_name),
        ),
        timestamp=ctx.now - timedelta(hours=3),
        thread_id=alert_thread_id,
        labels=["inbox", "updates"],
    )

    # Resolved follow-up — different thread, should NOT be forwarded
    resolved_alert = ctx.email(
        from_name=alert_system_name,
        from_addr=alert_system_email,
        subject="RESOLVED: Service degradation on payment gateway",
        body=ctx.format_email_body(
            "The payment gateway latency has returned to normal levels.",
            "All regions are reporting healthy response times. No further action required.",
            signoff_name="Monitoring System",
        ),
        timestamp=ctx.now - timedelta(hours=1),
        thread_id=ctx.next_id("thread"),
        labels=["inbox", "updates"],
        is_read=True,
    )

    # Manager thread — asking about incident status, CC'd to leadership
    manager_name = ctx.fake.name()
    manager_email = ctx.email_for_name(manager_name, domain="summitview.co")
    leadership_cc = [
        ctx.email_for_name(ctx.fake.name(), domain="summitview.co"),
        ctx.email_for_name(ctx.fake.name(), domain="summitview.co"),
        ctx.email_for_name(ctx.fake.name(), domain="summitview.co"),
    ]
    manager_thread_id = ctx.next_id("thread")
    manager_msg = ctx.email(
        from_name=manager_name,
        from_addr=manager_email,
        subject="Payment gateway incident — status check",
        body=ctx.format_email_body(
            "I saw the alert about the payment gateway degradation. Can you confirm you are handling this?",
            "The executive team needs a status update as soon as possible.",
            signoff_name=ctx.first_name(manager_name),
        ),
        timestamp=ctx.now - timedelta(hours=2, minutes=30),
        thread_id=manager_thread_id,
        labels=["inbox"],
        cc=leadership_cc,
    )

    incident_ids = [alert_msg_1.id, alert_msg_2.id, alert_msg_3.id]

    ctx.base["emails"].extend([
        alert_msg_1, alert_msg_2, alert_msg_3,
        resolved_alert, manager_msg,
    ])
    ctx.ensure_contact(alert_system_name, alert_system_email)
    ctx.ensure_contact(engineer_name, engineer_email)
    ctx.ensure_contact(team_member_name, team_member_email)
    ctx.ensure_contact(oncall_name, oncall_email)
    ctx.ensure_contact(manager_name, manager_email)

    return {
        "alert_id": alert_msg_1.id,
        "oncall_email": oncall_email,
        "error_code": error_code,
        "manager_email_id": manager_msg.id,
        "manager_name": manager_name,
        "status_phrase": status_phrase,
        "incident_ids": incident_ids,
        "alert_system_email": alert_system_email,
        "resolved_alert_id": resolved_alert.id,
    }


# ---------------------------------------------------------------------------
# Gmail: Delegation Routing
# ---------------------------------------------------------------------------

@_register("delegation_routing")
def build_delegation_routing(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create 3 routing emails (budget, tech, complaint) plus a decoy.

    Each email explicitly names the person it should be forwarded to.
    The decoy looks similar but requires no action.
    """
    # CFO target
    cfo_name = ctx.fake.name()
    cfo_email = ctx.email_for_name(cfo_name, domain="fin.thornton.com")

    # CTO target
    cto_name = ctx.fake.name()
    cto_email = ctx.email_for_name(cto_name, domain="eng.thornton.com")

    # Support lead target
    support_lead_name = ctx.fake.name()
    support_lead_email = ctx.email_for_name(support_lead_name, domain="support.thornton.com")

    # Manager to BCC
    manager_name = ctx.fake.name()
    manager_email = ctx.email_for_name(manager_name, domain="summitview.co")

    # Budget question
    budget_sender_name = ctx.fake.name()
    budget_sender_email = ctx.email_for_name(budget_sender_name, domain="operations.thornton.com")
    budget_email = ctx.email(
        from_name=budget_sender_name,
        from_addr=budget_sender_email,
        subject="Q2 budget allocation question",
        body=ctx.format_email_body(
            f"We have a question about the Q2 budget allocation for the vendor program. I think the CFO should weigh in — {cfo_name} ({cfo_email}) would know whether the variance is within the approved range.",
            "Can you route this to the right person?",
            signoff_name=ctx.first_name(budget_sender_name),
        ),
        timestamp=ctx.now - timedelta(hours=4),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # Technical issue
    tech_sender_name = ctx.fake.name()
    tech_sender_email = ctx.email_for_name(tech_sender_name, domain="operations.thornton.com")
    tech_email = ctx.email(
        from_name=tech_sender_name,
        from_addr=tech_sender_email,
        subject="API rate limiting issue on staging",
        body=ctx.format_email_body(
            f"We are hitting rate limits on the staging API. The CTO's team needs to review this — please forward to {cto_name} ({cto_email}) so they can adjust the throttle configuration.",
            "This is blocking the QA cycle for the next release.",
            signoff_name=ctx.first_name(tech_sender_name),
        ),
        timestamp=ctx.now - timedelta(hours=5),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # Customer complaint
    complaint_sender_name = ctx.fake.name()
    complaint_sender_email = ctx.email_for_name(complaint_sender_name, domain="customers.co")
    complaint_email = ctx.email(
        from_name=complaint_sender_name,
        from_addr=complaint_sender_email,
        subject="Unresolved billing dispute — customer escalation",
        body=ctx.format_email_body(
            f"A customer has escalated a billing dispute that has been open for two weeks. This needs support lead review — please forward to {support_lead_name} ({support_lead_email}).",
            "The customer is threatening to cancel their contract if we do not resolve this by end of week.",
            signoff_name=ctx.first_name(complaint_sender_name),
        ),
        timestamp=ctx.now - timedelta(hours=2),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    # Decoy: looks like it needs forwarding but does not
    decoy_sender_name = ctx.fake.name()
    decoy_sender_email = ctx.email_for_name(decoy_sender_name, domain="crossteam.thornton.com")
    decoy_email = ctx.email(
        from_name=decoy_sender_name,
        from_addr=decoy_sender_email,
        subject="Cross-team alignment — Q2 planning",
        body=ctx.format_email_body(
            "Sharing the cross-team alignment doc for Q2 planning. No action needed — this is just for your awareness.",
            "The working group already signed off on the proposal last Friday.",
            signoff_name=ctx.first_name(decoy_sender_name),
        ),
        timestamp=ctx.now - timedelta(hours=6),
        thread_id=ctx.next_id("thread"),
        labels=["inbox"],
    )

    all_ids = [budget_email.id, tech_email.id, complaint_email.id]

    ctx.base["emails"].extend([budget_email, tech_email, complaint_email, decoy_email])
    ctx.ensure_contact(budget_sender_name, budget_sender_email)
    ctx.ensure_contact(tech_sender_name, tech_sender_email)
    ctx.ensure_contact(complaint_sender_name, complaint_sender_email)
    ctx.ensure_contact(cfo_name, cfo_email)
    ctx.ensure_contact(cto_name, cto_email)
    ctx.ensure_contact(support_lead_name, support_lead_email)
    ctx.ensure_contact(manager_name, manager_email)

    return {
        "budget_id": budget_email.id,
        "tech_id": tech_email.id,
        "complaint_id": complaint_email.id,
        "decoy_id": decoy_email.id,
        "cfo_email": cfo_email,
        "cto_email": cto_email,
        "support_lead_email": support_lead_email,
        "manager_email": manager_email,
        "all_ids": all_ids,
    }


# ---------------------------------------------------------------------------
# Gmail: Data Compilation
# ---------------------------------------------------------------------------

@_register("data_compilation")
def build_data_compilation(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create 3 department-head budget emails and 2 decoy emails with wrong numbers.

    Dept A is in Primary, Dept B in Updates, and Dept C is old (12+ days)
    to require scrolling. Decoys are draft/superseded figures.
    """
    exec_name = ctx.fake.name()
    exec_email = ctx.email_for_name(exec_name, domain="silverpeak.co")

    dept_names = ["Engineering", "Marketing", "Operations"]
    dept_domains = ["eng.thornton.com", "mktg.thornton.com", "operations.thornton.com"]
    numbers = ["$142,500", "$89,000", "$215,750"]
    wrong_numbers = ["$138,200", "$91,500"]

    dept_head_names: list[str] = []
    dept_emails: list[str] = []

    # Dept A: Primary tab
    dept_a_name = ctx.fake.name()
    dept_a_email = ctx.email_for_name(dept_a_name, domain=dept_domains[0])
    dept_head_names.append(dept_a_name)
    dept_emails.append(dept_a_email)
    ctx.base["emails"].append(
        ctx.email(
            from_name=dept_a_name,
            from_addr=dept_a_email,
            subject=f"Q1 figures — {dept_names[0]}",
            body=ctx.format_email_body(
                f"Here are the Q1 budget figures for {dept_names[0]}.",
                f"Total Q1 spend: {numbers[0]}",
                "Let me know if you need a breakdown by cost center.",
                signoff_name=ctx.first_name(dept_a_name),
            ),
            timestamp=ctx.now - timedelta(days=2, hours=3),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
        )
    )

    # Dept B: Updates tab
    dept_b_name = ctx.fake.name()
    dept_b_email = ctx.email_for_name(dept_b_name, domain=dept_domains[1])
    dept_head_names.append(dept_b_name)
    dept_emails.append(dept_b_email)
    ctx.base["emails"].append(
        ctx.email(
            from_name=dept_b_name,
            from_addr=dept_b_email,
            subject=f"Q1 figures — {dept_names[1]}",
            body=ctx.format_email_body(
                f"Attached are the Q1 budget numbers for {dept_names[1]}.",
                f"Our total Q1 spend came in at {numbers[1]}.",
                "Happy to walk through the details on our next call.",
                signoff_name=ctx.first_name(dept_b_name),
            ),
            timestamp=ctx.now - timedelta(days=3, hours=5),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
        )
    )

    # Dept C: old email (10+ days ago, will be on page 2+)
    dept_c_name = ctx.fake.name()
    dept_c_email = ctx.email_for_name(dept_c_name, domain=dept_domains[2])
    dept_head_names.append(dept_c_name)
    dept_emails.append(dept_c_email)
    ctx.base["emails"].append(
        ctx.email(
            from_name=dept_c_name,
            from_addr=dept_c_email,
            subject=f"Q1 figures — {dept_names[2]}",
            body=ctx.format_email_body(
                f"Sending the Q1 budget summary for {dept_names[2]}.",
                f"Final Q1 number: {numbers[2]}",
                "This includes the warehouse expansion costs that were approved in January.",
                signoff_name=ctx.first_name(dept_c_name),
            ),
            timestamp=ctx.now - timedelta(days=12, hours=2),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
            is_read=True,
        )
    )

    # Decoy emails with wrong numbers from similar departments
    decoy_a_name = ctx.fake.name()
    decoy_a_email = ctx.email_for_name(decoy_a_name, domain="eng.thornton.com")
    ctx.base["emails"].append(
        ctx.email(
            from_name=decoy_a_name,
            from_addr=decoy_a_email,
            subject="Q1 preliminary estimates — Engineering (DRAFT)",
            body=ctx.format_email_body(
                "These are preliminary estimates only — please do not use for the final report.",
                f"Draft estimate: {wrong_numbers[0]}",
                "The final numbers will come from the department head directly.",
                signoff_name=ctx.first_name(decoy_a_name),
            ),
            timestamp=ctx.now - timedelta(days=5, hours=1),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
            is_read=True,
        )
    )

    decoy_b_name = ctx.fake.name()
    decoy_b_email = ctx.email_for_name(decoy_b_name, domain="mktg.thornton.com")
    ctx.base["emails"].append(
        ctx.email(
            from_name=decoy_b_name,
            from_addr=decoy_b_email,
            subject="Q1 reforecast — Marketing (superseded)",
            body=ctx.format_email_body(
                "Ignore this earlier reforecast — the final numbers were sent separately by the department head.",
                f"Outdated figure: {wrong_numbers[1]}",
                signoff_name=ctx.first_name(decoy_b_name),
            ),
            timestamp=ctx.now - timedelta(days=7, hours=3),
            thread_id=ctx.next_id("thread"),
            labels=["inbox"],
            is_read=True,
        )
    )

    ctx.ensure_contact(exec_name, exec_email)
    for name, email_addr in zip(dept_head_names, dept_emails):
        ctx.ensure_contact(name, email_addr)

    return {
        "exec_email": exec_email,
        "dept_emails": dept_emails,
        "dept_a_name": dept_a_name,
        "dept_b_name": dept_b_name,
        "dept_c_name": dept_c_name,
        "dept_a_dept": dept_names[0],
        "dept_b_dept": dept_names[1],
        "dept_c_dept": dept_names[2],
        "number_a": numbers[0],
        "number_b": numbers[1],
        "number_c": numbers[2],
        "wrong_numbers": wrong_numbers,
    }


# ---------------------------------------------------------------------------
# Gmail: Subscription Cleanup
# ---------------------------------------------------------------------------

@_register("subscription_cleanup")
def build_subscription_cleanup(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create newsletter, notification, and spam emails for subscription cleanup.

    Generates 4 newsletter emails in Promotions, 2 automated notifications in
    Updates, and 2 spam emails in Promotions. One newsletter (supply chain) is
    the "good" one to be forwarded.
    """
    newsletter_domain_a = "weeklydigest.thornton.com"
    newsletter_domain_b = "techinsights.io"
    personal_email = "avery.personal@outlook.com"
    good_newsletter_topic = "AI in supply chain management"

    # 4 newsletter emails in Promotions tab
    promo_ids: list[str] = []
    newsletter_senders = [
        ("Weekly Digest", f"editor@{newsletter_domain_a}", "Your weekly operations roundup"),
        ("Tech Insights", f"newsletter@{newsletter_domain_b}", "New trends in enterprise tooling"),
        ("Market Watch", "alerts@mktwatch.co", "Industry benchmarks for Q1"),
        ("Supply Chain Today", "news@supply.thornton.com", "How AI is transforming supply chain management"),
    ]
    good_newsletter_id: str | None = None
    for idx, (sender_name, sender_addr, subject) in enumerate(newsletter_senders):
        body_text = (
            f"This week we cover the latest developments in operations and technology. "
            f"Featured: {subject.lower()}."
        )
        if "supply chain" in subject.lower():
            body_text = (
                f"In this issue: a deep dive into {good_newsletter_topic}. We explore how modern "
                "logistics teams are using machine learning to optimize inventory forecasting and "
                "reduce waste across regional distribution centers."
            )
        em = ctx.email(
            from_name=sender_name,
            from_addr=sender_addr,
            subject=subject,
            body=ctx.format_email_body(body_text, signoff_name=sender_name),
            timestamp=ctx.now - timedelta(days=2, hours=idx * 3),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "promotions"],
        )
        promo_ids.append(em.id)
        if "supply chain" in subject.lower():
            good_newsletter_id = em.id
        ctx.base["emails"].append(em)

    # 2 automated notification emails in Updates tab
    update_ids: list[str] = []
    update_senders = [
        ("CI Build System", "builds@ci.thornton.com", "Build #4821 completed successfully"),
        ("Monitoring Alerts", "noreply@status.thornton.com", "Weekly uptime report — all services green"),
    ]
    for idx, (sender_name, sender_addr, subject) in enumerate(update_senders):
        em = ctx.email(
            from_name=sender_name,
            from_addr=sender_addr,
            subject=subject,
            body=ctx.format_email_body(
                f"Automated notification: {subject}.",
                "This is an automated message. No reply is necessary.",
                signoff_name=sender_name,
            ),
            timestamp=ctx.now - timedelta(days=1, hours=idx * 4),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "updates"],
        )
        update_ids.append(em.id)
        ctx.base["emails"].append(em)

    # 2 spam emails with suspicious subjects
    spam_ids: list[str] = []
    spam_entries = [
        ("Prize Center", "winner@luxurydeals.net", "You've won a free laptop! Claim now!"),
        ("Benefits Club", "gifts@globalwins.net", "Claim your $500 gift card now — act fast!"),
    ]
    for idx, (sender_name, sender_addr, subject) in enumerate(spam_entries):
        em = ctx.email(
            from_name=sender_name,
            from_addr=sender_addr,
            subject=subject,
            body=ctx.format_email_body(
                f"Congratulations! {subject} Click the link below to redeem your reward.",
                "This offer expires in 24 hours. Do not miss out!",
                signoff_name=sender_name,
            ),
            timestamp=ctx.now - timedelta(days=1, hours=idx * 2 + 1),
            thread_id=ctx.next_id("thread"),
            labels=["inbox", "promotions"],
        )
        spam_ids.append(em.id)
        ctx.base["emails"].append(em)

    return {
        "promo_ids": promo_ids,
        "update_ids": update_ids,
        "good_newsletter_id": good_newsletter_id,
        "good_newsletter_topic": good_newsletter_topic,
        "personal_email": personal_email,
        "spam_ids": spam_ids,
        "newsletter_domain_a": newsletter_domain_a,
        "newsletter_domain_b": newsletter_domain_b,
    }


# ---------------------------------------------------------------------------
# Easy-task builders (simple Gmail operations)
# ---------------------------------------------------------------------------

@_register("star_email")
def build_star_email(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed an email that the agent must star."""
    thread_id = ctx.next_id("thread")
    em = ctx.email(
        from_name="Alice Chen",
        from_addr="alice.chen@thornton.com",
        subject="Project Update — Q1 Milestones",
        body=ctx.format_email_body(
            "Hi team, here's a quick summary of where we stand on Q1 milestones.",
            "Design phase is complete. Engineering is at 80%. QA starts next week.",
            signoff_name="Alice",
        ),
        timestamp=ctx.now - timedelta(days=1),
        thread_id=thread_id,
        labels=["inbox"],
    )
    ctx.base["emails"].append(em)
    ctx.ensure_contact("Alice Chen", "alice.chen@thornton.com")
    return {"target_email_id": em.id}


@_register("compose_new")
def build_compose_new(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed baseline state for composing a new email (no special setup needed)."""
    ctx.ensure_contact("Alice", "alice@thornton.com")
    return {}


@_register("reply_simple")
def build_reply_simple(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed an email from Bob that the agent must reply to."""
    thread_id = ctx.next_id("thread")
    em = ctx.email(
        from_name="Bob Martinez",
        from_addr="bob.martinez@thornton.com",
        subject="Meeting Tomorrow at 2pm",
        body=ctx.format_email_body(
            "Hi, just confirming our meeting tomorrow at 2pm in Conference Room B.",
            "I'll bring the project deck. Let me know if you can make it.",
            signoff_name="Bob",
        ),
        timestamp=ctx.now - timedelta(hours=4),
        thread_id=thread_id,
        labels=["inbox"],
    )
    ctx.base["emails"].append(em)
    ctx.ensure_contact("Bob Martinez", "bob.martinez@thornton.com")
    return {"target_email_id": em.id, "target_thread_id": thread_id}


@_register("delete_spam")
def build_delete_spam(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed a spam email and a normal email for the delete-spam task."""
    thread_spam = ctx.next_id("thread")
    spam = ctx.email(
        from_name="Winner Notification",
        from_addr="winner@prizecentral.net",
        subject="YOU WON $1,000,000!!! Click NOW!!!",
        body="Congratulations! You have been selected as our lucky winner. Click the link below to claim your prize immediately!",
        timestamp=ctx.now - timedelta(hours=2),
        thread_id=thread_spam,
        labels=["inbox"],
    )
    ctx.base["emails"].append(spam)

    thread_normal = ctx.next_id("thread")
    normal = ctx.email(
        from_name="Team Lead",
        from_addr="lead@thornton.com",
        subject="Sprint Planning Notes",
        body=ctx.format_email_body(
            "Here are the notes from today's sprint planning session.",
            signoff_name="Team Lead",
        ),
        timestamp=ctx.now - timedelta(hours=3),
        thread_id=thread_normal,
        labels=["inbox"],
    )
    ctx.base["emails"].append(normal)
    return {"spam_email_id": spam.id, "normal_email_id": normal.id}


@_register("forward_email")
def build_forward_email(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed an invoice email from Carol Wang to be forwarded."""
    thread_id = ctx.next_id("thread")
    em = ctx.email(
        from_name="Carol Wang",
        from_addr="carol.wang@bluespark.io",
        subject="Invoice #1234 — March Services",
        body=ctx.format_email_body(
            "Hi, please find attached the invoice for March consulting services.",
            "Total: $4,500.00. Payment terms: Net 30.",
            "Let me know if you have any questions.",
            signoff_name="Carol",
        ),
        timestamp=ctx.now - timedelta(days=2),
        thread_id=thread_id,
        labels=["inbox"],
    )
    ctx.base["emails"].append(em)
    ctx.ensure_contact("Carol Wang", "carol.wang@bluespark.io")
    ctx.ensure_contact("Dave", "dave@thornton.com")
    return {"target_email_id": em.id}


@_register("create_label")
def build_create_label(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """No special seed setup needed for creating a label."""
    return {}


@_register("mark_all_read")
def build_mark_all_read(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed 5 unread emails in the inbox.

    Forces all pre-existing and future distractor emails to is_read=True so
    only the 5 seeded emails are unread.  This prevents distractor emails from
    being marked as read by the agent's "mark all" action and triggering false
    invariant violations.
    """
    # Mark any emails already in the base state as read (from prior steps).
    for em in ctx.base.get("emails", []):
        em.is_read = True
    # Signal the seeder to force distractor emails to is_read=True as well.
    ctx.base["_force_distractor_emails_read"] = True

    senders = [
        ("Dana Lee", "dana.lee@thornton.com"),
        ("Eric Zhao", "eric.zhao@thornton.com"),
        ("Fiona Park", "fiona.park@thornton.com"),
        ("Greg Novak", "greg.novak@thornton.com"),
        ("Hannah Reeves", "hannah.reeves@thornton.com"),
    ]
    email_ids: list[str] = []
    for i, (name, addr) in enumerate(senders):
        thread_id = ctx.next_id("thread")
        em = ctx.email(
            from_name=name,
            from_addr=addr,
            subject=f"Update #{i + 1} — {ctx.initiative_name().title()}",
            body=ctx.generic_email_body(name),
            timestamp=ctx.now - timedelta(hours=i + 1),
            thread_id=thread_id,
            labels=["inbox"],
            is_read=False,
        )
        ctx.base["emails"].append(em)
        email_ids.append(em.id)
    return {"unread_email_ids": email_ids, "unread_count": len(email_ids)}


# search_and_star builder is in _seed_builders_easy.py (with 20 padding emails)


@_register("change_setting")
def build_change_setting(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """No special seed setup needed for changing a setting."""
    return {}


@_register("update_contact")
def build_update_contact(ctx: SeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed a contact for Alice Chen that the agent must update."""
    c = ctx.contact(
        name="Alice Chen",
        email="alice.chen@thornton.com",
        company="Company Inc.",
        note="Engineering",
    )
    ctx.base["contacts"].append(c)
    return {"contact_id": c.id, "contact_name": c.name}


# ---------------------------------------------------------------------------
# Import batch modules so their @_register decorators fire
# ---------------------------------------------------------------------------

import breakingweb.tasks._seed_builders_batch01 as _batch01  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch02 as _batch02  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch03 as _batch03  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch04 as _batch04  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch05 as _batch05  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch06 as _batch06  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch07 as _batch07  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch08 as _batch08  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch09 as _batch09  # noqa: E402, F401
import breakingweb.tasks._seed_builders_batch10 as _batch10  # noqa: E402, F401
import breakingweb.tasks._seed_builders_easy as _easy  # noqa: E402, F401
