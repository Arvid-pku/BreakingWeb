"""Solvability proof for the v2 upgraded pp_update_insurance task.

The v2 task is a genuine VERIFICATION scenario (reconcile / branch on
discrepancy), not a single read-extract-write. The authoritative new-card
values live in a billing THREAD that the agent must mine:

* THREE billing card messages exist. The authoritative (most recent) card and a
  same-carrier NEAR-RECENCY decoy share an (almost) identical subject and the
  SAME plan name, so the agent must disambiguate by message ``timestamp`` — not
  by subject text. A third, older different-carrier "SUPERSEDED" card is a
  further decoy.
* The authoritative card body carries an internal CONTRADICTION: the prose lists
  a mis-transcribed member id (``new_member_id_typo``) while a footer + explicit
  ``Correction:`` line state the CORRECTED member id (``new_member_id``). The
  agent must apply the corrected value.
* The new contact EMAIL is delivered only in a FOLLOW-UP message in the SAME
  thread; the first card message carries only the phone. The agent must read the
  whole thread.

This test drives the CORRECT solution through the real backend endpoints
(POST /profile/insurance and POST /profile/demographics) via the FastAPI
TestClient, then evaluates with the canonical_diff evaluator. It also proves a
battery of near-misses (stale card, near-recency decoy, mis-transcribed typo
member id, missing follow-up email) all fail.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _create_session(client: TestClient) -> tuple[str, dict]:
    """Create a session via the REST endpoint and return (session_id, targets).

    Targets are read back from the app's own SessionManager so the test drives
    mutations against the same session the evaluator will read.
    """
    resp = client.post(
        "/api/env/patient_portal/session",
        json={"task_id": "pp_update_insurance", "seed": 42},
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]
    targets = dict(app.state.session_manager.get_targets(session_id))
    return session_id, targets


def _post_insurance(client: TestClient, session_id: str, *, plan_name, member_id, group_number):
    return client.post(
        "/api/env/patient_portal/profile/insurance",
        json={
            "session_id": session_id,
            "plan_name": plan_name,
            "member_id": member_id,
            "group_number": group_number,
        },
    )


def _post_demographics(client: TestClient, session_id: str, *, phone, email):
    return client.post(
        "/api/env/patient_portal/profile/demographics",
        json={"session_id": session_id, "phone": phone, "email": email},
    )


def _evaluate(session_id: str, targets: dict) -> dict:
    state = app.state.session_manager.get_state(session_id)
    return evaluate(
        task=get_task("pp_update_insurance"),
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )


def test_seed_produces_distinct_discriminators():
    """The decoys must be genuinely distinct so the task is non-trivial."""
    client = TestClient(app)
    _, t = _create_session(client)

    # Authoritative vs the patient's original.
    assert t["new_plan_name"] != t["old_plan_name"]
    assert t["new_member_id"] != t["old_member_id"]
    # Authoritative vs the different-carrier SUPERSEDED decoy.
    assert t["new_plan_name"] != t["stale_plan_name"]
    assert t["new_member_id"] != t["stale_member_id"]
    # Authoritative vs the same-carrier NEAR-RECENCY decoy: same plan name,
    # different member id / group number / phone (recency-only disambiguation).
    assert t["new_plan_name"] == t["near_plan_name"]
    assert t["new_member_id"] != t["near_member_id"]
    assert t["new_group_number"] != t["near_group_number"]
    assert t["new_phone"] != t["near_phone"]
    # The prose typo member id differs from the corrected member id.
    assert t["new_member_id"] != t["new_member_id_typo"]


def test_correct_trajectory_via_real_endpoints_passes():
    """Applying the CORRECTED most-recent-card values through real routes passes."""
    client = TestClient(app)
    session_id, targets = _create_session(client)

    # 1) Insurance: corrected member id (not the prose typo), new plan/group.
    r1 = _post_insurance(
        client, session_id,
        plan_name=targets["new_plan_name"],
        member_id=targets["new_member_id"],
        group_number=targets["new_group_number"],
    )
    assert r1.status_code == 200, r1.text

    # 2) Contact: phone from the card message, email from the follow-up message.
    r2 = _post_demographics(
        client, session_id,
        phone=targets["new_phone"], email=targets["new_email"],
    )
    assert r2.status_code == 200, r2.text

    result = _evaluate(session_id, targets)
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99, f"score too low: {result}"
    # canonical_diff is richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_typo_member_id_near_miss_fails():
    """Applying the mis-transcribed prose member id (not the correction) fails."""
    client = TestClient(app)
    session_id, targets = _create_session(client)

    r1 = _post_insurance(
        client, session_id,
        plan_name=targets["new_plan_name"],
        member_id=targets["new_member_id_typo"],  # the trap value
        group_number=targets["new_group_number"],
    )
    assert r1.status_code == 200, r1.text
    r2 = _post_demographics(
        client, session_id,
        phone=targets["new_phone"], email=targets["new_email"],
    )
    assert r2.status_code == 200, r2.text

    result = _evaluate(session_id, targets)
    assert result.get("success") is False, f"typo-member-id near-miss should fail: {result}"


def test_near_recency_decoy_near_miss_fails():
    """Applying the same-carrier NEAR-RECENCY decoy's values must fail."""
    client = TestClient(app)
    session_id, targets = _create_session(client)

    # Same plan name as the real card (same carrier) but the decoy's member id,
    # group number and phone — the trap for an agent that disambiguates by
    # subject string instead of by timestamp.
    r1 = _post_insurance(
        client, session_id,
        plan_name=targets["near_plan_name"],
        member_id=targets["near_member_id"],
        group_number=targets["near_group_number"],
    )
    assert r1.status_code == 200, r1.text
    r2 = _post_demographics(
        client, session_id,
        phone=targets["near_phone"], email=targets["new_email"],
    )
    assert r2.status_code == 200, r2.text

    result = _evaluate(session_id, targets)
    assert result.get("success") is False, f"near-recency near-miss should fail: {result}"


def test_stale_card_values_near_miss_fails():
    """Applying the STALE (superseded) card's values must fail evaluation."""
    client = TestClient(app)
    session_id, targets = _create_session(client)

    r1 = _post_insurance(
        client, session_id,
        plan_name=targets["stale_plan_name"],
        member_id=targets["stale_member_id"],
        group_number=targets["stale_group_number"],
    )
    assert r1.status_code == 200, r1.text
    r2 = _post_demographics(
        client, session_id,
        phone=targets["new_phone"], email=targets["new_email"],
    )
    assert r2.status_code == 200, r2.text

    result = _evaluate(session_id, targets)
    assert result.get("success") is False, f"stale-card near-miss should fail: {result}"


def test_missing_followup_email_near_miss_fails():
    """Updating insurance + phone but missing the follow-up-thread email fails."""
    client = TestClient(app)
    session_id, targets = _create_session(client)

    r1 = _post_insurance(
        client, session_id,
        plan_name=targets["new_plan_name"],
        member_id=targets["new_member_id"],
        group_number=targets["new_group_number"],
    )
    assert r1.status_code == 200, r1.text
    # Update only the phone; do NOT read the follow-up message for the email.
    r2 = client.post(
        "/api/env/patient_portal/profile/demographics",
        json={"session_id": session_id, "phone": targets["new_phone"]},
    )
    assert r2.status_code == 200, r2.text

    result = _evaluate(session_id, targets)
    assert result.get("success") is False, f"missing-email near-miss should fail: {result}"
