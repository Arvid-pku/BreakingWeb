import { useEffect, useMemo, useRef, useState } from "react";

import { useLmsLayout } from "../context";
import type { PeerReview } from "../types";

function rubricKey(criterion: string): string {
  return criterion.trim().toLowerCase().replace(/\s+/g, "_");
}

function normaliseScores(scores: Record<string, number>): Record<string, number> {
  return Object.fromEntries(Object.entries(scores).map(([key, value]) => [rubricKey(key), value]));
}

export function PeerReviewsPage({ initialReviewId }: { initialReviewId?: string } = {}) {
  const { api, notify } = useLmsLayout();
  const [reviews, setReviews] = useState<PeerReview[]>([]);
  const [selectedId, setSelectedId] = useState<string>(initialReviewId ?? "");
  const [scores, setScores] = useState<Record<string, number>>({});
  const [comments, setComments] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const reviewFormRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const items = await api.listPeerReviews();
        if (!cancelled) {
          setReviews(items);
          if (items.length > 0 && !initialReviewId) {
            const firstPending = items.find((item) => item.status !== "submitted") ?? items[0];
            setSelectedId(firstPending.id);
          } else if (initialReviewId && items.some((item) => item.id === initialReviewId)) {
            setSelectedId(initialReviewId);
          } else if (items.length > 0) {
            const firstPending = items.find((item) => item.status !== "submitted") ?? items[0];
            setSelectedId(firstPending.id);
          }
        }
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api]);

  const selectedReview = useMemo(
    () => reviews.find((review) => review.id === selectedId) ?? null,
    [reviews, selectedId],
  );

  useEffect(() => {
    if (!selectedReview) {
      setScores({});
      setComments("");
      return;
    }
    const seedScores = Object.keys(selectedReview.rubric_scores).length > 0
      ? selectedReview.rubric_scores
      : selectedReview.previous_rubric_scores;
    setScores(normaliseScores(seedScores));
    setComments(selectedReview.comments || selectedReview.previous_comments || "");
  }, [selectedReview]);

  const criteria = selectedReview?.assignment_rubric ?? [];

  const handleSubmit = async () => {
    if (!selectedReview) return;
    const submittedScores = { ...scores };
    reviewFormRef.current?.querySelectorAll<HTMLInputElement>("input[data-rubric-key]").forEach((input) => {
      const key = input.dataset.rubricKey;
      const value = Number.parseInt(input.value, 10);
      if (key && !Number.isNaN(value)) {
        submittedScores[key] = value;
      }
    });
    let submittedComments = comments;
    const commentsInput = reviewFormRef.current?.querySelector<HTMLTextAreaElement>("textarea[data-peer-review-comments]");
    if (commentsInput && commentsInput.value.trim().length > 0) {
      submittedComments = commentsInput.value;
    }
    setSaving(true);
    try {
      const updated = await api.submitPeerReview(selectedReview.id, submittedScores, submittedComments);
      setReviews((current) => current.map((review) => review.id === updated.id ? updated : review));
      notify("Peer Review Submitted", `${updated.reviewee_name}'s review was submitted.`);
    } catch {
      notify("Peer Review Submission Failed", "Unable to submit peer review.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="lms-loading">Loading...</div>;

  return (
    <div aria-label="Peer Reviews">
      <h1 className="lms-section-header">Peer Reviews</h1>

      {reviews.length === 0 ? (
        <p className="lms-empty">No peer reviews assigned.</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 340px) 1fr", gap: "1rem" }}>
          <section aria-label="Peer review list">
            {reviews.map((review) => (
              <button
                key={review.id}
                type="button"
                className="lms-card"
                style={{
                  width: "100%",
                  textAlign: "left",
                  border: review.id === selectedId ? "2px solid #2a67d0" : undefined,
                  marginBottom: "0.75rem",
                }}
                onClick={() => setSelectedId(review.id)}
                aria-label={`Peer review ${review.id} for ${review.reviewee_name}`}
              >
                <div className="lms-card__title">{review.submission_title}</div>
                <div style={{ fontSize: "0.9rem", color: "#666" }}>Reviewee: {review.reviewee_name}</div>
                <div style={{ fontSize: "0.85rem", color: "#666" }}>Due: {new Date(review.due_at).toLocaleString()}</div>
                <div style={{ marginTop: "0.5rem" }}>
                  <span className={`lms-badge lms-badge--${review.status}`}>{review.status}</span>
                  {review.returned_for_revision && (
                    <span className="lms-badge lms-badge--resubmit_requested" style={{ marginLeft: "0.5rem" }}>
                      returned
                    </span>
                  )}
                </div>
              </button>
            ))}
          </section>

          {selectedReview && (
            <section ref={reviewFormRef} aria-label={`Peer review details for ${selectedReview.reviewee_name}`}>
              <div className="lms-card">
                <h2 className="lms-card__title">{selectedReview.submission_title}</h2>
                <p><strong>Reviewee:</strong> {selectedReview.reviewee_name}</p>
                <p style={{ whiteSpace: "pre-wrap" }}>{selectedReview.submission_body}</p>
              </div>

              <div className="lms-card" aria-label="Peer review rubric">
                <h2 className="lms-card__title">Rubric</h2>
                <table className="lms-table" aria-label="Peer review rubric table">
                  <thead>
                    <tr>
                      <th>Criterion</th>
                      <th>Max Points</th>
                      <th>Description</th>
                      <th>Your Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {criteria.map((item) => {
                      const key = rubricKey(item.criterion);
                      return (
                        <tr key={item.criterion}>
                          <td>{item.criterion}</td>
                          <td>5</td>
                          <td>{item.description}</td>
                          <td>
                            <input
                              type="number"
                              min={1}
                              max={5}
                              className="lms-input"
                              value={scores[key] ?? ""}
                              data-rubric-key={key}
                              onChange={(e) => {
                                const value = e.target.value;
                                setScores((current) => ({
                                  ...current,
                                  [key]: value === "" ? 0 : Number.parseInt(value, 10),
                                }));
                              }}
                              aria-label={`Score for ${item.criterion}`}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {(selectedReview.returned_for_revision || Object.keys(selectedReview.previous_rubric_scores).length > 0) && (
                <div className="lms-card" aria-label="Previous review attempt">
                  <h2 className="lms-card__title">Previous Review Attempt</h2>
                  {Object.keys(selectedReview.previous_rubric_scores).length > 0 ? (
                    <ul style={{ marginBottom: "0.75rem" }}>
                      {Object.entries(selectedReview.previous_rubric_scores).map(([criterion, value]) => (
                        <li key={criterion}>{criterion}: {value}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No previous rubric scores recorded.</p>
                  )}
                  <p style={{ whiteSpace: "pre-wrap" }}>
                    <strong>Previous comments:</strong> {selectedReview.previous_comments || "None"}
                  </p>
                </div>
              )}

              <div className="lms-card" aria-label="Peer review comments">
                <h2 className="lms-card__title">Comments</h2>
                <textarea
                  className="lms-input"
                  style={{ width: "100%", minHeight: "140px" }}
                  value={comments}
                  data-peer-review-comments
                  onChange={(e) => setComments(e.target.value)}
                  aria-label="Peer review comments"
                />
                <button
                  type="button"
                  className="lms-btn lms-btn--primary"
                  style={{ marginTop: "0.75rem" }}
                  onClick={handleSubmit}
                  disabled={saving}
                  aria-label="Submit peer review"
                >
                  {saving ? "Submitting..." : "Submit Review"}
                </button>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
