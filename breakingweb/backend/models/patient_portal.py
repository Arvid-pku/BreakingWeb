from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .base import BaseEntity, BaseEnvState, utc_now


# --- Nested types (not separate entities) ---

class InsurancePlan(BaseModel):
    plan_name: str
    member_id: str
    group_number: str
    copay: Decimal
    deductible: Decimal
    deductible_met: Decimal = Decimal("0")
    model_config = ConfigDict(extra="forbid")


class EmergencyContact(BaseModel):
    name: str
    phone: str
    relationship: str
    model_config = ConfigDict(extra="forbid")


class ScreeningRecommendation(BaseModel):
    screening_name: str
    recommended_age_start: int
    frequency: str
    last_completed: date | None = None
    next_due: date | None = None
    model_config = ConfigDict(extra="forbid")


class SlotInfo(BaseModel):
    datetime: datetime
    type: str  # "in-person" or "telehealth"
    duration_minutes: int = 30
    model_config = ConfigDict(extra="forbid")


# --- Domain entities (extend BaseEntity) ---

class Patient(BaseEntity):
    name: str
    sex: Literal["male", "female"]
    dob: date
    phone: str
    email: str
    insurance_plan: InsurancePlan
    pcp_id: str
    allergies: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    pharmacy_ids: list[str] = Field(default_factory=list)
    emergency_contact: EmergencyContact
    applicable_screenings: list[ScreeningRecommendation] = Field(default_factory=list)


class Provider(BaseEntity):
    name: str
    specialty: str
    department: str
    npi: str
    accepting_new: bool = True
    available_slots: list[SlotInfo] = Field(default_factory=list)

    # Fields that are side-effects of legitimate agent actions (scheduling
    # an appointment consumes a slot) and must not appear in the canonical-
    # diff collateral-damage sweep. compute_diff reads this tuple and strips
    # the listed fields before comparing provider entities.
    DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]] = ("available_slots",)


class Appointment(BaseEntity):
    provider_id: str
    datetime: datetime
    type: str  # "in-person" or "telehealth"
    status: str = "scheduled"  # scheduled, completed, cancelled, no-show
    reason: str = ""
    notes: str = ""
    linked_referral_id: str | None = None
    pre_auth_status: str = "not_required"
    booked_at: datetime = Field(default_factory=utc_now)
    location: str = ""
    # B-1 expansion: confirmation workflow + cancellation reason.
    # ``requires_confirmation`` is set by the seed builder for high-stakes
    # appointments (e.g. specialist visits, procedures). When True the
    # appointment lands in ``confirmation_state: "pending"`` and the SPA
    # surfaces a Confirm button; the backend exposes
    # POST /appointments/{id}/confirm to transition pending -> confirmed.
    requires_confirmation: bool = False
    confirmation_state: str = "not_required"  # not_required | pending | confirmed
    confirmed_at: datetime | None = None
    # Cancel endpoint accepts an optional reason which is recorded here.
    cancellation_reason: str | None = None


class Prescription(BaseEntity):
    medication: str
    dosage: str
    frequency: str
    provider_id: str
    pharmacy_id: str
    refills_remaining: int
    last_filled: datetime
    expires_at: datetime
    status: str = "active"  # active, expired, discontinued, pending_renewal
    interactions: list[str] = Field(default_factory=list)


class LabResult(BaseEntity):
    test_name: str
    test_code: str
    ordered_by: str  # provider_id
    collected_at: datetime
    value: str
    unit: str
    reference_range: str
    flag: str = "normal"  # normal, abnormal, critical
    status: str = "resulted"  # ordered, collected, pending, resulted, reviewed
    linked_appointment_id: str | None = None


class ClinicalMessage(BaseEntity):
    from_type: str  # "patient" or "provider"
    provider_id: str
    subject: str
    body: str
    thread_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    is_read: bool = False
    category: str = "clinical"  # clinical, billing, scheduling, rx_renewal
    linked_entity_id: str | None = None
    linked_entity_type: str | None = None
    is_urgent: bool = False


