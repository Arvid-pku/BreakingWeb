"""Unit tests for match_diff — non-bijection cases only (Task 4)."""

from breakingweb.eval_core import match_diff, Create, Update
from breakingweb.tasks.canonical_diff import CanonicalDiff


def _diff(d: dict) -> CanonicalDiff:
    return CanonicalDiff.model_validate(d)


def test_single_create_matches():
    cd = _diff({
        "create": [{
            "entity": "emails",
            "properties": {"subject": {"eq": "hello"}, "is_read": {"eq": False}},
        }],
    })
    agent_diff = [Create(entity="emails", entity_id="e1",
                         fields={"subject": "hello", "is_read": False})]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is True
    assert report.score == 1.0


def test_single_create_fails_when_property_mismatches():
    cd = _diff({
        "create": [{
            "entity": "emails",
            "properties": {"subject": {"eq": "hello"}},
        }],
    })
    agent_diff = [Create(entity="emails", entity_id="e1",
                         fields={"subject": "goodbye"})]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is False


def test_invariant_blocks_change():
    cd = _diff({
        "invariant": [{"collection": "state.contacts", "preserve": "ALL"}],
    })
    agent_diff = [Update(entity="contacts", entity_id="c1",
                         field_changes={"name": ("old", "new")})]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is False


def test_no_change_and_no_required_creates_passes():
    cd = _diff({
        "invariant": [{"collection": "state.emails", "preserve": "ALL"}],
    })
    report = match_diff([], cd, targets={}, initial=None, final=None)
    assert report.passed is True


def test_excess_create_fails_as_unaccounted():
    cd = _diff({
        "create": [{
            "entity": "emails",
            "properties": {"subject": {"eq": "wanted"}},
        }],
    })
    agent_diff = [
        Create(entity="emails", entity_id="e1", fields={"subject": "wanted"}),
        Create(entity="emails", entity_id="e2", fields={"subject": "extra"}),
    ]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is False
    assert any("unaccounted" in f.kind.lower() or "unaccounted" in f.description.lower()
               for f in report.failures), f"failures: {report.failures}"


# ── Task 5: Bijection matching ──────────────────────────────────────
#
# The bijection variable ``v`` is bound per-slot and exposed to ``{expr: ...}``
# predicates via ``PredicateScope.bijection_var``. The scalar ``{eq: "v"}``
# form compares literally against the string ``"v"`` (no special-casing), so
# these tests use ``{expr: "x == v"}`` to exercise the actual v-binding path.


def test_bijection_saturated_passes():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {
                "vaccine_ref": {"expr": "x == v"},
                "status": {"eq": "scheduled"},
            },
        }],
    })
    targets = {"due_ids": ["imm_1", "imm_2"]}
    agent_diff = [
        Create(entity="appointments", entity_id="a1",
               fields={"vaccine_ref": "imm_1", "status": "scheduled"}),
        Create(entity="appointments", entity_id="a2",
               fields={"vaccine_ref": "imm_2", "status": "scheduled"}),
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=None)
    assert report.passed is True, f"failures: {report.failures}"


def test_bijection_unsaturated_fails():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": ["imm_1", "imm_2"]}
    agent_diff = [
        Create(entity="appointments", entity_id="a1",
               fields={"vaccine_ref": "imm_1"}),
        # Missing imm_2
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=None)
    assert report.passed is False


def test_bijection_graph_links_to_check_and_resolves_slot_labels():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "desc": "Schedule overdue vaccines",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": ["imm_1", "imm_2"]}
    final_state = {
        "appointments": [],
        "immunizations": [
            {"id": "imm_1", "vaccine_name": "MMR"},
            {"id": "imm_2", "vaccine_name": "Tdap"},
        ],
    }
    agent_diff = [
        Create(entity="appointments", entity_id="a1", fields={"vaccine_ref": "imm_1"}),
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=final_state)
    assert report.passed is False
    graph = report.bijection_graphs[0]
    assert graph["check_index"] == 0
    assert graph["check_desc"] == report.checks[0]["desc"]
    assert graph["slots"][0]["label"] == "MMR (imm_1)"
    assert graph["slots"][1]["label"] == "Tdap (imm_2)"


def test_bijection_empty_target_requires_zero_creates():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": []}
    report = match_diff([], cd, targets=targets, initial=None, final=None)
    assert report.passed is True


def test_bijection_excess_fails():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": ["imm_1"]}
    agent_diff = [
        Create(entity="appointments", entity_id="a1",
               fields={"vaccine_ref": "imm_1"}),
        Create(entity="appointments", entity_id="a2",
               fields={"vaccine_ref": "imm_1"}),
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=None)
    assert report.passed is False


# -- Task 6: Named invariants + constraints + scoring ----------------

def test_named_invariant_attached_on_failure():
    cd = _diff({
        "invariant": [{"collection": "state.contacts", "preserve": "ALL"}],
        "named_invariants": [
            {"name": "Agent did not modify contacts",
             "ref": "invariant[0]", "severity": "high"},
        ],
    })
    agent_diff = [Update(entity="contacts", entity_id="c1",
                         field_changes={"name": ("a", "b")})]
    report = match_diff(agent_diff, cd, targets={}, initial=None, final=None)
    assert report.passed is False
    labeled = [n for n in report.negative_checks if n["desc"] == "Agent did not modify contacts"]
    assert labeled, f"expected named invariant label in negative_checks, got: {report.negative_checks}"
    assert labeled[0]["passed"] is False


def test_constraint_block_fails_task():
    cd = _diff({
        "constraints": [{
            "desc": "chat must have at least one message",
            "expr": "len(state['chat']) >= 1",
            "severity": "critical",
        }],
    })
    final_state = {"chat": []}
    report = match_diff([], cd, targets={}, initial=None, final=final_state)
    assert report.passed is False
    assert any("chat must have" in c["desc"] for c in report.negative_checks)


