from __future__ import annotations

import fnmatch
import shlex
from datetime import date, datetime, time, timedelta, timezone
from email.utils import getaddresses
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from .base import BaseEntity, BaseEnvState


def _query_tokens(query: str) -> list[str]:
    if not query:
        return []
    try:
        return shlex.split(query)
    except ValueError:
        return query.split()


def _query_term_groups(query: str) -> list[list[str]]:
    tokens = _query_tokens(query)
    if not tokens:
        return []

    groups: list[list[str]] = [[]]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.upper() == "OR":
            if groups[-1]:
                groups.append([])
            index += 1
            continue

        lowered = token.lower()

        if lowered.startswith("subject:") or lowered.startswith("from:"):
            parts = [token]
            lookahead = index + 1
            while lookahead < len(tokens):
                next_token = tokens[lookahead]
                if next_token.upper() == "OR" or ":" in next_token:
                    break
                parts.append(next_token)
                lookahead += 1
            groups[-1].append(" ".join(parts))
            index = lookahead
            continue

        groups[-1].append(token)
        index += 1

    groups = [group for group in groups if group]
    if len(groups) <= 1:
        return groups

    distributable_suffix: list[str] = []
    while len(groups[-1]) > 1:
        candidate = groups[-1][-1]
        if ":" not in candidate:
            break
        key = candidate.split(":", 1)[0].lower()
        if key not in {"has", "is", "label", "after", "before", "newer_than", "older_than"}:
            break
        distributable_suffix.insert(0, groups[-1].pop())

    if distributable_suffix:
        for group in groups:
            for token in distributable_suffix:
                if token not in group:
                    group.append(token)

    return groups


def _parse_query_date(value: str) -> datetime | None:
    normalized = value.strip().replace("/", "-")
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_relative_duration(value: str) -> timedelta | None:
    normalized = value.strip().lower()
    if len(normalized) < 2:
        return None
    amount = normalized[:-1]
    unit = normalized[-1]
    if not amount.isdigit():
        return None
    magnitude = int(amount)
    if unit == "d":
        return timedelta(days=magnitude)
    if unit == "w":
        return timedelta(weeks=magnitude)
    if unit == "m":
        return timedelta(days=30 * magnitude)
    if unit == "y":
        return timedelta(days=365 * magnitude)
    return None


def _canonicalize_recipient(value: str) -> str:
    trimmed = value.strip()
    if "@" in trimmed:
        return trimmed.lower()
    return trimmed


def _normalize_recipient_list(values: Any) -> list[str]:
    if values is None:
        return []

    raw_values = [values] if isinstance(values, str) else [str(value) for value in values]
    parsed = [
        _canonicalize_recipient(addr)
        for _, addr in getaddresses(raw_values)
        if addr.strip()
    ]
    if parsed:
        return parsed

    return [
        _canonicalize_recipient(value)
        for value in raw_values
        if value.strip()
    ]


class Attachment(BaseEntity):
    filename: str
    content_type: str
    size_bytes: int
    kind: str = "file"


class Email(BaseEntity):
    from_addr: str
    from_name: str
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    timestamp: datetime
    is_read: bool = False
    is_starred: bool = False
    labels: list[str] = Field(default_factory=lambda: ["inbox"])
    thread_id: str
    in_reply_to: str | None = None
    forwarded_from_id: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    archived: bool = False
    deleted: bool = False
    category: str = "primary"
    pre_delete_labels: list[str] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def _normalize_recipients(cls, value: Any) -> list[str]:
        return _normalize_recipient_list(value)

    @property
    def snippet(self) -> str:
        return " ".join(self.body.split())[:140]


class Draft(BaseEntity):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    attachments: list[Attachment] = Field(default_factory=list)
    thread_id: str | None = None
    in_reply_to: str | None = None
    updated_at: datetime

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def _normalize_recipients(cls, value: Any) -> list[str]:
        return _normalize_recipient_list(value)


