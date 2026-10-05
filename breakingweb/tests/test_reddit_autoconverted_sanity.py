"""Sanity tests for auto-converted Reddit canonical_diffs.

The 48 Reddit tasks auto-converted from legacy eval.checks into
constraint-only canonical_diff blocks don't have hand-written
happy-path tests. This file locks in two invariants per task:

1. The canonical_diff loads cleanly via the registry.
2. Do-nothing trajectory doesn't trivially score 1.0 (the task genuinely
   requires agent action).

Tasks that legitimately have no action required — or whose constraints
all trivially hold on the initial state — are expected to score 1.0 and
are listed in ``NO_ACTION_REQUIRED_TASKS`` below.
"""

from __future__ import annotations

import pytest

from breakingweb.backend.state import SessionManager
from breakingweb.eval_core import compute_diff, match_diff
from breakingweb.tasks._registry import load_all_tasks


# Tasks whose happy-path is already hand-written in test_reddit_<id>_canonical_diff.py.
# The sanity sweep skips these to avoid duplicate coverage.
_HAND_WRITTEN = {
    "reddit_upvote_post",
    "reddit_subscribe_subreddit",
    "reddit_create_text_post",
    "reddit_delete_own_comment",
    "reddit_compose_message",
    "reddit_clear_notifications",
    "reddit_mark_messages_read",
    "reddit_save_from_feed",
    "reddit_unsubscribe",
    "reddit_hide_post",
    "reddit_downvote_comment",
    "reddit_edit_own_post",
    "reddit_reply_to_message",
    "reddit_switch_dark_mode",
    "reddit_update_settings",
    "reddit_verify_inbox_clean",
    "reddit_engage_user_content",
    "reddit_post_with_flair",
    "reddit_save_comments",
    "reddit_vote_spree",
    "reddit_curate_saved",
    "reddit_manage_subscriptions",
    "reddit_reply_nested_comment",
    "reddit_follow_notification",
    "reddit_post_and_comment",
    "reddit_privacy_overhaul",
    "reddit_search_and_message",
    "reddit_create_and_engage",
    "reddit_edit_then_comment",
    "reddit_message_management",
}


def _auto_converted_reddit_tasks() -> list[str]:
    return sorted(
        tid for tid, t in load_all_tasks().items()
        if t.env_id == "reddit" and t.canonical_diff is not None and tid not in _HAND_WRITTEN
    )


@pytest.mark.parametrize("task_id", _auto_converted_reddit_tasks())
def test_do_nothing_does_not_trivially_pass(task_id: str) -> None:
    """Do-nothing should not score 1.0 — the task genuinely requires action.

    Tolerates partial credit (trivially-true constraints on initial state)
    but asserts the overall score falls short of the full-pass threshold,
    confirming the canonical_diff actually grades agent work.
    """
    sm = SessionManager()
    sid, targets, _ = sm.create_session(env_id="reddit", task_id=task_id, seed=42)
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)

    task = load_all_tasks()[task_id]
    report = match_diff(
        compute_diff(initial, state), task.canonical_diff,
        targets=dict(targets), initial=initial, final=state,
    )
    assert report.score < 1.0, (
        f"{task_id}: do-nothing trivially scored 1.0 — canonical_diff's "
        f"constraints all pass on the initial state. Revisit the "
        f"authoring to ensure constraints encode agent action, not just "
        f"initial conditions."
    )
