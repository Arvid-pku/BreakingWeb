"""AXTree accessibility audit — verifies the SPA exposes task-critical state.

If the agent acts from the AXTree, all task-critical information must be
accessible through ARIA labels, semantic elements, visible text, or
element attributes.  This test checks the React source code to confirm.

Categories checked:
  1. Star state — Star/Unstar toggle visible in button labels
  2. Read/unread state — Unread badge or ARIA indicator on email rows
  3. Label state — LabelChip components on email rows
  4. Settings fields — All GmailSettings fields have form controls
  5. Contact fields — Name, email, company, note, VIP visible in table
  6. Filter fields — All FilterRule fields in Settings page
  7. Notifications — Toast/notification area for action feedback
  8. Sidebar counts — Inbox/Sent/Trash/Starred counts visible
  9. Thread view — Reply/Forward/Star/Archive/Delete/Label actions
 10. Error handling — SPA catches API errors to show feedback

Each check reads the React TSX source directly (no browser needed).
"""

from __future__ import annotations

from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "environments" / "gmail" / "src"


def _read(relpath: str) -> str:
    return (SRC / relpath).read_text()


def _src_contains(relpath: str, *needles: str) -> list[str]:
    """Return which needles are NOT found in the file."""
    content = _read(relpath)
    return [n for n in needles if n not in content]


# ── 1. Star state ────────────────────────────────────────────────────────

class TestStarStateObservable:
    def test_email_row_has_star_toggle_aria_label(self):
        content = _read("components/EmailRow.tsx")
        assert "Unstar" in content and "Star " in content, (
            "EmailRow must show Star/Unstar in button aria-label"
        )

    def test_email_row_star_uses_is_starred(self):
        content = _read("components/EmailRow.tsx")
        assert "is_starred" in content, "EmailRow must read is_starred"

    def test_thread_has_star_toggle(self):
        content = _read("pages/Thread.tsx")
        assert "is_starred" in content or "Star this thread" in content


# ── 2. Read/unread state ─────────────────────────────────────────────────

class TestReadUnreadObservable:
    def test_email_row_has_unread_indicator(self):
        content = _read("components/EmailRow.tsx")
        # Codex added: aria-label includes "Unread/Read thread from..."
        # and visible "Unread" badge
        has_aria = "Unread" in content and "aria-label" in content
        has_badge = "Unread" in content and "gmail-email-row__status" in content
        assert has_aria or has_badge, (
            "EmailRow must expose read/unread state via ARIA label or visible badge"
        )

    def test_email_row_bold_for_unread(self):
        content = _read("components/EmailRow.tsx")
        assert "is_read" in content, (
            "EmailRow must use is_read to style unread emails differently"
        )


# ── 3. Label state ───────────────────────────────────────────────────────

class TestLabelStateObservable:
    def test_email_row_shows_label_chips(self):
        content = _read("components/EmailRow.tsx")
        assert "LabelChip" in content, (
            "EmailRow must render LabelChip components for email labels"
        )

    def test_label_chip_has_aria_label(self):
        content = _read("components/LabelChip.tsx")
        assert "Label:" in content, (
            "LabelChip must include label name in aria-label"
        )


# ── 4. Settings fields ──────────────────────────────────────────────────

