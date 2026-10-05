from __future__ import annotations

from datetime import datetime, timezone

from breakingweb.backend.models.gmail import Contact, Email, FilterRule, GmailSettings, GmailState, Label


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _build_state() -> GmailState:
    return GmailState(
        env_id="gmail",
        task_id="test_task",
        owner_name="Test User",
        owner_email="test@example.com",
        created_at=_dt("2026-03-20T12:00:00"),
        emails=[
            Email(
                id="email_recent",
                from_addr="alice@example.com",
                from_name="Alice",
                to=["test@example.com"],
                subject="Recent project update",
                body="Recent body",
                timestamp=_dt("2026-03-19T09:00:00"),
                labels=["inbox", "Projects"],
                thread_id="thread_1",
            ),
            Email(
                id="email_old",
                from_addr="bob@example.com",
                from_name="Bob",
                to=["test@example.com"],
                subject="Old project update",
                body="Old body",
                timestamp=_dt("2026-03-10T09:00:00"),
                labels=["inbox", "Archive-Projects"],
                thread_id="thread_2",
            ),
        ],
        contacts=[
            Contact(
                id="contact_1",
                name="Dana Cross",
                email="dana@example.com",
                note="Initial note",
                is_vip=False,
                is_starred=False,
            )
        ],
        labels=[
            Label(id="label_projects", name="Projects", show_in_message_list="show"),
            Label(id="label_archive", name="Archive-Projects", show_in_message_list="hide"),
        ],
        filters=[
            FilterRule(
                id="filter_1",
                name="Projects filter",
                query="label:Projects",
                label_requirements=["Projects"],
                add_labels=["Projects"],
            )
        ],
        settings=GmailSettings(id="settings"),
    )


def test_label_rename_and_delete_propagate_to_emails_and_filters() -> None:
    state = _build_state()

    renamed = state.update_label(
        "label_projects",
        name="Engineering/Active",
        show_in_label_list="show_if_unread",
        show_in_message_list="hide",
    )

    assert renamed.name == "Engineering/Active"
    assert renamed.show_in_label_list == "show_if_unread"
    assert renamed.show_in_message_list == "hide"
    assert "Engineering/Active" in state.get_email("email_recent").labels
    assert "Projects" not in state.get_email("email_recent").labels
    assert state.filters[0].add_labels == ["Engineering/Active"]
    assert state.filters[0].label_requirements == ["Engineering/Active"]

    removed = state.remove_label("label_archive")

    assert removed.name == "Archive-Projects"
    assert state.get_email("email_old").labels == ["inbox"]
    assert all(label.name != "Archive-Projects" for label in state.labels)


def test_contact_update_supports_star_toggle() -> None:
    state = _build_state()

    updated = state.update_contact(
        "contact_1",
        note="Promoted to Staff Engineer",
        is_vip=True,
        is_starred=True,
    )

    assert updated.note == "Promoted to Staff Engineer"
    assert updated.is_vip is True
    assert updated.is_starred is True


def test_search_supports_absolute_and_relative_date_filters() -> None:
    state = _build_state()

    newer = [email.id for email in state.search("newer_than:7d")]
    older = [email.id for email in state.search("older_than:7d")]
    after = [email.id for email in state.search("after:2026-03-15")]
    before = [email.id for email in state.search("before:2026-03-15")]

    assert newer == ["email_recent"]
    assert older == ["email_old"]
    assert after == ["email_recent"]
    assert before == ["email_old"]


def test_filters_preserve_never_spam_flag() -> None:
    state = _build_state()
    rule = FilterRule(
        id="filter_2",
        name="Critical alerts",
        query="from:@alerts.example.com",
        from_addresses=["*@alerts.example.com"],
        add_labels=["Ops/Critical"],
        star=True,
        never_spam=True,
    )

    created = state.create_filter(rule)

    assert created.never_spam is True
    assert state.filters[-1].never_spam is True


def test_send_email_normalizes_display_name_recipients() -> None:
    state = _build_state()

    sent = state.send_email(
        to=["Ravi Menon <SOFIA.BROOKS@ATLAS.DEV>"],
        cc=["Priya Sharma <PRIYA@ATLAS.DEV>"],
        bcc=["LEGAL@ATLAS.DEV"],
        subject="Atlas decision",
        body="Forwarding the final decision on Project Atlas.",
    )

    assert sent.to == ["sofia.brooks@atlas.dev"]
    assert sent.cc == ["priya@atlas.dev"]
    assert sent.bcc == ["legal@atlas.dev"]
