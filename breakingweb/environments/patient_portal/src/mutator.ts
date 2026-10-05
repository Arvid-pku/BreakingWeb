import type { RouteMutator } from "@breakingweb/shared";

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
} from "./types";

/* ------------------------------------------------------------------ */
/*  PatientPortalFixture — matches the JSON fixture shape              */
/* ------------------------------------------------------------------ */

export interface PatientPortalFixture {
  env_id: string;
  task_id: string;
  patient: Patient;
  providers: Provider[];
  appointments: Appointment[];
  prescriptions: Prescription[];
  lab_results: LabResult[];
  messages: ClinicalMessage[];
  referrals: Referral[];
  claims: InsuranceClaim[];
  immunizations: Immunization[];
  pharmacies: Pharmacy[];
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

let _idCounter = 0;
function genId(prefix: string): string {
  return `${prefix}_${Date.now()}_${++_idCounter}`;
}

/* ------------------------------------------------------------------ */
/*  Route matching                                                     */
/* ------------------------------------------------------------------ */

type Handler = (
  state: PatientPortalFixture,
  params: Record<string, string>,
  body: Record<string, unknown> | undefined,
  query: Record<string, unknown> | undefined,
) => { state: PatientPortalFixture; response: unknown };

interface Route {
  method: string;
  pattern: RegExp;
  paramNames: string[];
  handler: Handler;
}

const routes: Route[] = [];

function route(method: string, pattern: string, handler: Handler) {
  const paramNames: string[] = [];
  const regexStr = pattern.replace(/:(\w+)/g, (_, name) => {
    paramNames.push(name);
    return "([^/]+)";
  });
  routes.push({
    method: method.toUpperCase(),
    pattern: new RegExp(`^${regexStr}$`),
    paramNames,
    handler,
  });
}

function matchRoute(
  method: string,
  path: string,
): { handler: Handler; params: Record<string, string> } | null {
  const upper = method.toUpperCase();
  for (const r of routes) {
    if (r.method !== upper) continue;
    const m = path.match(r.pattern);
    if (m) {
      const params: Record<string, string> = {};
      r.paramNames.forEach((name, i) => { params[name] = m[i + 1]; });
      return { handler: r.handler, params };
    }
  }
  return null;
}

/* ------------------------------------------------------------------ */
/*  Profile                                                            */
/* ------------------------------------------------------------------ */

route("GET", "profile", (state) => ({
  state,
  response: {
    ...state.patient,
    default_pharmacy: state.pharmacies.find((p) => p.is_default) ?? null,
  },
}));

route("POST", "profile/demographics", (state, _params, body) => {
  if (body?.phone) state.patient.phone = String(body.phone);
  if (body?.email) state.patient.email = String(body.email);
  if (body?.emergency_contact) {
    state.patient.emergency_contact = body.emergency_contact as Patient["emergency_contact"];
  }
  return { state, response: state.patient };
});

route("POST", "profile/insurance", (state, _params, body) => {
  if (body?.plan_name) state.patient.insurance_plan.plan_name = String(body.plan_name);
  if (body?.member_id) state.patient.insurance_plan.member_id = String(body.member_id);
  if (body?.group_number) state.patient.insurance_plan.group_number = String(body.group_number);
  return { state, response: state.patient };
});

/* ------------------------------------------------------------------ */
/*  Pharmacies                                                         */
/* ------------------------------------------------------------------ */

route("POST", "profile/pharmacy/add", (state, _params, body) => {
  const pharm: Pharmacy = {
    id: genId("pharm"),
    name: String(body?.name ?? ""),
    address: String(body?.address ?? ""),
    phone: String(body?.phone ?? ""),
    is_default: false,
    is_mail_order: Boolean(body?.is_mail_order),
    dispensing_fee: "0",
    cost_per_90day_supply: null,
  };
  state.pharmacies.push(pharm);
  state.patient.pharmacy_ids.push(pharm.id);
  return { state, response: pharm };
});

route("POST", "profile/pharmacy/:pharm_id/set-default", (state, params) => {
  for (const p of state.pharmacies) {
    p.is_default = p.id === params.pharm_id;
  }
  const target = state.pharmacies.find((p) => p.id === params.pharm_id);
  if (!target) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: target };
});

