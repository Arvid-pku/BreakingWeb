import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BenchmarkToolbar,
  SearchBar,
  Toast,
  preserveQueryParams,
  useApi,
  useBenchmarkState,
} from "@breakingweb/shared";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { createRobinhoodApi } from "./api";
import { RobinhoodLayoutContext } from "./context";
import { FeatherLogo, IconBell, IconAccount } from "./icons";
import type { Watchlist, Stock, PriceData } from "./types";

export function RobinhoodShell({ sessionId }: { sessionId: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { update, log } = useBenchmarkState("robinhood");
  const { request } = useApi("robinhood", sessionId);
  const api = useMemo(() => createRobinhoodApi(request), [request]);

  const [account, setAccount] = useState<{
    cash_balance: string;
    buying_power: string;
    portfolio_value: string;
    margin_maintenance: string;
    day_trade_count: number;
  } | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const [liveTick, setLiveTick] = useState(0);
  const [isLive, setIsLive] = useState(false);
  const [livePrices, setLivePrices] = useState<Record<string, PriceData>>({});
  const [toasts, setToasts] = useState<Array<{ id: string; title: string; description?: string }>>([]);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [watchlistStocks, setWatchlistStocks] = useState<Record<string, Stock>>({});

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

  const refreshAccount = useCallback(async () => {
    try {
      const data = await api.getAccount();
      setAccount({
        cash_balance: data.cash_balance,
        buying_power: data.buying_power,
        portfolio_value: data.portfolio_value,
        margin_maintenance: data.margin_maintenance,
        day_trade_count: data.day_trade_count,
      });
      update({
        sessionId,
        currentRoute: locationRef.current.pathname,
      });
    } catch {
      // silently continue
    }
  }, [api, sessionId, update]);

  // Load watchlists for sidebar
  const loadWatchlists = useCallback(async () => {
    try {
      const wls = await api.listWatchlists();
      setWatchlists(wls);
      // Load stock data for all symbols in watchlists
      const allSymbols = new Set<string>();
      for (const wl of wls) {
        for (const sym of wl.symbols) allSymbols.add(sym);
      }
      const stockMap: Record<string, Stock> = {};
      await Promise.all(
        Array.from(allSymbols).map(async (sym) => {
          try {
            const stock = await api.getStock(sym);
            stockMap[sym] = stock;
          } catch {
            // skip unknown stocks
          }
        }),
      );
      setWatchlistStocks(stockMap);
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => {
    const nextSearch = new URLSearchParams(location.search).get("q") ?? "";
    setSearchValue(nextSearch);
  }, [location.search]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void refreshAccount();
      void loadWatchlists();
    }, 120);
    return () => clearTimeout(debounceRef.current);
  }, [location.pathname, location.search, refreshAccount, loadWatchlists]);

  // Track which order fills we've already notified about
  const notifiedFillsRef = useRef<Set<string>>(new Set());

  // Live price polling (every 2 seconds)
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const data = await api.getPrices();
        setLiveTick(data.tick);
        setIsLive(data.tick > 0);
        setLivePrices(data.prices);
        setAccount((prev) =>
          prev
            ? { ...prev, portfolio_value: data.portfolio_value, cash_balance: data.cash_balance }
            : prev,
        );
        // Update watchlist stock prices from live data
        setWatchlistStocks((prev) => {
          const next = { ...prev };
          for (const [sym, pd] of Object.entries(data.prices)) {
            if (next[sym]) {
              next[sym] = { ...next[sym], price: pd.price, day_change: pd.day_change, day_change_pct: pd.day_change_pct };
            }
          }
          return next;
        });
        // Only notify for newly filled orders (not already seen)
        const newFills = data.pending_orders_filled.filter((id) => !notifiedFillsRef.current.has(id));
        if (newFills.length > 0) {
          void refreshAccount();
          void loadWatchlists();
          for (const orderId of newFills) {
            notifiedFillsRef.current.add(orderId);
            notify("Order Filled", `Order ${orderId} has been filled`);
          }
        }
      } catch {
        // silently continue
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [api, notify, refreshAccount, loadWatchlists]);

  useEffect(() => {
    log("route_change", { pathname: location.pathname, query: location.search, sessionId });
  }, [location.pathname, location.search, log, sessionId]);

  const handleSearchSubmit = useCallback(() => {
    const query = searchValue.trim();
    log("search_submit", { query, route: location.pathname, sessionId });
    navigate(preserveQueryParams(`/search?q=${encodeURIComponent(query)}`, location.search));
  }, [location.pathname, location.search, log, navigate, searchValue, sessionId]);

  const showSidebar = location.pathname === "/" || location.pathname.startsWith("/stocks/");

  return (
    <RobinhoodLayoutContext.Provider
      value={{ sessionId, account, api, refreshAccount, notify, searchValue, setSearchValue, livePrices, liveTick }}
    >
      <div className="rh-shell">
        <header className="rh-topbar" role="banner">
          <div className="rh-topbar__left">
            <Link to={preserveQueryParams("/", location.search)} className="rh-topbar__logo" aria-label="Home">
              <FeatherLogo />
            </Link>
            <nav className="rh-topbar__nav">
              <Link to={preserveQueryParams("/", location.search)} className="rh-topbar__link">Investing</Link>
              <Link to={preserveQueryParams("/orders", location.search)} className="rh-topbar__link">Orders</Link>
              <Link to={preserveQueryParams("/options/positions", location.search)} className="rh-topbar__link">Options</Link>
              <Link to={preserveQueryParams("/alerts", location.search)} className="rh-topbar__link">Alerts</Link>
              <Link to={preserveQueryParams("/transfers", location.search)} className="rh-topbar__link">Transfers</Link>
              <Link to={preserveQueryParams("/recurring", location.search)} className="rh-topbar__link">Recurring</Link>
              <Link to={preserveQueryParams("/history", location.search)} className="rh-topbar__link">History</Link>
              <Link to={preserveQueryParams("/tax", location.search)} className="rh-topbar__link">Tax</Link>
            </nav>
          </div>
          <div className="rh-topbar__center">
            <SearchBar
              value={searchValue}
              onChange={setSearchValue}
              onSubmit={handleSearchSubmit}
              placeholder="Search"
              ariaLabel="Search stocks"
              className="rh-topbar__search"
            />
          </div>
          {isLive && (
            <span className="rh-live-indicator" aria-label="Live prices active">
              <span className="rh-live-dot" />
              Live
            </span>
          )}
          <div className="rh-topbar__right">
            <Link
              to={preserveQueryParams("/notifications", location.search)}
              className="rh-topbar__icon-btn"
              aria-label="Notifications"
            >
              <IconBell />
            </Link>
            <Link
              to={preserveQueryParams("/account", location.search)}
              className="rh-topbar__icon-btn"
              aria-label="Account"
            >
              <IconAccount />
            </Link>
          </div>
        </header>

        <div className="rh-body">
          <main className="rh-main">
            <Outlet />
          </main>
          {showSidebar && (
            <aside className="rh-sidebar" aria-label="Watchlists sidebar">
              <div className="rh-sidebar__header">
                <Link
                  to={preserveQueryParams("/lists", location.search)}
                  className="rh-sidebar__title-link"
                >
                  Lists
                </Link>
              </div>
              {watchlists.map((wl) => (
                <div key={wl.id} className="rh-sidebar__list">
                  <Link
                    to={preserveQueryParams(`/lists/${wl.id}`, location.search)}
                    className="rh-sidebar__list-name"
                  >
                    {wl.name}
                  </Link>
                  {wl.symbols.map((sym) => {
                    const stock = watchlistStocks[sym];
                    const price = stock ? parseFloat(stock.price) : 0;
                    const changePct = stock ? parseFloat(stock.day_change_pct) : 0;
                    const isPositive = changePct >= 0;
                    return (
                      <Link
                        key={sym}
                        to={preserveQueryParams(`/stocks/${sym}`, location.search)}
                        className="rh-sidebar__stock-row"
                      >
                        <span className="rh-sidebar__symbol">{sym}</span>
                        <span className="rh-sidebar__sparkline">
                          <svg width="60" height="24" viewBox="0 0 60 24" aria-hidden="true">
                            <polyline
                              fill="none"
                              stroke={isPositive ? "#00C805" : "#FF5000"}
                              strokeWidth="1.5"
                              points="0,18 10,14 20,16 30,10 40,12 50,8 60,6"
                            />
                          </svg>
                        </span>
                        <span className="rh-sidebar__price-col">
                          <span className="rh-sidebar__price">${price.toFixed(2)}</span>
                          <span className={`rh-sidebar__change ${isPositive ? "rh-gain" : "rh-loss"}`}>
                            {isPositive ? "+" : ""}{changePct.toFixed(2)}%
                          </span>
                        </span>
                      </Link>
                    );
                  })}
                </div>
              ))}
            </aside>
          )}
        </div>
        <Toast messages={toasts} onDismiss={dismissToast} />
        <BenchmarkToolbar envId="robinhood" sessionId={sessionId} />
      </div>
    </RobinhoodLayoutContext.Provider>
  );
}
