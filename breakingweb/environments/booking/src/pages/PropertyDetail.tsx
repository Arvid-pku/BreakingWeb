import { useEffect, useState } from "react";
import { useParams, useNavigate, useLocation, Link } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import type { Property, RoomType, Review, SavedList } from "../types";
import { useBookingLayout } from "../context";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function Stars({ count }: { count: number }) {
  return (
    <span className="bk-stars" aria-label={`${count} stars`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} style={{ opacity: i < count ? 1 : 0.25 }}>
          ★
        </span>
      ))}
    </span>
  );
}

function ScoreBadge({ score }: { score: number }) {
  return (
    <span className="bk-score-badge" style={{ fontSize: 16, padding: "6px 10px" }}>
      {score.toFixed(1)}
    </span>
  );
}

function facilityIcon(_name: string): string {
  return "✓";
}

const REVIEW_CATEGORIES: { key: keyof NonNullable<Property["review_breakdown"]>; label: string }[] = [
  { key: "staff", label: "Staff" },
  { key: "facilities", label: "Facilities" },
  { key: "cleanliness", label: "Cleanliness" },
  { key: "comfort", label: "Comfort" },
  { key: "value_for_money", label: "Value for money" },
  { key: "location", label: "Location" },
  { key: "free_wifi", label: "Free WiFi" },
];

