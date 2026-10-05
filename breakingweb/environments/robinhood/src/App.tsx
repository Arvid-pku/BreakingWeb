import { useEffect, useState } from "react";
import {
  Button,
  FormField,
  useSession,
} from "@breakingweb/shared";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import { FeatherLogo } from "./icons";
import { RobinhoodShell } from "./Shell";
import { PortfolioPage } from "./pages/Portfolio";
import { StockDetailPage } from "./pages/StockDetail";
import { TradePage } from "./pages/Trade";
import { OptionsChainPage } from "./pages/OptionsChain";
import { OptionsTradePage } from "./pages/OptionsTrade";
import { OptionsPositionsPage } from "./pages/OptionsPositions";
import { SearchPage } from "./pages/Search";
import { WatchlistsPage } from "./pages/Watchlists";
import { WatchlistDetailPage } from "./pages/WatchlistDetail";
import { OrdersPage } from "./pages/Orders";
import { TransactionsPage } from "./pages/Transactions";
import { RecurringPage } from "./pages/Recurring";
import { TransfersPage } from "./pages/Transfers";
import { TaxCenterPage } from "./pages/TaxCenter";
import { DividendsPage } from "./pages/Dividends";
import { NotificationsPage } from "./pages/Notifications";
import { AlertsPage } from "./pages/Alerts";
import { AccountPage } from "./pages/Account";

interface ManifestTask {
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

function RobinhoodWorkspace() {
  const { sessionId, createSession } = useSession("robinhood");
  const location = useLocation();
  const [tasks, setTasks] = useState<ManifestTask[]>([]);
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
        const env = (manifest.environments ?? []).find(
          (e: { env_id: string }) => e.env_id === "robinhood",
        );
        const nextTasks = (env?.tasks ?? []) as ManifestTask[];
        setTasks(nextTasks);
        if (nextTasks.length > 0 && !nextTasks.some((t) => t.task_id === selectedTaskId)) {
          setSelectedTaskId(nextTasks[0].task_id);
        }
      })
      .catch(() => {
        if (!cancelled) setBootError("Unable to load Robinhood task definitions from the benchmark manifest.");
      });
    return () => { cancelled = true; };
  }, []);

  if (sessionId) {
    return <Navigate to={{ pathname: "/", search: location.search }} replace />;
  }

  const selectedTask = tasks.find((t) => t.task_id === selectedTaskId);

  return (
    <section className="rh-launcher" aria-label="No active Robinhood session">
      <div className="rh-launcher__card">
        <div className="rh-launcher__header">
          <FeatherLogo />
          <h1 className="rh-launcher__title">Robinhood Benchmark</h1>
          <p className="rh-launcher__subtitle">Select a task, set a seed, then launch.</p>
        </div>
        <div className="rh-launcher__form">
          <FormField
            as="select"
            id="rh-launcher-task"
            label="Task"
            inputProps={{
              value: selectedTaskId,
              onChange: (e: React.ChangeEvent<HTMLSelectElement>) =>
                setSelectedTaskId(e.target.value),
            }}
          >
            {tasks.map((t) => (
              <option key={t.task_id} value={t.task_id}>
                {t.title} ({t.difficulty})
              </option>
            ))}
          </FormField>
          <FormField
            id="rh-launcher-seed"
            label="Seed"
            hint="Same seed reproduces the same portfolio."
            inputProps={{
              value: seedText,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => setSeedText(e.target.value),
              inputMode: "numeric" as const,
            }}
          />
          {selectedTask ? (
            <div className="rh-launcher__task-info">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.instruction_template}</span>
            </div>
          ) : null}
          {bootError ? <p className="rh-launcher__error">{bootError}</p> : null}
          <div className="rh-launcher__actions">
            <Button
              variant="secondary"
              aria-label="Reset to defaults"
              onClick={() => { setSeedText("42"); }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              aria-label="Launch selected Robinhood benchmark task"
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

export function App() {
  return (
    <Routes>
      <Route path="/launch" element={<RobinhoodWorkspace />} />
      <Route element={<RobinhoodShellWrapper />}>
        <Route path="/" element={<PortfolioPage />} />
        <Route path="/stocks/:symbol" element={<StockDetailPage />} />
        <Route path="/stocks/:symbol/trade" element={<TradePage />} />
        <Route path="/stocks/:symbol/options" element={<OptionsChainPage />} />
        <Route path="/stocks/:symbol/options/trade" element={<OptionsTradePage />} />
        <Route path="/options/positions" element={<OptionsPositionsPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/lists" element={<WatchlistsPage />} />
        <Route path="/lists/:id" element={<WatchlistDetailPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/history" element={<TransactionsPage />} />
        <Route path="/recurring" element={<RecurringPage />} />
        <Route path="/transfers" element={<TransfersPage />} />
        <Route path="/tax" element={<TaxCenterPage />} />
        <Route path="/dividends" element={<DividendsPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/account" element={<AccountPage />} />
      </Route>
    </Routes>
  );
}

function RobinhoodShellWrapper() {
  const { sessionId } = useSession("robinhood");
  if (!sessionId) return <Navigate to="/launch" replace />;
  return <RobinhoodShell sessionId={sessionId} />;
}
