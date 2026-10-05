"""Server injection layer: feature flags applied to environment state.

Targets Planning, State Tracking, and Backtracking primitives.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any


def _rh_normalize_notification_type(raw_type: Any) -> str:
    if not raw_type:
        return "security_alert"
    notification_type = str(raw_type)
    if notification_type in {
        "order_fill",
        "price_alert",
        "dividend",
        "earnings",
        "transfer_complete",
        "security_alert",
        "recurring_investment",
        "tax_document",
        "margin_call",
        "corporate_action",
    }:
        return notification_type
    return {
        "account": "security_alert",
        "alert": "price_alert",
        "alerts": "price_alert",
        "market": "price_alert",
        "order": "order_fill",
        "orders": "order_fill",
        "price": "price_alert",
        "recurring": "recurring_investment",
        "system": "security_alert",
        "tax": "tax_document",
        "transfer": "transfer_complete",
        "watchlist": "price_alert",
        "dividend_notice": "dividend",
        "earnings_alert": "earnings",
        "margin": "margin_call",
        "corporate": "corporate_action",
    }.get(notification_type, "security_alert")


def _lms_latest_timestamp(state: Any) -> datetime:
    fallback = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    latest = fallback
    for course in getattr(state, "courses", []):
        for candidate in (
            getattr(course, "drop_deadline", None),
            getattr(course, "final_exam_date", None),
        ):
            if candidate and candidate > latest:
                latest = candidate
    for assignment in getattr(state, "assignments", []):
        for candidate in (getattr(assignment, "due_at", None), getattr(assignment, "submitted_at", None)):
            if candidate and candidate > latest:
                latest = candidate
    for post in getattr(state, "discussion_posts", []):
        candidate = getattr(post, "timestamp", None)
        if candidate and candidate > latest:
            latest = candidate
    for ann in getattr(state, "announcements", []):
        candidate = getattr(ann, "posted_at", None)
        if candidate and candidate > latest:
            latest = candidate
    for review in getattr(state, "peer_reviews", []):
        candidate = getattr(review, "due_at", None)
        if candidate and candidate > latest:
            latest = candidate
    for event in getattr(state, "calendar_events", []):
        candidate = getattr(event, "start_datetime", None)
        if candidate and candidate > latest:
            latest = candidate
    return latest


def apply_server_injection(state: Any, params: dict[str, Any]) -> None:
    """Mutate server state to create degraded conditions."""
    action = params.get("action", "")
    mutated = False

    if action == "scramble_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "emails"):
            for email in state.emails:
                if hasattr(email, "timestamp"):
                    offset = rng.randint(-86400 * 7, 86400 * 7)
                    email.timestamp += timedelta(seconds=offset)
                    mutated = True
        elif hasattr(state, "courses") and hasattr(state, "assignments"):
            for course in getattr(state, "courses", []):
                for field in ("drop_deadline", "final_exam_date"):
                    value = getattr(course, field, None)
                    if value is not None:
                        setattr(course, field, value + timedelta(seconds=rng.randint(-86400 * 3, 86400 * 3)))
                        mutated = True
            for assignment in getattr(state, "assignments", []):
                if getattr(assignment, "due_at", None) is not None:
                    assignment.due_at += timedelta(seconds=rng.randint(-86400 * 4, 86400 * 4))
                    mutated = True
                if getattr(assignment, "submitted_at", None) is not None:
                    assignment.submitted_at += timedelta(seconds=rng.randint(-3600 * 12, 3600 * 12))
                    mutated = True
            for discussion in getattr(state, "discussions", []):
                if getattr(discussion, "due_at", None) is not None:
                    discussion.due_at += timedelta(seconds=rng.randint(-86400 * 4, 86400 * 4))
                    mutated = True
            for post in getattr(state, "discussion_posts", []):
                if getattr(post, "timestamp", None) is not None:
                    post.timestamp += timedelta(seconds=rng.randint(-3600 * 18, 3600 * 18))
                    mutated = True
                if getattr(post, "updated_at", None) is not None:
                    post.updated_at += timedelta(seconds=rng.randint(-3600 * 18, 3600 * 18))
                    mutated = True
            for ann in getattr(state, "announcements", []):
                if getattr(ann, "posted_at", None) is not None:
                    ann.posted_at += timedelta(seconds=rng.randint(-86400 * 5, 86400 * 5))
                    mutated = True
            for review in getattr(state, "peer_reviews", []):
                if getattr(review, "due_at", None) is not None:
                    review.due_at += timedelta(seconds=rng.randint(-86400 * 3, 86400 * 3))
                    mutated = True
            for event in getattr(state, "calendar_events", []):
                if getattr(event, "start_datetime", None) is not None:
                    delta = timedelta(seconds=rng.randint(-86400 * 4, 86400 * 4))
                    event.start_datetime += delta
                    mutated = True
                    if getattr(event, "end_datetime", None) is not None:
                        event.end_datetime += delta
                        mutated = True

    elif action == "shuffle_contacts":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "contacts"):
            rng.shuffle(state.contacts)
            mutated = True

    elif action == "hide_prerequisite":
        # Two call shapes:
        #   (legacy) label_name: "Foo"
        #   (multi)  prerequisites: [{kind: label|contact|filter, name|email: ...}, ...]
        # Multi mode lets a single Planning task force the agent to recreate
        # several missing pieces (e.g. label + contact + filter) instead of
        # one. Legacy callers keep working.
        prerequisites = params.get("prerequisites")
        legacy_label = params.get("label_name")
        if legacy_label and not prerequisites:
            prerequisites = [{"kind": "label", "name": legacy_label}]
        for prereq in prerequisites or []:
            if not isinstance(prereq, dict):
                continue
            kind = str(prereq.get("kind", "label")).lower()
            if kind == "label":
                name = prereq.get("name")
                if name and hasattr(state, "labels"):
                    state.labels = [lab for lab in state.labels if lab.name != name]
                    mutated = True
            elif kind == "contact":
                # Match by email if provided, otherwise by exact name.
                email_match = prereq.get("email")
                name_match = prereq.get("name")
                if hasattr(state, "contacts") and (email_match or name_match):
                    state.contacts = [
                        c for c in state.contacts
                        if (email_match and getattr(c, "email", None) != email_match)
                        or (not email_match and name_match and getattr(c, "name", None) != name_match)
                    ] if email_match else [
                        c for c in state.contacts if getattr(c, "name", None) != name_match
                    ]
                    mutated = True
            elif kind == "filter":
                name = prereq.get("name") or prereq.get("query")
                if hasattr(state, "filters") and name:
                    state.filters = [
                        f for f in state.filters
                        if getattr(f, "name", None) != name
                        and getattr(f, "query", None) != name
                    ]
                    mutated = True

    elif action == "inject_distractor_emails":
        # ARCHITECTURAL NOTE (kept in server.py, not seed.py):
        # This action lives at the server layer because the injector
        # pipeline (apply.py) runs seed-layer first, then server-layer.
        # Several Gmail variants pair this distractor injection with
        # OTHER server-layer state mutations (`scramble_timestamps`,
        # `shuffle_contacts`) that must run AFTER the initial seed pool
        # is in place. Moving it to the seed layer would break that
        # ordering — the timestamps would be scrambled before the
        # distractors arrived, leaving the distractors with un-scrambled
        # base timestamps. Keeping it server-layer preserves the "all
        # post-seed mutations together" invariant.
        count = params.get("count", 5)
        subject_prefix = params.get("subject_prefix", "")
        if hasattr(state, "emails") and state.emails:
            _REALISTIC_EMAILS = [
                {
                    "subject": "Quick follow-up on our earlier discussion",
                    "body": "Hey, just wanted to circle back on what we talked about this morning. I think we're aligned on the timeline but I want to double-check the resource allocation before I update the tracker. Can you confirm whether the Q3 numbers are final?",
                },
                {
                    "subject": "Updated timeline for the deliverables",
                    "body": "Hi team,\n\nI've pushed the design review to Thursday based on the feedback from stakeholders. Engineering milestones stay the same. Please flag any conflicts by EOD tomorrow so we can adjust.",
                },
                {
                    "subject": "Notes from today's sync",
                    "body": "Sharing notes from the sync:\n\n1. Dashboard redesign approved — dev starts next sprint\n2. API migration blocked on the auth team's review\n3. Hiring update: two offers out, one accepted\n\nLet me know if I missed anything.",
                },
                {
                    "subject": "Revised figures — please review",
                    "body": "Attached the updated projections with the corrected assumptions. Main change: we moved the infrastructure costs from OpEx to CapEx per finance's guidance. Net impact is about $40K lower quarterly burn.",
                },
                {
                    "subject": "Re: Action items from the meeting",
                    "body": "Following up on the three open items:\n\n- Contract review: legal says they need until Friday\n- Vendor selection: narrowed to two finalists, scheduling demos\n- Budget reallocation: waiting on director approval\n\nI'll send another update once legal comes back.",
                },
                {
                    "subject": "One more thing on the project scope",
                    "body": "I realized we didn't address the internationalization requirement in today's planning. If we're targeting EU launch in Q2, we need to budget for translation and compliance review. Adding it to the backlog for now.",
                },
                {
                    "subject": "Sharing the latest draft for your feedback",
                    "body": "Here's the v3 draft incorporating the comments from last round. I restructured section 2 and added the competitive analysis appendix. Would appreciate your review by Wednesday so we can finalize before the board presentation.",
                },
                {
                    "subject": "Heads up on the schedule change",
                    "body": "The all-hands got moved from Tuesday 3pm to Wednesday 10am due to a conflict with the leadership offsite. Same agenda, same Zoom link. Calendar invites updated.",
                },
                {
                    "subject": "Checking in on the open items",
                    "body": "Haven't heard back on the two items from last week — the vendor NDA and the staging environment access request. Are these still blocked or did they get resolved? Happy to help push things along if needed.",
                },
                {
                    "subject": "Summary of decisions from this morning",
                    "body": "Quick recap of what we decided:\n\n- Go with Option B for the pricing model\n- Delay the beta launch by two weeks to fix the onboarding flow\n- Hire a contractor for the data migration piece\n\nI'll update the project plan and share it by EOD.",
                },
            ]
            _REALISTIC_NAMES = [
                ("Jordan Park", "jordan.park@thornton.com"),
                ("Morgan Liu", "morgan.liu@thornton.com"),
                ("Casey Rivera", "casey.rivera@thornton.com"),
                ("Taylor Brooks", "taylor.brooks@thornton.com"),
                ("Riley Santos", "riley.santos@thornton.com"),
                ("Quinn Patel", "quinn.patel@thornton.com"),
                ("Drew Nakamura", "drew.nakamura@thornton.com"),
                ("Jamie Okafor", "jamie.okafor@thornton.com"),
                ("Alex Drummond", "alex.drummond@thornton.com"),
                ("Avery Kim", "avery.kim@thornton.com"),
            ]
            rng = random.Random(params.get("seed", 42))
            template = state.emails[0]
            # Track existing IDs so we don't collide with prior injectors that
            # also use Random(42) (e.g. seed-layer increase_distractors).
            existing_email_ids = {e.id for e in state.emails}
            existing_thread_ids = {e.thread_id for e in state.emails}

            def _unique_id(prefix: str, taken: set[str]) -> str:
                # Reject collisions; loop bounded by the 90,000 keyspace.
                while True:
                    candidate = f"{prefix}_{rng.randint(10000, 99999)}"
                    if candidate not in taken:
                        taken.add(candidate)
                        return candidate

            for i in range(count):
                distractor = template.model_copy(deep=True)
                distractor.id = _unique_id("email", existing_email_ids)
                distractor.thread_id = _unique_id("thread", existing_thread_ids)
                entry = _REALISTIC_EMAILS[i % len(_REALISTIC_EMAILS)]
                distractor.subject = f"{subject_prefix}{entry['subject']}"
                name, addr = _REALISTIC_NAMES[i % len(_REALISTIC_NAMES)]
                distractor.from_name = name
                distractor.from_addr = addr
                distractor.body = entry["body"]
                distractor.is_read = rng.random() > 0.4  # 60% read, 40% unread
                offset = rng.randint(-3600 * 48, 3600 * 2)
                distractor.timestamp += timedelta(seconds=offset)
                state.emails.insert(rng.randint(0, len(state.emails)), distractor)
                mutated = True

    elif action == "corrupt_state":
        # Multiple call shapes (Gmail and Robinhood):
        #   (legacy gmail)  email_id, field, value
        #   (multi gmail)   corruptions: [{email_id, field, value}, ...]
        #   (swap gmail)    swap: {email_id_a, email_id_b, fields: [...]}
        #   (rh single)     target: positions|orders, target_id, field, value
        #   (rh multi)      corruptions: [{target: positions|orders, target_id, field, value}, ...]
        #   (rh swap)       swap: {target: positions|orders, target_id_a, target_id_b, fields: [...]}
        # Swap exchanges the listed fields between two existing records so
        # the surface still looks internally consistent (no NULLs, no
        # obvious placeholder strings) — both halves still type-check.
        # That's harder than a single `value="CORRUPTED"` write because
        # nothing dangles.

        def _by_id(items: list, eid: str) -> Any | None:
            for e in items:
                if getattr(e, "id", None) == eid:
                    return e
            return None

        def _resolve_collection(target_kind: str | None) -> list | None:
            kind = (target_kind or "").lower()
            if kind in {"", "email", "emails"} and hasattr(state, "emails"):
                return state.emails
            if kind in {"position", "positions"} and hasattr(state, "positions"):
                return state.positions
            if kind in {"order", "orders"} and hasattr(state, "orders"):
                return state.orders
            if kind in {"notification", "notifications"} and hasattr(state, "notifications"):
                return state.notifications
            return None

        # Build the corruption list. Legacy Gmail call (email_id+field+value)
        # is normalized into the multi shape so the loop below covers both.
        corruptions = list(params.get("corruptions") or [])
        if not corruptions:
            eid = params.get("email_id")
            if eid is not None:
                corruptions = [{
                    "email_id": eid,
                    "field": params.get("field", "subject"),
                    "value": params.get("value", "CORRUPTED"),
                }]
            else:
                tid = params.get("target_id")
                if tid is not None:
                    corruptions = [{
                        "target": params.get("target", "emails"),
                        "target_id": tid,
                        "field": params.get("field"),
                        "value": params.get("value"),
                    }]

        for spec in corruptions:
            if not isinstance(spec, dict):
                continue
            # Spec resolution: prefer explicit `target`/`target_id`,
            # fall back to legacy `email_id`.
            collection = _resolve_collection(spec.get("target"))
            if collection is None:
                # Legacy email shape.
                if hasattr(state, "emails"):
                    collection = state.emails
                else:
                    continue
            record_id = spec.get("target_id") or spec.get("email_id")
            target = _by_id(collection, record_id) if record_id else None
            if target is None:
                continue
            field = spec.get("field")
            if field and hasattr(target, field):
                setattr(target, field, spec.get("value"))
                mutated = True

        swap = params.get("swap")
        if isinstance(swap, dict):
            collection = _resolve_collection(swap.get("target"))
            if collection is None and hasattr(state, "emails"):
                collection = state.emails
            id_a = swap.get("target_id_a") or swap.get("email_id_a")
            id_b = swap.get("target_id_b") or swap.get("email_id_b")
            a = _by_id(collection or [], id_a) if id_a else None
            b = _by_id(collection or [], id_b) if id_b else None
            fields = swap.get("fields") or []
            if a is not None and b is not None:
                for field in fields:
                    if hasattr(a, field) and hasattr(b, field):
                        tmp = getattr(a, field)
                        setattr(a, field, getattr(b, field))
                        setattr(b, field, tmp)
                        mutated = True

    # --- Robinhood server actions ---

    elif action == "scramble_order_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "orders"):
            for order in state.orders:
                if hasattr(order, "created_at") and order.created_at:
                    offset = rng.randint(-86400 * 3, 86400 * 3)
                    order.created_at += timedelta(seconds=offset)
                    mutated = True

    elif action == "scramble_notification_timestamps":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "notifications"):
            for notif in state.notifications:
                if hasattr(notif, "timestamp") and notif.timestamp:
                    offset = rng.randint(-86400 * 5, 86400 * 5)
                    notif.timestamp += timedelta(seconds=offset)
                    mutated = True

    elif action == "shuffle_positions":
        rng = random.Random(params.get("seed", 42))
        if hasattr(state, "positions"):
            rng.shuffle(state.positions)
            mutated = True

    elif action == "hide_watchlist":
        # Two call shapes (mirrors hide_prerequisite):
        #   (legacy) watchlist_name: "Foo"
        #   (multi)  prerequisites: [{kind: watchlist|setting, name|key: ..., default?: any}, ...]
        # Setting-kind clears a per-account preference (e.g.
        # `extended_hours_enabled`, `position_threshold_alert_pct`) so the
        # agent must re-set it as part of the task plan.
        prerequisites = params.get("prerequisites")
        legacy_watchlist = params.get("watchlist_name")
        if legacy_watchlist and not prerequisites:
            prerequisites = [{"kind": "watchlist", "name": legacy_watchlist}]
        for prereq in prerequisites or []:
            if not isinstance(prereq, dict):
                continue
            kind = str(prereq.get("kind", "watchlist")).lower()
            if kind == "watchlist":
                name = prereq.get("name")
                if name and hasattr(state, "watchlists"):
                    state.watchlists = [w for w in state.watchlists if w.name != name]
                    mutated = True
            elif kind == "setting":
                key = prereq.get("key") or prereq.get("name")
                if key and hasattr(state, "settings"):
                    settings = getattr(state, "settings", None)
                    default = prereq.get("default")
                    if isinstance(settings, dict):
                        settings[key] = default
                        mutated = True
                    elif hasattr(settings, key):
                        setattr(settings, key, default)
                        mutated = True

    elif action in {"inject_notifications", "inject_distractor_notifications"}:
        if hasattr(state, "add_notification"):
            for spec in params.get("notifications", []) or []:
                state.add_notification(
                    type=spec.get("type", "deal_alert"),
                    title=spec.get("title", "Notification"),
                    message=spec.get("message", spec.get("body", "")),
                    related_id=spec.get("related_id"),
                )
                mutated = True
        elif hasattr(state, "notifications"):
            from breakingweb.backend.models.robinhood import Notification
            from breakingweb.backend.models.base import utc_now
            rng = random.Random(params.get("seed", 42))
            _NOTIF_TEMPLATES = [
                ("system", "Account Update", "Your account settings have been reviewed."),
                ("price_alert", "Price Movement", "A stock in your watchlist moved significantly."),
                ("order_fill", "Order Update", "An order status has changed. Check your orders."),
                ("dividend", "Dividend Notice", "A dividend payment is being processed."),
                ("transfer", "Transfer Update", "A transfer status has been updated."),
            ]
            custom_notifications = params.get("notifications") or []
            if not custom_notifications and params.get("messages"):
                custom_notifications = [
                    {"title": "Notification", "message": message}
                    for message in params.get("messages", [])
                ]
            if not custom_notifications:
                count = int(params.get("count", 5))
                custom_types = params.get("types") or []
                for i in range(count):
                    if custom_types:
                        ntype = custom_types[i % len(custom_types)]
                        title = f"{ntype.replace('_', ' ').title()} Update"
                        msg = f"A {ntype.replace('_', ' ')} notification requires review."
                    else:
                        ntype, title, msg = _NOTIF_TEMPLATES[i % len(_NOTIF_TEMPLATES)]
                    custom_notifications.append({"type": ntype, "title": title, "message": msg})
            for spec in custom_notifications:
                ntype = _rh_normalize_notification_type(spec.get("type", spec.get("category", "system")))
                title = spec.get("title", "Notification")
                msg = spec.get("message", spec.get("body", ""))
                state.notifications.append(Notification(
                    id=f"notif_noise_{rng.randint(10000, 99999)}",
                    type=ntype,
                    title=title,
                    message=msg,
                    timestamp=utc_now() - timedelta(hours=rng.randint(1, 72)),
                    is_read=spec.get("is_read", rng.random() > 0.5),
                ))
            mutated = True

    elif action in {"add_lms_correction_notice", "inject_lms_correction_notice"}:
        if hasattr(state, "courses") and hasattr(state, "announcements"):
            from breakingweb.backend.models.lms import Announcement, DiscussionPost
            rng = random.Random(params.get("seed", 42))

            def pick_course() -> Any:
                course_id = params.get("course_id")
                if course_id and hasattr(state, "get_course"):
                    course = state.get_course(course_id)
                    if course is not None:
                        return course
                course_code = params.get("course_code")
                if course_code and hasattr(state, "get_course_by_code"):
                    course = state.get_course_by_code(course_code)
                    if course is not None:
                        return course
                course_title = params.get("course_title")
                if course_title:
                    for course in state.courses:
                        if course.title == course_title:
                            return course
                return state.courses[0] if state.courses else None

            course = pick_course()
            if course is not None:
                notice_type = str(params.get("type", "announcement")).lower()
                created_at = params.get("posted_at")
                if not created_at:
                    created_at = _lms_latest_timestamp(state) + timedelta(minutes=int(params.get("minutes_offset", 20)))
                title = params.get("title", f"Correction: {getattr(course, 'course_code', course.title)}")
                body = params.get("body", "Correction: please use the latest course update.")

                if notice_type == "discussion_post" and hasattr(state, "discussions"):
                    discussion_id = params.get("discussion_id")
                    discussion = None
                    if discussion_id and hasattr(state, "get_discussion"):
                        discussion = state.get_discussion(discussion_id)
                    if discussion is None and params.get("discussion_title"):
                        discussion = next(
                            (d for d in state.discussions if d.title == params.get("discussion_title")),
                            None,
                        )
                    if discussion is not None:
                        post_id = f"post_noise_{rng.randint(10000, 99999)}"
                        state.discussion_posts.append(DiscussionPost(
                            id=post_id,
                            discussion_id=discussion.id,
                            author_id=params.get("author_id", getattr(course, "instructor_id", state.student.id)),
                            author_name=params.get("author_name", getattr(course, "instructor_name", "Instructor")),
                            body=body,
                            timestamp=created_at,
                            is_anonymous=bool(params.get("is_anonymous", False)),
                        ))
                        mutated = True
                else:
                    ann_id = params.get("id", f"ann_noise_{rng.randint(10000, 99999)}")
                    state.announcements.append(Announcement(
                        id=ann_id,
                        course_id=course.id,
                        title=title,
                        body=body,
                        posted_at=created_at,
                        is_read=bool(params.get("is_read", False)),
                        priority=params.get("priority", "normal"),
                    ))
                    mutated = True

    if mutated and hasattr(state, "touch"):
        state.touch()
