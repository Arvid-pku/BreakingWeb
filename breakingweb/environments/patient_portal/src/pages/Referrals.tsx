import { useCallback, useEffect, useState } from "react";

import { usePatientPortal } from "../context";
import type { Referral } from "../types";

const SPECIALTY_OPTIONS = [
  "cardiology",
  "dermatology",
  "endocrinology",
  "neurology",
  "orthopedics",
  "radiology",
];

export function ReferralsPage() {
  const { api, providers, notify } = usePatientPortal();
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [showRequest, setShowRequest] = useState(false);
  const [toSpecialty, setToSpecialty] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const providerName = (id: string | null) => {
    if (!id) return "Unassigned";
    return providers.find((p) => p.id === id)?.name ?? id;
  };

  const loadReferrals = useCallback(async () => {
    try {
      const items = await api.listReferrals();
      setReferrals(items.sort((a, b) => new Date(b.expires_at).getTime() - new Date(a.expires_at).getTime()));
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => { void loadReferrals(); }, [loadReferrals]);

  const handleRequest = async () => {
    if (!toSpecialty || !reason.trim() || submitting) return;
    setSubmitting(true);
    try {
      await api.requestReferral({ to_specialty: toSpecialty, reason: reason.trim() });
      notify("Referral request submitted");
      setToSpecialty("");
      setReason("");
      setShowRequest(false);
      void loadReferrals();
    } catch {
      notify("Failed to submit referral request");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div aria-label="Referrals Page">
      <h2>Referrals</h2>

      <section aria-label="Active Referrals" className="pp-section">
        <h3>Referral List</h3>
        {referrals.length === 0 ? (
          <p>No referrals on file.</p>
        ) : (
          <table aria-label="Referral table">
            <thead>
              <tr>
                <th>Referral ID</th>
                <th>Specialty</th>
                <th>Provider</th>
                <th>Status</th>
                <th>Prior Auth</th>
                <th>Linked Appointment</th>
                <th>Expires</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {referrals.map((referral) => (
                <tr key={referral.id}>
                  <td>{referral.id}</td>
                  <td>{referral.to_specialty}</td>
                  <td>{providerName(referral.to_provider_id)}</td>
                  <td><span className={`pp-status-badge pp-status-badge--${referral.status}`}>{referral.status}</span></td>
                  <td>{referral.prior_auth_required ? referral.prior_auth_status : "Not required"}</td>
                  <td>{referral.linked_appointment_id ?? "None"}</td>
                  <td>{new Date(referral.expires_at).toLocaleDateString()}</td>
                  <td>{referral.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-label="Request New Referral" className="pp-section">
        <button
          className="pp-btn pp-btn--primary"
          aria-label={showRequest ? "Hide request form" : "Request New Referral"}
          onClick={() => setShowRequest(!showRequest)}
        >
          {showRequest ? "Cancel" : "Request New Referral"}
        </button>
        {showRequest && (
          <div className="pp-form-section" aria-label="New referral request form">
            <div className="pp-form-field">
              <label htmlFor="ref-specialty">Specialty</label>
              <select
                id="ref-specialty"
                value={toSpecialty}
                onChange={(e) => setToSpecialty(e.target.value)}
                aria-label="Select referral specialty"
              >
                <option value="">Select a specialty...</option>
                {SPECIALTY_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            <div className="pp-form-field">
              <label htmlFor="ref-reason">Reason for referral</label>
              <input
                id="ref-reason"
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                aria-label="Reason for referral"
                placeholder="e.g., Post-accident MRI evaluation"
              />
            </div>

            <button
              className="pp-btn pp-btn--primary"
              aria-label="Submit referral request"
              onClick={() => void handleRequest()}
              disabled={submitting || !toSpecialty || !reason.trim()}
            >
              {submitting ? "Submitting..." : "Submit referral request"}
            </button>
            <p className="pp-text--sm pp-text--muted">
              Your PCP is automatically listed as the requesting provider. Submitted requests appear above with status "requested".
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
