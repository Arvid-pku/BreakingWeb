import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { preserveQueryParams } from "@breakingweb/shared";

import { usePatientPortal } from "../context";
import type { Appointment, InsuranceClaim, Prescription } from "../types";

// Use shared preserveQueryParams — see Shell.tsx for the bug-history note on
// why a session-only preserve helper here was catastrophic for recording.
const preserveSession = preserveQueryParams;

export function DashboardPage() {
  const location = useLocation();
  const { profile, providers, unreadCount, api } = usePatientPortal();
  const [upcoming, setUpcoming] = useState<Appointment[]>([]);
  const [needsRefill, setNeedsRefill] = useState<Prescription[]>([]);
  const [deniedClaims, setDeniedClaims] = useState<InsuranceClaim[]>([]);

  useEffect(() => {
    void api.listAppointments({ status: "scheduled" }).then((items) => {
      const sorted = items
        .sort((a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime())
        .slice(0, 3);
      setUpcoming(sorted);
    });
    void api.listMedications({ status: "active" }).then((items) => {
      setNeedsRefill(items.filter((rx) => rx.refills_remaining <= 1));
    });
    void api.listClaims({ status: "denied" }).then((items) => {
      setDeniedClaims(items);
    });
  }, [api]);

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;
  const providerSpecialty = (id: string) => providers.find((p) => p.id === id)?.specialty ?? "";
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  return (
    <div aria-label="Patient Dashboard">
      <section aria-label="Welcome Banner" className="pp-section">
        <h2>Welcome, {profile?.name ?? "Patient"}</h2>
        <p>{today}</p>
      </section>

      <section aria-label="Upcoming Appointments" className="pp-section">
        <h3>Upcoming Appointments</h3>
        {upcoming.length === 0 ? (
          <p>No upcoming appointments.</p>
        ) : (
          <table aria-label="Upcoming appointments table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Provider</th>
                <th>Specialty</th>
                <th>Type</th>
                <th>Location</th>
              </tr>
            </thead>
            <tbody>
              {upcoming.map((apt) => {
                const start = new Date(apt.datetime);
                const end = new Date(start.getTime() + (apt.duration_minutes ?? 30) * 60_000);
                const datePart = start.toLocaleDateString();
                const startTime = start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                const endTime = end.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                return (
                <tr key={apt.id}>
                  <td>{datePart} {startTime} – {endTime}</td>
                  <td>{providerName(apt.provider_id)}</td>
                  <td>{providerSpecialty(apt.provider_id)}</td>
                  <td><span className={`pp-type-badge pp-type-badge--${apt.type}`}>{apt.type}</span></td>
                  <td>{apt.location}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <Link to={preserveSession("/appointments", location.search)} aria-label="View all appointments">View All</Link>
      </section>

      <section aria-label="Action Items" className="pp-section">
        <h3>Action Items</h3>
        <ul className="pp-action-list">
          {unreadCount > 0 && (
            <li>
              <Link to={preserveSession("/messages", location.search)} aria-label={`${unreadCount} unread messages`}>
                {unreadCount} unread message{unreadCount !== 1 ? "s" : ""}
              </Link>
            </li>
          )}
          {needsRefill.length > 0 && (
            <li>
              <Link to={preserveSession("/medications", location.search)} aria-label={`${needsRefill.length} prescriptions need refill`}>
                {needsRefill.length} prescription{needsRefill.length !== 1 ? "s" : ""} need refill or renewal
              </Link>
            </li>
          )}
          {deniedClaims.length > 0 && (
            <li>
              <Link to={preserveSession("/billing", location.search)} aria-label={`${deniedClaims.length} denied claims`}>
                {deniedClaims.length} denied claim{deniedClaims.length !== 1 ? "s" : ""} - review and appeal
              </Link>
            </li>
          )}
          {unreadCount === 0 && needsRefill.length === 0 && deniedClaims.length === 0 && (
            <li>No action items at this time.</li>
          )}
        </ul>
      </section>

      <section aria-label="Quick Actions" className="pp-section">
        <h3>Quick Actions</h3>
        <div className="pp-quick-actions">
          <Link to={preserveSession("/appointments", location.search)} className="pp-btn pp-btn--primary" aria-label="Schedule Appointment">
            Schedule Appointment
          </Link>
          <Link to={preserveSession("/messages", location.search)} className="pp-btn pp-btn--primary" aria-label="Send Message">
            Send Message
          </Link>
          <Link to={preserveSession("/medications", location.search)} className="pp-btn pp-btn--primary" aria-label="Request Refill">
            Request Refill
          </Link>
        </div>
      </section>
    </div>
  );
}
