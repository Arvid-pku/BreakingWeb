import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import type { Reservation, GeniusInfo } from "../types";
import { useBookingLayout } from "../context";

type TabFilter = "all" | "upcoming" | "completed" | "cancelled";

function statusBadgeClass(status: string): string {
  switch (status.toLowerCase()) {
    case "confirmed":
      return "bk-status bk-status--confirmed";
    case "completed":
      return "bk-status bk-status--completed";
    case "cancelled":
      return "bk-status bk-status--cancelled";
    case "modified":
      return "bk-status bk-status--modified";
    default:
      return "bk-status";
  }
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00");
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function MyTrips() {
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();

  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [genius, setGenius] = useState<GeniusInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabFilter>("all");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.listReservations().catch(() => ({ reservations: [], total: 0 })),
      api.getGenius().catch(() => null),
    ]).then(([resData, geniusData]) => {
      if (cancelled) return;
      setReservations(resData.reservations ?? []);
      setGenius(geniusData);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [api, sessionId]);

  const filteredReservations = reservations.filter((r) => {
    if (activeTab === "all") return true;
    const status = r.status.toLowerCase();
    if (activeTab === "upcoming") return status === "confirmed" || status === "modified";
    if (activeTab === "completed") return status === "completed";
    if (activeTab === "cancelled") return status === "cancelled";
    return true;
  });

  if (loading) {
    return <div className="bk-loading">Loading your trips...</div>;
  }

  const tabs: { key: TabFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "upcoming", label: "Upcoming" },
    { key: "completed", label: "Completed" },
    { key: "cancelled", label: "Cancelled" },
  ];

  return (
    <div>
      {/* Genius Level Banner */}
      {genius && (
        <div className="bk-genius-banner">
          <h3>
            Genius Level {genius.level}
          </h3>
          <p>
            You have {genius.total_bookings} bookings.
            {genius.bookings_needed_for_next > 0 && (
              <> Book {genius.bookings_needed_for_next} more to reach the next level.</>
            )}
          </p>
        </div>
      )}

      <div className="bk-section">
        <h1 className="bk-section-title">My Trips</h1>

        {/* Tab Filters */}
        <div className="bk-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              className={`bk-tab-btn ${activeTab === tab.key ? "active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Reservation List */}
        {filteredReservations.length === 0 ? (
          <div className="bk-empty">
            <h3>No reservations found</h3>
            <p>
              {activeTab === "all"
                ? "You haven't made any bookings yet."
                : `No ${activeTab} reservations.`}
            </p>
            <Link
              to={preserveQueryParams("/search", location.search)}
              className="bk-btn bk-btn--primary"
              style={{ marginTop: 16, display: "inline-flex" }}
            >
              Search for stays
            </Link>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {filteredReservations.map((reservation) => (
              <div key={reservation.id} className="bk-card">
                <div className="bk-card-horizontal">
                  <div className="bk-card-body">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div>
                        <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>
                          {reservation.property_name}
                        </h3>
                        <div style={{ fontSize: 13, color: "var(--bk-gray-600)", marginBottom: 8 }}>
                          {reservation.room_type_name}
                        </div>
                      </div>
                      <span className={statusBadgeClass(reservation.status)}>
                        {reservation.status}
                      </span>
                    </div>

                    <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 13, marginBottom: 8 }}>
                      <div>
                        <strong>Check-in:</strong> {formatDate(reservation.check_in)}
                      </div>
                      <div>
                        <strong>Check-out:</strong> {formatDate(reservation.check_out)}
                      </div>
                      <div>
                        <strong>Nights:</strong> {reservation.nights}
                      </div>
                      <div>
                        <strong>Guests:</strong> {reservation.guests}
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: "auto" }}>
                      <div style={{ fontSize: 12, color: "var(--bk-gray-600)" }}>
                        Confirmation: <strong>{reservation.confirmation_number}</strong>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div className="bk-price">
                          {reservation.currency === "USD" ? "$" : reservation.currency}{" "}
                          {reservation.total_price.toFixed(2)}
                        </div>
                        <div className="bk-price-note">Total price</div>
                      </div>
                    </div>

                    {reservation.is_genius_deal && (
                      <div style={{ marginTop: 6 }}>
                        <span className="bk-badge bk-badge--genius">Genius Deal</span>
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                      <Link
                        to={preserveQueryParams(`/trips/${reservation.id}`, location.search)}
                        className="bk-btn bk-btn--primary bk-btn--sm"
                      >
                        View details
                      </Link>
                      {/* Inline cancel removed: cancellation requires acknowledging
                          the fee via the detail page modal. Users click "View details". */}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
