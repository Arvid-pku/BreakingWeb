import { useEffect, useState } from "react";

import { useLmsLayout } from "../context";
import type { CalendarEvent, Course } from "../types";

const EVENT_TYPE_LABELS: Record<string, string> = {
  lecture: "Lecture",
  office_hours: "Office Hours",
  exam: "Exam",
  deadline: "Deadline",
  lab: "Lab",
};

export function CalendarPage() {
  const { api } = useLmsLayout();

  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [filterType, setFilterType] = useState<string>("all");
  const [filterCourse, setFilterCourse] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [evts, cs] = await Promise.all([
          api.getCalendar(),
          api.listCourses(),
        ]);
        if (!cancelled) {
          setEvents(evts);
          setCourses(cs);
        }
      } catch {
        // handled
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [api]);

  if (loading) return <div className="lms-loading">Loading...</div>;

  // Apply filters
  let filtered = [...events];
  if (filterType !== "all") {
    filtered = filtered.filter((e) => e.event_type === filterType);
  }
  if (filterCourse !== "all") {
    filtered = filtered.filter((e) => e.course_id === filterCourse);
  }

  // Sort by date
  filtered.sort(
    (a, b) => new Date(a.start_datetime).getTime() - new Date(b.start_datetime).getTime(),
  );

  const courseMap = new Map(courses.map((c) => [c.id, c]));

  return (
    <div aria-label="Calendar">
      <h1 className="lms-section-header">Calendar</h1>

      {/* Filters */}
      <div className="lms-card" style={{ display: "flex", gap: "1rem", alignItems: "center" }} aria-label="Calendar Filters">
        <label htmlFor="filter-type" style={{ fontWeight: 500 }}>
          Event type:
        </label>
        <select
          id="filter-type"
          className="lms-input"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          aria-label="Filter by event type"
        >
          <option value="all">All types</option>
          <option value="lecture">Lecture</option>
          <option value="office_hours">Office Hours</option>
          <option value="exam">Exam</option>
          <option value="deadline">Deadline</option>
          <option value="lab">Lab</option>
        </select>

        <label htmlFor="filter-course" style={{ fontWeight: 500 }}>
          Course:
        </label>
        <select
          id="filter-course"
          className="lms-input"
          value={filterCourse}
          onChange={(e) => setFilterCourse(e.target.value)}
          aria-label="Filter by course"
        >
          <option value="all">All courses</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.course_code}
            </option>
          ))}
        </select>
      </div>

      {/* Events List */}
      <section aria-label="Calendar Events">
        {filtered.length === 0 ? (
          <p className="lms-empty">No events match the current filters</p>
        ) : (
          <div>
            {filtered.map((event) => {
              const course = courseMap.get(event.course_id);
              const startDate = new Date(event.start_datetime);
              const endDate = new Date(event.end_datetime);
              return (
                <div
                  key={event.id}
                  className="lms-card"
                  aria-label={`Event: ${event.title} on ${startDate.toLocaleDateString()}`}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <span
                        className={`lms-badge lms-badge--${event.event_type}`}
                        aria-label={`Type: ${EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}`}
                      >
                        {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
                      </span>
                      <span style={{ marginLeft: "0.5rem", fontWeight: 500 }}>
                        {course?.course_code ?? event.course_id}
                      </span>
                    </div>
                    <span style={{ fontSize: "0.85rem", color: "#666" }}>
                      {startDate.toLocaleDateString()}
                    </span>
                  </div>
                  <div style={{ marginTop: "0.25rem", fontWeight: 600 }}>
                    {event.title}
                  </div>
                  <div style={{ fontSize: "0.85rem", color: "#666", marginTop: "0.25rem" }}>
                    {startDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    {" - "}
                    {endDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    {event.location && ` -- ${event.location}`}
                  </div>
                  {event.recurrence !== "none" && (
                    <div style={{ fontSize: "0.8rem", color: "#999", marginTop: "0.25rem" }}>
                      Repeats {event.recurrence}
                      {event.recurrence_end_date && ` until ${new Date(event.recurrence_end_date).toLocaleDateString()}`}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
