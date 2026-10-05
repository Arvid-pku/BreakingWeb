from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from breakingweb.backend.models.patient_portal import (
    Appointment,
    ClinicalMessage,
    EmergencyContact,
    Immunization,
    InsuranceClaim,
    InsurancePlan,
    LabResult,
    Patient,
    PatientPortalState,
    Pharmacy,
    Prescription,
    Provider,
    Referral,
    ScreeningRecommendation,
    SlotInfo,
)


def test_patient_with_nested_types():
    p = Patient(
        id="patient_1",
        name="Jane Doe",
        sex="female",
        dob=date(1980, 5, 15),
        phone="(555) 123-4567",
        email="jane.doe@example.com",
        insurance_plan=InsurancePlan(
            plan_name="Blue Cross PPO Gold",
            member_id="BCB-9384751",
            group_number="GRP-44820",
            copay=Decimal("30"),
            deductible=Decimal("2000"),
            deductible_met=Decimal("850"),
        ),
        pcp_id="prov_1",
        allergies=["Penicillin"],
        conditions=["Hypertension"],
        pharmacy_ids=["pharm_1"],
        emergency_contact=EmergencyContact(
            name="John Doe", phone="(555) 987-6543", relationship="Spouse"
        ),
        applicable_screenings=[
            ScreeningRecommendation(
                screening_name="Mammogram",
                recommended_age_start=40,
                frequency="every 2 years",
                last_completed=date(2024, 6, 1),
                next_due=date(2026, 6, 1),
            )
        ],
    )
    assert p.name == "Jane Doe"
    assert p.insurance_plan.copay == Decimal("30")
    assert len(p.applicable_screenings) == 1


def test_provider_with_slots():
    prov = Provider(
        id="prov_1",
        name="Dr. Sarah Mitchell",
        specialty="pcp",
        department="Primary Care",
        npi="1234567890",
        accepting_new=True,
        available_slots=[
            SlotInfo(
                datetime=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
                type="in-person",
                duration_minutes=30,
            )
        ],
    )
    assert prov.specialty == "pcp"
    assert len(prov.available_slots) == 1


def test_prescription_fields():
    rx = Prescription(
        id="rx_1",
        medication="Metformin 500mg",
        dosage="500mg",
        frequency="twice daily",
        provider_id="prov_1",
        pharmacy_id="pharm_1",
        refills_remaining=3,
        last_filled=datetime(2026, 2, 1, tzinfo=timezone.utc),
        expires_at=datetime(2027, 2, 1, tzinfo=timezone.utc),
        status="active",
        interactions=["Warfarin"],
    )
    assert rx.refills_remaining == 3
    assert rx.interactions == ["Warfarin"]


def _make_state(**overrides) -> PatientPortalState:
    """Minimal valid state for testing query methods."""
    defaults = dict(
        env_id="patient_portal",
        task_id="test_task",
        patient=Patient(
            id="patient_1", name="Test User", sex="male",
            dob=date(1985, 1, 1), phone="555-0000",
            email="test@example.com",
            insurance_plan=InsurancePlan(
                plan_name="Test Plan", member_id="M-1",
                group_number="G-1", copay=Decimal("30"),
                deductible=Decimal("2000"), deductible_met=Decimal("0"),
            ),
            pcp_id="prov_1",
            emergency_contact=EmergencyContact(
                name="EC", phone="555-1111", relationship="Spouse"
            ),
        ),
    )
    defaults.update(overrides)
    return PatientPortalState(**defaults)


def test_get_appointment_found_and_missing():
    state = _make_state(appointments=[
        Appointment(id="apt_1", provider_id="prov_1",
                    datetime=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    type="in-person", location="Main Office"),
    ])
    assert state.get_appointment("apt_1") is not None
    assert state.get_appointment("apt_999") is None


def test_unread_messages():
    state = _make_state(messages=[
        ClinicalMessage(id="msg_1", from_type="provider", provider_id="prov_1",
                        subject="Test", body="Body", thread_id="t1", is_read=False),
        ClinicalMessage(id="msg_2", from_type="provider", provider_id="prov_1",
                        subject="Test2", body="Body2", thread_id="t2", is_read=True),
    ])
    assert len(state.unread_messages()) == 1
    assert state.unread_count() == 1


def test_gen_id_monotonic():
    state = _make_state(appointments=[
        Appointment(id="apt_5", provider_id="prov_1",
                    datetime=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    type="in-person", location="Clinic"),
    ])
    assert state._gen_id("apt") == "apt_6"
    assert state._gen_id("msg") == "msg_7"


def test_sent_messages():
    state = _make_state(messages=[
        ClinicalMessage(id="msg_1", from_type="patient", provider_id="prov_1",
                        subject="Q", body="Body", thread_id="t1"),
        ClinicalMessage(id="msg_2", from_type="provider", provider_id="prov_1",
                        subject="A", body="Reply", thread_id="t1"),
    ])
    assert len(state.sent_messages()) == 1
    assert state.sent_messages()[0].from_type == "patient"


def test_total_patient_responsibility():
    state = _make_state(claims=[
        InsuranceClaim(id="clm_1", service_date=date(2026, 1, 15), provider_id="prov_1",
                       appointment_id="apt_1", procedure_code="99213", diagnosis_code="I10",
                       status="approved", amount_billed=Decimal("250"),
                       patient_responsibility=Decimal("50"),
                       appeal_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc)),
        InsuranceClaim(id="clm_2", service_date=date(2026, 2, 1), provider_id="prov_1",
                       appointment_id="apt_2", procedure_code="99214", diagnosis_code="E11",
                       status="denied", amount_billed=Decimal("400"),
                       patient_responsibility=Decimal("100"),
                       appeal_deadline=datetime(2026, 7, 1, tzinfo=timezone.utc)),
    ])
    # Only approved/appealed claims count
    assert state.total_patient_responsibility() == Decimal("50")