class Contact(BaseEntity):
    name: str
    email: str
    company: str | None = None
    note: str | None = None
    is_vip: bool = False
    is_starred: bool = False
    source: str = "seeded"
    last_contacted_at: datetime | None = None


class Label(BaseEntity):
    name: str
    color: str = "#5f6368"
    system: bool = False
    show_in_label_list: str = "show"
    show_in_message_list: str = "show"
    show_in_imap: bool = True


class FilterRule(BaseEntity):
    name: str
    query: str = ""
    from_addresses: list[str] = Field(default_factory=list)
    subject_keywords: list[str] = Field(default_factory=list)
    label_requirements: list[str] = Field(default_factory=list)
    has_attachment: bool | None = None
    add_labels: list[str] = Field(default_factory=list)
    archive: bool = False
    mark_read: bool = False
    forward_to: str | None = None
    star: bool = False
    never_spam: bool = False

    def matches_email(self, email: Email) -> bool:
        if self.from_addresses:
            sender = email.from_addr.lower()
            if not any(fnmatch.fnmatch(sender, pattern.lower()) for pattern in self.from_addresses):
                return False
        if self.subject_keywords:
            lowered_subject = email.subject.lower()
            if not all(keyword.lower() in lowered_subject for keyword in self.subject_keywords):
                return False
        if self.label_requirements:
            labels = {label.lower() for label in email.labels}
            if not all(label.lower() in labels for label in self.label_requirements):
                return False
        if self.has_attachment is not None and bool(email.attachments) != self.has_attachment:
            return False
        return True


class GmailSettings(BaseEntity):
    signature: str = ""
    forwarding_address: str | None = None
    display_density: str = "comfortable"
    vacation_responder_enabled: bool = False
    vacation_responder_message: str = ""
    auto_advance: str = "newer"
    language: str = "English (US)"
    input_tools_enabled: bool = True
    right_to_left: bool = False
    max_page_size: int = 50
    undo_send_seconds: int = 5
    default_reply_behavior: str = "reply"
    hover_actions_enabled: bool = True
    send_and_archive: bool = False
    default_text_style: str = "Sans Serif"