route("POST", "profile/pharmacy/:pharm_id/remove", (state, params) => {
  const idx = state.pharmacies.findIndex((p) => p.id === params.pharm_id);
  if (idx === -1) return { state, response: { error: "Not found", status: 404 } };
  const target = state.pharmacies[idx];
  if (target.is_default) return { state, response: { error: "Cannot remove default pharmacy", status: 422 } };
  state.pharmacies.splice(idx, 1);
  state.patient.pharmacy_ids = state.patient.pharmacy_ids.filter((id) => id !== params.pharm_id);
  return { state, response: target };
});

route("GET", "pharmacies", (state) => ({
  state,
  response: { items: state.pharmacies },
}));

/* ------------------------------------------------------------------ */
/*  Providers                                                          */
/* ------------------------------------------------------------------ */

route("GET", "providers", (state) => ({
  state,
  response: { items: state.providers },
}));

route("GET", "providers/search", (state, _params, _body, query) => {
  let items = [...state.providers];
  if (query?.specialty) items = items.filter((p) => p.specialty === String(query.specialty));
  if (query?.accepting_new !== undefined) items = items.filter((p) => p.accepting_new === (query.accepting_new === "true" || query.accepting_new === true));
  if (query?.slot_type) items = items.filter((p) => p.available_slots.some((s) => s.type === String(query.slot_type)));
  return { state, response: { items } };
});

/* ------------------------------------------------------------------ */
/*  Appointments                                                       */
/* ------------------------------------------------------------------ */

route("GET", "appointments", (state, _params, _body, query) => {
  let items = [...state.appointments];
  if (query?.status) items = items.filter((a) => a.status === String(query.status));
  return { state, response: { items } };
});

route("GET", "appointments/available-slots", (state, _params, _body, query) => {
  const providerId = String(query?.provider_id ?? "");
  const provider = state.providers.find((p) => p.id === providerId);
  if (!provider) return { state, response: { error: "Provider not found", status: 404 } };
  return { state, response: { items: provider.available_slots } };
});

route("GET", "appointments/:apt_id", (state, params) => {
  const apt = state.appointments.find((a) => a.id === params.apt_id);
  if (!apt) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: apt };
});

route("POST", "appointments/create", (state, _params, body) => {
  const providerId = String(body?.provider_id ?? "");
  const provider = state.providers.find((p) => p.id === providerId);
  if (!provider) return { state, response: { error: "Provider not found", status: 404 } };

  const slotDt = String(body?.slot_datetime ?? "");
  const slotIdx = provider.available_slots.findIndex((s) => s.datetime === slotDt);
  if (slotIdx === -1) return { state, response: { error: `No slot at ${slotDt}`, status: 422 } };

  const slot = provider.available_slots[slotIdx];
  provider.available_slots.splice(slotIdx, 1);

  const apt: Appointment = {
    id: genId("apt"),
    provider_id: providerId,
    datetime: slot.datetime,
    duration_minutes: slot.duration_minutes ?? 30,
    type: String(body?.type ?? slot.type),
    status: "scheduled",
    reason: String(body?.reason ?? ""),
    notes: "",
    linked_referral_id: body?.linked_referral_id ? String(body.linked_referral_id) : null,
    pre_auth_status: "not_required",
    booked_at: new Date().toISOString(),
    location: (body?.type ?? slot.type) === "in-person" ? "Main Campus" : "Telehealth",
  };
  state.appointments.push(apt);
  if (apt.linked_referral_id) {
    const linkedReferral = state.referrals.find((ref) => ref.id === apt.linked_referral_id);
    if (linkedReferral) {
      linkedReferral.linked_appointment_id = apt.id;
      apt.pre_auth_status = linkedReferral.prior_auth_status;
    }
  }
  return { state, response: apt };
});

