#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks" / "patient_portal"
VARIANTS_DIR = ROOT / "injector" / "variants"
AUDIT_PATH = ROOT.parent / "docs" / "patient_portal_degradation_audit.md"


def load_tasks() -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for path in sorted(TASKS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        task_id = raw.get("task_id")
        if not task_id:
            continue
        raw["_path"] = path
        tasks[task_id] = raw
    return tasks


def variant(
    task_id: str,
    suffix: str,
    primitive: str,
    description: str,
    injections: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "variant_id": f"{task_id}__{suffix}",
        "base_task_id": task_id,
        "target_primitive": primitive,
        "description": description,
        "injections": injections,
    }


def seed(action: str, **params: Any) -> dict[str, Any]:
    return {"layer": "seed", "params": {"action": action, **params}}


def network(action: str, url_pattern: str, **params: Any) -> dict[str, Any]:
    return {"layer": "network", "params": {"action": action, "url_pattern": url_pattern, **params}}


def appointment_cancel_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "appointment_cancel_retry_v1",
        "backtracking",
        "The first appointment cancellation request returns 503. The agent must confirm the visit is still present and retry the cancellation.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/appointments/*/cancel",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary scheduling service failure. Retry the cancellation.",
                behavior={"mode": "once"},
            )
        ],
    )


def appointment_create_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "appointment_create_retry_v1",
        "backtracking",
        "The first appointment-booking request returns 503. The agent must verify the appointment did not persist and retry the booking.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/appointments/create",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary scheduling service failure. Retry the booking request.",
                behavior={"mode": "once"},
            )
        ],
    )


def appointment_reschedule_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "appointment_reschedule_retry_v1",
        "backtracking",
        "The first reschedule request returns 503. The agent must verify the original appointment still holds and retry the reschedule.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/appointments/*/reschedule",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary scheduling service failure. Retry the reschedule request.",
                behavior={"mode": "once"},
            )
        ],
    )


def appointments_list_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "appointments_list_stale_v1",
        "verification",
        "The first appointments list response is stale and omits the key schedule context. The agent must refresh the schedule before deciding which appointment to change.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/appointments**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def provider_search_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "provider_search_stale_v1",
        "exploration",
        "Provider discovery returns empty results on the first pass. The agent must retry search or explore the full provider directory instead of assuming no match exists.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/providers/search**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            ),
            network(
                "stale_data",
                "**/api/env/patient_portal/providers**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            ),
        ],
    )


def slot_search_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "slot_search_stale_v1",
        "planning",
        "The first slot lookup returns no availability. The agent must keep the sequencing plan intact and retry availability checks instead of abandoning the workflow.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/appointments/available-slots**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def labs_list_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "labs_list_stale_v1",
        "verification",
        "The first labs list response is stale and omits the relevant result. The agent must refresh or reopen the labs view before acting on the portal state.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/labs**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def lab_trend_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "lab_trend_stale_v1",
        "verification",
        "The first HbA1c trend fetch is stale and appears empty. The agent must verify the trend with a fresh read before scheduling follow-up care.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/labs/trend/*",
                stale_body={"test_name": "HbA1c", "items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def claims_list_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "claims_list_stale_v1",
        "verification",
        "The first claims list response is stale and briefly hides the relevant claim. The agent must refresh the billing state before deciding whether to pay or leave the claim unchanged.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/claims**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def messages_list_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "messages_list_stale_v1",
        "exploration",
        "The first inbox fetch is stale and briefly hides the task-relevant thread. The agent must retry or revisit the mailbox rather than assume the message is missing.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/messages**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def medications_list_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "medications_list_stale_v1",
        "verification",
        "The first medications list response is stale and briefly hides the task-relevant prescriptions. The agent must refresh the medication cabinet before acting on it.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/medications**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def referrals_list_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "referrals_list_stale_v1",
        "verification",
        "The first referrals view is stale and temporarily hides the relevant approved or pending referral. The agent must refresh the referral state before using it.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/referrals**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def pharmacies_list_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "pharmacies_list_stale_v1",
        "grounding",
        "The first pharmacy list response is stale and omits the relevant pharmacy. The agent must refresh the pharmacy list before selecting the transfer or default target.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/pharmacies**",
                stale_body={"items": []},
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


def mark_all_read_verification(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "mark_all_read_verification_v1",
        "verification",
        "The first mark-all-read request returns a fake success while leaving the unread messages untouched. The agent must verify the unread state and retry.",
        [
            network(
                "silent_fail",
                "**/api/env/patient_portal/messages/mark-all-read",
                methods=["POST"],
                fail_count=1,
                response_body={"count": 12},
                behavior={"mode": "once"},
            )
        ],
    )


def medication_refill_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "medication_refill_retry_v1",
        "backtracking",
        "The first refill request fails transiently. The agent must retry the refill instead of assuming the medication changed state.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/medications/*/refill",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary pharmacy service failure. Retry the refill request.",
                behavior={"mode": "once"},
            )
        ],
    )


