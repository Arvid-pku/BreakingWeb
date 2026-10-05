"""Tests for the `plant_wrong_answer` mirror_target_id upgrade.

The brief asks: "Make wrong answers plausible from every angle — same
shape as the right answer, similar metadata (sender, timestamp, format),
and no single property that immediately disqualifies them."

`mirror_target_id` (and the convenience `mirror_subject_contains`) makes
the planted email inherit the target's `from_name`, `from_addr`, `to`, and
`labels` automatically — variant authors don't have to hand-copy every
field.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from breakingweb.injector.seed import apply_seed_injection


def _make_state(emails: list) -> SimpleNamespace:
    return SimpleNamespace(emails=list(emails), resolved_targets={})


def _email(**kwargs):
    """Minimal duck-typed Email substitute is not enough — _plant_wrong_answer
    instantiates breakingweb.backend.models.gmail.Email. We need the real
    model for the test."""
    from breakingweb.backend.models.gmail import Email
    defaults = {
        "id": kwargs.get("id", "e_target"),
        "thread_id": kwargs.get("thread_id", "thread_target"),
        "from_name": kwargs.get("from_name", "Target Sender"),
        "from_addr": kwargs.get("from_addr", "target.sender@thornton.com"),
        "to": kwargs.get("to", ["me@thornton.com"]),
        "subject": kwargs.get("subject", "Authoritative answer"),
        "body": kwargs.get("body", "real body"),
        "timestamp": kwargs.get("timestamp", datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)),
        "labels": kwargs.get("labels", ["inbox", "starred"]),
        "is_read": False,
    }
    return Email(**defaults)


def test_mirror_target_id_inherits_metadata() -> None:
    target = _email(id="e_target", from_name="Procurement Team", from_addr="proc@thornton.com",
                    labels=["inbox", "procurement"])
    state = _make_state([target])
    apply_seed_injection(state, {
        "action": "plant_wrong_answer",
        "mirror_target_id": "e_target",
        "subject": "CORRECTION: PO numbers reassigned",
        "body": "All PO numbers from yesterday are now invalidated.",
    })
    # Newest email is the planted one.
    planted = state.emails[0]
    assert planted.subject == "CORRECTION: PO numbers reassigned"
    # Metadata mirrored from target.
    assert planted.from_name == "Procurement Team"
    assert planted.from_addr == "proc@thornton.com"
    assert planted.labels == ["inbox", "procurement"]
    # Defaults like is_starred=True still apply.
    assert planted.is_starred is True


def test_mirror_subject_contains_finds_target() -> None:
    a = _email(id="ea", subject="random meeting", from_name="A")
    b = _email(id="eb", subject="Q4 revenue numbers — final", from_name="Procurement Team",
               from_addr="proc@thornton.com")
    state = _make_state([a, b])
    apply_seed_injection(state, {
        "action": "plant_wrong_answer",
        "mirror_subject_contains": "q4 revenue",
        "subject": "URGENT: Q4 revenue numbers — corrected",
        "body": "Use these numbers instead.",
    })
    planted = state.emails[0]
    assert planted.from_name == "Procurement Team"
    assert planted.from_addr == "proc@thornton.com"


def test_explicit_overrides_still_win() -> None:
    target = _email(id="e_target", from_name="Real Sender", from_addr="real@thornton.com")
    state = _make_state([target])
    apply_seed_injection(state, {
        "action": "plant_wrong_answer",
        "mirror_target_id": "e_target",
        "from_name": "Different Sender",   # explicit override
        "from": "diff@thornton.com",
        "subject": "Wrong",
        "body": "Wrong",
    })
    planted = state.emails[0]
    assert planted.from_name == "Different Sender"
    assert planted.from_addr == "diff@thornton.com"