class TestSettingsFieldsObservable:
    REQUIRED_FIELDS = [
        "undo_send", "default_reply", "send_and_archive",
        "max_page_size", "signature", "vacation_responder",
        "display_density", "forwarding_address",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_settings_field_in_page(self, field):
        content = _read("pages/Settings.tsx")
        assert field in content or field.replace("_", " ") in content.lower(), (
            f"Settings page must expose {field} with a form control"
        )


# ── 5. Contact fields ───────────────────────────────────────────────────

class TestContactFieldsObservable:
    REQUIRED_FIELDS = ["name", "email", "company", "note", "is_vip"]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_contact_field_in_labels_page(self, field):
        content = _read("pages/Labels.tsx")
        assert field in content, f"Labels/Contacts page must show Contact.{field}"

    def test_contact_edit_button_exists(self):
        content = _read("pages/Labels.tsx")
        assert "Edit contact" in content, (
            "Contacts table must have Edit button for each contact"
        )

    def test_contact_star_toggle_exists(self):
        content = _read("pages/Labels.tsx")
        assert "star" in content.lower() and "contact" in content.lower()


# ── 6. Filter fields ────────────────────────────────────────────────────

class TestFilterFieldsObservable:
    REQUIRED_FIELDS = [
        "from_addresses", "subject_keywords", "add_labels",
        "archive", "forward_to",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_filter_field_in_settings(self, field):
        content = _read("pages/Settings.tsx")
        assert field in content, f"Settings page must show FilterRule.{field}"


# ── 7. Notification area ────────────────────────────────────────────────

class TestNotificationArea:
    def test_app_has_notification_system(self):
        # The notify function lives in Shell.tsx (the layout wrapper),
        # not App.tsx (the route definitions).
        content = _read("Shell.tsx")
        assert "notify" in content, "Shell must have a notify function"

    def test_notification_area_is_live_region(self):
        # The notification area must be an ARIA live region so the AXTree
        # picks up toast messages (e.g., "Reply sent", "Moved to trash").
        # The live region may be in App, Shell, or a shared component.
        all_src = ""
        for f in SRC.rglob("*.tsx"):
            all_src += f.read_text()
        has_live = "aria-live" in all_src or 'role="status"' in all_src or 'role="alert"' in all_src
        assert has_live, (
            "SPA must have an ARIA live region (aria-live or role='status') "
            "so BrowserGym's AXTree captures toast messages"
        )


# ── 8. Sidebar counts ───────────────────────────────────────────────────

class TestSidebarCounts:
    def test_sidebar_shows_inbox_count(self):
        content = _read("App.tsx") + _read("Shell.tsx")
        assert "Inbox" in content and "count" in content.lower()

    def test_sidebar_shows_sent_count(self):
        content = _read("App.tsx") + _read("Shell.tsx")
        assert "Sent" in content


# ── 9. Thread view actions ───────────────────────────────────────────────

class TestThreadViewActions:
    REQUIRED_ACTIONS = [
        "Reply to",
        "Forward",
        "Star this thread",
        "Archive this thread",
        "Delete this thread",
        "Apply label",
    ]

    @pytest.mark.parametrize("action", REQUIRED_ACTIONS)
    def test_thread_action_exists(self, action):
        # Reply button is in ThreadView.tsx component, other actions in Thread.tsx
        content = _read("pages/Thread.tsx") + _read("components/ThreadView.tsx")
        assert action in content, (
            f"Thread view must have '{action}' button/action"
        )


# ── 10. Error handling for verification primitive ────────────────────────

class TestErrorHandling:
    """Check whether the SPA catches and displays API errors.

    For backtracking/patience tests: if the API returns 503, the agent
    needs a signal. Currently the SPA has NO try/catch on send/forward,
    meaning the SPA silently stays on the current page. This is an
    implicit signal (no navigation = no success) but not explicit.

    For verification tests: silent fails return 200, so there's no
    error to catch. The signal must come from state contradiction
    (e.g., Sent count still 0 after "Reply sent" toast).
    """

    def test_inbox_page_handles_load_errors(self):
        missing = _src_contains("pages/Inbox.tsx", "catch", "error")
        assert not missing, (
            f"Inbox page must handle API errors: missing {missing}"
        )

    def test_compose_sends_without_error_handling(self):
        """Document: Compose has no try/catch on sendMessage.

        This means 503 errors cause the SPA to stay on the compose page
        with no error notification. The implicit signal is: still on
        /compose URL + no 'Message sent' toast + Sent count unchanged.
        """
        content = _read("pages/Compose.tsx")
        has_catch = "catch" in content or "try" in content
        # This is a documentation test, not a failure — the behavior
        # is intentional for the backtracking primitive.
        if not has_catch:
            # Verify the implicit signals ARE present
            assert "notify" in content, (
                "Compose must call notify on success so absence = failure signal"
            )
            assert "navigate" in content, (
                "Compose must navigate away on success so staying = failure signal"
            )

    def test_verification_has_sidebar_count_signal(self):
        """The key signal for verification: sidebar Sent count.

        After a silent-fail send, the toast says "Reply sent" but the
        sidebar Sent count stays 0. An agent with verification would
        check the count.
        """
        content = _read("App.tsx") + _read("Shell.tsx")
        assert "Sent" in content, "Sidebar must show Sent count"
