import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BenchmarkToolbar,
  Toast,
  preserveQueryParams,
  useApi,
  useBenchmarkState,
} from "@breakingweb/shared";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { createPatientPortalApi } from "./api";
import { PatientPortalContext } from "./context";
import type { Patient, Provider } from "./types";

// Use shared preserveQueryParams instead of a session-only local helper —
// internal SPA navigation MUST keep `control=on` or BenchmarkToolbar's
// recorder/heartbeat will silently die. Bug history: a custom session-only
// preserve here caused all in-task navigations on patient_portal to drop the
// recorder; ~45 task-conditions across P4/P3/duplicate annotators
// were affected before this was caught.
const preserveSession = preserveQueryParams;

export function PatientPortalShell({ sessionId }: { sessionId: string }) {
  const location = useLocation();
  const { update, log } = useBenchmarkState("patient_portal");
  const { request } = useApi("patient_portal", sessionId);
  const api = useMemo(() => createPatientPortalApi(request), [request]);

  const [profile, setProfile] = useState<Patient | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [toasts, setToasts] = useState<Array<{ id: string; title: string; description?: string }>>([]);

  const notify = useCallback((title: string, description?: string) => {
    const id = `${title}-${Date.now()}`;
    setToasts((cur) => [...cur, { id, title, description }]);
  }, []);

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

  const refreshProfile = useCallback(async () => {
    try {
      const data = await api.getProfile();
      setProfile(data);
      update({ sessionId, currentRoute: locationRef.current.pathname });
    } catch {
      // silently continue
    }
  }, [api, sessionId, update]);

  const refreshProviders = useCallback(async () => {
    try {
      const data = await api.listProviders();
      setProviders(data);
    } catch {
      // silently continue
    }
  }, [api]);

  const refreshUnread = useCallback(async () => {
    try {
      const msgs = await api.listMessages({ unread: true });
      setUnreadCount(msgs.length);
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void refreshProfile();
      void refreshProviders();
      void refreshUnread();
    }, 120);
    return () => clearTimeout(debounceRef.current);
  }, [location.pathname, location.search, refreshProfile, refreshProviders, refreshUnread]);

  useEffect(() => {
    log("route_change", { pathname: location.pathname, query: location.search, sessionId });
  }, [location.pathname, location.search, log, sessionId]);

  const navItems = [
    { to: "/", label: "Dashboard" },
    { to: "/appointments", label: "Appointments" },
    { to: "/messages", label: "Messages" },
    { to: "/medications", label: "Medications" },
    { to: "/labs", label: "Lab Results" },
    { to: "/referrals", label: "Referrals" },
    { to: "/billing", label: "Billing" },
    { to: "/profile", label: "Profile" },
  ];

  return (
    <PatientPortalContext.Provider
      value={{ sessionId, profile, providers, unreadCount, api, refreshProfile, refreshProviders, refreshUnread, notify }}
    >
      <div className="pp-shell">
        <header className="pp-topbar" role="banner">
          <h1 className="pp-topbar__title">Patient Portal</h1>
          {profile && <span className="pp-topbar__patient">{profile.name}</span>}
        </header>
        <div className="pp-body">
          <nav className="pp-sidebar" aria-label="Patient Portal Navigation">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={preserveSession(item.to, location.search)}
                end={item.to === "/"}
                className={({ isActive }) => `pp-sidebar__link${isActive ? " pp-sidebar__link--active" : ""}`}
                aria-label={item.label === "Messages" && unreadCount > 0 ? `Messages (${unreadCount} unread)` : item.label}
              >
                {item.label}
                {item.label === "Messages" && unreadCount > 0 && (
                  <span className="pp-badge" aria-label={`${unreadCount} unread messages`}>{unreadCount}</span>
                )}
              </NavLink>
            ))}
          </nav>
          <main className="pp-main">
            <Outlet />
          </main>
        </div>
        <Toast messages={toasts} onDismiss={dismissToast} />
        <BenchmarkToolbar envId="patient_portal" sessionId={sessionId} />
      </div>
    </PatientPortalContext.Provider>
  );
}