route("POST", "appointments/:apt_id/cancel", (state, params) => {
  const apt = state.appointments.find((a) => a.id === params.apt_id);
  if (!apt) return { state, response: { error: "Not found", status: 404 } };
  if (apt.status !== "scheduled") return { state, response: { error: `Cannot cancel: ${apt.status}`, status: 422 } };
  apt.status = "cancelled";
  return { state, response: apt };
});

route("POST", "appointments/:apt_id/reschedule", (state, params, body) => {
  const apt = state.appointments.find((a) => a.id === params.apt_id);
  if (!apt) return { state, response: { error: "Not found", status: 404 } };
  if (apt.status !== "scheduled") return { state, response: { error: `Cannot reschedule: ${apt.status}`, status: 422 } };

  const provider = state.providers.find((p) => p.id === apt.provider_id);
  if (!provider) return { state, response: { error: "Provider not found", status: 404 } };

  const newDt = String(body?.new_slot_datetime ?? "");
  const slotIdx = provider.available_slots.findIndex((s) => s.datetime === newDt);
  if (slotIdx === -1) return { state, response: { error: `No slot at ${newDt}`, status: 422 } };

  provider.available_slots.splice(slotIdx, 1);
  apt.datetime = newDt;
  if (body?.new_type) apt.type = String(body.new_type);
  apt.location = apt.type === "in-person" ? "Main Campus" : "Telehealth";
  return { state, response: apt };
});

/* ------------------------------------------------------------------ */
/*  Messages                                                           */
/* ------------------------------------------------------------------ */

route("GET", "messages", (state, _params, _body, query) => {
  let items = [...state.messages];
  if (query?.category) items = items.filter((m) => m.category === String(query.category));
  if (query?.unread !== undefined) {
    const isUnread = query.unread === "true" || query.unread === true;
    items = items.filter((m) => m.is_read === !isUnread);
  }
  return { state, response: { items } };
});

route("GET", "messages/thread/:thread_id", (state, params) => {
  const items = state.messages
    .filter((m) => m.thread_id === params.thread_id)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  return { state, response: { items } };
});

route("POST", "messages/send", (state, _params, body) => {
  const msgId = genId("msg");
  const msg: ClinicalMessage = {
    id: msgId,
    from_type: "patient",
    provider_id: String(body?.provider_id ?? ""),
    subject: String(body?.subject ?? ""),
    body: String(body?.body ?? ""),
    thread_id: `thread_${msgId}`,
    timestamp: new Date().toISOString(),
    is_read: true,
    category: String(body?.category ?? "clinical"),
    linked_entity_id: body?.linked_entity_id ? String(body.linked_entity_id) : null,
    linked_entity_type: body?.linked_entity_type ? String(body.linked_entity_type) : null,
    is_urgent: Boolean(body?.is_urgent),
  };
  state.messages.push(msg);
  return { state, response: msg };
});

route("POST", "messages/:msg_id/reply", (state, params, body) => {
  const original = state.messages.find((m) => m.id === params.msg_id);
  if (!original) return { state, response: { error: "Not found", status: 404 } };
  const replyId = genId("msg");
  const reply: ClinicalMessage = {
    id: replyId,
    from_type: "patient",
    provider_id: original.provider_id,
    subject: `Re: ${original.subject}`,
    body: String(body?.body ?? ""),
    thread_id: original.thread_id,
    timestamp: new Date().toISOString(),
    is_read: true,
    category: original.category,
    linked_entity_id: null,
    linked_entity_type: null,
    is_urgent: Boolean(body?.is_urgent),
  };
  state.messages.push(reply);
  return { state, response: reply };
});

