import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BenchmarkToolbar,
  Toast,
  preserveQueryParams,
  useApi,
  useBenchmarkState,
} from "@breakingweb/shared";
import { Link, Outlet, useLocation } from "react-router-dom";

import { createLmsApi } from "./api";
import { LmsLayoutContext } from "./context";
import type { Student } from "./types";

export function LmsShell({ sessionId }: { sessionId: string }) {
  const location = useLocation();
  const { update, log } = useBenchmarkState("lms");
  const { request } = useApi("lms", sessionId);
  const api = useMemo(() => createLmsApi(request), [request]);

  const [student, setStudent] = useState<Student | null>(null);
  const [toasts, setToasts] = useState<Array<{ id: string; title: string; description?: string }>>([]);

  const notify = (title: string, description?: string) => {
    const id = `${title}-${Date.now()}`;
    setToasts((cur) => [...cur, { id, title, description }]);
  };

  const dismissToast = (id: string) => {
    setToasts((cur) => cur.filter((t) => t.id !== id));
  };

  useEffect(() => {
    if (toasts.length === 0) return;
    const timer = window.setTimeout(() => setToasts((cur) => cur.slice(1)), 2800);
    return () => window.clearTimeout(timer);
  }, [toasts]);

  const locationRef = useRef(location);
  locationRef.current = location;
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const refreshStudent = useCallback(async () => {
    try {
      const data = await api.getProfile();
      setStudent(data);
      update({
        sessionId,
        currentRoute: locationRef.current.pathname,
      });
    } catch {
      // silently continue
    }
  }, [api, sessionId, update]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void refreshStudent();
    }, 120);
    return () => clearTimeout(debounceRef.current);
  }, [location.pathname, location.search, refreshStudent]);

  useEffect(() => {
    log("route_change", { pathname: location.pathname, query: location.search, sessionId });
  }, [location.pathname, location.search, log, sessionId]);

  return (
    <LmsLayoutContext.Provider value={{ sessionId, student, api, refreshStudent, notify }}>
      <div className="lms-shell">
        <header className="lms-topbar" role="banner">
          <Link
            to={preserveQueryParams("/", location.search)}
            className="lms-topbar__logo"
            aria-label="LMS Home"
          >
            LMS
          </Link>
          <nav className="lms-topbar__nav" aria-label="Main navigation">
            <Link to={preserveQueryParams("/", location.search)} className="lms-topbar__link" aria-label="Dashboard">
              Dashboard
            </Link>
            <Link to={preserveQueryParams("/courses", location.search)} className="lms-topbar__link" aria-label="Courses">
              Courses
            </Link>
            <Link to={preserveQueryParams("/calendar", location.search)} className="lms-topbar__link" aria-label="Calendar">
              Calendar
            </Link>
            <Link to={preserveQueryParams("/peer-reviews", location.search)} className="lms-topbar__link" aria-label="Peer Reviews">
              Peer Reviews
            </Link>
            <Link to={preserveQueryParams("/messages", location.search)} className="lms-topbar__link" aria-label="Messages">
              Messages
            </Link>
          </nav>
          {student && (
            <div className="lms-topbar__user" aria-label="Current user">
              <span>{student.name}</span>
              <span className="lms-topbar__gpa" aria-label={`GPA ${student.gpa}`}>
                GPA: {student.gpa}
              </span>
            </div>
          )}
        </header>

        <div className="lms-body">
          <main className="lms-main">
            <Outlet />
          </main>
        </div>
        <Toast messages={toasts} onDismiss={dismissToast} />
        <BenchmarkToolbar envId="lms" sessionId={sessionId} />
      </div>
    </LmsLayoutContext.Provider>
  );
}
