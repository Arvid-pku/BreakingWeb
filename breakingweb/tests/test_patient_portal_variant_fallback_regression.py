from __future__ import annotations

from collections import Counter

import pytest

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.patient_portal import SessionCreateRequest, create_session, list_variants
from breakingweb.backend.state import SessionManager
from breakingweb.injector.middleware import clear_all_degradations
from breakingweb.injector.seed import apply_seed_injection
from breakingweb.tasks._registry import env_tasks


@pytest.fixture(autouse=True)
def _reset_degradations() -> None:
    clear_all_degradations()
    yield
    clear_all_degradations()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_patient_portal_variants_endpoint_exposes_generated_yaml_batch(client: TestClient) -> None:
    response = client.get("/api/env/patient_portal/variants")
    assert response.status_code == 200, response.text

    variants = response.json()
    assert isinstance(variants, list)
    assert variants, "expected YAML-backed Patient Portal variants"
    assert all(v.get("source") == "yaml" for v in variants)
    assert all(str(v.get("filename", "")).startswith("pp_") for v in variants)
    assert not any(str(v.get("filename", "")).startswith("__auto__") for v in variants)
    # At least 1 variant per task. The benchmark curates to one-meaningful
    # variant per task; a few demo tasks retain additional variants when tests
    # explicitly reference them.
    assert len(variants) >= len(env_tasks("patient_portal"))
    counts = Counter(v.get("base_task_id") for v in variants)
    for task in env_tasks("patient_portal"):
        assert counts[task.task_id] >= 1, (
            f"{task.task_id} has no variant: {counts[task.task_id]}"
        )
    assert any(
        v.get("filename") == "pp_mark_all_read__mark_all_read_verification_v1.yaml"
        and v.get("base_task_id") == "pp_mark_all_read"
        and v.get("target_primitive") == "verification"
        for v in variants
    )
    assert any(
        v.get("filename") == "pp_mark_all_read__messages_list_stale_v1.yaml"
        and v.get("base_task_id") == "pp_mark_all_read"
        and v.get("target_primitive") == "verification"
        for v in variants
    )
    assert any(
        v.get("filename") == "pp_update_phone__profile_view_stale_v1.yaml"
        and v.get("base_task_id") == "pp_update_phone"
        and v.get("target_primitive") == "verification"
        for v in variants
    )

    api_variants = list_variants()
    assert api_variants == variants


@pytest.mark.parametrize(
    ("task_id", "variant_filename", "target_primitive"),
    [
        (
            "pp_mark_all_read",
            "pp_mark_all_read__mark_all_read_verification_v1.yaml",
            "verification",
        ),
        (
            "pp_update_phone",
            "pp_update_phone__profile_view_stale_v1.yaml",
            "verification",
        ),
    ],
)
def test_patient_portal_yaml_variant_can_create_session(
    task_id: str,
    variant_filename: str,
    target_primitive: str,
) -> None:
    session_manager = SessionManager()

    payload = create_session(
        SessionCreateRequest(
            task_id=task_id,
            variant_filename=variant_filename,
        ),
        session_manager=session_manager,
    )

    state = session_manager.get(payload["session_id"])
    assert state.degradation["variant_filename"] == variant_filename
    assert state.degradation["base_task_id"] == task_id
    assert state.degradation["target_primitive"] == target_primitive


def test_patient_portal_confusing_decoys_support_core_entity_types() -> None:
    session_manager = SessionManager()
    session_id, _, _ = session_manager.create_session("patient_portal", "pp_complete_account_audit", 42)
    state = session_manager.get(session_id)

    before = {
        "messages": len(state.messages),
        "claims": len(state.claims),
        "pharmacies": len(state.pharmacies),
        "labs": len(state.lab_results),
        "prescriptions": len(state.prescriptions),
        "immunizations": len(state.immunizations),
        "screenings": len(state.patient.applicable_screenings),
    }

    apply_seed_injection(
        state,
        {
            "action": "add_confusing_decoys",
            "decoys": [
                {
                    "type": "message",
                    "category": "billing",
                    "subject": "Lookalike billing thread",
                    "body": "Older thread that should not drive the task outcome.",
                    "timestamp": "2025-02-20T08:30:00+00:00",
                },
                {
                    "type": "claim",
                    "service_date": "2025-01-10",
                    "status": "denied",
                    "amount_billed": "410.00",
                    "amount_covered": "0.00",
                    "patient_responsibility": "410.00",
                    "eob_available": False,
                    "appeal_deadline": "2025-02-15T00:00:00+00:00",
                },
                {
                    "type": "pharmacy",
                    "name": "Walgreens Express #2044",
                    "address": "11 Cedar St, Springfield, IL 62705",
                    "phone": "(555) 410-2204",
                },
                {
                    "type": "lab_result",
                    "test_name": "HbA1c",
                    "test_code": "4548-4",
                    "collected_at": "2025-01-15T08:00:00+00:00",
                    "value": "6.8",
                    "unit": "%",
                    "reference_range": "4.0-5.6",
                    "flag": "abnormal",
                },
                {
                    "type": "prescription",
                    "medication": "Metoprolol 25mg",
                    "dosage": "25mg",
                    "frequency": "once daily",
                    "refills_remaining": 3,
                    "last_filled": "2025-02-01T08:00:00+00:00",
                    "expires_at": "2027-02-01T08:00:00+00:00",
                    "status": "active",
                    "interactions": [],
                },
                {
                    "type": "immunization",
                    "vaccine_name": "Influenza (Flu)",
                    "administered_at": "2025-10-01T09:00:00+00:00",
                    "next_due_at": "2026-12-01T09:00:00+00:00",
                    "series_complete": True,
                },
                {
                    "type": "screening",
                    "screening_name": "Bone Density Scan",
                    "recommended_age_start": 65,
                    "frequency": "every 2 years",
                    "last_completed": "2025-06-01",
                    "next_due": "2027-06-01",
                },
            ],
        },
    )

    assert len(state.messages) == before["messages"] + 1
    assert len(state.claims) == before["claims"] + 1
    assert len(state.pharmacies) == before["pharmacies"] + 1
    assert len(state.lab_results) == before["labs"] + 1
    assert len(state.prescriptions) == before["prescriptions"] + 1
    assert len(state.immunizations) == before["immunizations"] + 1
    assert len(state.patient.applicable_screenings) == before["screenings"] + 1

    assert any(m.subject == "Lookalike billing thread" for m in state.messages)
    assert any(c.patient_responsibility == "410.00" or str(c.patient_responsibility) == "410.00" for c in state.claims)
    assert any(p.name == "Walgreens Express #2044" for p in state.pharmacies)
    assert any(l.test_name == "HbA1c" and str(l.value) == "6.8" for l in state.lab_results)
    assert any(rx.medication == "Metoprolol 25mg" for rx in state.prescriptions)
    assert any(imm.vaccine_name == "Influenza (Flu)" for imm in state.immunizations)
    assert any(s.screening_name == "Bone Density Scan" for s in state.patient.applicable_screenings)
