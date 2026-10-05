"""Composable seed builder framework for the Patient Portal environment.

Provides :class:`PatientPortalSeedContext` and a registry of builder
functions that generate deterministic healthcare test data.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from breakingweb.backend.models.patient_portal import (
    Appointment,
    ClinicalMessage,
    EmergencyContact,
    Immunization,
    InsuranceClaim,
    InsurancePlan,
    LabResult,
    Pharmacy,
    Prescription,
    Provider,
    Referral,
    ScreeningRecommendation,
    SlotInfo,
)


# ---------------------------------------------------------------------------
# ResolvedActor (shared shape with Gmail / Robinhood)
# ---------------------------------------------------------------------------

@dataclass
class ResolvedActor:
    """A named person with a deterministically-generated email address."""

    name: str
    email: str
    first_name: str


# ---------------------------------------------------------------------------
# Hardcoded provider name templates by specialty
# ---------------------------------------------------------------------------

_PROVIDER_NAMES: dict[str, list[str]] = {
    "pcp": [
        "Dr. Sarah Mitchell", "Dr. David Chen", "Dr. Lisa Patel",
        "Dr. James Rivera", "Dr. Emily Brooks",
    ],
    "cardiology": [
        "Dr. Robert Kim", "Dr. Ana Rodriguez", "Dr. Michael Torres",
        "Dr. Patricia Nguyen", "Dr. Steven Wright",
    ],
    "endocrinology": [
        "Dr. Karen Singh", "Dr. Thomas Garcia", "Dr. Maria Lopez",
        "Dr. Brian Morris", "Dr. Jennifer Adams",
    ],
    "dermatology": [
        "Dr. Sandra Lee", "Dr. Andrew Park", "Dr. Rachel Green",
        "Dr. Kevin Pham", "Dr. Laura Martinez",
    ],
    "orthopedics": [
        "Dr. William Clark", "Dr. Diana Flores", "Dr. Mark Sullivan",
        "Dr. Christine Yang", "Dr. Peter Walsh",
    ],
    "neurology": [
        "Dr. Helen Cho", "Dr. Daniel Murphy", "Dr. Samantha Price",
        "Dr. Richard Tanaka", "Dr. Olivia Bennett",
    ],
    "radiology": [
        "Dr. Paul Hoffman", "Dr. Natalie Russo", "Dr. Gregory Lin",
        "Dr. Catherine Stone", "Dr. Derek Foster",
    ],
    "phlebotomy": [
        "Outpatient Lab Services", "Clinical Laboratory",
        "Diagnostic Lab Center", "Pre-Op Lab Suite",
    ],
    "billing": [
        "Billing Department", "Claims Office", "Patient Accounts",
    ],
    "admin": [
        "Front Desk", "Patient Services", "Medical Records",
    ],
}

_SPECIALTY_DEPARTMENTS: dict[str, str] = {
    "pcp": "Primary Care",
    "cardiology": "Cardiology",
    "endocrinology": "Endocrinology",
    "dermatology": "Dermatology",
    "orthopedics": "Orthopedics",
    "neurology": "Neurology",
    "radiology": "Radiology",
    "phlebotomy": "Laboratory",
    "billing": "Billing",
    "admin": "Administration",
}

# ---------------------------------------------------------------------------
# Screening pools
# ---------------------------------------------------------------------------

_SCREENING_ALL: list[dict[str, Any]] = [
    {"name": "Colonoscopy", "min_age": 45, "frequency": "every 10 years"},
    {"name": "Lipid Panel", "min_age": 20, "frequency": "every 5 years"},
    {"name": "Blood Pressure Screening", "min_age": 18, "frequency": "annually"},
    {"name": "Diabetes Screening", "min_age": 35, "frequency": "every 3 years"},
    {"name": "Lung Cancer Screening", "min_age": 50, "frequency": "annually"},
]

_SCREENING_FEMALE: list[dict[str, Any]] = [
    {"name": "Mammogram", "min_age": 40, "frequency": "every 2 years"},
    {"name": "Cervical Cancer Screening", "min_age": 21, "frequency": "every 3 years"},
    {"name": "Bone Density Scan", "min_age": 65, "frequency": "every 2 years"},
]

# ---------------------------------------------------------------------------
# Medication pool
# ---------------------------------------------------------------------------

_MEDICATIONS: list[dict[str, Any]] = [
    {"name": "Lisinopril 10mg", "dosage": "10mg", "frequency": "once daily"},
    {"name": "Metformin 500mg", "dosage": "500mg", "frequency": "twice daily"},
    {"name": "Atorvastatin 20mg", "dosage": "20mg", "frequency": "once daily at bedtime"},
    {"name": "Amlodipine 5mg", "dosage": "5mg", "frequency": "once daily"},
    {"name": "Losartan 50mg", "dosage": "50mg", "frequency": "once daily"},
    {"name": "Warfarin 5mg", "dosage": "5mg", "frequency": "once daily"},
    {"name": "Omeprazole 20mg", "dosage": "20mg", "frequency": "once daily before breakfast"},
    {"name": "Levothyroxine 75mcg", "dosage": "75mcg", "frequency": "once daily on empty stomach"},
    {"name": "Gabapentin 300mg", "dosage": "300mg", "frequency": "three times daily"},
    {"name": "Sertraline 50mg", "dosage": "50mg", "frequency": "once daily"},
    # Extra non-interacting maintenance meds. Additive: every existing task pins
    # by name or uses a smaller active_count, so widening the pool only matters
    # for tasks that explicitly request a larger active/expired cabinet (e.g.
    # pp_check_interactions, which needs enough distinct meds to seat 11 active +
    # 3 expired prescriptions plus the interaction-pair members).
    {"name": "Hydrochlorothiazide 25mg", "dosage": "25mg", "frequency": "once daily"},
    {"name": "Pantoprazole 40mg", "dosage": "40mg", "frequency": "once daily before breakfast"},
    {"name": "Montelukast 10mg", "dosage": "10mg", "frequency": "once daily at bedtime"},
    {"name": "Escitalopram 10mg", "dosage": "10mg", "frequency": "once daily"},
    {"name": "Rosuvastatin 10mg", "dosage": "10mg", "frequency": "once daily at bedtime"},
    {"name": "Cetirizine 10mg", "dosage": "10mg", "frequency": "once daily"},
]

# Known drug interaction pairs
_INTERACTION_PAIRS: list[tuple[str, str]] = [
    ("Warfarin 5mg", "Atorvastatin 20mg"),
    ("Lisinopril 10mg", "Losartan 50mg"),
    ("Metformin 500mg", "Gabapentin 300mg"),
]

# ---------------------------------------------------------------------------
# Lab test pool
# ---------------------------------------------------------------------------

_LAB_TESTS: list[dict[str, Any]] = [
    {"name": "HbA1c", "code": "4548-4", "unit": "%", "ref": "4.0-5.6", "normal": "5.2", "abnormal": "7.1", "critical": "10.5"},
    {"name": "LDL Cholesterol", "code": "2089-1", "unit": "mg/dL", "ref": "0-130", "normal": "110", "abnormal": "155", "critical": "220"},
    {"name": "HDL Cholesterol", "code": "2085-9", "unit": "mg/dL", "ref": "40-60", "normal": "52", "abnormal": "32", "critical": "22"},
    {"name": "Triglycerides", "code": "2571-8", "unit": "mg/dL", "ref": "0-150", "normal": "120", "abnormal": "210", "critical": "550"},
    {"name": "Total Cholesterol", "code": "2093-3", "unit": "mg/dL", "ref": "0-200", "normal": "180", "abnormal": "245", "critical": "320"},
    {"name": "TSH", "code": "3016-3", "unit": "mIU/L", "ref": "0.4-4.0", "normal": "2.1", "abnormal": "6.8", "critical": "15.0"},
    {"name": "Creatinine", "code": "2160-0", "unit": "mg/dL", "ref": "0.6-1.2", "normal": "0.9", "abnormal": "1.8", "critical": "4.5"},
    {"name": "Glucose Fasting", "code": "1558-6", "unit": "mg/dL", "ref": "70-100", "normal": "88", "abnormal": "135", "critical": "350"},
    {"name": "INR", "code": "6301-6", "unit": "", "ref": "0.8-1.2", "normal": "1.0", "abnormal": "2.8", "critical": "5.0"},
    {"name": "CBC WBC", "code": "6690-2", "unit": "10^3/uL", "ref": "4.5-11.0", "normal": "7.2", "abnormal": "14.5", "critical": "25.0"},
]

_LIPID_PANEL_COMPONENTS = ["LDL Cholesterol", "HDL Cholesterol", "Triglycerides", "Total Cholesterol"]

# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------

_CLINICAL_SUBJECTS: list[str] = [
    "Follow-up on recent lab results",
    "Medication adjustment recommendation",
    "Appointment reminder",
    "Test results available",
    "Care plan update",
]

_BILLING_SUBJECTS: list[str] = [
    "Statement for recent visit",
    "Insurance claim update",
    "Outstanding balance notification",
]

_RX_RENEWAL_SUBJECTS: list[str] = [
    "Prescription renewal request",
    "Refill authorization needed",
    "Medication renewal due",
]

_BODY_CONTEXT_SUBJECTS: dict[str, str] = {
    "discharge_summary": "Discharge Summary",
    "formulary_info": "Formulary Coverage Update",
    "generic_alternative": "Generic Alternative Recommendation",
    "bp_medication_adjustment": "Blood Pressure Medication Adjustment",
    "referral_details": "Specialist Referral Information",
    "pharmacy_closure_notice": "Mail-Order Pharmacy Closing — Action Needed",
}

# Denial reason pool for EOB claims
_EOB_DENIAL_REASONS: list[str] = [
    "Service not medically necessary",
    "Out-of-network provider",
    "Missing prior authorization",
    "Duplicate claim submission",
    "Procedure not covered under plan",
]

# ---------------------------------------------------------------------------
# Vaccine pool
# ---------------------------------------------------------------------------

_VACCINES: list[dict[str, Any]] = [
    # `short_name` is used by canonical_diff predicates that try to match the
    # vaccine name in an appointment reason. The full `name` includes a
    # parenthetical (e.g. "Tdap (Tetanus)") which agents rarely repeat
    # verbatim — the short form is the bare form an agent is likely to type
    # ("Tdap", "Flu"), and is what task evaluators should match against.
    {"name": "Influenza (Flu)", "short_name": "Influenza", "series": False, "annual": True},
    {"name": "COVID-19 Booster", "short_name": "COVID-19", "series": False, "annual": True},
    {"name": "Tdap (Tetanus)", "short_name": "Tdap", "series": False, "annual": False, "interval_years": 10},
    {"name": "Shingles (Shingrix)", "short_name": "Shingles", "series": True, "doses": 2, "interval_months": 2},
    {"name": "Hepatitis B", "short_name": "Hepatitis B", "series": True, "doses": 3, "interval_months": 1},
    {"name": "Pneumococcal (PCV20)", "short_name": "Pneumococcal", "series": False, "annual": False, "min_age": 65},
    {"name": "HPV", "short_name": "HPV", "series": True, "doses": 3, "interval_months": 2, "max_age": 45},
]

# ---------------------------------------------------------------------------
# Pharmacy pool
# ---------------------------------------------------------------------------

_PHARMACY_TEMPLATES: list[dict[str, str]] = [
    {"name": "CVS Pharmacy #4821", "address": "1200 Market St, Springfield, IL 62701", "phone": "(555) 234-5678"},
    {"name": "Walgreens #09832", "address": "450 Oak Ave, Springfield, IL 62702", "phone": "(555) 345-6789"},
    {"name": "CVS Pharmacy #4833", "address": "890 Pine Blvd, Springfield, IL 62703", "phone": "(555) 456-7890"},
    {"name": "Rite Aid #1155", "address": "320 Elm St, Springfield, IL 62704", "phone": "(555) 567-8901"},
]

_MAIL_ORDER_PHARMACY: dict[str, str] = {
    "name": "Express Scripts Mail Order",
    "address": "PO Box 21100, Tempe, AZ 85285",
    "phone": "(800) 555-1234",
}

# Additional mail-order pharmacy templates used when ``mail_order_count`` > 1.
# The first mail-order pharmacy always uses ``_MAIL_ORDER_PHARMACY`` (the
# legacy single-entry default); these supply distinct names/addresses for the
# 2nd+ entries so a cost-comparison task can seed several mail-order options
# the agent must price-compare. Order is fixed (not shuffled) so the
# cheapest-by-cost answer depends purely on the rng-drawn cost values, not on
# template ordering.
_EXTRA_MAIL_ORDER_PHARMACIES: list[dict[str, str]] = [
    {
        "name": "OptumRx Home Delivery",
        "address": "PO Box 30050, Salt Lake City, UT 84130",
        "phone": "(800) 555-2233",
    },
    {
        "name": "CarePlus Mail Pharmacy",
        "address": "PO Box 9100, Orlando, FL 32819",
        "phone": "(800) 555-3344",
    },
    {
        "name": "Cornerstone Mail-Order Rx",
        "address": "PO Box 4400, Columbus, OH 43215",
        "phone": "(800) 555-4455",
    },
]


# ---------------------------------------------------------------------------
# PatientPortalSeedContext
# ---------------------------------------------------------------------------

class PatientPortalSeedContext:
    """Mutable accumulator threaded through every Patient Portal builder step."""

    def __init__(
        self,
        seed: int,
        rng: random.Random,
        fake: Any,
        now: datetime,
        base: dict[str, Any],
    ) -> None:
        self.seed = seed
        self.rng = rng
        self.fake = fake
        self.now = now
        self.base = base
        self.actors: dict[str, ResolvedActor] = {}
        self.outputs: dict[str, Any] = {}
        self.counters: dict[str, int] = {}

    def next_id(self, prefix: str) -> str:
        """Return a monotonically increasing id like ``prov_1``."""
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]}"

    def get_provider_by_specialty(self, specialty: str) -> dict | None:
        """Return the first provider dict matching *specialty*, or None."""
        for prov in self.base.get("providers", []):
            if prov.get("specialty") == specialty:
                return prov
        return None

    def get_pcp(self) -> dict:
        """Return the PCP provider dict.  Raises if none found."""
        pcp_id = self.base.get("patient", {}).get("pcp_id")
        if pcp_id:
            for prov in self.base.get("providers", []):
                if prov.get("id") == pcp_id:
                    return prov
        raise ValueError("No PCP found in base state")

    def email_for_name(self, name: str, domain: str = "thornton.com") -> str:
        local = "".join(
            ch.lower() for ch in name if ch.isalnum() or ch == " "
        ).replace(" ", ".")
        local = ".".join(part for part in local.split(".") if part) or "contact"
        return f"{local}@{domain}"

    def resolve_actor(
        self,
        key: str,
        domain: str = "thornton.com",
        name: str | None = None,
        is_vip: bool = False,
    ) -> ResolvedActor:
        """Generate a deterministic actor and cache it under *key*."""
        if key in self.actors:
            return self.actors[key]
        if name is None:
            name = self.fake.name()
        first_name = name.split()[0]
        email = self.email_for_name(name, domain)
        actor = ResolvedActor(name=name, email=email, first_name=first_name)
        self.actors[key] = actor
        return actor


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------

BuilderFn = Callable[["PatientPortalSeedContext", dict[str, Any]], dict[str, Any]]

PATIENT_PORTAL_BUILDER_REGISTRY: dict[str, BuilderFn] = {}


def _register(name: str) -> Callable[[BuilderFn], BuilderFn]:
    def decorator(fn: BuilderFn) -> BuilderFn:
        PATIENT_PORTAL_BUILDER_REGISTRY[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# 1. patient_profile
# ---------------------------------------------------------------------------

_INSURANCE_TIERS: dict[str, dict[str, Any]] = {
    "basic": {"copay": Decimal("50"), "deductible": Decimal("5000"), "plan_prefix": "Bronze"},
    "standard": {"copay": Decimal("30"), "deductible": Decimal("2000"), "plan_prefix": "Silver"},
    "premium": {"copay": Decimal("15"), "deductible": Decimal("500"), "plan_prefix": "Gold"},
}


@_register("patient_profile")
def build_patient_profile(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create the patient singleton, insurance, emergency contact, and PCP assignment.

    Params: allergies (list[str]), conditions (list[str]), insurance_tier (str),
            overdue_screening_count (int) — force this many screenings to be overdue
    Outputs: patient_name, pcp_id, pcp_name, insurance_plan_name, member_id,
             group_number, conditions_list, allergies_list, applicable_screening_names,
             overdue_screening_names (the subset whose next_due has already passed)
    """
    allergies = params.get("allergies", [])
    conditions = params.get("conditions", [])
    tier_key = params.get("insurance_tier", "standard")
    tier = _INSURANCE_TIERS.get(tier_key, _INSURANCE_TIERS["standard"])
    overdue_screening_count: int = params.get("overdue_screening_count", 0)

    # Generate patient demographics
    patient_name = ctx.fake.name()
    sex = ctx.rng.choice(["male", "female"])
    # Age between 25 and 75
    age = ctx.rng.randint(25, 75)
    dob = date(ctx.now.year - age, ctx.rng.randint(1, 12), ctx.rng.randint(1, 28))
    phone = f"(555) {ctx.rng.randint(100, 999)}-{ctx.rng.randint(1000, 9999)}"
    email = ctx.email_for_name(patient_name)

    # Emergency contact
    ec_name = ctx.fake.name()
    ec_phone = f"(555) {ctx.rng.randint(100, 999)}-{ctx.rng.randint(1000, 9999)}"
    ec_rel = ctx.rng.choice(["Spouse", "Parent", "Sibling", "Child", "Friend"])

    # --- Deterministic on-file overrides (verification-difficulty lever) ---
    # Verification tasks like pp_update_phone need the value already ON FILE to
    # be a VISUAL LOOKALIKE of the new target (e.g. transposed last two digits),
    # so an agent that "trusts the displayed value" and re-saves what it sees,
    # or hallucinates a near-identical number, trips the high/critical
    # "phone != initial.phone" disambiguation constraints. These params let a
    # task pin the on-file phone/email and the OLD emergency-contact identity
    # to deterministic lookalikes instead of random values. They never change
    # the mutation surface; they only make the seeded baseline a deliberate
    # near-miss of the target the agent must write.
    if params.get("phone") is not None:
        phone = str(params["phone"])
    if params.get("email") is not None:
        email = str(params["email"])
    _ec_override = params.get("emergency_contact")
    if isinstance(_ec_override, dict):
        if _ec_override.get("name") is not None:
            ec_name = str(_ec_override["name"])
        if _ec_override.get("phone") is not None:
            ec_phone = str(_ec_override["phone"])
        if _ec_override.get("relationship") is not None:
            ec_rel = str(_ec_override["relationship"])

    # Insurance plan
    plan_name = f"{tier['plan_prefix']} {ctx.rng.choice(['PPO', 'HMO', 'EPO'])} Plan"
    member_id = f"MBR-{ctx.rng.randint(1000000, 9999999)}"
    group_number = f"GRP-{ctx.rng.randint(10000, 99999)}"
    deductible_met = Decimal(str(ctx.rng.randint(0, int(tier['deductible']))))

    # PCP assignment -- the PCP provider will be created by provider_directory,
    # but we reserve the ID here for cross-reference.
    pcp_id = "prov_1"

    # Build applicable screenings based on age and sex
    eligible: list[dict[str, Any]] = []
    for s in _SCREENING_ALL:
        if age >= s["min_age"]:
            eligible.append(s)
    if sex == "female":
        for s in _SCREENING_FEMALE:
            if age >= s["min_age"]:
                eligible.append(s)

    # Pick 3-5 from eligible
    num_screenings = min(len(eligible), ctx.rng.randint(3, 5))
    ctx.rng.shuffle(eligible)
    selected_screenings = eligible[:num_screenings]

    screening_models: list[dict[str, Any]] = []
    overdue_forced = 0
    for idx, s in enumerate(selected_screenings):
        # Force overdue for the first `overdue_screening_count` screenings
        force_overdue = overdue_forced < overdue_screening_count
        if force_overdue:
            # Make last_completed far enough in the past that next_due has already passed
            freq_years = _parse_frequency_years(s["frequency"])
            years_ago = freq_years + ctx.rng.randint(1, 2)
            last_completed = date(ctx.now.year - years_ago, ctx.rng.randint(1, 12), ctx.rng.randint(1, 28))
            next_due = date(last_completed.year + freq_years, last_completed.month, last_completed.day)
            overdue_forced += 1
        elif ctx.rng.random() > 0.3:
            # Random last_completed in the past 0-5 years (some may be None)
            years_ago = ctx.rng.randint(0, 5)
            last_completed = date(ctx.now.year - years_ago, ctx.rng.randint(1, 12), ctx.rng.randint(1, 28))
            # Compute next_due based on frequency
            freq_years = _parse_frequency_years(s["frequency"])
            next_due = date(last_completed.year + freq_years, last_completed.month, last_completed.day)
        else:
            last_completed = None
            next_due = date(ctx.now.year, ctx.rng.randint(1, 12), ctx.rng.randint(1, 28))

        screening_models.append({
            "screening_name": s["name"],
            "recommended_age_start": s["min_age"],
            "frequency": s["frequency"],
            "last_completed": last_completed.isoformat() if last_completed else None,
            "next_due": next_due.isoformat() if next_due else None,
        })

    patient_dict = {
        "id": "patient_1",
        "name": patient_name,
        "sex": sex,
        "dob": dob.isoformat(),
        "phone": phone,
        "email": email,
        "insurance_plan": {
            "plan_name": plan_name,
            "member_id": member_id,
            "group_number": group_number,
            "copay": str(tier["copay"]),
            "deductible": str(tier["deductible"]),
            "deductible_met": str(deductible_met),
        },
        "pcp_id": pcp_id,
        "allergies": allergies,
        "conditions": conditions,
        "pharmacy_ids": [],
        "emergency_contact": {
            "name": ec_name,
            "phone": ec_phone,
            "relationship": ec_rel,
        },
        "applicable_screenings": screening_models,
    }

    ctx.base["patient"] = patient_dict
    # B-1: opt-in confirmation workflow. Specialties listed here trigger the
    # create_appointment route to land new appointments in
    # confirmation_state="pending" so the agent must complete a two-step
    # schedule+confirm workflow. Empty list = legacy behavior.
    if "auto_confirm_specialties" in params:
        ctx.base["auto_confirm_specialties"] = list(params["auto_confirm_specialties"] or [])

    # Compute the overdue subset — every screening whose next_due has already
    # passed relative to the seeded clock. Consumers (e.g. the
    # pp_preventive_screening_review canonical_diff) need this as a target
    # so a bijection can create one appointment per overdue screening
    # without reconstructing the filter inside a predicate (Class 8
    # comprehension-scope hazard).
    _today = ctx.now.date()
    overdue_screening_names = [
        s["screening_name"]
        for s in screening_models
        if s["next_due"] is not None and date.fromisoformat(s["next_due"]) < _today
    ]

    return {
        "patient_name": patient_name,
        "pcp_id": pcp_id,
        "pcp_name": "",  # Will be filled by provider_directory
        "insurance_plan_name": plan_name,
        "member_id": member_id,
        "group_number": group_number,
        "conditions_list": conditions,
        "allergies_list": allergies,
        "applicable_screening_names": [s["screening_name"] for s in screening_models],
        "overdue_screening_names": overdue_screening_names,
        # On-file (pre-task) contact values. Exposed so verification tasks can
        # reference the deliberate near-miss baseline as exact-value lookalikes
        # in canonical_diff constraints without re-reading the seed.
        "on_file_phone": phone,
        "on_file_email": email,
        "on_file_ec_name": ec_name,
        "on_file_ec_phone": ec_phone,
        "on_file_ec_relationship": ec_rel,
    }


def _parse_frequency_years(freq: str) -> int:
    """Parse a screening frequency string into years."""
    if "10 years" in freq:
        return 10
    if "5 years" in freq:
        return 5
    if "3 years" in freq:
        return 3
    if "2 years" in freq:
        return 2
    return 1  # annually


# ---------------------------------------------------------------------------
# 2. provider_directory
# ---------------------------------------------------------------------------

