"""The immunization_record builder must emit admin_providers and window targets.
Plus session_start must appear on every session's targets.

Note: SessionManager.create_session returns ``(session_id, targets, seed)`` where
``targets`` is the flat resolved-targets dict, matching the convention used
throughout the codebase (see test_amazon_seed_stability.py). The plan's test
sketch wrote ``meta.get("targets", {})`` — we treat ``meta`` as the targets dict
directly so the assertions line up with the actual API.
"""

from breakingweb.backend.state import SessionManager


def test_immunization_record_emits_admin_providers():
    sm = SessionManager()
    sid, meta, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    targets = meta
    assert "admin_providers" in targets
    assert isinstance(targets["admin_providers"], dict)
    for imm_id in targets["due_imm_ids"]:
        assert imm_id in targets["admin_providers"], (
            f"admin_providers missing entry for due_imm_id {imm_id}"
        )
        assert len(targets["admin_providers"][imm_id]) >= 1, (
            f"admin_providers[{imm_id}] is empty — should have at least one provider id"
        )


def test_immunization_record_emits_window():
    sm = SessionManager()
    sid, meta, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    targets = meta
    assert "window_start" in targets
    assert "window_end" in targets
    assert isinstance(targets["window_start"], str)
    assert isinstance(targets["window_end"], str)


def test_session_start_in_targets():
    sm = SessionManager()
    sid, meta, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    targets = meta
    assert "session_start" in targets
    assert isinstance(targets["session_start"], str)


def test_existing_outputs_preserved():
    """Existing targets still present — no regression."""
    sm = SessionManager()
    sid, meta, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    targets = meta
    assert "due_imm_ids" in targets
    assert "completed_imm_ids" in targets
    assert "upcoming_ids" in targets
