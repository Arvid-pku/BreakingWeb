import { useState, useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import { useBookingLayout } from "../context";
import type { Deal } from "../types";

export default function Deals() {
  const { sessionId, api } = useBookingLayout();
  const location = useLocation();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api.getDeals().then((data) => {
      if (!cancelled) {
        setDeals(data.deals || []);
        setLoading(false);
      }
    }).catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sessionId, api]);

  if (loading) return <div className="bk-loading">Loading deals...</div>;

  return (
    <div>
      <div className="bk-section">
        <h1 className="bk-section-title">Today's Best Deals</h1>
        <p className="bk-section-subtitle">
          Save on your next stay with these limited-time offers
        </p>
      </div>

      {deals.length === 0 ? (
        <div className="bk-empty">
          <h3>No deals available right now</h3>
          <p>Check back later for new offers</p>
          <Link to={preserveQueryParams("/search", location.search)} className="bk-btn bk-btn--primary" style={{ marginTop: 16 }}>
            Browse all properties
          </Link>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {deals.map((deal, i) => {
            const prop = deal.property;
            return (
              <Link
                key={`${prop.id}-${i}`}
                to={preserveQueryParams(`/property/${prop.id}`, location.search)}
                style={{ textDecoration: "none", color: "inherit" }}
              >
                <div className="bk-card bk-card-horizontal">
                  <div className="bk-card-image">
                    {prop.images?.[0] ? (
                      <img src={prop.images[0]} alt={prop.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                    ) : (
                      <span style={{ fontSize: 14, color: "#cdcdcd", fontWeight: 600 }}>Hotel</span>
                    )}
                  </div>
                  <div className="bk-card-body">
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontWeight: 700, fontSize: 16 }}>{prop.name}</span>
                      <span className="bk-stars">
                        {"★".repeat(prop.star_rating)}{"☆".repeat(5 - prop.star_rating)}
                      </span>
                    </div>
                    <div style={{ fontSize: 13, color: "#6b6b6b" }}>
                      {prop.neighborhood ? `${prop.neighborhood}, ` : ""}{prop.city}, {prop.country}
                      {prop.distance_from_center_km > 0 && (
                        <span> · {prop.distance_from_center_km} km from center</span>
                      )}
                    </div>
                    {prop.review_score > 0 && (
                      <div className="bk-score">
                        <span className="bk-score-badge">{prop.review_score.toFixed(1)}</span>
                        <span className="bk-score-label">{prop.review_score_label}</span>
                        <span className="bk-score-count">{prop.review_count.toLocaleString()} reviews</span>
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                      <span className="bk-badge bk-badge--green">
                        {deal.discount_pct}% off
                      </span>
                      {prop.is_genius_property && (
                        <span className="bk-badge bk-badge--genius">Genius</span>
                      )}
                      {prop.free_cancellation && (
                        <span className="bk-badge bk-badge--green">Free cancellation</span>
                      )}
                    </div>
                    <div style={{ fontSize: 13, color: "#6b6b6b", marginTop: 4 }}>
                      {deal.room_type}
                    </div>
                  </div>
                  <div className="bk-card-pricing">
                    <div>
                      <span className="bk-discount-badge">-{deal.discount_pct}%</span>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="bk-price-original">
                        {deal.currency === "USD" ? "$" : deal.currency === "EUR" ? "€" : deal.currency === "GBP" ? "£" : ""}{deal.original_price.toFixed(0)}
                      </div>
                      <div className="bk-price">
                        {deal.currency === "USD" ? "$" : deal.currency === "EUR" ? "€" : deal.currency === "GBP" ? "£" : ""}{deal.price.toFixed(0)}
                      </div>
                      <div className="bk-price-note">per night</div>
                    </div>
                    <button className="bk-btn bk-btn--primary bk-btn--sm" style={{ marginTop: 8 }}>
                      See deal
                    </button>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
