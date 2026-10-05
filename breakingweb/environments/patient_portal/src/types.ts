/* TypeScript interfaces mirroring Pydantic models from backend/models/patient_portal.py */

export interface InsurancePlan {
  plan_name: string;
  member_id: string;
  group_number: string;
  copay: string;
  deductible: string;
  deductible_met: string;
}

export interface EmergencyContact {
  name: string;
  phone: string;
  relationship: string;
}

export interface ScreeningRecommendation {
  screening_name: string;
  recommended_age_start: number;
  frequency: string;
  last_completed: string | null;
  next_due: string | null;
}

export interface SlotInfo {
  datetime: string;
  type: string;
  duration_minutes: number;
}

export interface Patient {
  id: string;
  name: string;
  sex: "male" | "female";
  dob: string;
  phone: string;
  email: string;
  insurance_plan: InsurancePlan;
  pcp_id: string;
  allergies: string[];
  conditions: string[];
  pharmacy_ids: string[];
  emergency_contact: EmergencyContact;
  applicable_screenings: ScreeningRecommendation[];
  default_pharmacy: Pharmacy | null;
}

export interface Provider {
  id: string;
  name: string;
  specialty: string;
  department: string;
  npi: string;
  accepting_new: boolean;
  available_slots: SlotInfo[];
}

export interface Appointment {
  id: string;
  provider_id: string;
  datetime: string;
  duration_minutes: number;
  type: string;
  status: string;
  reason: string;
  notes: string;
  linked_referral_id: string | null;
  pre_auth_status: string;
  booked_at: string;
  location: string;
  requires_confirmation: boolean;
  confirmation_state: string;
  confirmed_at: string | null;
  cancellation_reason: string | null;
}

export interface Prescription {
  id: string;
  medication: string;
  dosage: string;
  frequency: string;
  provider_id: string;
  pharmacy_id: string;
  refills_remaining: number;
  last_filled: string;
  expires_at: string;
  status: string;
  interactions: string[];
}

export interface LabResult {
  id: string;
  test_name: string;
  test_code: string;
  ordered_by: string;
  collected_at: string;
  value: string;
  unit: string;
  reference_range: string;
  flag: string;
  status: string;
  linked_appointment_id: string | null;
}

export interface ClinicalMessage {
  id: string;
  from_type: string;
  provider_id: string;
  subject: string;
  body: string;
  thread_id: string;
  timestamp: string;
  is_read: boolean;
  category: string;
  linked_entity_id: string | null;
  linked_entity_type: string | null;
  is_urgent: boolean;
}

export interface Referral {
  id: string;
  from_provider_id: string;
  to_specialty: string;
  to_provider_id: string | null;
  reason: string;
  status: string;
  prior_auth_required: boolean;
  prior_auth_status: string;
  expires_at: string;
  notes: string;
  linked_appointment_id: string | null;
}

export interface InsuranceClaim {
  id: string;
  service_date: string;
  provider_id: string;
  appointment_id: string;
  procedure_code: string;
  diagnosis_code: string;
  status: string;
  amount_billed: string;
  amount_covered: string;
  patient_responsibility: string;
  eob_available: boolean;
  appeal_deadline: string;
  denial_reason: string | null;
  supporting_referral_id: string | null;
  supporting_lab_ids: string[];
}

export interface Immunization {
  id: string;
  vaccine_name: string;
  administered_at: string;
  next_due_at: string | null;
  series_complete: boolean;
  administering_provider_id: string;
}

export interface Pharmacy {
  id: string;
  name: string;
  address: string;
  phone: string;
  is_default: boolean;
  is_mail_order: boolean;
  dispensing_fee: string;
  cost_per_90day_supply: string | null;
}
