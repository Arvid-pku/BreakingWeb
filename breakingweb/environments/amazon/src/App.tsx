import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BenchmarkToolbar,
  Button,
  FormField,
  Toast,
  preserveQueryParams,
  useApi,
  useBenchmarkState,
  useSession,
} from "@breakingweb/shared";
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import { createAmazonApi } from "./api";
import { AmazonLayoutContext } from "./context";
import type { CartSummary } from "./types";

import { HomePage } from "./pages/Home";
import { SearchPage } from "./pages/Search";
import { ProductDetailPage } from "./pages/ProductDetail";
import { CartPage } from "./pages/Cart";
import { CheckoutPage } from "./pages/Checkout";
import { OrderConfirmationPage } from "./pages/OrderConfirmation";
import { OrdersPage } from "./pages/Orders";
import { WishlistPage } from "./pages/Wishlist";
import { SettingsPage } from "./pages/Settings";
import { LoginPage } from "./pages/Login";
import { ReturnsPage } from "./pages/Returns";
import { ReturnFormPage } from "./pages/ReturnForm";
import { CategoriesPage } from "./pages/Categories";
import { DealsPage } from "./pages/Deals";
import { NotificationsPage } from "./pages/Notifications";
import { AccountPage } from "./pages/Account";
import { GiftCardsPage } from "./pages/GiftCards";
import { CustomerServicePage } from "./pages/CustomerService";
import { RegistryPage } from "./pages/Registry";
import { Navbar } from "./components/Navbar";
import { Footer } from "./components/Footer";

/* ── Task manifest types ── */

interface AmazonManifestTask {
  task_id: string;
  title: string;
  difficulty: string;
  instruction_template: string;
  start_path?: string;
}

function launcherUrl(startPath: string, sessionId: string) {
  const base = import.meta.env.BASE_URL;
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  const normalizedPath = startPath.replace(/^\/+/, "");
  const separator = normalizedPath.includes("?") ? "&" : "?";
  return `${normalizedBase}${normalizedPath}${separator}session=${encodeURIComponent(sessionId)}`;
}

/* ── Launcher (no active session) ── */

function AmazonLauncher() {
  const { sessionId, createSession } = useSession("amazon");
  const location = useLocation();
  const [tasks, setTasks] = useState<AmazonManifestTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [seedText, setSeedText] = useState("42");
  const [bootError, setBootError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/manifest")
      .then((r) => r.json())
      .then((manifest) => {
        if (cancelled) return;
        const amazonEnv = (manifest.environments ?? []).find(
          (env: { env_id: string }) => env.env_id === "amazon",
        );
        const nextTasks = (amazonEnv?.tasks ?? []) as AmazonManifestTask[];
        setTasks(nextTasks);
        if (nextTasks.length > 0) {
          setSelectedTaskId(nextTasks[0].task_id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBootError("Unable to load Amazon task definitions from the benchmark manifest.");
        }
      });
    return () => { cancelled = true; };
  }, []);

  if (sessionId) {
    return <Navigate to={{ pathname: "/", search: location.search }} replace />;
  }

  const selectedTask = tasks.find((t) => t.task_id === selectedTaskId);

  return (
    <section className="amazon-launcher" aria-label="No active Amazon session">
      <div className="amazon-launcher__card">
        <div className="amazon-launcher__header">
          <h1 className="amazon-launcher__title">
            <span className="amazon-logo-text">amazon</span> Benchmark
          </h1>
          <p className="amazon-launcher__subtitle">Select a task, set a seed, then launch.</p>
        </div>
        <div className="amazon-launcher__form">
          <FormField
            as="select"
            id="amazon-launcher-task"
            label="Task"
            inputProps={{
              value: selectedTaskId,
              onChange: (e: React.ChangeEvent<HTMLSelectElement>) =>
                setSelectedTaskId(e.target.value),
            }}
          >
            {tasks.map((task) => (
              <option key={task.task_id} value={task.task_id}>
                {task.title} ({task.difficulty})
              </option>
            ))}
          </FormField>
          <FormField
            id="amazon-launcher-seed"
            label="Seed"
            hint="Same seed reproduces the same product catalog."
            inputProps={{
              value: seedText,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => setSeedText(e.target.value),
              inputMode: "numeric" as const,
            }}
          />
          {selectedTask ? (
            <div className="amazon-launcher__task-info">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.instruction_template}</span>
            </div>
          ) : null}
          {bootError ? <p className="amazon-launcher__error">{bootError}</p> : null}
          <div className="amazon-launcher__actions">
            <Button
              variant="secondary"
              aria-label="Reset to defaults"
              onClick={() => {
                if (tasks.length > 0) setSelectedTaskId(tasks[0].task_id);
                setSeedText("42");
              }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              aria-label="Launch selected Amazon benchmark task"
              disabled={!selectedTask || isCreating}
              onClick={async () => {
                if (!selectedTask) return;
                setIsCreating(true);
                setBootError(null);
                try {
                  const parsedSeed = seedText.trim() === "" ? undefined : Number.parseInt(seedText.trim(), 10);
                  const response = await createSession(
                    selectedTask.task_id,
                    parsedSeed === undefined || Number.isNaN(parsedSeed) ? undefined : parsedSeed,
                  );
                  const nextPath = response.start_path ?? selectedTask.start_path ?? "/";
                  window.location.assign(launcherUrl(nextPath, response.session_id));
                } catch {
                  setBootError("Unable to create session. Check that the FastAPI backend is running.");
                } finally {
                  setIsCreating(false);
                }
              }}
            >
              {isCreating ? "Launching..." : "Launch task"}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Amazon Shell (wraps all authenticated pages) ── */

function AmazonShell({ sessionId }: { sessionId: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { log } = useBenchmarkState("amazon");
  const { request } = useApi("amazon", sessionId);
  const api = useMemo(() => createAmazonApi(request), [request]);
  const [cartSummary, setCartSummary] = useState<CartSummary | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [searchValue, setSearchValue] = useState("");
  const [toasts, setToasts] = useState<Array<{ id: string; title: string; description?: string; onUndo?: () => void }>>([]);

  const notify = useCallback((title: string, description?: string) => {
    const id = `${title}-${Date.now()}-${Math.random()}`;
    setToasts((curr) => [...curr, { id, title, description }]);
    window.setTimeout(() => {
      setToasts((curr) => curr.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((curr) => curr.filter((t) => t.id !== id));
  }, []);

  const refreshCart = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const summary = await api.getCart();
      setCartSummary(summary);
    } catch {
      // Cart data may be stale but app remains usable
    } finally {
      setIsRefreshing(false);
    }
  }, [api]);

  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { void refreshCart(); }, 120);
    return () => clearTimeout(debounceRef.current);
  }, [location.pathname, refreshCart]);

  useEffect(() => {
    log("route_change", { pathname: location.pathname, query: location.search, sessionId });
  }, [location.pathname, location.search, log, sessionId]);

  useEffect(() => {
    const nextSearch = new URLSearchParams(location.search).get("q") ?? "";
    setSearchValue(nextSearch);
  }, [location.search]);

  const handleSearchSubmit = useCallback(() => {
    const query = searchValue.trim();
    if (!query) return;
    log("search_submit", { query, route: location.pathname, sessionId });
    navigate(preserveQueryParams(`/search?q=${encodeURIComponent(query)}&_t=${Date.now()}`, location.search));
  }, [location.pathname, location.search, log, navigate, searchValue, sessionId]);

  return (
    <AmazonLayoutContext.Provider
      value={{ sessionId, cartSummary, isRefreshing, api, refreshCart, notify, searchValue, setSearchValue, toasts }}
    >
      <div className="amazon-shell">
        <Navbar
          searchValue={searchValue}
          onSearchChange={setSearchValue}
          onSearchSubmit={handleSearchSubmit}
          cartCount={cartSummary?.item_count ?? 0}
        />
        <main className="amazon-main">
          <Outlet />
        </main>
        <Footer />
        <Toast messages={toasts} onDismiss={dismissToast} />
        <BenchmarkToolbar envId="amazon" sessionId={sessionId} />
      </div>
    </AmazonLayoutContext.Provider>
  );
}

