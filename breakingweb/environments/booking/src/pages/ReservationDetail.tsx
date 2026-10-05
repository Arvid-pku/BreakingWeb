import { useEffect, useState } from "react";
import { Link, useParams, useLocation, useNavigate } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import type { Reservation, PaymentMethod } from "../types";
import { useBookingLayout } from "../context";

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
  // Append T00:00 to avoid UTC midnight → previous-day-in-local-tz shift
  const d = new Date(dateStr + "T00:00");
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function ReservationDetail() {
  const { id } = useParams<{ id: string }>();
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();
  const navigate = useNavigate();

  const [reservation, setReservation] = useState<Reservation | null>(null);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelPreview, setCancelPreview] = useState<{
    fee_amount: number;
    total_price: number;
    days_until_checkin: number;
    policy_description: string;
    refundable: boolean;
    currency: string;
  } | null>(null);
  const [showModifyModal, setShowModifyModal] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [modifying, setModifying] = useState(false);
  const [modCheckIn, setModCheckIn] = useState("");
  const [modCheckOut, setModCheckOut] = useState("");
  const [modGuests, setModGuests] = useState(0);
  const [modSpecialRequests, setModSpecialRequests] = useState("");

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    Promise.all([
      api.getReservation(id).catch(() => null),
      api.listPaymentMethods().catch(() => ({ payment_methods: [] })),
    ]).then(([res, pmData]) => {
      if (cancelled) return;
      setReservation(res);
      setPaymentMethods(pmData.payment_methods ?? []);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [api, sessionId, id]);

  const openCancelModal = async () => {
    if (!reservation) return;
    setCancelPreview(null);
    setShowCancelModal(true);
    try {
      const preview = await api.previewCancelReservation(reservation.id);
      setCancelPreview(preview);
    } catch {
      notify("Error", "Could not compute cancellation fee.");
      setShowCancelModal(false);
    }
  };

  const handleCancel = async () => {
    if (!reservation || !cancelPreview) return;
    setCancelling(true);
    try {
      const updated = await api.cancelReservation(reservation.id, cancelPreview.fee_amount);
      setReservation(updated);
      notify(
        "Booking Cancelled",
        cancelPreview.fee_amount > 0
          ? `Cancelled with a fee of ${cancelPreview.currency === "USD" ? "$" : cancelPreview.currency + " "}${cancelPreview.fee_amount.toFixed(2)}.`
          : "Reservation has been cancelled with no fee.",
      );
    } catch {
      notify("Error", "Failed to cancel reservation.");
    }
    setCancelling(false);
    setShowCancelModal(false);
    setCancelPreview(null);
  };

  const openModifyModal = () => {
    if (!reservation) return;
    setModCheckIn(reservation.check_in);
    setModCheckOut(reservation.check_out);
    setModGuests(reservation.guests);
    setModSpecialRequests(reservation.guest_info?.special_requests || "");
    setShowModifyModal(true);
  };

  const handleApplyWallet = async () => {
    if (!reservation) return;
    try {
      const result = await api.applyWallet({ reservation_id: reservation.id });
      notify("Wallet Applied", result.message);
    } catch {
      notify("Failed", "Could not apply wallet credit.");
    }
  };

  const handleModify = async () => {
    if (!reservation) return;
    setModifying(true);
    try {
      const updated = await api.modifyReservation(reservation.id, {
        check_in: modCheckIn !== reservation.check_in ? modCheckIn : undefined,
        check_out: modCheckOut !== reservation.check_out ? modCheckOut : undefined,
        guests: modGuests !== reservation.guests ? modGuests : undefined,
        special_requests: modSpecialRequests !== (reservation.guest_info?.special_requests || "") ? modSpecialRequests : undefined,
      });
      setReservation(updated);
      notify("Booking Modified", "Your reservation has been updated successfully.");
    } catch {
      notify("Modification Failed", "Could not modify your reservation. Please try again.");
    }
    setModifying(false);
    setShowModifyModal(false);
  };

  if (loading) {
    return <div className="bk-loading">Loading reservation...</div>;
  }

  if (!reservation) {
    return (
      <div className="bk-empty">
        <h3>Reservation not found</h3>
        <p>The reservation you are looking for does not exist.</p>
        <Link
          to={preserveQueryParams("/trips", location.search)}
          className="bk-btn bk-btn--primary"
          style={{ marginTop: 16, display: "inline-flex" }}
        >
          Back to My Trips
        </Link>
      </div>
    );
  }

  const status = reservation.status.toLowerCase();
  const isCancellable = status === "confirmed" || status === "modified";
  const isCompleted = status === "completed";
  const canReview = isCompleted && !reservation.rating_submitted;
  const payment = paymentMethods.find((pm) => pm.id === reservation.payment_method_id);

  const subtotal = reservation.price_per_night * reservation.nights;
  const currencySymbol = reservation.currency === "USD" ? "$" : reservation.currency + " ";

  return (
    <div>
      {/* Back link */}
      <div style={{ marginBottom: 16 }}>
        <Link
          to={preserveQueryParams("/trips", location.search)}
          className="bk-btn bk-btn--ghost bk-btn--sm"
        >
          &larr; Back to My Trips
        </Link>
      </div>

      {/* Header: Confirmation + Status */}
      <div className="bk-card" style={{ padding: 24, marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--bk-gray-600)", marginBottom: 4 }}>
              Confirmation Number
            </div>
            <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: 1 }}>
              {reservation.confirmation_number}
            </div>
          </div>
          <span className={statusBadgeClass(reservation.status)} style={{ fontSize: 14, padding: "6px 14px" }}>
            {reservation.status}
          </span>
        </div>

        {reservation.is_genius_deal && (
          <span className="bk-badge bk-badge--genius">Genius Deal</span>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20 }}>
        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Property Info */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Property</h2>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>
              <Link
                to={preserveQueryParams(`/property/${reservation.property_id}`, location.search)}
              >
                {reservation.property_name}
              </Link>
            </div>
          </div>

          {/* Stay Details */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Stay Details</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 14 }}>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Room Type</div>
                <div style={{ fontWeight: 600 }}>{reservation.room_type_name}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Meals Included</div>
                <div style={{ fontWeight: 600 }}>{reservation.meals_included || "None"}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Check-in</div>
                <div style={{ fontWeight: 600 }}>{formatDate(reservation.check_in)}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Check-out</div>
                <div style={{ fontWeight: 600 }}>{formatDate(reservation.check_out)}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Nights</div>
                <div style={{ fontWeight: 600 }}>{reservation.nights}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Guests</div>
                <div style={{ fontWeight: 600 }}>{reservation.guests}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Rooms</div>
                <div style={{ fontWeight: 600 }}>{reservation.rooms}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Booked On</div>
                <div style={{ fontWeight: 600 }}>{formatDate(reservation.booked_at)}</div>
              </div>
            </div>
          </div>

          {/* Guest Info */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Guest Information</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 14 }}>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Full Name</div>
                <div style={{ fontWeight: 600 }}>{reservation.guest_info.full_name}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Email</div>
                <div style={{ fontWeight: 600 }}>{reservation.guest_info.email}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Phone</div>
                <div style={{ fontWeight: 600 }}>{reservation.guest_info.phone || "Not provided"}</div>
              </div>
              <div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Country</div>
                <div style={{ fontWeight: 600 }}>{reservation.guest_info.country || "Not provided"}</div>
              </div>
            </div>
            {reservation.guest_info.special_requests && (
              <div style={{ marginTop: 12 }}>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 12, marginBottom: 2 }}>Special Requests</div>
                <div style={{ fontSize: 14, fontStyle: "italic" }}>
                  {reservation.guest_info.special_requests}
                </div>
              </div>
            )}
          </div>

          {/* Payment Info */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Payment Information</h2>
            {payment ? (
              <div style={{ fontSize: 14 }}>
                <div style={{ fontWeight: 600 }}>
                  {payment.card_type} ending in {payment.last_four}
                </div>
                <div style={{ color: "var(--bk-gray-600)", fontSize: 13, marginTop: 4 }}>
                  {payment.holder_name} &middot; Expires {payment.expiry}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 14, color: "var(--bk-gray-600)" }}>
                Payment method on file
              </div>
            )}
          </div>

          {/* Cancellation Policy */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>Cancellation Policy</h2>
            <div style={{ fontSize: 14 }}>
              <div style={{ marginBottom: 8 }}>
                <span className="bk-badge bk-badge--blue" style={{ textTransform: "capitalize" }}>
                  {reservation.cancellation_policy.type}
                </span>
              </div>
              <p style={{ color: "var(--bk-gray-600)", marginBottom: 6 }}>
                {reservation.cancellation_policy.description}
              </p>
              {reservation.cancellation_policy.free_cancel_before_days > 0 && (
                <p style={{ fontSize: 13 }}>
                  Free cancellation up to{" "}
                  <strong>{reservation.cancellation_policy.free_cancel_before_days} days</strong>{" "}
                  before check-in.
                </p>
              )}
              {reservation.cancellation_policy.penalty_percentage > 0 && (
                <p style={{ fontSize: 13, color: "var(--bk-red)" }}>
                  Late cancellation penalty: {reservation.cancellation_policy.penalty_percentage}% of total.
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Right column: Price breakdown + Actions */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Price Breakdown */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Price Breakdown</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>
                  {currencySymbol}{reservation.price_per_night.toFixed(2)} x {reservation.nights}{" "}
                  {reservation.nights === 1 ? "night" : "nights"}
                </span>
                <span>{currencySymbol}{subtotal.toFixed(2)}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Taxes</span>
                <span>{currencySymbol}{reservation.taxes.toFixed(2)}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>City fee</span>
                <span>{currencySymbol}{reservation.city_fee.toFixed(2)}</span>
              </div>
              {reservation.resort_fee > 0 && (
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Resort fee</span>
                  <span>{currencySymbol}{reservation.resort_fee.toFixed(2)}</span>
                </div>
              )}
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Cleaning fee</span>
                <span>{currencySymbol}{reservation.cleaning_fee.toFixed(2)}</span>
              </div>
              {reservation.genius_discount > 0 && (
                <div style={{ display: "flex", justifyContent: "space-between", color: "var(--bk-green)" }}>
                  <span>Genius discount</span>
                  <span>-{currencySymbol}{reservation.genius_discount.toFixed(2)}</span>
                </div>
              )}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  borderTop: "2px solid var(--bk-border)",
                  paddingTop: 10,
                  marginTop: 4,
                  fontWeight: 700,
                  fontSize: 18,
                }}
              >
                <span>Total</span>
                <span>{currencySymbol}{reservation.total_price.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Actions</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {isCancellable && (
                <button
                  className="bk-btn bk-btn--danger bk-btn--block"
                  onClick={openCancelModal}
                >
                  Cancel Booking
                </button>
              )}
              {isCancellable && (
                <button
                  className="bk-btn bk-btn--secondary bk-btn--block"
                  onClick={openModifyModal}
                >
                  Modify Booking
                </button>
              )}
              {canReview && (
                <Link
                  to={preserveQueryParams(`/reviews?write=true&reservation=${reservation.id}&property=${reservation.property_id}`, location.search)}
                  className="bk-btn bk-btn--primary bk-btn--block"
                  style={{ textAlign: "center" }}
                >
                  Write a Review
                </Link>
              )}
              {status === "cancelled" && (
                <Link
                  to={preserveQueryParams(`/rebook/${reservation.id}`, location.search)}
                  className="bk-btn bk-btn--primary bk-btn--block"
                  style={{ textAlign: "center" }}
                  aria-label="See rebooking options"
                >
                  See Rebooking Options
                </Link>
              )}
              <Link
                to={preserveQueryParams(`/messages?property=${reservation.property_id}&reservation=${reservation.id}`, location.search)}
                className="bk-btn bk-btn--ghost bk-btn--block"
                style={{ textAlign: "center" }}
              >
                Contact Property
              </Link>
              <button
                className="bk-btn bk-btn--ghost bk-btn--block"
                onClick={handleApplyWallet}
              >
                Apply Wallet Credit
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Modify Modal */}
      {showModifyModal && reservation && (
        <div
          style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,.5)", display: "flex",
            alignItems: "center", justifyContent: "center", zIndex: 1000,
          }}
          onClick={() => setShowModifyModal(false)}
        >
          <div
            className="bk-card"
            style={{ padding: 28, maxWidth: 500, width: "100%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>
              Modify Reservation
            </h3>
            <p style={{ fontSize: 14, color: "var(--bk-gray-600)", marginBottom: 16 }}>
              {reservation.property_name} &mdash; {reservation.confirmation_number}
            </p>
            <div className="bk-form-group">
              <label>Check-in</label>
              <input type="date" className="bk-input" value={modCheckIn}
                onChange={(e) => setModCheckIn(e.target.value)} />
            </div>
            <div className="bk-form-group">
              <label>Check-out</label>
              <input type="date" className="bk-input" value={modCheckOut}
                onChange={(e) => setModCheckOut(e.target.value)} />
            </div>
            <div className="bk-form-group">
              <label>Guests</label>
              <select className="bk-select" value={modGuests}
                onChange={(e) => setModGuests(Number(e.target.value))}>
                {[1,2,3,4,5,6].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div className="bk-form-group">
              <label>Special Requests</label>
              <textarea className="bk-textarea" value={modSpecialRequests}
                onChange={(e) => setModSpecialRequests(e.target.value)}
                placeholder="e.g. Late check-out, high floor, extra pillows" />
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 20, justifyContent: "flex-end" }}>
              <button className="bk-btn bk-btn--secondary" onClick={() => setShowModifyModal(false)}
                disabled={modifying}>Cancel</button>
              <button className="bk-btn bk-btn--primary" onClick={handleModify}
                disabled={modifying}>{modifying ? "Saving..." : "Save Changes"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Confirmation Modal */}
      {showCancelModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={() => setShowCancelModal(false)}
        >
          <div
            className="bk-card"
            style={{ padding: 28, maxWidth: 460, width: "100%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: 20, fontWeight: 700, marginBottom: 12 }}>
              Cancel Reservation?
            </h3>
            <p style={{ fontSize: 14, color: "var(--bk-gray-600)", marginBottom: 8 }}>
              Are you sure you want to cancel your reservation at{" "}
              <strong>{reservation.property_name}</strong>?
            </p>
            <p style={{ fontSize: 14, marginBottom: 4 }}>
              <strong>Confirmation:</strong> {reservation.confirmation_number}
            </p>
            <p style={{ fontSize: 14, marginBottom: 4 }}>
              <strong>Dates:</strong> {formatDate(reservation.check_in)} &rarr;{" "}
              {formatDate(reservation.check_out)}
            </p>
            {cancelPreview === null ? (
              <div className="bk-info-box" style={{ marginTop: 12 }}>
                Computing cancellation fee...
              </div>
            ) : cancelPreview.fee_amount > 0 ? (
              <div
                className="bk-info-box"
                style={{
                  marginTop: 12,
                  background: "#fff5f5",
                  border: "1px solid #fca5a5",
                }}
                aria-label={`Cancellation fee ${cancelPreview.fee_amount} ${cancelPreview.currency}`}
              >
                <div style={{ fontWeight: 700, fontSize: 15 }}>
                  Cancellation fee: {cancelPreview.currency === "USD" ? "$" : cancelPreview.currency + " "}
                  {cancelPreview.fee_amount.toFixed(2)}
                </div>
                <div style={{ fontSize: 13, color: "var(--bk-gray-600)", marginTop: 4 }}>
                  Policy: {cancelPreview.policy_description}
                  <br />
                  {cancelPreview.days_until_checkin} day(s) until check-in &middot;{" "}
                  Total paid: {cancelPreview.currency === "USD" ? "$" : cancelPreview.currency + " "}
                  {cancelPreview.total_price.toFixed(2)}
                </div>
              </div>
            ) : (
              <div
                className="bk-info-box"
                style={{ marginTop: 12, background: "#f0fdf4", border: "1px solid #86efac" }}
                aria-label="Free cancellation"
              >
                <div style={{ fontWeight: 700, fontSize: 15 }}>Free cancellation — no fee</div>
                <div style={{ fontSize: 13, color: "var(--bk-gray-600)", marginTop: 4 }}>
                  {cancelPreview.policy_description}
                </div>
              </div>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 20, justifyContent: "flex-end" }}>
              <button
                className="bk-btn bk-btn--secondary"
                onClick={() => setShowCancelModal(false)}
                disabled={cancelling}
              >
                Keep Reservation
              </button>
              <button
                className="bk-btn bk-btn--danger"
                onClick={handleCancel}
                disabled={cancelling || cancelPreview === null}
                aria-label={
                  cancelPreview && cancelPreview.fee_amount > 0
                    ? `Confirm cancellation with ${cancelPreview.fee_amount} ${cancelPreview.currency} fee`
                    : "Confirm cancellation"
                }
              >
                {cancelling ? "Cancelling..." : "Confirm Cancellation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
