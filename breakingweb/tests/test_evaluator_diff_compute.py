"""Unit tests for compute_diff(initial, final) -> list[DiffEntry]."""

from pydantic import BaseModel, Field

from breakingweb.eval_core import Create, Delete, Update, compute_diff


def test_create_detected():
    initial = {"emails": []}
    final = {"emails": [{"id": "e1", "subject": "hi"}]}
    diff = compute_diff(initial, final)
    assert len(diff) == 1
    assert isinstance(diff[0], Create)
    assert diff[0].entity == "emails"
    assert diff[0].entity_id == "e1"
    assert diff[0].fields["subject"] == "hi"


def test_update_detected():
    initial = {"emails": [{"id": "e1", "is_read": False, "subject": "hi"}]}
    final = {"emails": [{"id": "e1", "is_read": True, "subject": "hi"}]}
    diff = compute_diff(initial, final)
    assert len(diff) == 1
    assert isinstance(diff[0], Update)
    assert diff[0].entity_id == "e1"
    assert diff[0].field_changes["is_read"] == (False, True)
    assert "subject" not in diff[0].field_changes  # unchanged


def test_delete_detected():
    initial = {"emails": [{"id": "e1", "subject": "gone"}]}
    final = {"emails": []}
    diff = compute_diff(initial, final)
    assert len(diff) == 1
    assert isinstance(diff[0], Delete)
    assert diff[0].entity_id == "e1"


def test_no_change_empty_diff():
    initial = {"emails": [{"id": "e1", "subject": "hi"}]}
    final = {"emails": [{"id": "e1", "subject": "hi"}]}
    diff = compute_diff(initial, final)
    assert diff == []


def test_multiple_collections():
    initial = {"emails": [], "filters": [{"id": "f1", "name": "x"}]}
    final = {"emails": [{"id": "e1"}], "filters": []}
    diff = compute_diff(initial, final)
    kinds = {type(d).__name__ for d in diff}
    assert kinds == {"Create", "Delete"}


def test_diff_stable_ordering():
    """Diff entries sorted by (collection, kind, entity_id)."""
    initial = {"emails": [{"id": "e2"}, {"id": "e1"}]}
    final = {"emails": []}
    diff = compute_diff(initial, final)
    assert [d.entity_id for d in diff] == ["e1", "e2"]


def test_pydantic_model_as_state():
    """compute_diff accepts pydantic models in addition to dicts.

    We use a minimal in-test pydantic state rather than the full
    ``PatientPortalState`` because that model has many required fields
    (``patient``, ``task_id``, etc.) that would clutter this unit test.
    This still exercises the pydantic path in ``_collections_of``.
    """

    class _Email(BaseModel):
        id: str
        subject: str = ""

    class _State(BaseModel):
        emails: list[_Email] = Field(default_factory=list)
        filters: list[_Email] = Field(default_factory=list)

    initial = _State()
    final = _State(emails=[_Email(id="e1", subject="hello")])

    diff = compute_diff(initial, final)
    assert any(
        isinstance(d, Create) and d.entity == "emails" and d.entity_id == "e1"
        for d in diff
    )
