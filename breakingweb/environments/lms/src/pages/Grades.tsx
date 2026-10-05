import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useLmsLayout } from "../context";
import type { Assignment, Course, Grade } from "../types";

export function GradesPage() {
  const { id: courseId } = useParams<{ id: string }>();
  const { api } = useLmsLayout();

  const [course, setCourse] = useState<Course | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [gradesData, setGradesData] = useState<{
    weighted_score: string | null;
    category_scores: Record<string, string | null>;
    grades: Grade[];
  } | null>(null);
  const [whatIfScores, setWhatIfScores] = useState<Record<string, string>>({});
  const [whatIfResult, setWhatIfResult] = useState<string | null>(null);
  const [calculatingWhatIf, setCalculatingWhatIf] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, gd, assigns] = await Promise.all([
          api.getCourse(courseId!),
          api.getCourseGrades(courseId!),
          api.listAssignments(courseId!),
        ]);
        if (!cancelled) {
          setCourse(c);
          setGradesData(gd);
          setAssignments(assigns);
        }
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api, courseId]);

  const handleWhatIf = async () => {
    // Filter out empty entries
    const nonEmpty: Record<string, string> = {};
    for (const [key, val] of Object.entries(whatIfScores)) {
      if (val.trim()) nonEmpty[key] = val.trim();
    }
    if (Object.keys(nonEmpty).length === 0) return;

    setCalculatingWhatIf(true);
    try {
      const result = await api.whatIfGrades(courseId!, nonEmpty);
      setWhatIfResult(result.what_if_weighted_score);
    } catch {
      setWhatIfResult(null);
    } finally {
      setCalculatingWhatIf(false);
    }
  };

  if (loading) return <div className="lms-loading">Loading...</div>;
  if (!course || !gradesData) return <div className="lms-empty">Course not found</div>;

  const policy = course.syllabus.grading_policy;

  // Group grades by category
  const gradesByCategory: Record<string, Grade[]> = {};
  for (const catName of Object.keys(policy)) {
    gradesByCategory[catName] = gradesData.grades.filter((g) => g.weight_category === catName);
  }

  // Find ungraded assignments for what-if
  const ungradedAssignments = assignments.filter(
    (a) => a.score === null && a.submission_status !== "graded",
  );

  return (
    <div aria-label={`Grades for ${course.course_code}`}>
      <h1 className="lms-section-header">Grades: {course.course_code}</h1>

      {/* Overall Score */}
      <div className="lms-card" aria-label="Overall Grade">
        <h2 className="lms-card__title">Overall Weighted Score</h2>
        <div style={{ fontSize: "1.5rem", fontWeight: 700 }} aria-label={`Overall weighted score ${gradesData.weighted_score ?? "N/A"}%`}>
          {gradesData.weighted_score ? `${gradesData.weighted_score}%` : "N/A"}
        </div>
      </div>

      {/* Category Breakdown */}
      <div className="lms-card" aria-label="Grade Breakdown">
        <h2 className="lms-card__title">Category Breakdown</h2>
        <table className="lms-table" aria-label="Category Breakdown Table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Weight</th>
              <th>Count</th>
              <th>Average</th>
              <th>Weighted Contribution</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(policy).map(([catName, catPolicy]) => {
              const catGrades = gradesByCategory[catName] ?? [];
              const gradedCount = catGrades.filter((g) => g.score !== null).length;
              const catScore = gradesData.category_scores[catName];
              const weight = parseFloat(catPolicy.weight);
              const contribution = catScore !== null
                ? (parseFloat(catScore) * weight).toFixed(2)
                : "-";
              return (
                <tr key={catName}>
                  <td>{catName}</td>
                  <td>{(weight * 100).toFixed(0)}%</td>
                  <td>{gradedCount} / {catGrades.length}</td>
                  <td>{catScore !== null ? `${catScore}%` : "N/A"}</td>
                  <td>{contribution !== "-" ? `${contribution}%` : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Per-Category Assignment Details */}
      {Object.entries(policy).map(([catName]) => {
        const catGrades = gradesByCategory[catName] ?? [];
        if (catGrades.length === 0) return null;

        return (
          <div key={catName} className="lms-card" aria-label={`${catName} Grades`}>
            <h2 className="lms-card__title">{catName}</h2>
            <table className="lms-table" aria-label={`${catName} Assignment Grades`}>
              <thead>
                <tr>
                  <th>Assignment</th>
                  <th>Score</th>
                  <th>Points</th>
                  <th>%</th>
                  <th>Late Penalty</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {catGrades.map((g) => {
                  const assignment = assignments.find((a) => a.id === g.assignment_id);
                  const pct = g.score !== null
                    ? ((parseFloat(g.score) / parseFloat(g.points_possible)) * 100).toFixed(1)
                    : "-";
                  const latePenalty = parseFloat(g.late_penalty_applied);
                  return (
                    <tr
                      key={g.id}
                      className={g.is_dropped ? "lms-dropped" : ""}
                      style={g.is_dropped ? { textDecoration: "line-through" } : {}}
                    >
                      <td>{assignment?.title ?? g.assignment_id}</td>
                      <td>{g.score ?? "-"}</td>
                      <td>{g.points_possible}</td>
                      <td>{pct}</td>
                      <td>{latePenalty > 0 ? `${(latePenalty * 100).toFixed(0)}%` : "-"}</td>
                      <td>
                        {g.is_dropped ? (
                          <span className="lms-badge lms-badge--dropped" aria-label="Dropped">Dropped</span>
                        ) : g.score !== null ? (
                          <span className="lms-badge lms-badge--graded">Graded</span>
                        ) : (
                          <span className="lms-badge lms-badge--not_submitted">Pending</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}

      {/* What-If Calculator */}
      <div className="lms-whatif" aria-label="What-If Calculator">
        <h2 className="lms-card__title">What-If Calculator</h2>
        <p style={{ fontSize: "0.85rem", color: "#666", marginBottom: "0.75rem" }}>
          Enter hypothetical scores for ungraded assignments to see projected grade.
        </p>
        {ungradedAssignments.length === 0 ? (
          <p style={{ fontSize: "0.9rem" }}>All assignments are graded.</p>
        ) : (
          <>
            {ungradedAssignments.map((a) => (
              <div key={a.id} className="lms-whatif__row">
                <span className="lms-whatif__label">
                  {a.title} ({a.points_possible} pts)
                </span>
                <input
                  type="number"
                  className="lms-input lms-whatif__input"
                  value={whatIfScores[a.id] ?? ""}
                  onChange={(e) =>
                    setWhatIfScores((prev) => ({ ...prev, [a.id]: e.target.value }))
                  }
                  placeholder="Score"
                  min="0"
                  max={a.points_possible}
                  aria-label={`Hypothetical score for ${a.title}`}
                />
              </div>
            ))}
            <button
              type="button"
              className="lms-btn lms-btn--primary"
              onClick={handleWhatIf}
              disabled={calculatingWhatIf}
              aria-label="Calculate what-if grade"
              style={{ marginTop: "0.5rem" }}
            >
              {calculatingWhatIf ? "Calculating..." : "Calculate"}
            </button>
            {whatIfResult !== null && (
              <div className="lms-whatif__result" aria-label={`Projected grade ${whatIfResult}%`}>
                Projected Weighted Score: {whatIfResult}%
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
