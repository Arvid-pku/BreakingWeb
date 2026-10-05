import { useCallback, useEffect, useState } from "react";

import { usePatientPortal } from "../context";
import type { Pharmacy, Prescription } from "../types";

export function MedicationsPage() {
  const { api, providers, notify } = usePatientPortal();
  const [active, setActive] = useState<Prescription[]>([]);
  const [inactive, setInactive] = useState<Prescription[]>([]);
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [transferRxId, setTransferRxId] = useState<string | null>(null);
  const [transferPharmacyId, setTransferPharmacyId] = useState("");

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;
  const pharmacyName = (id: string) => pharmacies.find((p) => p.id === id)?.name ?? id;

  const loadMedications = useCallback(async () => {
    try {
      const items = await api.listMedications();
      setActive(items.filter((rx) => rx.status === "active"));
      setInactive(items.filter((rx) => rx.status !== "active"));
    } catch {
      // silently continue
    }
  }, [api]);

  const loadPharmacies = useCallback(async () => {
    try {
      setPharmacies(await api.listPharmacies());
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => {
    void loadMedications();
    void loadPharmacies();
  }, [loadMedications, loadPharmacies]);

  const handleRefill = async (rxId: string) => {
    try {
      await api.refillMedication(rxId);
      notify("Refill requested successfully");
      void loadMedications();
    } catch {
      notify("Failed to request refill");
    }
  };

  const handleRenewal = async (rxId: string) => {
    try {
      await api.requestRenewal(rxId);
      notify("Renewal request sent to your provider");
      void loadMedications();
    } catch {
      notify("Failed to request renewal");
    }
  };

  const handleTransfer = async () => {
    if (!transferRxId || !transferPharmacyId) return;
    try {
      await api.transferMedication(transferRxId, transferPharmacyId);
      notify("Prescription transferred");
      setTransferRxId(null);
      setTransferPharmacyId("");
      void loadMedications();
      void loadPharmacies();
    } catch {
      notify("Failed to transfer prescription");
    }
  };

  const isExpiringSoon = (rx: Prescription) => {
    const expiresAt = new Date(rx.expires_at);
    const now = new Date();
    const thirtyDays = 30 * 24 * 60 * 60 * 1000;
    return expiresAt.getTime() - now.getTime() < thirtyDays;
  };

  const refillColor = (remaining: number) => {
    if (remaining >= 2) return "pp-refill--green";
    if (remaining === 1) return "pp-refill--yellow";
    return "pp-refill--red";
  };

  return (
    <div aria-label="Medications Page">
      <h2>Medications</h2>

      <section aria-label="Active Prescriptions" className="pp-section">
        <h3>Active Prescriptions</h3>
        {active.length === 0 ? (
          <p>No active prescriptions.</p>
        ) : (
          <div className="pp-med-cards">
            {active.map((rx) => (
              <article
                key={rx.id}
                className="pp-med-card"
                aria-label={`${rx.medication} ${rx.dosage} - ${rx.status}`}
              >
                <div className="pp-med-card__header">
                  <h4>{rx.medication} {rx.dosage}</h4>
                  <span className={`pp-status-badge pp-status-badge--${rx.status}`}>{rx.status}</span>
                </div>
                <dl className="pp-med-card__details">
                  <div>
                    <dt>Frequency</dt>
                    <dd>{rx.frequency}</dd>
                  </div>
                  <div>
                    <dt>Prescriber</dt>
                    <dd>{providerName(rx.provider_id)}</dd>
                  </div>
                  <div>
                    <dt>Pharmacy</dt>
                    <dd>{pharmacyName(rx.pharmacy_id)}</dd>
                  </div>
                  <div>
                    <dt>Refills Remaining</dt>
                    <dd><span className={refillColor(rx.refills_remaining)}>{rx.refills_remaining}</span></dd>
                  </div>
                  <div>
                    <dt>Last Filled</dt>
                    <dd>{new Date(rx.last_filled).toLocaleDateString()}</dd>
                  </div>
                  <div>
                    <dt>Expires</dt>
                    <dd className={isExpiringSoon(rx) ? "pp-text--danger" : ""}>{new Date(rx.expires_at).toLocaleDateString()}</dd>
                  </div>
                </dl>

                {rx.interactions.length > 0 && (
                  <div role="alert" aria-label="Drug interaction warning" className="pp-interaction-warning">
                    <strong>Interactions:</strong> {rx.interactions.join(", ")}
                  </div>
                )}

                <div className="pp-med-card__actions">
                  {rx.refills_remaining > 0 && rx.status === "active" && (
                    <button
                      className="pp-btn pp-btn--primary pp-btn--sm"
                      aria-label={`Request refill for ${rx.medication}`}
                      onClick={() => handleRefill(rx.id)}
                    >
                      Request Refill
                    </button>
                  )}
                  {rx.refills_remaining === 0 && (
                    <button
                      className="pp-btn pp-btn--secondary pp-btn--sm"
                      aria-label={`Request renewal for ${rx.medication}`}
                      onClick={() => handleRenewal(rx.id)}
                    >
                      Request Renewal
                    </button>
                  )}
                  <button
                    className="pp-btn pp-btn--secondary pp-btn--sm"
                    aria-label={`Transfer ${rx.medication} to another pharmacy`}
                    onClick={() => setTransferRxId(rx.id)}
                  >
                    Transfer Pharmacy
                  </button>
                </div>

                {transferRxId === rx.id && (
                  <div
                    role="dialog"
                    aria-modal="true"
                    aria-label={`Transfer prescription form for ${rx.medication}`}
                    className="pp-form-section"
                  >
                    <h4>Transfer Prescription — {rx.medication}</h4>
                    <div className="pp-form-field">
                      <label htmlFor={`transfer-pharmacy-${rx.id}`}>Select Pharmacy</label>
                      <select
                        id={`transfer-pharmacy-${rx.id}`}
                        value={transferPharmacyId}
                        onChange={(e) => setTransferPharmacyId(e.target.value)}
                        aria-label="Select pharmacy for transfer"
                      >
                        <option value="">Select a pharmacy...</option>
                        {pharmacies.map((pharmacy) => (
                          <option key={pharmacy.id} value={pharmacy.id}>
                            {`${pharmacy.name}${pharmacy.is_mail_order ? " [Mail]" : ""}`}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="pp-form-actions">
                      <button
                        className="pp-btn pp-btn--primary"
                        aria-label="Confirm transfer"
                        onClick={handleTransfer}
                        disabled={!transferPharmacyId}
                      >
                        Transfer
                      </button>
                      <button
                        className="pp-btn pp-btn--secondary"
                        aria-label="Cancel transfer"
                        onClick={() => { setTransferRxId(null); setTransferPharmacyId(""); }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section aria-label="Inactive Prescriptions" className="pp-section">
        <button
          className="pp-btn pp-btn--secondary"
          aria-label={showInactive ? "Hide inactive prescriptions" : "Show inactive prescriptions"}
          onClick={() => setShowInactive(!showInactive)}
        >
          {showInactive ? "Hide" : "Show"} Inactive Prescriptions ({inactive.length})
        </button>
        {showInactive && inactive.length > 0 && (
          <table aria-label="Inactive prescriptions table">
            <thead>
              <tr>
                <th>Medication</th>
                <th>Dosage</th>
                <th>Status</th>
                <th>Prescriber</th>
                <th>Expires</th>
              </tr>
            </thead>
            <tbody>
              {inactive.map((rx) => (
                <tr key={rx.id}>
                  <td>{rx.medication}</td>
                  <td>{rx.dosage}</td>
                  <td><span className={`pp-status-badge pp-status-badge--${rx.status}`}>{rx.status}</span></td>
                  <td>{providerName(rx.provider_id)}</td>
                  <td>{new Date(rx.expires_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