def medication_renewal_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "medication_renewal_retry_v1",
        "backtracking",
        "The first renewal request fails transiently. The agent must retry and confirm the medication actually moved to pending renewal.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/medications/*/renewal",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary pharmacy service failure. Retry the renewal request.",
                behavior={"mode": "once"},
            )
        ],
    )


def medication_transfer_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "medication_transfer_retry_v1",
        "backtracking",
        "The first transfer request fails transiently. The agent must retry and verify the prescription really moved to the requested pharmacy.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/medications/*/transfer",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary pharmacy transfer failure. Retry the transfer request.",
                behavior={"mode": "once"},
            )
        ],
    )


def claim_appeal_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "claim_appeal_retry_v1",
        "backtracking",
        "The first appeal submission fails transiently. The agent must retry and confirm the claim status actually changed to appealed.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/claims/*/appeal",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary claims service failure. Retry the appeal submission.",
                behavior={"mode": "once"},
            )
        ],
    )


def claim_pay_verification(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "claim_pay_verification_v1",
        "verification",
        "The first claim payment returns a fake success while leaving the balance unpaid. The agent must verify the patient responsibility actually changed to zero.",
        [
            network(
                "silent_fail",
                "**/api/env/patient_portal/claims/*/pay",
                methods=["POST"],
                fail_count=1,
                response_body={
                    "id": "clm_fake_paid",
                    "service_date": "2026-01-10",
                    "provider_id": "prov_fake",
                    "appointment_id": "apt_fake",
                    "procedure_code": "99213",
                    "diagnosis_code": "I10",
                    "status": "approved",
                    "amount_billed": "180.00",
                    "amount_covered": "140.00",
                    "patient_responsibility": "0.00",
                    "eob_available": True,
                    "appeal_deadline": "2026-12-31T00:00:00+00:00",
                    "denial_reason": None,
                    "supporting_referral_id": None,
                    "supporting_lab_ids": [],
                },
                behavior={"mode": "once"},
            )
        ],
    )


def profile_demographics_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "profile_demographics_retry_v1",
        "backtracking",
        "The first demographics update fails transiently. The agent must retry and verify the profile actually changed.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/profile/demographics",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary profile service failure. Retry the demographics update.",
                behavior={"mode": "once"},
            )
        ],
    )


def profile_insurance_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "profile_insurance_retry_v1",
        "backtracking",
        "The first insurance update fails transiently. The agent must retry and verify the new plan details actually persisted.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/profile/insurance",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary insurance profile failure. Retry the insurance update.",
                behavior={"mode": "once"},
            )
        ],
    )


def default_pharmacy_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "default_pharmacy_retry_v1",
        "backtracking",
        "The first default-pharmacy update fails transiently. The agent must retry and verify the correct pharmacy became the sole default.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/profile/pharmacy/*/set-default",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary pharmacy profile failure. Retry the default-pharmacy update.",
                behavior={"mode": "once"},
            )
        ],
    )


