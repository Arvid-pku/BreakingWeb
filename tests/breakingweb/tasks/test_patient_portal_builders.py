"""Determinism and correctness tests for Patient Portal seed builders."""

import random
from datetime import datetime, timezone

from breakingweb.backend.seeder import FakeDataGenerator
from breakingweb.tasks._seed_builders_patient_portal import (
    PATIENT_PORTAL_BUILDER_REGISTRY,
    PatientPortalSeedContext,
)


def _make_ctx(seed: int = 42) -> PatientPortalSeedContext:
    rng = random.Random(seed)
    fake = FakeDataGenerator(seed)
    now = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    return PatientPortalSeedContext(seed=seed, rng=rng, fake=fake, now=now, base={})


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

def test_all_builders_registered():
    expected = {
        "patient_profile", "provider_directory", "pharmacy_list",
        "appointment_history", "prescription_cabinet", "lab_results_panel",
        "message_threads", "referral_chain", "insurance_claims", "immunization_record",
    }
    assert expected.issubset(set(PATIENT_PORTAL_BUILDER_REGISTRY.keys()))


# ---------------------------------------------------------------------------
# patient_profile
# ---------------------------------------------------------------------------

def test_patient_profile_determinism():
    out1 = PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](_make_ctx(42), {"conditions": ["Diabetes"]})
    out2 = PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](_make_ctx(42), {"conditions": ["Diabetes"]})
    assert out1["patient_name"] == out2["patient_name"]
    assert out1["member_id"] == out2["member_id"]


def test_patient_profile_creates_patient():
    ctx = _make_ctx(42)
    out = PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {"conditions": ["Hypertension"]})
    assert "patient" in ctx.base
    assert ctx.base["patient"]["pcp_id"] == "prov_1"
    assert out["pcp_id"] == "prov_1"
    assert out["conditions_list"] == ["Hypertension"]


def test_patient_profile_insurance_tiers():
    for tier, expected_copay in [("basic", "50"), ("standard", "30"), ("premium", "15")]:
        ctx = _make_ctx(99)
        PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {"insurance_tier": tier})
        assert ctx.base["patient"]["insurance_plan"]["copay"] == expected_copay


def test_patient_profile_screenings():
    ctx = _make_ctx(42)
    out = PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    screenings = ctx.base["patient"]["applicable_screenings"]
    assert len(screenings) >= 1
    assert len(out["applicable_screening_names"]) == len(screenings)


# ---------------------------------------------------------------------------
# provider_directory
# ---------------------------------------------------------------------------

def test_provider_directory_creates_pcp():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {"conditions": ["Hypertension"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "cardiology"]})
    pcp_ids = out["providers_by_specialty"].get("pcp", [])
    assert len(pcp_ids) >= 1
    # PCP ID should match patient.pcp_id
    assert ctx.base["patient"]["pcp_id"] in pcp_ids


def test_provider_directory_determinism():
    def _run(seed: int):
        ctx = _make_ctx(seed)
        PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
        return PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "cardiology"]})

    out1 = _run(42)
    out2 = _run(42)
    assert out1["provider_ids"] == out2["provider_ids"]


def test_provider_billing_not_accepting():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "billing"]})
    billing_prov = next(p for p in ctx.base["providers"] if p["specialty"] == "billing")
    assert billing_prov["accepting_new"] is False


def test_provider_slots_office_hours():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    prov = ctx.base["providers"][0]
    assert 3 <= len(prov["available_slots"]) <= 6


# ---------------------------------------------------------------------------
# pharmacy_list
# ---------------------------------------------------------------------------

def test_pharmacy_list_default():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["pharmacy_list"](ctx, {"count": 2})
    assert out["default_pharmacy_id"] != ""
    default = next(p for p in ctx.base["pharmacies"] if p["id"] == out["default_pharmacy_id"])
    assert default["is_default"] is True


def test_pharmacy_list_mail_order():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["pharmacy_list"](ctx, {"count": 2, "include_mail_order": True})
    assert out["mail_order_pharmacy_id"] is not None
    mail = next(p for p in ctx.base["pharmacies"] if p["id"] == out["mail_order_pharmacy_id"])
    assert mail["is_mail_order"] is True


