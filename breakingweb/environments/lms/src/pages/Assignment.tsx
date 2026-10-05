import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useLmsLayout } from "../context";
import type { Assignment as AssignmentType, Course } from "../types";

export function AssignmentPage() {
  const { id: courseId, aid: assignmentId } = useParams<{ id: string; aid: string }>();
  const { api, notify } = useLmsLayout();

  const [assignment, setAssignment] = useState<AssignmentType | null>(null);
  const [course, setCourse] = useState<Course | null>(null);
  const [fileName, setFileName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [a, c] = await Promise.all([
          api.getAssignment(assignmentId!),
          api.getCourse(courseId!),
        ]);
        if (!cancelled) {
          setAssignment(a);
          setCourse(c);
        }
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api, assignmentId, courseId]);

  const handleSubmit = async () => {
    if (!assignment || !fileName.trim()) return;
    setSubmitting(true);
    try {
      const updated = await api.submitAssignment(assignment.id, fileName.trim());
      setAssignment(updated);
      setFileName("");
      notify("Assignment Submitted", `${assignment.title} submitted successfully`);
    } catch {
      notify("Submission Failed", "Unable to submit assignment");
    } finally {
      setSubmitting(false);
    }
  };

  const handleResubmit = async () => {
    if (!assignment || !fileName.trim()) return;
    setSubmitting(true);
    try {
      // Route to /resubmit only when status is explicitly "resubmit_requested"
      // (backend resubmit endpoint requires that); otherwise route to /submit,
      // which backend (lms.py:646) accepts for graded/late/not_submitted too.
      const updated =
        assignment.submission_status === "resubmit_requested"
          ? await api.resubmitAssignment(assignment.id, fileName.trim())
          : await api.submitAssignment(assignment.id, fileName.trim());
      setAssignment(updated);
      setFileName("");
      notify("Assignment Resubmitted", `${assignment.title} resubmitted successfully`);
    } catch {
      notify("Resubmission Failed", "Unable to resubmit assignment");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="lms-loading">Loading...</div>;
  if (!assignment) return <div className="lms-empty">Assignment not found</div>;

  const canSubmit = assignment.submission_status === "not_submitted";
  // Resubmission is allowed for any status the backend POST /submit accepts
  // (lms.py:646), gated on remaining attempts. Previously only
  // "resubmit_requested" unlocked the form, which blocked legitimate
  // resubmit-after-feedback and late-recovery flows where the instructor
  // never explicitly flagged the assignment.
  const canResubmit = (
    assignment.submission_status === "resubmit_requested" ||
    assignment.submission_status === "graded" ||
    assignment.submission_status === "late"
  ) && assignment.attempt_count <= assignment.max_attempts;

  return (
    <div aria-label={`Assignment ${assignment.title}`}>
      <h1 className="lms-section-header">{assignment.title}</h1>

      {/* Assignment Info */}
      <div className="lms-card" aria-label="Assignment Details">
        <p><strong>Course:</strong> {course?.course_code ?? courseId}</p>
        <p><strong>Type:</strong> {assignment.type}</p>
        <p><strong>Due date:</strong> {new Date(assignment.due_at).toLocaleString()}</p>
        <p><strong>Points possible:</strong> {assignment.points_possible}</p>
        <p><strong>Category:</strong> {assignment.weight_category}</p>
        <p>
          <strong>Status:</strong>{" "}
          <span
            className={`lms-badge lms-badge--${assignment.submission_status}`}
            aria-label={`Status: ${assignment.submission_status.replace(/_/g, " ")}`}
          >
            {assignment.submission_status.replace(/_/g, " ")}
          </span>
        </p>
        <p aria-label={`Attempt ${assignment.attempt_count} of ${assignment.max_attempts}`}>
          <strong>Attempts:</strong> {assignment.attempt_count} of {assignment.max_attempts}
        </p>
        {assignment.submitted_at && (
          <p><strong>Submitted at:</strong> {new Date(assignment.submitted_at).toLocaleString()}</p>
        )}
        {assignment.file_name && (
          <p><strong>File:</strong> {assignment.file_name}</p>
        )}
      </div>

      {/* Score & Feedback */}
      {assignment.score !== null && (
        <div className="lms-card" aria-label="Score and Feedback">
          <h2 className="lms-card__title">Score & Feedback</h2>
          <p aria-label={`Score ${assignment.score} out of ${assignment.points_possible}`}>
            <strong>Score:</strong> {assignment.score} / {assignment.points_possible}
            ({((parseFloat(assignment.score) / parseFloat(assignment.points_possible)) * 100).toFixed(1)}%)
          </p>
          {assignment.feedback && (
            <div>
              <strong>Feedback:</strong>
              <p style={{ marginTop: "0.25rem", whiteSpace: "pre-wrap" }}>{assignment.feedback}</p>
            </div>
          )}
        </div>
      )}

      {/* Rubric */}
      {assignment.rubric.length > 0 && (
        <div className="lms-card" aria-label="Rubric">
          <h2 className="lms-card__title">Rubric</h2>
          <table className="lms-table" aria-label="Rubric Table">
            <thead>
              <tr>
                <th>Criterion</th>
                <th>Max Points</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {assignment.rubric.map((item, idx) => (
                <tr key={idx}>
                  <td>{item.criterion}</td>
                  <td>{item.max_points}</td>
                  <td>{item.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Submission Form */}
      {(canSubmit || canResubmit) && (
        <div className="lms-card" aria-label="Submit Assignment">
          <h2 className="lms-card__title">
            {canResubmit ? "Resubmit Assignment" : "Submit Assignment"}
          </h2>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <label htmlFor="file-name-input" style={{ fontWeight: 500 }}>
              File name:
            </label>
            <input
              id="file-name-input"
              type="text"
              className="lms-input"
              value={fileName}
              onChange={(e) => setFileName(e.target.value)}
              placeholder="submission.pdf"
              aria-label="File name for submission"
            />
            {canResubmit ? (
              <button
                type="button"
                className="lms-btn lms-btn--primary"
                onClick={handleResubmit}
                disabled={submitting || !fileName.trim()}
                aria-label="Resubmit assignment"
              >
                {submitting ? "Resubmitting..." : "Resubmit"}
              </button>
            ) : (
              <button
                type="button"
                className="lms-btn lms-btn--primary"
                onClick={handleSubmit}
                disabled={submitting || !fileName.trim()}
                aria-label="Submit assignment"
              >
                {submitting ? "Submitting..." : "Submit"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
