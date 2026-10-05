import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useLmsLayout } from "../context";
import type { Course, Enrollment } from "../types";

interface CourseWithMeta {
  course: Course;
  weightedScore: string | null;
  enrollmentStatus: Enrollment["status"];
  role: Enrollment["role"];
}

export function CoursesPage() {
  const { api } = useLmsLayout();
  const location = useLocation();
  const [coursesData, setCoursesData] = useState<CourseWithMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [courses, enrollments] = await Promise.all([
          api.listCourses(),
          api.listEnrollments(),
        ]);
        // Build a map of courseId -> enrollment for quick lookup
        const enrollmentMap = new Map<string, Enrollment>();
        for (const e of enrollments) {
          enrollmentMap.set(e.course_id, e);
        }
        // Include enrolled and waitlisted courses (skip dropped/completed if not in courses list)
        const results: CourseWithMeta[] = [];
        for (const course of courses) {
          const enrollment = enrollmentMap.get(course.id);
          const status = enrollment?.status ?? "enrolled";
          const role = enrollment?.role ?? "student";
          try {
            const gradesData = await api.getCourseGrades(course.id);
            results.push({ course, weightedScore: gradesData.weighted_score, enrollmentStatus: status, role });
          } catch {
            results.push({ course, weightedScore: null, enrollmentStatus: status, role });
          }
        }
        // Also include waitlisted courses not already in the list
        for (const enrollment of enrollments) {
          if (enrollment.status === "waitlisted" && !results.some((r) => r.course.id === enrollment.course_id)) {
            try {
              const course = await api.getCourse(enrollment.course_id);
              results.push({ course, weightedScore: null, enrollmentStatus: "waitlisted", role: enrollment.role });
            } catch {
              // skip
            }
          }
        }
        if (!cancelled) setCoursesData(results);
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api]);

  if (loading) return <div className="lms-loading">Loading...</div>;

  return (
    <div aria-label="Courses">
      <h1 className="lms-section-header">Courses</h1>
      {coursesData.length === 0 ? (
        <p className="lms-empty">No enrolled courses</p>
      ) : (
        <div className="lms-grid">
          {coursesData.map(({ course, weightedScore, enrollmentStatus, role }) => (
            <Link
              key={course.id}
              to={preserveQueryParams(`/courses/${course.id}`, location.search)}
              className="lms-card"
              style={{ textDecoration: "none", color: "inherit" }}
              aria-label={`Course ${course.course_code} ${course.title}`}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                <div className="lms-card__title" style={{ margin: 0 }}>{course.course_code}</div>
                {enrollmentStatus === "waitlisted" && (
                  <span className="lms-badge lms-badge--normal" aria-label="Waitlisted">Waitlisted</span>
                )}
                {role === "ta" && (
                  <span className="lms-badge" style={{ backgroundColor: "#7c3aed", color: "#fff" }} aria-label="Teaching Assistant">TA</span>
                )}
              </div>
              <div style={{ fontSize: "1.1rem", fontWeight: 500, margin: "0.25rem 0" }}>
                {course.title}
              </div>
              <div style={{ fontSize: "0.85rem", color: "#666" }}>
                {course.instructor_name}
              </div>
              <div style={{ fontSize: "0.85rem", color: "#666" }}>
                {course.semester} -- {course.credits} credits
              </div>
              <div style={{ fontSize: "0.8rem", color: "#888" }} aria-label={`Drop deadline: ${new Date(course.drop_deadline).toLocaleDateString()}`}>
                Drop deadline: {new Date(course.drop_deadline).toLocaleDateString()}
              </div>
              {weightedScore !== null && (
                <div
                  style={{ marginTop: "0.5rem", fontWeight: 600 }}
                  aria-label={`Current grade ${weightedScore}%`}
                >
                  Grade: {weightedScore}%
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
