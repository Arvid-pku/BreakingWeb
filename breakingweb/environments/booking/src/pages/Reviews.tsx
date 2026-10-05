import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Review, Reservation } from "../types";
import { useBookingLayout } from "../context";

export default function Reviews() {
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const [reviews, setReviews] = useState<Review[]>([]);
  const [unreviewedStays, setUnreviewedStays] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);

  // Review form state
  const writeMode = searchParams.get("write") === "true";
  const writeReservationId = searchParams.get("reservation") || "";
  const writePropertyId = searchParams.get("property") || "";
  const [showForm, setShowForm] = useState(writeMode);
  const [formPropertyId, setFormPropertyId] = useState(writePropertyId);
  const [formReservationId, setFormReservationId] = useState(writeReservationId);
  const [formScore, setFormScore] = useState(8);
  const [formTitle, setFormTitle] = useState("");
  const [formPositive, setFormPositive] = useState("");
  const [formNegative, setFormNegative] = useState("");
  const [formPurpose, setFormPurpose] = useState("leisure");
  const [formWith, setFormWith] = useState("couple");
  const [formStaff, setFormStaff] = useState(8);
  const [formFacilities, setFormFacilities] = useState(8);
  const [formCleanliness, setFormCleanliness] = useState(8);
  const [formComfort, setFormComfort] = useState(8);
  const [formValue, setFormValue] = useState(8);
  const [formLocation, setFormLocation] = useState(8);
  const [formWifi, setFormWifi] = useState(8);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reviewData, reservationData] = await Promise.all([
        api.listReviews(),
        api.listReservations(),
      ]);

      setReviews(reviewData.reviews);

      // Find completed reservations that haven't been reviewed
      const reviewedReservationIds = new Set(
        reviewData.reviews.map((r) => r.reservation_id)
      );
      const unreviewed = reservationData.reservations.filter(
        (res) =>
          res.status === "completed" && !res.rating_submitted && !reviewedReservationIds.has(res.id)
      );
      setUnreviewedStays(unreviewed);
    } catch {
      notify("Error", "Failed to load reviews.");
    } finally {
      setLoading(false);
    }
  }, [api, sessionId, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSubmitReview = async () => {
    if (!formPropertyId) { notify("Error", "No property selected."); return; }
    if (!formTitle.trim()) { notify("Error", "Please add a review title."); return; }
    if (!formPositive.trim()) { notify("Error", "Please describe what you liked."); return; }
    setSubmitting(true);
    try {
      await api.addReview({
        property_id: formPropertyId,
        reservation_id: formReservationId,
        overall_score: formScore,
        staff: formStaff, facilities: formFacilities,
        cleanliness: formCleanliness, comfort: formComfort,
        value_for_money: formValue, location: formLocation,
        free_wifi: formWifi,
        title: formTitle, positive: formPositive, negative: formNegative,
        travel_purpose: formPurpose, traveled_with: formWith,
      });
      notify("Review Submitted", "Thank you for sharing your experience!");
      setShowForm(false);
      setFormTitle(""); setFormPositive(""); setFormNegative("");
      void load(); // refresh
    } catch {
      notify("Error", "Failed to submit review. Please try again.");
    }
    setSubmitting(false);
  };

  const openReviewForm = (res: Reservation) => {
    setFormPropertyId(res.property_id);
    setFormReservationId(res.id);
    setShowForm(true);
  };

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });

  const getScoreColor = (score: number) => {
    if (score >= 8) return "var(--bk-green)";
    if (score >= 6) return "var(--bk-blue-light)";
    if (score >= 4) return "#b37700";
    return "var(--bk-red)";
  };

  if (loading) {
    return <div className="bk-loading">Loading reviews...</div>;
  }

  return (
    <div>
      <h1 className="bk-section-title" style={{ marginBottom: 24 }}>
        My Reviews
      </h1>

      {/* Unreviewed stays */}
      {unreviewedStays.length > 0 && (
        <div className="bk-section">
          <div className="bk-info-box bk-info-box--blue" style={{ marginBottom: 20 }}>
            <strong>
              You have {unreviewedStays.length} completed stay
              {unreviewedStays.length !== 1 ? "s" : ""} waiting for a review!
            </strong>
          </div>

          <h2
            style={{
              fontSize: 16,
              fontWeight: 700,
              marginBottom: 12,
            }}
          >
            Leave a Review
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
            {unreviewedStays.map((res) => (
              <div
                key={res.id}
                className="bk-card"
                style={{
                  padding: "12px 16px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>
                    {res.property_name}
                  </span>
                  <span
                    style={{
                      fontSize: 12,
                      color: "var(--bk-gray-600)",
                      marginLeft: 10,
                    }}
                  >
                    {res.room_type_name} &middot; {formatDate(res.check_in)} -{" "}
                    {formatDate(res.check_out)}
                  </span>
                </div>
                <button
                  className="bk-btn bk-btn--primary bk-btn--sm"
                  onClick={() => openReviewForm(res)}
                >
                  Write Review
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Review submission form */}
      {showForm && (
        <div className="bk-section">
          <div className="bk-card" style={{ padding: 24 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Write Your Review</h2>
            <div className="bk-form-group">
              <label>Overall Score (1-10)</label>
              <input type="number" className="bk-input" min={1} max={10} step={0.5}
                value={formScore} onChange={(e) => setFormScore(Number(e.target.value))} />
            </div>
            <div className="bk-form-group">
              <label>Title</label>
              <input className="bk-input" value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)} placeholder="Summarize your stay" />
            </div>
            <div className="bk-form-group">
              <label>What did you like?</label>
              <textarea className="bk-textarea" value={formPositive}
                onChange={(e) => setFormPositive(e.target.value)}
                placeholder="Tell us about the highlights of your stay" />
            </div>
            <div className="bk-form-group">
              <label>What could be improved?</label>
              <textarea className="bk-textarea" value={formNegative}
                onChange={(e) => setFormNegative(e.target.value)}
                placeholder="Share any areas for improvement (optional)" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div className="bk-form-group"><label>Staff (1-10)</label>
                <input type="number" className="bk-input" min={1} max={10} step={0.5} value={formStaff} onChange={(e) => setFormStaff(Number(e.target.value))} /></div>
              <div className="bk-form-group"><label>Facilities (1-10)</label>
                <input type="number" className="bk-input" min={1} max={10} step={0.5} value={formFacilities} onChange={(e) => setFormFacilities(Number(e.target.value))} /></div>
              <div className="bk-form-group"><label>Cleanliness (1-10)</label>
                <input type="number" className="bk-input" min={1} max={10} step={0.5} value={formCleanliness} onChange={(e) => setFormCleanliness(Number(e.target.value))} /></div>
              <div className="bk-form-group"><label>Comfort (1-10)</label>
                <input type="number" className="bk-input" min={1} max={10} step={0.5} value={formComfort} onChange={(e) => setFormComfort(Number(e.target.value))} /></div>
              <div className="bk-form-group"><label>Value for Money (1-10)</label>
                <input type="number" className="bk-input" min={1} max={10} step={0.5} value={formValue} onChange={(e) => setFormValue(Number(e.target.value))} /></div>
              <div className="bk-form-group"><label>Location (1-10)</label>
                <input type="number" className="bk-input" min={1} max={10} step={0.5} value={formLocation} onChange={(e) => setFormLocation(Number(e.target.value))} /></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
              <div className="bk-form-group"><label>Travel purpose</label>
                <select className="bk-select" value={formPurpose} onChange={(e) => setFormPurpose(e.target.value)}>
                  <option value="leisure">Leisure</option><option value="business">Business</option>
                  <option value="family">Family</option></select></div>
              <div className="bk-form-group"><label>Traveled with</label>
                <select className="bk-select" value={formWith} onChange={(e) => setFormWith(e.target.value)}>
                  <option value="solo">Solo</option><option value="couple">Couple</option>
                  <option value="family">Family</option><option value="friends">Friends</option></select></div>
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button className="bk-btn bk-btn--secondary" onClick={() => setShowForm(false)} disabled={submitting}>Cancel</button>
              <button className="bk-btn bk-btn--primary" onClick={handleSubmitReview} disabled={submitting}>
                {submitting ? "Submitting..." : "Submit Review"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Reviews list */}
      {reviews.length === 0 ? (
        <div className="bk-empty">
          <h3>No reviews yet</h3>
          <p>
            After completing a stay, you can leave a review to share your
            experience.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {reviews.map((review) => (
            <div key={review.id} className="bk-review-card">
              <div className="bk-review-header">
                <div>
                  <Link
                    to={preserveQueryParams(
                      `/property/${review.property_id}`,
                      location.search
                    )}
                    style={{ fontWeight: 700, fontSize: 16 }}
                  >
                    {review.room_type || "Property"}
                  </Link>
                  {review.title && (
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginTop: 4 }}>
                      {review.title}
                    </h3>
                  )}
                </div>
                <div style={{ textAlign: "right" }}>
                  <div
                    className="bk-score-badge"
                    style={{
                      background: getScoreColor(review.overall_score),
                      fontSize: 16,
                      padding: "6px 10px",
                    }}
                  >
                    {review.overall_score.toFixed(1)}
                  </div>
                </div>
              </div>

              {/* Positive/Negative text */}
              <div style={{ marginBottom: 10 }}>
                {review.positive && (
                  <div style={{ marginBottom: 6 }}>
                    <span
                      className="bk-review-positive"
                      style={{ fontWeight: 600, fontSize: 13 }}
                    >
                      + {" "}
                    </span>
                    <span style={{ fontSize: 13 }}>{review.positive}</span>
                  </div>
                )}
                {review.negative && (
                  <div>
                    <span
                      className="bk-review-negative"
                      style={{ fontWeight: 600, fontSize: 13 }}
                    >
                      - {" "}
                    </span>
                    <span style={{ fontSize: 13 }}>{review.negative}</span>
                  </div>
                )}
              </div>

              {/* Meta information */}
              <div className="bk-review-meta">
                <span>{formatDate(review.created_at)}</span>
                {review.travel_purpose && (
                  <>
                    {" "}&middot;{" "}
                    <span style={{ textTransform: "capitalize" }}>
                      {review.travel_purpose}
                    </span>
                  </>
                )}
                {review.traveled_with && (
                  <>
                    {" "}&middot;{" "}
                    <span style={{ textTransform: "capitalize" }}>
                      {review.traveled_with}
                    </span>
                  </>
                )}
                {review.stay_date && (
                  <>
                    {" "}&middot; Stayed: {review.stay_date}
                  </>
                )}
              </div>

              {/* Property response */}
              {review.property_response && (
                <div
                  style={{
                    marginTop: 12,
                    padding: "10px 14px",
                    background: "var(--bk-gray-50)",
                    borderRadius: "var(--bk-radius)",
                    borderLeft: "3px solid var(--bk-blue-light)",
                  }}
                >
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: "var(--bk-blue)",
                      display: "block",
                      marginBottom: 4,
                    }}
                  >
                    Property Response
                  </span>
                  <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                    {review.property_response}
                  </p>
                </div>
              )}

              {/* Helpful count */}
              {review.helpful_count > 0 && (
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 12,
                    color: "var(--bk-gray-600)",
                  }}
                >
                  {review.helpful_count} traveler{review.helpful_count !== 1 ? "s" : ""} found this review helpful
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