@_register("provider_directory")
def build_provider_directory(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create N providers across requested specialties with realistic available slots.

    Params:
      specialties (list[str]): one provider of each listed specialty by default.
      count_per_specialty (dict[str, int]): override the default count-of-1
        for specific specialties. E.g. {"pcp": 2} creates two distinct PCPs.
        Required when tasks need bijection identity tests across providers of
        the same specialty (e.g. immunizations administered by different PCPs).
      must_include (list[str]): specialties that must be present; merged with
        `specialties` with duplicates collapsed.
      force_in_person_specialties (list[str]): for each listed specialty, every
        provider of that specialty is guaranteed at least one in-person slot.
        If a provider's randomly-generated slots are all telehealth, the
        earliest slot's type is flipped to "in-person". This is applied AFTER
        all RNG slot draws (so it does not perturb the deterministic seed
        stream of other tasks) and only activates when the param is supplied —
        existing tasks are unaffected. Required by tasks whose canonical
        answer is "the earliest in-person slot of provider X", to keep that
        answer guaranteed to exist across every seed.
      force_earlier_telehealth_specialties (list[str]): for each listed
        specialty, every provider of that specialty is guaranteed to own a
        TELEHEALTH slot that is STRICTLY EARLIER than its earliest in-person
        slot. Implies the in-person guarantee (the provider is given an
        in-person slot first if it lacks one). This converts the
        "earliest in-person slot" answer from a passive predicate into an
        ACTIVE modality trap: the provider's globally-earliest slot is now
        always telehealth, so an agent that books "the earliest slot" (ignoring
        modality) lands on a concrete wrong slot on EVERY seed (not just the
        ~1-in-3 seeds where the RNG happened to draw an early telehealth slot).
        The injected slot is 1 hour before the earliest in-person slot, fully
        deterministic, applied after all RNG draws so other tasks' seed streams
        are unchanged. No-op unless the specialty is opted in.
      non_accepting_provider_specs (dict[str, int]): mark the first N providers
        created of each named specialty as ``accepting_new=False``. Lets a task
        seed a closed-panel decoy provider in a specialty the agent must
        otherwise book — the agent must filter those out before picking the
        earliest slot. Requires `count_per_specialty[spec] > N` so at least one
        accepting provider of that specialty remains.
      min_slot_specialty (str): compute the earliest available slot among the
        ACCEPTING providers of this specialty and expose it as
        ``earliest_slot_dt`` (ISO string) plus the tied provider id list
        ``earliest_slot_provider_ids``. To make the computation a genuine
        discriminator, a strictly-earlier decoy slot is injected into one
        non-accepting provider of the same specialty (when one exists), so the
        globally-earliest slot belongs to a provider the agent must reject.
      earlier_sibling_decoy_specialty (str): inject a slot strictly EARLIER
        (one hour before) than the canonical first provider's earliest slot
        into the first SIBLING provider of this specialty (a provider of the
        specialty that is NOT ``prov_1``/the canonical first). This turns a
        same-specialty sibling into a grounding trap: the globally-earliest
        slot belongs to a provider the agent must reject, so "book the earliest
        visible slot" is wrong and only "book the assigned provider's OWN
        earliest slot" is correct. Requires the specialty to have >=2 providers
        (e.g. ``count_per_specialty {pcp: 2}``). Exposes
        ``global_earliest_decoy_slot_dt`` / ``global_earliest_decoy_provider_id``.
    Outputs: provider_ids, providers_by_specialty, earliest_slot_dt,
             earliest_slot_provider_ids, global_earliest_decoy_slot_dt,
             global_earliest_decoy_provider_id
    """
    specialties = params.get("specialties", ["pcp"])
    count_per_specialty = params.get("count_per_specialty", {}) or {}
    must_include = set(params.get("must_include", []))
    force_in_person_specialties = set(params.get("force_in_person_specialties", []) or [])
    force_earlier_telehealth_specialties = set(
        params.get("force_earlier_telehealth_specialties", []) or []
    )
    # Owning the earlier-telehealth trap implies the in-person guarantee, since
    # the trap is defined relative to "the earliest in-person slot".
    force_in_person_specialties |= force_earlier_telehealth_specialties
    non_accepting_provider_specs: dict[str, int] = {
        str(k): int(v) for k, v in (params.get("non_accepting_provider_specs", {}) or {}).items()
    }
    # `accepting_specialties` overrides the hardcoded closed-panel default for
    # the listed specialties so that providers of those specialties start with
    # ``accepting_new=True`` (billing/admin are closed-panel by default). This
    # is what makes a ``non_accepting_provider_specs`` carve-out a genuine
    # OPEN-vs-CLOSED discriminator within an otherwise-closed specialty (e.g.
    # admin): the first N admin providers are forced closed (the trap the agent
    # must reject) while the remainder are explicitly open and bookable. No-op
    # for specialties not listed, so existing tasks are byte-identical.
    accepting_specialties = set(params.get("accepting_specialties", []) or [])
    min_slot_specialty: str | None = params.get("min_slot_specialty")
    # tie_break_specialty: for a specialty with >= 2 providers, force the two
    # providers' EARLIEST slots to be only minutes apart AND make the globally-
    # earliest slot belong to the SECOND-created provider of that specialty. This
    # turns "earliest slot across both providers" into a genuine cross-provider
    # comparison: an agent that stops at the first provider it reads books a slot
    # that is later (by minutes) than the true global earliest, picking the wrong
    # owning provider. The exact (datetime, provider) is recomputed by the
    # min_slot_by_specialty/earliest_slot_*_by_specialty outputs below, so the
    # canonical_diff pins the correct second provider deterministically.
    tie_break_specialty: str | None = params.get("tie_break_specialty")
    # Merge specialties + must_include, deduped. count_per_specialty controls
    # how many providers of each specialty are created (default 1).
    all_specialties = list(dict.fromkeys(specialties + list(must_include)))

    if "providers" not in ctx.base:
        ctx.base["providers"] = []

    provider_ids: list[str] = []
    providers_by_specialty: dict[str, list[str]] = {}

    # Track which names have already been used per specialty so multiple
    # providers of the same specialty don't collide on name.
    used_names_per_spec: dict[str, set[str]] = {}
    # Per-specialty count of providers created so far (this builder call), so
    # `non_accepting_provider_specs` can target the first N of a specialty.
    created_count_per_spec: dict[str, int] = {}

    for base_spec in all_specialties:
        n_of_this = max(1, int(count_per_specialty.get(base_spec, 1)))
        for _copy_idx in range(n_of_this):
            spec = base_spec
            names_pool = list(_PROVIDER_NAMES.get(spec, [f"Dr. {ctx.fake.name()}"]))
            used = used_names_per_spec.setdefault(spec, set())
            available_names = [n for n in names_pool if n not in used]
            if not available_names:
                # Exhausted pool — generate a unique synthetic name.
                available_names = [f"Dr. {ctx.fake.name()}"]
            dept = _SPECIALTY_DEPARTMENTS.get(spec, spec.title())

            # For PCP, always use prov_1 to match patient.pcp_id (first PCP only)
            if spec == "pcp" and not any(p.get("id") == "prov_1" for p in ctx.base["providers"]):
                prov_id = "prov_1"
                ctx.counters["prov"] = max(ctx.counters.get("prov", 0), 1)
            else:
                prov_id = ctx.next_id("prov")

            prov_name = ctx.rng.choice(available_names)
            used.add(prov_name)
            # billing/admin are closed-panel by default, but a task may opt a
            # specialty back into open-panel via `accepting_specialties` so that
            # a `non_accepting_provider_specs` carve-out becomes a real
            # open-vs-closed discriminator instead of "everyone is closed".
            if spec in accepting_specialties:
                accepting = True
            else:
                accepting = spec not in ("billing", "admin")
            # `non_accepting_provider_specs` forces the first N created providers
            # of a specialty to be closed-panel (accepting_new=False) so a task
            # can seed a tempting-but-ineligible provider in a bookable
            # specialty. The index is per-specialty within this builder call.
            spec_index = created_count_per_spec.get(spec, 0)
            if spec_index < non_accepting_provider_specs.get(spec, 0):
                accepting = False
            created_count_per_spec[spec] = spec_index + 1
            npi = f"{ctx.rng.randint(1000000000, 9999999999)}"

            # Generate 3-6 available slots over the next 2 weeks
            num_slots = ctx.rng.randint(3, 6)
            slots: list[dict[str, Any]] = []
            for _ in range(num_slots):
                days_ahead = ctx.rng.randint(1, 14)
                hour = ctx.rng.randint(9, 16)
                slot_dt = ctx.now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
                slot_type = ctx.rng.choice(["in-person", "telehealth"])
                slots.append({
                    "datetime": slot_dt.isoformat(),
                    "type": slot_type,
                    "duration_minutes": 30,
                })
            # Sort slots by datetime
            slots.sort(key=lambda s: s["datetime"])

            # Guarantee at least one in-person slot for opted-in specialties.
            # Applied after all RNG draws so the deterministic seed stream is
            # unchanged for tasks that do not request this. If no slot is
            # in-person, flip the earliest slot to in-person (a stable, fully
            # deterministic choice). No-op when an in-person slot already
            # exists or the specialty is not opted in.
            if spec in force_in_person_specialties and slots and not any(
                s["type"] == "in-person" for s in slots
            ):
                slots[0]["type"] = "in-person"

            # Modality trap: guarantee a TELEHEALTH slot strictly EARLIER than
            # the earliest in-person slot. Makes "earliest slot of provider X"
            # (ignoring modality) a concrete wrong answer on every seed, so the
            # in-person filter in the canonical datetime expr is an active
            # discriminator rather than an occasionally-vacuous predicate.
            # Deterministic (1h before the earliest in-person slot), applied
            # after RNG draws, no-op unless the specialty is opted in.
            if spec in force_earlier_telehealth_specialties and slots:
                inperson_dts = [
                    s["datetime"] for s in slots if s["type"] == "in-person"
                ]
                if inperson_dts:
                    earliest_inperson = min(inperson_dts)
                    has_earlier_telehealth = any(
                        s["type"] == "telehealth" and s["datetime"] < earliest_inperson
                        for s in slots
                    )
                    if not has_earlier_telehealth:
                        trap_dt = (
                            datetime.fromisoformat(earliest_inperson)
                            - timedelta(hours=1)
                        )
                        slots.append({
                            "datetime": trap_dt.isoformat(),
                            "type": "telehealth",
                            "duration_minutes": 30,
                        })
                        slots.sort(key=lambda s: s["datetime"])

            prov_dict = {
                "id": prov_id,
                "name": prov_name,
                "specialty": spec,
                "department": dept,
                "npi": npi,
                "accepting_new": accepting,
                "available_slots": slots,
            }
            ctx.base["providers"].append(prov_dict)
            provider_ids.append(prov_id)
            providers_by_specialty.setdefault(spec, []).append(prov_id)

    # Update PCP name in outputs if we created a PCP
    if "pcp" in providers_by_specialty:
        pcp_prov = next(
            (p for p in ctx.base["providers"] if p["id"] == "prov_1"), None
        )
        if pcp_prov:
            ctx.outputs["pcp_name"] = pcp_prov["name"]
        # Expose the SECOND PCP (the same-specialty decoy) by id and name so a
        # task/variant can pin "do not book/confirm with the other PCP" and so a
        # grounding stressor can inject a lookalike from the decoy PCP without
        # re-deriving the id inside a filter scope. prov_1 is always the
        # assigned PCP, so the decoy is providers_by_specialty["pcp"][1:].
        pcp_ids_in_order = providers_by_specialty["pcp"]
        if len(pcp_ids_in_order) > 1:
            decoy_pid = pcp_ids_in_order[1]
            decoy_prov = next(
                (p for p in ctx.base["providers"] if p["id"] == decoy_pid), None
            )
            if decoy_prov:
                ctx.outputs["decoy_pcp_id"] = decoy_pid
                ctx.outputs["decoy_pcp_name"] = decoy_prov["name"]

    # tie_break_specialty: make the two providers' earliest slots only minutes
    # apart and place the globally-earliest one on the SECOND-created provider.
    if tie_break_specialty:
        tb_ids = providers_by_specialty.get(tie_break_specialty, [])
        if len(tb_ids) >= 2:
            first_prov = next(
                (p for p in ctx.base["providers"] if p["id"] == tb_ids[0]), None
            )
            second_prov = next(
                (p for p in ctx.base["providers"] if p["id"] == tb_ids[1]), None
            )
            if (
                first_prov
                and second_prov
                and first_prov.get("available_slots")
                and second_prov.get("available_slots")
            ):
                first_slots = sorted(
                    first_prov["available_slots"], key=lambda s: s["datetime"]
                )
                first_earliest_dt = datetime.fromisoformat(
                    first_slots[0]["datetime"]
                )
                # Place the second provider's earliest slot 15 minutes BEFORE the
                # first provider's earliest slot, so the global earliest belongs
                # to the second-created provider and the gap is only minutes.
                tie_dt = first_earliest_dt - timedelta(minutes=15)
                second_slots = sorted(
                    second_prov["available_slots"], key=lambda s: s["datetime"]
                )
                second_slots[0]["datetime"] = tie_dt.isoformat()
                second_prov["available_slots"] = sorted(
                    second_slots, key=lambda s: s["datetime"]
                )

    # Derived: for each specialty, the globally-earliest available slot across
    # ALL providers of that specialty. Tasks that ask the agent to book "the
    # next available <specialty> slot" when there are MULTIPLE providers of
    # that specialty need a scalar answer that disambiguates BOTH the datetime
    # AND the owning provider — comparing only `x in providers_by_specialty[s]`
    # plus a min-over-slots expr leaves a false-positive hole (an agent could
    # name the earliest datetime but the wrong sibling provider). Exposing the
    # owning provider id as a scalar lets the canonical_diff pin it exactly.
    # Slot datetimes are unique within a specialty (random day/hour over 14
    # days), so the (datetime, provider_id) pair is deterministic; ties break
    # on provider_id ascending for total determinism.
    min_slot_by_specialty: dict[str, dict[str, str]] = {}
    earliest_slot_provider_by_specialty: dict[str, str] = {}
    earliest_slot_datetime_by_specialty: dict[str, str] = {}
    for spec, ids in providers_by_specialty.items():
        candidates: list[tuple[str, str]] = []
        for pid in ids:
            prov = next((p for p in ctx.base["providers"] if p["id"] == pid), None)
            if prov is None:
                continue
            for slot in prov.get("available_slots", []):
                candidates.append((slot["datetime"], pid))
        if not candidates:
            continue
        candidates.sort(key=lambda c: (c[0], c[1]))
        best_dt, best_pid = candidates[0]
        min_slot_by_specialty[spec] = {"datetime": best_dt, "provider_id": best_pid}
        earliest_slot_provider_by_specialty[spec] = best_pid
        earliest_slot_datetime_by_specialty[spec] = best_dt

    # --- Earliest-accepting-slot discriminator (min_slot_specialty) ---------
    # Compute the earliest available slot among ACCEPTING providers of the
    # named specialty. To make this a genuine discriminator (rather than a
    # trivial single-provider min), inject a strictly-earlier decoy slot into a
    # NON-accepting provider of the same specialty when one exists — the
    # globally-earliest slot then belongs to a provider the agent must reject.
    earliest_slot_dt: str | None = None
    earliest_slot_provider_ids: list[str] = []
    if min_slot_specialty:
        spec_providers = [
            p for p in ctx.base["providers"]
            if p.get("specialty") == min_slot_specialty
        ]
        accepting_providers = [p for p in spec_providers if p.get("accepting_new")]
        non_accepting = [p for p in spec_providers if not p.get("accepting_new")]

        # Earliest slot across accepting providers (the correct answer).
        accepting_slot_dts = [
            s["datetime"]
            for p in accepting_providers
            for s in p.get("available_slots", [])
        ]
        if accepting_slot_dts:
            earliest_accept = min(accepting_slot_dts)
            # Inject a decoy slot one hour BEFORE the earliest accepting slot
            # into the first non-accepting provider (if any) so the closed-panel
            # provider holds the globally-earliest slot.
            if non_accepting:
                decoy_dt = (
                    datetime.fromisoformat(earliest_accept) - timedelta(hours=1)
                )
                decoy_provider = non_accepting[0]
                decoy_provider.setdefault("available_slots", []).append({
                    "datetime": decoy_dt.isoformat(),
                    "type": "in-person",
                    "duration_minutes": 30,
                })
                decoy_provider["available_slots"].sort(key=lambda s: s["datetime"])
            earliest_slot_dt = earliest_accept
            earliest_slot_provider_ids = sorted(
                p["id"]
                for p in accepting_providers
                if any(s["datetime"] == earliest_accept for s in p.get("available_slots", []))
            )

    # -- Computed discriminator: earliest IN-PERSON Administration slot --------
    # Tasks like pp_complete_account_audit require the agent to schedule a
    # single in-person front-desk (Administration) visit at the EARLIEST
    # in-person slot across ALL admin providers. With multiple admin providers
    # this is a genuine cross-provider top-K computation that the agent must
    # re-derive (not just read one provider's slot list). We pre-compute the
    # canonical answer here and expose it as scalar targets so the
    # canonical_diff predicate can pin an exact (provider_id, datetime) without
    # reconstructing a min() over a comprehension scope it cannot see (Class 6
    # filter-scope hazard).
    #
    # Tie-break is lexicographic on (datetime_iso, provider_id) so the winner
    # is deterministic when two admin providers share the earliest slot time.
    # Only in-person slots are eligible (a front-desk records visit is on-site).
    #
    # IMPORTANT: only ACCEPTING (open-panel) admin providers are eligible. When
    # a task carves out closed-panel admin providers via
    # ``non_accepting_provider_specs`` + ``accepting_specialties`` and injects a
    # strictly-earlier decoy slot into a closed provider (via
    # ``min_slot_specialty``), the GLOBALLY earliest in-person admin slot
    # belongs to a provider the agent must reject — so the canonical answer is
    # the earliest in-person slot among ACCEPTING admin providers only. When no
    # admin specialty was opted into open-panel (legacy tasks), every admin
    # provider is closed; in that case we fall back to considering ALL admin
    # providers so the answer still exists (preserving prior behaviour).
    admin_provider_ids = providers_by_specialty.get("admin", [])
    admin_providers = [p for p in ctx.base["providers"] if p["id"] in admin_provider_ids]
    _eligible_admin = [p for p in admin_providers if p.get("accepting_new")]
    if not _eligible_admin:
        # Legacy / all-closed admin directory: keep the historical behaviour of
        # ranking across every admin provider so the answer is non-empty.
        _eligible_admin = admin_providers
    _inperson_candidates: list[tuple[str, str]] = []
    for p in _eligible_admin:
        for s in p.get("available_slots", []):
            if s.get("type") == "in-person":
                _inperson_candidates.append((s["datetime"], p["id"]))
    admin_earliest_inperson_slot_datetime: str | None = None
    admin_earliest_inperson_provider_id: str | None = None
    if _inperson_candidates:
        _inperson_candidates.sort(key=lambda t: (t[0], t[1]))
        admin_earliest_inperson_slot_datetime = _inperson_candidates[0][0]
        admin_earliest_inperson_provider_id = _inperson_candidates[0][1]
    # Expose the set of ACCEPTING (open-panel) admin provider ids so the
    # canonical_diff can restrict its min()/membership predicates to the
    # bookable subset without reconstructing the accepting filter inside a
    # comprehension scope it cannot see (Class 6 filter-scope hazard).
    accepting_admin_provider_ids = sorted(
        p["id"] for p in admin_providers if p.get("accepting_new")
    )
    # A SECOND open-panel admin provider id, distinct from the canonical
    # earliest-slot provider when one exists. Grounding-stressor variants seed a
    # same-reason/same-type lookalike appointment onto this provider so the
    # agent must distinguish the seeded decoy from its OWN required booking
    # WITHOUT landing the decoy on a closed-panel provider (which would trip the
    # open-panel constraint). Falls back to the canonical provider when only one
    # open-panel admin exists.
    decoy_admin_provider_id: str | None = None
    _other_open = [
        pid for pid in accepting_admin_provider_ids
        if pid != admin_earliest_inperson_provider_id
    ]
    if _other_open:
        decoy_admin_provider_id = _other_open[0]
    elif accepting_admin_provider_ids:
        decoy_admin_provider_id = accepting_admin_provider_ids[0]

    # -- Earlier-sibling decoy slot (earlier_sibling_decoy_specialty) ----------
    # Tasks that pin "book the EARLIEST slot on the ASSIGNED provider's own
    # calendar" (where the assigned provider is the canonical first provider of
    # a specialty — for PCP that is always ``prov_1``) need a genuine grounding
    # discriminator: a SIBLING provider of the same specialty whose earliest
    # slot is strictly GLOBALLY EARLIER than the assigned provider's earliest
    # slot. An agent that naively books "the earliest visible <specialty> slot"
    # lands on the sibling and fails the ``provider_id == assigned`` predicate;
    # the canonical answer (the assigned provider's own earliest slot) is later
    # in wall-clock time, so the trap is real, not cosmetic.
    #
    # The decoy slot is injected ONE HOUR before the assigned provider's
    # earliest slot into the first sibling provider of the named specialty
    # (a provider of that specialty that is NOT the canonical first provider).
    # The injection happens after all RNG draws so the deterministic seed stream
    # is unchanged for tasks that do not request this. We expose the resulting
    # globally-earliest (datetime, provider_id) so a solvability proof / test
    # can assert the trap exists without re-deriving it.
    earlier_decoy_specialty: str | None = params.get("earlier_sibling_decoy_specialty")
    global_earliest_decoy_slot_dt: str | None = None
    global_earliest_decoy_provider_id: str | None = None
    if earlier_decoy_specialty:
        spec_ids = providers_by_specialty.get(earlier_decoy_specialty, [])
        spec_provs = [p for p in ctx.base["providers"] if p["id"] in spec_ids]
        # Canonical first provider of this specialty (prov_1 for PCP); the rest
        # are siblings the agent must reject.
        canonical = next(
            (p for p in spec_provs if p["id"] == "prov_1"),
            spec_provs[0] if spec_provs else None,
        )
        siblings = [p for p in spec_provs if canonical is not None and p["id"] != canonical["id"]]
        if canonical is not None and siblings and canonical.get("available_slots"):
            assigned_earliest = min(s["datetime"] for s in canonical["available_slots"])
            decoy_dt = (
                datetime.fromisoformat(assigned_earliest) - timedelta(hours=1)
            )
            decoy_provider = siblings[0]
            decoy_provider.setdefault("available_slots", []).append({
                "datetime": decoy_dt.isoformat(),
                "type": "in-person",
                "duration_minutes": 30,
            })
            decoy_provider["available_slots"].sort(key=lambda s: s["datetime"])
            global_earliest_decoy_slot_dt = decoy_dt.isoformat()
            global_earliest_decoy_provider_id = decoy_provider["id"]

    return {
        "provider_ids": provider_ids,
        "providers_by_specialty": providers_by_specialty,
        "min_slot_by_specialty": min_slot_by_specialty,
        "earliest_slot_provider_by_specialty": earliest_slot_provider_by_specialty,
        "earliest_slot_datetime_by_specialty": earliest_slot_datetime_by_specialty,
        "earliest_slot_dt": earliest_slot_dt,
        "earliest_slot_provider_ids": earliest_slot_provider_ids,
        "admin_earliest_inperson_slot_datetime": admin_earliest_inperson_slot_datetime,
        "admin_earliest_inperson_provider_id": admin_earliest_inperson_provider_id,
        "accepting_admin_provider_ids": accepting_admin_provider_ids,
        "decoy_admin_provider_id": decoy_admin_provider_id,
        "global_earliest_decoy_slot_dt": global_earliest_decoy_slot_dt,
        "global_earliest_decoy_provider_id": global_earliest_decoy_provider_id,
        # Second same-specialty PCP (the decoy), when one exists. Used by tasks
        # that forbid booking/confirming with the other PCP and by grounding
        # stressors that plant a lookalike from this provider.
        "decoy_pcp_id": ctx.outputs.get("decoy_pcp_id"),
        "decoy_pcp_name": ctx.outputs.get("decoy_pcp_name"),
    }


# ---------------------------------------------------------------------------
# 3. pharmacy_list
# ---------------------------------------------------------------------------

@_register("pharmacy_list")
def build_pharmacy_list(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create pharmacies with one default. Optional mail-order.

    Params:
        count (2-3)
        include_mail_order (bool)
        mail_order_count (int): number of distinct mail-order pharmacies to
            create, each with its own rng-drawn ``cost_per_90day_supply``.
            Defaults to 1 when ``include_mail_order`` is True, 0 otherwise.
            When > 1 the builder exposes ``mail_order_pharmacy_ids`` (all of
            them), ``mail_order_costs`` (id → cost string), and
            ``cheapest_mail_order_pharmacy_id`` (min cost, ties broken by
            ascending pharmacy id).
        mail_order_costs_override (list): explicit ordered
            ``cost_per_90day_supply`` values for the mail-order pharmacies (in
            creation order). Overrides the rng draw so the "cheapest mail-order"
            discriminator is deterministic and can carry a deliberate near-tie.
        must_include_name (str | list[str]): case-insensitive substring(s) of
            pharmacy template names that MUST be present in the selected
            pharmacies. Each matched template is pinned before other
            templates are appended up to `count`.
        target_pharmacy_name (str): case-insensitive substring of a pharmacy
            template name whose id should be exposed as `target_pharmacy_id`
            in the outputs. The name must also match one of `must_include_name`
            (or the caller must guarantee it ends up in the selection) —
            otherwise `target_pharmacy_id` may be None.
    Outputs: pharmacy_ids, default_pharmacy_id, mail_order_pharmacy_id,
             target_pharmacy_id, new_default_pharmacy_id,
             lowest_fee_retail_pharmacy_id, lowest_fee_retail_pharmacy_name,
             retail_fee_by_id,
             mail_order_pharmacy_ids, mail_order_costs,
             cheapest_mail_order_pharmacy_id

    ``new_default_pharmacy_id`` is the first non-default, non-mail-order
    retail pharmacy in ``pharmacy_ids`` (i.e. ``selected[1]`` when count >= 2).
    Tasks like ``pp_coordinate_rx_transfer`` that tell the agent to transfer
    prescriptions to "another retail pharmacy in your pharmacy list" use this
    as the canonical new-default answer.

    ``distinct_retail_fees`` (list[int]): when supplied, the retail pharmacies
    are assigned these dispensing fees in selection order (recycled if the
    list is shorter than the count). This makes the "lowest dispensing fee"
    discriminator deterministic and unambiguous across seeds. When omitted,
    each retail pharmacy gets a random fee from ``[5, 8, 10, 12]`` (legacy
    behaviour).

    ``lowest_fee_retail_pharmacy_id`` is the id of the non-default, non-mail
    -order retail pharmacy with the strictly lowest ``dispensing_fee``,
    breaking ties by the lower numeric id suffix. Tasks that ask the agent to
    re-derive the cheapest retail pharmacy use this as the canonical answer.
    """
    count = params.get("count", 2)
    include_mail_order = params.get("include_mail_order", False)
    distinct_retail_fees_raw = params.get("distinct_retail_fees")
    # ``retail_decoy_fees`` (list[int]): when supplied, the builder appends extra
    # NON-DEFAULT, NON-MAIL-ORDER retail pharmacies with these dispensing fees
    # that are deliberately NOT added to ``patient.pharmacy_ids`` (i.e. they are
    # visible via ``GET /pharmacies`` but are NOT part of the patient's pharmacy
    # LIST exposed on ``GET /profile``). Tasks that scope the cheapest-retail
    # discriminator to "the retail pharmacies in your pharmacy list" use these as
    # cheaper-fee traps: an agent that sorts every visible pharmacy by fee picks
    # a decoy and fails, while an agent that first restricts to
    # ``profile.pharmacy_ids`` picks the correct in-list pharmacy. The decoys are
    # excluded from ``cheapest_retail_pharmacy_id`` (which is computed over
    # list-members only) and exposed under ``retail_decoy_pharmacy_ids`` plus the
    # naive-wrong answer ``cheapest_overall_retail_pharmacy_id``.
    retail_decoy_fees_raw = params.get("retail_decoy_fees")
    # Optional explicit, ordered ``cost_per_90day_supply`` values for the
    # mail-order pharmacies (creation order = ``mail_order_pharmacy_ids`` order).
    # When supplied, each mail-order pharmacy gets the corresponding cost instead
    # of an rng draw, making the "cheapest mail-order" discriminator deterministic
    # AND letting a cost-comparison task seed a deliberate NEAR-TIE (two options
    # within $1 of each other) so a naive "first mail-order" / eyeball pick lands
    # on the wrong one. Values are recycled if the list is shorter than
    # ``mail_order_count``. The cheapest is still computed from the actual values
    # (min cost, ties broken by ascending pharmacy id) so the canonical answer is
    # never positional.
    mail_order_costs_override_raw = params.get("mail_order_costs_override")
    # Number of distinct mail-order pharmacies to create, each with its own
    # rng-drawn ``cost_per_90day_supply``. Defaults to 1 when
    # ``include_mail_order`` is True (legacy single-mail-order behavior), 0
    # otherwise. When > 1, the builder exposes the full ``mail_order_pharmacy_ids``
    # list plus a precomputed ``cheapest_mail_order_pharmacy_id`` (min cost,
    # ties broken by ascending pharmacy id) so cost-comparison tasks can pin
    # the single correct destination without re-deriving the min inside a
    # canonical_diff predicate (Class 6 hazard).
    mail_order_count = int(params.get("mail_order_count", 1 if include_mail_order else 0))
    must_include_raw = params.get("must_include_name") or []
    if isinstance(must_include_raw, str):
        must_include_names = [must_include_raw]
    else:
        must_include_names = list(must_include_raw)
    target_pharmacy_name: str | None = params.get("target_pharmacy_name")

    if "pharmacies" not in ctx.base:
        ctx.base["pharmacies"] = []

    templates = list(_PHARMACY_TEMPLATES)
    ctx.rng.shuffle(templates)

    # Pin must_include templates to the front (preserving shuffle for the rest).
    pinned: list[dict[str, str]] = []
    for needle in must_include_names:
        match = next(
            (t for t in templates if needle.lower() in t["name"].lower()),
            None,
        )
        if match is not None:
            templates.remove(match)
            pinned.append(match)
    templates = pinned + templates
    selected = templates[:min(count, len(templates))]

    # If target_pharmacy_name resolves to selected[0] (the default), swap it
    # with selected[1] so the target is a non-default pharmacy the agent can
    # switch TO. Tasks like pp_update_default_pharmacy need target != default.
    if (
        target_pharmacy_name
        and len(selected) >= 2
        and target_pharmacy_name.lower() in selected[0]["name"].lower()
    ):
        selected[0], selected[1] = selected[1], selected[0]

    pharmacy_ids: list[str] = []
    default_pharmacy_id: str = ""
    mail_order_pharmacy_id: str | None = None
    target_pharmacy_id: str | None = None
    new_default_pharmacy_id: str | None = None

    # Deterministic distinct dispensing fees in selection order, when the
    # caller wants an unambiguous "lowest fee" discriminator.
    distinct_retail_fees: list[int] | None = None
    if distinct_retail_fees_raw:
        distinct_retail_fees = [int(f) for f in distinct_retail_fees_raw]

    for i, tmpl in enumerate(selected):
        pharm_id = ctx.next_id("pharm")
        is_default = i == 0
        if distinct_retail_fees:
            dispensing_fee = Decimal(str(distinct_retail_fees[i % len(distinct_retail_fees)]))
        else:
            dispensing_fee = Decimal(str(ctx.rng.choice([5, 8, 10, 12])))

        pharm_dict = {
            "id": pharm_id,
            "name": tmpl["name"],
            "address": tmpl["address"],
            "phone": tmpl["phone"],
            "is_default": is_default,
            "is_mail_order": False,
            "dispensing_fee": str(dispensing_fee),
        }
        ctx.base["pharmacies"].append(pharm_dict)
        pharmacy_ids.append(pharm_id)
        if is_default:
            default_pharmacy_id = pharm_id
        elif new_default_pharmacy_id is None:
            # First non-default retail pharmacy — canonical "switch-to" answer
            # for tasks that transfer prescriptions away from the closing default.
            new_default_pharmacy_id = pharm_id
        if (
            target_pharmacy_name
            and target_pharmacy_id is None
            and target_pharmacy_name.lower() in tmpl["name"].lower()
        ):
            target_pharmacy_id = pharm_id

    mail_order_pharmacy_ids: list[str] = []
    mail_order_costs: dict[str, str] = {}
    mail_order_costs_override: list[Decimal] | None = None
    if mail_order_costs_override_raw:
        mail_order_costs_override = [
            Decimal(str(c)) for c in mail_order_costs_override_raw
        ]
    if mail_order_count > 0:
        # Template 0 is always the legacy Express Scripts entry so existing
        # single-mail-order tasks are byte-identical; entries 1+ pull from the
        # extra pool. We never shuffle these so the cheapest answer is decided
        # purely by the rng-drawn cost, never by template position.
        mail_order_templates = [_MAIL_ORDER_PHARMACY] + _EXTRA_MAIL_ORDER_PHARMACIES
        for mo_idx in range(mail_order_count):
            tmpl = mail_order_templates[mo_idx % len(mail_order_templates)]
            pharm_id = ctx.next_id("pharm")
            if mail_order_costs_override is not None:
                cost = mail_order_costs_override[
                    mo_idx % len(mail_order_costs_override)
                ]
            else:
                cost = Decimal(str(ctx.rng.randint(15, 45)))
            pharm_dict = {
                "id": pharm_id,
                "name": tmpl["name"],
                "address": tmpl["address"],
                "phone": tmpl["phone"],
                "is_default": False,
                "is_mail_order": True,
                "dispensing_fee": "0",
                "cost_per_90day_supply": str(cost),
            }
            ctx.base["pharmacies"].append(pharm_dict)
            pharmacy_ids.append(pharm_id)
            mail_order_pharmacy_ids.append(pharm_id)
            mail_order_costs[pharm_id] = str(cost)
            if mail_order_pharmacy_id is None:
                # Preserve legacy semantics: ``mail_order_pharmacy_id`` is the
                # FIRST mail-order pharmacy created (Express Scripts).
                mail_order_pharmacy_id = pharm_id

    # Precompute the single cheapest mail-order pharmacy by 90-day-supply cost
    # (ties broken by ascending pharmacy id). Tasks that ask the agent to pick
    # "the lowest-cost mail-order pharmacy" pin this scalar as the canonical
    # destination so the bijection/where predicate never has to compute a min
    # over a collection inside the filter scope.
    cheapest_mail_order_pharmacy_id: str | None = None
    if mail_order_pharmacy_ids:
        cheapest_mail_order_pharmacy_id = min(
            mail_order_pharmacy_ids,
            key=lambda pid: (float(mail_order_costs[pid]), pid),
        )

    # Update patient's pharmacy_ids
    if "patient" in ctx.base:
        ctx.base["patient"]["pharmacy_ids"] = pharmacy_ids

    # Out-of-list retail decoy pharmacies. These are real Pharmacy entities in
    # the world state (so they appear on ``GET /pharmacies`` and are valid
    # transfer targets), but they are deliberately NOT in ``pharmacy_ids`` /
    # ``patient.pharmacy_ids`` — they are not part of the patient's pharmacy
    # LIST. Their fees are set BELOW the cheapest in-list retail fee so a naive
    # agent that sorts every visible pharmacy by ``dispensing_fee`` is lured to
    # the wrong (out-of-list) destination. The id suffix continues from the
    # in-list pharmacies; templates recycle from the retail pool with a distinct
    # store number so the decoy names are plausible but distinguishable.
    retail_decoy_pharmacy_ids: list[str] = []
    retail_decoy_fee_by_id: dict[str, str] = {}
    if retail_decoy_fees_raw:
        retail_decoy_fees = [int(f) for f in retail_decoy_fees_raw]
        for d_idx, fee in enumerate(retail_decoy_fees):
            tmpl = _PHARMACY_TEMPLATES[d_idx % len(_PHARMACY_TEMPLATES)]
            pharm_id = ctx.next_id("pharm")
            pharm_dict = {
                "id": pharm_id,
                # Suffix the store name so it is clearly a different storefront
                # than the in-list templates of the same chain.
                "name": f"{tmpl['name'].split('#')[0].strip()} #D{700 + d_idx}",
                "address": tmpl["address"],
                "phone": tmpl["phone"],
                "is_default": False,
                "is_mail_order": False,
                "dispensing_fee": str(Decimal(str(fee))),
            }
            ctx.base["pharmacies"].append(pharm_dict)
            retail_decoy_pharmacy_ids.append(pharm_id)
            retail_decoy_fee_by_id[pharm_id] = str(Decimal(str(fee)))

    # Compute the cheapest NON-DEFAULT, NON-MAIL-ORDER retail pharmacy. This is
    # the canonical answer for tasks that ask the agent to re-derive "lowest
    # dispensing fee retail pharmacy" rather than naming the store. Tie-break by
    # the lower numeric id suffix so the answer is deterministic when two
    # retail pharmacies share a fee.
    #
    # pp_coordinate_rx_transfer also reads this as the canonical destination
    # for moving prescriptions to "the retail pharmacy with the lowest
    # dispensing fee" (excluding the closing default and any mail-order
    # pharmacy). It is exposed under both the descriptive name and the legacy
    # ``cheapest_retail_pharmacy_id`` alias; both refer to the same pharmacy.
    def _id_suffix(pid: str) -> int:
        try:
            return int(pid.rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            return 0

    # IN-LIST retail candidates: non-default, non-mail-order pharmacies that are
    # part of the patient's pharmacy LIST (``pharmacy_ids``). Out-of-list retail
    # decoys are EXCLUDED here so the canonical cheapest answer respects the
    # "retail pharmacies in your pharmacy list" scoping in the instruction.
    retail_candidates = [
        p for p in ctx.base.get("pharmacies", [])
        if not p.get("is_mail_order")
        and not p.get("is_default")
        and p["id"] in pharmacy_ids
    ]
    lowest_fee_retail_pharmacy_id: str | None = None
    lowest_fee_retail_pharmacy_name: str | None = None
    cheapest_retail_pharmacy_id: str | None = None
    retail_fee_by_id: dict[str, str] = {
        p["id"]: str(p["dispensing_fee"]) for p in retail_candidates
    }
    if retail_candidates:
        cheapest = min(
            retail_candidates,
            key=lambda p: (Decimal(str(p["dispensing_fee"])), _id_suffix(p["id"])),
        )
        lowest_fee_retail_pharmacy_id = cheapest["id"]
        lowest_fee_retail_pharmacy_name = cheapest["name"]
        cheapest_retail_pharmacy_id = cheapest["id"]

    # The NAIVE-WRONG answer: the cheapest non-default, non-mail-order retail
    # pharmacy considering EVERY visible pharmacy (including out-of-list decoys).
    # Exposed so tasks/tests can prove the decoy trap genuinely diverges from the
    # correct, list-scoped answer. Not used by grading.
    all_retail_candidates = [
        p for p in ctx.base.get("pharmacies", [])
        if not p.get("is_mail_order") and not p.get("is_default")
    ]
    cheapest_overall_retail_pharmacy_id: str | None = None
    if all_retail_candidates:
        cheapest_overall_retail_pharmacy_id = min(
            all_retail_candidates,
            key=lambda p: (Decimal(str(p["dispensing_fee"])), _id_suffix(p["id"])),
        )["id"]

    return {
        "pharmacy_ids": pharmacy_ids,
        "default_pharmacy_id": default_pharmacy_id,
        "mail_order_pharmacy_id": mail_order_pharmacy_id,
        "mail_order_pharmacy_ids": mail_order_pharmacy_ids,
        "mail_order_costs": mail_order_costs,
        "cheapest_mail_order_pharmacy_id": cheapest_mail_order_pharmacy_id,
        "target_pharmacy_id": target_pharmacy_id,
        "new_default_pharmacy_id": new_default_pharmacy_id,
        "lowest_fee_retail_pharmacy_id": lowest_fee_retail_pharmacy_id,
        "lowest_fee_retail_pharmacy_name": lowest_fee_retail_pharmacy_name,
        "retail_fee_by_id": retail_fee_by_id,
        "cheapest_retail_pharmacy_id": cheapest_retail_pharmacy_id,
        "retail_decoy_pharmacy_ids": retail_decoy_pharmacy_ids,
        "retail_decoy_fee_by_id": retail_decoy_fee_by_id,
        "cheapest_overall_retail_pharmacy_id": cheapest_overall_retail_pharmacy_id,
    }


# ---------------------------------------------------------------------------
# 4. appointment_history
# ---------------------------------------------------------------------------

@_register("appointment_history")
def build_appointment_history(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a mix of upcoming, completed, and cancelled appointments.

    Params: upcoming_count, completed_count, cancelled_count,
            include_specialist (bool), conflict_pair (bool),
            conflict_same_provider (bool) — when conflict_pair is set, force
            both conflicting appointments onto the PCP so booked_at is the
            only discriminator,
            conflict_count (int, default 2) — number of appointments sharing
            the same datetime when conflict_pair is set; >2 produces a
            triple-or-more overlap. The cluster cycles
            providers[j % len(providers)] and booked_at is strictly increasing
            with j, so the most-recently-booked member lands on a specialist
            provider and the keep/cancel partition is exposed via
            conflict_keep_apt_id / conflict_cancel_apt_ids while the
            most-recently-booked discriminator is exposed via
            later_booked_conflict_apt_id (and its type-matched earliest slot).
            >2 also makes the most-recently-booked re-derivation harder,
            conflict_clusters (list[int]) — sizes of independent groups of
            same-datetime double/triple-booked appointments; within each
            cluster booked_at is strictly increasing so the first is the
            unique earliest-booked (keep) and the rest are later-booked
            duplicates (cancel),
            keeper_trap_clusters (list[int]) — cluster indices whose earliest-
            booked keeper is placed on a specialist provider + telehealth type
            while the later-booked duplicates sit on the PCP + in-person, so a
            "keep the PCP/in-person one" heuristic cancels the keeper (the
            partition stays purely booked_at, so it remains correct),
            pseudo_conflict_count (int) — number of decoy same-datetime groups
            with exactly one scheduled member and the rest completed; the
            scheduled survivor (exposed as pseudo_conflict_apt_ids) must NOT be
            cancelled, forcing a status=='scheduled' filter before partitioning,
            target_specialty (str | None) — when set, the upcoming
            appointment for that specialty is exposed as `target_apt_id`
            (PP-5). When unset, `target_apt_id` falls back to
            `specialist_apt_id` (the first non-PCP upcoming).
    Outputs: upcoming_ids, completed_ids, cancelled_ids, next_appointment_id,
             conflict_apt_ids, conflict_apt_date, conflict_provider_name,
             conflict_keep_apt_id, conflict_cancel_apt_ids,
             conflict_last_booked_apt_id,
             later_booked_conflict_apt_id, later_booked_conflict_provider_id,
             later_booked_conflict_earliest_slot, later_booked_conflict_type,
             later_booked_conflict_type_matched_earliest_slot,
             pcp_apt_id, specialist_apt_id, telehealth_apt_id, target_apt_id,
             cluster_all_apt_ids, cluster_cancel_apt_ids, cluster_keep_apt_ids,
             pseudo_conflict_apt_ids
    """
    upcoming_count = params.get("upcoming_count", 2)
    completed_count = params.get("completed_count", 2)
    cancelled_count = params.get("cancelled_count", 1)
    include_specialist = params.get("include_specialist", True)
    conflict_pair = params.get("conflict_pair", False)
    target_specialty: str | None = params.get("target_specialty")
    # When True, both appointments in the conflict pair are booked with the
    # *same* provider (the PCP). The two appointments then share provider AND
    # datetime, so the ONLY field that distinguishes them is ``booked_at`` —
    # forcing a consumer task to re-derive the earlier/later booking rather
    # than ground on the provider. Defaults False to preserve the existing
    # two-different-providers behaviour for tasks that rely on it.
    conflict_same_provider: bool = bool(params.get("conflict_same_provider", False))
    # PP-CD v2: decouple booked_at ordering from id / creation order for the
    # `conflict_pair` cluster. When False (default) booked_at is strictly
    # increasing with the loop index j, so the earliest-booked member is also
    # the FIRST-created / lowest-id member — an agent can "keep the first
    # same-time appointment" and pass without ever reading booked_at. The two
    # other cluster consumers (pp_resolve_schedule_conflicts /
    # pp_resolve_specialist_conflicts) bind `later_booked_apt_id` to
    # `conflict_apt_ids.1` and freeze everything except that slot, so they
    # REQUIRE slot 1 to remain the most-recently-booked member — they must NOT
    # opt into the shuffle. When True the per-member booked_at values are
    # assigned by a seed-deterministic permutation of the day offsets, so the
    # earliest-booked member is no longer systematically the lowest id / first
    # listed. The keep/cancel partition (and every later_booked_* discriminator)
    # is recomputed by sorting on (booked_at, id) AFTER assignment, so outputs
    # stay correct; only the SELECTION challenge gets harder (the agent must
    # actually compare timestamps). Opt-in keeps full back-compat.
    conflict_shuffle_booked_at: bool = bool(
        params.get("conflict_shuffle_booked_at", False)
    )
    # PP-CD v2: a SECOND same-datetime group of scheduled appointments that are
    # legitimately distinct visits (NOT duplicates) and must be left untouched.
    # This converts "find the one same-time trio" into "identify WHICH same-time
    # group is the duplicate set" — a real grounding step. These appointments
    # sit at their own (distinct) datetime, are flagged with a clearly
    # non-duplicate reason, and are frozen by the existing
    # `a.id not in conflict_cancel_apt_ids` invariant. Default 0 = off.
    conflict_decoy_same_time_count: int = max(
        0, int(params.get("conflict_decoy_same_time_count", 0) or 0)
    )
    # PP-CD v2: already-cancelled appointment(s) sharing the LIVE cluster's
    # exact datetime. A content-blind agent might treat one of these as a live
    # duplicate (and try to re-cancel it — a 422) or, worse, conclude the
    # duplicate set is already partially resolved. They are pinned (status !=
    # 'scheduled' so the cancel endpoint rejects them, and excluded from the
    # cancel set) but they widen the same-time confusion surface. Default 0.
    conflict_cancelled_same_time_count: int = max(
        0, int(params.get("conflict_cancelled_same_time_count", 0) or 0)
    )
    # B-1: per-specialty list of specialties whose upcoming appointments
    # should be created with `requires_confirmation=True`. Default empty
    # list preserves backward compatibility — existing tasks remain
    # confirmation-free unless they opt in.
    confirmation_specialties: list[str] = list(
        params.get("requires_confirmation_specialties", []) or []
    )

    if "appointments" not in ctx.base:
        ctx.base["appointments"] = []

    providers = ctx.base.get("providers", [])
    if not providers:
        raise ValueError("provider_directory must run before appointment_history")

    pcp_provider = next((p for p in providers if p["specialty"] == "pcp"), providers[0])
    specialist_providers = [p for p in providers if p["specialty"] not in ("pcp", "billing", "admin")]
    completed_provider_pool = [p for p in providers if p["specialty"] not in ("billing", "admin")] or providers

    upcoming_ids: list[str] = []
    pcp_apt_date: str = ""
    completed_ids: list[str] = []
    cancelled_ids: list[str] = []
    conflict_apt_ids: list[str] = []
    conflict_apt_date: str = ""
    conflict_provider_name: str = ""
    pcp_apt_id: str | None = None
    specialist_apt_id: str | None = None
    telehealth_apt_id: str | None = None
    next_appointment_id: str | None = None
    # PP-5: when target_specialty is provided, this is the apt_id of the
    # upcoming appointment whose provider has that specialty. Falls back
    # to specialist_apt_id (first non-PCP) when unset.
    target_apt_id: str | None = None
    # Pre-pick a target-specialty provider (if any). Falls back to None
    # when no provider matches; in that case target_apt_id stays None and
    # the YAML's eval falls back to specialist_apt_id.
    target_specialty_provider: dict[str, Any] | None = None
    if target_specialty:
        target_specialty_provider = next(
            (p for p in providers if p.get("specialty") == target_specialty),
            None,
        )

    def _link_matching_referral(apt_dict: dict[str, Any], prov: dict[str, Any]) -> None:
        for ref in ctx.base.get("referrals", []):
            if ref.get("linked_appointment_id"):
                continue
            provider_match = ref.get("to_provider_id") == prov["id"]
            specialty_match = ref.get("to_specialty") == prov.get("specialty")
            if provider_match or specialty_match:
                apt_dict["linked_referral_id"] = ref["id"]
                ref["linked_appointment_id"] = apt_dict["id"]
                break

    # --- Upcoming appointments ---
    # PP-5: if target_specialty is set, reserve slot i==1 for that
    # specialty so target_apt_id is bound to a provider of that specialty
    # rather than "first non-PCP".
    target_slot_index = 1 if (target_specialty_provider is not None and upcoming_count >= 2) else None
    for i in range(upcoming_count):
        apt_id = ctx.next_id("apt")
        days_ahead = ctx.rng.randint(1, 21)
        hour = ctx.rng.randint(9, 16)
        apt_dt = ctx.now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)

        # First upcoming is PCP, optional reserved target-specialty slot,
        # rest alternate.
        if i == 0:
            prov = pcp_provider
        elif i == target_slot_index and target_specialty_provider is not None:
            prov = target_specialty_provider
        elif include_specialist and specialist_providers:
            prov = ctx.rng.choice(specialist_providers)
        else:
            prov = pcp_provider

        apt_type = ctx.rng.choice(["in-person", "telehealth"])
        booked_at = ctx.now - timedelta(days=ctx.rng.randint(1, 14))

        needs_confirm = prov.get("specialty") in confirmation_specialties
        apt_dict = {
            "id": apt_id,
            "provider_id": prov["id"],
            "datetime": apt_dt.isoformat(),
            "type": apt_type,
            "status": "scheduled",
            "reason": ctx.rng.choice(["Follow-up", "Routine checkup", "Medication review", "Annual physical"]),
            "notes": "",
            "linked_referral_id": None,
            "booked_at": booked_at.isoformat(),
            "location": "Main Campus" if apt_type == "in-person" else "Telehealth",
            "requires_confirmation": needs_confirm,
            "confirmation_state": "pending" if needs_confirm else "not_required",
        }
        _link_matching_referral(apt_dict, prov)
        ctx.base["appointments"].append(apt_dict)
        upcoming_ids.append(apt_id)

        if i == 0:
            pcp_apt_id = apt_id
            # Human-readable date for instruction templating (e.g.
            # "March 15 2026 at 10:00"). The raw ISO string is too
            # noisy for a task prompt.
            pcp_apt_date = apt_dt.strftime("%B %-d %Y at %H:%M")
        if i == 0 or (next_appointment_id is None):
            next_appointment_id = apt_id
        if include_specialist and specialist_providers and prov != pcp_provider and specialist_apt_id is None:
            specialist_apt_id = apt_id
        if apt_type == "telehealth" and telehealth_apt_id is None:
            telehealth_apt_id = apt_id
        # PP-5: target_apt_id is the appt for the requested specialty.
        if (
            target_specialty
            and target_apt_id is None
            and prov.get("specialty") == target_specialty
        ):
            target_apt_id = apt_id

    # --- Completed appointments ---
    for _ in range(completed_count):
        apt_id = ctx.next_id("apt")
        days_ago = ctx.rng.randint(7, 90)
        hour = ctx.rng.randint(9, 16)
        apt_dt = ctx.now.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
        prov = ctx.rng.choice(completed_provider_pool)
        booked_at = apt_dt - timedelta(days=ctx.rng.randint(7, 30))

        apt_dict = {
            "id": apt_id,
            "provider_id": prov["id"],
            "datetime": apt_dt.isoformat(),
            "type": ctx.rng.choice(["in-person", "telehealth"]),
            "status": "completed",
            "reason": ctx.rng.choice(["Follow-up", "Lab review", "Consultation"]),
            "notes": "Patient doing well. Continue current treatment plan.",
            "linked_referral_id": None,
            "booked_at": booked_at.isoformat(),
            "location": "Main Campus",
        }
        _link_matching_referral(apt_dict, prov)
        ctx.base["appointments"].append(apt_dict)
        completed_ids.append(apt_id)

    # --- Cancelled appointments ---
    for _ in range(cancelled_count):
        apt_id = ctx.next_id("apt")
        days_ago = ctx.rng.randint(1, 30)
        hour = ctx.rng.randint(9, 16)
        apt_dt = ctx.now.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
        prov = ctx.rng.choice(providers)
        booked_at = apt_dt - timedelta(days=ctx.rng.randint(7, 21))

        apt_dict = {
            "id": apt_id,
            "provider_id": prov["id"],
            "datetime": apt_dt.isoformat(),
            "type": "in-person",
            "status": "cancelled",
            "reason": "Patient requested cancellation",
            "notes": "",
            "linked_referral_id": None,
            "booked_at": booked_at.isoformat(),
            "location": "Main Campus",
        }
        ctx.base["appointments"].append(apt_dict)
        cancelled_ids.append(apt_id)

    # --- Conflict cluster: N overlapping scheduled appointments ---
    # `conflict_count` controls how many appointments share the exact same
    # datetime when `conflict_pair` is set (default 2 = the legacy pair).
    # Two independent sets of consumers read this single cluster:
    #   * pp_cancel_appointment / pp_cancel_duplicate_appointments need the
    #     earliest-booked = KEEP, later-booked = CANCEL partition exposed via
    #     conflict_keep_apt_id / conflict_cancel_apt_ids / conflict_last_booked_apt_id.
    #   * pp_resolve_specialist_conflicts needs the most-recently-booked member
    #     to land on a *specialist* provider (so a same-provider, same-type
    #     earliest-slot reschedule is non-trivial) and exposes that as
    #     later_booked_conflict_apt_id + the type-matched earliest-slot
    #     discriminator.
    #
    # To satisfy BOTH from ONE cluster build, booked_at is strictly increasing
    # with the loop index j (day offsets 0, 1, 2, ...) so ordering is total and
    # deterministic, AND providers cycle providers[j % len(providers)]. For a
    # cluster of three this puts the unique earliest-booked (j==0) on the PCP
    # and the most-recently-booked (j==conflict_count-1) on a specialist
    # provider (providers[2] for the canonical 3-cluster). booked_at values are
    # always distinct so "most-recently-booked" is unambiguous and the
    # keep/cancel partition is well-defined.
    conflict_count = max(2, int(params.get("conflict_count", 2)))
    conflict_keep_apt_id: str | None = None
    conflict_cancel_apt_ids: list[str] = []
    conflict_last_booked_apt_id: str | None = None
    # Most-recently-booked discriminator outputs for the specialist-conflict
    # consumer (None when no cluster was built or no same-type slot exists).
    later_booked_conflict_apt_id: str | None = None
    later_booked_conflict_provider_id: str | None = None
    later_booked_conflict_earliest_slot: str | None = None
    # Type-matched discriminator: the earliest available slot with the SAME
    # visit type (in-person / telehealth) as the later-booked conflict
    # appointment. This is a strictly harder destination than the bare
    # earliest slot because the provider's globally-earliest slot is often
    # the OTHER type (a trap), so the agent must filter slots by type before
    # taking the min rather than reading off the first slot. None when no
    # cluster was built or no same-type slot exists.
    later_booked_conflict_type_matched_earliest_slot: str | None = None
    later_booked_conflict_type: str | None = None
    # PP-CC-TRAP: id of a non-cluster upcoming appointment booked with the
    # SAME provider as the later-booked conflict but at a DIFFERENT
    # (non-overlapping) datetime — a provider-grounding decoy so an agent that
    # shortcuts on "move the appointment with provider X" touches the wrong
    # row. None unless `conflict_provider_grounding_decoy` is set.
    conflict_provider_decoy_apt_id: str | None = None
    if conflict_pair and len(providers) >= 2 and conflict_count >= 2:
        conflict_dt = ctx.now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=ctx.rng.randint(3, 10))
        conflict_apt_date = conflict_dt.strftime("%B %-d %Y at %H:%M")
        # Each appointment booked one day later than the previous so booked_at
        # values are always distinct and ordering is deterministic. The first
        # created (j==0) is the unique earliest-booked (KEEP); the last (j==
        # conflict_count-1) is the most-recently-booked.
        first_booked_at = ctx.now - timedelta(days=ctx.rng.randint(conflict_count, conflict_count + 5))
        conflict_booked_ats = [first_booked_at + timedelta(days=j) for j in range(conflict_count)]
        # PP-CD v2: when shuffle is requested, permute which member receives
        # which booked_at timestamp. The set of timestamps is unchanged (still
        # distinct, still spanning `conflict_count` days), but the EARLIEST
        # booked_at is no longer guaranteed to land on j==0 / the lowest id.
        # The keep/cancel partition is computed by sorting on (booked_at, id)
        # below, so the answer stays correct regardless of permutation — the
        # agent simply can no longer shortcut on id order. The permutation is
        # drawn from the seed RNG so it is deterministic per seed, and we reject
        # the identity permutation (for conflict_count >= 2) so the earliest is
        # provably NOT the first-created member.
        if conflict_shuffle_booked_at and conflict_count >= 2:
            perm = list(range(conflict_count))
            for _attempt in range(16):
                ctx.rng.shuffle(perm)
                # Reject identity: require the earliest booked_at (perm index
                # pointing at conflict_booked_ats[0]) to NOT be member j==0.
                if perm.index(0) != 0:
                    break
            else:
                # Fallback: rotate so member 0 is never the earliest.
                perm = perm[1:] + perm[:1]
                if perm.index(0) == 0:
                    perm = list(reversed(range(conflict_count)))
            conflict_booked_ats = [conflict_booked_ats[perm[j]] for j in range(conflict_count)]
        cluster: list[dict[str, Any]] = []
        for j in range(conflict_count):
            apt_id = ctx.next_id("apt")
            # When conflict_same_provider is set, both appointments use the
            # PCP so booked_at is the only discriminator; otherwise keep the
            # legacy two-different-providers behaviour.
            prov = pcp_provider if conflict_same_provider else providers[j % len(providers)]
            booked_at = conflict_booked_ats[j]

            apt_dict = {
                "id": apt_id,
                "provider_id": prov["id"],
                "datetime": conflict_dt.isoformat(),
                "type": "in-person",
                "status": "scheduled",
                "reason": "Follow-up",
                "notes": "",
                "linked_referral_id": None,
                "booked_at": booked_at.isoformat(),
                "location": "Main Campus",
            }
            _link_matching_referral(apt_dict, prov)
            ctx.base["appointments"].append(apt_dict)
            conflict_apt_ids.append(apt_id)
            upcoming_ids.append(apt_id)
            cluster.append(apt_dict)

        conflict_provider_name = (
            pcp_provider.get("name", "")
            if conflict_same_provider
            else providers[0].get("name", "")
        )
        # Earliest-booked appointment is the one to KEEP; every other member
        # of the cluster must be cancelled. Tie-break on id for total order
        # (booked_at values are distinct here, so the tie-break never fires —
        # it mirrors the canonical_diff predicate for safety).
        ordered = sorted(cluster, key=lambda a: (a["booked_at"], a["id"]))
        conflict_keep_apt_id = ordered[0]["id"]
        conflict_cancel_apt_ids = [a["id"] for a in ordered[1:]]
        # Last-booked (max by booked_at, id) member of the cluster — preserved
        # as a back-compat output so the original `later_booked_apt_id` target
        # still resolves. It is always one of the appointments to cancel.
        conflict_last_booked_apt_id = ordered[-1]["id"]

        # Specialist-conflict consumer (pp_resolve_specialist_conflicts):
        # expose the SAME most-recently-booked cluster member as a set of
        # scalar discriminators so a canonical_diff predicate / solvability
        # proof can pin exact values without recomputing the date math inside a
        # filter/where scope (hazard Class 6). Because booked_at is strictly
        # increasing with j and providers cycle providers[j % len(providers)],
        # this latest-booked member lands on a specialist (e.g. providers[2]
        # for a 3-cluster), making the same-provider, same-type earliest-slot
        # destination non-trivial.
        later_apt = ordered[-1]
        later_booked_conflict_apt_id = later_apt["id"]
        later_booked_conflict_provider_id = later_apt["provider_id"]
        later_prov = next(
            (p for p in providers if p["id"] == later_apt["provider_id"]), None
        )
        # PP-CC-TRAP: when `conflict_guarantee_type_trap` is set, GUARANTEE the
        # type-matched-slot discriminator is non-trivial in EVERY seed. The
        # cluster appointments are `type: in-person`, so the canonical
        # destination is the provider's earliest IN-PERSON slot. Without this
        # guarantee the provider's globally-earliest slot is in-person in a
        # large fraction of seeds (3-6 random slots, 50/50 type coin flip), so
        # the "earliest type-matched slot" collapses to the bare-earliest slot
        # and the trap is a no-op. We force the trap by injecting a strictly-
        # EARLIER telehealth decoy slot one hour before the provider's earliest
        # in-person slot. The bare-earliest slot is then ALWAYS the wrong
        # (telehealth) visit type, so the agent MUST filter slots by visit type
        # before taking min() — a pure backtracking/verification discriminator.
        # (Mirrors the min_slot_specialty closed-panel decoy at lines 726-739.)
        if later_prov and bool(params.get("conflict_guarantee_type_trap", False)):
            later_prov.setdefault("available_slots", [])
            _inperson_dts = [
                s["datetime"]
                for s in later_prov["available_slots"]
                if s.get("type") == "in-person"
            ]
            if not _inperson_dts:
                # The provider has no in-person slot to match the in-person
                # cluster appointment — fabricate one in the future so the
                # destination exists at all, then trap it with an earlier
                # telehealth decoy below.
                _anchor_inperson = conflict_dt + timedelta(days=1)
                later_prov["available_slots"].append({
                    "datetime": _anchor_inperson.isoformat(),
                    "type": "in-person",
                    "duration_minutes": 30,
                })
                _inperson_dts = [_anchor_inperson.isoformat()]
            _earliest_inperson = min(_inperson_dts)
            _decoy_dt = datetime.fromisoformat(_earliest_inperson) - timedelta(hours=1)
            # Avoid colliding with an existing slot datetime.
            _existing_dts = {s["datetime"] for s in later_prov["available_slots"]}
            while _decoy_dt.isoformat() in _existing_dts:
                _decoy_dt -= timedelta(minutes=30)
            later_prov["available_slots"].append({
                "datetime": _decoy_dt.isoformat(),
                "type": "telehealth",
                "duration_minutes": 30,
            })
            later_prov["available_slots"].sort(key=lambda s: s["datetime"])
        if later_prov and later_prov.get("available_slots"):
            later_booked_conflict_earliest_slot = min(
                s["datetime"] for s in later_prov["available_slots"]
            )
            # Same-visit-type earliest slot. The later-booked conflict's own
            # `type` is the constraint; only slots of that exact type qualify.
            later_booked_conflict_type = later_apt.get("type")
            _same_type_slots = [
                s["datetime"]
                for s in later_prov["available_slots"]
                if s.get("type") == later_apt.get("type")
            ]
            if _same_type_slots:
                later_booked_conflict_type_matched_earliest_slot = min(
                    _same_type_slots
                )

        # PP-CC-TRAP: provider-grounding decoy. Book a 4th non-cluster upcoming
        # appointment with the SAME provider as the later-booked conflict, at a
        # distinct (non-overlapping) datetime well before the conflict slot, in
        # the OPPOSITE visit type. An agent that grounds on "the appointment
        # with provider X" (rather than re-deriving the most-recently-booked
        # cluster member) will touch this decoy and fail — it is frozen by the
        # critical sibling invariant. None unless opted in.
        if later_apt is not None and bool(
            params.get("conflict_provider_grounding_decoy", False)
        ):
            decoy_apt_id = ctx.next_id("apt")
            # Two days before the conflict slot, distinct hour — no overlap.
            decoy_dt = (conflict_dt - timedelta(days=2)).replace(hour=8)
            decoy_type = (
                "telehealth" if later_apt.get("type") == "in-person" else "in-person"
            )
            # Booked between the cluster's first-booked and now so it is neither
            # the earliest- nor the latest-booked across the full upcoming set.
            decoy_booked_at = first_booked_at + timedelta(hours=12)
            decoy_apt = {
                "id": decoy_apt_id,
                "provider_id": later_apt["provider_id"],
                "datetime": decoy_dt.isoformat(),
                "type": decoy_type,
                "status": "scheduled",
                "reason": "Follow-up",
                "notes": "",
                "linked_referral_id": None,
                "booked_at": decoy_booked_at.isoformat(),
                "location": "Main Campus" if decoy_type == "in-person" else "Telehealth",
                "requires_confirmation": False,
                "confirmation_state": "not_required",
            }
            _link_matching_referral(decoy_apt, later_prov or {})
            ctx.base["appointments"].append(decoy_apt)
            upcoming_ids.append(decoy_apt_id)
            conflict_provider_decoy_apt_id = decoy_apt_id

        # PP-CD v2: DECOY same-time group — a second cluster of scheduled
        # appointments that share THEIR OWN distinct datetime but are
        # legitimately separate visits (different providers, an explicitly
        # non-duplicate reason). They are NOT in conflict_cancel_apt_ids, so the
        # `a.id not in conflict_cancel_apt_ids` invariant freezes them at
        # critical severity: an agent that cancels a member of this group
        # (because it, too, is "same-time") fails. This forces the agent to
        # identify WHICH same-time group is the duplicate set rather than
        # cancelling any overlapping pair it finds.
        if conflict_decoy_same_time_count >= 2:
            decoy_dt = conflict_dt + timedelta(days=ctx.rng.randint(1, 4))
            # Guarantee the decoy datetime never equals the live cluster's.
            while decoy_dt.isoformat() == conflict_dt.isoformat():
                decoy_dt = decoy_dt + timedelta(days=1)
            for d in range(conflict_decoy_same_time_count):
                apt_id = ctx.next_id("apt")
                prov = providers[(d + 1) % len(providers)]
                booked_at = ctx.now - timedelta(days=ctx.rng.randint(2, 20))
                apt_dict = {
                    "id": apt_id,
                    "provider_id": prov["id"],
                    "datetime": decoy_dt.isoformat(),
                    "type": "in-person",
                    "status": "scheduled",
                    # A distinct, non-duplicate reason. These are real,
                    # separate visits that merely happen to overlap.
                    "reason": ctx.rng.choice(
                        ["Specialist consult", "Lab draw", "Imaging"]
                    ),
                    "notes": "",
                    "linked_referral_id": None,
                    "booked_at": booked_at.isoformat(),
                    "location": "Main Campus",
                }
                _link_matching_referral(apt_dict, prov)
                ctx.base["appointments"].append(apt_dict)
                upcoming_ids.append(apt_id)

        # PP-CD v2: already-CANCELLED appointment(s) sharing the LIVE cluster's
        # exact datetime. A content-blind agent could mistake one of these for a
        # live duplicate and try to re-cancel it (the endpoint 422s on a
        # non-scheduled appointment), or assume the duplicate set is already
        # partially resolved. They are not scheduled and not in the cancel set,
        # so they are inert to the canonical diff but widen the confusion.
        for _c in range(conflict_cancelled_same_time_count):
            apt_id = ctx.next_id("apt")
            prov = providers[_c % len(providers)]
            booked_at = ctx.now - timedelta(days=ctx.rng.randint(7, 30))
            apt_dict = {
                "id": apt_id,
                "provider_id": prov["id"],
                "datetime": conflict_dt.isoformat(),
                "type": "in-person",
                "status": "cancelled",
                "reason": "Patient requested cancellation",
                "notes": "",
                "linked_referral_id": None,
                "cancellation_reason": "Patient requested cancellation",
                "booked_at": booked_at.isoformat(),
                "location": "Main Campus",
            }
            ctx.base["appointments"].append(apt_dict)
            cancelled_ids.append(apt_id)

    # --- Conflict clusters: multiple groups of double/triple-booked
    # scheduled appointments. `conflict_clusters` is a list of integers, each
    # the size of one cluster (number of appointments sharing one exact
    # datetime). Within every cluster booked_at values are STRICTLY
    # increasing, so the first appointment created is the unique
    # earliest-booked (the one to KEEP) and every later one is a later-booked
    # duplicate (to CANCEL). Distinct clusters land on distinct datetimes so
    # they never cross-collide.
    #
    # This generalises the single `conflict_pair` flow (PP-CC). The two are
    # independent: tasks may opt into either. `conflict_clusters` precomputes
    # the per-cluster keep/cancel partition and exposes it as scalar target
    # lists (`cluster_cancel_apt_ids` / `cluster_keep_apt_ids`) so a canonical
    # diff can saturate a cancel bijection over the cancel set and freeze the
    # keep set WITHOUT reconstructing the group-by-datetime + earliest-booked
    # tie-break inside a predicate (rule-6 comprehension-scope hazard).
    conflict_clusters: list[int] = [int(n) for n in (params.get("conflict_clusters") or [])]
    cluster_all_apt_ids: list[str] = []
    cluster_cancel_apt_ids: list[str] = []
    cluster_keep_apt_ids: list[str] = []
    # PP-CC-2 discrimination knobs (all opt-in; default preserves v1 behaviour):
    #   keeper_trap_clusters (list[int]) — cluster indices whose EARLIEST-booked
    #     keeper is deliberately placed on a non-PCP specialist provider with a
    #     `telehealth` visit type, while the later-booked duplicates sit on the
    #     PCP with an `in-person` type. The keep/cancel partition is STILL purely
    #     booked_at ordering (keeper is k==0, the earliest), so it stays exactly
    #     correct — but a naive "keep the PCP one / keep the in-person one"
    #     heuristic cancels the keeper, which trips the critical keeper-scheduled
    #     constraint. Directly attacks the most-tempting backtracking failure.
    #   pseudo_conflict_count (int) — number of decoy same-datetime groups where
    #     exactly ONE member is `scheduled` and the rest are `completed`. These
    #     share a datetime but are NOT real conflicts (only one scheduled), so
    #     the scheduled member must NOT be cancelled. The agent must filter to
    #     status=='scheduled' AND exact (date,time) before partitioning;
    #     cancelling the scheduled pseudo member is the new tempting trap.
    #     Exposed as `pseudo_conflict_apt_ids` (the scheduled survivors) so the
    #     canonical_diff can freeze them with a critical invariant.
    keeper_trap_clusters: set[int] = {
        int(i) for i in (params.get("keeper_trap_clusters") or [])
    }
    pseudo_conflict_count: int = int(params.get("pseudo_conflict_count", 0) or 0)
    pseudo_conflict_apt_ids: list[str] = []
    if conflict_clusters and len(providers) >= 1:
        # Spread clusters across distinct future days/hours. Day offsets are
        # drawn from a disjoint band per cluster so two clusters cannot share a
        # datetime even after the hour pick.
        used_days: set[int] = set()
        # A monotonically increasing booking clock so EVERY cluster appointment
        # across the whole seed has a globally-unique booked_at and the
        # earliest-per-cluster is unambiguous.
        booking_cursor = ctx.now - timedelta(days=30)
        for c_idx, size in enumerate(conflict_clusters):
            size = max(2, int(size))
            # Pick a distinct day offset for this cluster.
            day_off = ctx.rng.randint(3, 21)
            while day_off in used_days:
                day_off = (day_off % 21) + 3
            used_days.add(day_off)
            cluster_hour = ctx.rng.choice([9, 11, 13, 14, 15])
            # Cluster appointments sit on the half-hour (minute=30). Every
            # other appointment generator in this builder lands on minute=0,
            # so a cluster datetime can NEVER collide with a non-cluster
            # upcoming/completed/cancelled appointment — the conflict groups
            # the agent must resolve are exactly the cluster groups, with no
            # accidental cross-contamination from distractor appointments.
            cluster_dt = ctx.now.replace(
                hour=cluster_hour, minute=30, second=0, microsecond=0
            ) + timedelta(days=day_off)

            cluster_ids_local: list[str] = []
            is_trap = c_idx in keeper_trap_clusters
            # For a keeper-trap cluster, the earliest-booked keeper (k==0) goes
            # on a specialist provider with a telehealth type; the later-booked
            # duplicates (k>=1) all land on the PCP with an in-person type. This
            # makes the keeper look like the "odd one out" to a heuristic agent
            # that keeps the PCP / in-person appointment.
            trap_specialist = (
                specialist_providers[c_idx % len(specialist_providers)]
                if (is_trap and specialist_providers)
                else None
            )
            for k in range(size):
                # Advance the global booking clock by a random positive step so
                # booked_at is strictly increasing within (and across) clusters.
                booking_cursor = booking_cursor + timedelta(
                    hours=ctx.rng.randint(6, 40)
                )
                apt_id = ctx.next_id("apt")
                if is_trap and trap_specialist is not None:
                    if k == 0:
                        prov = trap_specialist
                        apt_type = "telehealth"
                    else:
                        prov = pcp_provider
                        apt_type = "in-person"
                else:
                    prov = providers[(c_idx + k) % len(providers)]
                    apt_type = "in-person"
                apt_dict = {
                    "id": apt_id,
                    "provider_id": prov["id"],
                    "datetime": cluster_dt.isoformat(),
                    "type": apt_type,
                    "status": "scheduled",
                    "reason": ctx.rng.choice(
                        ["Follow-up", "Routine checkup", "Consultation"]
                    ),
                    "notes": "",
                    "linked_referral_id": None,
                    "booked_at": booking_cursor.isoformat(),
                    "location": "Telehealth" if apt_type == "telehealth" else "Main Campus",
                }
                _link_matching_referral(apt_dict, prov)
                ctx.base["appointments"].append(apt_dict)
                upcoming_ids.append(apt_id)
                cluster_all_apt_ids.append(apt_id)
                cluster_ids_local.append(apt_id)
            # First created == earliest booked == KEEP. Rest == CANCEL.
            cluster_keep_apt_ids.append(cluster_ids_local[0])
            cluster_cancel_apt_ids.extend(cluster_ids_local[1:])

        # De-collision pass (PP-CC): when conflict_clusters is active the ONLY
        # legitimate same-datetime groups are the clusters themselves. The
        # generic upcoming generator picks random (day, hour) on minute=0, so
        # two distractor upcoming appointments can coincidentally share a
        # datetime and form a spurious conflict group the precomputed
        # keep/cancel partition does not cover. Nudge any such non-cluster
        # scheduled appointment forward in 1-day steps until its datetime is
        # unique among all scheduled appointments. Cluster datetimes sit on
        # minute=30 and are never touched, so this never breaks a real cluster.
        cluster_id_set = set(cluster_all_apt_ids)
        taken_dts: set[str] = set()
        for a in ctx.base["appointments"]:
            if a.get("status") == "scheduled":
                taken_dts.add(a["datetime"])
        for a in ctx.base["appointments"]:
            if a.get("status") != "scheduled" or a["id"] in cluster_id_set:
                continue
            # Count how many scheduled appointments share this datetime.
            same = [
                o for o in ctx.base["appointments"]
                if o.get("status") == "scheduled" and o["datetime"] == a["datetime"]
            ]
            if len(same) <= 1:
                continue
            # Shift THIS appointment to the next free datetime (keep minute=0
            # so it never lands inside a cluster's minute=30 slot).
            dt = datetime.fromisoformat(a["datetime"])
            for _ in range(60):
                dt = dt + timedelta(days=1)
                candidate = dt.isoformat()
                if candidate not in taken_dts:
                    taken_dts.discard(a["datetime"])
                    a["datetime"] = candidate
                    taken_dts.add(candidate)
                    break

        # PP-CC-2 pseudo-conflict (status-filter) decoys. Each group puts ONE
        # scheduled appointment and one or more `completed` appointments on the
        # exact same datetime. They SHARE a datetime with the scheduled member
        # but are NOT a real conflict to resolve (only one member is scheduled),
        # so the scheduled survivor must be LEFT scheduled. An agent that groups
        # by datetime WITHOUT first filtering to status=='scheduled' will see a
        # spurious "conflict" and cancel the scheduled member — a critical
        # over-cancellation error. The scheduled survivors are exposed as
        # `pseudo_conflict_apt_ids` so the canonical_diff can freeze them.
        # Pseudo groups sit on minute=45 so they never collide with cluster
        # (minute=30) or distractor/upcoming (minute=0) datetimes.
        if pseudo_conflict_count > 0:
            for pc_idx in range(pseudo_conflict_count):
                pc_day = 24 + pc_idx * 2  # well past the cluster day band (3-21)
                pc_hour = ctx.rng.choice([9, 11, 13, 15])
                pc_dt = ctx.now.replace(
                    hour=pc_hour, minute=45, second=0, microsecond=0
                ) + timedelta(days=pc_day)
                # Scheduled survivor (must NOT be cancelled).
                sched_prov = providers[pc_idx % len(providers)]
                sched_id = ctx.next_id("apt")
                sched_booked = ctx.now - timedelta(days=ctx.rng.randint(10, 25))
                sched_apt = {
                    "id": sched_id,
                    "provider_id": sched_prov["id"],
                    "datetime": pc_dt.isoformat(),
                    "type": "in-person",
                    "status": "scheduled",
                    "reason": ctx.rng.choice(["Follow-up", "Routine checkup"]),
                    "notes": "",
                    "linked_referral_id": None,
                    "booked_at": sched_booked.isoformat(),
                    "location": "Main Campus",
                }
                ctx.base["appointments"].append(sched_apt)
                upcoming_ids.append(sched_id)
                pseudo_conflict_apt_ids.append(sched_id)
                # A completed appointment sharing the same datetime (the decoy
                # that makes the datetime LOOK double-booked). It is already
                # `completed`, so it is not a conflict to resolve.
                comp_prov = providers[(pc_idx + 1) % len(providers)]
                comp_id = ctx.next_id("apt")
                comp_booked = pc_dt - timedelta(days=ctx.rng.randint(7, 20))
                comp_apt = {
                    "id": comp_id,
                    "provider_id": comp_prov["id"],
                    "datetime": pc_dt.isoformat(),
                    "type": "in-person",
                    "status": "completed",
                    "reason": "Lab review",
                    "notes": "Patient doing well. Continue current treatment plan.",
                    "linked_referral_id": None,
                    "booked_at": comp_booked.isoformat(),
                    "location": "Main Campus",
                }
                ctx.base["appointments"].append(comp_apt)
                completed_ids.append(comp_id)

    # Back-compat: when `conflict_clusters` is used WITHOUT the legacy
    # `conflict_pair`, expose the first cluster's ids as `conflict_apt_ids`
    # so existing tasks/variants that read `{output.conflict_apt_ids}` and
    # `{output.conflict_apt_ids.1}` still resolve to real conflicting
    # appointments (slot 0 = earliest-booked keep, slot 1 = a later-booked
    # cancel). Does not affect callers that already pass `conflict_pair`.
    if not conflict_pair and conflict_clusters and len(cluster_all_apt_ids) >= 2:
        # Rebuild the first cluster's id list (size of clusters[0]) from the
        # ordered cluster_all_apt_ids prefix.
        first_size = max(2, int(conflict_clusters[0]))
        conflict_apt_ids = list(cluster_all_apt_ids[:first_size])

        # Pre-compute the discriminator the agent must re-derive: the
        # most-recently-booked of the cluster, tie-broken by id ascending.
        # Exposed as scalar targets so canonical_diff predicates and the
        # solvability proof can pin exact values without recomputing the
        # date math inside a filter/where scope (hazard Class 6).
        conflict_apts = [
            a for a in ctx.base["appointments"] if a["id"] in conflict_apt_ids
        ]
        later_apt = max(conflict_apts, key=lambda a: (a["booked_at"], a["id"]))
        later_booked_conflict_apt_id = later_apt["id"]
        later_booked_conflict_provider_id = later_apt["provider_id"]
        later_prov = next(
            (p for p in providers if p["id"] == later_apt["provider_id"]), None
        )
        if later_prov and later_prov.get("available_slots"):
            later_booked_conflict_earliest_slot = min(
                s["datetime"] for s in later_prov["available_slots"]
            )
            # Same-visit-type earliest slot. The later-booked conflict's own
            # `type` is the constraint; only slots of that exact type qualify.
            later_booked_conflict_type = later_apt.get("type")
            _same_type_slots = [
                s["datetime"]
                for s in later_prov["available_slots"]
                if s.get("type") == later_apt.get("type")
            ]
            if _same_type_slots:
                later_booked_conflict_type_matched_earliest_slot = min(
                    _same_type_slots
                )

    # PP-5: when target_specialty is unset (or no matching provider was
    # found), fall back to specialist_apt_id so consumers can read a
    # uniform `target_apt_id` field regardless of the seed shape.
    if target_apt_id is None:
        target_apt_id = specialist_apt_id

    return {
        "upcoming_ids": upcoming_ids,
        "completed_ids": completed_ids,
        "cancelled_ids": cancelled_ids,
        "next_appointment_id": next_appointment_id,
        "conflict_apt_ids": conflict_apt_ids,
        "conflict_apt_date": conflict_apt_date,
        "conflict_provider_name": conflict_provider_name,
        "conflict_keep_apt_id": conflict_keep_apt_id,
        "conflict_cancel_apt_ids": conflict_cancel_apt_ids,
        "conflict_last_booked_apt_id": conflict_last_booked_apt_id,
        # Pre-computed scalar discriminators for the conflict cluster (None
        # when no cluster was built). `later_booked_conflict_apt_id` is the
        # most-recently-booked conflict (tie-break: id asc);
        # `later_booked_conflict_provider_id` is its provider; and
        # `later_booked_conflict_earliest_slot` is that provider's earliest
        # available slot datetime (ISO string) — the canonical destination
        # for an in-place reschedule or a cancel+rebook.
        "later_booked_conflict_apt_id": later_booked_conflict_apt_id,
        "later_booked_conflict_provider_id": later_booked_conflict_provider_id,
        "later_booked_conflict_earliest_slot": later_booked_conflict_earliest_slot,
        # `later_booked_conflict_type` is the visit type (in-person /
        # telehealth) of the later-booked conflict; the type-matched slot is
        # that provider's earliest available slot of THAT SAME type — the
        # canonical destination when a task requires preserving visit type.
        "later_booked_conflict_type": later_booked_conflict_type,
        "later_booked_conflict_type_matched_earliest_slot": later_booked_conflict_type_matched_earliest_slot,
        # PP-CC-TRAP: provider-grounding decoy (4th upcoming appt sharing the
        # later-booked conflict's provider at a distinct datetime). None unless
        # `conflict_provider_grounding_decoy` was set.
        "conflict_provider_decoy_apt_id": conflict_provider_decoy_apt_id,
        "pcp_apt_id": pcp_apt_id,
        "pcp_apt_date": pcp_apt_date,
        "specialist_apt_id": specialist_apt_id,
        "telehealth_apt_id": telehealth_apt_id,
        "target_apt_id": target_apt_id,
        # PP-CC conflict-cluster outputs (empty unless `conflict_clusters` set).
        "cluster_all_apt_ids": cluster_all_apt_ids,
        "cluster_cancel_apt_ids": cluster_cancel_apt_ids,
        "cluster_keep_apt_ids": cluster_keep_apt_ids,
        # PP-CC-2 pseudo-conflict survivors (scheduled appointments that share a
        # datetime with a COMPLETED decoy but are NOT a conflict to resolve).
        # Empty unless `pseudo_conflict_count` > 0.
        "pseudo_conflict_apt_ids": pseudo_conflict_apt_ids,
    }


# ---------------------------------------------------------------------------
# 5. prescription_cabinet
# ---------------------------------------------------------------------------

@_register("prescription_cabinet")
def build_prescription_cabinet(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate prescriptions with varying refill states.

    Params: active_count (int), expired_count (int), zero_refill_count (int),
            expiring_soon_count (int), expiring_zero_refill_count (int),
            expiring_zero_refill_days (list[int]), far_zero_refill_count (int),
            far_zero_refill_days (list[int]),
            interaction_pair (bool), source_pharmacy_role (str),
            source_active_count (int), source_exclude_pharmacy_name (str),
            maintenance_medications (list[str])
    Outputs: active_rx_ids, zero_refill_rx_id, expiring_rx_ids,
             expiring_zero_refill_rx_ids, far_zero_refill_rx_ids,
             interacting_rx_ids,
             interacting_medications, zero_refill_rx_ids,
             zero_refill_medications, rxes_at_source_pharmacy,
             non_source_active_rx_ids, source_pharmacy_id,
             retail_refillable_active_rx_ids, maintenance_rx_ids,
             non_maintenance_rx_ids, maintenance_rx_medications

    Note on ``maintenance_medications``: the named medications are pinned into
    the front of the active set (so both partition subsets are non-empty and
    deterministic) and the active rxes are split into ``maintenance_rx_ids``
    (medication matches a maintenance name) vs ``non_maintenance_rx_ids``.
    Used by formulary-partition tasks (e.g. pp_insurance_plan_change) where the
    new plan covers maintenance meds only via mail-order while retail meds must
    stay at the default pharmacy.

    Note on ``expiring_zero_refill_count``: forces the first N entries of
    the ``expiring_rx_ids`` subset to have ``refills_remaining == 0``. This
    lets tasks deterministically pin the "expiring AND zero-refill" target
    intersection. Remaining expiring rxes get ``randint(1, 2)`` so the
    distinction is meaningful.

    Note on ``source_pharmacy_role`` / ``source_active_count``: pins the first
    ``source_active_count`` ACTIVE prescriptions onto the pharmacy identified
    by ``source_pharmacy_role`` (``"mail_order"`` or ``"default"``) and exposes
    that exact id set as ``rxes_at_source_pharmacy``. The remaining active
    prescriptions are pinned off the source (and, if
    ``source_exclude_pharmacy_name`` is given, off the transfer destination
    too) and exposed as ``non_source_active_rx_ids`` so a transfer bijection
    can saturate over a deterministic subset while the rest stay decoys.
    """
    active_count = params.get("active_count", 3)
    expired_count = params.get("expired_count", 0)
    zero_refill_count = params.get("zero_refill_count", 0)
    expiring_soon_count = params.get("expiring_soon_count", 0)
    expiring_zero_refill_count = params.get("expiring_zero_refill_count", 0)
    # Near-boundary expiry computation (state_tracking lever). When supplied,
    # ``expiring_zero_refill_days`` pins the EXACT day-offset-from-anchor of
    # each expiring zero-refill target (instead of the legacy ``randint(5, 25)``
    # that lands every target deep inside the window). Used to seat targets at
    # +26/+28/+29/+30 days so the agent cannot eyeball "expiring soon" and must
    # compute days-to-expiry against the floating seed clock. Offsets are
    # consumed in order; if fewer offsets than ``expiring_zero_refill_count``
    # are given, the remaining targets fall back to the legacy random window.
    expiring_zero_refill_days_raw = params.get("expiring_zero_refill_days") or []
    expiring_zero_refill_days = [int(d) for d in expiring_zero_refill_days_raw]
    # FAR zero-refill traps: active prescriptions with refills_remaining == 0
    # whose expiry lands JUST OUTSIDE the 30-day window (e.g. +31/+33/+37/+44
    # days from the anchor). They share the "0 refills" axis with the renew
    # targets but must be SKIPPED because they are not expiring within 30 days.
    # Without these the 30-day cutoff is never exercised (every zero-refill rx
    # is either deep-inside or far-outside). Exposed as ``far_zero_refill_rx_ids``
    # so a constraint can freeze the whole set without recomputing the cutoff
    # inside a predicate (Class 6 set-precompute hazard). Offsets are taken
    # from ``far_zero_refill_days`` in order (recycled if shorter than the
    # count); each must be > 30 so the rx is genuinely out-of-window across the
    # ±24h anchor jitter (use >= 31 to stay clear of the boundary).
    far_zero_refill_count = int(params.get("far_zero_refill_count", 0) or 0)
    far_zero_refill_days_raw = params.get("far_zero_refill_days") or []
    far_zero_refill_days = [int(d) for d in far_zero_refill_days_raw] or [31, 33, 37, 44]
    interaction_pair = params.get("interaction_pair", False)
    # When True, after the genuine active↔active interaction pair is wired up,
    # attach a DECOY interaction entry between an expired prescription and one
    # active prescription that is NOT a member of the genuine pair. This means
    # the cabinet contains two prescriptions whose ``interactions`` list is
    # non-empty but only ONE pair is an active↔active conflict; an agent that
    # naively scans for ``interactions != []`` (rather than confirming both
    # members are ``status == "active"``) will surface the wrong pair. Requires
    # ``interaction_pair`` and at least one expired prescription to take effect.
    expired_interaction_decoy = bool(params.get("expired_interaction_decoy", False))
    # When True (and there are at least TWO expired prescriptions plus a spare
    # active rx), wire a SECOND decoy interaction onto a DIFFERENT expired rx and
    # a DIFFERENT active rx (disjoint from the genuine pair AND from the first
    # decoy). This thickens the active/expired discrimination: the agent now has
    # to reject TWO tempting ``interactions != []`` cross-links whose partner is
    # not active, not one. Requires ``expired_interaction_decoy``.
    second_expired_interaction_decoy = bool(
        params.get("second_expired_interaction_decoy", False)
    )
    # When True, the EXPIRED prescriptions (created by ``expired_count``) are
    # added to the precomputed renewable set ``renewable_rx_ids`` and exposed
    # individually via ``expired_renewable_rx_ids`` / ``expired_renewable_rx_id``.
    # This is the backtracking lever for pp_request_renewal: an expired rx still
    # reports 0 refills, so an agent that naively maps "0 refills -> refill"
    # will POST /medications/{id}/refill and hit a 422 (refill requires status
    # == active), forcing it to discover the blocker and re-route to the
    # renewal endpoint (which accepts status in {active, expired}). The renewal
    # bijection then spans THREE seed sub-categories — dedicated zero-refill,
    # expiring-AND-zero-refill, and expired — so no single literal reading
    # ("renew the one zero-refill" / "renew everything expiring") saturates it.
    # Default False keeps every existing prescription_cabinet consumer
    # byte-identical (renewable_rx_ids then collapses to the two zero-refill
    # categories, which is what pre-v2 tasks already renewed).
    renew_expired = bool(params.get("renew_expired", False))
    target_medication_name: str | None = params.get("target_medication_name")
    target_exclude_mail_order = bool(params.get("target_exclude_mail_order", False))
    target_exclude_pharmacy_name: str | None = params.get("target_exclude_pharmacy_name")
    # ----- Cost-optimization eligibility fixture (pp_rx_cost_optimization) -----
    # The cost-optimization task asks the agent to transfer EXACTLY the active
    # prescriptions that are (retail AND refills>=1) to the cheapest mail-order
    # pharmacy. The legacy builder placed the non-target actives on a RANDOM
    # pharmacy (mail-order included) with refills randint(2,6), so the eligible
    # set size wobbled across seeds (3..5) and the conjunctive (retail AND
    # refills>=1) predicate was never actually stressed at retail. These knobs
    # make the eligibility partition DETERMINISTIC and add the two excludes the
    # weakest models collapse on:
    #   - ``retail_refillable_pin_count`` (int): pin the first N non-target
    #     actives to a non-default, non-mail-order RETAIL pharmacy with >=2
    #     refills (genuine eligible members — they MUST be transferred).
    #   - ``mail_order_active_count`` (int): pin the next M actives to a
    #     mail-order pharmacy with refills (honest "already at mail-order"
    #     excludes — present at a mail-order pharmacy so they must NOT move).
    #   - ``retail_zero_refill_count`` (int): create K *additional* active
    #     prescriptions pinned to a RETAIL pharmacy but with refills_remaining=0
    #     (the conjunctive trap: "currently filled at retail" is true but
    #     refills==0 forces exclusion).
    # The target rx (Atorvastatin) is always retail+refillable via
    # ``target_exclude_mail_order`` and is the first eligible member.
    retail_refillable_pin_count = int(params.get("retail_refillable_pin_count", 0) or 0)
    mail_order_active_count = int(params.get("mail_order_active_count", 0) or 0)
    retail_zero_refill_count = int(params.get("retail_zero_refill_count", 0) or 0)
    # When True, the FIRST expired prescription reuses ``target_medication_name``
    # so an agent that "transfers Atorvastatin" by medication-name match alone
    # surfaces an expired same-name decoy it must NOT touch.
    expired_target_decoy = bool(params.get("expired_target_decoy", False))
    # When True, every active prescription starts on the default pharmacy.
    # Used by tasks like pp_coordinate_rx_transfer where the scenario is
    # "your default pharmacy is closing — transfer all your active rxes to
    # another retail pharmacy". We need each rx to actually move (not be
    # already at the destination) so the canonical_diff update[0] bijection
    # saturates.
    active_at_default_only = bool(params.get("active_at_default_only", False))
    # PP: place exactly the first N active prescriptions on the default
    # pharmacy (the "transfer set") and the remaining active prescriptions on
    # `active_trap_pharmacy_id` (a non-default retail pharmacy that should NOT
    # be touched). Lets a task expose `active_at_default_rx_ids` so a transfer
    # bijection saturates over exactly the rxes at the closing/old default
    # while sibling rxes at another pharmacy act as a frozen distractor set.
    active_at_default_count = int(params.get("active_at_default_count", 0) or 0)
    active_trap_pharmacy_id: str | None = params.get("active_trap_pharmacy_id")
    # PP grounding stressor: after the first ``active_at_default_count`` active
    # rxes are pinned to the OLD default (the transfer set), the remaining
    # active rxes are distributed round-robin across
    # ``active_decoy_pharmacy_ids`` instead of a single trap. This lets a task
    # seed a multi-pharmacy frozen distractor set — e.g. one active rx already
    # sitting at the NEW (cheapest) default pharmacy (which must NOT be
    # "moved"), plus actives at one or more other retail traps. When this list
    # is empty the builder falls back to the legacy single
    # ``active_trap_pharmacy_id`` behaviour so existing tasks are byte-identical.
    # ``active_at_new_default_pharmacy_id`` (when set and present in the decoy
    # list) is exposed back so a task can pin a "do not transfer the rx that is
    # already at the destination" decoy deterministically; the id set of active
    # rxes that landed on it is exposed as ``active_at_new_default_rx_ids``.
    active_decoy_pharmacy_ids_raw = params.get("active_decoy_pharmacy_ids") or []
    if isinstance(active_decoy_pharmacy_ids_raw, str):
        active_decoy_pharmacy_ids = [active_decoy_pharmacy_ids_raw]
    else:
        active_decoy_pharmacy_ids = [str(p) for p in active_decoy_pharmacy_ids_raw]
    active_at_new_default_pharmacy_id: str | None = params.get(
        "active_at_new_default_pharmacy_id"
    )
    # Deterministically pin the first ``expired_at_default_count`` EXPIRED rxes
    # onto the OLD default pharmacy. An expired rx at the closing default is a
    # natural decoy: an agent reading "everything at my old pharmacy" might
    # sweep it into the transfer set, but the instruction restricts transfers to
    # ACTIVE rxes only, so it must stay frozen. Defaults to 0 (legacy random
    # placement for expired rxes).
    expired_at_default_count = int(params.get("expired_at_default_count", 0) or 0)
    # Force the FIRST `source_active_count` active prescriptions onto a
    # single "source" pharmacy identified by role. Used by tasks like
    # pp_transfer_prescription where the scenario is "the mail-order pharmacy
    # is discontinuing — transfer exactly the prescriptions filled there to a
    # specific retail location". The remaining active prescriptions are
    # pinned to a pharmacy that is NEITHER the source NOR (optionally) the
    # destination, so they are decoys the agent must NOT move. Exposes the
    # exact subset as `rxes_at_source_pharmacy` so a bijection can saturate
    # over a deterministic set without reconstructing the filter inside a
    # predicate (Class 6 set-in-filter hazard). `source_pharmacy_role` is one
    # of {"mail_order", "default"}; `source_exclude_pharmacy_name` keeps the
    # NON-source active rxes off the transfer destination so they stay decoys.
    source_pharmacy_role: str | None = params.get("source_pharmacy_role")
    source_active_count = int(params.get("source_active_count", 0) or 0)
    source_exclude_pharmacy_name: str | None = params.get("source_exclude_pharmacy_name")
    # Formulary partition: tasks like pp_insurance_plan_change need the active
    # prescriptions split into a "maintenance / mail-order-only" subset (which
    # the new plan covers only via the mail-order pharmacy) and the remaining
    # retail subset (which must stay at the default retail pharmacy). The
    # caller passes the canonical medication names that are designated
    # maintenance meds; the builder PINS those medications into the active set
    # (so the partition is deterministic and both subsets are non-empty) and
    # exposes the two disjoint id lists as outputs. Matching is by
    # case-insensitive medication-name substring against the rx medication.
    maintenance_medications: list[str] = [
        str(m) for m in (params.get("maintenance_medications") or [])
    ]

    if "prescriptions" not in ctx.base:
        ctx.base["prescriptions"] = []

    providers = ctx.base.get("providers", [])
    pharmacies = ctx.base.get("pharmacies", [])
    pcp_id = ctx.base.get("patient", {}).get("pcp_id", "prov_1")
    default_pharm_id = next((p["id"] for p in pharmacies if p.get("is_default")), "pharm_1") if pharmacies else "pharm_1"

    # Resolve the "source" pharmacy id (the one the source active rxes are
    # pinned to) from its role. Falls back to None when no matching pharmacy
    # exists; in that case the source-pinning logic is skipped and
    # `rxes_at_source_pharmacy` stays empty.
    source_pharmacy_id: str | None = None
    if source_pharmacy_role == "mail_order":
        source_pharmacy_id = next(
            (p["id"] for p in pharmacies if p.get("is_mail_order")), None
        )
    elif source_pharmacy_role == "default":
        source_pharmacy_id = default_pharm_id if pharmacies else None

    # Resolve the pharmacies the cost-optimization fixture pins onto. The
    # "retail pin" pharmacy is a non-default, non-mail-order retail pharmacy
    # (so the rx is genuinely "at retail" and the agent must MOVE it, rather
    # than it already sitting at the default it would stay on). The mail-order
    # pin target is the first mail-order pharmacy (an honest "already at
    # mail-order" exclude). Both fall back to None, in which case the
    # corresponding pin loop is skipped.
    retail_pin_pharmacy_id: str | None = next(
        (
            p["id"] for p in pharmacies
            if not p.get("is_mail_order") and not p.get("is_default")
        ),
        None,
    )
    mail_order_pin_pharmacy_id: str | None = next(
        (p["id"] for p in pharmacies if p.get("is_mail_order")), None
    )

    # Shuffle the medication pool, then pin target_medication_name first if specified
    med_pool = list(_MEDICATIONS)
    ctx.rng.shuffle(med_pool)
    if target_medication_name:
        pinned = next(
            (m for m in med_pool if target_medication_name.lower() in m["name"].lower()),
            None,
        )
        if pinned:
            med_pool.remove(pinned)
            med_pool.insert(0, pinned)
    # Pin maintenance medications to the front of the pool (preserving the
    # caller-supplied order) so the first active rxes are exactly the
    # maintenance meds. This makes the maintenance/retail partition
    # deterministic regardless of the shuffle. Pinned AFTER
    # target_medication_name so an explicit single target still wins slot 0.
    if maintenance_medications:
        maintenance_pinned: list[dict[str, Any]] = []
        for needle in maintenance_medications:
            match = next(
                (m for m in med_pool if needle.lower() in m["name"].lower()),
                None,
            )
            if match is not None:
                med_pool.remove(match)
                maintenance_pinned.append(match)
        med_pool = maintenance_pinned + med_pool
    med_idx = 0

    active_rx_ids: list[str] = []
    zero_refill_rx_id: str | None = None
    zero_refill_medication: str = ""
    # Full list of the dedicated zero-refill active prescriptions created by the
    # ``zero_refill_count`` loop (NOT the expiring subset). Tasks that must
    # renew *every* out-of-refills prescription (e.g. pp_request_renewal, which
    # asks the agent to renew each medication that has 0 refills remaining)
    # need the complete set to drive a bijection without recomputing the
    # refills==0 filter inside a predicate (Class 6 set-precompute hazard).
    zero_refill_rx_ids: list[str] = []
    zero_refill_medications: list[str] = []
    target_rx_id: str | None = None
    expiring_rx_ids: list[str] = []
    expiring_zero_refill_rx_ids: list[str] = []
    # FAR (out-of-window) zero-refill prescriptions — share the 0-refill axis
    # with the renew targets but expire > 30 days out, so they must be skipped.
    far_zero_refill_rx_ids: list[str] = []
    interacting_rx_ids: list[str] = []
    interacting_medications: list[str] = []
    # Subset of active rxes deterministically pinned to the source pharmacy
    # (e.g. the discontinuing mail-order pharmacy). This is the canonical
    # transfer set for pp_transfer_prescription.
    rxes_at_source_pharmacy: list[str] = []

    def _make_rx(
        med: dict,
        status: str,
        refills: int,
        expires_days: int,
        *,
        force_retail_pharmacy: bool = False,
        exclude_pharmacy_name: str | None = None,
        force_default_pharmacy: bool = False,
        pin_pharmacy_id: str | None = None,
        force_pharmacy_id: str | None = None,
        exclude_pharmacy_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        nonlocal med_idx
        rx_id = ctx.next_id("rx")
        provider_id = ctx.rng.choice([p["id"] for p in providers]) if providers else pcp_id
        available_pharmacies = list(pharmacies)
        if force_default_pharmacy and pharmacies:
            default_match = [p for p in pharmacies if p.get("is_default")]
            if default_match:
                available_pharmacies = default_match
        if force_retail_pharmacy and pharmacies:
            retail_pharmacies = [p for p in pharmacies if not p.get("is_mail_order")]
            if retail_pharmacies:
                available_pharmacies = retail_pharmacies
        if exclude_pharmacy_name:
            filtered = [
                p for p in available_pharmacies
                if exclude_pharmacy_name.lower() not in p.get("name", "").lower()
            ]
            if filtered:
                available_pharmacies = filtered
        if exclude_pharmacy_ids:
            filtered = [
                p for p in available_pharmacies
                if p.get("id") not in exclude_pharmacy_ids
            ]
            if filtered:
                available_pharmacies = filtered
        # An explicit pharmacy id pin overrides every heuristic above so the
        # rx lands deterministically on the requested pharmacy. ``pin_pharmacy_id``
        # (used to build a controlled "transfer set" at the default and a frozen
        # distractor set at another retail pharmacy) and ``force_pharmacy_id``
        # (used by the source-pharmacy transfer fixture) are driven by distinct,
        # mutually-exclusive callers; either one wins over the random choice.
        if pin_pharmacy_id and any(p["id"] == pin_pharmacy_id for p in pharmacies):
            pharm_id = pin_pharmacy_id
        elif force_pharmacy_id and any(p["id"] == force_pharmacy_id for p in pharmacies):
            pharm_id = force_pharmacy_id
        else:
            pharm_id = ctx.rng.choice([p["id"] for p in available_pharmacies]) if available_pharmacies else default_pharm_id
        last_filled = ctx.now - timedelta(days=ctx.rng.randint(7, 60))
        expires_at = ctx.now + timedelta(days=expires_days)

        return {
            "id": rx_id,
            "medication": med["name"],
            "dosage": med["dosage"],
            "frequency": med["frequency"],
            "provider_id": provider_id,
            "pharmacy_id": pharm_id,
            "refills_remaining": refills,
            "last_filled": last_filled.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": status,
            "interactions": [],
        }

    # Active prescriptions (normal refills)
    active_at_default_rx_ids: list[str] = []
    active_at_new_default_rx_ids: list[str] = []
    for active_idx in range(active_count):
        if med_idx >= len(med_pool):
            break
        med = med_pool[med_idx]
        med_idx += 1
        is_target_med = bool(
            target_medication_name
            and target_medication_name.lower() in med["name"].lower()
        )
        force_retail_pharmacy = bool(target_exclude_mail_order and is_target_med)
        exclude_pharmacy_for_rx = (
            target_exclude_pharmacy_name if is_target_med else None
        )
        # When active_at_default_count is set: pin the first N active rxes to
        # the default pharmacy (the transfer set) and the rest to the trap
        # pharmacy (a frozen distractor set). This takes precedence over the
        # random/force_default placement so the split is deterministic.
        pin_pharmacy_for_rx: str | None = None
        if active_at_default_count > 0:
            if active_idx < active_at_default_count:
                pin_pharmacy_for_rx = default_pharm_id
            elif active_decoy_pharmacy_ids:
                # Distribute the non-transfer-set actives round-robin across the
                # decoy pharmacies (which may include the NEW default itself, a
                # second retail trap, etc.) so the agent faces a multi-pharmacy
                # frozen distractor set rather than a single trap.
                decoy_pos = active_idx - active_at_default_count
                pin_pharmacy_for_rx = active_decoy_pharmacy_ids[
                    decoy_pos % len(active_decoy_pharmacy_ids)
                ]
            elif active_trap_pharmacy_id:
                pin_pharmacy_for_rx = active_trap_pharmacy_id
        # Cost-optimization pinning (pp_rx_cost_optimization): the target rx is
        # slot 0 (forced retail + refillable via target_exclude_mail_order). The
        # NEXT ``retail_refillable_pin_count`` non-target actives are pinned to a
        # retail pharmacy with deterministic >=2 refills (genuine eligible
        # members), then the following ``mail_order_active_count`` actives are
        # pinned to a mail-order pharmacy (honest "already at mail-order"
        # excludes). This freezes the eligible-set cardinality across seeds.
        refills_override: int | None = None
        if (retail_refillable_pin_count > 0 or mail_order_active_count > 0) and not is_target_med:
            non_target_idx = active_idx - (1 if target_medication_name else 0)
            if 0 <= non_target_idx < retail_refillable_pin_count:
                if retail_pin_pharmacy_id is not None:
                    pin_pharmacy_for_rx = retail_pin_pharmacy_id
                    refills_override = ctx.rng.randint(2, 6)
            elif (
                retail_refillable_pin_count
                <= non_target_idx
                < retail_refillable_pin_count + mail_order_active_count
            ):
                if mail_order_pin_pharmacy_id is not None:
                    pin_pharmacy_for_rx = mail_order_pin_pharmacy_id
                    refills_override = ctx.rng.randint(2, 6)
        # Source-pharmacy pinning: the first `source_active_count` active rxes
        # land on the source pharmacy (the transfer set); the rest are pinned
        # off the source AND (optionally) off the destination so they are
        # decoys the agent must not move.
        force_pharmacy_for_rx: str | None = None
        exclude_pharmacy_ids_for_rx: tuple[str, ...] = ()
        is_source_rx = False
        if source_pharmacy_id is not None and source_active_count > 0:
            if active_idx < source_active_count:
                force_pharmacy_for_rx = source_pharmacy_id
                is_source_rx = True
            else:
                # Non-source actives must NOT live on the source pharmacy
                # (otherwise the "transfer everything at the mail-order
                # pharmacy" instruction would be ambiguous), and they stay off
                # the transfer destination so they remain legitimate decoys.
                exclude_pharmacy_ids_for_rx = (source_pharmacy_id,)
                if source_exclude_pharmacy_name and exclude_pharmacy_for_rx is None:
                    exclude_pharmacy_for_rx = source_exclude_pharmacy_name
        rx = _make_rx(
            med,
            "active",
            refills_override if refills_override is not None else ctx.rng.randint(2, 6),
            ctx.rng.randint(90, 365),
            force_retail_pharmacy=force_retail_pharmacy,
            exclude_pharmacy_name=exclude_pharmacy_for_rx,
            force_default_pharmacy=active_at_default_only,
            pin_pharmacy_id=pin_pharmacy_for_rx,
            force_pharmacy_id=force_pharmacy_for_rx,
            exclude_pharmacy_ids=exclude_pharmacy_ids_for_rx,
        )
        ctx.base["prescriptions"].append(rx)
        active_rx_ids.append(rx["id"])
        if (
            active_at_default_count > 0
            and active_idx < active_at_default_count
            and rx["pharmacy_id"] == default_pharm_id
        ):
            active_at_default_rx_ids.append(rx["id"])
        if (
            active_at_new_default_pharmacy_id
            and rx["pharmacy_id"] == active_at_new_default_pharmacy_id
        ):
            active_at_new_default_rx_ids.append(rx["id"])
        if is_source_rx:
            rxes_at_source_pharmacy.append(rx["id"])
        # Track target rx if this medication matches the pinned target
        if target_medication_name and target_rx_id is None:
            if target_medication_name.lower() in med["name"].lower():
                target_rx_id = rx["id"]

    # Zero-refill prescriptions. The first ``retail_zero_refill_count`` of these
    # are pinned to a RETAIL pharmacy (the conjunctive eligibility trap for
    # pp_rx_cost_optimization: "currently filled at retail" is true, but
    # refills==0 must still exclude it). The remainder keep legacy random
    # placement. When ``active_at_default_only`` is set every zero-refill rx
    # starts on the closing default pharmacy so its transfer is never a no-op.
    for zr_idx in range(zero_refill_count):
        if med_idx >= len(med_pool):
            break
        med = med_pool[med_idx]
        med_idx += 1
        zr_pin = (
            retail_pin_pharmacy_id
            if zr_idx < retail_zero_refill_count and retail_pin_pharmacy_id is not None
            else None
        )
        rx = _make_rx(
            med, "active", 0, ctx.rng.randint(30, 180),
            force_default_pharmacy=active_at_default_only,
            pin_pharmacy_id=zr_pin,
        )
        ctx.base["prescriptions"].append(rx)
        active_rx_ids.append(rx["id"])
        zero_refill_rx_ids.append(rx["id"])
        zero_refill_medications.append(med["name"])
        if zero_refill_rx_id is None:
            zero_refill_rx_id = rx["id"]
            zero_refill_medication = med["name"]

    # Expiring-soon prescriptions. The first ``expiring_zero_refill_count``
    # entries are forced to refills=0 so the "expiring AND zero-refill"
    # intersection is deterministic across seeds; remaining ones get 1-2
    # refills so they explicitly should NOT be renewed.
    n_expiring_zero = min(expiring_zero_refill_count, expiring_soon_count)
    for idx in range(expiring_soon_count):
        # Cycle the medication pool rather than breaking when exhausted, so a
        # task that seeds a large partition (many expiring + far zero-refill
        # rxes) still gets every required prescription. Ids stay unique; only
        # the display medication name repeats. Tasks that stay within the
        # 10-med pool are unaffected (med_idx never wraps for them).
        med = med_pool[med_idx % len(med_pool)]
        med_idx += 1
        if idx < n_expiring_zero:
            refills = 0
        elif expiring_zero_refill_count > 0:
            # Deterministic non-zero refill count for the "has refills" subset.
            refills = ctx.rng.randint(1, 2)
        else:
            # Legacy behaviour for tasks that didn't opt in to the split.
            refills = ctx.rng.randint(0, 2)
        # Near-boundary expiry for the zero-refill targets when explicit offsets
        # are provided; otherwise keep the legacy deep-inside-window draw. The
        # explicit offsets seat targets at +26/+28/+29/+30 days so the 30-day
        # cutoff is a genuine per-rx computation against the floating clock.
        if refills == 0 and idx < len(expiring_zero_refill_days):
            expires_days = expiring_zero_refill_days[idx]
        else:
            expires_days = ctx.rng.randint(5, 25)
        rx = _make_rx(
            med, "active", refills, expires_days,
            force_default_pharmacy=active_at_default_only,
        )
        ctx.base["prescriptions"].append(rx)
        active_rx_ids.append(rx["id"])
        expiring_rx_ids.append(rx["id"])
        if refills == 0:
            expiring_zero_refill_rx_ids.append(rx["id"])

    # FAR zero-refill traps: active, refills_remaining == 0, expiring JUST
    # outside the 30-day window. They look like renew targets on the refill
    # axis but must be skipped on the expiry axis. Days are taken from
    # ``far_zero_refill_days`` in order (recycled), each > 30.
    for far_idx in range(far_zero_refill_count):
        med = med_pool[med_idx % len(med_pool)]
        med_idx += 1
        far_days = far_zero_refill_days[far_idx % len(far_zero_refill_days)]
        rx = _make_rx(med, "active", 0, far_days)
        ctx.base["prescriptions"].append(rx)
        active_rx_ids.append(rx["id"])
        far_zero_refill_rx_ids.append(rx["id"])

    # Expired prescriptions
    expired_rx_ids: list[str] = []
    expired_at_default_rx_ids: list[str] = []
    # When expired_target_decoy is set, mint the FIRST expired rx with the target
    # medication so a name-match-only agent surfaces an expired same-name decoy
    # it must NOT transfer. Pinned to a retail pharmacy so it superficially looks
    # like an eligible "retail Atorvastatin" until the agent reads status.
    target_med_dict: dict[str, Any] | None = None
    if expired_target_decoy and target_medication_name:
        target_med_dict = next(
            (
                m for m in _MEDICATIONS
                if target_medication_name.lower() in m["name"].lower()
            ),
            None,
        )
    for expired_idx in range(expired_count):
        if expired_idx == 0 and target_med_dict is not None:
            med = target_med_dict
        else:
            med = med_pool[med_idx % len(med_pool)]
            med_idx += 1
        # Pin the first ``expired_at_default_count`` expired rxes to the OLD
        # default pharmacy so they sit alongside the active transfer set as a
        # status-based decoy (same pharmacy, but expired → must NOT move). The
        # rx_cost target-decoy (slot 0) instead pins to a retail pharmacy so a
        # name-match agent is lured by an expired "retail Atorvastatin".
        if expired_idx == 0 and target_med_dict is not None:
            pin_expired = retail_pin_pharmacy_id
        elif expired_idx < expired_at_default_count:
            pin_expired = default_pharm_id
        else:
            pin_expired = None
        rx = _make_rx(
            med, "expired", 0, -ctx.rng.randint(1, 90),
            pin_pharmacy_id=pin_expired,
        )
        ctx.base["prescriptions"].append(rx)
        expired_rx_ids.append(rx["id"])
        if (
            expired_idx < expired_at_default_count
            and not (expired_idx == 0 and target_med_dict is not None)
            and rx["pharmacy_id"] == default_pharm_id
        ):
            expired_at_default_rx_ids.append(rx["id"])

    # Interaction pair -- two active meds with mutual conflict entries
    if interaction_pair and len(_INTERACTION_PAIRS) > 0:
        pair = ctx.rng.choice(_INTERACTION_PAIRS)
        pair_meds = [
            next((m for m in _MEDICATIONS if m["name"] == pair[0]), None),
            next((m for m in _MEDICATIONS if m["name"] == pair[1]), None),
        ]
        if pair_meds[0] and pair_meds[1]:
            rx_ids_pair: list[str] = []
            for k, pm in enumerate(pair_meds):
                # Reuse an existing prescription for this medication ONLY when it
                # is ACTIVE — the interaction pair must be an active↔active
                # conflict. If the only existing match is expired (or none
                # exists), mint a fresh ACTIVE prescription so the genuine pair
                # is always actionable regardless of seed.
                existing = next(
                    (
                        r for r in ctx.base["prescriptions"]
                        if r["medication"] == pm["name"] and r.get("status") == "active"
                    ),
                    None,
                )
                if existing:
                    rx_ids_pair.append(existing["id"])
                else:
                    rx = _make_rx(pm, "active", ctx.rng.randint(1, 4), ctx.rng.randint(60, 200))
                    ctx.base["prescriptions"].append(rx)
                    active_rx_ids.append(rx["id"])
                    rx_ids_pair.append(rx["id"])

            # Set interactions on both
            for rx_dict in ctx.base["prescriptions"]:
                if rx_dict["id"] == rx_ids_pair[0]:
                    rx_dict["interactions"] = [pair[1]]
                elif rx_dict["id"] == rx_ids_pair[1]:
                    rx_dict["interactions"] = [pair[0]]

            interacting_rx_ids = rx_ids_pair
            interacting_medications = list(pair)

    # Decoy interaction trap: wire a cross-interaction between an expired
    # prescription and one ACTIVE prescription that is NOT part of the genuine
    # active↔active pair. The decoy is intentionally invalid (one member is
    # expired), so the only conflict that warrants action is the genuine pair.
    decoy_interaction_rx_ids: list[str] = []
    if expired_interaction_decoy and expired_rx_ids:
        expired_id = expired_rx_ids[0]
        expired_rx = next(
            (r for r in ctx.base["prescriptions"] if r["id"] == expired_id), None
        )
        # Choose an active rx outside the genuine pair as the decoy's active side.
        decoy_active = next(
            (
                r for r in ctx.base["prescriptions"]
                if r.get("status") == "active"
                and r["id"] not in interacting_rx_ids
            ),
            None,
        )
        if expired_rx is not None and decoy_active is not None:
            expired_rx["interactions"] = [decoy_active["medication"]]
            decoy_active["interactions"] = [expired_rx["medication"]]
            decoy_interaction_rx_ids = [expired_id, decoy_active["id"]]

    # Second decoy interaction trap (opt-in): a DIFFERENT expired rx cross-linked
    # to a DIFFERENT active rx, disjoint from both the genuine active↔active pair
    # and the first decoy. With two such traps the agent must verify member
    # status across MORE non-empty ``interactions`` lists before it can isolate
    # the single active↔active conflict — a deeper state-tracking demand, not an
    # ambiguity (the instruction already says to ignore any interaction involving
    # an expired prescription).
    second_decoy_interaction_rx_ids: list[str] = []
    if (
        second_expired_interaction_decoy
        and expired_interaction_decoy
        and len(expired_rx_ids) >= 2
        and decoy_interaction_rx_ids
    ):
        used_ids = set(interacting_rx_ids) | set(decoy_interaction_rx_ids)
        second_expired_id = next(
            (eid for eid in expired_rx_ids if eid not in used_ids), None
        )
        second_decoy_active = next(
            (
                r for r in ctx.base["prescriptions"]
                if r.get("status") == "active"
                and r["id"] not in used_ids
            ),
            None,
        )
        second_expired_rx = next(
            (r for r in ctx.base["prescriptions"] if r["id"] == second_expired_id),
            None,
        )
        if second_expired_rx is not None and second_decoy_active is not None:
            second_expired_rx["interactions"] = [second_decoy_active["medication"]]
            second_decoy_active["interactions"] = [second_expired_rx["medication"]]
            second_decoy_interaction_rx_ids = [
                second_expired_id,
                second_decoy_active["id"],
            ]

    # Provider ids that wrote the genuine active↔active interaction pair. Tasks
    # that route the agent to a prescriber (rather than the PCP) can pin this;
    # exposed unconditionally so it is available without re-scanning rx records.
    interacting_prescriber_ids: list[str] = []
    for rid in interacting_rx_ids:
        rx_obj = next((r for r in ctx.base["prescriptions"] if r["id"] == rid), None)
        if rx_obj is not None:
            interacting_prescriber_ids.append(rx_obj["provider_id"])

    # Subset of expiring rxes that still have ≥1 refill remaining — this is
    # the "request refill" target for tasks that distinguish refill-vs-renewal
    # based on whether the expiring rx has refills left.
    expiring_with_refills_rx_ids = [
        rid for rid in expiring_rx_ids
        if rid not in expiring_zero_refill_rx_ids
    ]

    # Precomputed canonical RENEWAL set for pp_request_renewal. Every member is
    # a prescription that has 0 refills remaining and is renewal-eligible
    # (status in {active, expired}), spanning up to three seed sub-categories:
    #   * the dedicated active zero-refill rxes (``zero_refill_rx_ids``),
    #   * the expiring-AND-zero-refill rxes (``expiring_zero_refill_rx_ids``), and
    #   * (only when ``renew_expired`` is set) the expired rxes
    #     (``expired_renewable_rx_ids``), which are the backtracking gate.
    # The union is computed here — never inside a canonical_diff predicate — so
    # the renewal bijection iterates a single deterministic scalar list (Class 6
    # set-precompute hazard). Order is category-stable and de-duplicated while
    # preserving first appearance so the list is fully deterministic across
    # seeds. ``expiring_with_refills_rx_ids`` are deliberately EXCLUDED: those
    # are expiring but still have refills, so they are refill-eligible decoys
    # the agent must NOT renew.
    expired_renewable_rx_ids: list[str] = list(expired_rx_ids) if renew_expired else []
    expired_renewable_rx_id: str | None = (
        expired_renewable_rx_ids[0] if expired_renewable_rx_ids else None
    )
    _renewable_seen: set[str] = set()
    renewable_rx_ids: list[str] = []
    for rid in [*zero_refill_rx_ids, *expiring_zero_refill_rx_ids, *expired_renewable_rx_ids]:
        if rid not in _renewable_seen:
            _renewable_seen.add(rid)
            renewable_rx_ids.append(rid)

    # Active rxes NOT pinned to the source pharmacy. These share the "active"
    # category with the transfer set but must remain on their current
    # pharmacy — they are the decoys a filtered invariant freezes.
    non_source_active_rx_ids = [
        rid for rid in active_rx_ids if rid not in rxes_at_source_pharmacy
    ]

    # Parallel medication-name lists for the source / non-source partitions.
    # Exposed so a misleading narrative (e.g. a "pharmacy closing" notice in a
    # message thread) can be authored deterministically against the SEEDED med
    # names without re-reading the cabinet, while the canonical transfer set
    # stays keyed off the structured ``rxes_at_source_pharmacy`` ids. The names
    # are returned in ``active_rx_ids`` order for determinism.
    _rx_by_id_for_names = {rx["id"]: rx for rx in ctx.base["prescriptions"]}
    source_medication_names = [
        str(_rx_by_id_for_names[rid]["medication"])
        for rid in rxes_at_source_pharmacy
        if rid in _rx_by_id_for_names
    ]
    non_source_active_medication_names = [
        str(_rx_by_id_for_names[rid]["medication"])
        for rid in non_source_active_rx_ids
        if rid in _rx_by_id_for_names
    ]

    # Cost-optimization eligibility set: the active prescriptions that are both
    # (a) currently dispensed by a RETAIL (non-mail-order) pharmacy and
    # (b) have at least one refill remaining (so they can actually be filled at
    # a new pharmacy without first requiring a renewal). These are the only
    # prescriptions a "move my refillable retail prescriptions to mail order"
    # task should transfer. Active rxes that are already at a mail-order
    # pharmacy, or that have zero refills remaining, are deliberately EXCLUDED
    # and must be left frozen. Precomputed here as a scalar list so the
    # canonical_diff bijection can iterate it directly (Class 6: never compute
    # this set inside a filter/where predicate). Ids are returned in
    # active_rx_ids order for determinism.
    mail_order_pharm_ids = {
        p["id"] for p in pharmacies if p.get("is_mail_order")
    }
    rx_by_id = {rx["id"]: rx for rx in ctx.base["prescriptions"]}
    retail_refillable_active_rx_ids = [
        rid for rid in active_rx_ids
        if (rx := rx_by_id.get(rid)) is not None
        and rx.get("pharmacy_id") not in mail_order_pharm_ids
        and int(rx.get("refills_remaining", 0)) >= 1
    ]

    # Formulary partition over the ACTIVE prescriptions: an active rx is a
    # "maintenance / mail-order-only" rx iff its medication matches one of the
    # caller-supplied maintenance_medications (case-insensitive substring).
    # The complement is the "retail" subset that must stay at the default
    # pharmacy. Both lists are disjoint and cover active_rx_ids exactly, so a
    # task can drive one bijection over each subset (move-to-mail-order vs
    # freeze-at-retail) without reconstructing the partition inside a
    # predicate. Computed in builder per Class-6 (sets must be precomputed).
    def _rx_medication(rid: str) -> str:
        for r in ctx.base["prescriptions"]:
            if r["id"] == rid:
                return str(r.get("medication", ""))
        return ""

    maintenance_lc = [m.lower() for m in maintenance_medications]
    maintenance_rx_ids: list[str] = []
    non_maintenance_rx_ids: list[str] = []
    for rid in active_rx_ids:
        med_name = _rx_medication(rid).lower()
        if maintenance_lc and any(needle in med_name for needle in maintenance_lc):
            maintenance_rx_ids.append(rid)
        else:
            non_maintenance_rx_ids.append(rid)
    # Parallel list of the maintenance medication display names actually
    # present in the active set (for instruction/grading cross-reference).
    maintenance_rx_medications = [_rx_medication(rid) for rid in maintenance_rx_ids]

    return {
        "active_rx_ids": active_rx_ids,
        "active_at_default_rx_ids": active_at_default_rx_ids,
        "active_at_new_default_rx_ids": active_at_new_default_rx_ids,
        "expired_rx_ids": expired_rx_ids,
        "expired_at_default_rx_ids": expired_at_default_rx_ids,
        "expired_renewable_rx_ids": expired_renewable_rx_ids,
        "expired_renewable_rx_id": expired_renewable_rx_id,
        "renewable_rx_ids": renewable_rx_ids,
        "zero_refill_rx_id": zero_refill_rx_id,
        "zero_refill_medication": zero_refill_medication,
        "zero_refill_rx_ids": zero_refill_rx_ids,
        "zero_refill_medications": zero_refill_medications,
        "target_rx_id": target_rx_id,
        "expiring_rx_ids": expiring_rx_ids,
        "expiring_zero_refill_rx_ids": expiring_zero_refill_rx_ids,
        "far_zero_refill_rx_ids": far_zero_refill_rx_ids,
        # Scalar single-id handles for the first two renew-targets. Variant
        # injections render placeholders by whole-string {target.KEY} match (no
        # list indexing), so a contradictory-message stressor that must LINK to
        # one genuine renew-target needs a scalar id exposed here. None when the
        # set is empty.
        "first_expiring_zero_refill_rx_id": (
            expiring_zero_refill_rx_ids[0] if expiring_zero_refill_rx_ids else None
        ),
        "second_expiring_zero_refill_rx_id": (
            expiring_zero_refill_rx_ids[1] if len(expiring_zero_refill_rx_ids) > 1 else None
        ),
        "expiring_with_refills_rx_ids": expiring_with_refills_rx_ids,
        "retail_refillable_active_rx_ids": retail_refillable_active_rx_ids,
        "interacting_rx_ids": interacting_rx_ids,
        "interacting_medications": interacting_medications,
        "interacting_prescriber_ids": interacting_prescriber_ids,
        "decoy_interaction_rx_ids": decoy_interaction_rx_ids,
        "second_decoy_interaction_rx_ids": second_decoy_interaction_rx_ids,
        # Source-pharmacy transfer fixture outputs.
        "rxes_at_source_pharmacy": rxes_at_source_pharmacy,
        "non_source_active_rx_ids": non_source_active_rx_ids,
        "source_pharmacy_id": source_pharmacy_id,
        "source_medication_names": source_medication_names,
        "non_source_active_medication_names": non_source_active_medication_names,
        "maintenance_rx_ids": maintenance_rx_ids,
        "non_maintenance_rx_ids": non_maintenance_rx_ids,
        "maintenance_rx_medications": maintenance_rx_medications,
    }


# ---------------------------------------------------------------------------
# 6. lab_results_panel
# ---------------------------------------------------------------------------

@_register("lab_results_panel")
def build_lab_results_panel(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate lab results across dates and statuses.

    Params: resulted_count (int), pending_count (int), abnormal_count (int),
            critical_count (int), trend_test (str), trend_values (list[str])
    Outputs: resulted_lab_ids, pending_lab_ids, abnormal_lab_ids, critical_lab_id,
             trend_lab_ids, trend_test_name
    """
    resulted_count = params.get("resulted_count", 3)
    pending_count = params.get("pending_count", 1)
    abnormal_count = params.get("abnormal_count", 1)
    critical_count = params.get("critical_count", 0)
    trend_test = params.get("trend_test", None)
    trend_values = params.get("trend_values", None)

    if "lab_results" not in ctx.base:
        ctx.base["lab_results"] = []

    providers = ctx.base.get("providers", [])
    pcp_id = ctx.base.get("patient", {}).get("pcp_id", "prov_1")
    appointments = ctx.base.get("appointments", [])
    completed_apts = [a for a in appointments if a.get("status") == "completed"]
    linked_apt_cursor = 0

    # Available ordering providers (non-billing, non-admin)
    ordering_providers = [p["id"] for p in providers if p.get("specialty") not in ("billing", "admin")]
    if not ordering_providers:
        ordering_providers = [pcp_id]

    # When a trend_test is specified, exclude it from the random-pick pool so
    # a random normal/abnormal lab doesn't collide with the explicit trend
    # sequence and silently invert the most-recent reading (e.g. HbA1c's
    # normal=5.2 landing within the 6-month window after a 6.5→7.8 trend).
    lab_pool = [t for t in _LAB_TESTS if t["name"] != trend_test] if trend_test else list(_LAB_TESTS)
    ctx.rng.shuffle(lab_pool)
    lab_idx = 0

    resulted_lab_ids: list[str] = []
    pending_lab_ids: list[str] = []
    abnormal_lab_ids: list[str] = []
    critical_lab_id: str | None = None
    trend_lab_ids: list[str] = []
    trend_test_name: str | None = None

    def _pick_lab() -> dict[str, Any]:
        nonlocal lab_idx
        lab = lab_pool[lab_idx % len(lab_pool)]
        lab_idx += 1
        return lab

    def _make_lab(test: dict, flag: str, status: str, days_ago: int, value_override: str | None = None) -> dict[str, Any]:
        nonlocal linked_apt_cursor
        lab_id = ctx.next_id("lab")
        collected_at = ctx.now - timedelta(days=days_ago)
        value = value_override or test[flag] if flag in test else test["normal"]
        linked_apt = None
        if completed_apts:
            linked_apt = completed_apts[linked_apt_cursor % len(completed_apts)]
            linked_apt_cursor += 1
        ordered_by = linked_apt["provider_id"] if linked_apt else ctx.rng.choice(ordering_providers)
        return {
            "id": lab_id,
            "test_name": test["name"],
            "test_code": test["code"],
            "ordered_by": ordered_by,
            "collected_at": collected_at.isoformat(),
            "value": value,
            "unit": test["unit"],
            "reference_range": test["ref"],
            "flag": flag,
            "status": status,
            "linked_appointment_id": linked_apt["id"] if linked_apt else None,
        }

    # Normal resulted labs
    normal_count = max(0, resulted_count - abnormal_count - critical_count)
    for _ in range(normal_count):
        test = _pick_lab()
        # Check if this is a Lipid Panel component -- if the test name matches a
        # lipid component, it's already individual.  We generate panel tests
        # only when explicitly requested via trend_test.
        lab = _make_lab(test, "normal", "resulted", ctx.rng.randint(1, 60))
        ctx.base["lab_results"].append(lab)
        resulted_lab_ids.append(lab["id"])

    # Abnormal labs
    for _ in range(abnormal_count):
        test = _pick_lab()
        lab = _make_lab(test, "abnormal", "resulted", ctx.rng.randint(1, 30))
        ctx.base["lab_results"].append(lab)
        resulted_lab_ids.append(lab["id"])
        abnormal_lab_ids.append(lab["id"])

    # Critical labs
    for _ in range(critical_count):
        test = _pick_lab()
        lab = _make_lab(test, "critical", "resulted", ctx.rng.randint(0, 3))
        ctx.base["lab_results"].append(lab)
        resulted_lab_ids.append(lab["id"])
        abnormal_lab_ids.append(lab["id"])
        if critical_lab_id is None:
            critical_lab_id = lab["id"]

    # Pending labs
    for _ in range(pending_count):
        test = _pick_lab()
        lab_id = ctx.next_id("lab")
        collected_at = ctx.now - timedelta(days=ctx.rng.randint(0, 2))
        linked_apt = None
        if completed_apts:
            linked_apt = completed_apts[linked_apt_cursor % len(completed_apts)]
            linked_apt_cursor += 1
        ordered_by = linked_apt["provider_id"] if linked_apt else ctx.rng.choice(ordering_providers)
        lab = {
            "id": lab_id,
            "test_name": test["name"],
            "test_code": test["code"],
            "ordered_by": ordered_by,
            "collected_at": collected_at.isoformat(),
            "value": "",
            "unit": test["unit"],
            "reference_range": test["ref"],
            "flag": "normal",
            "status": "pending",
            "linked_appointment_id": linked_apt["id"] if linked_apt else None,
        }
        ctx.base["lab_results"].append(lab)
        pending_lab_ids.append(lab_id)

    # Trend test -- create a time series of the same test
    if trend_test and trend_values:
        trend_test_info = next((t for t in _LAB_TESTS if t["name"] == trend_test), None)
        if trend_test_info:
            trend_test_name = trend_test
            for i, val in enumerate(trend_values):
                days_ago = (len(trend_values) - i) * 90  # quarterly spacing
                flag = "normal"
                try:
                    # Determine flag from reference range
                    ref_parts = trend_test_info["ref"].split("-")
                    if len(ref_parts) == 2:
                        low, high = float(ref_parts[0]), float(ref_parts[1])
                        v = float(val)
                        if v > high * 1.5 or v < low * 0.5:
                            flag = "critical"
                        elif v > high or v < low:
                            flag = "abnormal"
                except (ValueError, IndexError):
                    pass

                lab = _make_lab(trend_test_info, flag, "resulted", days_ago, value_override=val)
                ctx.base["lab_results"].append(lab)
                trend_lab_ids.append(lab["id"])
                # If this is a critical trend value and no separate critical lab was created,
                # use it as the primary critical_lab_id
                if flag == "critical" and critical_lab_id is None:
                    critical_lab_id = lab["id"]

            # Adversarial same-test points that DELIBERATELY threaten the
            # last-two-by-collected_at sort. These make eyeballing/lazy
            # grounding fail while staying fair: the canonical discriminator
            # expr filters on ``status == 'resulted'`` and sorts strictly by
            # ``collected_at``, so an agent that applies that exact filter is
            # unaffected, while one that (a) takes the raw trend-view tail
            # without the resulted filter, or (b) mis-sorts the near-duplicate
            # resulted point, lands the wrong row in [-1]/[-2] and may flip the
            # branch. Each entry: {days_ago, value, status, flag?}.
            #   - A NON-``resulted`` (e.g. ``collected``) HbA1c dated MORE
            #     recently than the latest trend point traps agents that skip
            #     the status filter (the /labs/trend view returns every status,
            #     sorted ascending, so this row is the visible tail).
            #   - A ``resulted`` near-duplicate dated one day BEFORE the true
            #     most-recent point becomes the genuine [-2]; its value is set
            #     so the true last pair direction is PRESERVED but only when the
            #     agent sorts by date precisely.
            for spec in params.get("trend_adversarial_points", []) or []:
                if not isinstance(spec, dict):
                    continue
                try:
                    d_ago = float(spec["days_ago"])
                except (KeyError, TypeError, ValueError):
                    continue
                a_status = str(spec.get("status", "resulted"))
                a_val = str(spec.get("value", ""))
                a_flag = spec.get("flag")
                if a_flag is None and trend_test_info is not None:
                    a_flag = "normal"
                    try:
                        ref_parts = trend_test_info["ref"].split("-")
                        if len(ref_parts) == 2:
                            low, high = float(ref_parts[0]), float(ref_parts[1])
                            v = float(a_val)
                            if v > high * 1.5 or v < low * 0.5:
                                a_flag = "critical"
                            elif v > high or v < low:
                                a_flag = "abnormal"
                    except (ValueError, IndexError):
                        pass
                lab = _make_lab(
                    trend_test_info,
                    str(a_flag),
                    a_status,
                    d_ago,
                    value_override=a_val,
                )
                ctx.base["lab_results"].append(lab)

    # Derived: the test_name / test_code of every out-of-range RESULTED lab
    # (flag in {"abnormal", "critical"}), ordered by collected_at descending
    # then lab id, deduplicated while preserving that order. Tasks that ask
    # the agent to RE-DERIVE which resulted labs are out of range (e.g.
    # pp_cross_reference_labs_meds) need a scalar list target so a
    # `substring_all` / `set_eq` predicate can verify the agent named the
    # exact abnormal panel — without pushing reference-range parsing into a
    # `filter:`/`expr` scope (which only sees a+target+initial+state).
    _all_labs_by_id = {lab["id"]: lab for lab in ctx.base["lab_results"]}
    _abnormal_sorted = sorted(
        abnormal_lab_ids,
        key=lambda lid: (_all_labs_by_id[lid]["collected_at"], lid),
        reverse=True,
    )
    abnormal_lab_test_names: list[str] = []
    abnormal_lab_test_codes: list[str] = []
    # Per-lab "<test_name> <value> <unit>" label for every out-of-range
    # RESULTED lab, in the same (collected_at desc, id) order. Tasks that want
    # the agent to RE-DERIVE and quote each abnormal reading's actual value —
    # not merely list the test names — pin a `substring_all`/expr predicate
    # against this scalar list so a generic "review your labs" reason cannot
    # satisfy the gate. The unit is appended only when non-empty (e.g. INR has
    # no unit) so the label is an exact substring an agent can reproduce.
    abnormal_lab_value_labels: list[str] = []
    # test_name of the single most-severe (critical) out-of-range RESULTED lab.
    # Empty string when no critical lab exists. Lets a task escalate the
    # most-tempting "abnormal vs critical" distinction into an exact predicate
    # without pushing flag parsing into a filter scope.
    critical_lab_test_name: str = ""
    for lid in _abnormal_sorted:
        lab = _all_labs_by_id.get(lid)
        if lab is None:
            continue
        if lab["test_name"] not in abnormal_lab_test_names:
            abnormal_lab_test_names.append(lab["test_name"])
        if lab["test_code"] not in abnormal_lab_test_codes:
            abnormal_lab_test_codes.append(lab["test_code"])
        unit = str(lab.get("unit") or "").strip()
        value_label = (
            f"{lab['test_name']} {lab['value']} {unit}".strip()
            if unit
            else f"{lab['test_name']} {lab['value']}".strip()
        )
        if value_label not in abnormal_lab_value_labels:
            abnormal_lab_value_labels.append(value_label)
        if not critical_lab_test_name and lab.get("flag") == "critical":
            critical_lab_test_name = lab["test_name"]

    return {
        "resulted_lab_ids": resulted_lab_ids,
        "pending_lab_ids": pending_lab_ids,
        "abnormal_lab_ids": abnormal_lab_ids,
        "abnormal_lab_test_names": abnormal_lab_test_names,
        "abnormal_lab_test_codes": abnormal_lab_test_codes,
        "abnormal_lab_value_labels": abnormal_lab_value_labels,
        "critical_lab_test_name": critical_lab_test_name,
        "critical_lab_id": critical_lab_id,
        "trend_lab_ids": trend_lab_ids,
        "trend_test_name": trend_test_name,
    }


# ---------------------------------------------------------------------------
# Helper: resolve contextual provider
# ---------------------------------------------------------------------------

def _resolve_context_provider(
    ctx: PatientPortalSeedContext,
    body_context: dict[str, Any],
    clinical_providers: list[dict[str, Any]],
    pcp_id: str,
) -> dict[str, Any] | None:
    providers = ctx.base.get("providers", [])
    providers_by_id = {p["id"]: p for p in providers}

    explicit_provider_id = body_context.get("provider_id")
    if explicit_provider_id:
        return providers_by_id.get(str(explicit_provider_id))

    provider_selector = body_context.get("provider_selector")
    if provider_selector == "pcp":
        return providers_by_id.get(pcp_id)
    if provider_selector == "most_recent_completed":
        completed_apts = [a for a in ctx.base.get("appointments", []) if a.get("status") == "completed"]
        if completed_apts:
            most_recent = max(completed_apts, key=lambda a: a["datetime"])
            return providers_by_id.get(most_recent["provider_id"])

    specialty = body_context.get("provider_specialty")
    if specialty:
        return next((p for p in providers if p.get("specialty") == specialty), None)

    if clinical_providers:
        return clinical_providers[0]
    return providers_by_id.get(pcp_id) or (providers[0] if providers else None)


# ---------------------------------------------------------------------------
# Helper: generate contextual message body
# ---------------------------------------------------------------------------

def _generate_contextual_body(ctx: PatientPortalSeedContext, body_context: dict[str, Any]) -> str:
    """Generate a realistic message body based on *body_context* type.

    Reads from ctx.base["prescriptions"] and ctx.base["providers"] so it must
    be called after those builders have run.
    """
    btype = body_context.get("type", "")
    prescriptions = [rx for rx in ctx.base.get("prescriptions", []) if rx.get("status") == "active"]
    providers = ctx.base.get("providers", [])
    referrals = ctx.base.get("referrals", [])

    if btype == "discharge_summary":
        # List active meds, change one dosage, add one new med, omit one existing med
        if not prescriptions:
            return (
                "Discharge Summary - Medication List:\n"
                "No active medications found in your record.\n"
                "Please contact your care team if you believe this is in error."
            )
        # Work with up to 4 meds for readability
        meds = prescriptions[:4]
        lines = ["Discharge Summary - Medication List:"]
        changed_one = False
        omit_idx = len(meds) - 1  # omit the last active med from the discharge list
        line_number = 1
        for i, rx in enumerate(meds):
            if i == omit_idx:
                continue  # this one is "removed" — not listed on discharge summary
            med_name = rx["medication"]
            freq = rx.get("frequency", "daily")
            if not changed_one and i == 0:
                # Change dosage on first med
                original_dosage = rx.get("dosage", "")
                # Produce a plausibly changed dosage (double or halve)
                try:
                    dose_num = "".join(c for c in original_dosage if c.isdigit())
                    dose_unit = "".join(c for c in original_dosage if not c.isdigit())
                    new_num = int(dose_num) * 2 if int(dose_num) < 100 else int(dose_num) // 2
                    new_dosage = f"{new_num}{dose_unit}"
                except (ValueError, TypeError):
                    new_dosage = original_dosage
                lines.append(
                    f"{line_number}. {med_name.split()[0]} {new_dosage} {freq}"
                    f" (was {original_dosage} - dosage adjusted)"
                )
                changed_one = True
            else:
                lines.append(f"{line_number}. {med_name} {freq} (unchanged)")
            line_number += 1
        # Add one new med not in the current active list
        new_med_name = body_context.get("new_medication_name", "Metformin 500mg")
        new_med_frequency = body_context.get("new_medication_frequency", "twice daily")
        new_med = f"{new_med_name} {new_med_frequency} (NEW - started during hospitalization)"
        lines.append(f"{line_number}. {new_med}")
        # Note the omitted med
        omitted_name = meds[omit_idx]["medication"]
        lines.append(f"Note: {omitted_name} was discontinued during hospitalization.")
        if body_context.get("include_referral_mention"):
            # An explicit `referral_specialty` override wins — downstream callers
            # (e.g. `build_message_threads`) pre-compute a deterministic specialty
            # and set it here so the seed's exposed
            # `context_specialist_provider_ids` target exactly matches the
            # specialty named in the rendered body.
            override_specialty = body_context.get("referral_specialty")
            referral_mentions = [
                ref.get("to_specialty", "specialist").title()
                for ref in referrals
                if ref.get("status") in ("approved", "requested")
            ]
            if override_specialty:
                lines.append(
                    f"Follow-up referral recommended: {str(override_specialty).title()} consultation."
                )
            elif referral_mentions:
                lines.append(
                    "Follow-up referrals noted on discharge: "
                    + ", ".join(sorted(set(referral_mentions[:2])))
                    + ". Please coordinate with your PCP."
                )
            else:
                specialist = next(
                    (p for p in providers if p.get("specialty") not in ("pcp", "billing", "admin")),
                    None,
                )
                if specialist is not None:
                    lines.append(
                        f"Follow-up referral recommended: {specialist.get('specialty', 'specialist').title()} consultation."
                    )
        return "\n".join(lines)

    elif btype in ("formulary_info", "generic_alternative"):
        if not prescriptions:
            return (
                "Formulary Update: Please contact your insurance provider to verify "
                "coverage for your current medications."
            )
        requested_med_name = body_context.get("medication_name")
        new_med_name = body_context.get("new_medication_name")
        include_all_active = bool(body_context.get("include_all_active"))
        alternatives = body_context.get("alternatives", {})
        coverage_map = body_context.get("coverage_status_by_medication", {})
        default_coverage_status = str(body_context.get("coverage_status", "not covered"))
        preferred_pharmacy = body_context.get("preferred_pharmacy")

        def _default_alternative_name(name: str) -> str:
            generic_base = name.split()[0].lower()
            return f"{generic_base.capitalize()} (preferred generic)"

        def _coverage_line(med_name: str, coverage_status: str, alternative: str) -> str:
            coverage_lower = coverage_status.lower()
            if coverage_lower in ("covered", "preferred", "preferred brand", "preferred generic"):
                return f"{med_name}: covered as {coverage_status}."
            return f"{med_name}: {coverage_status}; preferred alternative is {alternative}."

        if include_all_active:
            lines = ["Formulary Review for New Plan:"]
            for rx in prescriptions:
                med_name = rx["medication"]
                alternative = alternatives.get(med_name, _default_alternative_name(med_name))
                coverage_status = str(coverage_map.get(med_name, default_coverage_status))
                lines.append(_coverage_line(med_name, coverage_status, alternative))
            if preferred_pharmacy:
                lines.append(f"Preferred pharmacy for this plan: {preferred_pharmacy}.")
            lines.append("Please let us know which medications need prior authorization.")
            return "\n".join(lines)

        med_name = new_med_name or requested_med_name or prescriptions[0]["medication"]
        alternative = body_context.get("alternative_name", _default_alternative_name(med_name))
        coverage_status = str(coverage_map.get(med_name, default_coverage_status))
        if btype == "formulary_info":
            coverage_lower = coverage_status.lower()
            if coverage_lower in ("covered", "preferred", "preferred brand", "preferred generic"):
                return (
                    f"Formulary Update: The recommended medication {med_name} is covered under your "
                    f"insurance plan as {coverage_status}. You may proceed if you would like to start it."
                )
            return (
                f"Formulary Update: The recommended medication {med_name} is {coverage_status} under "
                f"your insurance plan. The preferred covered alternative is {alternative}. "
                "Please message me if you would like me to prescribe the preferred option instead."
            )
        return (
            f"Cost Optimization Recommendation: The medication option {med_name} has a lower-cost "
            f"alternative available: {alternative}. Switching could reduce your monthly out-of-pocket "
            "cost. Please contact your provider if you would like to authorize the switch."
        )

    elif btype == "bp_medication_adjustment":
        # Find a BP-related med (Lisinopril, Losartan, Amlodipine, etc.) or use first active
        bp_keywords = ("lisinopril", "losartan", "amlodipine", "metoprolol", "atenolol", "valsartan")
        current_medication_name = body_context.get("current_medication_name")
        bp_rx = next(
            (
                rx for rx in prescriptions
                if current_medication_name and current_medication_name.lower() in rx["medication"].lower()
            ),
            None,
        ) or next(
            (rx for rx in prescriptions if any(k in rx["medication"].lower() for k in bp_keywords)),
            prescriptions[0] if prescriptions else None,
        )
        if bp_rx is None:
            return (
                "Based on your recent labs, I'd like to adjust your blood pressure medication. "
                "Please monitor your BP daily and report any dizziness."
            )
        med_name = bp_rx["medication"]
        current_dosage = bp_rx.get("dosage", "current dose")
        new_medication_name = body_context.get("new_medication_name")
        alternative_name = body_context.get("alternative_name")
        coverage_status = str(body_context.get("coverage_status", "covered"))
        if new_medication_name:
            coverage_line = (
                f"Formulary note: {new_medication_name} is covered on your current plan."
                if coverage_status.lower() in ("covered", "preferred", "preferred generic")
                else f"Formulary note: {new_medication_name} is {coverage_status}; preferred covered alternative is {alternative_name}."
            )
            return (
                f"I recommend changing your blood pressure medication from {med_name} to "
                f"{new_medication_name}. Please stop the old dose once you start the new medication "
                f"and monitor your blood pressure daily for the next 2 weeks. {coverage_line}"
            )
        # Produce a new higher dosage
        try:
            dose_num = "".join(c for c in current_dosage if c.isdigit())
            dose_unit = "".join(c for c in current_dosage if not c.isdigit())
            new_num = int(dose_num) * 2 if int(dose_num) < 100 else int(dose_num) + 25
            new_dosage = f"{new_num}{dose_unit}"
        except (ValueError, TypeError):
            new_dosage = "increased dose"
        med_base = med_name.split()[0]
        return (
            f"Based on your recent labs, I'd like to adjust your blood pressure medication. "
            f"Please increase your {med_base} from {current_dosage} to {new_dosage} starting "
            f"next week. Monitor your BP daily and report any dizziness or lightheadedness."
        )

    elif btype == "referral_details":
        # Find a non-PCP, non-billing, non-admin specialist provider
        specialist = next(
            (p for p in providers if p.get("specialty") not in ("pcp", "billing", "admin")),
            None,
        )
        if specialist is None:
            return (
                "Referral Information: A specialist referral has been submitted for you. "
                "Please check the referrals section of your portal for details and contact "
                "your care team with any questions."
            )
        name = specialist.get("name", "Specialist")
        specialty = specialist.get("specialty", "specialist").title()
        return (
            f"Referral Details: I have submitted a referral for you to see {name} "
            f"in our {specialty} department. The referral has been sent to your insurance "
            f"for prior authorization. You should receive approval within 3-5 business days. "
            f"Once approved, please call the {specialty} office to schedule your appointment."
        )

    elif btype == "pharmacy_closure_notice":
        # A "your mail-order pharmacy is closing" notice that lists the
        # affected prescriptions BY MEDICATION NAME. The list is intentionally
        # a DECOY that DISAGREES with the structured per-rx ``pharmacy_id``
        # truth. Two ways to drive it:
        #   * ``source_pharmacy_id`` (preferred): the builder derives the true
        #     set of active rxes at that pharmacy, then renders a MISLEADING
        #     list that (a) OMITS the last true-source medication and (b) ADDS
        #     the first active medication NOT at the source pharmacy. The
        #     narrative therefore names a med that should NOT move and hides one
        #     that must — so an agent that trusts the prose transfers the wrong
        #     set. The text never reveals the true set.
        #   * ``affected_medications`` (literal override): the caller supplies
        #     the exact (already-misleading) name list.
        # The canonical answer for any consuming task must come from the
        # structured state (which rxes have ``pharmacy_id == source``), never
        # from this text — making the message a pure state_tracking trap.
        pharmacy_name = str(body_context.get("pharmacy_name", "your mail-order pharmacy"))
        destination_hint = body_context.get("destination_hint")
        affected = [str(m) for m in (body_context.get("affected_medications") or [])]
        if not affected:
            source_pharmacy_id = body_context.get("source_pharmacy_id")
            if source_pharmacy_id:
                source_meds = [
                    rx["medication"] for rx in prescriptions
                    if rx.get("pharmacy_id") == source_pharmacy_id
                ]
                non_source_meds = [
                    rx["medication"] for rx in prescriptions
                    if rx.get("pharmacy_id") != source_pharmacy_id
                ]
                # OMIT one genuinely-affected med (drop the last true-source med)
                # and ADD one med that is NOT at the closing pharmacy.
                misleading = source_meds[:-1] if len(source_meds) > 1 else list(source_meds)
                if non_source_meds:
                    misleading = misleading + [non_source_meds[0]]
                affected = misleading
        lines = [
            f"Pharmacy Service Notice: {pharmacy_name} is discontinuing service.",
            "Our records indicate the following prescriptions are filled there and "
            "will need to be transferred:",
        ]
        if affected:
            for i, med in enumerate(affected, start=1):
                lines.append(f"{i}. {med}")
        else:
            lines.append("(Please review your medication list for affected prescriptions.)")
        if destination_hint:
            lines.append(
                f"You may transfer these to {destination_hint} or another in-network pharmacy."
            )
        lines.append(
            "Please verify each medication's current pharmacy in your portal before "
            "transferring; this notice is for your convenience and may not reflect "
            "recent changes."
        )
        return "\n".join(lines)

    # Fallback — should not normally be reached
    return ctx.fake.paragraph(nb_sentences=ctx.rng.randint(2, 4))


# ---------------------------------------------------------------------------
# 7. message_threads
# ---------------------------------------------------------------------------

@_register("message_threads")
def build_message_threads(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create message threads with realistic clinical conversations.

    Params: thread_count (int), unread_count (int), categories (list[str]),
            include_billing (bool), include_rx_renewal (bool),
            body_context (dict) — optional; injects specific content into the
            first provider message of the first clinical thread.
            unread_by_category (dict[str, int]) — optional; for each
            ``category -> N`` entry, create N *dedicated* threads (in addition
            to ``thread_count``) whose final message is an UNREAD provider
            message in that exact category. This guarantees a deterministic,
            category-labelled spread of unread messages so a task can target a
            computed subset (e.g. "mark only the unread clinical/scheduling
            messages, leave billing unread") rather than the all-or-nothing
            ``mark-all-read`` shortcut. The category-split ids are exposed via
            ``unread_msg_ids_by_category`` plus convenience scalar lists.
    Outputs: thread_ids, unread_msg_ids, billing_thread_id, rx_renewal_thread_id,
             all_msg_ids, unread_msg_ids_by_category
    """
    thread_count = params.get("thread_count", 3)
    unread_count = params.get("unread_count", 2)
    categories = params.get("categories", ["clinical"])
    include_billing = params.get("include_billing", False)
    include_rx_renewal = params.get("include_rx_renewal", False)
    # Dedicated per-category unread threads. Maps category -> count. Each entry
    # yields exactly `count` threads whose final provider message is unread and
    # carries that category. Purely additive — tasks that omit it are
    # unaffected.
    unread_by_category: dict[str, int] = dict(params.get("unread_by_category", {}) or {})
    body_context: dict[str, Any] | None = params.get("body_context")
    body_contexts: list[dict[str, Any]] = [dict(item) for item in params.get("body_contexts", [])]
    if body_context:
        body_contexts.insert(0, dict(body_context))

    if "messages" not in ctx.base:
        ctx.base["messages"] = []

    providers = ctx.base.get("providers", [])
    clinical_providers = [p for p in providers if p.get("specialty") not in ("billing", "admin")]
    billing_providers = [p for p in providers if p.get("specialty") == "billing"]
    pcp_id = ctx.base.get("patient", {}).get("pcp_id", "prov_1")

    thread_ids: list[str] = []
    unread_msg_ids: list[str] = []
    all_msg_ids: list[str] = []
    # Map of category -> list of UNREAD message ids in that category. Populated
    # both by the main loop (when its randomly-assigned unread message lands in
    # a category) and by the dedicated `unread_by_category` threads below.
    unread_msg_ids_by_category: dict[str, list[str]] = {}
    # Map of body_context type → the id of the first provider message in the
    # thread seeded for that context. Downstream tasks (e.g.
    # pp_respond_to_provider) use this to identify the specific incoming
    # message the agent must read.
    context_msg_ids: dict[str, str] = {}
    # Per-context-type: the specialty string named inside the rendered body
    # (currently populated for `discharge_summary` contexts that include a
    # referral mention) and the list of provider ids matching that specialty
    # in the seeded directory. Enables downstream tasks (e.g.
    # pp_post_hospitalization) to look up the single legitimate set of
    # "specialist follow-up" providers without re-parsing the body text.
    context_specialties: dict[str, str] = {}
    context_specialist_provider_ids: dict[str, list[str]] = {}
    # Per-context-type: for `discharge_summary` contexts, the rx id the body
    # text flags as "discontinued during hospitalization". Mirrors
    # `_generate_contextual_body`'s logic — the omitted rx is the last entry
    # of the first 4 active prescriptions, so downstream tasks (e.g.
    # pp_medication_reconciliation) can identify the exact rx the agent must
    # route through the renewal flow without re-parsing the body string.
    context_discontinued_rx_ids: dict[str, list[str]] = {}
    billing_thread_id: str | None = None
    rx_renewal_thread_id: str | None = None
    unread_assigned = 0

    for t in range(thread_count):
        thread_id = ctx.next_id("thread")
        thread_ids.append(thread_id)
        thread_context = body_contexts.pop(0) if body_contexts else None

        # Decide category for this thread
        if thread_context:
            cat = str(thread_context.get("category", "clinical"))
        elif include_billing and billing_thread_id is None and t == thread_count - 2:
            cat = "billing"
        elif include_rx_renewal and rx_renewal_thread_id is None and t == thread_count - 1:
            cat = "rx_renewal"
        elif categories:
            cat = ctx.rng.choice(categories)
        else:
            cat = "clinical"

        # Pick provider for the thread
        if thread_context:
            resolved_provider = _resolve_context_provider(ctx, thread_context, clinical_providers, pcp_id)
            prov_id = resolved_provider["id"] if resolved_provider else pcp_id
        elif cat == "billing" and billing_providers:
            prov_id = billing_providers[0]["id"]
        elif clinical_providers:
            prov_id = ctx.rng.choice(clinical_providers)["id"]
        else:
            prov_id = pcp_id

        # Pick subject — override with body_context type subject for the first clinical thread
        if cat == "billing":
            subject = ctx.rng.choice(_BILLING_SUBJECTS)
        elif cat == "rx_renewal":
            subject = ctx.rng.choice(_RX_RENEWAL_SUBJECTS)
        elif thread_context:
            subject = thread_context.get(
                "subject",
                _BODY_CONTEXT_SUBJECTS.get(thread_context.get("type", ""), ctx.rng.choice(_CLINICAL_SUBJECTS)),
            )
        else:
            subject = ctx.rng.choice(_CLINICAL_SUBJECTS)

        # For discharge_summary contexts with include_referral_mention, pick a
        # deterministic specialist specialty up-front so (a) the rendered body
        # mentions an exact specialty string and (b) the seeder can export the
        # matching specialist provider ids as a target for downstream tasks.
        if (
            thread_context
            and str(thread_context.get("type", "")) == "discharge_summary"
            and thread_context.get("include_referral_mention")
            and "referral_specialty" not in thread_context
        ):
            ctx_type = str(thread_context.get("type", ""))
            existing_referral_specs = [
                ref.get("to_specialty")
                for ref in ctx.base.get("referrals", [])
                if ref.get("status") in ("approved", "requested") and ref.get("to_specialty")
            ]
            chosen_specialty: str | None = None
            if existing_referral_specs:
                chosen_specialty = str(existing_referral_specs[0])
            else:
                # Reproduce the fallback used by `_generate_contextual_body`:
                # first non-pcp/billing/admin provider.
                fallback_specialist = next(
                    (
                        p for p in providers
                        if p.get("specialty") not in ("pcp", "billing", "admin")
                    ),
                    None,
                )
                if fallback_specialist is not None:
                    chosen_specialty = fallback_specialist.get("specialty")
            if chosen_specialty:
                thread_context["referral_specialty"] = chosen_specialty
                context_specialties[ctx_type] = chosen_specialty
                context_specialist_provider_ids[ctx_type] = [
                    p["id"] for p in providers
                    if p.get("specialty") == chosen_specialty
                ]

        # For discharge_summary contexts, pre-compute which active rx the body
        # will flag as "discontinued during hospitalization". The body
        # generator operates on the first 4 active prescriptions and omits the
        # last one (`meds[omit_idx]`); mirror that logic exactly so the target
        # matches the text the agent reads.
        if (
            thread_context
            and str(thread_context.get("type", "")) == "discharge_summary"
        ):
            ctx_type = str(thread_context.get("type", ""))
            active_rxes = [
                rx for rx in ctx.base.get("prescriptions", [])
                if rx.get("status") == "active"
            ]
            if active_rxes:
                meds_subset = active_rxes[:4]
                discontinued_rx = meds_subset[-1]
                context_discontinued_rx_ids.setdefault(ctx_type, []).append(
                    discontinued_rx["id"]
                )

        # Create 2-4 messages per thread (alternating provider/patient)
        msgs_in_thread = ctx.rng.randint(2, 4)
        for m in range(msgs_in_thread):
            msg_id = ctx.next_id("msg")
            from_type = "provider" if m % 2 == 0 else "patient"
            timestamp = ctx.now - timedelta(
                days=ctx.rng.randint(0, 14),
                hours=ctx.rng.randint(0, 23),
            )

            # Last message in unread threads should be unread (from provider)
            is_last = m == msgs_in_thread - 1
            is_read = True
            if is_last and from_type == "provider" and unread_assigned < unread_count:
                is_read = False
                unread_assigned += 1
            # Force-unread the first provider message of a contextual thread
            # (this is the seed carrier for the task's clinical content — if
            # the task asks the agent to read it, it must actually be unread).
            if thread_context and from_type == "provider" and m == 0 and is_read:
                is_read = False
                unread_assigned += 1

            # Inject contextual body for contextual threads; keep subsequent messages relevant
            if thread_context and from_type == "provider" and m == 0:
                body = _generate_contextual_body(ctx, thread_context)
            elif thread_context and from_type == "patient":
                body = "Thank you, I've reviewed this and will follow up as needed."
            elif thread_context and from_type == "provider" and m > 0:
                body = "Please let me know if you have any questions about the information above or your current medications."
            else:
                body = ctx.fake.paragraph(nb_sentences=ctx.rng.randint(2, 4))

            msg_dict = {
                "id": msg_id,
                "from_type": from_type,
                "provider_id": prov_id,
                "subject": subject,
                "body": body,
                "thread_id": thread_id,
                "timestamp": timestamp.isoformat(),
                "is_read": is_read,
                "category": cat,
            }
            ctx.base["messages"].append(msg_dict)
            all_msg_ids.append(msg_id)
            if not is_read:
                unread_msg_ids.append(msg_id)
                unread_msg_ids_by_category.setdefault(cat, []).append(msg_id)
            # Record context-keyed id for the first provider message of
            # contextual threads (e.g. bp_medication_adjustment → msg_X).
            if thread_context and from_type == "provider" and m == 0:
                ctx_type = str(thread_context.get("type", ""))
                if ctx_type and ctx_type not in context_msg_ids:
                    context_msg_ids[ctx_type] = msg_id

        if cat == "billing":
            billing_thread_id = thread_id
        elif cat == "rx_renewal":
            rx_renewal_thread_id = thread_id

    # --- Dedicated per-category unread threads -------------------------------
    # For every `category -> N` entry in `unread_by_category`, build N threads
    # whose final message is an UNREAD provider message in that exact category.
    # Each thread is a deterministic 3-message conversation
    # (provider -> patient -> provider) so the last message is always from the
    # provider and is the one left unread. This guarantees a known,
    # category-labelled spread of unread messages for tasks that target a
    # computed subset of the inbox rather than every unread message.
    _SUBJECTS_BY_CATEGORY: dict[str, list[str]] = {
        "billing": _BILLING_SUBJECTS,
        "rx_renewal": _RX_RENEWAL_SUBJECTS,
        "clinical": _CLINICAL_SUBJECTS,
    }
    for ded_cat in sorted(unread_by_category.keys()):
        ded_count = int(unread_by_category[ded_cat])
        for _ded_i in range(ded_count):
            thread_id = ctx.next_id("thread")
            thread_ids.append(thread_id)
            if ded_cat == "billing" and billing_providers:
                ded_prov_id = billing_providers[0]["id"]
            elif clinical_providers:
                ded_prov_id = ctx.rng.choice(clinical_providers)["id"]
            else:
                ded_prov_id = pcp_id
            ded_subjects = _SUBJECTS_BY_CATEGORY.get(ded_cat, _CLINICAL_SUBJECTS)
            ded_subject = ctx.rng.choice(ded_subjects)
            for ded_m in range(3):
                msg_id = ctx.next_id("msg")
                from_type = "provider" if ded_m % 2 == 0 else "patient"
                timestamp = ctx.now - timedelta(
                    days=ctx.rng.randint(0, 14),
                    hours=ctx.rng.randint(0, 23),
                )
                is_last = ded_m == 2
                is_read = not is_last  # only the final provider message is unread
                if from_type == "provider":
                    body = ctx.fake.paragraph(nb_sentences=ctx.rng.randint(2, 4))
                else:
                    body = "Thank you, I've reviewed this and will follow up as needed."
                msg_dict = {
                    "id": msg_id,
                    "from_type": from_type,
                    "provider_id": ded_prov_id,
                    "subject": ded_subject,
                    "body": body,
                    "thread_id": thread_id,
                    "timestamp": timestamp.isoformat(),
                    "is_read": is_read,
                    "category": ded_cat,
                }
                ctx.base["messages"].append(msg_dict)
                all_msg_ids.append(msg_id)
                if not is_read:
                    unread_msg_ids.append(msg_id)
                    unread_msg_ids_by_category.setdefault(ded_cat, []).append(msg_id)
            if ded_cat == "billing" and billing_thread_id is None:
                billing_thread_id = thread_id
            elif ded_cat == "rx_renewal" and rx_renewal_thread_id is None:
                rx_renewal_thread_id = thread_id

    return {
        "thread_ids": thread_ids,
        "unread_msg_ids": unread_msg_ids,
        "billing_thread_id": billing_thread_id,
        "rx_renewal_thread_id": rx_renewal_thread_id,
        "all_msg_ids": all_msg_ids,
        # Per-category list of UNREAD message ids (e.g.
        # {"clinical": ["msg_3"], "billing": ["msg_9"]}). Lets a task target a
        # computed subset of the inbox without re-deriving categories inside a
        # predicate.
        "unread_msg_ids_by_category": unread_msg_ids_by_category,
        # Per-body-context-type id of the first provider message for that
        # context (e.g. {"bp_medication_adjustment": "msg_1"}). Empty when
        # no `body_context`/`body_contexts` was supplied.
        "context_msg_ids": context_msg_ids,
        # Per-body-context-type specialty named in the rendered body (currently
        # populated for `discharge_summary` contexts with a referral mention).
        # Empty when no such context exists.
        "context_specialties": context_specialties,
        # Per-body-context-type list of provider ids whose specialty matches
        # the specialty named in the rendered body. Empty when no such
        # context exists.
        "context_specialist_provider_ids": context_specialist_provider_ids,
        # Per-body-context-type list of prescription ids the body flags as
        # "discontinued during hospitalization" (populated for
        # `discharge_summary` contexts).
        "context_discontinued_rx_ids": context_discontinued_rx_ids,
    }


# ---------------------------------------------------------------------------
# 7b. insurance_card_message
# ---------------------------------------------------------------------------

# Deterministic carrier/plan pools for the new-insurance scenario. These are
# distinct from the tier-derived plan names in `patient_profile` so the
# authoritative new plan is unambiguously different from the patient's
# existing (seeded) plan.
_INSURANCE_CARRIERS: list[dict[str, str]] = [
    {"carrier": "Aetna", "tier": "PPO Silver", "prefix": "AET"},
    {"carrier": "Cigna", "tier": "HMO Gold", "prefix": "CIG"},
    {"carrier": "United Healthcare", "tier": "PPO Platinum", "prefix": "UHC"},
    {"carrier": "Humana", "tier": "EPO Bronze", "prefix": "HUM"},
    {"carrier": "Kaiser Permanente", "tier": "HMO Plus", "prefix": "KP"},
]


@_register("insurance_card_message")
def build_insurance_card_message(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Seed a thread of billing messages that carry insurance-card details.

    This builder constructs a genuine VERIFICATION scenario (recompute /
    reconcile / branch on discrepancy), not a single read-extract-write:

    * THREE billing card messages exist, all from the same billing department.
      The authoritative (most recent) card and a *near-recency* decoy share the
      **same carrier** and **near-identical subjects**, so the agent CANNOT
      disambiguate by subject string — it must compute recency from the
      ``timestamp`` fields. A third, older "SUPERSEDED" card from a different
      carrier is an additional decoy.
    * The authoritative message contains an internal CONTRADICTION the agent
      must reconcile: the prose lists one member ID, but a "card-image
      transcription" footer lists a different member ID, and an explicit
      ``Correction:`` line states which value is the corrected/authoritative
      one. Grading targets the CORRECTED member id, not the mis-transcribed
      prose value. This forces a branch on discrepancy — the defining behavior
      of the verification primitive.
    * Contact details are SPLIT across the thread: the new phone is in the
      authoritative card message, but the new email is in a linked follow-up
      message in the SAME thread, so the agent must read the entire thread, not
      just the first card message.

    None of the answer values appear in the task instruction.

    Must run AFTER ``provider_directory`` (needs a billing/PCP provider) and is
    independent of ``message_threads`` (it appends its own messages).

    Params:
        stale_offset_days (int): how many days BEFORE ``ctx.now`` the older
            different-carrier "SUPERSEDED" decoy is timestamped (default 21).
        near_offset_days (int): how many days BEFORE ``ctx.now`` the
            same-carrier near-recency decoy is timestamped (default 3). Must be
            strictly greater than ``current_offset_days``.
        current_offset_days (int): how many days BEFORE ``ctx.now`` the
            authoritative card message is timestamped (default 1).
        followup_offset_hours (int): how many hours AFTER the authoritative
            card message the follow-up (email) message in the same thread is
            timestamped (default 2).
    Outputs: new_plan_name, new_member_id, new_member_id_typo,
             new_group_number, new_phone, new_email, stale_plan_name,
             stale_member_id, stale_group_number, near_plan_name,
             near_member_id, near_group_number, near_phone,
             current_card_msg_id, stale_card_msg_id, near_card_msg_id,
             followup_msg_id, billing_provider_id
    """
    stale_offset_days = int(params.get("stale_offset_days", 21))
    near_offset_days = int(params.get("near_offset_days", 3))
    current_offset_days = int(params.get("current_offset_days", 1))
    followup_offset_hours = int(params.get("followup_offset_hours", 2))

    providers = ctx.base.get("providers", [])
    billing_prov = next(
        (p for p in providers if p.get("specialty") == "billing"), None
    )
    pcp_id = ctx.base.get("patient", {}).get("pcp_id", "prov_1")
    billing_provider_id = billing_prov["id"] if billing_prov else pcp_id

    if "messages" not in ctx.base:
        ctx.base["messages"] = []

    # Pick two DISTINCT carriers deterministically: index 0 = authoritative
    # (also reused by the near-recency decoy), index 1 = stale decoy.
    pool = list(_INSURANCE_CARRIERS)
    ctx.rng.shuffle(pool)
    current = pool[0]
    stale = pool[1]

    def _plan(c: dict[str, str]) -> str:
        return f"{c['carrier']} {c['tier']}"

    def _member(c: dict[str, str]) -> str:
        return f"{c['prefix']}-{ctx.rng.randint(1000000, 9999999)}"

    def _group(c: dict[str, str]) -> str:
        return f"GRP-{ctx.rng.randint(10000, 99999)}"

    new_plan_name = _plan(current)
    new_member_id = _member(current)
    new_group_number = _group(current)
    # Internal contradiction: the prose footer transcribes a typo member id that
    # differs from the corrected value by a single transposed digit. The
    # authoritative answer is ``new_member_id`` (the corrected value); the typo
    # value is a trap that must NOT be applied.
    _digits = new_member_id.split("-", 1)[1]
    if len(_digits) >= 2 and _digits[-1] != _digits[-2]:
        _typo_digits = _digits[:-2] + _digits[-1] + _digits[-2]
    else:
        # Fallback: bump the last digit so the typo is guaranteed distinct.
        _typo_digits = _digits[:-1] + str((int(_digits[-1]) + 1) % 10)
    new_member_id_typo = f"{new_member_id.split('-', 1)[0]}-{_typo_digits}"
    new_phone = f"(555) {ctx.rng.randint(200, 999)}-{ctx.rng.randint(1000, 9999)}"
    # Deterministic new contact email derived from the patient name + new
    # carrier domain so it is clearly distinct from the patient's seeded email.
    domain = "".join(ch for ch in current["carrier"].lower() if ch.isalpha()) + "mail.com"
    patient_name = ctx.base.get("patient", {}).get("name", "member")
    new_email = ctx.email_for_name(patient_name, domain)

    # Near-recency decoy reuses the SAME carrier (so subject + plan name look
    # almost identical) but with a different member id / group number, and is
    # timestamped between the stale and authoritative messages.
    near_plan_name = _plan(current)
    near_member_id = _member(current)
    while near_member_id in (new_member_id, new_member_id_typo):
        near_member_id = _member(current)
    near_group_number = _group(current)
    near_phone = f"(555) {ctx.rng.randint(200, 999)}-{ctx.rng.randint(1000, 9999)}"

    stale_plan_name = _plan(stale)
    stale_member_id = _member(stale)
    stale_group_number = _group(stale)
    stale_phone = f"(555) {ctx.rng.randint(200, 999)}-{ctx.rng.randint(1000, 9999)}"

    current_ts = ctx.now - timedelta(days=current_offset_days)
    near_ts = ctx.now - timedelta(days=near_offset_days)
    stale_ts = ctx.now - timedelta(days=stale_offset_days)
    followup_ts = current_ts + timedelta(hours=followup_offset_hours)

    # 1) Older, different-carrier SUPERSEDED decoy.
    stale_msg_id = ctx.next_id("msg")
    stale_thread_id = ctx.next_id("thread")
    stale_body = (
        "Insurance Card Update (SUPERSEDED):\n"
        f"Plan name: {stale_plan_name}\n"
        f"Member ID: {stale_member_id}\n"
        f"Group number: {stale_group_number}\n"
        f"Benefits hotline: {stale_phone}\n"
        "NOTE: This card was issued in a prior enrollment period and has been "
        "replaced. Please disregard if you have received a newer card update."
    )
    ctx.base["messages"].append({
        "id": stale_msg_id,
        "from_type": "provider",
        "provider_id": billing_provider_id,
        "subject": "Insurance Card Update",
        "body": stale_body,
        "thread_id": stale_thread_id,
        "timestamp": stale_ts.isoformat(),
        "is_read": True,
        "category": "billing",
    })

    # 2) Same-carrier NEAR-RECENCY decoy with a near-identical subject. Only the
    # timestamp distinguishes it from the authoritative card.
    near_msg_id = ctx.next_id("msg")
    near_thread_id = ctx.next_id("thread")
    near_body = (
        "Insurance Card Update — Action Required:\n"
        f"Plan name: {near_plan_name}\n"
        f"Member ID: {near_member_id}\n"
        f"Group number: {near_group_number}\n"
        f"Contact phone: {near_phone}\n"
        "Please review your member details and confirm they are current."
    )
    ctx.base["messages"].append({
        "id": near_msg_id,
        "from_type": "provider",
        "provider_id": billing_provider_id,
        "subject": "Insurance Card Update — Action Required",
        "body": near_body,
        "thread_id": near_thread_id,
        "timestamp": near_ts.isoformat(),
        "is_read": True,
        "category": "billing",
    })

    # 3) Authoritative card message (most recent) — contains the prose/footer
    # member-id CONTRADICTION and the corrected value, plus the new phone. The
    # email is intentionally OMITTED here and delivered in the follow-up.
    current_msg_id = ctx.next_id("msg")
    current_thread_id = ctx.next_id("thread")
    current_body = (
        "New Insurance Card on File:\n"
        f"Plan name: {new_plan_name}\n"
        f"Member ID: {new_member_id_typo}\n"
        f"Group number: {new_group_number}\n"
        f"Contact phone: {new_phone}\n"
        "--- card image transcription (footer) ---\n"
        f"Member ID (as printed on card): {new_member_id}\n"
        f"Correction: the Member ID listed in the body above ({new_member_id_typo}) "
        f"was mis-transcribed. The correct Member ID is {new_member_id}. Please "
        "apply the corrected Member ID.\n"
        "Your new contact email follows in the next message in this thread; "
        "please update both your phone and email on file."
    )
    ctx.base["messages"].append({
        "id": current_msg_id,
        "from_type": "provider",
        "provider_id": billing_provider_id,
        "subject": "New Insurance Card on File",
        "body": current_body,
        "thread_id": current_thread_id,
        "timestamp": current_ts.isoformat(),
        "is_read": False,
        "category": "billing",
    })

    # 4) Follow-up in the SAME thread carrying the new contact EMAIL only.
    followup_msg_id = ctx.next_id("msg")
    followup_body = (
        "Follow-up to your New Insurance Card on File:\n"
        f"As mentioned, your updated contact email on file should be: {new_email}\n"
        "Please make sure both your phone (from the previous message) and this "
        "email are saved to your profile so claims route correctly."
    )
    ctx.base["messages"].append({
        "id": followup_msg_id,
        "from_type": "provider",
        "provider_id": billing_provider_id,
        "subject": "New Insurance Card on File",
        "body": followup_body,
        "thread_id": current_thread_id,
        "timestamp": followup_ts.isoformat(),
        "is_read": False,
        "category": "billing",
    })

    return {
        "new_plan_name": new_plan_name,
        "new_member_id": new_member_id,
        "new_member_id_typo": new_member_id_typo,
        "new_group_number": new_group_number,
        "new_phone": new_phone,
        "new_email": new_email,
        "stale_plan_name": stale_plan_name,
        "stale_member_id": stale_member_id,
        "stale_group_number": stale_group_number,
        "near_plan_name": near_plan_name,
        "near_member_id": near_member_id,
        "near_group_number": near_group_number,
        "near_phone": near_phone,
        "current_card_msg_id": current_msg_id,
        "stale_card_msg_id": stale_msg_id,
        "near_card_msg_id": near_msg_id,
        "followup_msg_id": followup_msg_id,
        "billing_provider_id": billing_provider_id,
    }


# ---------------------------------------------------------------------------
# 8. referral_chain
# ---------------------------------------------------------------------------

@_register("referral_chain")
def build_referral_chain(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create referrals in various states.

    Params: approved_count (int), pending_count (int), denied_count (int),
            with_prior_auth (bool), expiring_soon (bool),
            must_have_specialties (list[str]) — approved referrals guaranteed for these specialties,
            extra_specialty_referrals (list[dict]) — additional decoy referrals appended
              AFTER the guaranteed/approved batch. Each dict accepts keys
              ``specialty`` (str), ``status`` (str: approved|requested|denied),
              ``prior_auth`` (bool, default False), ``prior_auth_status`` (str,
              optional override e.g. "pending"|"approved"|"denied"), and
              ``pin_to_specialty_provider`` (bool, default True — force
              ``to_provider_id`` to a provider that actually matches the
              referral specialty rather than borrowing a candidate appointment's
              provider). These are intentionally placed after the eligible
              approved referral so the create-appointment gate (which picks the
              FIRST approved referral for a specialty) still resolves to the
              eligible one, while the directory shows several same-specialty
              referrals the agent must disambiguate.
            pin_must_have_providers (bool, default False) — when True, every
              ``must_have_specialties`` approved referral pins its
              ``to_provider_id`` to a provider whose specialty matches, instead
              of inheriting an unrelated candidate appointment's provider.
            pending_preauth_count (int) — number of APPROVED referrals whose
              prior_auth is required but still PENDING (a trap: the referral is
              "approved" but the backend gate rejects scheduling because
              pre-auth is not approved). These consume approved slots AFTER the
              guaranteed `must_have_specialties` referral(s), so the
              fully-eligible referral stays distinct from the pending-preauth
              decoys.
    Outputs: approved_ref_ids, pending_ref_ids, denied_ref_ids,
             prior_auth_ref_id, expiring_ref_id,
             eligible_approved_ref_ids (approved referrals that clear the
               scheduling gate: not prior_auth_required OR prior_auth_status ==
               "approved"),
             eligible_ref_id_by_specialty (specialty → first eligible approved
               referral id),
             eligible_provider_id_by_specialty (specialty → that referral's
               to_provider_id),
             ineligible_approved_ref_ids (approved referrals blocked by an
               unapproved prior-auth — decoys the agent must NOT link),
             ineligible_ref_id_by_specialty (specialty → first ineligible
               approved decoy referral id, as a scalar),
             eligible_ref_id, eligible_specialty, preauth_pending_ref_ids

    ``eligible_ref_id`` is the single APPROVED referral whose specialty is the
    first ``must_have_specialties`` entry AND that is schedulable right now
    (``status == 'approved'`` and (not ``prior_auth_required`` or
    ``prior_auth_status == 'approved'``)). It is the canonical answer for
    referral-to-schedule tasks: the agent must select exactly this referral and
    reject the pending-preauth approved decoys. ``preauth_pending_ref_ids`` is
    the list of approved-but-blocked decoys.
    """
    approved_count = params.get("approved_count", 1)
    pending_count = params.get("pending_count", 1)
    denied_count = params.get("denied_count", 0)
    with_prior_auth = params.get("with_prior_auth", False)
    expiring_soon = params.get("expiring_soon", False)
    pending_preauth_count = int(params.get("pending_preauth_count", 0))
    must_have_specialties: list[str] = list(params.get("must_have_specialties", []))
    extra_specialty_referrals: list[dict[str, Any]] = [
        dict(item) for item in (params.get("extra_specialty_referrals") or [])
    ]
    pin_must_have_providers = bool(params.get("pin_must_have_providers", False))
    # When True, the pinned must_have referrals name only ACCEPTING providers
    # (skip closed-panel decoys) and successive same-specialty pinned referrals
    # name DISTINCT providers. Lets a task seed a closed-panel endo decoy
    # (non_accepting_provider_specs) while guaranteeing the approved referral's
    # destination provider is bookable. Implies pin_must_have_providers.
    pin_must_have_accepting_only = bool(params.get("pin_must_have_accepting_only", False))
    if pin_must_have_accepting_only:
        pin_must_have_providers = True

    if "referrals" not in ctx.base:
        ctx.base["referrals"] = []

    providers = ctx.base.get("providers", [])
    providers_by_id = {p["id"]: p for p in providers}
    appointments = ctx.base.get("appointments", [])
    pcp_id = ctx.base.get("patient", {}).get("pcp_id", "prov_1")
    specialist_specs = [p for p in providers if p.get("specialty") not in ("pcp", "billing", "admin")]

    # Specialties available for referrals
    available_specialties = list({p["specialty"] for p in specialist_specs}) or ["cardiology", "dermatology"]

    approved_ref_ids: list[str] = []
    pending_ref_ids: list[str] = []
    denied_ref_ids: list[str] = []
    prior_auth_ref_id: str | None = None
    expiring_ref_id: str | None = None

    # When a referral pins to a specialty provider, callers may want to skip
    # closed-panel (accepting_new=False) providers so the named destination is
    # always bookable, and/or force a SPECIFIC provider id (so two same-specialty
    # approved referrals can deterministically name DIFFERENT providers). These
    # are tracked per-specialty so successive pinned referrals of the same
    # specialty walk down the accepting-provider list instead of all collapsing
    # onto the first one.
    _pinned_accepting_idx_by_spec: dict[str, int] = {}

    def _make_ref(status: str, expires_days: int, prior_auth: bool = False,
                  specialty: str | None = None,
                  pin_to_specialty_provider: bool = False,
                  prior_auth_status_override: str | None = None,
                  pin_accepting_only: bool = False,
                  explicit_to_provider_id: str | None = None,
                  pin_distinct_accepting: bool = False) -> dict[str, Any]:
        ref_id = ctx.next_id("ref")
        candidate_appointments = [
            apt for apt in appointments
            if apt.get("status") in ("scheduled", "completed")
            and not apt.get("linked_referral_id")
            and providers_by_id.get(apt.get("provider_id"), {}).get("specialty") not in ("pcp", "billing", "admin")
        ]
        preferred_appointment = candidate_appointments[0] if candidate_appointments else None
        if specialty is None and preferred_appointment is not None:
            specialty = providers_by_id[preferred_appointment["provider_id"]]["specialty"]
        if specialty is None:
            specialty = ctx.rng.choice(available_specialties)
        if explicit_to_provider_id is not None:
            # Caller forces the exact destination provider (a deterministic decoy
            # that names a DIFFERENT same-specialty provider than the eligible
            # referral). Do not borrow a candidate appointment's provider.
            preferred_appointment = None
            to_prov = providers_by_id.get(explicit_to_provider_id)
        elif pin_to_specialty_provider:
            # Force the referral to point at a provider that actually matches
            # the referral specialty, not an unrelated candidate appointment's
            # provider. Required when a task pins the appointment's provider_id
            # to the referral's to_provider_id and that provider must own the
            # bookable slots. With ``pin_accepting_only`` the search skips
            # closed-panel providers so the named destination is bookable; with
            # ``pin_distinct_accepting`` successive pinned referrals of the same
            # specialty walk down the accepting list so they name DIFFERENT
            # providers (used to seed an approved-referral decoy).
            preferred_appointment = None
            spec_candidates = [
                p for p in specialist_specs
                if p["specialty"] == specialty
                and (p.get("accepting_new") if pin_accepting_only else True)
            ]
            if pin_distinct_accepting and spec_candidates:
                idx = _pinned_accepting_idx_by_spec.get(specialty, 0)
                to_prov = spec_candidates[min(idx, len(spec_candidates) - 1)]
                _pinned_accepting_idx_by_spec[specialty] = idx + 1
            else:
                to_prov = spec_candidates[0] if spec_candidates else None
        else:
            to_prov = (
                providers_by_id.get(preferred_appointment["provider_id"])
                if preferred_appointment is not None
                else next((p for p in specialist_specs if p["specialty"] == specialty), None)
            )
        to_prov_id = to_prov["id"] if to_prov else None
        linked_appointment = preferred_appointment or next(
            (
                apt for apt in appointments
                if apt.get("status") in ("scheduled", "completed")
                and not apt.get("linked_referral_id")
                and (
                    (to_prov_id is not None and apt.get("provider_id") == to_prov_id)
                    or specialty == providers_by_id.get(apt.get("provider_id"), {}).get("specialty")
                )
            ),
            None,
        )
        if linked_appointment is not None:
            linked_appointment["linked_referral_id"] = ref_id
        reason = ctx.rng.choice([
            "Specialist consultation",
            "Further evaluation needed",
            "Follow-up recommended by PCP",
            "Diagnostic imaging required",
        ])
        prior_auth_status = "not_required"
        if prior_auth:
            prior_auth_status = "approved" if status == "approved" else "pending"
        # Explicit override lets a caller seed an APPROVED referral whose
        # pre-auth is still pending (a schedulable-looking but gate-blocked
        # decoy), or otherwise pin the prior-auth status directly. HEAD applies
        # the override whenever it is supplied (covering callers that set it on
        # a referral with prior_auth=False); the pending-preauth decoy path
        # always pairs it with prior_auth=True, so both intents are honored.
        if prior_auth_status_override is not None:
            prior_auth_status = prior_auth_status_override

        return {
            "id": ref_id,
            "from_provider_id": pcp_id,
            "to_specialty": specialty,
            "to_provider_id": to_prov_id,
            "reason": reason,
            "status": status,
            "prior_auth_required": prior_auth,
            "prior_auth_status": prior_auth_status,
            "expires_at": (ctx.now + timedelta(days=expires_days)).isoformat(),
            "notes": "",
            "linked_appointment_id": linked_appointment["id"] if linked_appointment else None,
        }

    # Approved — guarantee must_have_specialties first, then fill remaining randomly
    guaranteed = list(must_have_specialties)  # consume in order
    # The eligible specialty is the first guaranteed specialty (the schedulable
    # target). Pending-preauth decoys must use OTHER specialties so that, for
    # the decoy specialty, the only approved referral is gate-blocked.
    eligible_specialty: str | None = must_have_specialties[0] if must_have_specialties else None
    preauth_pending_ref_ids: list[str] = []
    # Specialties available for pending-preauth decoys: distinct from every
    # guaranteed specialty and from each other.
    decoy_specialty_pool = [
        s for s in available_specialties if s not in set(must_have_specialties)
    ]
    decoy_specialty_idx = 0
    # Decide which approved indices become pending-preauth decoys: the LAST
    # `pending_preauth_count` approved slots (so the guaranteed eligible
    # referral at i==0 is never a decoy).
    n_pending_preauth = max(0, min(pending_preauth_count, max(0, approved_count - 1)))
    pending_preauth_indices = set(
        range(approved_count - n_pending_preauth, approved_count)
    ) if n_pending_preauth else set()

    for i in range(approved_count):
        needs_auth = with_prior_auth and prior_auth_ref_id is None and i == 0
        forced_specialty = guaranteed.pop(0) if guaranteed else None
        is_pending_preauth_decoy = i in pending_preauth_indices and i != 0
        if is_pending_preauth_decoy:
            # Assign a distinct decoy specialty so this approved referral is the
            # sole approved referral for that specialty — and it is gate-blocked
            # because pre-auth is required but still pending.
            if forced_specialty is None and decoy_specialty_idx < len(decoy_specialty_pool):
                forced_specialty = decoy_specialty_pool[decoy_specialty_idx]
                decoy_specialty_idx += 1
            ref = _make_ref(
                "approved", ctx.rng.randint(60, 180), prior_auth=True,
                specialty=forced_specialty, prior_auth_status_override="pending",
            )
            ctx.base["referrals"].append(ref)
            approved_ref_ids.append(ref["id"])
            preauth_pending_ref_ids.append(ref["id"])
            continue
        ref = _make_ref("approved", ctx.rng.randint(60, 180), prior_auth=needs_auth,
                        specialty=forced_specialty,
                        pin_to_specialty_provider=pin_must_have_providers
                        and forced_specialty is not None,
                        pin_accepting_only=pin_must_have_accepting_only
                        and forced_specialty is not None,
                        pin_distinct_accepting=pin_must_have_accepting_only
                        and forced_specialty is not None)
        ctx.base["referrals"].append(ref)
        approved_ref_ids.append(ref["id"])
        if needs_auth:
            prior_auth_ref_id = ref["id"]

    # The eligible referral: the single approved referral for `eligible_specialty`
    # that is schedulable right now (status approved AND (no prior auth required
    # OR prior_auth approved)). Computed from the freshly-seeded referrals so the
    # canonical answer never has to be reconstructed inside a diff predicate.
    eligible_ref_id: str | None = None
    if eligible_specialty is not None:
        eligible_ref_id = next(
            (
                r["id"] for r in ctx.base["referrals"]
                if r["to_specialty"] == eligible_specialty
                and r["status"] == "approved"
                and (
                    not r["prior_auth_required"]
                    or r["prior_auth_status"] == "approved"
                )
            ),
            None,
        )

    # Pending
    for _ in range(pending_count):
        ref = _make_ref("requested", ctx.rng.randint(30, 90))
        ctx.base["referrals"].append(ref)
        pending_ref_ids.append(ref["id"])

    # Denied
    for _ in range(denied_count):
        ref = _make_ref("denied", ctx.rng.randint(30, 90))
        ctx.base["referrals"].append(ref)
        denied_ref_ids.append(ref["id"])

    # Extra decoy referrals — appended AFTER the eligible approved batch so the
    # scheduling gate (which resolves the FIRST approved same-specialty
    # referral) keeps pointing at the eligible one. These deliberately mimic an
    # eligible referral (same specialty, sometimes status="approved") while
    # being blocked by an unapproved prior-auth or a non-approved status, so the
    # agent must disambiguate rather than pattern-match on specialty alone.
    for spec_ref in extra_specialty_referrals:
        e_specialty = spec_ref.get("specialty")
        e_status = str(spec_ref.get("status", "requested"))
        e_prior_auth = bool(spec_ref.get("prior_auth", False))
        e_pa_override = spec_ref.get("prior_auth_status")
        e_pin = bool(spec_ref.get("pin_to_specialty_provider", True))
        # Decoy referrals may name a DIFFERENT accepting same-specialty provider
        # than the eligible referral, so an agent that links the wrong approved
        # referral books the wrong provider. ``accepting_distinct`` walks the
        # shared accepting-provider counter (so this decoy names the NEXT
        # accepting endo after the eligible referral's), and ``to_provider_id``
        # forces an exact destination.
        e_accepting_distinct = bool(spec_ref.get("accepting_distinct", False))
        e_explicit_prov = spec_ref.get("to_provider_id")
        ref = _make_ref(
            e_status,
            ctx.rng.randint(60, 180),
            prior_auth=e_prior_auth,
            specialty=e_specialty,
            pin_to_specialty_provider=e_pin and e_specialty is not None,
            prior_auth_status_override=e_pa_override,
            pin_accepting_only=e_accepting_distinct,
            pin_distinct_accepting=e_accepting_distinct,
            explicit_to_provider_id=e_explicit_prov,
        )
        ctx.base["referrals"].append(ref)
        if e_status == "approved":
            approved_ref_ids.append(ref["id"])
        elif e_status == "requested":
            pending_ref_ids.append(ref["id"])
        elif e_status == "denied":
            denied_ref_ids.append(ref["id"])

    # Expiring soon referral
    if expiring_soon:
        ref = _make_ref("approved", ctx.rng.randint(3, 10))
        ctx.base["referrals"].append(ref)
        approved_ref_ids.append(ref["id"])
        expiring_ref_id = ref["id"]

    # ----------------------------------------------------------------------
    # Eligibility computation. An approved referral clears the
    # create-appointment gate iff it is approved AND (prior-auth not required
    # OR prior-auth already approved). Tasks that pin the appointment's
    # linked_referral_id to an EXACT eligible referral (rather than "any
    # neurology referral") need this precomputed so a canonical_diff predicate
    # never reconstructs the eligibility filter inside a comprehension scope
    # (Class 6/8 hazard).
    # ----------------------------------------------------------------------
    referrals_now = ctx.base["referrals"]
    by_id = {r["id"]: r for r in referrals_now}

    def _is_eligible(r: dict[str, Any]) -> bool:
        return (
            r.get("status") == "approved"
            and (
                not r.get("prior_auth_required")
                or r.get("prior_auth_status") == "approved"
            )
        )

    eligible_approved_ref_ids = [rid for rid in approved_ref_ids if _is_eligible(by_id[rid])]
    ineligible_approved_ref_ids = [
        rid for rid in approved_ref_ids if not _is_eligible(by_id[rid])
    ]
    eligible_ref_id_by_specialty: dict[str, str] = {}
    eligible_provider_id_by_specialty: dict[str, str | None] = {}
    eligible_ref_ids_by_specialty: dict[str, list[str]] = {}
    for rid in eligible_approved_ref_ids:
        r = by_id[rid]
        spec = r.get("to_specialty")
        if spec is None:
            continue
        eligible_ref_ids_by_specialty.setdefault(spec, []).append(rid)
        if spec not in eligible_ref_id_by_specialty:
            eligible_ref_id_by_specialty[spec] = rid
            eligible_provider_id_by_specialty[spec] = r.get("to_provider_id")

    # Mirror of the eligible map for the INELIGIBLE approved decoys (approved
    # referrals blocked by an unapproved prior-auth). Exposes, per specialty,
    # the first such decoy referral id as a SCALAR. Difficulty variants that
    # forge a "wrong-referral" misleading_success body need this scalar (the
    # `{target.X}` placeholder resolver supports only flat keys, not list
    # indexing), so a paired intervention can advertise a fake link pointing at
    # the preauth-pending neurology decoy and force the agent to verify the
    # PERSISTED linked_referral_id rather than trust the response.
    ineligible_ref_id_by_specialty: dict[str, str] = {}
    for rid in ineligible_approved_ref_ids:
        r = by_id[rid]
        spec = r.get("to_specialty")
        if spec is None:
            continue
        if spec not in ineligible_ref_id_by_specialty:
            ineligible_ref_id_by_specialty[spec] = rid

    # Per-specialty discriminators the canonical_diff pins as scalar targets.
    # For each specialty named in must_have_specialties, locate the first
    # approved referral of that specialty, expose its destination provider id
    # (to_provider_id), and pre-compute that provider's single earliest
    # available slot. Tasks like pp_provider_transition use these so the
    # evaluator can require the agent to book with the EXACT provider the
    # referral names (not "any provider of the right specialty") and in that
    # provider's earliest slot — without recomputing a min over a comprehension
    # inside a filter scope (hazard Class 6). Computed here so the values stay
    # deterministic per (task_id, seed).
    def _earliest_slot_iso(prov_id: str | None) -> str | None:
        if not prov_id:
            return None
        prov = providers_by_id.get(prov_id)
        if not prov:
            return None
        slot_times = [s.get("datetime") for s in prov.get("available_slots", []) if s.get("datetime")]
        return min(slot_times) if slot_times else None

    approved_target_provider_by_specialty: dict[str, str | None] = {}
    approved_target_slot_by_specialty: dict[str, str | None] = {}
    for spec in must_have_specialties:
        matching_ref = next(
            (
                r for r in ctx.base["referrals"]
                if r["id"] in approved_ref_ids
                and r.get("status") == "approved"
                and r.get("to_specialty") == spec
            ),
            None,
        )
        target_prov_id = matching_ref.get("to_provider_id") if matching_ref else None
        approved_target_provider_by_specialty[spec] = target_prov_id
        approved_target_slot_by_specialty[spec] = _earliest_slot_iso(target_prov_id)

    # Convenience scalars for the most common single-specialty case
    # (pp_provider_transition's endocrinology transition). When more than one
    # specialty is requested these fall back to the first one in order.
    first_spec = must_have_specialties[0] if must_have_specialties else None
    approved_endo_target_provider_id = (
        approved_target_provider_by_specialty.get("endocrinology")
        if "endocrinology" in approved_target_provider_by_specialty
        else (approved_target_provider_by_specialty.get(first_spec) if first_spec else None)
    )
    approved_endo_target_slot = (
        approved_target_slot_by_specialty.get("endocrinology")
        if "endocrinology" in approved_target_slot_by_specialty
        else (approved_target_slot_by_specialty.get(first_spec) if first_spec else None)
    )

    return {
        "approved_ref_ids": approved_ref_ids,
        "pending_ref_ids": pending_ref_ids,
        "denied_ref_ids": denied_ref_ids,
        "prior_auth_ref_id": prior_auth_ref_id,
        "expiring_ref_id": expiring_ref_id,
        "eligible_approved_ref_ids": eligible_approved_ref_ids,
        "ineligible_approved_ref_ids": ineligible_approved_ref_ids,
        "eligible_ref_id_by_specialty": eligible_ref_id_by_specialty,
        "eligible_provider_id_by_specialty": eligible_provider_id_by_specialty,
        "eligible_ref_ids_by_specialty": eligible_ref_ids_by_specialty,
        "ineligible_ref_id_by_specialty": ineligible_ref_id_by_specialty,
        "eligible_ref_id": eligible_ref_id,
        "eligible_specialty": eligible_specialty,
        "preauth_pending_ref_ids": preauth_pending_ref_ids,
        "approved_target_provider_by_specialty": approved_target_provider_by_specialty,
        "approved_target_slot_by_specialty": approved_target_slot_by_specialty,
        "approved_endo_target_provider_id": approved_endo_target_provider_id,
        "approved_endo_target_slot": approved_endo_target_slot,
    }


# ---------------------------------------------------------------------------
# 9. insurance_claims
# ---------------------------------------------------------------------------

@_register("insurance_claims")
def build_insurance_claims(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create insurance claims in various statuses.

    Params: approved_count (int), denied_count (int), processing_count (int),
            with_eob (bool), near_appeal_deadline (bool),
            approved_no_eob_count (int), approved_zero_resp_count (int)
    Outputs: approved_claim_ids, denied_claim_ids, processing_claim_ids,
             appealable_claim_id, most_recent_denied_claim_id,
             top_3_appealable_claim_ids, payable_approved_claim_ids,
             total_patient_responsibility

    ``approved_no_eob_count`` adds N approved claims whose ``eob_available`` is
    forced False regardless of ``with_eob`` (the EOB cannot be reviewed yet, so
    these are NOT payable in an "review EOB then pay" workflow even though they
    carry a positive balance).

    ``approved_zero_resp_count`` adds N approved claims that are fully covered
    (``amount_covered == amount_billed`` ⇒ ``patient_responsibility == 0``).
    The ``/claims/{id}/pay`` route rejects these (422 — "No patient
    responsibility to pay"), so they must NOT be acted on.

    ``payable_approved_claim_ids`` is the precomputed discriminator a task can
    drive a saturating bijection over: every approved claim that has an
    available EOB AND a strictly-positive ``patient_responsibility``. Computing
    it here keeps the canonical_diff free of filter-scope date/eob math
    (hazard: ``where``/``filter`` scopes see only id + changed fields, or
    ``a`` + ``target``).
    """
    approved_count = params.get("approved_count", 1)
    denied_count = params.get("denied_count", 0)
    processing_count = params.get("processing_count", 0)
    with_eob = params.get("with_eob", False)
    near_appeal_deadline = params.get("near_appeal_deadline", False)
    approved_no_eob_count = params.get("approved_no_eob_count", 0)
    approved_zero_resp_count = params.get("approved_zero_resp_count", 0)
    # When set, the approved-but-no-EOB decoys draw their patient_responsibility
    # from this (lo, hi) dollar band so they OUTRANK several genuinely-payable
    # approved claims by raw balance. This makes the EOB filter load-bearing: a
    # naive "top-K approved by balance" picks these high decoys and fails.
    approved_no_eob_band = params.get("approved_no_eob_band")
    if approved_no_eob_band is not None:
        approved_no_eob_band = (float(approved_no_eob_band[0]), float(approved_no_eob_band[1]))
    # When set (dollars), the K-th and (K+1)-th payable claims (the boundary that
    # decides who makes the top-K cut) are pulled to within this margin of each
    # other so the ranking is genuinely close and careful state-tracking — not a
    # one-glance eyeball — is required to get the boundary right.
    payable_tie_margin = params.get("payable_tie_margin")
    # When set, the fully-covered (zero-responsibility) approved claims are
    # forced to a service_date strictly LATER than every positive-balance
    # approved claim. Combined with `mra_positive_balance_only` below this turns
    # the naive "latest approved claim" answer into a $0.00-balance decoy: the
    # agent must hold "the latest approved claim that actually has a positive
    # balance to review" across reads (state_tracking), not just pick the most
    # recent approved row. Backward-compatible (defaults False).
    approved_zero_resp_later_dated = bool(
        params.get("approved_zero_resp_later_dated", False)
    )
    # When set, `most_recent_approved_claim_id` (and the derived
    # `billing_followup_reason`) are computed over only approved claims with a
    # strictly-positive patient_responsibility, so a later-dated fully-covered
    # decoy is correctly excluded from the answer. Backward-compatible.
    mra_positive_balance_only = bool(params.get("mra_positive_balance_only", False))
    # Force N positive-balance approved claims to SHARE the latest positive
    # service_date so the claim-id tie-break in `most_recent_approved_claim_id`
    # actually fires (rather than being vacuously decided by a unique max date).
    force_latest_positive_tie = int(params.get("force_latest_positive_tie", 0))
    # Optional: denied claims that look like appeal candidates but are NOT
    # eligible (deadline already passed, or no EOB issued). These are decoys
    # that force the agent to apply the full eligibility filter
    # (status==denied AND eob_available AND appeal_deadline >= now) rather
    # than acting on every denied claim. Backward-compatible: defaults to 0.
    expired_denied_count = params.get("expired_denied_count", 0)
    no_eob_denied_count = params.get("no_eob_denied_count", 0)
    # Additional denied claims that LOOK appealable (status == denied) but are
    # NOT eligible, forcing the agent to apply the full eligibility filter
    # (denied AND eob_available AND appeal_deadline >= now) rather than acting
    # on every denied claim. `denied_no_eob_count` denied claims have no EOB;
    # `denied_expired_count` / `denied_past_deadline_count` denied claims have an
    # already-passed appeal deadline (and DO carry an EOB so the deadline is the
    # only disqualifier).
    denied_no_eob_count = params.get("denied_no_eob_count", 0)
    denied_expired_count = params.get("denied_expired_count", 0)
    denied_past_deadline_count = params.get("denied_past_deadline_count", 0)
    # ``eligible_pr_plan`` (optional list of numbers) assigns EXACT
    # patient_responsibility values, in order, to the genuine eligible denied
    # claims produced by ``denied_count`` (status==denied AND eob AND future
    # deadline). This lets an author engineer DELIBERATE TIES at the top-3
    # boundary so the ascending-claim-id tiebreaker actually decides
    # membership — a state_tracking load that a model skipping the tiebreaker
    # gets wrong. Any eligible claim beyond the plan keeps the random draw.
    eligible_pr_plan = list(params.get("eligible_pr_plan", []) or [])
    # ``ineligible_pr_floor`` narrows the random amount_billed (==PR for denied)
    # of the INELIGIBLE denied decoys (no-EOB / expired-deadline) to
    # [ineligible_pr_floor, ineligible_pr_ceiling] so they reliably OUTRANK the
    # genuine eligible top-3 by patient responsibility. A model that ranks
    # top-K-by-PR before (or without) applying the full eligibility filter then
    # picks decoys the appeal route rejects (422). Defaults preserve the legacy
    # [100, 2000] draw.
    ineligible_pr_floor = params.get("ineligible_pr_floor")
    ineligible_pr_ceiling = int(params.get("ineligible_pr_ceiling", 2000))
    _inel_low = int(ineligible_pr_floor) if ineligible_pr_floor is not None else 100
    _inel_high = ineligible_pr_ceiling
    # Optional: when True, the `denied_count` eligible (denied + EOB) claims are
    # given DETERMINISTIC, monotonically-spaced appeal deadlines instead of the
    # default RNG-clustered 30-60d window. This removes the brittle "rank-2 vs
    # rank-3 is a near-coin-flip on clustered RNG dates" failure mode: rank-1 and
    # rank-2 are each unambiguously earlier than rank-3 by a comfortable margin,
    # so the deadline-ranking discriminator is ROBUST rather than fragile. The
    # spacing also installs exactly ONE intentional same-deadline pair among the
    # LATEST two eligible claims (frozen siblings) so the claim-id tiebreaker is
    # tested deliberately, not as an accidental tie on the load-bearing boundary.
    monotonic_appealable_deadlines = bool(
        params.get("monotonic_appealable_deadlines", False)
    )
    # Recency leaders + near-tie cluster. The dispute task's answer is the K most
    # recent ELIGIBLE denied claims. To make the documented claim-id tiebreaker
    # LOAD-BEARING (rather than a degenerate "take the whole cluster"), seed:
    #   * `recent_lead_days`: a list of EXACT day-offsets (before now) for the
    #     strictly-newest eligible claims (one per offset, distinct dates). These
    #     fill the first len(recent_lead_days) recency ranks unambiguously.
    #   * `recent_tie_count`: N fully-eligible claims that all SHARE the
    #     `recent_tie_days_ago` service_date, which sits just BELOW the leaders.
    #     With K = recent_appealable_n and len(recent_lead_days) == K-1, exactly
    #     ONE of the N tied claims earns the final rank (later-numbered id wins)
    #     and the rest are dropped — so resolving the answer REQUIRES the
    #     tiebreaker. All leader/tie offsets are < the ordinary denied pool's
    #     randint(7, 120) window, so they always dominate recency.
    recent_lead_days = params.get("recent_lead_days", []) or []
    recent_tie_count = int(params.get("recent_tie_count", 0))
    recent_tie_days_ago = int(params.get("recent_tie_days_ago", 6))
    # Sort-order trap: N denied + NO-EOB claims whose service_date is NEWER than
    # every eligible claim (incl. the leaders). An agent that sorts by recency
    # BEFORE applying the eligibility filter grabs these into its top-K and
    # mis-fires; a correct filter-then-sort drops them. Defaults to 0.
    newest_no_eob_trap_count = int(params.get("newest_no_eob_trap_count", 0))
    newest_trap_days_ago = int(params.get("newest_trap_days_ago", 2))

    if "claims" not in ctx.base:
        ctx.base["claims"] = []

    providers = ctx.base.get("providers", [])
    providers_by_id = {p["id"]: p for p in providers}
    appointments = ctx.base.get("appointments", [])
    lab_results = ctx.base.get("lab_results", [])
    referrals = ctx.base.get("referrals", [])
    clinical_completed_apts = [
        a for a in appointments
        if a.get("status") == "completed"
        and providers_by_id.get(a.get("provider_id"), {}).get("specialty") not in ("billing", "admin")
    ]
    completed_apts = clinical_completed_apts or [a for a in appointments if a.get("status") == "completed"]
    used_appointment_ids: set[str] = set()
    labs_by_appointment: dict[str, list[str]] = {}
    for lab in lab_results:
        linked_appointment_id = lab.get("linked_appointment_id")
        if linked_appointment_id:
            labs_by_appointment.setdefault(linked_appointment_id, []).append(lab["id"])

    approved_claim_ids: list[str] = []
    denied_claim_ids: list[str] = []
    processing_claim_ids: list[str] = []
    appealable_claim_id: str | None = None
    total_patient_responsibility = Decimal("0")

    # Procedure and diagnosis code pools
    proc_codes = ["99213", "99214", "99215", "93000", "80053", "71046", "36415"]
    diag_codes = ["E11.65", "I10", "J06.9", "M54.5", "Z00.00", "K21.0", "R51"]

    def _find_supporting_referral(apt: dict[str, Any] | None) -> str | None:
        if apt is None:
            return None
        if apt.get("linked_referral_id"):
            return apt["linked_referral_id"]
        apt_provider = apt.get("provider_id")
        apt_specialty = providers_by_id.get(apt_provider, {}).get("specialty")
        for ref in referrals:
            if ref.get("linked_appointment_id") == apt.get("id"):
                return ref["id"]
            if ref.get("to_provider_id") == apt_provider or ref.get("to_specialty") == apt_specialty:
                return ref["id"]
        return None

    def _pick_completed_appointment(prefer_referral: bool) -> dict[str, Any] | None:
        candidate_groups: list[list[dict[str, Any]]] = []
        if prefer_referral:
            candidate_groups.append([
                apt for apt in completed_apts
                if apt["id"] not in used_appointment_ids and _find_supporting_referral(apt) is not None
            ])
        else:
            candidate_groups.append([
                apt for apt in completed_apts
                if apt["id"] not in used_appointment_ids and _find_supporting_referral(apt) is None
            ])
        candidate_groups.append([apt for apt in completed_apts if apt["id"] not in used_appointment_ids])
        if prefer_referral:
            candidate_groups.append([apt for apt in completed_apts if _find_supporting_referral(apt) is not None])
        else:
            candidate_groups.append([apt for apt in completed_apts if _find_supporting_referral(apt) is None])
        candidate_groups.append(completed_apts)
        for group in candidate_groups:
            if group:
                apt = group[0]
                used_appointment_ids.add(apt["id"])
                return apt
        return None

    def _make_claim(status: str, appeal_days: int, eob: bool = False,
                    zero_resp: bool = False,
                    service_date_override: "date | None" = None,
                    service_days_ago: int | None = None,
                    forced_pr: "Decimal | int | float | str | None" = None,
                    pr_low: int = 100, pr_high: int = 2000,
                    pr_band: tuple[float, float] | None = None) -> dict[str, Any]:
        """Build one claim.

        ``pr_band`` (lo, hi) — when set on an approved non-zero-resp claim, the
        patient_responsibility is drawn directly from this dollar band and
        ``amount_covered``/``amount_billed`` are derived so the three stay
        self-consistent (billed = covered + responsibility). This lets a task
        seed high-balance decoys (e.g. no-EOB approved claims that OUTRANK
        several payable claims by raw balance) so the EOB/positive-balance
        filter becomes load-bearing rather than a no-op.
        """
        clm_id = ctx.next_id("clm")
        # ``service_date_override`` pins the date directly; ``service_days_ago``
        # pins it to an EXACT offset from now (used to seed recency near-ties /
        # a newest-of-all sort-order trap and date-ordered approved/zero-resp
        # decoys so the documented tiebreakers become load-bearing). When both
        # are None the legacy wide random window is used.
        if service_date_override is not None:
            service_date = service_date_override
        elif service_days_ago is not None:
            service_date = (ctx.now - timedelta(days=int(service_days_ago))).date()
        else:
            service_date = (ctx.now - timedelta(days=ctx.rng.randint(7, 120))).date()

        # Link to a completed appointment if available
        apt = _pick_completed_appointment(prefer_referral=(status == "denied"))
        apt_id = apt["id"] if apt else ctx.next_id("apt")
        prov_id = apt["provider_id"] if apt else (ctx.rng.choice([p["id"] for p in providers]) if providers else "prov_1")
        supporting_referral_id = _find_supporting_referral(apt)
        supporting_lab_ids = labs_by_appointment.get(apt_id, [])[:2] if apt else []

        # ``forced_pr`` (denied claims only) plants an EXACT patient_responsibility
        # so authors can engineer ties at the top-3 boundary (forcing the
        # claim-id tiebreaker to bind) or push ineligible decoys above the
        # genuine eligible set. ``pr_low``/``pr_high`` narrow the random draw
        # (e.g. to the high end so ineligible decoys reliably outrank the answer).
        # For denied claims patient_responsibility == amount_billed, so we set
        # amount_billed from the forced/ranged value.
        if status == "denied" and forced_pr is not None:
            amount_billed = Decimal(str(forced_pr))
        else:
            amount_billed = Decimal(str(ctx.rng.randint(pr_low, pr_high)))
        if status == "approved":
            if zero_resp:
                # Fully covered — patient owes nothing. The pay route rejects
                # these (422), so they must never be acted on.
                amount_covered = amount_billed
                patient_resp = Decimal("0")
            elif pr_band is not None:
                # Draw the patient responsibility directly from the requested
                # band, then derive billed/covered to stay consistent. Used to
                # plant high-balance decoys above the payable cutoff.
                lo, hi = pr_band
                patient_resp = Decimal(str(round(ctx.rng.uniform(lo, hi), 2)))
                # Keep a plausible coverage ratio (~60-90% covered) by inflating
                # amount_billed so covered = billed - responsibility stays > 0.
                ratio = ctx.rng.uniform(0.6, 0.9)
                amount_billed = (patient_resp / Decimal(str(1 - ratio))).quantize(Decimal("0.01"))
                amount_covered = amount_billed - patient_resp
            else:
                amount_covered = Decimal(str(round(float(amount_billed) * ctx.rng.uniform(0.6, 0.9), 2)))
                patient_resp = amount_billed - amount_covered
        elif status == "denied":
            amount_covered = Decimal("0")
            patient_resp = amount_billed
        else:  # processing
            amount_covered = Decimal("0")
            patient_resp = Decimal("0")

        claim_dict: dict[str, Any] = {
            "id": clm_id,
            "service_date": service_date.isoformat(),
            "provider_id": prov_id,
            "appointment_id": apt_id,
            "procedure_code": ctx.rng.choice(proc_codes),
            "diagnosis_code": ctx.rng.choice(diag_codes),
            "status": status,
            "amount_billed": str(amount_billed),
            "amount_covered": str(amount_covered),
            "patient_responsibility": str(patient_resp),
            "eob_available": eob,
            "appeal_deadline": (ctx.now + timedelta(days=appeal_days)).isoformat(),
            "denial_reason": None,
            "supporting_referral_id": supporting_referral_id,
            "supporting_lab_ids": supporting_lab_ids,
        }
        if status == "denied" and eob:
            claim_dict["denial_reason"] = ctx.rng.choice(_EOB_DENIAL_REASONS)
        if apt is not None:
            evidence_bits: list[str] = []
            if supporting_referral_id:
                evidence_bits.append(f"referral {supporting_referral_id}")
            if supporting_lab_ids:
                evidence_bits.append(f"labs {', '.join(supporting_lab_ids)}")
            if evidence_bits:
                base_notes = apt.get("notes", "").strip()
                evidence_note = "Claim support available via " + " and ".join(evidence_bits) + "."
                if evidence_note not in base_notes:
                    apt["notes"] = f"{base_notes} {evidence_note}".strip()
        return claim_dict

    # Approved claims
    # Positive-balance approved claims. When `force_latest_positive_tie` >= 2,
    # the last N of these are pinned to a single shared "latest positive"
    # service_date so the claim-id tie-break in `most_recent_approved_claim_id`
    # is load-bearing (two approved claims share the latest service date and the
    # winner is decided by id). When `approved_zero_resp_later_dated` is set, all
    # positive approved claims are kept strictly OLDER than the zero-resp decoys
    # below by anchoring them in a 45-90 day window.
    positive_approved_ids: list[str] = []
    if approved_zero_resp_later_dated or force_latest_positive_tie >= 2:
        # Latest positive service_date sits ~40 days back; the zero-resp decoys
        # (when later-dated) land ~10 days back, strictly more recent.
        latest_positive_date = (ctx.now - timedelta(days=40)).date()
        n_tied = max(0, min(force_latest_positive_tie, approved_count))
        for idx in range(approved_count):
            if idx >= approved_count - n_tied:
                # Tie members share the latest positive service_date.
                sd = latest_positive_date
            else:
                # Strictly older than the latest positive date (50-90 days back).
                sd = (ctx.now - timedelta(days=ctx.rng.randint(50, 90))).date()
            claim = _make_claim(
                "approved", ctx.rng.randint(30, 90), eob=with_eob,
                service_date_override=sd,
            )
            ctx.base["claims"].append(claim)
            approved_claim_ids.append(claim["id"])
            positive_approved_ids.append(claim["id"])
            total_patient_responsibility += Decimal(claim["patient_responsibility"])
    else:
        for _ in range(approved_count):
            claim = _make_claim("approved", ctx.rng.randint(30, 90), eob=with_eob)
            ctx.base["claims"].append(claim)
            approved_claim_ids.append(claim["id"])
            positive_approved_ids.append(claim["id"])
            total_patient_responsibility += Decimal(claim["patient_responsibility"])

    # Approved claims whose EOB is NOT yet available. These carry a positive
    # balance but the EOB cannot be reviewed, so an "review EOB then pay"
    # workflow must skip them. They are still legitimate approved claims, so
    # they appear in approved_claim_ids.
    for _ in range(approved_no_eob_count):
        claim = _make_claim("approved", ctx.rng.randint(30, 90), eob=False,
                            pr_band=approved_no_eob_band)
        ctx.base["claims"].append(claim)
        approved_claim_ids.append(claim["id"])
        positive_approved_ids.append(claim["id"])
        total_patient_responsibility += Decimal(claim["patient_responsibility"])

    # Approved claims that are fully covered (patient_responsibility == 0).
    # The pay route rejects these (422), so they must never be paid. When
    # `approved_zero_resp_later_dated` is set they are pinned to a service_date
    # MORE RECENT than every positive approved claim, so the naive "latest
    # approved claim" answer points at a $0.00-balance decoy and the agent must
    # instead track the latest approved claim with an actual positive balance.
    for _ in range(approved_zero_resp_count):
        if approved_zero_resp_later_dated:
            sd_zero = (ctx.now - timedelta(days=ctx.rng.randint(5, 20))).date()
            claim = _make_claim(
                "approved", ctx.rng.randint(30, 90), eob=with_eob, zero_resp=True,
                service_date_override=sd_zero,
            )
        else:
            claim = _make_claim("approved", ctx.rng.randint(30, 90), eob=with_eob, zero_resp=True)
        ctx.base["claims"].append(claim)
        approved_claim_ids.append(claim["id"])
        total_patient_responsibility += Decimal(claim["patient_responsibility"])

    # Denied claims
    for i in range(denied_count):
        is_near = near_appeal_deadline and appealable_claim_id is None and i == 0
        if monotonic_appealable_deadlines:
            # Deterministic, comfortably-spaced deadlines so the rank-1/rank-2
            # vs rank-3 boundary is robust. rank-1 = 4d (the urgent "near"
            # claim), rank-2 = 18d, then +14d per step. The LAST two eligible
            # claims deliberately SHARE a deadline (tie) so the claim-id
            # tiebreaker is exercised on a pair that sits well past the top-2
            # boundary (both are frozen siblings, not the answer).
            if denied_count >= 2 and i >= denied_count - 2:
                # Both of the last two claims get the same (latest) deadline.
                appeal_days = 4 + 14 * (denied_count - 2)
            else:
                appeal_days = 4 + 14 * i
        else:
            appeal_days = ctx.rng.randint(3, 7) if is_near else ctx.rng.randint(30, 60)
        forced_pr = eligible_pr_plan[i] if i < len(eligible_pr_plan) else None
        claim = _make_claim("denied", appeal_days, eob=with_eob, forced_pr=forced_pr)
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        if is_near or (monotonic_appealable_deadlines and i == 0):
            appealable_claim_id = claim["id"]

    # Ineligible denied claims (decoys): denied but NOT appealable.
    # Past-deadline claims use a negative appeal_days so appeal_deadline < now;
    # no-EOB claims carry eob_available=False. Both still count as denied
    # (added to denied_claim_ids) so they exercise the eligibility filter and
    # the invariant that forbids touching out-of-scope denied claims.
    ineligible_denied_ids: list[str] = []
    for _ in range(expired_denied_count):
        claim = _make_claim("denied", -ctx.rng.randint(10, 60), eob=with_eob,
                            pr_low=_inel_low, pr_high=_inel_high)
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        ineligible_denied_ids.append(claim["id"])
    for _ in range(no_eob_denied_count):
        claim = _make_claim("denied", ctx.rng.randint(30, 60), eob=False,
                            pr_low=_inel_low, pr_high=_inel_high)
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        ineligible_denied_ids.append(claim["id"])

    # Denied-but-INELIGIBLE claims: no EOB available. These are denied (so they
    # look appealable by status) but the appeal route rejects them ("EOB is not
    # yet available"). They carry a high patient_responsibility so a top-K-by-PR
    # selection that ignores the eob filter would wrongly pick them up.
    # (Also the non-appealable EOB-gate decoy used by pp_complex_claim_dispute.)
    for _ in range(denied_no_eob_count):
        claim = _make_claim("denied", ctx.rng.randint(30, 60), eob=False,
                            pr_low=_inel_low, pr_high=_inel_high)
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        ineligible_denied_ids.append(claim["id"])

    # Denied-but-INELIGIBLE claims: appeal deadline already passed. They DO
    # carry an EOB, so only the (negative) deadline disqualifies them; the
    # appeal route rejects them ("Appeal deadline has passed").
    for _ in range(denied_expired_count):
        claim = _make_claim("denied", -ctx.rng.randint(5, 40), eob=True,
                            pr_low=_inel_low, pr_high=_inel_high)
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        ineligible_denied_ids.append(claim["id"])

    # Non-appealable decoy: denied + EOB but the appeal deadline has passed
    # (negative appeal_days places the deadline before ctx.now -> fails deadline gate).
    for _ in range(denied_past_deadline_count):
        claim = _make_claim("denied", -ctx.rng.randint(5, 40), eob=with_eob,
                            pr_low=_inel_low, pr_high=_inel_high)
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        ineligible_denied_ids.append(claim["id"])

    # Recency leaders: fully-ELIGIBLE denied claims at distinct, pinned dates
    # newer than the ordinary denied pool. They fill the top recency ranks
    # unambiguously, leaving the tie cluster to decide only the FINAL rank.
    for lead_days in recent_lead_days:
        claim = _make_claim(
            "denied",
            ctx.rng.randint(40, 60),
            eob=True,
            service_days_ago=int(lead_days),
        )
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])

    # Recency near-tie cluster: fully-ELIGIBLE denied claims sharing one
    # service_date that sits just below the leaders. Appended after the leaders
    # so they receive higher claim-id numbers; the later-numbered tied claim wins
    # the final recency rank and the rest are dropped (tiebreaker is decisive).
    tie_cluster_ids: list[str] = []
    for _ in range(recent_tie_count):
        claim = _make_claim(
            "denied",
            ctx.rng.randint(40, 60),
            eob=True,
            service_days_ago=recent_tie_days_ago,
        )
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        tie_cluster_ids.append(claim["id"])

    # Sort-order trap: denied + NO-EOB claims whose service_date is the NEWEST of
    # ALL denied claims (newer than the eligible tie cluster). They are ineligible
    # (no EOB) but a recency-before-filter agent grabs them first.
    for _ in range(newest_no_eob_trap_count):
        claim = _make_claim(
            "denied",
            ctx.rng.randint(40, 60),
            eob=False,
            service_days_ago=newest_trap_days_ago,
        )
        ctx.base["claims"].append(claim)
        denied_claim_ids.append(claim["id"])
        ineligible_denied_ids.append(claim["id"])

    # Processing claims
    for _ in range(processing_count):
        claim = _make_claim("processing", ctx.rng.randint(60, 120))
        ctx.base["claims"].append(claim)
        processing_claim_ids.append(claim["id"])

    # Derived: the most-recent denied claim by service_date (cid tiebreaker).
    # Canonical_diff filters need a scalar target id to narrow "all claims
    # except the target one" without access to `initial` or lambdas inside
    # the `filter:` scope (hazard: invariant filter only sees `a` + `target`).
    def _claim_service_date(cid: str) -> str:
        for c in ctx.base["claims"]:
            if c["id"] == cid:
                return c["service_date"]
        return ""

    most_recent_denied_claim_id: str | None = None
    if denied_claim_ids:
        most_recent_denied_claim_id = max(
            denied_claim_ids,
            key=lambda cid: (_claim_service_date(cid), cid),
        )

    # Derived: the top-3 appealable denied claims by patient responsibility
    # (highest first, claim-id tiebreaker ascending). "Appealable" means
    # status=='denied' AND eob_available AND appeal_deadline >= ctx.now.
    # Canonical_diff needs a scalar list target to drive a bijection update;
    # computing it in the builder keeps the diff simple and avoids pushing
    # date/filter math into the invariant/where scope (hazard: filter sees
    # only a+target, where sees only id+changed fields).
    def _claim_by_id(cid: str) -> dict[str, Any] | None:
        for c in ctx.base["claims"]:
            if c["id"] == cid:
                return c
        return None

    ctx_now_iso = ctx.now.isoformat()
    appealable_ids = [
        cid for cid in denied_claim_ids
        if (c := _claim_by_id(cid)) is not None
        and c.get("eob_available")
        and c.get("appeal_deadline", "") >= ctx_now_iso
    ]
    appealable_ids_sorted = sorted(
        appealable_ids,
        key=lambda cid: (
            -float(_claim_by_id(cid)["patient_responsibility"]),
            cid,
        ),
    )
    top_3_appealable_claim_ids = appealable_ids_sorted[:3]

    # Derived: the most-recent APPROVED claim by service_date (cid tiebreaker
    # ascending, mirroring most_recent_denied_claim_id). Tasks that ask the
    # agent to act on "your most recent approved claim" need a scalar id +
    # the claim's patient_responsibility so the canonical_diff can gate an
    # exact, re-derived value (the agent must locate the claim, read its
    # balance, and format it) without leaking the answer into the prompt.
    most_recent_approved_claim_id: str | None = None
    most_recent_approved_patient_responsibility: str = "0"
    billing_followup_reason: str = ""
    # When `mra_positive_balance_only` is set, restrict the "most recent
    # approved" computation to approved claims with a strictly-positive
    # patient_responsibility. This excludes fully-covered ($0) approved decoys —
    # which may carry a LATER service_date (see approved_zero_resp_later_dated) —
    # so the answer is the latest approved claim that actually has a balance to
    # review, forcing the agent to track balance state, not just recency.
    if mra_positive_balance_only:
        _mra_pool = [
            cid for cid in approved_claim_ids
            if (c := _claim_by_id(cid)) is not None
            and float(c.get("patient_responsibility", "0")) > 0
        ]
    else:
        _mra_pool = list(approved_claim_ids)
    if _mra_pool:
        most_recent_approved_claim_id = max(
            _mra_pool,
            key=lambda cid: (_claim_service_date(cid), cid),
        )
        _mra = _claim_by_id(most_recent_approved_claim_id)
        if _mra is not None:
            most_recent_approved_patient_responsibility = str(
                _mra.get("patient_responsibility", "0")
            )
            # Deterministic, re-derivable appointment-reason string that bakes
            # in the most-recent approved claim's id AND its patient balance.
            # The agent must (1) locate the most-recent approved claim, (2) read
            # its patient_responsibility, and (3) format this exact string —
            # making the claim-review step load-bearing rather than decorative.
            # Exposed as a seed output (not a literal in the instruction) so it
            # never leaks the answer into the prompt.
            billing_followup_reason = (
                f"Incorrect charge review for claim "
                f"{most_recent_approved_claim_id} "
                f"(patient balance ${most_recent_approved_patient_responsibility})"
            )

    # Derived: the top-K APPROVED claims that are payable, ranked by
    # patient_responsibility (highest first, claim-id tiebreaker ascending).
    # "Payable" means status=='approved' AND eob_available AND
    # patient_responsibility > 0. This is the approved-claim analogue of
    # top_3_appealable_claim_ids and exists so a pay-claim task can drive a
    # SATURATING bijection over the K highest-balance approved claims without
    # pushing top-K / tie-break math into the where/filter scope (hazard: the
    # invariant filter sees only `a` + `target`, the where sees only `id`).
    # `payable_top_k` (default 3) controls K; the threshold below is exposed so
    # an instruction can describe the boundary ("balance >= $X") without leaking
    # the target ids.
    payable_top_k = int(params.get("payable_top_k", 3))
    payable_ids = [
        cid for cid in approved_claim_ids
        if (c := _claim_by_id(cid)) is not None
        and c.get("eob_available")
        and float(c.get("patient_responsibility", "0")) > 0
    ]
    payable_ids_sorted = sorted(
        payable_ids,
        key=lambda cid: (
            -float(_claim_by_id(cid)["patient_responsibility"]),
            cid,
        ),
    )

    # Force a near-tie at the top-K boundary: pull the (K+1)-th payable claim's
    # balance up to within `payable_tie_margin` dollars BELOW the K-th, so the
    # 3rd vs 4th decision is razor-thin and the agent must rank carefully rather
    # than eyeballing. The K-th claim stays strictly the larger of the two, so
    # the top-K membership (and id tiebreak) remains deterministic. amounts are
    # kept self-consistent (billed = covered + responsibility).
    if payable_tie_margin is not None and len(payable_ids_sorted) > payable_top_k:
        kth = _claim_by_id(payable_ids_sorted[payable_top_k - 1])
        kp1 = _claim_by_id(payable_ids_sorted[payable_top_k])
        if kth is not None and kp1 is not None:
            kth_pr = Decimal(str(kth["patient_responsibility"]))
            margin = Decimal(str(payable_tie_margin))
            # Place the (K+1)-th strictly below the K-th by `margin` (>= $0.01).
            new_pr = (kth_pr - margin).quantize(Decimal("0.01"))
            if new_pr <= 0:
                new_pr = Decimal("0.01")
            covered = Decimal(str(kp1["amount_covered"]))
            kp1["patient_responsibility"] = str(new_pr)
            kp1["amount_billed"] = str((covered + new_pr).quantize(Decimal("0.01")))
            # Re-sort after the boundary nudge.
            payable_ids_sorted = sorted(
                payable_ids,
                key=lambda cid: (
                    -float(_claim_by_id(cid)["patient_responsibility"]),
                    cid,
                ),
            )

    top_k_payable_claim_ids = payable_ids_sorted[:payable_top_k]
    # The smallest patient_responsibility among the selected top-K (the
    # inclusive cutoff). When fewer than K payable claims exist this is the
    # smallest of all payable; when none exist it is "0". Stored as a string to
    # match the Decimal-as-string convention used elsewhere.
    if top_k_payable_claim_ids:
        payable_cutoff = min(
            float(_claim_by_id(cid)["patient_responsibility"])
            for cid in top_k_payable_claim_ids
        )
    else:
        payable_cutoff = 0.0
    payable_cutoff_amount = str(round(payable_cutoff, 2))

    # Derived: the payable approved claims — approved AND eob_available AND a
    # strictly-positive patient_responsibility. This is the discriminator an
    # "review the EOB, then pay the patient responsibility" task drives a
    # saturating bijection over. Approved-but-no-EOB and fully-covered
    # (zero-responsibility) approved claims are deliberately excluded so the
    # agent must filter, not just "pay every approved claim". Sorted by
    # claim id for deterministic ordering across runs (reuses the same payable
    # membership computed above for top_k_payable_claim_ids).
    payable_approved_claim_ids = sorted(payable_ids)

    # Derived: the N most-RECENT appealable denied claims, ordered by
    # service_date descending (most recent first), claim-id descending as the
    # tiebreaker so the newest id wins on a service-date tie. Distinct from
    # top_3_appealable_claim_ids (which orders by patient responsibility): this
    # is the recency-based set used by the dispute-claim task. Computed in the
    # builder so the canonical_diff bijection can target a scalar list without
    # pushing date/sort math into the where/filter scope.
    recent_appealable_n = params.get("recent_appealable_n", 2)

    def _claim_id_num(cid: str) -> int:
        """Numeric suffix of a ``clm_N`` id for instruction-faithful tiebreak.

        The dispute-claim instruction breaks service_date ties by the
        *later-numbered* claim id. A lexical string sort would mis-order ids
        once they cross the single→double-digit boundary (``clm_9`` >
        ``clm_13`` lexically), so the recency ordering must compare the integer
        suffix, not the raw id string.
        """
        try:
            return int(str(cid).rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            return 0

    recent_appealable_sorted = sorted(
        appealable_ids,
        key=lambda cid: (_claim_by_id(cid)["service_date"], _claim_id_num(cid)),
        reverse=True,
    )
    recent_appealable_claim_ids = recent_appealable_sorted[:recent_appealable_n]

    # Derived: the appealable denied claims sorted by URGENCY — earliest
    # appeal_deadline first, claim-id tiebreaker ascending. Distinct from the
    # patient-responsibility sort above. Canonical_diff needs a scalar list to
    # drive an exact-cardinality bijection (appeal the most-urgent N) without
    # pushing date-parse/sort math into the invariant/where scope (hazard:
    # filter sees only a+target, where sees only id+changed fields).
    appealable_ids_by_deadline = sorted(
        appealable_ids,
        key=lambda cid: (_claim_by_id(cid)["appeal_deadline"], cid),
    )
    top_2_urgent_appealable_claim_ids = appealable_ids_by_deadline[:2]

    # Derived: the exact appeal_deadline ISO strings of the rank-1 and rank-2
    # urgent claims, plus deadlines positioned just INSIDE / just OUTSIDE the
    # rank-2 boundary. These exist so a paired intervention variant can plant
    # boundary-lookalike decoy claims whose deadlines sit within a day or two of
    # the load-bearing rank-2 cutoff (but which are INELIGIBLE by EOB/deadline),
    # forcing the agent to re-verify eligibility rather than grab the
    # earliest-by-deadline row. Exposed as seed targets so the variant resolves
    # `{target.rank2_boundary_deadline}` etc. without leaking the answer ids.
    rank1_appeal_deadline = ""
    rank2_appeal_deadline = ""
    rank2_boundary_deadline = ""
    rank1_tie_deadline = ""
    if len(top_2_urgent_appealable_claim_ids) >= 1:
        rank1_appeal_deadline = _claim_by_id(top_2_urgent_appealable_claim_ids[0])["appeal_deadline"]
        rank1_tie_deadline = rank1_appeal_deadline
    if len(top_2_urgent_appealable_claim_ids) >= 2:
        rank2_appeal_deadline = _claim_by_id(top_2_urgent_appealable_claim_ids[1])["appeal_deadline"]
        # One day BEFORE the rank-2 deadline: a decoy at this date would slot
        # between rank-1 and rank-2 if it were eligible, so an agent that ranks
        # purely by deadline (skipping the EOB/deadline re-check) is tempted to
        # appeal it. The decoy is seeded ineligible in the variant.
        _r2 = datetime.fromisoformat(rank2_appeal_deadline)
        rank2_boundary_deadline = (_r2 - timedelta(days=1)).isoformat()

    # Derived: the FULL set of appealable denied claims (every denied claim that
    # passes all three backend appeal gates: status=='denied' AND eob_available
    # AND appeal_deadline >= ctx.now). Sorted ascending by id for a stable scalar
    # target list that drives the saturating bijection update. This is the
    # genuine answer set when the seed also contains non-appealable denied
    # decoys (no-EOB / past-deadline) that must be EXCLUDED.
    appealable_denied_claim_ids = sorted(appealable_ids)
    appealable_denied_count = len(appealable_denied_claim_ids)

    # Recompute the approved-claim total from the FINAL claim states: the
    # near-tie boundary nudge above may have adjusted one approved claim's
    # patient_responsibility after the running sum was first accumulated.
    total_patient_responsibility = sum(
        (Decimal(str(_claim_by_id(cid)["patient_responsibility"]))
         for cid in approved_claim_ids
         if _claim_by_id(cid) is not None),
        Decimal("0"),
    )

    return {
        "approved_claim_ids": approved_claim_ids,
        "denied_claim_ids": denied_claim_ids,
        "processing_claim_ids": processing_claim_ids,
        "appealable_claim_id": appealable_claim_id,
        "appealable_claim_ids": appealable_ids_sorted,
        "most_recent_denied_claim_id": most_recent_denied_claim_id,
        "most_recent_approved_claim_id": most_recent_approved_claim_id,
        "most_recent_approved_patient_responsibility": (
            most_recent_approved_patient_responsibility
        ),
        "positive_approved_claim_ids": positive_approved_ids,
        "billing_followup_reason": billing_followup_reason,
        "top_3_appealable_claim_ids": top_3_appealable_claim_ids,
        "top_k_payable_claim_ids": top_k_payable_claim_ids,
        "payable_cutoff_amount": payable_cutoff_amount,
        "payable_approved_claim_ids": payable_approved_claim_ids,
        "recent_appealable_claim_ids": recent_appealable_claim_ids,
        "ineligible_denied_ids": ineligible_denied_ids,
        "top_2_urgent_appealable_claim_ids": top_2_urgent_appealable_claim_ids,
        "appealable_claim_ids_by_deadline": appealable_ids_by_deadline,
        "rank1_appeal_deadline": rank1_appeal_deadline,
        "rank2_appeal_deadline": rank2_appeal_deadline,
        "rank2_boundary_deadline": rank2_boundary_deadline,
        "rank1_tie_deadline": rank1_tie_deadline,
        "appealable_denied_claim_ids": appealable_denied_claim_ids,
        "appealable_denied_count": appealable_denied_count,
        "total_patient_responsibility": str(total_patient_responsibility),
    }


# ---------------------------------------------------------------------------
# 10. immunization_record
# ---------------------------------------------------------------------------

@_register("immunization_record")
def build_immunization_record(ctx: PatientPortalSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a mix of completed and due immunizations.

    Params: completed_count (int), due_count (int), series_incomplete (bool)
    Outputs: completed_imm_ids, due_imm_ids, incomplete_series_imm_id, due_vaccine_names
    """
    completed_count = params.get("completed_count", 3)
    due_count = params.get("due_count", 1)
    series_incomplete = params.get("series_incomplete", False)

    if "immunizations" not in ctx.base:
        ctx.base["immunizations"] = []

    providers = ctx.base.get("providers", [])
    # Immunizations are clinically administered by PCPs (not cardiologists /
    # endocrinologists / dermatologists). Restrict admin-provider candidates
    # to PCPs — this matches real healthcare AND avoids the referral-required
    # gate in the patient_portal UI, which blocks booking with specialists
    # unless an approved referral exists.
    pcp_providers = [
        p for p in providers
        if p.get("available_slots") and p.get("specialty") == "pcp"
    ]
    if pcp_providers:
        providers_with_slots = pcp_providers
    else:
        # Fallback: any non-billing/admin provider with slots, then any at all.
        providers_with_slots = [
            p for p in providers
            if p.get("available_slots") and p.get("specialty") not in ("billing", "admin")
        ]
        if not providers_with_slots:
            providers_with_slots = [
                p for p in providers if p.get("specialty") not in ("billing", "admin")
            ]
        if not providers_with_slots:
            providers_with_slots = providers[:1] if providers else [{"id": "prov_1"}]

    vaccine_pool = list(_VACCINES)
    ctx.rng.shuffle(vaccine_pool)
    vax_idx = 0

    completed_imm_ids: list[str] = []
    due_imm_ids: list[str] = []
    incomplete_series_imm_id: str | None = None
    due_vaccine_names: list[str] = []
    # Parallel list of bare vaccine forms (no parenthetical), for predicates
    # that check whether an appointment reason "contains the vaccine".
    # The agent rarely types "Tdap (Tetanus)" verbatim — they'll write
    # "Tdap" or "Tetanus booster", and the predicate must accept either.
    due_vaccine_short_names: list[str] = []
    # When series_incomplete is True, these describe the remaining doses the
    # agent must schedule: one slot per dose (e.g. doses 2 and 3 of a 3-dose
    # series ⇒ two slot labels). series_admin_provider_id is the provider
    # who administered the first dose — the agent is expected to continue
    # with the same administering provider for clinical continuity.
    remaining_dose_slots: list[str] = []
    series_admin_provider_id: str | None = None
    series_vaccine_name: str | None = None
    series_doses_total: int = 0

    # Completed immunizations. Constrain administered_at so that if the
    # vaccine has a recurring cadence (annual / interval_years), its computed
    # next_due_at is strictly in the FUTURE. Otherwise the UI would display
    # completed vaccines as "overdue" alongside the ones in due_imm_ids, and
    # the agent would see more overdue entries than the task targets —
    # making the bijection unsatisfiable in the agent's frame of reference.
    for _ in range(completed_count):
        if vax_idx >= len(vaccine_pool):
            vax_idx = 0
        vax = vaccine_pool[vax_idx]
        vax_idx += 1
        imm_id = ctx.next_id("imm")
        admin_prov = ctx.rng.choice(providers_with_slots)

        # Pick administered_at based on cadence so next_due ends up in the future.
        if vax.get("annual"):
            # Administered 30–335 days ago → next_due 30–335 days in the future.
            administered_at = ctx.now - timedelta(days=ctx.rng.randint(30, 335))
            next_due = administered_at + timedelta(days=365)
        elif vax.get("interval_years"):
            years = vax["interval_years"]
            max_days_ago = max(60, years * 365 - 30)
            administered_at = ctx.now - timedelta(days=ctx.rng.randint(30, max_days_ago))
            next_due = administered_at + timedelta(days=years * 365)
        else:
            # No recurring cadence — series complete, no next_due.
            administered_at = ctx.now - timedelta(days=ctx.rng.randint(30, 730))
            next_due = None

        imm_dict = {
            "id": imm_id,
            "vaccine_name": vax["name"],
            "administered_at": administered_at.isoformat(),
            "next_due_at": next_due.isoformat() if next_due else None,
            "series_complete": True,
            "administering_provider_id": admin_prov["id"],
        }
        ctx.base["immunizations"].append(imm_dict)
        completed_imm_ids.append(imm_id)

    # Due immunizations (next_due_at is in the past).
    # Rotate through the PCP pool so that when multiple PCPs exist, each
    # overdue vaccine is bound to a DIFFERENT administering provider. This
    # preserves the bijection's identity-test property: the agent must
    # actually look up which provider administered which vaccine, not just
    # book any PCP for any vaccine.
    for _idx_due in range(due_count):
        if vax_idx >= len(vaccine_pool):
            vax_idx = 0
        vax = vaccine_pool[vax_idx]
        vax_idx += 1
        imm_id = ctx.next_id("imm")
        # Round-robin: if N PCPs are available, vaccine i uses PCP (i mod N).
        admin_prov = providers_with_slots[_idx_due % len(providers_with_slots)]
        administered_at = ctx.now - timedelta(days=ctx.rng.randint(365, 1095))
        # next_due is in the past (overdue)
        next_due = ctx.now - timedelta(days=ctx.rng.randint(1, 60))

        imm_dict = {
            "id": imm_id,
            "vaccine_name": vax["name"],
            "administered_at": administered_at.isoformat(),
            "next_due_at": next_due.isoformat(),
            "series_complete": True,
            "administering_provider_id": admin_prov["id"],
        }
        ctx.base["immunizations"].append(imm_dict)
        due_imm_ids.append(imm_id)
        due_vaccine_names.append(vax["name"])
        due_vaccine_short_names.append(vax.get("short_name", vax["name"]))

    # Incomplete series
    if series_incomplete:
        # Find a multi-dose vaccine; prefer the one specified by series_vaccine param
        _series_vaccine_name = params.get("series_vaccine", None)
        if _series_vaccine_name:
            series_vax = next((v for v in _VACCINES if v["name"] == _series_vaccine_name and v.get("series")), None)
            if series_vax is None:
                series_vax = next((v for v in _VACCINES if v.get("series") and v.get("doses", 0) >= 2), _VACCINES[3])
        else:
            series_vax = next((v for v in _VACCINES if v.get("series") and v.get("doses", 0) >= 2), _VACCINES[3])
        imm_id = ctx.next_id("imm")
        admin_prov = ctx.rng.choice(providers_with_slots)
        administered_at = ctx.now - timedelta(days=ctx.rng.randint(30, 180))
        interval = series_vax.get("interval_months", 2) * 30
        next_due = administered_at + timedelta(days=interval)

        imm_dict = {
            "id": imm_id,
            "vaccine_name": series_vax["name"],
            "administered_at": administered_at.isoformat(),
            "next_due_at": next_due.isoformat(),
            "series_complete": False,
            "administering_provider_id": admin_prov["id"],
        }
        ctx.base["immunizations"].append(imm_dict)
        incomplete_series_imm_id = imm_id
        if series_vax["name"] not in due_vaccine_names:
            due_vaccine_names.append(series_vax["name"])
            due_vaccine_short_names.append(series_vax.get("short_name", series_vax["name"]))
        # Record series-level metadata for canonical_diff authoring. The
        # patient has received exactly one dose (this record) — so
        # remaining_doses = total_doses - 1. Emit one slot label per
        # remaining dose so a bijection over remaining_dose_slots generates
        # the right number of target slots. Each slot is distinct so the
        # matcher's identity test doesn't degenerate (hazard Class 4).
        series_admin_provider_id = admin_prov["id"]
        series_vaccine_name = series_vax["name"]
        series_doses_total = int(series_vax.get("doses", 3))
        doses_received = 1
        remaining = max(0, series_doses_total - doses_received)
        remaining_dose_slots = [
            f"{series_vax['name']} (dose {doses_received + i + 1} of {series_doses_total})"
            for i in range(remaining)
        ]

    # -- Extension: admin_providers + scheduling window ------------------
    # For each due immunization, look up the provider(s) who administered the
    # most recent completed dose of the same vaccine. Falls back to the due
    # imm's own administering_provider_id if no completed dose matches.
    all_imms = ctx.base["immunizations"]
    completed_imms = [
        imm for imm in all_imms if imm["id"] in completed_imm_ids
    ]
    admin_providers: dict[str, list[str]] = {}
    for due_id in due_imm_ids:
        due_imm = next((imm for imm in all_imms if imm["id"] == due_id), None)
        if due_imm is None:
            continue
        vaccine_name = due_imm["vaccine_name"]
        # Find completed doses with matching vaccine_name (exact match — seed
        # data uses the canonical vaccine_name strings from _VACCINES).
        matching_completed = [
            imm for imm in completed_imms
            if imm["vaccine_name"] == vaccine_name
        ]
        if matching_completed:
            # Most recent completed dose by administered_at
            most_recent = max(
                matching_completed, key=lambda i: i["administered_at"]
            )
            admin_providers[due_id] = [most_recent["administering_provider_id"]]
        else:
            # Fallback: use the due imm's own administering provider
            admin_providers[due_id] = [due_imm["administering_provider_id"]]

    # Use ctx.now (seed-derived anchor time) so windows stay deterministic
    # across runs with the same seed.
    _window_start = ctx.now
    _window_end = _window_start + timedelta(days=30)

    # Series window — needs to fit (doses_total - 1) consecutive slots with
    # at least 1 month (30d) spacing. Add a generous buffer so the agent has
    # some latitude in picking exact dates while still respecting spacing.
    if series_doses_total > 0:
        _series_window_start = ctx.now
        _series_window_end = _series_window_start + timedelta(
            days=30 * max(1, series_doses_total) + 60
        )
    else:
        _series_window_start = ctx.now
        _series_window_end = ctx.now + timedelta(days=180)

    return {
        "completed_imm_ids": completed_imm_ids,
        "due_imm_ids": due_imm_ids,
        "incomplete_series_imm_id": incomplete_series_imm_id,
        "due_vaccine_names": due_vaccine_names,
        "due_vaccine_short_names": due_vaccine_short_names,
        "admin_providers": admin_providers,
        "window_start": _window_start.isoformat(),
        "window_end": _window_end.isoformat(),
        "remaining_dose_slots": remaining_dose_slots,
        "series_admin_provider_id": series_admin_provider_id,
        "series_vaccine_name": series_vaccine_name,
        "series_doses_total": series_doses_total,
        "series_window_start": _series_window_start.isoformat(),
        "series_window_end": _series_window_end.isoformat(),
    }
