"""Regression guard for hazard Class 13 — compute_diff crashed on states
with primitive-valued list fields (e.g. ``AmazonState.wishlist: list[str]``).

Original bug: ``_collections_of`` fell through to ``dict(v)`` on each
element of a ``list[str]`` field and raised ``ValueError: dictionary
update sequence element #0 has length 1; 2 is required``.

Current behavior (after the eval_core refactor + opt-in primitive lists):
- compute_diff never raises on primitive-list fields.
- Fields NOT listed in a state's ``DIFF_DIFFABLE_PRIMITIVE_LISTS`` are
  silently dropped from the diff output (``recently_viewed``,
  ``search_history``).
- Fields listed in ``DIFF_DIFFABLE_PRIMITIVE_LISTS`` (e.g. ``wishlist`` on
  AmazonState) ARE diffable: each element becomes a synthetic entity with
  ``id == value``, so create/delete entries can express add/remove.

These tests guard the no-crash invariant for all primitive-list shapes
plus the documented opt-in/opt-out boundary.
"""

from __future__ import annotations

from breakingweb.backend.models.amazon import AmazonState
from breakingweb.backend.state import SessionManager
from breakingweb.eval_core import compute_diff, Create


def test_compute_diff_survives_wishlist_mutation():
    """No crash on a wishlist mutation; opt-in primitive list yields a Create."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="amazon", task_id="amazon_add_to_wishlist", seed=42
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    state.add_to_wishlist(targets["product_id"])

    # Must not raise (the original bug).
    diff = compute_diff(initial, state)

    # wishlist is in AmazonState.DIFF_DIFFABLE_PRIMITIVE_LISTS, so the new
    # element shows up as a Create entry with id == the product id.
    assert "wishlist" in AmazonState.DIFF_DIFFABLE_PRIMITIVE_LISTS, (
        "test premise: wishlist must remain opt-in to primitive-list diffing"
    )
    wishlist_creates = [
        e for e in diff if isinstance(e, Create) and e.entity == "wishlist"
    ]
    assert len(wishlist_creates) == 1, (
        f"expected exactly one wishlist Create, got {len(wishlist_creates)}"
    )
    assert wishlist_creates[0].entity_id == targets["product_id"]


def test_compute_diff_survives_recently_viewed_mutation():
    """Non-opt-in primitive lists are silently dropped from the diff."""
    sm = SessionManager()
    sid, _, _ = sm.create_session(
        env_id="amazon", task_id="amazon_add_to_wishlist", seed=42
    )
    initial = sm.get_initial_snapshot(sid)
    state = sm.get_state(sid)
    state.add_to_browsing_history(state.products[0].id)

    diff = compute_diff(initial, state)

    # recently_viewed and search_history are NOT in DIFF_DIFFABLE_PRIMITIVE_LISTS,
    # so mutations to them produce no diff entries.
    assert all(
        entry.entity not in ("recently_viewed", "search_history")
        for entry in diff
    )


def test_compute_diff_on_dict_snapshots_skips_non_optin_primitive_lists():
    """Same opt-in rules apply when initial/final are plain dicts (model_dump)."""
    sm = SessionManager()
    sid, _, _ = sm.create_session(
        env_id="amazon", task_id="amazon_add_to_wishlist", seed=42
    )
    initial = sm.get_initial_snapshot(sid).model_dump()
    # Mutate a NON-opt-in primitive list to confirm it's still dropped on dicts.
    final = {**initial, "search_history": list(initial.get("search_history") or []) + ["term_XYZ"]}

    # Must not raise.
    diff = compute_diff(initial, final)
    assert all(entry.entity != "search_history" for entry in diff)