class Referral(BaseEntity):
    from_provider_id: str
    to_specialty: str
    to_provider_id: str | None = None
    reason: str
    status: str = "requested"
    prior_auth_required: bool = False
    prior_auth_status: str = "not_required"
    expires_at: datetime
    notes: str = ""
    linked_appointment_id: str | None = None


class InsuranceClaim(BaseEntity):
    service_date: date
    provider_id: str
    appointment_id: str
    procedure_code: str
    diagnosis_code: str
    status: str = "submitted"  # submitted, processing, approved, denied, appealed
    amount_billed: Decimal
    amount_covered: Decimal = Decimal("0")
    patient_responsibility: Decimal = Decimal("0")
    eob_available: bool = False
    appeal_deadline: datetime
    denial_reason: str | None = None
    supporting_referral_id: str | None = None
    supporting_lab_ids: list[str] = Field(default_factory=list)


class Immunization(BaseEntity):
    vaccine_name: str
    administered_at: datetime
    next_due_at: datetime | None = None
    series_complete: bool = True
    administering_provider_id: str


class Pharmacy(BaseEntity):
    name: str
    address: str
    phone: str
    is_default: bool = False
    is_mail_order: bool = False
    dispensing_fee: Decimal = Decimal("0")
    cost_per_90day_supply: Decimal | None = None


