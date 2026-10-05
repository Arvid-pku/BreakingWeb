import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import { useBookingLayout } from "../context";
import type {
  Destination,
  Deal,
  PropertyBrief,
  SearchHistoryEntry,
  GeniusInfo,
} from "../types";

/* ---------- helpers ---------- */

function stars(n: number): string {
  return "\u2605".repeat(n);
}

function scoreLabel(score: number): string {
  if (score >= 9) return "Wonderful";
  if (score >= 8) return "Very Good";
  if (score >= 7) return "Good";
  if (score >= 6) return "Pleasant";
  return "Review score";
}

function formatCurrency(amount: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function tomorrowStr(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

/* ---------- component ---------- */

export default function Home() {
  const { sessionId, api } = useBookingLayout();
  const location = useLocation();
  const navigate = useNavigate();
  const qp = (to: string) => preserveQueryParams(to, location.search);

  /* --- form state --- */
  const [destination, setDestination] = useState("");
  const [checkIn, setCheckIn] = useState(todayStr());
  const [checkOut, setCheckOut] = useState(tomorrowStr());
  const [guests, setGuests] = useState(2);

  /* --- data state --- */
  const [genius, setGenius] = useState<GeniusInfo | null>(null);
  const [history, setHistory] = useState<SearchHistoryEntry[]>([]);
  const [destinations, setDestinations] = useState<Destination[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [recentlyViewed, setRecentlyViewed] = useState<PropertyBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      api.getGenius().catch(() => null),
      api.getSearchHistory().catch(() => ({ history: [] })),
      api.getDestinations().catch(() => ({ destinations: [] })),
      api.getDeals().catch(() => ({ deals: [] })),
      api.getRecentlyViewed().catch(() => ({ properties: [] })),
    ])
      .then(([geniusRes, historyRes, destRes, dealsRes, viewedRes]) => {
        if (cancelled) return;
        setGenius(geniusRes);
        setHistory(historyRes?.history ?? []);
        setDestinations(destRes?.destinations ?? []);
        setDeals(dealsRes?.deals ?? []);
        setRecentlyViewed(viewedRes?.properties ?? []);
      })
      .catch(() => {
        if (!cancelled) setError("Failed to load homepage data. Please try again.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [api, sessionId]);

  /* --- search submit --- */
  function handleSearch(e: FormEvent) {
    e.preventDefault();
    const params = new URLSearchParams();
    if (destination) params.set("destination", destination);
    if (checkIn) params.set("check_in", checkIn);
    if (checkOut) params.set("check_out", checkOut);
    params.set("guests", String(guests));
    navigate(qp(`/search?${params.toString()}`));
  }

  /* --- render --- */

  if (error) {
    return (
      <div className="bk-empty">
        <h3>Something went wrong</h3>
        <p>{error}</p>
        <button className="bk-btn bk-btn--primary" style={{ marginTop: 12 }} onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* ============ HERO + SEARCH ============ */}
      <section className="bk-search-hero" style={{ margin: "-20px -20px 0", padding: "32px 0 36px" }}>
        <div className="bk-search-hero-inner">
          <h1>Find your next stay</h1>
          <p>Search deals on hotels, homes, and much more...</p>

          <form className="bk-search-bar" onSubmit={handleSearch} aria-label="Search properties">
            <div className="bk-search-field">
              <input
                type="text"
                placeholder="Where are you going?"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                aria-label="Destination"
              />
            </div>
            <div className="bk-search-field">
              <input
                type="date"
                value={checkIn}
                onChange={(e) => setCheckIn(e.target.value)}
                aria-label="Check-in date"
              />
            </div>
            <div className="bk-search-field">
              <input
                type="date"
                value={checkOut}
                onChange={(e) => setCheckOut(e.target.value)}
                aria-label="Check-out date"
              />
            </div>
            <div className="bk-search-field">
              <select
                value={guests}
                onChange={(e) => setGuests(Number(e.target.value))}
                aria-label="Number of guests"
              >
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>
                    {n} {n === 1 ? "guest" : "guests"}
                  </option>
                ))}
              </select>
            </div>
            <button type="submit" className="bk-search-btn">
              Search
            </button>
          </form>
        </div>
      </section>

      {loading ? (
        <div className="bk-loading">Loading...</div>
      ) : (
        <>
          {/* ============ GENIUS BANNER ============ */}
          {genius && (
            <section className="bk-genius-banner" aria-label="Genius loyalty program">
              <h3>
                <span className="bk-genius-badge" style={{ marginRight: 8 }}>
                  Genius Level {genius.level}
                </span>
                You're a Genius member!
              </h3>
              <p style={{ marginTop: 8 }}>
                {genius.total_bookings} lifetime bookings
                {genius.bookings_needed_for_next > 0 && (
                  <> &mdash; {genius.bookings_needed_for_next} more to reach the next level</>
                )}
              </p>
              {genius.benefits.length > 0 && (
                <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {genius.benefits.map((b) => (
                    <span key={b} className="bk-badge bk-badge--yellow">{b}</span>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* ============ RECENT SEARCHES ============ */}
          {history.length > 0 && (
            <section className="bk-section" aria-label="Recent searches">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <h2 className="bk-section-title" style={{ margin: 0 }}>Your recent searches</h2>
                <button
                  className="bk-btn bk-btn--tertiary"
                  style={{ fontSize: 14 }}
                  onClick={async () => {
                    await api.clearSearchHistory();
                    setHistory([]);
                  }}
                >
                  Clear all
                </button>
              </div>
              <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 4 }}>
                {history.slice(0, 6).map((entry, idx) => (
                  <Link
                    key={idx}
                    to={qp(
                      `/search?destination=${encodeURIComponent(entry.destination)}&check_in=${entry.check_in}&check_out=${entry.check_out}&guests=${entry.guests}`
                    )}
                    style={{ textDecoration: "none" }}
                  >
                    <div
                      className="bk-dest-card"
                      style={{ minWidth: 200, cursor: "pointer" }}
                    >
                      <h3>{entry.destination}</h3>
                      {entry.check_in && entry.check_out ? (
                        <p>
                          {new Date(entry.check_in + "T00:00").toLocaleDateString()} &ndash;{" "}
                          {new Date(entry.check_out + "T00:00").toLocaleDateString()}
                        </p>
                      ) : (
                        <p style={{ color: "var(--bk-gray-300)" }}>Flexible dates</p>
                      )}
                      <p>
                        {entry.guests} {entry.guests === 1 ? "guest" : "guests"}
                        {entry.rooms > 1 && <>, {entry.rooms} rooms</>}
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* ============ POPULAR DESTINATIONS ============ */}
          {destinations.length > 0 && (
            <section className="bk-section" aria-label="Popular destinations">
              <h2 className="bk-section-title">Popular destinations</h2>
              <div className="bk-grid bk-grid--4">
                {destinations.slice(0, 8).map((dest) => (
                  <Link
                    key={`${dest.city}-${dest.country}`}
                    to={qp(`/search?destination=${encodeURIComponent(dest.city)}`)}
                    style={{ textDecoration: "none" }}
                  >
                    <div className="bk-dest-card">
                      <h3>{dest.city}</h3>
                      <p>{dest.country}</p>
                      <p style={{ marginTop: 4 }}>
                        {dest.property_count.toLocaleString()} properties
                      </p>
                      {dest.min_price != null && (
                        <p style={{ fontWeight: 600, marginTop: 2, color: "var(--bk-gray-800)" }}>
                          From {formatCurrency(dest.min_price)} per night
                        </p>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* ============ TODAY'S DEALS ============ */}
          {deals.length > 0 && (
            <section className="bk-section" aria-label="Today's deals">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <h2 className="bk-section-title" style={{ marginBottom: 0 }}>
                  Today's deals
                </h2>
                <Link to={qp("/deals")} className="bk-btn bk-btn--ghost bk-btn--sm">
                  See all deals
                </Link>
              </div>
              <div className="bk-grid bk-grid--3">
                {deals.slice(0, 6).map((deal, idx) => (
                  <Link
                    key={`${deal.property.id}-${idx}`}
                    to={qp(`/property/${deal.property.id}`)}
                    style={{ textDecoration: "none" }}
                  >
                    <div className="bk-card" style={{ height: "100%" }}>
                      {/* image placeholder */}
                      <div
                        className="bk-card-image"
                        style={{ width: "100%", minHeight: 140 }}
                      >
                        {deal.property.images?.[0] ? (
                          <img
                            src={deal.property.images[0]}
                            alt={deal.property.name}
                            style={{ width: "100%", height: 140, objectFit: "cover" }}
                          />
                        ) : (
                          <span aria-hidden="true">&#128246;</span>
                        )}
                      </div>
                      <div className="bk-card-body">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ fontWeight: 700, fontSize: 15 }}>{deal.property.name}</div>
                            <div style={{ fontSize: 12, color: "var(--bk-gray-600)" }}>
                              {deal.property.city}, {deal.property.country}
                            </div>
                          </div>
                          <span className="bk-discount-badge">-{deal.discount_pct}%</span>
                        </div>
                        {deal.property.star_rating > 0 && (
                          <div className="bk-stars">{stars(deal.property.star_rating)}</div>
                        )}
                        <div className="bk-score">
                          <span className="bk-score-badge">{deal.property.review_score.toFixed(1)}</span>
                          <span className="bk-score-label">{deal.property.review_score_label || scoreLabel(deal.property.review_score)}</span>
                          <span className="bk-score-count">{deal.property.review_count.toLocaleString()} reviews</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
                          <span className="bk-price-original">
                            {formatCurrency(deal.original_price, deal.currency)}
                          </span>
                          <span className="bk-price">
                            {formatCurrency(deal.price, deal.currency)}
                          </span>
                        </div>
                        {deal.property.is_genius_property && (
                          <span className="bk-badge bk-badge--genius" style={{ marginTop: 4, alignSelf: "flex-start" }}>
                            Genius
                          </span>
                        )}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* ============ RECENTLY VIEWED ============ */}
          {recentlyViewed.length > 0 && (
            <section className="bk-section" aria-label="Recently viewed properties">
              <h2 className="bk-section-title">Your recently viewed properties</h2>
              <div style={{ display: "flex", gap: 16, overflowX: "auto", paddingBottom: 4 }}>
                {recentlyViewed.slice(0, 8).map((prop) => (
                  <Link
                    key={prop.id}
                    to={qp(`/property/${prop.id}`)}
                    style={{ textDecoration: "none", flexShrink: 0, width: 240 }}
                  >
                    <div className="bk-card" style={{ height: "100%" }}>
                      <div className="bk-card-image" style={{ width: "100%", minHeight: 120 }}>
                        {prop.images?.[0] ? (
                          <img
                            src={prop.images[0]}
                            alt={prop.name}
                            style={{ width: "100%", height: 120, objectFit: "cover" }}
                          />
                        ) : (
                          <span aria-hidden="true">&#128246;</span>
                        )}
                      </div>
                      <div className="bk-card-body">
                        <div style={{ fontWeight: 700, fontSize: 14 }}>{prop.name}</div>
                        <div style={{ fontSize: 12, color: "var(--bk-gray-600)" }}>
                          {prop.city}, {prop.country}
                        </div>
                        {prop.star_rating > 0 && (
                          <div className="bk-stars">{stars(prop.star_rating)}</div>
                        )}
                        <div className="bk-score" style={{ marginTop: 4 }}>
                          <span className="bk-score-badge">{prop.review_score.toFixed(1)}</span>
                          <span className="bk-score-label">{prop.review_score_label || scoreLabel(prop.review_score)}</span>
                        </div>
                        {prop.price_from != null && (
                          <div style={{ marginTop: 6 }}>
                            {prop.original_price_from != null && prop.original_price_from > prop.price_from && (
                              <span className="bk-price-original" style={{ marginRight: 6 }}>
                                {formatCurrency(prop.original_price_from, prop.currency)}
                              </span>
                            )}
                            <span className="bk-price" style={{ fontSize: 18 }}>
                              {formatCurrency(prop.price_from, prop.currency)}
                            </span>
                            <span className="bk-price-note" style={{ marginLeft: 4 }}>per night</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* empty fallback when everything is empty */}
          {destinations.length === 0 && deals.length === 0 && recentlyViewed.length === 0 && history.length === 0 && (
            <div className="bk-empty">
              <h3>Welcome to Booking.com</h3>
              <p>Use the search bar above to find your next stay.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
