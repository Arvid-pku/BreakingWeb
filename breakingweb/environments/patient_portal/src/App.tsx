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

import { PatientPortalShell } from "./Shell";
import { DashboardPage } from "./pages/Dashboard";
import { AppointmentsPage } from "./pages/Appointments";
import { MessagesPage } from "./pages/Messages";
import { MedicationsPage } from "./pages/Medications";
import { LabsPage } from "./pages/Labs";
import { ReferralsPage } from "./pages/Referrals";
import { BillingPage } from "./pages/Billing";
import { ProfilePage } from "./pages/Profile";

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

function PatientPortalWorkspace() {
  const { sessionId, createSession } = useSession("patient_portal");
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
          (e: { env_id: string }) => e.env_id === "patient_portal",
        );
        const nextTasks = (env?.tasks ?? []) as ManifestTask[];
        setTasks(nextTasks);
        if (nextTasks.length > 0 && !nextTasks.some((t) => t.task_id === selectedTaskId)) {
          setSelectedTaskId(nextTasks[0].task_id);
        }
      })
      .catch(() => {
        if (!cancelled) setBootError("Unable to load Patient Portal task definitions from the benchmark manifest.");
      });
    return () => { cancelled = true; };
  }, []);

  if (sessionId) {
    return <Navigate to={{ pathname: "/", search: location.search }} replace />;
  }

  const selectedTask = tasks.find((t) => t.task_id === selectedTaskId);

  return (
    <section className="pp-launcher" aria-label="No active Patient Portal session">
      <div className="pp-launcher__card">
        <div className="pp-launcher__header">
          <h1 className="pp-launcher__title">Patient Portal Benchmark</h1>
          <p className="pp-launcher__subtitle">Select a task, set a seed, then launch.</p>
        </div>
        <div className="pp-launcher__form">
          <FormField
            as="select"
            id="pp-launcher-task"
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
            id="pp-launcher-seed"
            label="Seed"
            hint="Same seed reproduces the same patient data."
            inputProps={{
              value: seedText,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => setSeedText(e.target.value),
              inputMode: "numeric" as const,
            }}
          />
          {selectedTask ? (
            <div className="pp-launcher__task-info">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.instruction_template}</span>
            </div>
          ) : null}
          {bootError ? <p className="pp-launcher__error">{bootError}</p> : null}
          <div className="pp-launcher__actions">
            <Button
              variant="secondary"
              aria-label="Reset to defaults"
              onClick={() => { setSeedText("42"); }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              aria-label="Launch selected Patient Portal benchmark task"
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
      <Route path="/launch" element={<PatientPortalWorkspace />} />
      <Route element={<PatientPortalShellWrapper />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/appointments" element={<AppointmentsPage />} />
        <Route path="/messages" element={<MessagesPage />} />
        <Route path="/medications" element={<MedicationsPage />} />
        <Route path="/labs" element={<LabsPage />} />
        <Route path="/referrals" element={<ReferralsPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
    </Routes>
  );
}

function PatientPortalShellWrapper() {
  const { sessionId } = useSession("patient_portal");
  if (!sessionId) return <Navigate to="/launch" replace />;
  return <PatientPortalShell sessionId={sessionId} />;
}