class PatientPortalState(BaseEnvState):
    DIFF_DIFFABLE_SINGLETONS: ClassVar[tuple[str, ...]] = ("patient",)

    env_id: str = "patient_portal"

    # Domain entities
    patient: Patient
    providers: list[Provider] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)
    prescriptions: list[Prescription] = Field(default_factory=list)
    lab_results: list[LabResult] = Field(default_factory=list)
    messages: list[ClinicalMessage] = Field(default_factory=list)
    referrals: list[Referral] = Field(default_factory=list)
    claims: list[InsuranceClaim] = Field(default_factory=list)
    immunizations: list[Immunization] = Field(default_factory=list)
    pharmacies: list[Pharmacy] = Field(default_factory=list)

    # B-1 expansion: specialties whose newly-created appointments auto-land
    # in confirmation_state="pending". Empty list (the default) preserves
    # the legacy "schedule = done" semantics. Task seed builders populate
    # this list to opt the session into a two-step schedule + confirm flow.
    auto_confirm_specialties: list[str] = Field(default_factory=list)

    _next_id: int = PrivateAttr(default=1)
    _initial_snapshot: dict[str, Any] | None = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        # Set _next_id past all existing entity IDs
        max_id = 0
        for collection_name in (
            "providers", "appointments", "prescriptions", "lab_results",
            "messages", "referrals", "claims", "immunizations", "pharmacies",
        ):
            for entity in getattr(self, collection_name, []):
                parts = entity.id.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    max_id = max(max_id, int(parts[1]))
        self._next_id = max_id + 1
        # Capture initial snapshot for collateral-damage detection
        if hasattr(self, "state_snapshot"):
            self._initial_snapshot = self.state_snapshot()

    def _gen_id(self, prefix: str) -> str:
        eid = f"{prefix}_{self._next_id}"
        self._next_id += 1
        return eid

    # --- Entity lookups ---
    def get_appointment(self, apt_id: str) -> Appointment | None:
        return next((a for a in self.appointments if a.id == apt_id), None)

    def get_prescription(self, rx_id: str) -> Prescription | None:
        return next((r for r in self.prescriptions if r.id == rx_id), None)

    def get_lab(self, lab_id: str) -> LabResult | None:
        return next((lab for lab in self.lab_results if lab.id == lab_id), None)

    def get_message(self, msg_id: str) -> ClinicalMessage | None:
        return next((m for m in self.messages if m.id == msg_id), None)

    def get_referral(self, ref_id: str) -> Referral | None:
        return next((r for r in self.referrals if r.id == ref_id), None)

    def get_claim(self, clm_id: str) -> InsuranceClaim | None:
        return next((c for c in self.claims if c.id == clm_id), None)

    def get_provider(self, prov_id: str) -> Provider | None:
        return next((p for p in self.providers if p.id == prov_id), None)

    def get_pharmacy(self, pharm_id: str) -> Pharmacy | None:
        return next((p for p in self.pharmacies if p.id == pharm_id), None)

    # --- Filtered queries ---
    def appointments_by_status(self, status: str) -> list[Appointment]:
        return [a for a in self.appointments if a.status == status]

    def upcoming_appointments(self) -> list[Appointment]:
        now = utc_now()
        return [a for a in self.appointments if a.status == "scheduled" and a.datetime > now]

    def prescriptions_by_status(self, status: str) -> list[Prescription]:
        return [r for r in self.prescriptions if r.status == status]

    def active_prescriptions(self) -> list[Prescription]:
        return self.prescriptions_by_status("active")

    def expiring_prescriptions(self, within_days: int = 30) -> list[Prescription]:
        now = utc_now()
        from datetime import timedelta
        cutoff = now + timedelta(days=within_days)
        return [r for r in self.prescriptions if r.status == "active" and r.expires_at <= cutoff]

    def labs_by_flag(self, flag: str) -> list[LabResult]:
        return [lab for lab in self.lab_results if lab.flag == flag]

    def unread_messages(self) -> list[ClinicalMessage]:
        return [m for m in self.messages if not m.is_read]

    def messages_by_category(self, category: str) -> list[ClinicalMessage]:
        return [m for m in self.messages if m.category == category]

    def messages_in_thread(self, thread_id: str) -> list[ClinicalMessage]:
        return sorted(
            [m for m in self.messages if m.thread_id == thread_id],
            key=lambda m: m.timestamp,
        )

    def referrals_by_status(self, status: str) -> list[Referral]:
        return [r for r in self.referrals if r.status == status]

    def claims_by_status(self, status: str) -> list[InsuranceClaim]:
        return [c for c in self.claims if c.status == status]

    def denied_claims(self) -> list[InsuranceClaim]:
        return self.claims_by_status("denied")

    def default_pharmacy(self) -> Pharmacy | None:
        return next((p for p in self.pharmacies if p.is_default), None)

    def provider_by_specialty(self, specialty: str) -> list[Provider]:
        return [p for p in self.providers if p.specialty == specialty]

    # --- Aggregates ---
    def total_patient_responsibility(self) -> Decimal:
        return sum(
            (c.patient_responsibility for c in self.claims if c.status in ("approved", "appealed")),
            Decimal("0"),
        )

    def unread_count(self) -> int:
        return len(self.unread_messages())

    def due_immunizations(self) -> list[Immunization]:
        now = utc_now()
        return [i for i in self.immunizations if i.next_due_at is not None and i.next_due_at <= now]

    def sent_messages(self) -> list[ClinicalMessage]:
        return [m for m in self.messages if m.from_type == "patient"]

    # --- State snapshot for collateral-damage detection ---
    def state_snapshot(self) -> dict[str, Any]:
        return {
            "appointments": {a.id: a.model_dump() for a in self.appointments},
            "prescriptions": {r.id: r.model_dump() for r in self.prescriptions},
            "lab_results": {lab.id: lab.model_dump() for lab in self.lab_results},
            "messages": {m.id: m.model_dump() for m in self.messages},
            "referrals": {r.id: r.model_dump() for r in self.referrals},
            "claims": {c.id: c.model_dump() for c in self.claims},
            "immunizations": {i.id: i.model_dump() for i in self.immunizations},
            "pharmacies": {p.id: p.model_dump() for p in self.pharmacies},
        }
