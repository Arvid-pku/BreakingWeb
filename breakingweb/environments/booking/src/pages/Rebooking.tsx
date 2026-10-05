import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { RebookingSuggestion } from "../types";
import { useBookingLayout } from "../context";

/** Page shown at /rebook/:reservationId. Lists the 3 system-generated
 *  alternatives for a cancelled reservation with full fee breakdown so the
 *  agent can pick the one that fits their budget. */
export default function Rebooking() {
  const { api, notify } = useBookingLayout();
  const location = useLocation();
  const { reservationId } = useParams<{ reservationId: string }>();

  const [suggestion, setSuggestion] = useState<RebookingSuggestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reservationId) return;
    let cancelled = false;
    api
      .getRebookingByReservation(reservationId)
      .then((s) => {
        if (!cancelled) {
          setSuggestion(s);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("No rebooking suggestion found for this reservation.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, reservationId]);

  const fmtMoney = (x: number, currency: string) =>
    `${currency === "USD" ? "$" : currency + " "}${x.toFixed(2)}`;

  if (loading) return <div className="bk-loading">Loading rebooking options...</div>;
  if (error || !suggestion) {
    return (
      <div className="bk-empty">
        <h3>No rebooking suggestions</h3>
        <p>{error || "This reservation does not have any generated alternatives yet."}</p>
        <Link
          className="bk-btn bk-btn--secondary"
          to={preserveQueryParams("/trips", location.search)}
        >
          Back to trips
        </Link>
      </div>
    );
  }

  return (
    <div>
      <h1 className="bk-section-title">Rebooking Options</h1>
      <div
        className="bk-card"
        style={{ padding: 16, marginBottom: 20, background: "#f0f9ff" }}
      >
        <strong>Looking for a replacement in {suggestion.city}?</strong>
        <div style={{ fontSize: 13, color: "var(--bk-gray-600)", marginTop: 4 }}>
          {suggestion.check_in} → {suggestion.check_out} &middot; {suggestion.guests} guest(s)
        </div>
        <div style={{ fontSize: 12, color: "var(--bk-gray-500)", marginTop: 6 }}>
          Alternatives are selected from the same city as your cancelled stay. Review
          the itemized fee breakdown below — the total with fees is what you'll pay.
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {suggestion.candidates.map((c) => {
          const perNightWithFees = (c.total_with_fees / c.nights).toFixed(2);
          return (
            <div
              key={c.property_id}
              className="bk-card"
              style={{ padding: 16 }}
              aria-label={`Rebooking candidate ${c.property_name}`}
              data-property-id={c.property_id}
              data-total-with-fees={c.total_with_fees}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
                    {c.property_name}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                    {c.star_rating}-star &middot; {c.review_score}/10 &middot;{" "}
                    {c.room_type_name}
                  </div>
                  <div style={{ marginTop: 10, fontSize: 13 }}>
                    <div>Base ({c.nights} nights × {fmtMoney(c.price_per_night, c.currency)}): {fmtMoney(c.base_total, c.currency)}</div>
                    <div>Taxes: {fmtMoney(c.taxes, c.currency)}</div>
                    <div>City fee: {fmtMoney(c.city_fee, c.currency)}</div>
                    {c.resort_fee > 0 && (
                      <div>Resort fee: {fmtMoney(c.resort_fee, c.currency)}</div>
                    )}
                    <div>Cleaning fee: {fmtMoney(c.cleaning_fee, c.currency)}</div>
                    <div style={{ fontWeight: 700, marginTop: 4 }}>
                      Total with fees: {fmtMoney(c.total_with_fees, c.currency)}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--bk-gray-500)" }}>
                      (≈ {fmtMoney(Number(perNightWithFees), c.currency)}/night all-in)
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginLeft: 16 }}>
                  <Link
                    className="bk-btn bk-btn--primary"
                    to={preserveQueryParams(
                      `/book/${c.property_id}/${c.room_type_id}?check_in=${suggestion.check_in}&check_out=${suggestion.check_out}&guests=${suggestion.guests}`,
                      location.search,
                    )}
                    aria-label={`Book ${c.property_name}`}
                  >
                    Book this
                  </Link>
                  <Link
                    className="bk-btn bk-btn--ghost bk-btn--sm"
                    to={preserveQueryParams(`/property/${c.property_id}`, location.search)}
                  >
                    View details
                  </Link>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 16, textAlign: "right" }}>
        <Link
          className="bk-btn bk-btn--secondary bk-btn--sm"
          to={preserveQueryParams("/trips", location.search)}
        >
          Back to trips
        </Link>
      </div>
    </div>
  );
}
