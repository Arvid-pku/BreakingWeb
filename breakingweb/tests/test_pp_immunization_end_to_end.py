"""Smoke test: full eval path via the real evaluator entry point.

Confirms the canonical_diff-equipped pilot task evaluates correctly when
an agent produces a sane trajectory vs a wrong-provider trajectory.
"""

from datetime import datetime, timedelta

from breakingweb.backend.state import SessionManager
from breakingweb.backend.models.patient_portal import Appointment
from breakingweb.tasks._evaluator import evaluate
from breakingweb.tasks._registry import get_task


def _future_datetime_in_window(targets: dict) -> str:
    start = datetime.fromisoformat(targets["window_start"].replace("Z", "+00:00"))
    return (start + timedelta(days=7)).isoformat()


def _make_appt(**kwargs) -> Appointment:
    kwargs.setdefault("type", "in-person")
    kwargs.setdefault("status", "scheduled")
    kwargs.setdefault("reason", "Immunization")
    return Appointment(**kwargs)


def test_correct_trajectory_evaluates_to_pass():
    """Correct agent trajectory on pp_immunization_gap_review passes via evaluate()."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    state = sm.get_state(sid)
    future = _future_datetime_in_window(dict(targets))

    for imm_id in targets["due_imm_ids"]:
        providers = targets["admin_providers"][imm_id]
        state.appointments.append(_make_appt(
            id=f"appt_new_{imm_id}",
            provider_id=providers[0],
            datetime=future,
        ))

    task = get_task("pp_immunization_gap_review")
    result = evaluate(
        task=task,
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is True, f"result: {result}"
    assert result.get("score", 0.0) >= 0.99
    # canonical_diff checks are richer than the legacy 2-check eval.
    assert len(result.get("checks", [])) + len(result.get("negative_checks", [])) > 2


def test_wrong_provider_evaluates_to_fail():
    """Wrong provider_id trajectory fails via evaluate()."""
    sm = SessionManager()
    sid, targets, _ = sm.create_session(
        env_id="patient_portal",
        task_id="pp_immunization_gap_review",
        seed=42,
    )
    state = sm.get_state(sid)
    future = _future_datetime_in_window(dict(targets))

    for imm_id in targets["due_imm_ids"]:
        state.appointments.append(_make_appt(
            id=f"appt_new_{imm_id}",
            provider_id="prov_wrong_id",
            datetime=future,
        ))

    task = get_task("pp_immunization_gap_review")
    result = evaluate(
        task=task,
        server_state=state,
        targets=dict(targets),
        trajectory=[],
    )
    assert result.get("success") is False