function formatCurrency(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function PropertyDetail() {
  const { id } = useParams<{ id: string }>();
  const { sessionId, api, notify } = useBookingLayout();
  const navigate = useNavigate();
  const location = useLocation();

  const [property, setProperty] = useState<Property | null>(null);
  const [loading, setLoading] = useState(true);
  const [roomQuantities, setRoomQuantities] = useState<Record<string, number>>({});
  const [savedLists, setSavedLists] = useState<SavedList[]>([]);
  const [saveDropdownOpen, setSaveDropdownOpen] = useState(false);

  // Parse search params for date/guest context
  const searchParams = new URLSearchParams(location.search);
  const [checkIn, setCheckIn] = useState(searchParams.get("check_in") || "");
  const [checkOut, setCheckOut] = useState(searchParams.get("check_out") || "");
  const [guests, setGuests] = useState(searchParams.get("guests") || "2");
  const rooms = searchParams.get("rooms") || "1";

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);

    api
      .getProperty(id)
      .then((prop) => {
        if (cancelled) return;
        setProperty(prop);
        // Initialise room quantities to 0
        const q: Record<string, number> = {};
        prop.room_types.forEach((rt) => {
          q[rt.id] = 0;
        });
        setRoomQuantities(q);
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          notify("Error", "Failed to load property details.");
          setLoading(false);
        }
      });

    // Also load saved lists for the "Save to list" dropdown
    api.listSavedLists().then((res) => {
      if (!cancelled) setSavedLists(res.lists ?? []);
    }).catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [api, id, sessionId, notify]);

  /* ---- handlers ---- */

  const handleRoomQtyChange = (roomId: string, qty: number) => {
    setRoomQuantities((prev) => ({ ...prev, [roomId]: qty }));
  };

  const handleReserve = (room: RoomType) => {
    const qty = roomQuantities[room.id] ?? 0;
    if (qty < 1) {
      notify("Please select at least 1 room");
      return;
    }
    const params = new URLSearchParams();
    if (checkIn) params.set("check_in", checkIn);
    if (checkOut) params.set("check_out", checkOut);
    params.set("guests", guests);
    params.set("rooms", String(qty));
    navigate(
      preserveQueryParams(
        `/book/${property!.id}/${room.id}?${params.toString()}`,
        location.search,
      ),
    );
  };

  /* ---- render ---- */

  if (loading) {
    return <div className="bk-loading">Loading property details...</div>;
  }

  if (!property) {
    return (
      <div className="bk-empty">
        <h3>Property not found</h3>
        <p>The property you are looking for does not exist or has been removed.</p>
        <Link to={preserveQueryParams("/search", location.search)} className="bk-btn bk-btn--primary" style={{ marginTop: 16 }}>
          Back to search
        </Link>
      </div>
    );
  }

  const reviews: Review[] = property.reviews ?? [];

  return (
    <div>
      {/* ============================================================ */}
      {/*  1. Property Header                                          */}
      {/* ============================================================ */}
      <section className="bk-section">
        <div className="bk-property-header" style={{ position: "relative" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <Stars count={property.star_rating} />
              {property.is_genius_property && (
                <span className="bk-genius-badge">Genius</span>
              )}
              {property.sustainability_badge && (
                <span className="bk-badge bk-badge--green">Travel Sustainable</span>
              )}
            </div>
            <h1 className="bk-property-title">{property.name}</h1>
            <p style={{ color: "var(--bk-gray-600)", fontSize: 13, marginTop: 4 }}>
              {property.address}, {property.city}, {property.country}
              <span style={{ marginLeft: 12, color: "var(--bk-blue-light)" }}>
                {property.distance_from_center_km} km from center
              </span>
            </p>
          </div>

          {/* 2. Review score + Save to list */}
          <div style={{ textAlign: "right", flexShrink: 0 }}>
            <div className="bk-score" style={{ justifyContent: "flex-end", marginBottom: 4 }}>
              <div>
                <span className="bk-score-label">{property.review_score_label}</span>
                <br />
                <span className="bk-score-count">
                  {property.review_count.toLocaleString()} review{property.review_count !== 1 ? "s" : ""}
                </span>
              </div>
              <ScoreBadge score={property.review_score} />
            </div>
            <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", alignItems: "center", marginTop: 4 }}>
              <a
                href="#reviews"
                style={{ fontSize: 13, color: "var(--bk-blue-light)", cursor: "pointer" }}
              >
                See all reviews
              </a>
              <button
                className="bk-btn bk-btn--secondary"
                style={{ fontSize: 13, padding: "4px 12px" }}
                onClick={() => setSaveDropdownOpen(!saveDropdownOpen)}
              >
                ♥ Save to list
              </button>
            </div>
            {saveDropdownOpen && (
              <div
                style={{
                  position: "absolute",
                  right: 0,
                  top: "100%",
                  marginTop: 4,
                  background: "#fff",
                  border: "1px solid var(--bk-gray-200)",
                  borderRadius: 8,
                  boxShadow: "0 4px 12px rgba(0,0,0,.12)",
                  padding: 12,
                  minWidth: 220,
                  zIndex: 100,
                  textAlign: "left",
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>Save to a list</div>
                {savedLists.length === 0 && (
                  <p style={{ fontSize: 13, color: "var(--bk-gray-400)" }}>No lists yet. Create one below.</p>
                )}
                {savedLists.map((list) => {
                  const alreadySaved = list.property_ids.includes(property.id);
                  return (
                    <button
                      key={list.id}
                      className="bk-btn bk-btn--tertiary"
                      style={{
                        display: "block",
                        width: "100%",
                        textAlign: "left",
                        padding: "6px 8px",
                        fontSize: 13,
                        color: alreadySaved ? "var(--bk-gray-400)" : undefined,
                      }}
                      disabled={alreadySaved}
                      onClick={async () => {
                        await api.addToSavedList(list.id, property.id);
                        setSavedLists((prev) =>
                          prev.map((l) =>
                            l.id === list.id
                              ? { ...l, property_ids: [...l.property_ids, property.id] }
                              : l
                          )
                        );
                        setSaveDropdownOpen(false);
                        notify(`Saved to "${list.name}"`, property.name);
                      }}
                    >
                      {list.name} {alreadySaved ? "(saved)" : ""}
                    </button>
                  );
                })}
                <hr style={{ margin: "8px 0", border: "none", borderTop: "1px solid var(--bk-gray-200)" }} />
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const input = (e.target as HTMLFormElement).elements.namedItem("newListName") as HTMLInputElement;
                    const name = input.value.trim();
                    if (!name) return;
                    const created = await api.createSavedList(name);
                    // Add the property to the newly created list
                    const updated = await api.addToSavedList(created.id, property.id);
                    setSavedLists((prev) => [...prev, updated]);
                    input.value = "";
                    setSaveDropdownOpen(false);
                    notify(`Saved to "${name}"`, property.name);
                  }}
                  style={{ display: "flex", gap: 6 }}
                >
                  <input
                    name="newListName"
                    type="text"
                    placeholder="New list name"
                    className="bk-input"
                    style={{ flex: 1, fontSize: 13, padding: "4px 8px" }}
                  />
                  <button type="submit" className="bk-btn bk-btn--primary" style={{ fontSize: 12, padding: "4px 10px" }}>
                    Create &amp; save
                  </button>
                </form>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  3. Short description                                        */}
      {/* ============================================================ */}
      <section className="bk-section">
        <p style={{ fontSize: 15, lineHeight: 1.7 }}>{property.short_description}</p>
      </section>

      {/* ============================================================ */}
      {/*  4. Popular facilities                                       */}
      {/* ============================================================ */}
      {property.popular_facilities.length > 0 && (
        <section className="bk-section">
          <h2 className="bk-section-title">Most popular facilities</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {property.popular_facilities.map((f) => (
              <span key={f} className="bk-facility-tag">
                <span>{facilityIcon(f)}</span> {f}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* ============================================================ */}
      {/*  10. Genius banner                                           */}
      {/* ============================================================ */}
      {property.is_genius_property && property.genius_discount_pct > 0 && (
        <div className="bk-genius-banner">
          <h3>Genius discount</h3>
          <p>
            You are getting a reduced rate because this property is offering a Genius discount.
            Save {property.genius_discount_pct}% on your stay with your Genius membership.
          </p>
        </div>
      )}

      {/* ============================================================ */}
      {/*  5. Room availability table                                  */}
      {/* ============================================================ */}
      <section className="bk-section" id="rooms">
        <h2 className="bk-section-title">Availability</h2>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 16 }}>
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 2 }}>Check-in</label>
            <input type="date" className="bk-input" value={checkIn}
              onChange={(e) => setCheckIn(e.target.value)} style={{ width: 150 }} />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 2 }}>Check-out</label>
            <input type="date" className="bk-input" value={checkOut}
              onChange={(e) => setCheckOut(e.target.value)} style={{ width: 150 }} />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 2 }}>Guests</label>
            <select className="bk-input" value={guests}
              onChange={(e) => setGuests(e.target.value)} style={{ width: 80 }}>
              {[1,2,3,4,5,6,7,8].map((n) => (
                <option key={n} value={String(n)}>{n}</option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ overflowX: "auto" }}>
          <table className="bk-room-table">
            <thead>
              <tr>
                <th>Room Type</th>
                <th>Sleeps</th>
                <th>Price per night</th>
                <th>Your choices</th>
                <th>Select amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {property.room_types.map((room) => (
                <tr key={room.id} style={{ opacity: room.is_available ? 1 : 0.5 }}>
                  {/* Room Type */}
                  <td>
                    <strong style={{ color: "var(--bk-blue-light)", fontSize: 14 }}>{room.name}</strong>
                    <div style={{ fontSize: 12, color: "var(--bk-gray-600)", marginTop: 4 }}>
                      {room.bed_count} {room.bed_type} bed{room.bed_count !== 1 ? "s" : ""}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--bk-gray-600)" }}>
                      {room.room_size_sqm} m²
                      {room.view_type && ` · ${room.view_type} view`}
                    </div>
                    {room.amenities.length > 0 && (
                      <div style={{ fontSize: 11, color: "var(--bk-gray-300)", marginTop: 4 }}>
                        {room.amenities.slice(0, 5).join(" · ")}
                        {room.amenities.length > 5 && ` +${room.amenities.length - 5} more`}
                      </div>
                    )}
                  </td>

                  {/* Sleeps */}
                  <td style={{ textAlign: "center" }}>
                    <span title={`Max ${room.max_occupancy} guests`}>
                      {room.max_occupancy}
                    </span>
                  </td>

                  {/* Price */}
                  <td>
                    {room.original_price !== null && room.original_price > room.price_per_night && (
                      <div className="bk-price-original">
                        {formatCurrency(room.original_price, property.currency)}
                      </div>
                    )}
                    <div className="bk-price" style={{ fontSize: 18 }}>
                      {formatCurrency(room.price_per_night, property.currency)}
                    </div>
                    <div className="bk-price-note">per night</div>
                    {room.original_price !== null && room.original_price > room.price_per_night && (
                      <span className="bk-discount-badge" style={{ marginTop: 4 }}>
                        {Math.round(((room.original_price - room.price_per_night) / room.original_price) * 100)}% off
                      </span>
                    )}
                  </td>

                  {/* Your choices */}
                  <td>
                    {room.meals_included && room.meals_included !== "none" && (
                      <div style={{ marginBottom: 4 }}>
                        <span className="bk-badge bk-badge--green">
                          ✓ {room.meals_included.charAt(0).toUpperCase() + room.meals_included.slice(1)} included
                        </span>
                      </div>
                    )}
                    <div style={{ fontSize: 12 }}>
                      {room.cancellation_policy.type === "free_cancellation" ? (
                        <span style={{ color: "var(--bk-green)", fontWeight: 600 }}>
                          ✓ Free cancellation
                        </span>
                      ) : (
                        <span style={{ color: "var(--bk-gray-600)" }}>
                          {room.cancellation_policy.description}
                        </span>
                      )}
                    </div>
                    {room.rooms_left > 0 && room.rooms_left <= 5 && (
                      <div style={{ fontSize: 12, color: "var(--bk-red)", fontWeight: 600, marginTop: 4 }}>
                        Only {room.rooms_left} room{room.rooms_left !== 1 ? "s" : ""} left!
                      </div>
                    )}
                  </td>

                  {/* Select amount */}
                  <td style={{ textAlign: "center" }}>
                    {room.is_available ? (
                      <select
                        className="bk-select"
                        style={{ width: 60 }}
                        value={roomQuantities[room.id] ?? 0}
                        onChange={(e) => handleRoomQtyChange(room.id, Number(e.target.value))}
                      >
                        {Array.from({ length: 6 }, (_, i) => (
                          <option key={i} value={i}>
                            {i}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span style={{ fontSize: 12, color: "var(--bk-red)" }}>Sold out</span>
                    )}
                  </td>

                  {/* Reserve */}
                  <td>
                    <button
                      className="bk-btn bk-btn--primary bk-btn--sm"
                      disabled={!room.is_available || (roomQuantities[room.id] ?? 0) < 1}
                      onClick={() => handleReserve(room)}
                    >
                      Reserve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  6. Amenities                                                */}
      {/* ============================================================ */}
      {property.amenities.length > 0 && (
        <section className="bk-section" id="amenities">
          <h2 className="bk-section-title">Amenities</h2>
          <div className="bk-amenity-grid">
            {property.amenities.map((a) => (
              <div key={a} className="bk-amenity-item">
                <span className="bk-amenity-check">✓</span>
                {a}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ============================================================ */}
      {/*  7. House rules                                              */}
      {/* ============================================================ */}
      <section className="bk-section" id="house-rules">
        <h2 className="bk-section-title">House rules</h2>
        <div className="bk-card" style={{ padding: 20 }}>
          <div className="bk-grid bk-grid--2" style={{ gap: 16 }}>
            <div>
              <strong style={{ fontSize: 13 }}>Check-in</strong>
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                From {property.house_rules.check_in_from} until {property.house_rules.check_in_until}
              </p>
            </div>
            <div>
              <strong style={{ fontSize: 13 }}>Check-out</strong>
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                From {property.house_rules.check_out_from} until {property.house_rules.check_out_until}
              </p>
            </div>
            <div>
              <strong style={{ fontSize: 13 }}>Children</strong>
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                {property.house_rules.children_allowed ? "Children are welcome" : "Not suitable for children"}
              </p>
            </div>
            <div>
              <strong style={{ fontSize: 13 }}>Pets</strong>
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                {property.house_rules.pets_allowed
                  ? `Pets are allowed${property.house_rules.pet_fee > 0 ? ` (${formatCurrency(property.house_rules.pet_fee, property.currency)} fee)` : " at no extra charge"}`
                  : "Pets are not allowed"}
              </p>
            </div>
            <div>
              <strong style={{ fontSize: 13 }}>Smoking</strong>
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                {property.house_rules.smoking_allowed ? "Smoking is allowed" : "No smoking"}
              </p>
            </div>
            <div>
              <strong style={{ fontSize: 13 }}>Parties</strong>
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                {property.house_rules.parties_allowed ? "Parties/events are allowed" : "Parties/events are not allowed"}
              </p>
            </div>
            {property.house_rules.quiet_hours_from && (
              <div>
                <strong style={{ fontSize: 13 }}>Quiet hours</strong>
                <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                  {property.house_rules.quiet_hours_from} &ndash; {property.house_rules.quiet_hours_until}
                </p>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ============================================================ */}
      {/*  8. Location                                                 */}
      {/* ============================================================ */}
      <section className="bk-section" id="location">
        <h2 className="bk-section-title">Location</h2>
        <div className="bk-card" style={{ padding: 20 }}>
          <p style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
            {property.address}, {property.neighborhood}, {property.city}, {property.country}
          </p>
          {property.nearby_attractions.length > 0 && (
            <>
              <h3 style={{ fontSize: 14, fontWeight: 700, marginTop: 16, marginBottom: 8 }}>
                What's nearby
              </h3>
              <div className="bk-grid bk-grid--2" style={{ gap: 6 }}>
                {property.nearby_attractions.map((a) => (
                  <div
                    key={a.name}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: 13,
                      padding: "4px 0",
                      borderBottom: "1px solid var(--bk-border)",
                    }}
                  >
                    <span>
                      <span style={{ color: "var(--bk-gray-300)", marginRight: 6 }}>
                        {a.type === "restaurant" ? "Dining" : a.type === "transport" ? "Transit" : a.type === "attraction" ? "Landmark" : "Nearby"}
                      </span>
                      {a.name}
                    </span>
                    <span style={{ color: "var(--bk-gray-600)", whiteSpace: "nowrap" }}>
                      {a.distance_km < 1 ? `${Math.round(a.distance_km * 1000)} m` : `${a.distance_km.toFixed(1)} km`}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
          {property.languages_spoken.length > 0 && (
            <p style={{ fontSize: 13, color: "var(--bk-gray-600)", marginTop: 12 }}>
              <strong>Languages spoken:</strong> {property.languages_spoken.join(", ")}
            </p>
          )}
        </div>
      </section>

      {/* ============================================================ */}
      {/*  9. Guest reviews                                            */}
      {/* ============================================================ */}
      <section className="bk-section" id="reviews">
        <h2 className="bk-section-title">Guest reviews</h2>

        {/* Score overview */}
        <div className="bk-card" style={{ padding: 20, marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
            <ScoreBadge score={property.review_score} />
            <div>
              <div style={{ fontWeight: 700, fontSize: 16 }}>{property.review_score_label}</div>
              <div style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                {property.review_count.toLocaleString()} review{property.review_count !== 1 ? "s" : ""}
              </div>
            </div>
          </div>

          {/* Breakdown bars */}
          {property.review_breakdown && (
            <div>
              {REVIEW_CATEGORIES.map(({ key, label }) => {
                const value = property.review_breakdown[key];
                return (
                  <div key={key} className="bk-review-bar">
                    <span className="bk-review-bar-label">{label}</span>
                    <div className="bk-review-bar-track">
                      <div
                        className="bk-review-bar-fill"
                        style={{ width: `${(value / 10) * 100}%` }}
                      />
                    </div>
                    <span className="bk-review-bar-value">{value.toFixed(1)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Individual review cards */}
        {reviews.length > 0 ? (
          reviews.map((review) => (
            <div key={review.id} className="bk-review-card">
              <div className="bk-review-header">
                <div>
                  <div className="bk-review-author">{review.author_name}</div>
                  <div className="bk-review-meta">
                    {review.author_country}
                    {review.traveled_with && ` · ${review.traveled_with}`}
                  </div>
                </div>
                <div className="bk-score">
                  <ScoreBadge score={review.overall_score} />
                </div>
              </div>

              {review.title && (
                <p style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
                  {review.title}
                </p>
              )}

              {review.positive && (
                <div style={{ marginBottom: 6 }}>
                  <span className="bk-review-positive" style={{ fontWeight: 600 }}>
                    +{" "}
                  </span>
                  <span className="bk-review-positive">{review.positive}</span>
                </div>
              )}

              {review.negative && (
                <div style={{ marginBottom: 6 }}>
                  <span className="bk-review-negative" style={{ fontWeight: 600 }}>
                    -{" "}
                  </span>
                  <span className="bk-review-negative">{review.negative}</span>
                </div>
              )}

              <div className="bk-review-meta" style={{ marginTop: 8 }}>
                {review.travel_purpose && (
                  <span>Traveled for {review.travel_purpose}</span>
                )}
                {review.stay_date && (
                  <span style={{ marginLeft: 12 }}>
                    Stayed: {review.stay_date}
                  </span>
                )}
                {review.room_type && (
                  <span style={{ marginLeft: 12 }}>Room: {review.room_type}</span>
                )}
              </div>

              {review.property_response && (
                <div
                  className="bk-info-box bk-info-box--blue"
                  style={{ marginTop: 12 }}
                >
                  <strong style={{ fontSize: 12 }}>Property response:</strong>
                  <p style={{ fontSize: 13, marginTop: 4 }}>{review.property_response}</p>
                </div>
              )}

              {review.helpful_count > 0 && (
                <div style={{ fontSize: 12, color: "var(--bk-gray-300)", marginTop: 8 }}>
                  {review.helpful_count} {review.helpful_count === 1 ? "person" : "people"} found this helpful
                </div>
              )}
            </div>
          ))
        ) : (
          <p style={{ color: "var(--bk-gray-600)", fontSize: 14 }}>
            No guest reviews yet for this property.
          </p>
        )}
      </section>

      {/* ============================================================ */}
      {/*  Full description (bottom)                                   */}
      {/* ============================================================ */}
      {property.description && property.description !== property.short_description && (
        <section className="bk-section">
          <h2 className="bk-section-title">About this property</h2>
          <p style={{ fontSize: 14, lineHeight: 1.8, color: "var(--bk-gray-600)" }}>
            {property.description}
          </p>
        </section>
      )}
    </div>
  );
}
