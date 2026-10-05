import { useState, useMemo, useCallback, useEffect, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useApi, useSession, useBenchmarkState, BenchmarkToolbar, preserveQueryParams } from "@breakingweb/shared";
import { createBookingApi } from "./api";
import { BookingLayoutContext, type ToastMessage } from "./context";

function Navbar() {
  const location = useLocation();
  const qp = (path: string) => preserveQueryParams(path, location.search);
  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <header className="bk-header">
      <div className="bk-header-top">
        <Link to={qp("/home")} className="bk-logo">Booking.com</Link>
        <nav className="bk-header-nav">
          <Link to={qp("/deals")} className={`bk-nav-btn ${isActive("/deals") ? "active" : ""}`}>
            Deals
          </Link>
          <Link to={qp("/trips")} className={`bk-nav-btn ${isActive("/trips") ? "active" : ""}`}>
            My Trips
          </Link>
          <Link to={qp("/saved")} className={`bk-nav-btn ${isActive("/saved") ? "active" : ""}`}>
            Saved
          </Link>
          <Link to={qp("/messages")} className={`bk-nav-btn ${isActive("/messages") ? "active" : ""}`}>
            Messages
          </Link>
          <Link to={qp("/notifications")} className={`bk-nav-btn ${isActive("/notifications") ? "active" : ""}`}>
            Notifications
          </Link>
          <Link to={qp("/account")} className="bk-nav-btn bk-nav-btn--primary">
            Account
          </Link>
        </nav>
      </div>
      <div className="bk-header-tabs">
        <div className="bk-header-tabs-inner">
          <Link to={qp("/home")} className={`bk-tab ${isActive("/home") ? "active" : ""}`}>
            Stays
          </Link>
          <Link to={qp("/search")} className={`bk-tab ${isActive("/search") || isActive("/property") ? "active" : ""}`}>
            Search
          </Link>
          <Link to={qp("/reviews")} className={`bk-tab ${isActive("/reviews") ? "active" : ""}`}>
            Reviews
          </Link>
          <Link to={qp("/settings")} className={`bk-tab ${isActive("/settings") ? "active" : ""}`}>
            Settings
          </Link>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="bk-footer">
      <p>Simulated Booking.com environment for BreakingWeb</p>
      <p style={{ marginTop: 4, opacity: 0.7 }}>
        This is a benchmark environment. No real bookings are made.
      </p>
    </footer>
  );
}

export default function BookingShell({ children }: { children: ReactNode }) {
  // sessionId is guaranteed non-null here because App only renders Shell
  // when sessionId is truthy.
  const { sessionId: rawSessionId } = useSession("booking");
  const sessionId = rawSessionId!;
  const { request } = useApi("booking", sessionId);
  const { log } = useBenchmarkState("booking");
  const location = useLocation();

  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const api = useMemo(() => createBookingApi(request), [request]);

  const notify = useCallback((title: string, description?: string) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { id, title, description }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  // Log route changes
  useEffect(() => {
    log("route_change", { path: location.pathname, search: location.search });
  }, [location.pathname, location.search, log]);

  return (
    <BookingLayoutContext.Provider value={{ sessionId, api, notify, toasts }}>
      <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <Navbar />
        <main className="bk-main" style={{ flex: 1 }}>
          {children}
        </main>
        <Footer />
      </div>

      {/* Toast notifications */}
      {toasts.length > 0 && (
        <div className="bk-toast-container">
          {toasts.map((t) => (
            <div key={t.id} className="bk-toast">
              <div className="bk-toast-title">{t.title}</div>
              {t.description && <div className="bk-toast-desc">{t.description}</div>}
            </div>
          ))}
        </div>
      )}

      <BenchmarkToolbar envId="booking" sessionId={sessionId} />
    </BookingLayoutContext.Provider>
  );
}