def test_pharmacy_updates_patient():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["pharmacy_list"](ctx, {"count": 2})
    assert ctx.base["patient"]["pharmacy_ids"] == out["pharmacy_ids"]


# ---------------------------------------------------------------------------
# prescription_cabinet
# ---------------------------------------------------------------------------

def test_prescription_cabinet_zero_refill():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    PATIENT_PORTAL_BUILDER_REGISTRY["pharmacy_list"](ctx, {"count": 2})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["prescription_cabinet"](ctx, {"active_count": 3, "zero_refill_count": 1})
    assert out.get("zero_refill_rx_id") is not None
    # Verify the zero-refill Rx actually has 0 refills
    zero_rx = next(
        (rx for rx in ctx.base["prescriptions"] if rx["id"] == out["zero_refill_rx_id"]),
        None,
    )
    assert zero_rx is not None
    assert zero_rx["refills_remaining"] == 0


def test_prescription_cabinet_interactions():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    PATIENT_PORTAL_BUILDER_REGISTRY["pharmacy_list"](ctx, {"count": 2})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["prescription_cabinet"](
        ctx, {"active_count": 3, "interaction_pair": True}
    )
    assert len(out["interacting_rx_ids"]) == 2
    assert len(out["interacting_medications"]) == 2


# ---------------------------------------------------------------------------
# lab_results_panel
# ---------------------------------------------------------------------------

def test_lab_results_panel_counts():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["lab_results_panel"](
        ctx, {"resulted_count": 4, "pending_count": 1, "abnormal_count": 1}
    )
    assert len(out["resulted_lab_ids"]) == 4
    assert len(out["pending_lab_ids"]) == 1
    assert len(out["abnormal_lab_ids"]) >= 1


def test_lab_results_panel_trend():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["lab_results_panel"](
        ctx, {"resulted_count": 1, "trend_test": "HbA1c", "trend_values": ["5.8", "6.2", "6.9"]}
    )
    assert out["trend_test_name"] == "HbA1c"
    assert len(out["trend_lab_ids"]) == 3


def test_lab_results_panel_critical():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["lab_results_panel"](
        ctx, {"resulted_count": 2, "critical_count": 1}
    )
    assert out["critical_lab_id"] is not None
    crit = next(l for l in ctx.base["lab_results"] if l["id"] == out["critical_lab_id"])
    assert crit["flag"] == "critical"


# ---------------------------------------------------------------------------
# message_threads
# ---------------------------------------------------------------------------

def test_message_threads_unread():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["message_threads"](
        ctx, {"thread_count": 3, "unread_count": 2}
    )
    assert len(out["thread_ids"]) == 3
    # Should have at most unread_count unread messages
    assert len(out["unread_msg_ids"]) <= 2


def test_message_threads_billing():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "billing"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["message_threads"](
        ctx, {"thread_count": 3, "include_billing": True}
    )
    assert out["billing_thread_id"] is not None


# ---------------------------------------------------------------------------
# referral_chain
# ---------------------------------------------------------------------------

def test_referral_chain_statuses():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "cardiology"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["referral_chain"](
        ctx, {"approved_count": 1, "pending_count": 1, "denied_count": 1}
    )
    assert len(out["approved_ref_ids"]) == 1
    assert len(out["pending_ref_ids"]) == 1
    assert len(out["denied_ref_ids"]) == 1


def test_referral_chain_prior_auth():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "cardiology"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["referral_chain"](
        ctx, {"approved_count": 1, "with_prior_auth": True}
    )
    assert out["prior_auth_ref_id"] is not None
    ref = next(r for r in ctx.base["referrals"] if r["id"] == out["prior_auth_ref_id"])
    assert ref["prior_auth_required"] is True
    assert ref["prior_auth_status"] == "approved"


# ---------------------------------------------------------------------------
# insurance_claims
# ---------------------------------------------------------------------------

def test_insurance_claims_statuses():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    PATIENT_PORTAL_BUILDER_REGISTRY["appointment_history"](ctx, {"completed_count": 3})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["insurance_claims"](
        ctx, {"approved_count": 1, "denied_count": 1, "processing_count": 1}
    )
    assert len(out["approved_claim_ids"]) == 1
    assert len(out["denied_claim_ids"]) == 1
    assert len(out["processing_claim_ids"]) == 1


