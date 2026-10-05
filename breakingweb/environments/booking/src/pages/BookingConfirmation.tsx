import { useEffect, useState } from "react";
import { Link, useParams, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Reservation } from "../types";
import { useBookingLayout } from "../context";

export default function BookingConfirmation() {
  const { reservationId } = useParams<{ reservationId: string }>();
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();

  const [reservation, setReservation] = useState<Reservation | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!reservationId) return;
    let cancelled = false;

    api
      .getReservation(reservationId)
      .then((r) => {
        if (!cancelled) setReservation(r);
      })
      .catch(() => {
        if (!cancelled) notify("Error", "Failed to load reservation details.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [api, sessionId, reservationId, notify]);

  if (loading) {
    return <div className="bk-loading">Loading confirmation...</div>;
  }

  if (!reservation) {
    return (
      <div className="bk-empty">
        <h3>Reservation not found</h3>
        <p>We could not find the reservation details.</p>
        <Link
          to={preserveQueryParams("/home", location.search)}
          className="bk-btn bk-btn--primary"
          style={{ marginTop: 16, display: "inline-flex" }}
        >
          Back to home
        </Link>
      </div>
    );
  }

  const formatDate = (d: string) =>
    new Date(d + "T00:00").toLocaleDateString("en-US", {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
    });

  return (
    <div className="bk-confirmation">
      {/* Green checkmark */}
      <div className="bk-confirmation-check" aria-hidden="true">
        &#10003;
      </div>

      <h1 className="bk-section-title" style={{ fontSize: 26, marginBottom: 8 }}>
        Your booking is confirmed!
      </h1>
      <p className="bk-section-subtitle" style={{ marginBottom: 24 }}>
        Thank you for your reservation. A confirmation email has been sent.
      </p>

      {/* Confirmation number */}
      <div
        className="bk-card"
        style={{ padding: 24, marginBottom: 24, textAlign: "center" }}
      >
        <div
          style={{ fontSize: 13, color: "var(--bk-gray-600)", marginBottom: 4 }}
        >
          Confirmation Number
        </div>
        <div
          style={{
            fontSize: 28,
            fontWeight: 800,
            letterSpacing: 1,
            color: "var(--bk-blue)",
          }}
        >
          {reservation.confirmation_number}
        </div>
      </div>

      {/* Booking summary */}
      <div
        className="bk-card"
        style={{ padding: 24, marginBottom: 24, textAlign: "left" }}
      >
        <h2
          className="bk-section-title"
          style={{ fontSize: 18, marginBottom: 16 }}
        >
          Booking Summary
        </h2>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Property
            </span>
            <span style={{ fontWeight: 600 }}>{reservation.property_name}</span>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Room Type
            </span>
            <span style={{ fontWeight: 600 }}>
              {reservation.room_type_name}
            </span>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Check-in
            </span>
            <span style={{ fontWeight: 600 }}>
              {formatDate(reservation.check_in)}
            </span>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Check-out
            </span>
            <span style={{ fontWeight: 600 }}>
              {formatDate(reservation.check_out)}
            </span>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Duration
            </span>
            <span style={{ fontWeight: 600 }}>
              {reservation.nights} night{reservation.nights !== 1 ? "s" : ""}
            </span>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Guests
            </span>
            <span style={{ fontWeight: 600 }}>
              {reservation.guests} guest{reservation.guests !== 1 ? "s" : ""}
            </span>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Rooms
            </span>
            <span style={{ fontWeight: 600 }}>
              {reservation.rooms} room{reservation.rooms !== 1 ? "s" : ""}
            </span>
          </div>

          {reservation.meals_included && reservation.meals_included !== "none" && (
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
                Meals
              </span>
              <span style={{ fontWeight: 600 }}>
                {reservation.meals_included}
              </span>
            </div>
          )}

          {reservation.is_genius_deal && (
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
                Genius Discount
              </span>
              <span className="bk-badge bk-badge--genius">
                -{reservation.genius_discount}%
              </span>
            </div>
          )}

          <hr style={{ border: "none", borderTop: "1px solid var(--bk-border)", margin: "4px 0" }} />

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              Price per night
            </span>
            <span>
              {reservation.currency} {reservation.price_per_night.toFixed(2)}
            </span>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>Taxes</span>
            <span>{reservation.currency} {reservation.taxes.toFixed(2)}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>City fee</span>
            <span>{reservation.currency} {reservation.city_fee.toFixed(2)}</span>
          </div>
          {reservation.resort_fee > 0 && (
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>Resort fee</span>
              <span>{reservation.currency} {reservation.resort_fee.toFixed(2)}</span>
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>Cleaning fee</span>
            <span>{reservation.currency} {reservation.cleaning_fee.toFixed(2)}</span>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              paddingTop: 8,
              borderTop: "2px solid var(--bk-gray-800)",
            }}
          >
            <span style={{ fontSize: 18, fontWeight: 700 }}>Total</span>
            <span className="bk-price">
              {reservation.currency} {reservation.total_price.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Status badge */}
      <div style={{ marginBottom: 24 }}>
        <span className={`bk-status bk-status--${reservation.status}`}>
          {reservation.status}
        </span>
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
        <Link
          to={preserveQueryParams("/trips", location.search)}
          className="bk-btn bk-btn--primary bk-btn--lg"
        >
          View my trips
        </Link>
        <Link
          to={preserveQueryParams("/home", location.search)}
          className="bk-btn bk-btn--secondary bk-btn--lg"
        >
          Back to home
        </Link>
      </div>
    </div>
  );
}
