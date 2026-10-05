import { useCallback, useEffect, useState } from "react";

import { usePatientPortal } from "../context";
import type { Immunization, Pharmacy } from "../types";

export function ProfilePage() {
  const { api, profile, providers, refreshProfile, notify } = usePatientPortal();
  const [immunizations, setImmunizations] = useState<Immunization[]>([]);
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);

  // Demographics form
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [ecName, setEcName] = useState("");
  const [ecPhone, setEcPhone] = useState("");
  const [ecRelationship, setEcRelationship] = useState("");

  // Insurance form
  const [planName, setPlanName] = useState("");
  const [memberId, setMemberId] = useState("");
  const [groupNumber, setGroupNumber] = useState("");

  // Add pharmacy form
  const [showAddPharmacy, setShowAddPharmacy] = useState(false);
  const [newPharmName, setNewPharmName] = useState("");
  const [newPharmAddress, setNewPharmAddress] = useState("");
  const [newPharmPhone, setNewPharmPhone] = useState("");
  const [newPharmMailOrder, setNewPharmMailOrder] = useState(false);

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;

  // Populate forms from profile
  useEffect(() => {
    if (!profile) return;
    setPhone(profile.phone);
    setEmail(profile.email);
    setEcName(profile.emergency_contact.name);
    setEcPhone(profile.emergency_contact.phone);
    setEcRelationship(profile.emergency_contact.relationship);
    setPlanName(profile.insurance_plan.plan_name);
    setMemberId(profile.insurance_plan.member_id);
    setGroupNumber(profile.insurance_plan.group_number);
  }, [profile]);

  const loadExtras = useCallback(async () => {
    try {
      const imm = await api.listImmunizations();
      setImmunizations(imm);
    } catch {
      // silently continue
    }
    try {
      setPharmacies(await api.listPharmacies());
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => { void loadExtras(); }, [loadExtras]);

  const handleSaveDemographics = async () => {
    try {
      await api.updateDemographics({
        phone,
        email,
        emergency_contact: { name: ecName, phone: ecPhone, relationship: ecRelationship },
      });
      notify("Demographics updated");
      void refreshProfile();
    } catch {
      notify("Failed to update demographics");
    }
  };

  const handleSaveInsurance = async () => {
    try {
      await api.updateInsurance({ plan_name: planName, member_id: memberId, group_number: groupNumber });
      notify("Insurance updated");
      void refreshProfile();
    } catch {
      notify("Failed to update insurance");
    }
  };

  const handleAddPharmacy = async () => {
    if (!newPharmName.trim() || !newPharmAddress.trim() || !newPharmPhone.trim()) return;
    try {
      const pharm = await api.addPharmacy({
        name: newPharmName,
        address: newPharmAddress,
        phone: newPharmPhone,
        is_mail_order: newPharmMailOrder,
      });
      setPharmacies((prev) => [...prev, pharm]);
      setShowAddPharmacy(false);
      setNewPharmName("");
      setNewPharmAddress("");
      setNewPharmPhone("");
      setNewPharmMailOrder(false);
      notify("Pharmacy added");
      void refreshProfile();
    } catch {
      notify("Failed to add pharmacy");
    }
  };

  const handleSetDefault = async (pharmId: string) => {
    try {
      await api.setDefaultPharmacy(pharmId);
      notify("Default pharmacy updated");
      void refreshProfile();
      setPharmacies((prev) => prev.map((p) => ({ ...p, is_default: p.id === pharmId })));
    } catch {
      notify("Failed to set default pharmacy");
    }
  };

  const handleRemovePharmacy = async (pharmId: string) => {
    try {
      await api.removePharmacy(pharmId);
      setPharmacies((prev) => prev.filter((p) => p.id !== pharmId));
      notify("Pharmacy removed");
      void refreshProfile();
    } catch {
      notify("Failed to remove pharmacy");
    }
  };

  const pcpProvider = providers.find((p) => p.id === profile?.pcp_id);

  return (
    <div aria-label="Profile Page">
      <h2>Profile</h2>

      {/* Demographics */}
      <section aria-label="Patient Demographics" className="pp-section">
        <h3>Demographics</h3>
        {profile && (!profile.name || !profile.dob) && (
          <div className="pp-card pp-card--warning" aria-label="Profile data incomplete">
            <p>Profile is loading or returned incomplete data (name/DOB missing). Submitting now would overwrite other fields with blanks. Click below to retry.</p>
            <button
              type="button"
              className="pp-btn pp-btn--secondary"
              onClick={() => void refreshProfile()}
              aria-label="Refresh profile"
            >
              Refresh profile
            </button>
          </div>
        )}
        {profile && profile.name && profile.dob && (
          <form aria-label="Patient Demographics" onSubmit={(e) => { e.preventDefault(); handleSaveDemographics(); }}>
            <div className="pp-form-field">
              <label htmlFor="profile-name">Name</label>
              <input id="profile-name" type="text" value={profile.name} readOnly aria-label="Patient name (read only)" />
            </div>
            <div className="pp-form-field">
              <label htmlFor="profile-dob">Date of Birth</label>
              <input id="profile-dob" type="text" value={profile.dob} readOnly aria-label="Date of birth (read only)" />
            </div>
            <div className="pp-form-field">
              <label htmlFor="profile-sex">Sex</label>
              <input id="profile-sex" type="text" value={profile.sex} readOnly aria-label="Sex (read only)" />
            </div>
            <div className="pp-form-field">
              <label htmlFor="profile-phone">Phone</label>
              <input
                id="profile-phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                aria-label={`Phone number: ${phone || "(empty)"}`}
              />
            </div>
            <div className="pp-form-field">
              <label htmlFor="profile-email">Email</label>
              <input
                id="profile-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-label={`Email address: ${email || "(empty)"}`}
              />
            </div>
            <fieldset className="pp-fieldset">
              <legend>Emergency Contact</legend>
              <div className="pp-form-field">
                <label htmlFor="ec-name">Name</label>
                <input
                  id="ec-name"
                  type="text"
                  value={ecName}
                  onChange={(e) => setEcName(e.target.value)}
                  aria-label={`Emergency contact name: ${ecName || "(empty)"}`}
                />
              </div>
              <div className="pp-form-field">
                <label htmlFor="ec-phone">Phone</label>
                <input
                  id="ec-phone"
                  type="tel"
                  value={ecPhone}
                  onChange={(e) => setEcPhone(e.target.value)}
                  aria-label={`Emergency contact phone: ${ecPhone || "(empty)"}`}
                />
              </div>
              <div className="pp-form-field">
                <label htmlFor="ec-relationship">Relationship</label>
                <input
                  id="ec-relationship"
                  type="text"
                  value={ecRelationship}
                  onChange={(e) => setEcRelationship(e.target.value)}
                  aria-label={`Emergency contact relationship: ${ecRelationship || "(empty)"}`}
                />
              </div>
            </fieldset>
            <button
              type="submit"
              className="pp-btn pp-btn--primary"
              aria-label="Save demographics"
            >
              Save Demographics
            </button>
          </form>
        )}
      </section>

      {/* Insurance */}
      <section aria-label="Insurance Card Details" className="pp-section">
        <h3>Insurance</h3>
        {profile && (
          <form aria-label="Insurance information" onSubmit={(e) => { e.preventDefault(); handleSaveInsurance(); }}>
            <div className="pp-insurance-card">
              <div className="pp-form-field">
                <label htmlFor="ins-plan">Plan Name</label>
                <input
                  id="ins-plan"
                  type="text"
                  value={planName}
                  onChange={(e) => setPlanName(e.target.value)}
                  aria-label={`Insurance plan name: ${planName || "(empty)"}`}
                />
              </div>
              <div className="pp-form-field">
                <label htmlFor="ins-member">Member ID</label>
                <input
                  id="ins-member"
                  type="text"
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  aria-label={`Insurance member ID: ${memberId || "(empty)"}`}
                />
              </div>
              <div className="pp-form-field">
                <label htmlFor="ins-group">Group Number</label>
                <input
                  id="ins-group"
                  type="text"
                  value={groupNumber}
                  onChange={(e) => setGroupNumber(e.target.value)}
                  aria-label={`Insurance group number: ${groupNumber || "(empty)"}`}
                />
              </div>
              <div className="pp-form-field">
                <label>Copay</label>
                <span aria-label="Copay amount">${profile.insurance_plan.copay}</span>
              </div>
              <div className="pp-form-field">
                <label>Deductible</label>
                <span aria-label="Deductible amount">${profile.insurance_plan.deductible} (${profile.insurance_plan.deductible_met} met)</span>
              </div>
            </div>
            <button
              type="submit"
              className="pp-btn pp-btn--primary"
              aria-label="Save insurance information"
            >
              Save Insurance
            </button>
          </form>
        )}
      </section>

      {/* Pharmacies */}
      <section aria-label="Pharmacies" className="pp-section">
        <h3>Pharmacies</h3>
        {pharmacies.length === 0 ? (
          <p>No pharmacies on file.</p>
        ) : (
          <table aria-label="Pharmacy list">
            <thead>
              <tr>
                <th>Pharmacy ID</th>
                <th>Name</th>
                <th>Address</th>
                <th>Phone</th>
                <th>Type</th>
                <th>Dispensing Fee</th>
                <th>90-Day Cost</th>
                <th>Default</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pharmacies.map((pharm) => (
                <tr key={pharm.id}>
                  <td>{pharm.id}</td>
                  <td>{pharm.name}</td>
                  <td>{pharm.address}</td>
                  <td>{pharm.phone}</td>
                  <td>{pharm.is_mail_order ? "Mail Order" : "Retail"}</td>
                  <td>${pharm.dispensing_fee}</td>
                  <td>{pharm.cost_per_90day_supply ? `$${pharm.cost_per_90day_supply}` : "N/A"}</td>
                  <td>{pharm.is_default ? "Yes" : "No"}</td>
                  <td>
                    {!pharm.is_default && (
                      <>
                        <button
                          className="pp-btn pp-btn--secondary pp-btn--sm"
                          aria-label={`Set ${pharm.name} as default pharmacy`}
                          onClick={() => handleSetDefault(pharm.id)}
                        >
                          Set Default
                        </button>
                        <button
                          className="pp-btn pp-btn--danger pp-btn--sm"
                          aria-label={`Remove ${pharm.name}`}
                          onClick={() => handleRemovePharmacy(pharm.id)}
                        >
                          Remove
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button
          className="pp-btn pp-btn--primary"
          aria-label={showAddPharmacy ? "Cancel adding pharmacy" : "Add pharmacy"}
          onClick={() => setShowAddPharmacy(!showAddPharmacy)}
        >
          {showAddPharmacy ? "Cancel" : "Add Pharmacy"}
        </button>
        {showAddPharmacy && (
          <div className="pp-form-section" aria-label="Add pharmacy form">
            <div className="pp-form-field">
              <label htmlFor="new-pharm-name">Pharmacy Name</label>
              <input id="new-pharm-name" type="text" value={newPharmName} onChange={(e) => setNewPharmName(e.target.value)} aria-label="Pharmacy name" />
            </div>
            <div className="pp-form-field">
              <label htmlFor="new-pharm-address">Address</label>
              <input id="new-pharm-address" type="text" value={newPharmAddress} onChange={(e) => setNewPharmAddress(e.target.value)} aria-label="Pharmacy address" />
            </div>
            <div className="pp-form-field">
              <label htmlFor="new-pharm-phone">Phone</label>
              <input id="new-pharm-phone" type="tel" value={newPharmPhone} onChange={(e) => setNewPharmPhone(e.target.value)} aria-label="Pharmacy phone" />
            </div>
            <div className="pp-form-field">
              <label className="pp-checkbox-label">
                <input type="checkbox" checked={newPharmMailOrder} onChange={(e) => setNewPharmMailOrder(e.target.checked)} aria-label="Mail order pharmacy" />
                Mail Order
              </label>
            </div>
            <button
              className="pp-btn pp-btn--primary"
              aria-label="Submit new pharmacy"
              onClick={handleAddPharmacy}
              disabled={!newPharmName.trim() || !newPharmAddress.trim() || !newPharmPhone.trim()}
            >
              Add Pharmacy
            </button>
          </div>
        )}
      </section>

      {/* Providers */}
      <section aria-label="My Providers" className="pp-section">
        <h3>My Providers</h3>
        <table aria-label="Provider list">
          <thead>
            <tr>
              <th>Name</th>
              <th>Specialty</th>
              <th>Department</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((prov) => (
              <tr key={prov.id}>
                <td>{prov.name}</td>
                <td>{prov.specialty}</td>
                <td>{prov.department}</td>
                <td>{prov.id === profile?.pcp_id ? <span className="pp-pcp-badge" aria-label="Primary Care Provider">PCP</span> : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Conditions / Diagnoses */}
      {profile && profile.conditions.length > 0 && (
        <section aria-label="Conditions and Diagnoses" className="pp-section">
          <h3>Conditions / Diagnoses</h3>
          <ul aria-label="Conditions list" className="pp-tag-list">
            {profile.conditions.map((condition) => (
              <li key={condition} className="pp-tag" aria-label={`Condition: ${condition}`}>
                {condition}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Allergies */}
      {profile && profile.allergies.length > 0 && (
        <section aria-label="Allergies" className="pp-section">
          <h3>Allergies</h3>
          <ul aria-label="Allergies list" className="pp-tag-list">
            {profile.allergies.map((allergy) => (
              <li key={allergy} className="pp-tag pp-tag--warning" aria-label={`Allergy: ${allergy}`}>
                ⚠ {allergy}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Applicable Screenings */}
      {profile && profile.applicable_screenings.length > 0 && (
        <section aria-label="Applicable Screenings" className="pp-section">
          <h3>Applicable Screenings</h3>
          <table aria-label="Applicable Screenings">
            <thead>
              <tr>
                <th>Screening</th>
                <th>Frequency</th>
                <th>Last Completed</th>
                <th>Next Due</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {profile.applicable_screenings.map((s) => {
                const isOverdue = s.next_due !== null && new Date(s.next_due) < new Date();
                return (
                  <tr key={s.screening_name}>
                    <td>{s.screening_name}</td>
                    <td className="pp-text--sm pp-text--muted">{s.frequency}</td>
                    <td>{s.last_completed ? new Date(s.last_completed).toLocaleDateString() : "Never"}</td>
                    <td className={isOverdue ? "pp-text--danger" : ""} aria-label={`Next due: ${s.next_due ? new Date(s.next_due).toLocaleDateString() : "N/A"}`}>
                      {s.next_due ? new Date(s.next_due).toLocaleDateString() : "N/A"}
                    </td>
                    <td>
                      {isOverdue
                        ? <span className="pp-status-badge pp-status-badge--denied" aria-label="Overdue">Overdue</span>
                        : <span className="pp-status-badge pp-status-badge--approved" aria-label="Current">Current</span>
                      }
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {/* Immunizations */}
      <section aria-label="Immunization Record" className="pp-section">
        <h3>Immunization Record</h3>
        {immunizations.length === 0 ? (
          <p>No immunization records.</p>
        ) : (
          <table aria-label="Immunization Record">
            <thead>
              <tr>
                <th>Vaccine</th>
                <th>Date Administered</th>
                <th>Administered By</th>
                <th>Next Due</th>
                <th>Series Complete</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {immunizations.map((imm) => {
                const isOverdue = imm.next_due_at !== null && new Date(imm.next_due_at) < new Date();
                return (
                <tr key={imm.id}>
                  <td>{imm.vaccine_name}</td>
                  <td>{new Date(imm.administered_at).toLocaleDateString()}</td>
                  <td>{providerName(imm.administering_provider_id)}</td>
                  <td>{imm.next_due_at ? new Date(imm.next_due_at).toLocaleDateString() : "N/A"}</td>
                  <td>{imm.series_complete ? "Yes" : "No"}</td>
                  <td>
                    {imm.next_due_at === null
                      ? <span className="pp-status-badge pp-status-badge--approved" aria-label="Current">Current</span>
                      : isOverdue
                        ? <span className="pp-status-badge pp-status-badge--denied" aria-label="Overdue">Overdue</span>
                        : <span className="pp-status-badge pp-status-badge--approved" aria-label="Current">Current</span>
                    }
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
