import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BenchmarkToolbar,
  Button,
  SearchBar,
  Sidebar,
  Toast,
  preserveQueryParams,
  useApi,
  useBenchmarkState,
} from "@breakingweb/shared";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { createGmailApi } from "./api";
import { GmailLayoutContext } from "./context";
import { GmailLogo, IconCompose } from "./icons";
import { inferVisibleThreads, loadMailboxSummary } from "./mailboxSummary";
import type { MailboxSummary } from "./types";

export function GmailShell({ sessionId }: { sessionId: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { update, log } = useBenchmarkState("gmail");
  const { request } = useApi("gmail", sessionId);
  const api = useMemo(() => createGmailApi(request), [request]);
  const [summary, setSummary] = useState<MailboxSummary | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [searchValue, setSearchValue] = useState("");
  const [toasts, setToasts] = useState<Array<{ id: string; title: string; description?: string; onUndo?: () => void }>>([]);

  const notify = (title: string, description?: string, onUndo?: () => void) => {
    const id = `${title}-${Date.now()}-${Math.random()}`;
    setToasts((current) => [...current, { id, title, description, onUndo }]);
    // Each toast auto-dismisses after 3s independently
    window.setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
    }, 3000);
  };

  const dismissToast = (id: string) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  };

  // Refs to break the circular dep: refreshMailbox reads location without
  // depending on it, so its identity stays stable across route changes.
  const locationRef = useRef(location);
  locationRef.current = location;
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const refreshMailbox = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const nextSummary = await loadMailboxSummary(api);
      setSummary(nextSummary);
      const loc = locationRef.current;
      const params = new URLSearchParams(loc.search);
      const currentFilter = params.get("filter");
      update({
        sessionId,
        currentRoute: loc.pathname,
        visibleThreads: inferVisibleThreads(loc.pathname, loc.search, nextSummary.counts),
        currentLabel: currentFilter === "starred"
          ? "starred"
          : (params.get("label") ?? "inbox"),
      });
    } catch {
      // Silently continue — sidebar counts will be stale but the app remains usable
    } finally {
      setIsRefreshing(false);
    }
  }, [api, sessionId, update]);

  useEffect(() => {
    const nextSearch = new URLSearchParams(location.search).get("q") ?? "";
    setSearchValue(nextSearch);
  }, [location.search]);

  // Debounce route-driven refreshes so rapid navigation doesn't spam the API
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { void refreshMailbox(); }, 120);
    return () => clearTimeout(debounceRef.current);
  }, [location.pathname, location.search, refreshMailbox]);

  useEffect(() => {
    log("route_change", { pathname: location.pathname, query: location.search, sessionId });
  }, [location.pathname, location.search, log, sessionId]);

  const handleSearchSubmit = useCallback(() => {
    const query = searchValue.trim();
    log("search_submit", { query, route: location.pathname, sessionId });
    // Include _t param so re-submitting the same query still triggers navigation
    navigate(preserveQueryParams(`/search?q=${encodeURIComponent(query)}&_t=${Date.now()}`, location.search));
  }, [location.pathname, location.search, log, navigate, searchValue, sessionId]);

  const navItems = [
    {
      title: "main",
      items: [
        { label: "Inbox", to: "/inbox?label=inbox", count: summary?.counts.inbox ?? 0 },
        { label: "Starred", to: "/inbox?label=inbox&filter=starred", count: summary?.counts.starred ?? 0 },
        { label: "Sent", to: "/inbox?label=sent", count: summary?.counts.sent ?? 0 },
        { label: "Drafts", to: "/inbox?label=drafts", count: summary?.counts.drafts ?? 0 },
        { label: "Archive", to: "/inbox?label=archived" },
        { label: "Trash", to: "/inbox?label=trash" },
      ],
    },
    {
      title: "manage",
      items: [
        { label: "Settings", to: "/settings" },
        { label: "Labels", to: "/labels" },
        { label: "Contacts", to: "/labels" },
      ],
    },
  ];

  return (
    <GmailLayoutContext.Provider
      value={{ sessionId, summary, isRefreshing, api, refreshMailbox, notify, searchValue, setSearchValue, toasts }}
    >
      <div className="gmail-shell">
        {/* Full-width topbar — matches real Gmail layout */}
        <header className="gmail-topbar" role="banner">
          <div className="gmail-topbar__left">
            <GmailLogo />
            <span className="gmail-topbar__title">Gmail</span>
          </div>
          <div className="gmail-topbar__center">
            <SearchBar
              value={searchValue}
              onChange={setSearchValue}
              onSubmit={handleSearchSubmit}
              placeholder="Search mail"
              ariaLabel="Search mail"
              className="gmail-topbar__search"
            />
          </div>
          <div className="gmail-topbar__right" />
        </header>

        {/* Body: sidebar + content */}
        <div className="gmail-body">
          <nav className="gmail-sidebar" aria-label="Gmail navigation">
            <Button
              variant="primary"
              className="gmail-compose-trigger"
              aria-label="Compose a new message"
              onClick={() => navigate(preserveQueryParams("/compose", location.search))}
            >
              <IconCompose /> Compose
            </Button>
            <Sidebar
              title="Gmail navigation"
              sections={navItems}
              footer={
                new URLSearchParams(location.search).get("agent_mode") === "1"
                  ? undefined
                  : (
                    <a
                      href="/launch"
                      style={{
                        display: "block",
                        padding: "0.5rem 0.75rem",
                        fontSize: "0.85rem",
                        color: "#656d76",
                        textDecoration: "none",
                        borderTop: "1px solid #d0d7de",
                        marginTop: "0.5rem",
                        paddingTop: "0.75rem",
                      }}
                      onMouseOver={(e) => (e.currentTarget.style.color = "#0969da")}
                      onMouseOut={(e) => (e.currentTarget.style.color = "#656d76")}
                    >
                      ← Back to Launcher
                    </a>
                  )
              }
            />
          </nav>
          <div className="gmail-main-column">
            <Outlet />
          </div>
        </div>
        <Toast messages={toasts} onDismiss={dismissToast} />
        <BenchmarkToolbar envId="gmail" sessionId={sessionId} />
      </div>
    </GmailLayoutContext.Provider>
  );
}
