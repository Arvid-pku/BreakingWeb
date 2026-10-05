import { useEffect, useState, useMemo } from "react";
import { useParams, useNavigate, useLocation, Link } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import type { Property, RoomType, PaymentMethod } from "../types";
import { useBookingLayout } from "../context";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function formatCurrency(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function nightsBetween(checkIn: string, checkOut: string): number {
  const a = new Date(checkIn);
  const b = new Date(checkOut);
  const diff = b.getTime() - a.getTime();
  return Math.max(1, Math.round(diff / (1000 * 60 * 60 * 24)));
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

const COUNTRIES = [
  "United States", "United Kingdom", "Canada", "Australia", "Germany",
  "France", "Spain", "Italy", "Netherlands", "Japan", "China",
  "South Korea", "India", "Brazil", "Mexico", "Argentina", "Switzerland",
  "Austria", "Belgium", "Sweden", "Norway", "Denmark", "Finland",
  "Portugal", "Ireland", "New Zealand", "Singapore", "Thailand",
  "Turkey", "United Arab Emirates", "South Africa", "Other",
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function BookingForm() {
  const { propertyId, roomId } = useParams<{ propertyId: string; roomId: string }>();
  const { sessionId, api, notify } = useBookingLayout();
  const navigate = useNavigate();
  const location = useLocation();

  // URL search params
  const searchParams = new URLSearchParams(location.search);
  const checkIn = searchParams.get("check_in") || "";
  const checkOut = searchParams.get("check_out") || "";
  const guestsParam = searchParams.get("guests") || "2";
  const roomsParam = searchParams.get("rooms") || "1";
  const numGuests = Number(guestsParam) || 2;
  const numRooms = Number(roomsParam) || 1;

  // State
  const [property, setProperty] = useState<Property | null>(null);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Form fields — pre-filled from account once loaded
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [country, setCountry] = useState("United States");
  const [specialRequests, setSpecialRequests] = useState("");
  const [accountLoaded, setAccountLoaded] = useState(false);
  const [selectedPaymentId, setSelectedPaymentId] = useState("");

  // Fetch data
  useEffect(() => {
    if (!propertyId) return;
    let cancelled = false;
    setLoading(true);

    Promise.all([
      api.getProperty(propertyId),
      api.listPaymentMethods().catch(() => ({ payment_methods: [] as PaymentMethod[] })),
      api.getAccount().catch(() => null),
    ])
      .then(([prop, pmResult, acct]) => {
        if (cancelled) return;
        setProperty(prop);
        const pms = pmResult.payment_methods;
        setPaymentMethods(pms);

        // Pre-select default payment method
        const defaultPm = pms.find((pm) => pm.is_default);
        if (defaultPm) {
          setSelectedPaymentId(defaultPm.id);
        } else if (pms.length > 0) {
          setSelectedPaymentId(pms[0].id);
        }

        // Pre-fill guest details from account
        if (acct && !accountLoaded) {
          setFullName(acct.name || "");
          setEmail(acct.email || "");
          setPhone(acct.phone || "");
          setCountry(acct.nationality || "United States");
          setAccountLoaded(true);
        }

        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          notify("Error", "Failed to load booking details.");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [api, propertyId, sessionId, notify]);

  // Derived data
  const room: RoomType | undefined = useMemo(
    () => property?.room_types.find((rt) => rt.id === roomId),
    [property, roomId],
  );

  const nights = useMemo(
    () => (checkIn && checkOut ? nightsBetween(checkIn, checkOut) : 1),
    [checkIn, checkOut],
  );

  const subtotal = room ? room.price_per_night * nights * numRooms : 0;
  const [feeBreakdown, setFeeBreakdown] = useState<{
    taxes: number;
    city_fee: number;
    resort_fee: number;
    cleaning_fee: number;
    total_fees: number;
    total_with_fees: number;
  } | null>(null);

  useEffect(() => {
    if (!room || !propertyId || nights <= 0) return;
    let ignore = false;
    api
      .pricePreview({
        property_id: propertyId,
        room_type_id: room.id,
        nights,
        rooms: numRooms,
      })
      .then((p) => {
        if (!ignore) setFeeBreakdown(p);
      })
      .catch(() => {
        if (!ignore) setFeeBreakdown(null);
      });
    return () => {
      ignore = true;
    };
  }, [api, propertyId, room, nights, numRooms]);

  const taxesAndFees = feeBreakdown?.total_fees ?? 0;
  const geniusDiscount =
    property?.is_genius_property && property.genius_discount_pct > 0
      ? Math.round(subtotal * (property.genius_discount_pct / 100) * 100) / 100
      : 0;
  const totalPrice = subtotal + taxesAndFees - geniusDiscount;
  const currency = property?.currency || "USD";

  /* ---- Submit handler ---- */

  const handleSubmit = async () => {
    if (!property || !room) return;

    if (!fullName.trim()) {
      notify("Missing information", "Please enter your full name.");
      return;
    }
    if (!email.trim()) {
      notify("Missing information", "Please enter your email address.");
      return;
    }
    if (!selectedPaymentId) {
      notify("Missing information", "Please select a payment method.");
      return;
    }

    setSubmitting(true);
    try {
      const reservation = await api.createReservation({
        property_id: property.id,
        room_type_id: room.id,
        check_in: checkIn,
        check_out: checkOut,
        guests: numGuests,
        rooms: numRooms,
        payment_method_id: selectedPaymentId,
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        country: country || undefined,
        special_requests: specialRequests.trim() || undefined,
        meals_included: room.meals_included || undefined,
      });

      notify("Booking confirmed!", `Confirmation number: ${reservation.confirmation_number}`);
      navigate(
        preserveQueryParams(`/confirmation/${reservation.id}`, location.search),
      );
    } catch {
      notify("Booking failed", "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  /* ---- Render ---- */

  if (loading) {
    return <div className="bk-loading">Loading booking details...</div>;
  }

  if (!property || !room) {
    return (
      <div className="bk-empty">
        <h3>Room not found</h3>
        <p>The selected room or property could not be found.</p>
        <Link
          to={preserveQueryParams(propertyId ? `/property/${propertyId}` : "/search", location.search)}
          className="bk-btn bk-btn--primary"
          style={{ marginTop: 16 }}
        >
          Go back
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
      {/* ============================================================ */}
      {/*  Main form area                                              */}
      {/* ============================================================ */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Back link */}
        <Link
          to={preserveQueryParams(`/property/${property.id}`, location.search)}
          style={{ fontSize: 13, display: "inline-block", marginBottom: 16 }}
        >
          &larr; Back to property
        </Link>

        <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 20 }}>
          Complete your booking
        </h1>

        {/* Genius banner */}
        {geniusDiscount > 0 && (
          <div className="bk-genius-banner" style={{ marginBottom: 20 }}>
            <h3>Genius discount applied</h3>
            <p>
              You are saving {formatCurrency(geniusDiscount, currency)} with your Genius
              membership ({property.genius_discount_pct}% off).
            </p>
          </div>
        )}

        {/* ---------------------------------------------------------- */}
        {/*  Guest details                                             */}
        {/* ---------------------------------------------------------- */}
        <div className="bk-card" style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
            Your details
          </h2>

          <div className="bk-grid bk-grid--2" style={{ gap: 16 }}>
            <div className="bk-form-group">
              <label htmlFor="guest-name">Full name *</label>
              <input
                id="guest-name"
                type="text"
                className="bk-input"
                placeholder="John Smith"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>

            <div className="bk-form-group">
              <label htmlFor="guest-email">Email address *</label>
              <input
                id="guest-email"
                type="email"
                className="bk-input"
                placeholder="john@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <span style={{ fontSize: 11, color: "var(--bk-gray-300)" }}>
                Confirmation email will be sent to this address
              </span>
            </div>

            <div className="bk-form-group">
              <label htmlFor="guest-phone">Phone number</label>
              <input
                id="guest-phone"
                type="tel"
                className="bk-input"
                placeholder="+1 234 567 8900"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
              <span style={{ fontSize: 11, color: "var(--bk-gray-300)" }}>
                Needed by the property to coordinate your arrival
              </span>
            </div>

            <div className="bk-form-group">
              <label htmlFor="guest-country">Country / Region</label>
              <select
                id="guest-country"
                className="bk-select"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
              >
                {COUNTRIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="bk-form-group" style={{ marginTop: 8 }}>
            <label htmlFor="guest-requests">Special requests</label>
            <textarea
              id="guest-requests"
              className="bk-textarea"
              placeholder="Any special requests for the property? (optional)"
              value={specialRequests}
              onChange={(e) => setSpecialRequests(e.target.value)}
              rows={3}
            />
            <span style={{ fontSize: 11, color: "var(--bk-gray-300)" }}>
              Special requests cannot be guaranteed, but the property will do its best to meet your needs.
            </span>
          </div>
        </div>

        {/* ---------------------------------------------------------- */}
        {/*  Payment method                                            */}
        {/* ---------------------------------------------------------- */}
        <div className="bk-card" style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
            Payment method
          </h2>

          {paymentMethods.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {paymentMethods.map((pm) => (
                <label
                  key={pm.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "12px 16px",
                    border: `2px solid ${selectedPaymentId === pm.id ? "var(--bk-blue-light)" : "var(--bk-border)"}`,
                    borderRadius: "var(--bk-radius-lg)",
                    cursor: "pointer",
                    background:
                      selectedPaymentId === pm.id ? "#e3f2fd" : "var(--bk-white)",
                    transition: "border-color 0.15s, background 0.15s",
                  }}
                >
                  <input
                    type="radio"
                    name="payment"
                    value={pm.id}
                    checked={selectedPaymentId === pm.id}
                    onChange={() => setSelectedPaymentId(pm.id)}
                    style={{ accentColor: "var(--bk-blue-light)" }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>
                      {pm.card_type} ending in {pm.last_four}
                      {pm.is_default && (
                        <span className="bk-badge bk-badge--blue" style={{ marginLeft: 8 }}>
                          Default
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--bk-gray-600)" }}>
                      {pm.holder_name} &middot; Expires {pm.expiry}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          ) : (
            <div className="bk-info-box">
              No saved payment methods found. Please add a payment method in your{" "}
              <Link to={preserveQueryParams("/settings", location.search)}>account settings</Link>{" "}
              before booking.
            </div>
          )}
        </div>

        {/* ---------------------------------------------------------- */}
        {/*  Cancellation policy                                       */}
        {/* ---------------------------------------------------------- */}
        <div className="bk-card" style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}>
            Cancellation policy
          </h2>
          {room.cancellation_policy.type === "free_cancellation" ? (
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <span style={{ color: "var(--bk-green)", fontSize: 18 }}>✓</span>
              <div>
                <p style={{ fontWeight: 600, color: "var(--bk-green)" }}>Free cancellation</p>
                <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                  {room.cancellation_policy.description ||
                    `Free cancellation up to ${room.cancellation_policy.free_cancel_before_days} day${room.cancellation_policy.free_cancel_before_days !== 1 ? "s" : ""} before check-in.`}
                </p>
              </div>
            </div>
          ) : (
            <div>
              <p style={{ fontWeight: 600, fontSize: 14 }}>
                {room.cancellation_policy.type === "non_refundable"
                  ? "Non-refundable"
                  : "Partial refund available"}
              </p>
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)", marginTop: 4 }}>
                {room.cancellation_policy.description}
              </p>
              {room.cancellation_policy.penalty_percentage > 0 && (
                <p style={{ fontSize: 12, color: "var(--bk-red)", marginTop: 4 }}>
                  Cancellation fee: {room.cancellation_policy.penalty_percentage}% of the total price
                </p>
              )}
            </div>
          )}
        </div>

        {/* ---------------------------------------------------------- */}
        {/*  Price summary (mobile-friendly, also in sidebar)          */}
        {/* ---------------------------------------------------------- */}
        <div className="bk-card" style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
            Price summary
          </h2>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
              <span>
                {formatCurrency(room.price_per_night, currency)} x {nights} night{nights !== 1 ? "s" : ""}
                {numRooms > 1 ? ` x ${numRooms} rooms` : ""}
              </span>
              <span>{formatCurrency(subtotal, currency)}</span>
            </div>

            {feeBreakdown && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                  <span>Taxes</span>
                  <span>{formatCurrency(feeBreakdown.taxes, currency)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                  <span>City fee</span>
                  <span>{formatCurrency(feeBreakdown.city_fee, currency)}</span>
                </div>
                {feeBreakdown.resort_fee > 0 && (
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                    <span>Resort fee</span>
                    <span>{formatCurrency(feeBreakdown.resort_fee, currency)}</span>
                  </div>
                )}
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                  <span>Cleaning fee</span>
                  <span>{formatCurrency(feeBreakdown.cleaning_fee, currency)}</span>
                </div>
              </>
            )}

            {geniusDiscount > 0 && (
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 14,
                  color: "var(--bk-green)",
                }}
              >
                <span>
                  Genius discount ({property.genius_discount_pct}%)
                </span>
                <span>-{formatCurrency(geniusDiscount, currency)}</span>
              </div>
            )}

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontWeight: 700,
                fontSize: 18,
                borderTop: "2px solid var(--bk-border)",
                paddingTop: 12,
                marginTop: 8,
              }}
            >
              <span>Total</span>
              <span>{formatCurrency(totalPrice, currency)}</span>
            </div>
          </div>
        </div>

        {/* ---------------------------------------------------------- */}
        {/*  Complete booking button                                   */}
        {/* ---------------------------------------------------------- */}
        <button
          type="button"
          className="bk-btn bk-btn--primary bk-btn--lg bk-btn--block"
          onClick={handleSubmit}
          disabled={submitting}
          style={{ marginBottom: 40, position: "relative", zIndex: 1 }}
        >
          {submitting ? "Processing..." : "Complete Booking"}
        </button>

        <p style={{ fontSize: 12, color: "var(--bk-gray-300)", textAlign: "center", marginBottom: 20 }}>
          By completing this booking you agree to the{" "}
          <span style={{ color: "var(--bk-blue-light)" }}>booking conditions</span>,{" "}
          <span style={{ color: "var(--bk-blue-light)" }}>general terms</span>, and{" "}
          <span style={{ color: "var(--bk-blue-light)" }}>privacy policy</span>.
        </p>
      </div>

      {/* ============================================================ */}
      {/*  Sidebar: Booking summary                                    */}
      {/* ============================================================ */}
      <aside
        style={{
          width: 340,
          flexShrink: 0,
          position: "sticky",
          top: 100,
        }}
      >
        <div className="bk-card" style={{ padding: 20 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>
            Your booking summary
          </h3>

          {/* Property name */}
          <Link
            to={preserveQueryParams(`/property/${property.id}`, location.search)}
            style={{ fontWeight: 600, fontSize: 15, display: "block", marginBottom: 4 }}
          >
            {property.name}
          </Link>
          <div style={{ fontSize: 12, color: "var(--bk-gray-600)", marginBottom: 12 }}>
            {property.address}, {property.city}
          </div>

          {/* Review score */}
          <div className="bk-score" style={{ marginBottom: 16 }}>
            <span className="bk-score-badge">{property.review_score.toFixed(1)}</span>
            <span className="bk-score-label">{property.review_score_label}</span>
            <span className="bk-score-count">
              ({property.review_count.toLocaleString()} reviews)
            </span>
          </div>

          <div
            style={{
              borderTop: "1px solid var(--bk-border)",
              paddingTop: 12,
              marginBottom: 12,
            }}
          >
            {/* Room type */}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
              <span style={{ fontWeight: 600 }}>Room</span>
              <span>{room.name}</span>
            </div>

            {/* Bed type */}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
              <span style={{ fontWeight: 600 }}>Bed</span>
              <span>
                {room.bed_count} {room.bed_type}
              </span>
            </div>

            {/* Dates */}
            {checkIn && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
                <span style={{ fontWeight: 600 }}>Check-in</span>
                <span>{formatDate(checkIn)}</span>
              </div>
            )}
            {checkOut && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
                <span style={{ fontWeight: 600 }}>Check-out</span>
                <span>{formatDate(checkOut)}</span>
              </div>
            )}

            {/* Duration */}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
              <span style={{ fontWeight: 600 }}>Duration</span>
              <span>
                {nights} night{nights !== 1 ? "s" : ""}
              </span>
            </div>

            {/* Guests */}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
              <span style={{ fontWeight: 600 }}>Guests</span>
              <span>{numGuests}</span>
            </div>

            {/* Rooms */}
            {numRooms > 1 && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
                <span style={{ fontWeight: 600 }}>Rooms</span>
                <span>{numRooms}</span>
              </div>
            )}

            {/* Meals */}
            {room.meals_included && room.meals_included !== "none" && (
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 8 }}>
                <span style={{ fontWeight: 600 }}>Meals</span>
                <span className="bk-badge bk-badge--green" style={{ fontSize: 11 }}>
                  {room.meals_included.charAt(0).toUpperCase() + room.meals_included.slice(1)} included
                </span>
              </div>
            )}
          </div>

          {/* Price breakdown in sidebar */}
          <div
            style={{
              borderTop: "1px solid var(--bk-border)",
              paddingTop: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
              <span>Subtotal</span>
              <span>{formatCurrency(subtotal, currency)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
              <span>Taxes &amp; fees</span>
              <span>{formatCurrency(taxesAndFees, currency)}</span>
            </div>
            {geniusDiscount > 0 && (
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 13,
                  color: "var(--bk-green)",
                  marginBottom: 4,
                }}
              >
                <span>Genius discount</span>
                <span>-{formatCurrency(geniusDiscount, currency)}</span>
              </div>
            )}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontWeight: 700,
                fontSize: 18,
                borderTop: "1px solid var(--bk-border)",
                paddingTop: 8,
                marginTop: 8,
              }}
            >
              <span>Total</span>
              <span style={{ color: "var(--bk-gray-800)" }}>
                {formatCurrency(totalPrice, currency)}
              </span>
            </div>
            <div style={{ fontSize: 11, color: "var(--bk-gray-300)", textAlign: "right", marginTop: 2 }}>
              Includes taxes and fees
            </div>
          </div>
        </div>

        {/* Cancellation info in sidebar */}
        {room.cancellation_policy.type === "free_cancellation" && (
          <div
            className="bk-info-box bk-info-box--blue"
            style={{ marginTop: 12 }}
          >
            <strong style={{ color: "var(--bk-green)" }}>Free cancellation</strong>
            <p style={{ fontSize: 12, marginTop: 2 }}>
              {room.cancellation_policy.description ||
                `Cancel free of charge up to ${room.cancellation_policy.free_cancel_before_days} days before check-in.`}
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}