def insurance_plan_transition_retry(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "insurance_plan_transition_retry_v1",
        "backtracking",
        "The insurance plan transition hits one transient write failure on the plan update and one on the default-pharmacy update. The agent must retry both and verify the transition completed.",
        [
            network(
                "error_then_success",
                "**/api/env/patient_portal/profile/insurance",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary insurance profile failure. Retry the insurance update.",
                behavior={"mode": "once"},
            ),
            network(
                "error_then_success",
                "**/api/env/patient_portal/profile/pharmacy/*/set-default",
                methods=["POST"],
                error_count=1,
                error_status=503,
                error_message="Temporary pharmacy profile failure. Retry the default-pharmacy update.",
                behavior={"mode": "once"},
            ),
        ],
    )


STALE_PROFILE_BODY = {
    "id": "pat_stale",
    "name": "Morgan Harper",
    "sex": "female",
    "dob": "1985-06-14",
    "phone": "(555) 010-1111",
    "email": "morgan.harper@example.com",
    "insurance_plan": {
        "plan_name": "Legacy Bronze HMO",
        "member_id": "LEG-0001123",
        "group_number": "GRP-00123",
        "copay": "50.00",
        "deductible": "3500.00",
        "deductible_met": "400.00",
    },
    "pcp_id": "prov_stale",
    "allergies": ["Penicillin"],
    "conditions": ["Hypertension"],
    "pharmacy_ids": [],
    "emergency_contact": {
        "name": "Jamie Harper",
        "phone": "(555) 010-2222",
        "relationship": "Spouse",
    },
    "applicable_screenings": [],
    "default_pharmacy": None,
}


def profile_view_stale(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "profile_view_stale_v1",
        "verification",
        "The first profile fetch is stale and shows outdated contact, insurance, and preventive details. The agent must refresh the profile before trusting what it sees.",
        [
            network(
                "stale_data",
                "**/api/env/patient_portal/profile**",
                stale_body=STALE_PROFILE_BODY,
                stale_count=1,
                behavior={"mode": "once"},
            )
        ],
    )


CLAIM_DECOYS = [
    {
        "type": "claim",
        "service_date": "2025-01-10",
        "status": "denied",
        "amount_billed": "425.00",
        "amount_covered": "0.00",
        "patient_responsibility": "425.00",
        "eob_available": False,
        "appeal_deadline": "2025-02-15T00:00:00+00:00",
        "denial_reason": "Documentation incomplete",
    },
    {
        "type": "claim",
        "service_date": "2025-02-18",
        "status": "approved",
        "amount_billed": "95.00",
        "amount_covered": "80.00",
        "patient_responsibility": "15.00",
        "eob_available": True,
        "appeal_deadline": "2025-04-01T00:00:00+00:00",
    },
    {
        "type": "message",
        "category": "billing",
        "subject": "Older claim update available",
        "body": "This archived billing thread refers to an older claim and is not the one that needs action.",
        "timestamp": "2025-02-20T08:30:00+00:00",
    },
]

MESSAGE_DECOYS = [
    {
        "type": "message",
        "category": "clinical",
        "subject": "Follow-up reminder from earlier thread",
        "body": "This older portal thread is similar in topic but does not contain the seeded action request.",
        "timestamp": "2025-02-10T09:00:00+00:00",
        "is_read": False,
    },
    {
        "type": "message",
        "category": "clinical",
        "subject": "Medication check-in note",
        "body": "This lookalike note is informational only. Verify the exact provider thread before acting.",
        "timestamp": "2025-02-12T10:15:00+00:00",
        "is_read": False,
    },
]

PHARMACY_DECOYS = [
    {
        "type": "pharmacy",
        "name": "Walgreens Express #2044",
        "address": "11 Cedar St, Springfield, IL 62705",
        "phone": "(555) 410-2204",
        "is_default": False,
        "is_mail_order": False,
    },
    {
        "type": "pharmacy",
        "name": "CVS CareMail Service",
        "address": "PO Box 5400, Tempe, AZ 85284",
        "phone": "(800) 555-4400",
        "is_default": False,
        "is_mail_order": True,
        "cost_per_90day_supply": "62.00",
    },
]

