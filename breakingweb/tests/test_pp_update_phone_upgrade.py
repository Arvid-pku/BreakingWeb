"""Solvability proof for the upgraded (medium-tier) pp_update_phone task.

The upgraded task is a VERIFICATION task: the values already ON FILE are
deliberate one-character look-alikes of the targets the agent must write (the
on-file phone is the new phone with the last two digits transposed; the on-file
email has a hyphen inserted in the domain; the OLD emergency contact's phone is
a look-alike of the patient's NEW phone). The agent must read, compare
character-by-character, and write the EXACT targets through the ONLY legitimate
endpoint (POST /profile/demographics), with every other patient singleton field
frozen and a wall of sibling-collection invariants plus critical/high
disambiguation constraints.

This test drives the CORRECT solution through the real backend mutation
endpoint via TestClient (so it also confirms the action clears every gate),
then evaluates with the unified evaluator. It also asserts that the OLD easy
answer and several plausible look-alike / cross-wire near-misses now FAIL.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


TASK_ID = "pp_update_phone"


def _new_session() -> tuple[TestClient, str, dict]:
    """Create a session inside the APP's session manager and return targets."""
    client = TestClient(app)
    sm = app.state.session_manager
    sid, targets, _ = sm.create_session(
        env_id="patient_portal", task_id=TASK_ID, seed=42
    )
    return client, sid, dict(targets)


def _evaluate(sid: str, targets: dict) -> dict:
    sm = app.state.session_manager
    state = sm.get_state(sid)
    return evaluate(
        task=get_task(TASK_ID),
        server_state=state,
        targets=targets,
        trajectory=[],
    )


