import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BenchmarkToolbar,
  SearchBar,
  Sidebar,
  Toast,
  preserveQueryParams,
  useApi,
  useBenchmarkState,
} from "@breakingweb/shared";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { createRedditApi } from "./api";
import { RedditLayoutContext } from "./context";
import type { MyProfile, RedditSettings } from "./types";
import { activateOnKeyDown } from "./utils";

export function RedditShell({ sessionId }: { sessionId: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { update, log } = useBenchmarkState("reddit");
  const { request } = useApi("reddit", sessionId);
  const api = useMemo(() => createRedditApi(request), [request]);
  const [profile, setProfile] = useState<MyProfile | null>(null);
  const [settings, setSettings] = useState<RedditSettings | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [searchValue, setSearchValue] = useState("");
  const [toasts, setToasts] = useState<Array<{ id: string; title: string; description?: string }>>([]);

  const notify = useCallback((title: string, description?: string) => {
    const id = `${title}-${Date.now()}-${Math.random()}`;
    setToasts((current) => [...current, { id, title, description }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const locationRef = useRef(location);
  locationRef.current = location;

  const refreshProfile = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const nextProfile = await api.getMyProfile();
      setProfile(nextProfile);
    } catch {
      // Silently continue
    } finally {
      setIsRefreshing(false);
    }
  }, [api]);

  const refreshSettings = useCallback(async () => {
    const nextSettings = await api.getSettings();
    setSettings(nextSettings);
    return nextSettings;
  }, [api]);

  const updateSettings = useCallback(async (updates: Partial<RedditSettings>) => {
    const nextSettings = await api.updateSettings(updates);
    setSettings(nextSettings);
    return nextSettings;
  }, [api]);

  // Fetch profile and settings once on mount only
  const hasBootstrapped = useRef(false);
  useEffect(() => {
    if (hasBootstrapped.current) return;
    hasBootstrapped.current = true;
    void refreshProfile();
    void refreshSettings().catch(() => {});
  }, [refreshProfile, refreshSettings]);

  useEffect(() => {
    const nextSearch = new URLSearchParams(location.search).get("q") ?? "";
    setSearchValue(nextSearch);
  }, [location.search]);

  // Stable refs for logging — avoids re-render cascades
  const logRef = useRef(log);
  logRef.current = log;
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  useEffect(() => {
    logRef.current("route_change", { pathname: location.pathname, query: location.search, sessionId: sessionIdRef.current });
  }, [location.pathname, location.search]);

  const handleSearchSubmit = useCallback(() => {
    const query = searchValue.trim();
    logRef.current("search_submit", { query, route: location.pathname, sessionId: sessionIdRef.current });
    navigate(preserveQueryParams(`/search?q=${encodeURIComponent(query)}&_t=${Date.now()}`, location.search));
  }, [location.pathname, location.search, navigate, searchValue]);

  const navItems = [
    {
      title: "feeds",
      items: [
        { label: "Home", to: "/feed" },
        { label: "Popular", to: "/feed?sort=hot" },
      ],
    },
    {
      title: "communities",
      items: (profile?.subscriptions ?? []).slice(0, 10).map((sub) => ({
        label: `r/${sub.name}`,
        to: `/r/${sub.name}`,
      })),
    },
    {
      title: "other",
      items: [
        { label: "Messages", to: "/messages", count: profile?.unread_messages ?? 0 },
        { label: "Notifications", to: "/notifications", count: profile?.unread_notifications ?? 0 },
        { label: "Saved", to: "/saved" },
        { label: "Profile", to: `/u/${profile?.username ?? "me"}` },
        { label: "Settings", to: "/settings" },
      ],
    },
  ];

  const layoutValue = useMemo(
    () => ({
      sessionId,
      profile,
      settings,
      isRefreshing,
      api,
      refreshProfile,
      refreshSettings,
      updateSettings,
      notify,
      searchValue,
      setSearchValue,
      toasts,
    }),
    [
      sessionId,
      profile,
      settings,
      isRefreshing,
      api,
      refreshProfile,
      refreshSettings,
      updateSettings,
      notify,
      searchValue,
      toasts,
    ],
  );

  return (
    <RedditLayoutContext.Provider value={layoutValue}>
      <div
        className="reddit-shell"
        data-theme={settings?.theme ?? "light"}
        data-reduced-motion={settings?.reduce_animations ? "true" : "false"}
      >
        <header className="reddit-topbar" role="banner">
          <div className="reddit-topbar__left">
            <svg viewBox="0 0 20 20" width="28" height="28" xmlns="http://www.w3.org/2000/svg" className="reddit-topbar__logo">
              <circle cx="10" cy="10" r="10" fill="#FF4500" />
              <path d="M16.67 10a1.46 1.46 0 0 0-2.47-1 7.12 7.12 0 0 0-3.85-1.23l.65-3.12 2.16.45a1 1 0 1 0 .13-.61l-2.42-.52a.27.27 0 0 0-.32.2l-.73 3.47a7.14 7.14 0 0 0-3.89 1.23 1.46 1.46 0 1 0-1.61 2.39 2.87 2.87 0 0 0 0 .44c0 2.24 2.61 4.06 5.83 4.06s5.83-1.82 5.83-4.06a2.87 2.87 0 0 0 0-.44 1.46 1.46 0 0 0 .68-1.26zM7.27 11.17a1 1 0 1 1 1 1 1 1 0 0 1-1-1zm5.75 2.72a3.69 3.69 0 0 1-2.52.75 3.67 3.67 0 0 1-2.51-.75.18.18 0 0 1 .25-.26 3.33 3.33 0 0 0 2.26.65 3.35 3.35 0 0 0 2.27-.65.18.18 0 1 1 .25.26zm-.19-1.72a1 1 0 1 1 1-1 1 1 0 0 1-1 1z" fill="#FFF" />
            </svg>
            <span
              className="reddit-topbar__title"
              onClick={() => navigate(preserveQueryParams("/feed", location.search))}
              onKeyDown={(event) =>
                activateOnKeyDown(event, () => navigate(preserveQueryParams("/feed", location.search)))
              }
              role="link"
              tabIndex={0}
            >
              reddit
            </span>
          </div>
          <div className="reddit-topbar__center">
            <SearchBar
              value={searchValue}
              onChange={setSearchValue}
              onSubmit={handleSearchSubmit}
              placeholder="Search Reddit"
              ariaLabel="Search Reddit"
              className="reddit-topbar__search"
            />
          </div>
          <div className="reddit-topbar__right">
            {profile ? (
              <button
                className="reddit-topbar__user"
                onClick={() => navigate(preserveQueryParams(`/u/${profile.username}`, location.search))}
                aria-label="View your profile"
              >
                <span className="reddit-topbar__avatar">
                  {profile.username.charAt(0).toUpperCase()}
                </span>
                <span className="reddit-topbar__username">{profile.username}</span>
                <span className="reddit-topbar__karma">{(profile.post_karma + profile.comment_karma).toLocaleString()} karma</span>
              </button>
            ) : null}
          </div>
        </header>

        <div className="reddit-body">
          <nav className="reddit-sidebar" aria-label="Reddit navigation">
            <button
              className="reddit-create-post-btn"
              aria-label="Create a new post"
              onClick={() => navigate(preserveQueryParams("/submit", location.search))}
            >
              + Create Post
            </button>
            <Sidebar
              title="Reddit navigation"
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
                        borderTop: "1px solid #343536",
                        marginTop: "0.5rem",
                        paddingTop: "0.75rem",
                      }}
                      onMouseOver={(e) => (e.currentTarget.style.color = "#FF4500")}
                      onMouseOut={(e) => (e.currentTarget.style.color = "#656d76")}
                    >
                      ← Back to Launcher
                    </a>
                  )
              }
            />
          </nav>
          <div className="reddit-main-column">
            <Outlet />
          </div>
        </div>
        <Toast messages={toasts} onDismiss={dismissToast} />
        <BenchmarkToolbar envId="reddit" sessionId={sessionId} />
      </div>
    </RedditLayoutContext.Provider>
  );
}