function AmazonShellWrapper() {
  const { sessionId } = useSession("amazon");
  if (!sessionId) return <Navigate to="/" replace />;
  return <AmazonShell sessionId={sessionId} />;
}

function AddressesRedirect() {
  const location = useLocation();
  return <Navigate to={preserveQueryParams("/account", location.search)} replace />;
}

function OrderConfirmationRedirect() {
  const { orderId } = useParams<{ orderId: string }>();
  const location = useLocation();
  if (!orderId) return <Navigate to={preserveQueryParams("/orders", location.search)} replace />;
  return (
    <Navigate
      to={preserveQueryParams(`/order-confirmation/${orderId}`, location.search)}
      replace
    />
  );
}

/* ── App ── */

export function App() {
  return (
    <Routes>
      <Route path="/" element={<AmazonLauncherOrShell />} />
      <Route element={<AmazonShellWrapper />}>
        <Route path="home" element={<HomePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="product/:id" element={<ProductDetailPage />} />
        <Route path="cart" element={<CartPage />} />
        <Route path="checkout" element={<CheckoutPage />} />
        <Route path="order-confirmation/:orderId" element={<OrderConfirmationPage />} />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="orders/:orderId" element={<OrderConfirmationRedirect />} />
        <Route path="wishlist" element={<WishlistPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="returns" element={<ReturnsPage />} />
        <Route path="returns/new/:orderId" element={<ReturnFormPage />} />
        <Route path="categories" element={<CategoriesPage />} />
        <Route path="deals" element={<DealsPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="addresses" element={<AddressesRedirect />} />
        <Route path="gift-cards" element={<GiftCardsPage />} />
        <Route path="customer-service" element={<CustomerServicePage />} />
        <Route path="registry" element={<RegistryPage />} />
      </Route>
    </Routes>
  );
}

/**
 * "/" route: if we have a session, redirect to /home; otherwise show launcher.
 */
function AmazonLauncherOrShell() {
  const { sessionId } = useSession("amazon");
  const location = useLocation();
  if (sessionId) {
    return <Navigate to={{ pathname: "/home", search: location.search }} replace />;
  }
  return <AmazonLauncher />;
}