route("POST", "messages/:msg_id/read", (state, params) => {
  const msg = state.messages.find((m) => m.id === params.msg_id);
  if (!msg) return { state, response: { error: "Not found", status: 404 } };
  msg.is_read = true;
  return { state, response: msg };
});

route("POST", "messages/mark-all-read", (state) => {
  let count = 0;
  for (const m of state.messages) {
    if (!m.is_read) { m.is_read = true; count++; }
  }
  return { state, response: { count } };
});

/* ------------------------------------------------------------------ */
/*  Medications                                                        */
/* ------------------------------------------------------------------ */

route("GET", "medications", (state, _params, _body, query) => {
  let items = [...state.prescriptions];
  if (query?.status) items = items.filter((r) => r.status === String(query.status));
  return { state, response: { items } };
});

route("POST", "medications/:rx_id/refill", (state, params) => {
  const rx = state.prescriptions.find((r) => r.id === params.rx_id);
  if (!rx) return { state, response: { error: "Not found", status: 404 } };
  if (rx.status !== "active") return { state, response: { error: "Not active", status: 422 } };
  if (rx.refills_remaining <= 0) return { state, response: { error: "No refills remaining", status: 422 } };
  rx.refills_remaining -= 1;
  rx.last_filled = new Date().toISOString();
  return { state, response: rx };
});

route("POST", "medications/:rx_id/renewal", (state, params) => {
  const rx = state.prescriptions.find((r) => r.id === params.rx_id);
  if (!rx) return { state, response: { error: "Not found", status: 404 } };
  rx.status = "pending_renewal";
  const renewalMessage: ClinicalMessage = {
    id: genId("msg"),
    from_type: "patient",
    provider_id: rx.provider_id,
    subject: `Renewal request for ${rx.medication}`,
    body: `Please renew ${rx.medication} ${rx.dosage}. Prescription ID: ${rx.id}.`,
    thread_id: genId("thread"),
    timestamp: new Date().toISOString(),
    is_read: true,
    category: "rx_renewal",
    linked_entity_id: rx.id,
    linked_entity_type: "prescription",
    is_urgent: false,
  };
  state.messages.push(renewalMessage);
  return { state, response: rx };
});

route("POST", "medications/:rx_id/transfer", (state, params, body) => {
  const rx = state.prescriptions.find((r) => r.id === params.rx_id);
  if (!rx) return { state, response: { error: "Not found", status: 404 } };
  rx.pharmacy_id = String(body?.pharmacy_id ?? "");
  return { state, response: rx };
});

/* ------------------------------------------------------------------ */
/*  Labs                                                               */
/* ------------------------------------------------------------------ */

route("GET", "labs", (state, _params, _body, query) => {
  let items = [...state.lab_results];
  if (query?.flag) items = items.filter((l) => l.flag === String(query.flag));
  if (query?.status) items = items.filter((l) => l.status === String(query.status));
  return { state, response: { items } };
});

route("GET", "labs/:lab_id", (state, params) => {
  const lab = state.lab_results.find((l) => l.id === params.lab_id);
  if (!lab) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: lab };
});

route("GET", "labs/trend/:test_name", (state, params) => {
  const testName = decodeURIComponent(params.test_name);
  const items = state.lab_results
    .filter((l) => l.test_name === testName)
    .sort((a, b) => new Date(a.collected_at).getTime() - new Date(b.collected_at).getTime());
  return { state, response: { test_name: testName, items } };
});

/* ------------------------------------------------------------------ */
/*  Referrals                                                          */
/* ------------------------------------------------------------------ */

route("GET", "referrals", (state, _params, _body, query) => {
  let items = [...state.referrals];
  if (query?.status) items = items.filter((r) => r.status === String(query.status));
  return { state, response: { items } };
});

route("GET", "referrals/:ref_id", (state, params) => {
  const ref = state.referrals.find((r) => r.id === params.ref_id);
  if (!ref) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: ref };
});

