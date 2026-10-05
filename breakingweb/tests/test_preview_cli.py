"""Unit tests for the preview CLI (Phase 0 — text-only mode)."""

from breakingweb.tasks.preview import represent_predicate, apply_canonical_diff


def test_represent_predicate_eq():
    assert represent_predicate({"eq": "scheduled"}) == "scheduled"


def test_represent_predicate_in_first():
    assert represent_predicate({"in": ["a", "b", "c"]}) == "a"


def test_represent_predicate_between_midpoint_numeric():
    assert represent_predicate({"between": [10, 20]}) == 15


def test_represent_predicate_between_date_fallback():
    # Non-numeric between: returns lo (midpoint semantically unclear)
    assert represent_predicate({"between": ["2026-01-01", "2026-01-31"]}) == "2026-01-01"


def test_represent_predicate_any_returns_none():
    assert represent_predicate({"any": True}) is None


def test_represent_predicate_set_eq_returns_list():
    assert represent_predicate({"set_eq": ["inbox", "starred"]}) == ["inbox", "starred"]


def test_represent_predicate_expr_raises():
    """{expr:} predicate can't be concretized without an explicit example value."""
    import pytest
    with pytest.raises(ValueError, match="expr"):
        represent_predicate({"expr": "x > 10"})


def test_represent_predicate_fields_recursive():
    result = represent_predicate({
        "fields": {"zip": {"eq": "94107"}, "city": {"eq": "SF"}},
    })
    assert result == {"zip": "94107", "city": "SF"}


def test_apply_canonical_diff_creates_entity_for_bijection():
    """Full smoke test: apply the pp_immunization canonical_diff to a seeded state."""
    # If the pilot task's canonical_diff is not yet wired (Task 10), skip this test
    from breakingweb.tasks._registry import get_task
    from breakingweb.backend.state import SessionManager

    task = get_task("pp_immunization_gap_review")
    # Use getattr so the test still works before Task 7 adds the schema field.
    if getattr(task, "canonical_diff", None) is None:
        import pytest
        pytest.skip("canonical_diff for pp_immunization_gap_review not yet authored (Task 10)")

    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    initial_state = sm.get_state(sid)
    final_state = apply_canonical_diff(
        initial_state=initial_state,
        task_id="pp_immunization_gap_review",
        targets=dict(targets),
    )
    # Preview may append either a typed Appointment or a raw dict fallback,
    # depending on whether the canonical_diff's predicates cover every
    # required pydantic field. Both shapes are valid for preview.
    def _id(a):
        return a["id"] if isinstance(a, dict) else a.id
    n_new = len([
        a for a in final_state.appointments
        if str(_id(a)).startswith("appt_new_")
    ])
    assert n_new == len(targets["due_imm_ids"])