def _post_demographics(client: TestClient, sid: str, body: dict) -> None:
    resp = client.post(
        "/api/env/patient_portal/profile/demographics",
        json={"session_id": sid, **body},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Correct solution
# ---------------------------------------------------------------------------

def test_correct_trajectory_passes() -> None:
    client, sid, targets = _new_session()

    # The verification trap must actually be present: every value on file is a
    # one-character look-alike of the target the agent must write.
    sm = app.state.session_manager
    initial = sm.get_state(sid).patient
    assert initial.phone != targets["new_phone"]
    assert initial.email != targets["new_email"]
    # On-file phone is the new phone with the last two digits transposed, and
    # the OLD emergency-contact phone is a look-alike of the patient's NEW phone
    # (the cross-wire bait) -- so they are confusable but distinct.
    assert initial.phone == targets["on_file_phone"]
    assert initial.email == targets["on_file_email"]
    assert initial.emergency_contact.phone == targets["on_file_ec_phone"]
    assert initial.emergency_contact.phone != targets["ec_new_phone"]

    # Single legitimate call updating exactly the three contact field groups.
    _post_demographics(
        client,
        sid,
        {
            "phone": targets["new_phone"],
            "email": targets["new_email"],
            "emergency_contact": {
                "name": targets["ec_name"],
                "phone": targets["ec_new_phone"],
                "relationship": targets["ec_relationship"],
            },
        },
    )

    result = _evaluate(sid, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # Richer than the legacy 1-check eval: at least the update + constraints.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


# ---------------------------------------------------------------------------
# Wrong / near-miss trajectories must FAIL
# ---------------------------------------------------------------------------

def test_phone_only_partial_fails() -> None:
    """Updating only the phone (the OLD easy answer) is now insufficient."""
    client, sid, targets = _new_session()
    _post_demographics(client, sid, {"phone": targets["new_phone"]})
    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"phone-only should fail: {result}"


def test_cross_wired_phones_fail() -> None:
    """Cross-wiring the patient phone with the emergency-contact phone fails."""
    client, sid, targets = _new_session()
    _post_demographics(
        client,
        sid,
        {
            # Patient phone accidentally set to the EC number (cross-wire).
            "phone": targets["ec_new_phone"],
            "email": targets["new_email"],
            "emergency_contact": {
                "name": targets["ec_name"],
                "phone": targets["ec_new_phone"],
                "relationship": targets["ec_relationship"],
            },
        },
    )
    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"cross-wired should fail: {result}"


def test_collateral_message_side_effect_fails() -> None:
    """A correct contact update PLUS an unsolicited message must fail.

    Over-acting (sending a message) trips the high-severity messages invariant
    even though the primary update is correct.
    """
    client, sid, targets = _new_session()
    _post_demographics(
        client,
        sid,
        {
            "phone": targets["new_phone"],
            "email": targets["new_email"],
            "emergency_contact": {
                "name": targets["ec_name"],
                "phone": targets["ec_new_phone"],
                "relationship": targets["ec_relationship"],
            },
        },
    )
    # Send an unsolicited message to a real provider.
    sm = app.state.session_manager
    state = sm.get_state(sid)
    provider_id = state.providers[0].id
    resp = client.post(
        "/api/env/patient_portal/messages/send",
        json={
            "session_id": sid,
            "provider_id": provider_id,
            "subject": "Updated my contact info",
            "body": "FYI I changed my phone and email.",
        },
    )
    assert resp.status_code == 200, resp.text

    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"collateral message should fail: {result}"


def _correct_ec(targets: dict) -> dict:
    return {
        "name": targets["ec_name"],
        "phone": targets["ec_new_phone"],
        "relationship": targets["ec_relationship"],
    }


def test_resaving_onfile_lookalike_phone_fails() -> None:
    """Re-saving the displayed on-file phone (a one-digit look-alike) fails.

    This is the core verification trap: the value on file (...5390) is a
    transposition of the target (...5309). An agent that "trusts the displayed
    value" and writes it back trips the critical phone-disambiguation
    constraint (state.patient.phone != initial.patient.phone).
    """
    client, sid, targets = _new_session()
    _post_demographics(
        client,
        sid,
        {
            "phone": targets["on_file_phone"],  # the look-alike, NOT the target
            "email": targets["new_email"],
            "emergency_contact": _correct_ec(targets),
        },
    )
    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"on-file phone look-alike should fail: {result}"


def test_lookalike_email_fails() -> None:
    """Saving the on-file look-alike email (hyphenated domain) fails."""
    client, sid, targets = _new_session()
    _post_demographics(
        client,
        sid,
        {
            "phone": targets["new_phone"],
            "email": targets["on_file_email"],  # meridian-health (hyphen) look-alike
            "emergency_contact": _correct_ec(targets),
        },
    )
    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"email look-alike should fail: {result}"


def test_ec_phone_set_to_patient_new_phone_fails() -> None:
    """Cross-wiring the patient's NEW phone into the EC phone slot fails.

    The OLD EC phone is a look-alike of the patient's new phone; an agent that
    confuses the two and writes the patient's new number as the EC phone trips
    the EC-phone disambiguation constraint.
    """
    client, sid, targets = _new_session()
    _post_demographics(
        client,
        sid,
        {
            "phone": targets["new_phone"],
            "email": targets["new_email"],
            "emergency_contact": {
                "name": targets["ec_name"],
                "phone": targets["new_phone"],  # cross-wired EC phone
                "relationship": targets["ec_relationship"],
            },
        },
    )
    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"EC-phone cross-wire should fail: {result}"


def test_old_ec_left_in_place_fails() -> None:
    """Leaving the OLD emergency contact untouched fails (no real replacement)."""
    client, sid, targets = _new_session()
    sm = app.state.session_manager
    old_ec = sm.get_state(sid).patient.emergency_contact
    _post_demographics(
        client,
        sid,
        {
            "phone": targets["new_phone"],
            "email": targets["new_email"],
            "emergency_contact": {
                "name": old_ec.name,
                "phone": old_ec.phone,
                "relationship": old_ec.relationship,
            },
        },
    )
    result = _evaluate(sid, targets)
    assert result.get("success") is False, f"unchanged EC should fail: {result}"