route("POST", "referrals/request", (state, _params, body) => {
  const ref: Referral = {
    id: genId("ref"),
    from_provider_id: state.patient.pcp_id,
    to_specialty: String(body?.to_specialty ?? ""),
    to_provider_id: null,
    reason: String(body?.reason ?? ""),
    status: "requested",
    prior_auth_required: false,
    prior_auth_status: "not_required",
    expires_at: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(),
    notes: "",
    linked_appointment_id: null,
  };
  state.referrals.push(ref);
  return { state, response: ref };
});

/* ------------------------------------------------------------------ */
/*  Claims                                                             */
/* ------------------------------------------------------------------ */

route("GET", "claims", (state, _params, _body, query) => {
  let items = [...state.claims];
  if (query?.status) items = items.filter((c) => c.status === String(query.status));
  return { state, response: { items } };
});

route("GET", "claims/:clm_id", (state, params) => {
  const claim = state.claims.find((c) => c.id === params.clm_id);
  if (!claim) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: claim };
});

route("POST", "claims/submit", (state, _params, body) => {
  const appointmentId = String(body?.appointment_id ?? "");
  const apt = state.appointments.find((a) => a.id === appointmentId);
  if (!apt) return { state, response: { error: "Appointment not found", status: 404 } };
  if (apt.status !== "completed") return { state, response: { error: `Appointment is ${apt.status}, must be completed`, status: 422 } };

  const clmId = genId("clm");
  const amountBilled = String(Math.floor(Math.random() * 2350 + 150));
  const claim: InsuranceClaim = {
    id: clmId,
    service_date: apt.datetime,
    provider_id: apt.provider_id,
    appointment_id: appointmentId,
    procedure_code: String(body?.procedure_code ?? ""),
    diagnosis_code: String(body?.diagnosis_code ?? ""),
    status: "submitted",
    amount_billed: amountBilled,
    amount_covered: "0",
    patient_responsibility: "0",
    eob_available: false,
    appeal_deadline: new Date(Date.now() + 180 * 24 * 60 * 60 * 1000).toISOString(),
    denial_reason: null,
    supporting_referral_id: apt.linked_referral_id ?? null,
    supporting_lab_ids: [],
  };
  state.claims.push(claim);
  return { state, response: claim };
});

route("POST", "claims/:clm_id/appeal", (state, params, body) => {
  const claim = state.claims.find((c) => c.id === params.clm_id);
  if (!claim) return { state, response: { error: "Not found", status: 404 } };
  if (claim.status !== "denied") return { state, response: { error: "Only denied claims can be appealed", status: 422 } };
  claim.status = "appealed";
  return { state, response: claim };
});

route("POST", "claims/:clm_id/pay", (state, params) => {
  const claim = state.claims.find((c) => c.id === params.clm_id);
  if (!claim) return { state, response: { error: "Not found", status: 404 } };
  if (parseFloat(claim.patient_responsibility) <= 0) return { state, response: { error: "No responsibility to pay", status: 422 } };
  claim.patient_responsibility = "0";
  return { state, response: claim };
});

/* ------------------------------------------------------------------ */
/*  Immunizations                                                      */
/* ------------------------------------------------------------------ */

route("GET", "immunizations", (state) => ({
  state,
  response: { items: state.immunizations },
}));

/* ------------------------------------------------------------------ */
/*  Exported mutator                                                   */
/* ------------------------------------------------------------------ */

export const patientPortalMutator: RouteMutator<PatientPortalFixture> = (
  state,
  method,
  path,
  body,
  query,
) => {
  const cleanPath = path.replace(/^\//, "");
  const match = matchRoute(method, cleanPath);
  if (!match) {
    return { state, response: { error: `No route: ${method} /${cleanPath}`, status: 404 } };
  }
  return match.handler(
    state,
    match.params,
    body as Record<string, unknown> | undefined,
    query,
  );
};
