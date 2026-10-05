import React, { useCallback, useEffect, useState } from "react";

import { usePatientPortal } from "../context";
import type { InsuranceClaim } from "../types";

export function BillingPage() {
  const { api, providers, profile, notify } = usePatientPortal();
  const [claims, setClaims] = useState<InsuranceClaim[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [appealReason, setAppealReason] = useState("");

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;

  const loadClaims = useCallback(async () => {
    try {
      const items = await api.listClaims();
      setClaims(items.sort((a, b) => new Date(b.service_date).getTime() - new Date(a.service_date).getTime()));
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => { void loadClaims(); }, [loadClaims]);

  const handlePay = async (clmId: string) => {
    try {
      await api.payClaim(clmId);
      notify("Payment submitted successfully");
      void loadClaims();
    } catch {
      notify("Failed to submit payment");
    }
  };

  const handleAppeal = async (clmId: string) => {
    if (!appealReason.trim()) return;
    try {
      await api.appealClaim(clmId, { reason: appealReason });
      notify("Appeal submitted successfully");
      setAppealReason("");
      setExpandedId(null);
      void loadClaims();
    } catch {
      notify("Failed to submit appeal");
    }
  };

  // Aggregates
  const totalOutstanding = claims
    .filter((c) => c.status === "approved" || c.status === "appealed")
    .reduce((sum, c) => sum + parseFloat(c.patient_responsibility), 0);

  const deductible = profile?.insurance_plan?.deductible ? parseFloat(profile.insurance_plan.deductible) : 0;
  const deductibleMet = profile?.insurance_plan?.deductible_met ? parseFloat(profile.insurance_plan.deductible_met) : 0;
  const deductiblePct = deductible > 0 ? Math.min((deductibleMet / deductible) * 100, 100) : 0;

  const ytdOop = claims
    .reduce((sum, c) => sum + parseFloat(c.patient_responsibility), 0);

  const canAppeal = (claim: InsuranceClaim) =>
    claim.status === "denied" && claim.eob_available && new Date(claim.appeal_deadline) > new Date();

  const canPay = (claim: InsuranceClaim) =>
    (claim.status === "approved" || claim.status === "appealed") && parseFloat(claim.patient_responsibility) > 0;

  return (
    <div aria-label="Billing Page">
      <h2>Billing & Claims</h2>

      <div className="pp-billing-layout">
        <div className="pp-billing-main">
          <section aria-label="Insurance Claims" className="pp-section">
            <h3>Claims</h3>
            {claims.length === 0 ? (
              <p>No claims on file.</p>
            ) : (
              <table aria-label="Insurance Claims">
                <thead>
                  <tr>
                    <th>Claim ID</th>
                    <th>Service Date</th>
                    <th>Provider</th>
                    <th>Linked Appointment</th>
                    <th>Procedure</th>
                    <th>Status</th>
                    <th>Amount Billed</th>
                    <th>Insurance Covered</th>
                    <th>Your Responsibility</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {claims.map((claim) => (
                    <React.Fragment key={claim.id}>
                      <tr>
                        <td>{claim.id}</td>
                        <td>{new Date(claim.service_date).toLocaleDateString()}</td>
                        <td>{providerName(claim.provider_id)}</td>
                        <td aria-label={`Linked appointment ${claim.appointment_id}`}>{claim.appointment_id}</td>
                        <td>{claim.procedure_code}</td>
                        <td><span className={`pp-status-badge pp-status-badge--${claim.status}`}>{claim.status}</span></td>
                        <td>${parseFloat(claim.amount_billed).toFixed(2)}</td>
                        <td>${parseFloat(claim.amount_covered).toFixed(2)}</td>
                        <td>${parseFloat(claim.patient_responsibility).toFixed(2)}</td>
                        <td>
                          {claim.eob_available && (
                            <button
                              className="pp-btn pp-btn--secondary pp-btn--sm"
                              aria-label={`View EOB for claim ${claim.id}`}
                              onClick={() => setExpandedId(expandedId === claim.id ? null : claim.id)}
                            >
                              {expandedId === claim.id ? "Hide" : "View"} EOB
                            </button>
                          )}
                          {canPay(claim) && (
                            <button
                              className="pp-btn pp-btn--primary pp-btn--sm"
                              aria-label={`Pay balance for claim ${claim.id}`}
                              onClick={() => handlePay(claim.id)}
                            >
                              Pay Balance
                            </button>
                          )}
                          {canAppeal(claim) && (
                            <button
                              className="pp-btn pp-btn--warning pp-btn--sm"
                              aria-label={`Appeal claim ${claim.id}`}
                              onClick={() => setExpandedId(claim.id)}
                            >
                              Dispute/Appeal
                            </button>
                          )}
                        </td>
                      </tr>
                      {expandedId === claim.id && (
                        <tr key={`${claim.id}-detail`} className="pp-detail-row">
                          <td colSpan={10}>
                            <div className="pp-claim-detail" aria-label={`Claim details for ${claim.id}`}>
                              <div><strong>Claim ID:</strong> {claim.id}</div>
                              <div><strong>Linked Appointment:</strong> {claim.appointment_id}</div>
                              <div><strong>Procedure Code:</strong> {claim.procedure_code}</div>
                              <div><strong>Diagnosis Code:</strong> {claim.diagnosis_code}</div>
                              <div><strong>Appeal Deadline:</strong> {new Date(claim.appeal_deadline).toLocaleDateString()}</div>
                              <div><strong>EOB Available:</strong> {claim.eob_available ? "Yes" : "No"}</div>
                              <div><strong>Denial Reason:</strong> {claim.denial_reason ?? "Not listed"}</div>
                              <div><strong>Supporting Referral:</strong> {claim.supporting_referral_id ?? "None documented"}</div>
                              <div>
                                <strong>Supporting Labs:</strong>{" "}
                                {claim.supporting_lab_ids.length > 0 ? claim.supporting_lab_ids.join(", ") : "None documented"}
                              </div>
                              {canAppeal(claim) && (
                                <div className="pp-appeal-form" aria-label="Appeal form">
                                  <label htmlFor={`appeal-reason-${claim.id}`}>Reason for appeal</label>
                                  <textarea
                                    id={`appeal-reason-${claim.id}`}
                                    value={appealReason}
                                    onChange={(e) => setAppealReason(e.target.value)}
                                    aria-label="Enter reason for appeal"
                                    placeholder="Describe why you are appealing this claim..."
                                    rows={3}
                                  />
                                  <button
                                    className="pp-btn pp-btn--primary"
                                    aria-label="Submit appeal"
                                    onClick={() => handleAppeal(claim.id)}
                                    disabled={!appealReason.trim()}
                                  >
                                    Submit Appeal
                                  </button>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>

        <aside className="pp-billing-sidebar" aria-label="Billing Summary">
          <h3>Summary</h3>
          <div className="pp-billing-summary">
            <div className="pp-summary-item">
              <span className="pp-summary-label">Total Outstanding</span>
              <span className="pp-summary-value">${totalOutstanding.toFixed(2)}</span>
            </div>
            <div className="pp-summary-item">
              <span className="pp-summary-label">Deductible</span>
              <progress
                value={deductibleMet}
                max={deductible}
                aria-label={`Deductible progress: $${deductibleMet.toFixed(2)} of $${deductible.toFixed(2)}`}
              />
              <span className="pp-summary-detail">${deductibleMet.toFixed(2)} / ${deductible.toFixed(2)}</span>
            </div>
            <div className="pp-summary-item">
              <span className="pp-summary-label">YTD Out-of-Pocket</span>
              <span className="pp-summary-value">${ytdOop.toFixed(2)}</span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