LAB_DECOYS = [
    {
        "type": "lab_result",
        "test_name": "HbA1c",
        "test_code": "4548-4",
        "collected_at": "2025-01-15T08:00:00+00:00",
        "value": "6.8",
        "unit": "%",
        "reference_range": "4.0-5.6",
        "flag": "abnormal",
        "status": "resulted",
    },
    {
        "type": "lab_result",
        "test_name": "LDL Cholesterol",
        "test_code": "2089-1",
        "collected_at": "2025-01-20T08:00:00+00:00",
        "value": "146",
        "unit": "mg/dL",
        "reference_range": "0-130",
        "flag": "abnormal",
        "status": "resulted",
    },
    {
        "type": "message",
        "category": "clinical",
        "subject": "Older results clarification",
        "body": "This archived note references prior lab work and is not the newest result requiring action.",
        "timestamp": "2025-01-21T12:00:00+00:00",
    },
]

MEDICATION_DECOYS = [
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
        "type": "prescription",
        "medication": "Albuterol Inhaler",
        "dosage": "2 puffs",
        "frequency": "as needed",
        "refills_remaining": 1,
        "last_filled": "2025-01-10T08:00:00+00:00",
        "expires_at": "2026-12-01T08:00:00+00:00",
        "status": "active",
        "interactions": [],
    },
]

PREVENTIVE_DECOYS = [
    {
        "type": "screening",
        "screening_name": "Bone Density Scan",
        "recommended_age_start": 65,
        "frequency": "every 2 years",
        "last_completed": "2025-06-01",
        "next_due": "2027-06-01",
    },
    {
        "type": "screening",
        "screening_name": "Lipid Panel",
        "recommended_age_start": 20,
        "frequency": "every 5 years",
        "last_completed": "2024-09-01",
        "next_due": "2027-09-01",
    },
    {
        "type": "immunization",
        "vaccine_name": "Influenza (Flu)",
        "administered_at": "2025-10-01T09:00:00+00:00",
        "next_due_at": "2026-12-01T09:00:00+00:00",
        "series_complete": True,
    },
]

ACCOUNT_DECOYS = (
    MESSAGE_DECOYS[:1]
    + CLAIM_DECOYS[:1]
    + PHARMACY_DECOYS[:1]
    + MEDICATION_DECOYS[:1]
    + PREVENTIVE_DECOYS[:1]
)


def claim_shadow(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "claim_shadow_v1",
        "state_tracking",
        "Older claim lookalikes and a stale billing thread appear beside the seeded records. The agent must identify the real eligible claim set rather than acting on cosmetic near-misses.",
        [seed("add_confusing_decoys", decoys=CLAIM_DECOYS)],
    )


def message_shadow(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "message_shadow_v1",
        "grounding",
        "Near-miss provider threads with similar subjects are added to the inbox. The agent must distinguish the seeded action-driving message from older, similarly worded notes.",
        [seed("add_confusing_decoys", decoys=MESSAGE_DECOYS)],
    )


def pharmacy_shadow(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "pharmacy_shadow_v1",
        "grounding",
        "The pharmacy list includes lookalike retail and mail-order entries. The agent must verify the exact pharmacy instead of choosing by brand family alone.",
        [seed("add_confusing_decoys", decoys=PHARMACY_DECOYS)],
    )


def lab_shadow(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "lab_shadow_v1",
        "grounding",
        "Older abnormal lab results and a similar results note are injected into the portal. The agent must ground its action in the seeded current lab signal, not the lookalikes.",
        [seed("add_confusing_decoys", decoys=LAB_DECOYS)],
    )


def medication_shadow(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "medication_shadow_v1",
        "state_tracking",
        "Extra active medications are added to the cabinet. The agent must keep track of the seeded target medications instead of acting on unrelated but plausible prescriptions.",
        [seed("add_confusing_decoys", decoys=MEDICATION_DECOYS)],
    )


