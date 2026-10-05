"""Given a canonical_diff, synthesize adversarial final-states that violate it.

The matcher isn't available yet in this test (Task 4 lands match_diff in a
parallel workstream). We test only that the generator PRODUCES cases with
mutations on the right axes. Later (Task 15) an integration test confirms
every generated case is actually rejected by match_diff.
"""

from breakingweb.tasks.canonical_diff import CanonicalDiff
from breakingweb.tasks.adversarial import synthesize_adversarial_cases


def test_generator_produces_field_mutation_case():
    cd = CanonicalDiff.model_validate({
        "create": [{
            "entity": "emails",
            "properties": {"subject": {"eq": "target"}},
        }],
    })
    initial = {"emails": []}
    cases = synthesize_adversarial_cases(cd, initial=initial, targets={})
    assert len(cases) >= 1
    # At least one case mutates the subject away from "target"
    for case in cases:
        assert "description" in case
        assert "final" in case
    subject_mutation = next(
        (c for c in cases if "subject" in c["description"]), None
    )
    assert subject_mutation is not None


def test_generator_produces_invariant_violation_case():
    cd = CanonicalDiff.model_validate({
        "invariant": [{"collection": "state.contacts", "preserve": "ALL"}],
    })
    initial = {"contacts": [{"id": "c1", "name": "Alice"}]}
    cases = synthesize_adversarial_cases(cd, initial=initial, targets={})
    # Expect at least one case that mutates a contacts entity
    inv_cases = [c for c in cases if "invariant" in c["description"].lower()
                                      or "contacts" in c["description"].lower()]
    assert len(inv_cases) >= 1


def test_generator_handles_eq_numeric():
    cd = CanonicalDiff.model_validate({
        "create": [{
            "entity": "orders",
            "properties": {"qty": {"eq": 5}},
        }],
    })
    initial = {"orders": []}
    cases = synthesize_adversarial_cases(cd, initial=initial, targets={})
    assert len(cases) >= 1


def test_generator_skips_any_predicate():
    """any: true cannot be negated — generator should skip it."""
    cd = CanonicalDiff.model_validate({
        "create": [{
            "entity": "notes",
            "properties": {"text": {"any": True}},
        }],
    })
    initial = {"notes": []}
    cases = synthesize_adversarial_cases(cd, initial=initial, targets={})
    # No mutation of `text` is possible (any is tautological). May still
    # produce 0 cases, but shouldn't raise.
    assert isinstance(cases, list)


def test_generator_produces_between_violation():
    cd = CanonicalDiff.model_validate({
        "create": [{
            "entity": "bookings",
            "properties": {"price": {"between": [100, 200]}},
        }],
    })
    initial = {"bookings": []}
    cases = synthesize_adversarial_cases(cd, initial=initial, targets={})
    assert any("price" in c["description"] for c in cases)