def test_constraint_block_passes_when_true():
    cd = _diff({
        "constraints": [{
            "desc": "chat has at least one message",
            "expr": "len(state['chat']) >= 1",
            "severity": "critical",
        }],
    })
    final_state = {"chat": [{"role": "assistant", "content": "hi"}]}
    report = match_diff([], cd, targets={}, initial=None, final=final_state)
    assert report.passed is True


def test_partial_credit_bijection():
    cd = _diff({
        "create": [{
            "entity": "appointments",
            "bijection": {"over": "target['due_ids']", "variable": "v"},
            "properties": {"vaccine_ref": {"expr": "x == v"}},
        }],
    })
    targets = {"due_ids": ["imm_1", "imm_2", "imm_3"]}
    agent_diff = [
        Create(entity="appointments", entity_id="a1", fields={"vaccine_ref": "imm_1"}),
        Create(entity="appointments", entity_id="a2", fields={"vaccine_ref": "imm_2"}),
        # Missing imm_3 -- 2/3 credit
    ]
    report = match_diff(agent_diff, cd, targets=targets, initial=None, final=None)
    assert report.passed is False
    assert 0.55 <= report.score <= 0.75, f"expected ~2/3 score, got {report.score}"


def test_named_invariant_severity_penalty_applied():
    """High-severity named invariant failure reduces score more than medium."""
    cd_high = _diff({
        "invariant": [{"collection": "state.contacts", "preserve": "ALL"}],
        "named_invariants": [
            {"name": "Major contact violation",
             "ref": "invariant[0]", "severity": "high"},
        ],
    })
    cd_low = _diff({
        "invariant": [{"collection": "state.contacts", "preserve": "ALL"}],
        "named_invariants": [
            {"name": "Minor contact violation",
             "ref": "invariant[0]", "severity": "low"},
        ],
    })
    agent_diff = [Update(entity="contacts", entity_id="c1",
                         field_changes={"name": ("a", "b")})]

    r_high = match_diff(agent_diff, cd_high, targets={}, initial=None, final=None)
    r_low = match_diff(agent_diff, cd_low, targets={}, initial=None, final=None)

    # high severity penalty (0.2) > low severity penalty (0.1) -> higher penalty
    # means lower score (both tasks pass zero positive weight; both fail the invariant)
    # Since passed_weight == 0, raw score is 0; penalty subtracts from 0, clamped
    # to 0. So score is 0 for both. The distinction is in the negative_checks penalty
    # field.
    high_penalty = next(n["penalty"] for n in r_high.negative_checks
                         if n["desc"] == "Major contact violation")
    low_penalty = next(n["penalty"] for n in r_low.negative_checks
                        if n["desc"] == "Minor contact violation")
    assert high_penalty > low_penalty


# ── Task 7: Integration with TaskDefinition + evaluator.py ──────────

def test_task_definition_parses_canonical_diff():
    from breakingweb.tasks._schema import TaskDefinition
    td = TaskDefinition.model_validate({
        "task_id": "test_dispatch",
        "env_id": "patient_portal",
        "title": "Test dispatch",
        "instruction_template": "Test.",
        "canonical_diff": {
            "invariant": [{"collection": "state.emails", "preserve": "ALL"}],
        },
    })
    assert td.canonical_diff is not None
    assert len(td.canonical_diff.invariant) == 1


def test_named_invariant_ref_resolution_validated_at_load():
    """A canonical_diff referencing invariant[99] when only 1 exists is rejected."""
    import pytest
    from breakingweb.tasks._schema import TaskDefinition
    from pydantic import ValidationError
    with pytest.raises((ValueError, ValidationError)):
        # This fails at canonical_diff-level load validation (not pydantic field parsing,
        # since the ref string is structurally valid — it's the out-of-range index that
        # fails).
        from breakingweb.tasks._registry import _validate_canonical_diff_refs
        td = TaskDefinition.model_validate({
            "task_id": "bad_ref",
            "env_id": "patient_portal",
            "title": "Bad ref",
            "instruction_template": "Test.",
            "canonical_diff": {
                "invariant": [{"collection": "state.emails", "preserve": "ALL"}],
                "named_invariants": [
                    {"name": "X", "ref": "invariant[99]", "severity": "high"},
                ],
            },
        })
        _validate_canonical_diff_refs(td)


def test_session_captures_initial_snapshot():
    """After create_session, the session exposes an initial_snapshot attribute."""
    from breakingweb.backend.state import SessionManager
    sm = SessionManager()
    sid, _, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    snapshot = sm.get_initial_snapshot(sid)
    assert snapshot is not None
    # Snapshot must be independent of current state — mutating current doesn't affect it
    current = sm.get_state(sid)
    assert len(current.appointments) == len(snapshot.appointments)


def test_gmail_collection_map_no_overwrite():
    """Class 13 regression: Email → emails (not deleted); sent/deleted reachable directly."""
    from breakingweb.backend.models.gmail import GmailSettings, GmailState
    from breakingweb.eval_core.diff import collection_for, collection_map_for

    state = GmailState(
        env_id="gmail", task_id="test", owner_name="T", owner_email="t@t.com",
        settings=GmailSettings(id="s1"),
    )
    mapping = collection_map_for(state)

    assert mapping.get("Email") == "emails", f"Email should map to emails, got {mapping.get('Email')}"
    assert collection_for("sent", state) == "sent"
    assert collection_for("deleted", state) == "deleted"
    assert collection_for("emails", state) == "emails"
    assert collection_for("Email", state) == "emails"
    assert collection_for("Label", state) == "labels"
    assert collection_for("Draft", state) == "drafts"
