"""BreakingWeb task evaluator — delegates to eval_core.

All evaluation logic lives in ``breakingweb.eval_core``. This module
preserves the public ``evaluate()`` signature and the Gmail-specific
``_compute_collateral`` helper for backward compatibility.
"""

from __future__ import annotations

from typing import Any

from breakingweb.eval_core import evaluate as _evaluate


def evaluate(
    task: Any,
    *,
    server_state: Any,
    targets: dict[str, Any],
    trajectory: list[dict[str, Any]],
) -> dict[str, Any]:
    return _evaluate(task, server_state, targets, trajectory)


def _compute_collateral(initial: dict[str, Any] | None, state: Any) -> dict[str, Any]:
    """Gmail-specific collateral diff (analytics only, no score impact).

    Retained for test backward compatibility. New envs should implement
    ``compute_collateral(initial)`` on their state class instead.
    """
    if initial is None or not hasattr(state, "state_snapshot"):
        return {}

    current = state.state_snapshot()
    report: dict[str, Any] = {}

    modified_emails: list[dict[str, Any]] = []
    init_flags = initial.get("email_flags", {})
    curr_flags = current.get("email_flags", {})
    for eid, init_f in init_flags.items():
        curr_f = curr_flags.get(eid)
        if curr_f is None:
            continue
        diffs = {k: {"before": init_f[k], "after": curr_f[k]}
                 for k in init_f if init_f[k] != curr_f.get(k)}
        if diffs:
            modified_emails.append({"email_id": eid, "changes": diffs})
    if modified_emails:
        report["emails_modified"] = modified_emails

    init_deleted = set(initial.get("deleted_ids", []))
    curr_deleted = set(current.get("deleted_ids", []))
    newly_deleted = curr_deleted - init_deleted
    if newly_deleted:
        report["emails_deleted"] = sorted(newly_deleted)

    sent_delta = current.get("sent_count", 0) - initial.get("sent_count", 0)
    if sent_delta > 0:
        report["emails_sent"] = sent_delta

    draft_delta = current.get("draft_count", 0) - initial.get("draft_count", 0)
    if draft_delta != 0:
        report["drafts_delta"] = draft_delta

    init_contacts = initial.get("contacts", {})
    curr_contacts = current.get("contacts", {})
    contacts_added = sorted(set(curr_contacts) - set(init_contacts))
    contacts_removed = sorted(set(init_contacts) - set(curr_contacts))
    contacts_modified: list[dict[str, Any]] = []
    for cid in set(init_contacts) & set(curr_contacts):
        diffs = {k: {"before": init_contacts[cid][k], "after": curr_contacts[cid][k]}
                 for k in init_contacts[cid]
                 if init_contacts[cid][k] != curr_contacts[cid].get(k)}
        if diffs:
            contacts_modified.append({"contact_id": cid, "changes": diffs})
    if contacts_added:
        report["contacts_added"] = contacts_added
    if contacts_removed:
        report["contacts_removed"] = contacts_removed
    if contacts_modified:
        report["contacts_modified"] = contacts_modified

    init_labels = initial.get("labels", {})
    curr_labels = current.get("labels", {})
    labels_added = sorted(set(curr_labels) - set(init_labels))
    labels_removed = sorted(set(init_labels) - set(curr_labels))
    labels_modified: list[dict[str, Any]] = []
    for lid in set(init_labels) & set(curr_labels):
        diffs = {k: {"before": init_labels[lid][k], "after": curr_labels[lid][k]}
                 for k in init_labels[lid]
                 if init_labels[lid][k] != curr_labels[lid].get(k)}
        if diffs:
            labels_modified.append({"label_id": lid, "changes": diffs})
    if labels_added:
        report["labels_added"] = labels_added
    if labels_removed:
        report["labels_removed"] = labels_removed
    if labels_modified:
        report["labels_modified"] = labels_modified

    init_filters = initial.get("filters", {})
    curr_filters = current.get("filters", {})
    filters_added = sorted(set(curr_filters) - set(init_filters))
    filters_removed = sorted(set(init_filters) - set(curr_filters))
    if filters_added:
        report["filters_added"] = filters_added
    if filters_removed:
        report["filters_removed"] = filters_removed

    init_settings = initial.get("settings", {})
    curr_settings = current.get("settings", {})
    settings_changed = {k: {"before": init_settings[k], "after": curr_settings[k]}
                        for k in init_settings
                        if init_settings.get(k) != curr_settings.get(k)}
    if settings_changed:
        report["settings_changed"] = settings_changed

    return report