def preventive_shadow(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "preventive_shadow_v1",
        "state_tracking",
        "The profile includes additional future-due screenings and immunizations that look relevant but are not currently actionable. The agent must separate due items from future reminders.",
        [seed("add_confusing_decoys", decoys=PREVENTIVE_DECOYS)],
    )


def account_clutter(task_id: str) -> dict[str, Any]:
    return variant(
        task_id,
        "account_clutter_v1",
        "exploration",
        "The portal is cluttered with older lookalike records across messages, claims, medications, pharmacies, and screenings. The agent must explore the full account state without confusing archival noise for the seeded task signals.",
        [seed("add_confusing_decoys", decoys=ACCOUNT_DECOYS)],
    )


FAMILY_BUILDERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "account_clutter_v1": account_clutter,
    "appointment_cancel_retry_v1": appointment_cancel_retry,
    "appointment_create_retry_v1": appointment_create_retry,
    "appointment_reschedule_retry_v1": appointment_reschedule_retry,
    "appointments_list_stale_v1": appointments_list_stale,
    "claim_appeal_retry_v1": claim_appeal_retry,
    "claim_pay_verification_v1": claim_pay_verification,
    "claims_list_stale_v1": claims_list_stale,
    "claim_shadow_v1": claim_shadow,
    "default_pharmacy_retry_v1": default_pharmacy_retry,
    "insurance_plan_transition_retry_v1": insurance_plan_transition_retry,
    "lab_shadow_v1": lab_shadow,
    "lab_trend_stale_v1": lab_trend_stale,
    "labs_list_stale_v1": labs_list_stale,
    "mark_all_read_verification_v1": mark_all_read_verification,
    "medication_refill_retry_v1": medication_refill_retry,
    "medication_renewal_retry_v1": medication_renewal_retry,
    "medications_list_stale_v1": medications_list_stale,
    "medication_shadow_v1": medication_shadow,
    "medication_transfer_retry_v1": medication_transfer_retry,
    "messages_list_stale_v1": messages_list_stale,
    "message_shadow_v1": message_shadow,
    "pharmacies_list_stale_v1": pharmacies_list_stale,
    "pharmacy_shadow_v1": pharmacy_shadow,
    "preventive_shadow_v1": preventive_shadow,
    "profile_demographics_retry_v1": profile_demographics_retry,
    "profile_insurance_retry_v1": profile_insurance_retry,
    "profile_view_stale_v1": profile_view_stale,
    "provider_search_stale_v1": provider_search_stale,
    "referrals_list_stale_v1": referrals_list_stale,
    "slot_search_stale_v1": slot_search_stale,
}