class GmailState(BaseEnvState):
    DIFF_DIFFABLE_SINGLETONS: ClassVar[tuple[str, ...]] = ("settings",)

    owner_name: str
    owner_email: str
    emails: list[Email] = Field(default_factory=list)
    drafts: list[Draft] = Field(default_factory=list)
    sent: list[Email] = Field(default_factory=list)
    deleted: list[Email] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)
    settings: GmailSettings

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def all_mail(self) -> list[Email]:
        return sorted(self.emails + self.sent + self.deleted, key=lambda email: email.timestamp, reverse=True)

    def inbox(self) -> list[Email]:
        return self.list_emails(label="inbox")

    def get_email(self, email_id: str) -> Email | None:
        for collection in (self.emails, self.sent, self.deleted):
            for email in collection:
                if email.id == email_id:
                    return email
        return None

    def get_thread(self, thread_id: str) -> list[Email]:
        emails = [email for email in self.all_mail() if email.thread_id == thread_id]
        return sorted(emails, key=lambda email: email.timestamp)

    def get_contact(self, contact_id: str) -> Contact | None:
        return next((contact for contact in self.contacts if contact.id == contact_id), None)

    def list_emails(self, label: str | None = None, q: str | None = None) -> list[Email]:
        label = label or "inbox"
        if label == "sent":
            items = list(self.sent)
        elif label in {"trash", "deleted"}:
            items = list(self.deleted)
        else:
            items = [email for email in self.emails if not email.deleted]
            if label == "archived":
                items = [email for email in items if email.archived]
            elif label != "all":
                items = [email for email in items if label in email.labels]
        if q:
            items = [email for email in items if self._email_matches_query(email, q)]
        return sorted(items, key=lambda email: email.timestamp, reverse=True)

    def search(self, query: str) -> list[Email]:
        items = [email for email in self.emails + self.sent if not email.deleted]
        return sorted(
            [email for email in items if self._email_matches_query(email, query)],
            key=lambda email: email.timestamp,
            reverse=True,
        )

    def count_unread(self, label: str = "inbox") -> int:
        return sum(1 for email in self.list_emails(label=label) if not email.is_read)

    def mailbox_counts(self) -> dict[str, int]:
        labels_by_name = {label.name.lower(): label for label in self.labels}
        counts: dict[str, int] = {
            "archived": len(self.list_emails(label="archived")),
            "unread_inbox": self.count_unread("inbox"),
        }

        for label in self.labels:
            counts.setdefault(label.name.lower(), 0)
            counts.setdefault(label.id, 0)

        starred_count = 0
        for email in self.emails:
            if email.deleted:
                continue
            if email.is_starred:
                starred_count += 1
            for label_name in email.labels:
                normalized = label_name.lower()
                counts[normalized] = counts.get(normalized, 0) + 1
                label = labels_by_name.get(normalized)
                if label is not None:
                    counts[label.id] = counts.get(label.id, 0) + 1
        counts["starred"] = starred_count

        sent_count = len(self.sent)
        draft_count = len(self.drafts)
        trash_count = len(self.deleted)
        all_mail_count = len(self.emails) + sent_count

        special_counts = {
            "sent": sent_count,
            "drafts": draft_count,
            "trash": trash_count,
            "all mail": all_mail_count,
        }
        for name, value in special_counts.items():
            counts[name] = value
            label = labels_by_name.get(name)
            if label is not None:
                counts[label.id] = value

        return counts

    def ensure_label(
        self,
        label_name: str,
        color: str = "#1a73e8",
        system: bool = False,
        show_in_label_list: str = "show",
        show_in_message_list: str = "show",
        show_in_imap: bool = True,
    ) -> Label:
        existing = next((label for label in self.labels if label.name.lower() == label_name.lower()), None)
        if existing is not None:
            return existing
        label = Label(
            id=f"label_{len(self.labels) + 1}",
            name=label_name,
            color=color,
            system=system,
            show_in_label_list=show_in_label_list,
            show_in_message_list=show_in_message_list,
            show_in_imap=show_in_imap,
        )
        self.labels.append(label)
        self.touch()
        return label

    def update_label(
        self,
        label_id: str,
        *,
        name: str | None = None,
        show_in_label_list: str | None = None,
        show_in_message_list: str | None = None,
        show_in_imap: bool | None = None,
    ) -> Label:
        label = next((item for item in self.labels if item.id == label_id), None)
        if label is None:
            raise KeyError(f"Unknown label id: {label_id}")
        if label.system and name and name != label.name:
            raise ValueError(f"System labels cannot be renamed: {label.name}")

        if name is not None and name != label.name:
            conflicting = next(
                (item for item in self.labels if item.id != label_id and item.name.lower() == name.lower()),
                None,
            )
            if conflicting is not None:
                raise ValueError(f"Label already exists: {name}")
            old_name = label.name
            label.name = name
            for email in self.emails + self.sent + self.deleted:
                email.labels = [name if existing == old_name else existing for existing in email.labels]
            for rule in self.filters:
                rule.add_labels = [name if existing == old_name else existing for existing in rule.add_labels]
                rule.label_requirements = [
                    name if existing == old_name else existing for existing in rule.label_requirements
                ]
        if show_in_label_list is not None:
            label.show_in_label_list = show_in_label_list
        if show_in_message_list is not None:
            label.show_in_message_list = show_in_message_list
        if show_in_imap is not None:
            label.show_in_imap = show_in_imap
        self.touch()
        return label

    def remove_label(self, label_id: str) -> Label:
        for index, label in enumerate(self.labels):
            if label.id != label_id:
                continue
            if label.system:
                raise ValueError(f"System labels cannot be deleted: {label.name}")
            removed = self.labels.pop(index)
            for email in self.emails + self.sent + self.deleted:
                email.labels = [existing for existing in email.labels if existing != removed.name]
            for rule in self.filters:
                rule.add_labels = [existing for existing in rule.add_labels if existing != removed.name]
                rule.label_requirements = [
                    existing for existing in rule.label_requirements if existing != removed.name
                ]
            self.touch()
            return removed
        raise KeyError(f"Unknown label id: {label_id}")

    def mark_read(self, email_id: str, is_read: bool = True) -> Email:
        email = self._require_email(email_id)
        email.is_read = is_read
        self.touch()
        return email

    def toggle_star(self, email_id: str, is_starred: bool | None = None) -> Email:
        email = self._require_email(email_id)
        email.is_starred = (not email.is_starred) if is_starred is None else is_starred
        if email.is_starred and "starred" not in email.labels:
            email.labels.append("starred")
        if not email.is_starred and "starred" in email.labels:
            email.labels = [label for label in email.labels if label != "starred"]
        self.touch()
        return email

    def apply_label(self, email_id: str, label_name: str, action: str = "add") -> Email:
        email = self._require_email(email_id)
        if action == "add":
            self.ensure_label(label_name)
            if label_name not in email.labels:
                email.labels.append(label_name)
            if label_name.lower() == "inbox":
                email.archived = False
        elif action == "remove":
            email.labels = [label for label in email.labels if label != label_name]
        else:
            raise ValueError(f"Unknown label action: {action}")
        self.touch()
        return email

    def archive_email(self, email_id: str) -> Email:
        email = self._require_email(email_id)
        email.archived = True
        email.labels = [label for label in email.labels if label != "inbox"]
        self.touch()
        return email

    def delete_email(self, email_id: str) -> Email:
        # If already in trash, permanently remove it.
        for index, email in enumerate(self.deleted):
            if email.id == email_id:
                removed = self.deleted.pop(index)
                self.touch()
                return removed
        # Otherwise, move to trash from inbox/sent.
        for collection in (self.emails, self.sent):
            for index, email in enumerate(collection):
                if email.id == email_id:
                    removed = collection.pop(index)
                    removed.pre_delete_labels = list(removed.labels)
                    removed.deleted = True
                    removed.archived = False
                    removed.labels = ["trash"]
                    self.deleted.append(removed)
                    self.touch()
                    return removed
        raise KeyError(f"Unknown email id: {email_id}")

    def restore_email(self, email_id: str) -> Email:
        """Move an email from trash back to inbox."""
        for index, email in enumerate(self.deleted):
            if email.id == email_id:
                restored = self.deleted.pop(index)
                restored.deleted = False
                restored.archived = False
                restored.labels = list(restored.pre_delete_labels) if restored.pre_delete_labels else ["inbox"]
                restored.pre_delete_labels = None
                self.emails.append(restored)
                self.touch()
                return restored
        raise KeyError(f"Email not in trash: {email_id}")

    def send_email(
        self,
        *,
        subject: str,
        body: str,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
        forwarded_from_id: str | None = None,
        from_name: str | None = None,
        from_addr: str | None = None,
        timestamp: datetime | None = None,
    ) -> Email:
        if in_reply_to and thread_id is None:
            original = self._require_email(in_reply_to)
            thread_id = original.thread_id
        thread_id = thread_id or f"thread_sent_{len(self.sent) + 1}"
        email = Email(
            id=f"sent_{len(self.sent) + 1}",
            from_addr=from_addr or self.owner_email,
            from_name=from_name or self.owner_name,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            body=body,
            timestamp=timestamp or datetime.now(timezone.utc),
            is_read=True,
            labels=["sent"],
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            attachments=attachments or [],
            category="sent",
            forwarded_from_id=forwarded_from_id,
        )
        self.sent.append(email)
        self.touch()
        return email

    def forward_email(
        self,
        email_id: str,
        *,
        to: list[str],
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> Email:
        original = self._require_email(email_id)
        subject = original.subject if original.subject.lower().startswith("fwd:") else f"Fwd: {original.subject}"
        forward_body = body.strip()
        if forward_body:
            forward_body += "\n\n"
        forward_body += f"Forwarded message from {original.from_name} <{original.from_addr}>:\n\n{original.body}"
        return self.send_email(
            subject=subject,
            body=forward_body,
            to=to,
            cc=cc,
            bcc=bcc,
            attachments=list(original.attachments),
            forwarded_from_id=original.id,
        )

    def create_filter(self, rule: FilterRule) -> FilterRule:
        self.filters.append(rule)
        self.touch()
        return rule

    def remove_filter(self, filter_id: str) -> FilterRule:
        for index, rule in enumerate(self.filters):
            if rule.id == filter_id:
                removed = self.filters.pop(index)
                self.touch()
                return removed
        raise KeyError(f"Unknown filter id: {filter_id}")

    def add_contact(self, contact: Contact) -> Contact:
        existing = next((item for item in self.contacts if item.email.lower() == contact.email.lower()), None)
        if existing is not None:
            existing.name = contact.name
            existing.company = contact.company
            existing.note = contact.note
            existing.is_vip = contact.is_vip
            existing.is_starred = contact.is_starred
            existing.last_contacted_at = contact.last_contacted_at
            self.touch()
            return existing
        self.contacts.append(contact)
        self.touch()
        return contact

    def update_contact(
        self,
        contact_id: str,
        *,
        name: str | None = None,
        email: str | None = None,
        company: str | None = None,
        note: str | None = None,
        is_vip: bool | None = None,
        is_starred: bool | None = None,
        last_contacted_at: datetime | None = None,
    ) -> Contact:
        contact = self.get_contact(contact_id)
        if contact is None:
            raise KeyError(f"Unknown contact id: {contact_id}")
        if email is not None and email.lower() != contact.email.lower():
            existing = next(
                (item for item in self.contacts if item.id != contact_id and item.email.lower() == email.lower()),
                None,
            )
            if existing is not None:
                raise ValueError(f"Contact already exists: {email}")
            contact.email = email
        if name is not None:
            contact.name = name
        if company is not None:
            contact.company = company
        if note is not None:
            contact.note = note
        if is_vip is not None:
            contact.is_vip = is_vip
        if is_starred is not None:
            contact.is_starred = is_starred
        if last_contacted_at is not None:
            contact.last_contacted_at = last_contacted_at
        self.touch()
        return contact

    def remove_contact(self, contact_id: str) -> Contact:
        for index, contact in enumerate(self.contacts):
            if contact.id == contact_id:
                removed = self.contacts.pop(index)
                self.touch()
                return removed
        raise KeyError(f"Unknown contact id: {contact_id}")

    def state_snapshot(self) -> dict[str, Any]:
        """Capture all mutable state dimensions for collateral-damage detection.

        Called once after seeding to record the baseline.  At evaluation time
        the evaluator diffs the current state against this snapshot and reports
        any unintended mutations as analytics-only collateral metrics.
        """
        email_flags: dict[str, dict[str, Any]] = {}
        for email in self.emails:
            email_flags[email.id] = {
                "is_read": email.is_read,
                "is_starred": email.is_starred,
                "labels": sorted(email.labels),
                "archived": email.archived,
            }

        contact_snap: dict[str, dict[str, Any]] = {}
        for contact in self.contacts:
            contact_snap[contact.id] = {
                "name": contact.name,
                "email": contact.email,
                "company": contact.company,
                "note": contact.note,
                "is_vip": contact.is_vip,
                "is_starred": contact.is_starred,
            }

        label_snap: dict[str, dict[str, Any]] = {}
        for label in self.labels:
            label_snap[label.id] = {
                "name": label.name,
                "color": label.color,
                "show_in_label_list": label.show_in_label_list,
                "show_in_message_list": label.show_in_message_list,
                "show_in_imap": label.show_in_imap,
            }

        filter_snap: dict[str, dict[str, Any]] = {}
        for rule in self.filters:
            filter_snap[rule.id] = {
                "name": rule.name,
                "from_addresses": sorted(rule.from_addresses),
                "subject_keywords": sorted(rule.subject_keywords),
                "add_labels": sorted(rule.add_labels),
                "archive": rule.archive,
                "mark_read": rule.mark_read,
                "forward_to": rule.forward_to,
                "star": rule.star,
            }

        settings = self.settings.model_dump(mode="json")
        settings.pop("id", None)

        return {
            "email_ids": sorted(email_flags.keys()),
            "email_flags": email_flags,
            "sent_count": len(self.sent),
            "deleted_ids": sorted(e.id for e in self.deleted),
            "draft_count": len(self.drafts),
            "contacts": contact_snap,
            "labels": label_snap,
            "filters": filter_snap,
            "settings": settings,
        }

    def session_summary(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "task_id": self.task_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "counts": {
                "inbox": len(self.list_emails(label="inbox")),
                "sent": len(self.sent),
                "trash": len(self.deleted),
                "contacts": len(self.contacts),
                "labels": len(self.labels),
                "filters": len(self.filters),
                "unread_inbox": self.count_unread("inbox"),
            },
        }

    def _require_email(self, email_id: str) -> Email:
        email = self.get_email(email_id)
        if email is None:
            raise KeyError(f"Unknown email id: {email_id}")
        return email

    def _email_matches_query(self, email: Email, query: str) -> bool:
        term_groups = _query_term_groups(query)
        if not term_groups:
            return True

        haystacks = [
            email.subject.lower(),
            email.body.lower(),
            email.from_name.lower(),
            email.from_addr.lower(),
            " ".join(email.to).lower(),
        ]
        labels = {label.lower() for label in email.labels}
        reference_time = max(
            [self.created_at, *(item.timestamp for item in self.emails + self.sent + self.deleted)],
            key=lambda item: item.timestamp() if isinstance(item, datetime) else 0.0,
        )

        for terms in term_groups:
            matches_group = True
            for term in terms:
                lowered = term.lower()
                if ":" in lowered:
                    key, value = lowered.split(":", 1)
                    if key == "from":
                        if value.startswith("@"):
                            if not email.from_addr.lower().endswith(value):
                                matches_group = False
                                break
                        elif value not in email.from_addr.lower() and value not in email.from_name.lower():
                            matches_group = False
                            break
                    elif key == "to":
                        if not any(value in addr.lower() for addr in email.to + email.cc + email.bcc):
                            matches_group = False
                            break
                    elif key == "subject":
                        if value not in email.subject.lower():
                            matches_group = False
                            break
                    elif key == "label":
                        if value not in labels:
                            matches_group = False
                            break
                    elif key == "has" and value == "attachment":
                        if not email.attachments:
                            matches_group = False
                            break
                    elif key == "after":
                        cutoff = _parse_query_date(value)
                        if cutoff is None or email.timestamp < cutoff:
                            matches_group = False
                            break
                    elif key == "before":
                        cutoff = _parse_query_date(value)
                        if cutoff is None or email.timestamp >= cutoff:
                            matches_group = False
                            break
                    elif key == "newer_than":
                        duration = _parse_relative_duration(value)
                        if duration is None or email.timestamp < reference_time - duration:
                            matches_group = False
                            break
                    elif key == "older_than":
                        duration = _parse_relative_duration(value)
                        if duration is None or email.timestamp > reference_time - duration:
                            matches_group = False
                            break
                    elif key == "is" and value == "unread":
                        if email.is_read:
                            matches_group = False
                            break
                    elif key == "is" and value == "read":
                        if not email.is_read:
                            matches_group = False
                            break
                    elif key == "is" and value == "starred":
                        if not email.is_starred:
                            matches_group = False
                            break
                    elif lowered not in " ".join(haystacks):
                        matches_group = False
                        break
                elif not any(lowered in haystack for haystack in haystacks):
                    matches_group = False
                    break

            if matches_group:
                return True

        return False