def test_insurance_claims_appealable():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    PATIENT_PORTAL_BUILDER_REGISTRY["appointment_history"](ctx, {"completed_count": 2})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["insurance_claims"](
        ctx, {"denied_count": 1, "near_appeal_deadline": True}
    )
    assert out["appealable_claim_id"] is not None


# ---------------------------------------------------------------------------
# immunization_record
# ---------------------------------------------------------------------------

def test_immunization_record_counts():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["immunization_record"](
        ctx, {"completed_count": 3, "due_count": 1}
    )
    assert len(out["completed_imm_ids"]) == 3
    assert len(out["due_imm_ids"]) == 1
    assert len(out["due_vaccine_names"]) >= 1


def test_immunization_record_incomplete_series():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp"]})
    out = PATIENT_PORTAL_BUILDER_REGISTRY["immunization_record"](
        ctx, {"completed_count": 2, "series_incomplete": True}
    )
    assert out["incomplete_series_imm_id"] is not None
    imm = next(i for i in ctx.base["immunizations"] if i["id"] == out["incomplete_series_imm_id"])
    assert imm["series_complete"] is False


def test_immunization_provider_has_slots():
    ctx = _make_ctx(42)
    PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {})
    PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "cardiology"]})
    PATIENT_PORTAL_BUILDER_REGISTRY["immunization_record"](ctx, {"completed_count": 2, "due_count": 1})
    # Every immunization's administering_provider_id must be in providers
    prov_ids = {p["id"] for p in ctx.base["providers"]}
    for imm in ctx.base["immunizations"]:
        assert imm["administering_provider_id"] in prov_ids


# ---------------------------------------------------------------------------
# Cross-builder determinism
# ---------------------------------------------------------------------------

def test_full_pipeline_determinism():
    """Run all builders in dependency order twice with same seed -- output must match."""
    def _run(seed: int):
        ctx = _make_ctx(seed)
        PATIENT_PORTAL_BUILDER_REGISTRY["patient_profile"](ctx, {"conditions": ["Diabetes"]})
        PATIENT_PORTAL_BUILDER_REGISTRY["provider_directory"](ctx, {"specialties": ["pcp", "cardiology"]})
        PATIENT_PORTAL_BUILDER_REGISTRY["pharmacy_list"](ctx, {"count": 2})
        PATIENT_PORTAL_BUILDER_REGISTRY["appointment_history"](ctx, {"upcoming_count": 2, "completed_count": 2})
        PATIENT_PORTAL_BUILDER_REGISTRY["prescription_cabinet"](ctx, {"active_count": 3, "zero_refill_count": 1})
        PATIENT_PORTAL_BUILDER_REGISTRY["lab_results_panel"](ctx, {"resulted_count": 3, "pending_count": 1})
        PATIENT_PORTAL_BUILDER_REGISTRY["message_threads"](ctx, {"thread_count": 2, "unread_count": 1})
        PATIENT_PORTAL_BUILDER_REGISTRY["referral_chain"](ctx, {"approved_count": 1})
        PATIENT_PORTAL_BUILDER_REGISTRY["insurance_claims"](ctx, {"approved_count": 1})
        PATIENT_PORTAL_BUILDER_REGISTRY["immunization_record"](ctx, {"completed_count": 2, "due_count": 1})
        return ctx.base

    base1 = _run(42)
    base2 = _run(42)

    # Compare key entity counts
    for key in ("providers", "appointments", "prescriptions", "lab_results",
                "messages", "referrals", "claims", "immunizations", "pharmacies"):
        assert len(base1.get(key, [])) == len(base2.get(key, []))

    # Compare entity IDs
    for key in ("providers", "appointments", "prescriptions", "lab_results",
                "messages", "referrals", "claims", "immunizations", "pharmacies"):
        ids1 = [e["id"] for e in base1.get(key, [])]
        ids2 = [e["id"] for e in base2.get(key, [])]
        assert ids1 == ids2
