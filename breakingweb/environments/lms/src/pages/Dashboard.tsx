import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useLmsLayout } from "../context";
import type { Announcement, Assignment, Course } from "../types";

export function DashboardPage() {
  const { api, student, notify } = useLmsLayout();
  const location = useLocation();
  const [courses, setCourses] = useState<Course[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [upcomingDeadlines, setUpcomingDeadlines] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [markingRead, setMarkingRead] = useState<Record<string, boolean>>({});
  const [markingAll, setMarkingAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [cs, anns] = await Promise.all([
          api.listCourses(),
          api.listAnnouncements(),
        ]);
        if (cancelled) return;
        setCourses(cs);
        setAnnouncements(anns);

        // Collect all assignments for upcoming deadlines
        const allAssignments: Assignment[] = [];
        for (const course of cs) {
          try {
            const assignments = await api.listAssignments(course.id);
            allAssignments.push(...assignments);
          } catch {
            // skip
          }
        }
        if (cancelled) return;

        const now = new Date();
        const weekFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
        const upcoming = allAssignments
          .filter((a) => {
            const due = new Date(a.due_at);
            return due >= now && due <= weekFromNow &&
              ["not_submitted", "submitted", "resubmit_requested"].includes(a.submission_status);
          })
          .sort((a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime());
        setUpcomingDeadlines(upcoming);
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api]);

  const handleMarkRead = async (id: string) => {
    setMarkingRead((prev) => ({ ...prev, [id]: true }));
    try {
      const updated = await api.markAnnouncementRead(id);
      setAnnouncements((prev) => prev.map((a) => a.id === updated.id ? updated : a));
    } catch {
      notify("Error", "Unable to mark announcement as read");
    } finally {
      setMarkingRead((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleMarkAllRead = async () => {
    setMarkingAll(true);
    try {
      await api.markAllAnnouncementsRead();
      setAnnouncements((prev) => prev.map((a) => ({ ...a, is_read: true })));
      notify("Done", "All announcements marked as read");
    } catch {
      notify("Error", "Unable to mark all announcements as read");
    } finally {
      setMarkingAll(false);
    }
  };

  if (loading) return <div className="lms-loading">Loading...</div>;

  const unreadAnnouncements = announcements.filter((a) => !a.is_read);
  const urgentAnnouncements = announcements.filter((a) => a.priority === "urgent" && !a.is_read);

  return (
    <div aria-label="Dashboard">
      <h1 className="lms-section-header">
        Dashboard
        {student && (
          <span style={{ fontWeight: 400, fontSize: "1rem", marginLeft: "1rem" }}>
            Welcome, {student.name}
          </span>
        )}
      </h1>

      {student && (
        <div className="lms-card" aria-label="Student Info">
          <p>
            <strong>Student:</strong> {student.name} ({student.email})
          </p>
          <p>
            <strong>Student ID:</strong> {student.student_id}
          </p>
          <p>
            <strong>GPA:</strong>{" "}
            <span aria-label={`GPA ${student.gpa}`}>{student.gpa}</span>
          </p>
          <p>
            <strong>Status:</strong>{" "}
            <span className={`lms-badge lms-badge--${student.enrollment_status === "active" ? "available" : "late"}`}>
              {student.enrollment_status}
            </span>
          </p>
          <p>
            <strong>Advisor:</strong> {student.advisor_name}
          </p>
        </div>
      )}

      {/* Upcoming Deadlines */}
      <section aria-label="Upcoming Deadlines" style={{ marginBottom: "1.5rem" }}>
        <h2 className="lms-card__title">Upcoming Deadlines (Next 7 Days)</h2>
        {upcomingDeadlines.length === 0 ? (
          <p className="lms-empty">No upcoming deadlines</p>
        ) : (
          <table className="lms-table" aria-label="Upcoming Deadlines Table">
            <thead>
              <tr>
                <th>Assignment</th>
                <th>Course</th>
                <th>Due Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {upcomingDeadlines.map((a) => {
                const course = courses.find((c) => c.id === a.course_id);
                return (
                  <tr key={a.id}>
                    <td>
                      <Link
                        to={preserveQueryParams(`/courses/${a.course_id}/assignments/${a.id}`, location.search)}
                        className="lms-link"
                        aria-label={`Assignment ${a.title}`}
                      >
                        {a.title}
                      </Link>
                    </td>
                    <td>{course?.course_code ?? a.course_id}</td>
                    <td>{new Date(a.due_at).toLocaleDateString()}</td>
                    <td>
                      <span className={`lms-badge lms-badge--${a.submission_status}`}>
                        {a.submission_status.replace(/_/g, " ")}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* Announcements */}
      <section aria-label="Announcements" style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
          <h2 className="lms-card__title" style={{ margin: 0 }}>
            Announcements
            {unreadAnnouncements.length > 0 && (
              <span style={{ fontWeight: 400, fontSize: "0.9rem", marginLeft: "0.5rem" }}>
                ({unreadAnnouncements.length} unread)
              </span>
            )}
          </h2>
          {unreadAnnouncements.length > 0 && (
            <button
              type="button"
              className="lms-btn lms-btn--secondary"
              onClick={handleMarkAllRead}
              disabled={markingAll}
              aria-label="Mark all announcements as read"
            >
              {markingAll ? "Marking..." : "Mark All as Read"}
            </button>
          )}
        </div>
        {announcements.length === 0 ? (
          <p className="lms-empty">No announcements</p>
        ) : (
          <div>
            {urgentAnnouncements.length > 0 && (
              <div style={{ marginBottom: "0.5rem" }}>
                {urgentAnnouncements.map((a) => {
                  const course = courses.find((c) => c.id === a.course_id);
                  return (
                    <div key={a.id} className="lms-card" style={{ borderLeft: "4px solid #c62828" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <strong>{a.title}</strong>
                        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                          <span className="lms-badge lms-badge--urgent" aria-label="Urgent announcement">Urgent</span>
                          <button
                            type="button"
                            className="lms-btn lms-btn--secondary"
                            onClick={() => handleMarkRead(a.id)}
                            disabled={markingRead[a.id]}
                            aria-label={`Mark announcement "${a.title}" as read`}
                            style={{ fontSize: "0.8rem", padding: "0.2rem 0.5rem" }}
                          >
                            {markingRead[a.id] ? "..." : "Mark as Read"}
                          </button>
                        </div>
                      </div>
                      <p style={{ fontSize: "0.9rem", margin: "0.25rem 0" }}>{a.body}</p>
                      <span style={{ fontSize: "0.8rem", color: "#666" }}>
                        {course?.course_code} -- {new Date(a.posted_at).toLocaleDateString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            {announcements
              .filter((a) => a.priority !== "urgent" || a.is_read)
              .slice(0, 5)
              .map((a) => {
                const course = courses.find((c) => c.id === a.course_id);
                return (
                  <div
                    key={a.id}
                    className="lms-card"
                    style={{ opacity: a.is_read ? 0.7 : 1 }}
                    aria-label={`Announcement: ${a.title}`}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: a.is_read ? 400 : 700 }}>{a.title}</span>
                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                        {!a.is_read && (
                          <span className="lms-badge lms-badge--normal">New</span>
                        )}
                        {!a.is_read && (
                          <button
                            type="button"
                            className="lms-btn lms-btn--secondary"
                            onClick={() => handleMarkRead(a.id)}
                            disabled={markingRead[a.id]}
                            aria-label={`Mark announcement "${a.title}" as read`}
                            style={{ fontSize: "0.8rem", padding: "0.2rem 0.5rem" }}
                          >
                            {markingRead[a.id] ? "..." : "Mark as Read"}
                          </button>
                        )}
                      </div>
                    </div>
                    <p style={{ fontSize: "0.9rem", margin: "0.25rem 0" }}>{a.body}</p>
                    <span style={{ fontSize: "0.8rem", color: "#666" }}>
                      {course?.course_code} -- {new Date(a.posted_at).toLocaleDateString()}
                    </span>
                  </div>
                );
              })}
          </div>
        )}
      </section>

      {/* Quick Links to Courses */}
      <section aria-label="Enrolled Courses">
        <h2 className="lms-card__title">My Courses</h2>
        <div className="lms-grid">
          {courses.map((c) => (
            <Link
              key={c.id}
              to={preserveQueryParams(`/courses/${c.id}`, location.search)}
              className="lms-card lms-link"
              style={{ textDecoration: "none", color: "inherit" }}
              aria-label={`Course ${c.course_code} ${c.title}`}
            >
              <div className="lms-card__title">{c.course_code}</div>
              <div>{c.title}</div>
              <div style={{ fontSize: "0.85rem", color: "#666", marginTop: "0.25rem" }}>
                {c.instructor_name} -- {c.semester}
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
