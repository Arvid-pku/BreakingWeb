from __future__ import annotations

from datetime import datetime, timezone

from breakingweb.backend.models.gmail import Draft, Email, GmailSettings, GmailState, Label


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _build_state() -> GmailState:
    return GmailState(
        env_id="gmail",
        task_id="mailbox_contract",
        owner_name="Test User",
        owner_email="test@example.com",
        created_at=_dt("2026-03-20T12:00:00"),
        emails=[
            Email(
                id="email_starred",
                from_addr="alice@example.com",
                from_name="Alice",
                to=["test@example.com"],
                subject="Quarterly update",
                body="Latest status update",
                timestamp=_dt("2026-03-19T09:00:00"),
                labels=["inbox", "starred", "Projects"],
                is_starred=True,
                thread_id="thread_1",
            ),
            Email(
                id="email_archived",
                from_addr="bob@example.com",
                from_name="Bob",
                to=["test@example.com"],
                subject="Reference material",
                body="Archived reference",
                timestamp=_dt("2026-03-18T09:00:00"),
                labels=["Projects"],
                archived=True,
                thread_id="thread_2",
            ),
        ],
        drafts=[
            Draft(
                id="draft_1",
                subject="Follow-up draft",
                updated_at=_dt("2026-03-19T11:00:00"),
            )
        ],
        labels=[
            Label(id="label_inbox", name="inbox", system=True),
            Label(id="label_starred", name="starred", system=True),
            Label(id="label_drafts", name="drafts", system=True),
            Label(id="label_allmail", name="all mail", system=True),
            Label(id="label_projects", name="Projects"),
        ],
        settings=GmailSettings(id="settings"),
    )


def test_mailbox_counts_cover_names_and_label_ids() -> None:
    state = _build_state()

    counts = state.mailbox_counts()

    assert counts["inbox"] == 1
    assert counts["starred"] == 1
    assert counts["drafts"] == 1
    assert counts["all mail"] == 2
    assert counts["projects"] == 2
    assert counts["label_starred"] == 1
    assert counts["label_projects"] == 2
    assert counts["label_drafts"] == 1


def test_mailbox_counts_include_archived_threads() -> None:
    state = _build_state()

    counts = state.mailbox_counts()

    assert counts["archived"] == 1


def test_adding_inbox_label_clears_archived_state() -> None:
    state = _build_state()

    updated = state.apply_label("email_archived", "inbox", "add")

    assert updated.archived is False
    assert "inbox" in updated.labels
    assert state.mailbox_counts()["archived"] == 0
