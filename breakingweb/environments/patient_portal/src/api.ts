import type { ApiRequestOptions } from "@breakingweb/shared";

import type {
  Appointment,
  ClinicalMessage,
  Immunization,
  InsuranceClaim,
  LabResult,
  Patient,
  Pharmacy,
  Prescription,
  Provider,
  Referral,
  SlotInfo,
} from "./types";

type RequestFn = <T>(path: string, options?: ApiRequestOptions) => Promise<T>;

export function createPatientPortalApi(request: RequestFn) {
  return {
    /* Profile */
    getProfile: () =>
      request<Patient>("profile"),

    updateDemographics: (body: { phone?: string; email?: string; emergency_contact?: { name: string; phone: string; relationship: string } }) =>
      request<Patient>("profile/demographics", { method: "POST", body }),

    updateInsurance: (body: { plan_name?: string; member_id?: string; group_number?: string }) =>
      request<Patient>("profile/insurance", { method: "POST", body }),

    /* Pharmacies */
    addPharmacy: (body: { name: string; address: string; phone: string; is_mail_order?: boolean }) =>
      request<Pharmacy>("profile/pharmacy/add", { method: "POST", body }),

    setDefaultPharmacy: (pharmacyId: string) =>
      request<Pharmacy>(`profile/pharmacy/${pharmacyId}/set-default`, { method: "POST" }),

    removePharmacy: (pharmacyId: string) =>
      request<Pharmacy>(`profile/pharmacy/${pharmacyId}/remove`, { method: "POST" }),

    listPharmacies: () =>
      request<{ items: Pharmacy[] }>("pharmacies").then((r) => r.items),

    /* Providers */
    listProviders: () =>
      request<{ items: Provider[] }>("providers").then((r) => r.items),

    searchProviders: (query: { specialty?: string; accepting_new?: boolean; slot_type?: string }) =>
      request<{ items: Provider[] }>("providers/search", { query: query as Record<string, unknown> }).then((r) => r.items),

    /* Appointments */
    listAppointments: (query?: { status?: string }) =>
      request<{ items: Appointment[] }>("appointments", { query: query as Record<string, unknown> }).then((r) => r.items),

    getAppointment: (aptId: string) =>
      request<Appointment>(`appointments/${aptId}`),

    getAvailableSlots: (providerId: string) =>
      request<{ items: SlotInfo[] }>("appointments/available-slots", { query: { provider_id: providerId } }).then((r) => r.items),

    createAppointment: (body: { provider_id: string; slot_datetime: string; type: string; reason?: string; notes?: string; linked_referral_id?: string }) =>
      request<Appointment>("appointments/create", { method: "POST", body }),

    cancelAppointment: (aptId: string, body?: { reason?: string }) =>
      request<Appointment>(`appointments/${aptId}/cancel`, { method: "POST", body: body ?? {} }),

    confirmAppointment: (aptId: string) =>
      request<Appointment>(`appointments/${aptId}/confirm`, { method: "POST" }),

    rescheduleAppointment: (aptId: string, body: { new_slot_datetime: string; new_type?: string }) =>
      request<Appointment>(`appointments/${aptId}/reschedule`, { method: "POST", body }),

    /* Messages */
    listMessages: (query?: { category?: string; unread?: boolean }) =>
      request<{ items: ClinicalMessage[] }>("messages", { query: query as Record<string, unknown> }).then((r) => r.items),

    getThread: (threadId: string) =>
      request<{ items: ClinicalMessage[] }>(`messages/thread/${threadId}`).then((r) => r.items),

    sendMessage: (body: { provider_id: string; subject: string; body: string; category?: string; linked_entity_id?: string; linked_entity_type?: string; is_urgent?: boolean }) =>
      request<ClinicalMessage>("messages/send", { method: "POST", body }),

    replyToMessage: (msgId: string, body: { body: string; is_urgent?: boolean }) =>
      request<ClinicalMessage>(`messages/${msgId}/reply`, { method: "POST", body }),

    markMessageRead: (msgId: string) =>
      request<ClinicalMessage>(`messages/${msgId}/read`, { method: "POST" }),

    markAllMessagesRead: () =>
      request<{ count: number }>("messages/mark-all-read", { method: "POST" }),

    /* Medications */
    listMedications: (query?: { status?: string }) =>
      request<{ items: Prescription[] }>("medications", { query: query as Record<string, unknown> }).then((r) => r.items),

    refillMedication: (rxId: string) =>
      request<Prescription>(`medications/${rxId}/refill`, { method: "POST" }),

    requestRenewal: (rxId: string) =>
      request<Prescription>(`medications/${rxId}/renewal`, { method: "POST" }),

    transferMedication: (rxId: string, pharmacyId: string) =>
      request<Prescription>(`medications/${rxId}/transfer`, { method: "POST", body: { pharmacy_id: pharmacyId } }),

    /* Labs */
    listLabs: (query?: { flag?: string; status?: string }) =>
      request<{ items: LabResult[] }>("labs", { query: query as Record<string, unknown> }).then((r) => r.items),

    getLab: (labId: string) =>
      request<LabResult>(`labs/${labId}`),

    getLabTrend: (testName: string) =>
      request<{ test_name: string; items: LabResult[] }>(`labs/trend/${encodeURIComponent(testName)}`),

    /* Referrals */
    listReferrals: (query?: { status?: string }) =>
      request<{ items: Referral[] }>("referrals", { query: query as Record<string, unknown> }).then((r) => r.items),

    getReferral: (refId: string) =>
      request<Referral>(`referrals/${refId}`),

    requestReferral: (body: { to_specialty: string; reason: string }) =>
      request<Referral>("referrals/request", { method: "POST", body }),

    /* Claims */
    listClaims: (query?: { status?: string }) =>
      request<{ items: InsuranceClaim[] }>("claims", { query: query as Record<string, unknown> }).then((r) => r.items),

    getClaim: (clmId: string) =>
      request<InsuranceClaim>(`claims/${clmId}`),

    submitClaim: (body: { appointment_id: string; procedure_code: string; diagnosis_code: string }) =>
      request<InsuranceClaim>("claims/submit", { method: "POST", body }),

    appealClaim: (clmId: string, body: { reason: string; evidence_references?: string[] }) =>
      request<InsuranceClaim>(`claims/${clmId}/appeal`, { method: "POST", body }),

    payClaim: (clmId: string) =>
      request<InsuranceClaim>(`claims/${clmId}/pay`, { method: "POST" }),

    /* Immunizations */
    listImmunizations: () =>
      request<{ items: Immunization[] }>("immunizations").then((r) => r.items),
  };
}