TASK_VARIANT_GROUPS: dict[str, list[str]] = {
    "account_clutter_v1": [
        "pp_care_gap_analysis",
        "pp_complete_account_audit",
        "pp_emergency_prep",
        "pp_full_care_transition",
        "pp_year_end_review",
    ],
    "appointment_cancel_retry_v1": [
        "pp_cancel_appointment",
        "pp_cancel_duplicate_appointments",
        "pp_resolve_schedule_conflicts",
    ],
    "appointment_create_retry_v1": [
        "pp_complex_scheduling",
        "pp_full_referral_chain",
        "pp_message_correct_provider",
        "pp_message_pcp",
        "pp_request_referral_preauth",
        "pp_schedule_annual_physical",
        "pp_schedule_pcp_followup",
        "pp_view_insurance",
    ],
    "appointment_reschedule_retry_v1": [
        "pp_cancel_reschedule",
        "pp_resolve_specialist_conflicts",
        "pp_setup_telehealth",
    ],
    "appointments_list_stale_v1": [
        "pp_cancel_appointment",
        "pp_cancel_duplicate_appointments",
        "pp_cancel_reschedule",
        "pp_reconcile_billing",
        "pp_resolve_schedule_conflicts",
        "pp_resolve_specialist_conflicts",
        "pp_setup_telehealth",
    ],
    "claim_appeal_retry_v1": [
        "pp_complex_claim_dispute",
        "pp_dispute_claim",
        "pp_file_claim_appeal",
    ],
    "claim_pay_verification_v1": [
        "pp_pay_claim",
    ],
    "claims_list_stale_v1": [
        "pp_claim_audit",
        "pp_complex_claim_dispute",
        "pp_message_billing",
        "pp_pay_claim",
        "pp_review_eob",
        "pp_treatment_cost_comparison",
        "pp_year_end_review",
    ],
    "claim_shadow_v1": [
        "pp_claim_audit",
        "pp_dispute_claim",
        "pp_file_claim_appeal",
        "pp_message_billing",
        "pp_reconcile_billing",
        "pp_review_eob",
        "pp_treatment_cost_comparison",
    ],
    "default_pharmacy_retry_v1": [
        "pp_update_default_pharmacy",
    ],
    "insurance_plan_transition_retry_v1": [
        "pp_insurance_plan_change",
    ],
    "lab_shadow_v1": [
        "pp_compare_lab_trends",
        "pp_lab_medication_loop",
        "pp_lab_trend_analysis",
        "pp_message_about_lab",
        "pp_read_lab_result",
        "pp_urgent_lab_response",
    ],
    "lab_trend_stale_v1": [
        "pp_compare_lab_trends",
        "pp_lab_trend_analysis",
    ],
    "labs_list_stale_v1": [
        "pp_cross_reference_labs_meds",
        "pp_lab_medication_loop",
        "pp_message_about_lab",
        "pp_read_lab_result",
        "pp_urgent_lab_response",
    ],
    "mark_all_read_verification_v1": [
        "pp_mark_all_read",
    ],
    "medication_refill_retry_v1": [
        "pp_refill_prescription",
    ],
    "medication_renewal_retry_v1": [
        "pp_request_renewal",
    ],
    "medications_list_stale_v1": [
        "pp_check_interactions",
        "pp_full_preventive_compliance",
        "pp_medication_conflict",
        "pp_message_pcp",
        "pp_refill_prescription",
        "pp_renew_expiring_rx",
        "pp_request_renewal",
    ],
    "medication_shadow_v1": [
        "pp_check_interactions",
        "pp_cross_reference_labs_meds",
        "pp_medication_conflict",
        "pp_renew_expiring_rx",
    ],
    "medication_transfer_retry_v1": [
        "pp_coordinate_rx_transfer",
        "pp_rx_cost_optimization",
        "pp_transfer_prescription",
    ],
    "messages_list_stale_v1": [
        "pp_insurance_formulary",
        "pp_mark_all_read",
        "pp_medication_reconciliation",
        "pp_multi_provider_coord",
        "pp_post_hospitalization",
        "pp_respond_to_provider",
    ],
    "message_shadow_v1": [
        "pp_insurance_formulary",
        "pp_medication_reconciliation",
        "pp_multi_provider_coord",
        "pp_post_hospitalization",
        "pp_respond_to_provider",
    ],
    "pharmacies_list_stale_v1": [
        "pp_insurance_plan_change",
        "pp_update_default_pharmacy",
    ],
    "pharmacy_shadow_v1": [
        "pp_coordinate_rx_transfer",
        "pp_rx_cost_optimization",
        "pp_transfer_prescription",
    ],
    "preventive_shadow_v1": [
        "pp_check_immunizations",
        "pp_full_preventive_compliance",
        "pp_immunization_gap_review",
        "pp_immunization_series",
        "pp_preventive_care_compliance",
        "pp_preventive_screening_review",
        "pp_wellness_visit_prep",
    ],
    "profile_demographics_retry_v1": [
        "pp_update_phone",
    ],
    "profile_insurance_retry_v1": [
        "pp_update_insurance",
    ],
    "profile_view_stale_v1": [
        "pp_complete_account_audit",
        "pp_emergency_prep",
        "pp_update_insurance",
        "pp_update_phone",
        "pp_view_insurance",
    ],
    "provider_search_stale_v1": [
        "pp_chronic_disease_setup",
        "pp_find_telehealth_cardiologist",
        "pp_provider_transition",
        "pp_schedule_new_specialist",
    ],
    "referrals_list_stale_v1": [
        "pp_full_referral_chain",
        "pp_message_correct_provider",
        "pp_multi_condition_mgmt",
        "pp_multi_referral_chain",
        "pp_post_accident_coordination",
        "pp_pre_surgery_clearance",
        "pp_prior_auth_marathon",
        "pp_request_referral_preauth",
        "pp_specialist_roundrobin",
    ],
    "slot_search_stale_v1": [
        "pp_care_gap_analysis",
        "pp_check_immunizations",
        "pp_chronic_disease_setup",
        "pp_complex_scheduling",
        "pp_find_telehealth_cardiologist",
        "pp_full_care_transition",
        "pp_immunization_gap_review",
        "pp_immunization_series",
        "pp_multi_condition_mgmt",
        "pp_multi_referral_chain",
        "pp_post_accident_coordination",
        "pp_pre_surgery_clearance",
        "pp_preventive_care_compliance",
        "pp_preventive_screening_review",
        "pp_prior_auth_marathon",
        "pp_provider_transition",
        "pp_schedule_annual_physical",
        "pp_schedule_new_specialist",
        "pp_schedule_pcp_followup",
        "pp_specialist_roundrobin",
        "pp_wellness_visit_prep",
    ],
}


