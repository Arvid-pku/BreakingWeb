import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { preserveQueryParams, Tabs } from "@breakingweb/shared";

import { useLmsLayout } from "../context";
import type { LmsLayoutContextValue } from "../context";
import type {
  Announcement,
  Assignment,
  Course,
  Discussion,
  Grade,
  Module,
} from "../types";

type LmsApi = LmsLayoutContextValue["api"];

const TABS = [
  { label: "Modules", value: "modules" },
  { label: "Assignments", value: "assignments" },
  { label: "Discussions", value: "discussions" },
  { label: "Announcements", value: "announcements" },
  { label: "Grades", value: "grades" },
  { label: "Syllabus", value: "syllabus" },
];

function tabFromPath(pathname: string): string | null {
  const normalized = pathname.split("?")[0];
  const segments = normalized.split("/").filter((segment) => segment.length > 0);
  if (segments[0] !== "courses") return null;

  const last = segments[segments.length - 1] ?? "";
  if (["modules", "assignments", "discussions", "announcements", "grades", "syllabus"].includes(last)) {
    return last;
  }

  const penultimate = segments[segments.length - 2];
  if (penultimate && ["modules", "assignments", "discussions", "announcements"].includes(penultimate)) {
    return penultimate;
  }
  return null;
}

export function CourseViewPage() {
  const { id } = useParams<{ id: string }>();
  const courseId = id!;
  const { api, notify } = useLmsLayout();
  const location = useLocation();

  const [course, setCourse] = useState<Course | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [discussions, setDiscussions] = useState<Discussion[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [gradesData, setGradesData] = useState<{
    weighted_score: string | null;
    category_scores: Record<string, string | null>;
    grades: Grade[];
  } | null>(null);
  const [activeTab, setActiveTab] = useState("modules");
  const [loading, setLoading] = useState(true);
  const [enrollmentStatus, setEnrollmentStatus] = useState<"enrolled" | "waitlisted" | "dropped" | "completed" | null>(null);
  const [dropConfirm, setDropConfirm] = useState(false);
  const [dropping, setDropping] = useState(false);
  const inferredTab = useMemo(() => tabFromPath(location.pathname), [location.pathname]);

  useEffect(() => {
    if (inferredTab) {
      setActiveTab(inferredTab);
    }
  }, [inferredTab]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [c, mods, assigns, discs, anns, gd, enrollments] = await Promise.all([
          api.getCourse(courseId),
          api.listModules(courseId),
          api.listAssignments(courseId),
          api.listDiscussions(courseId),
          api.listAnnouncements(courseId),
          api.getCourseGrades(courseId),
          api.listEnrollments(),
        ]);
        if (!cancelled) {
          setCourse(c);
          setModules(mods);
          setAssignments(assigns);
          setDiscussions(discs);
          setAnnouncements(anns);
          setGradesData(gd);
          const enrollment = enrollments.find((e) => e.course_id === courseId);
          setEnrollmentStatus(enrollment?.status ?? null);
        }
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api, courseId]);

  const handleDrop = async () => {
    setDropping(true);
    try {
      await api.dropCourse(courseId);
      setEnrollmentStatus("dropped");
      setDropConfirm(false);
      notify("Course Dropped", `You have dropped ${course?.course_code}`);
    } catch {
      notify("Error", "Unable to drop course");
    } finally {
      setDropping(false);
    }
  };

  if (loading) return <div className="lms-loading">Loading...</div>;
  if (!course) return <div className="lms-empty">Course not found</div>;

  const canDrop = enrollmentStatus === "enrolled" && new Date() < new Date(course.drop_deadline);

  return (
    <div aria-label={`Course ${course.course_code} ${course.title}`}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
        <h1 className="lms-section-header" style={{ margin: 0 }}>
          {course.course_code}: {course.title}
        </h1>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {enrollmentStatus === "dropped" && (
            <span className="lms-badge lms-badge--late" aria-label="Enrollment status: Dropped">Dropped</span>
          )}
          {canDrop && !dropConfirm && (
            <button
              type="button"
              className="lms-btn lms-btn--secondary"
              onClick={() => setDropConfirm(true)}
              aria-label={`Drop course ${course.course_code}`}
            >
              Drop Course
            </button>
          )}
          {canDrop && dropConfirm && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.9rem" }}>Drop {course.course_code}?</span>
              <button
                type="button"
                className="lms-btn lms-btn--primary"
                onClick={handleDrop}
                disabled={dropping}
                aria-label={`Confirm drop course ${course.course_code}`}
              >
                {dropping ? "Dropping..." : "Confirm"}
              </button>
              <button
                type="button"
                className="lms-btn lms-btn--secondary"
                onClick={() => setDropConfirm(false)}
                aria-label="Cancel drop course"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
      <p style={{ color: "#666", marginBottom: "1rem", marginTop: "0.25rem" }}>
        {course.instructor_name} -- {course.semester} -- {course.credits} credits
      </p>

      <Tabs label="Course sections" items={TABS} value={activeTab} onChange={setActiveTab} />

      <div style={{ marginTop: "1rem" }}>
        {activeTab === "modules" && (
          <ModulesTab modules={modules} assignments={assignments} courseId={courseId} api={api} onModulesChange={setModules} notify={notify} />
        )}
        {activeTab === "assignments" && (
          <AssignmentsTab assignments={assignments} courseId={courseId} />
        )}
        {activeTab === "discussions" && (
          <DiscussionsTab discussions={discussions} courseId={courseId} />
        )}
        {activeTab === "announcements" && (
          <AnnouncementsTab
            announcements={announcements}
            api={api}
            onAnnouncementsChange={setAnnouncements}
            notify={notify}
          />
        )}
        {activeTab === "grades" && gradesData && (
          <GradesTab course={course} gradesData={gradesData} assignments={assignments} />
        )}
        {activeTab === "syllabus" && (
          <SyllabusTab course={course} />
        )}
      </div>
    </div>
  );
}

/* --- Modules Tab --- */

function ModulesTab({
  modules,
  assignments,
  courseId,
  api,
  onModulesChange,
  notify,
}: {
  modules: Module[];
  assignments: Assignment[];
  courseId: string;
  api: LmsApi;
  onModulesChange: (mods: Module[]) => void;
  notify: (title: string, body: string) => void;
}) {
  const [completing, setCompleting] = useState<Record<string, boolean>>({});
  const location = useLocation();
  const assignmentById = useMemo(
    () => new Map(assignments.map((assignment) => [assignment.id, assignment])),
    [assignments],
  );

  const handleCompleteItem = async (moduleId: string, itemIndex: number) => {
    const key = `${moduleId}:${itemIndex}`;
    setCompleting((prev) => ({ ...prev, [key]: true }));
    try {
      const updated = await api.completeModuleItem(moduleId, itemIndex);
      onModulesChange(updated.modules ?? modules.map((m) => m.id === updated.module.id ? updated.module : m));
    } catch {
      notify("Error", "Unable to complete item");
    } finally {
      setCompleting((prev) => ({ ...prev, [key]: false }));
    }
  };

  const handleCompleteModule = async (moduleId: string) => {
    setCompleting((prev) => ({ ...prev, [moduleId]: true }));
    try {
      const updated = await api.completeModule(moduleId);
      onModulesChange(updated.modules ?? modules.map((m) => m.id === updated.module.id ? updated.module : m));
      notify("Module Complete", "Module marked as complete");
    } catch {
      notify("Error", "Unable to complete module");
    } finally {
      setCompleting((prev) => ({ ...prev, [moduleId]: false }));
    }
  };

  return (
    <section aria-label="Modules">
      {modules.length === 0 ? (
        <p className="lms-empty">No modules</p>
      ) : (
        <ol style={{ listStyle: "none", padding: 0 }}>
          {modules.map((mod) => {
            const isLocked = mod.status === "locked";
            const allItemsDone = mod.content_items.length > 0 && mod.content_items.every((i) => i.completed);
            return (
              <li key={mod.id} className="lms-card" aria-label={`Module ${mod.title}`}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                  {isLocked && (
                    <span className="lms-lock-icon" aria-label="Locked module" role="img">
                      &#x1f512;
                    </span>
                  )}
                  <strong>{mod.title}</strong>
                  <span className={`lms-badge lms-badge--${mod.status}`} aria-label={`Status: ${mod.status}`}>
                    {mod.status}
                  </span>
                  {isLocked && (
                    <span className="lms-badge lms-badge--locked" aria-label="Module is locked">Locked</span>
                  )}
                  {!isLocked && mod.status !== "completed" && allItemsDone && (
                    <button
                      type="button"
                      className="lms-btn lms-btn--primary"
                      onClick={() => handleCompleteModule(mod.id)}
                      disabled={completing[mod.id]}
                      aria-label={`Complete module ${mod.title}`}
                      style={{ fontSize: "0.85rem", padding: "0.2rem 0.6rem" }}
                    >
                      {completing[mod.id] ? "Completing..." : "Complete Module"}
                    </button>
                  )}
                </div>
                {isLocked && mod.unlock_condition !== "none" && (
                  <p style={{ fontSize: "0.85rem", color: "#888", margin: "0.25rem 0 0" }}>
                    {mod.unlock_condition === "prerequisite" && (
                      <>Requires: {mod.unlock_value.join(", ")} (completed)</>
                    )}
                    {mod.unlock_condition === "min_score" && (
                      <>
                        Requires:{" "}
                        {mod.unlock_value.map((v) => {
                          const parts = v.split(":");
                          return `${parts[0]} (score >= ${parts[1] ?? "0"})`;
                        }).join(", ")}
                      </>
                    )}
                    {mod.unlock_condition === "date" && (
                      <>Available after: {mod.unlock_value[0] ? new Date(mod.unlock_value[0]).toLocaleDateString() : "TBD"}</>
                    )}
                  </p>
                )}
                {mod.content_items.length > 0 && (
                  <ul style={{ marginTop: "0.5rem", paddingLeft: "1.25rem" }}>
                    {mod.content_items.map((item, idx) => {
                      const key = `${mod.id}:${idx}`;
                      const linkedAssignment = item.linked_assignment_id ? assignmentById.get(item.linked_assignment_id) : null;
                      return (
                        <li
                          key={idx}
                          style={{ fontSize: "0.9rem", marginBottom: "0.25rem", display: "flex", alignItems: "center", gap: "0.5rem" }}
                          aria-label={`Content item: ${item.title}${item.completed ? " (completed)" : ""}`}
                        >
                          <span style={{ marginRight: "0.25rem" }}>
                            {item.completed ? "\u2705" : "\u2B1C"}
                          </span>
                          <span>{item.title}</span>
                          <span style={{ color: "#999", fontSize: "0.8rem" }}>
                            ({item.type})
                          </span>
                          {linkedAssignment && (
                            <Link
                              to={preserveQueryParams(`/courses/${courseId}/assignments/${linkedAssignment.id}`, location.search)}
                              className="lms-link"
                              aria-label={`Linked assignment ${linkedAssignment.title}`}
                            >
                              Linked assignment: {linkedAssignment.title}
                            </Link>
                          )}
                          {!isLocked && !item.completed && (
                            <button
                              type="button"
                              className="lms-btn lms-btn--secondary"
                              onClick={() => handleCompleteItem(mod.id, idx)}
                              disabled={completing[key]}
                              aria-label={`Mark "${item.title}" as complete`}
                              style={{ fontSize: "0.75rem", padding: "0.1rem 0.4rem", marginLeft: "0.25rem" }}
                            >
                              {completing[key] ? "..." : "Complete"}
                            </button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

/* --- Assignments Tab --- */

function AssignmentsTab({ assignments, courseId }: { assignments: Assignment[]; courseId: string }) {
  const location = useLocation();

  return (
    <section aria-label="Assignments">
      {assignments.length === 0 ? (
        <p className="lms-empty">No assignments</p>
      ) : (
        <table className="lms-table" aria-label="Assignments Table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Type</th>
              <th>Category</th>
              <th>Due Date</th>
              <th>Status</th>
              <th>Feedback</th>
              <th>Score</th>
              <th>Points</th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((a) => {
              const feedbackAvailable = !!(a.feedback && a.feedback.trim().length > 0);
              return (
                <tr key={a.id}>
                  <td>
                    <Link
                      to={preserveQueryParams(`/courses/${courseId}/assignments/${a.id}`, location.search)}
                      className="lms-link"
                      aria-label={`Assignment ${a.title} (category ${a.weight_category}, status ${a.submission_status.replace(/_/g, " ")}${feedbackAvailable ? ", feedback available" : ""})`}
                    >
                      {a.title}
                    </Link>
                  </td>
                  <td>{a.type}</td>
                  <td>
                    <span
                      className={`lms-badge lms-badge--category-${a.weight_category}`}
                      aria-label={`Weight category: ${a.weight_category}`}
                    >
                      {a.weight_category}
                    </span>
                  </td>
                  <td>{new Date(a.due_at).toLocaleDateString()}</td>
                  <td>
                    <span
                      className={`lms-badge lms-badge--${a.submission_status}`}
                      aria-label={`Submission status: ${a.submission_status.replace(/_/g, " ")}`}
                    >
                      {a.submission_status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td>
                    {feedbackAvailable ? (
                      <span
                        className="lms-badge lms-badge--feedback"
                        aria-label="Feedback available"
                      >
                        feedback
                      </span>
                    ) : (
                      <span aria-label="No feedback" style={{ color: "#999" }}>-</span>
                    )}
                  </td>
                  <td>{a.score ?? "-"}</td>
                  <td>{a.points_possible}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

/* --- Discussions Tab --- */

function DiscussionsTab({ discussions, courseId }: { discussions: Discussion[]; courseId: string }) {
  const location = useLocation();

  return (
    <section aria-label="Discussions">
      {discussions.length === 0 ? (
        <p className="lms-empty">No discussions</p>
      ) : (
        <div>
          {discussions.map((d) => (
            <Link
              key={d.id}
              to={preserveQueryParams(`/courses/${courseId}/discussions/${d.id}`, location.search)}
              className="lms-card"
              style={{ display: "block", textDecoration: "none", color: "inherit" }}
              aria-label={`Discussion ${d.title}`}
            >
              <div className="lms-card__title">{d.title}</div>
              <div style={{ fontSize: "0.85rem", color: "#666" }}>
                Due: {new Date(d.due_at).toLocaleDateString()} --
                Min posts: {d.min_posts}, Min replies: {d.min_replies} --
                {d.points_possible} points
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

/* --- Announcements Tab --- */

function AnnouncementsTab({
  announcements,
  api,
  onAnnouncementsChange,
  notify,
}: {
  announcements: Announcement[];
  api: LmsApi;
  onAnnouncementsChange: (anns: Announcement[]) => void;
  notify: (title: string, body: string) => void;
}) {
  const [marking, setMarking] = useState<Record<string, boolean>>({});

  const handleMarkRead = async (announcementId: string) => {
    setMarking((prev) => ({ ...prev, [announcementId]: true }));
    try {
      const updated = await api.markAnnouncementRead(announcementId);
      onAnnouncementsChange(
        announcements.map((a) => (a.id === updated.id ? updated : a)),
      );
    } catch {
      notify("Error", "Unable to mark announcement as read");
    } finally {
      setMarking((prev) => ({ ...prev, [announcementId]: false }));
    }
  };

  return (
    <section aria-label="Announcements">
      {announcements.length === 0 ? (
        <p className="lms-empty">No announcements</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {announcements.map((a) => (
            <li
              key={a.id}
              className="lms-card"
              aria-label={`Announcement: ${a.title}${a.is_read ? " (read)" : " (unread)"}`}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                <strong>{a.title}</strong>
                {a.priority === "urgent" && (
                  <span className="lms-badge lms-badge--urgent" aria-label="Urgent announcement">
                    Urgent
                  </span>
                )}
                {!a.is_read && (
                  <span className="lms-badge lms-badge--unread" aria-label="Unread announcement">
                    Unread
                  </span>
                )}
              </div>
              <p style={{ fontSize: "0.85rem", color: "#666", margin: "0.25rem 0" }}>
                Posted: {new Date(a.posted_at).toLocaleString()}
              </p>
              <p style={{ margin: "0.5rem 0" }}>{a.body}</p>
              {!a.is_read && (
                <button
                  type="button"
                  className="lms-btn lms-btn--secondary"
                  onClick={() => handleMarkRead(a.id)}
                  disabled={marking[a.id]}
                  aria-label={`Mark announcement "${a.title}" as read`}
                  style={{ fontSize: "0.85rem", padding: "0.2rem 0.6rem" }}
                >
                  {marking[a.id] ? "Marking..." : "Mark as read"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* --- Grades Tab --- */

function GradesTab({
  course,
  gradesData,
  assignments,
}: {
  course: Course;
  gradesData: {
    weighted_score: string | null;
    category_scores: Record<string, string | null>;
    grades: Grade[];
  };
  assignments: Assignment[];
}) {
  const policy = course.syllabus.grading_policy;

  return (
    <section aria-label="Grade Breakdown">
      <div style={{ marginBottom: "1rem" }}>
        <strong>Overall Weighted Score: </strong>
        <span aria-label={`Overall weighted score ${gradesData.weighted_score ?? "N/A"}%`}>
          {gradesData.weighted_score ? `${gradesData.weighted_score}%` : "N/A"}
        </span>
      </div>

      <table className="lms-table" aria-label="Grade Breakdown Table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Weight</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(policy).map(([catName, catPolicy]) => (
            <tr key={catName}>
              <td>{catName}</td>
              <td>{(parseFloat(catPolicy.weight) * 100).toFixed(0)}%</td>
              <td>
                {gradesData.category_scores[catName]
                  ? `${gradesData.category_scores[catName]}%`
                  : "N/A"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: "1.5rem" }}>Assignment Details</h3>
      <table className="lms-table" aria-label="Assignment Grades">
        <thead>
          <tr>
            <th>Assignment</th>
            <th>Category</th>
            <th>Score</th>
            <th>Points</th>
            <th>%</th>
            <th>Late Penalty</th>
            <th>Dropped</th>
          </tr>
        </thead>
        <tbody>
          {gradesData.grades.map((g) => {
            const assignment = assignments.find((a) => a.id === g.assignment_id);
            const pct = g.score !== null
              ? ((parseFloat(g.score) / parseFloat(g.points_possible)) * 100).toFixed(1)
              : "-";
            return (
              <tr
                key={g.id}
                className={g.is_dropped ? "lms-dropped" : ""}
              >
                <td>{assignment?.title ?? g.assignment_id}</td>
                <td>{g.weight_category}</td>
                <td>{g.score ?? "-"}</td>
                <td>{g.points_possible}</td>
                <td>{pct}</td>
                <td>
                  {parseFloat(g.late_penalty_applied) > 0
                    ? `${(parseFloat(g.late_penalty_applied) * 100).toFixed(0)}%`
                    : "-"}
                </td>
                <td>
                  {g.is_dropped && (
                    <span className="lms-badge lms-badge--dropped" aria-label="Dropped">
                      Dropped
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

/* --- Syllabus Tab --- */

function SyllabusTab({ course }: { course: Course }) {
  const policy = course.syllabus.grading_policy;
  const latePolicy = course.syllabus.late_policy;

  return (
    <section aria-label="Syllabus">
      <h3>Grading Policy</h3>
      <table className="lms-table" aria-label="Grading Policy">
        <thead>
          <tr>
            <th>Category</th>
            <th>Weight</th>
            <th>Drop Lowest</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(policy).map(([name, p]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{(parseFloat(p.weight) * 100).toFixed(0)}%</td>
              <td>{p.drop_lowest > 0 ? p.drop_lowest : "None"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: "1.5rem" }}>Late Policy</h3>
      <div className="lms-card" aria-label="Late Policy Details">
        <p><strong>Penalty per day:</strong> {(parseFloat(latePolicy.penalty_per_day) * 100).toFixed(0)}% per day</p>
        <p><strong>Max late days:</strong> {latePolicy.max_late_days}</p>
        <p><strong>Grace period:</strong> {latePolicy.grace_period_hours} hours</p>
      </div>

      <h3 style={{ marginTop: "1.5rem" }}>Important Dates</h3>
      <div className="lms-card" aria-label="Important Dates">
        <p><strong>Drop deadline:</strong> {new Date(course.drop_deadline).toLocaleDateString()}</p>
        <p><strong>Final exam:</strong> {new Date(course.final_exam_date).toLocaleDateString()}</p>
      </div>

      <h3 style={{ marginTop: "1.5rem" }}>Grade Scale</h3>
      <div className="lms-card" aria-label="Grade Scale">
        <table className="lms-table" aria-label="Grade Scale Table">
          <thead>
            <tr>
              <th>Grade</th>
              <th>Range</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>A</td><td>90–100%</td></tr>
            <tr><td>B</td><td>80–89%</td></tr>
            <tr><td>C</td><td>70–79%</td></tr>
            <tr><td>D</td><td>60–69%</td></tr>
            <tr><td>F</td><td>below 60%</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