def build_assignment(tasks: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    assignment: dict[str, list[str]] = {}
    for family, task_ids in TASK_VARIANT_GROUPS.items():
        for task_id in task_ids:
            families = assignment.setdefault(task_id, [])
            if family in families:
                raise SystemExit(f"Task {task_id} assigned twice to {family}")
            families.append(family)

    missing = sorted(set(tasks) - set(assignment))
    extra = sorted(set(assignment) - set(tasks))
    if missing or extra:
        raise SystemExit(f"Coverage mismatch. missing={missing} extra={extra}")

    wrong_counts = {
        task_id: families
        for task_id, families in assignment.items()
        if len(families) != 2
    }
    if wrong_counts:
        raise SystemExit(f"Each task must have exactly two degradation families. bad={wrong_counts}")
    return assignment


def write_variant(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, width=1000))


def write_audit(rows: list[dict[str, str]]) -> None:
    primitive_counts = Counter(row["primitive"] for row in rows)
    family_counts = Counter(row["family"] for row in rows)
    task_ids = sorted({row["task_id"] for row in rows})
    lines = [
        "# Patient Portal Degradation Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Source standard:",
        "- `breakingweb/share_docs/TASK_GENERATION_STANDARD.md`",
        "- `breakingweb/share_docs/BATCH_TASK_GENERATION_STANDARD.md`",
        "",
        "Summary:",
        f"- Task count: {len(task_ids)}",
        f"- Variant count: {len(rows)}",
        f"- Variants per task: {len(rows) // max(len(task_ids), 1)}",
        f"- Primitive counts: {dict(sorted(primitive_counts.items()))}",
        f"- Family counts: {dict(sorted(family_counts.items()))}",
        "",
        "Task matrix:",
        "",
        "| Task | Variant | Primitive | Family |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['task_id']}` | `{row['variant_id']}` | `{row['primitive']}` | `{row['family']}` |"
        )
    AUDIT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    tasks = load_tasks()
    assignment = build_assignment(tasks)

    for existing in VARIANTS_DIR.glob("pp_*.yaml"):
        existing.unlink()

    rows: list[dict[str, str]] = []
    for task_id in sorted(tasks):
        for family in assignment[task_id]:
            builder = FAMILY_BUILDERS[family]
            data = builder(task_id)
            out_path = VARIANTS_DIR / f"{data['variant_id']}.yaml"
            write_variant(out_path, data)
            rows.append(
                {
                    "task_id": task_id,
                    "variant_id": data["variant_id"],
                    "primitive": data["target_primitive"],
                    "family": family,
                }
            )

    write_audit(rows)
    print(f"Generated {len(rows)} patient-portal variants in {VARIANTS_DIR}")
    print(f"Wrote audit summary to {AUDIT_PATH}")


if __name__ == "__main__":
    main()
