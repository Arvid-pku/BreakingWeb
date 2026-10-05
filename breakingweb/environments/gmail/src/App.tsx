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

import { GmailLogo } from "./icons";
import { ComposePage } from "./pages/Compose";
import { InboxPage } from "./pages/Inbox";
import { LabelsPage } from "./pages/Labels";
import { SearchPage } from "./pages/Search";
import { SettingsPage } from "./pages/Settings";
import { ThreadPage } from "./pages/Thread";
import { GmailShell } from "./Shell";

interface GmailManifestTask {
  task_id: string;
  title: string;
  difficulty: string;
  instruction_template: string;
  start_path?: string;
}

interface VariantEntry {
  filename: string;
  variant_id: string;
  base_task_id: string;
  target_primitive: string;
  description: string;
  source: string;
}

function launcherUrl(startPath: string, sessionId: string) {
  const base = import.meta.env.BASE_URL;
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  const normalizedPath = startPath.replace(/^\/+/, "");
  const separator = normalizedPath.includes("?") ? "&" : "?";
  return `${normalizedBase}${normalizedPath}${separator}session=${encodeURIComponent(sessionId)}`;
}

function GmailWorkspace() {
  const { sessionId, createSession } = useSession("gmail");
  const location = useLocation();
  const [tasks, setTasks] = useState<GmailManifestTask[]>([]);
  const [variants, setVariants] = useState<VariantEntry[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("gmail_thread_detective");
  const [selectedVariant, setSelectedVariant] = useState("");
  const [seedText, setSeedText] = useState("42");
  const [bootError, setBootError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/manifest")
      .then((response) => response.json())
      .then((manifest) => {
        if (cancelled) return;
        const gmailEnv = (manifest.environments ?? []).find(
          (env: { env_id: string }) => env.env_id === "gmail",
        );
        const nextTasks = (gmailEnv?.tasks ?? []) as GmailManifestTask[];
        setTasks(nextTasks);
        if (nextTasks.length > 0 && !nextTasks.some((task) => task.task_id === selectedTaskId)) {
          setSelectedTaskId(nextTasks[0].task_id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBootError("Unable to load Gmail task definitions from the benchmark manifest.");
        }
      });
    fetch("/api/env/gmail/variants")
      .then((response) => response.json())
      .then((data) => { if (!cancelled) setVariants(data as VariantEntry[]); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (sessionId) {
    const params = new URLSearchParams(location.search);
    if (!params.has("label")) params.set("label", "inbox");
    return <Navigate to={{ pathname: "/inbox", search: `?${params.toString()}` }} replace />;
  }

  const selectedTask = tasks.find((task) => task.task_id === selectedTaskId);
  const matchingVariants = variants.filter((v) => v.base_task_id === selectedTaskId);
  const isStressMode = selectedVariant !== "";
  const selectedVariantEntry = variants.find((v) => v.filename === selectedVariant);

  return (
    <section className="gmail-launcher" aria-label="No active Gmail session">
      <div className="gmail-launcher__card">
        <div className="gmail-launcher__header">
          <GmailLogo />
          <h1 className="gmail-launcher__title">
            Gmail Benchmark{" "}
            <span
              className={`gmail-launcher__mode-badge ${isStressMode ? "gmail-launcher__mode-badge--stress" : ""}`}
            >
              {isStressMode ? "Stress Test" : "Standard"}
            </span>
          </h1>
          <p className="gmail-launcher__subtitle">Select a task, optionally add a stress-test variant, then launch.</p>
        </div>
        <div className="gmail-launcher__form">
          <FormField
            as="select"
            id="gmail-launcher-task"
            label="Task"
            inputProps={{
              value: selectedTaskId,
              onChange: (event: React.ChangeEvent<HTMLSelectElement>) => {
                setSelectedTaskId(event.target.value);
                setSelectedVariant("");
              },
            }}
          >
            {tasks.map((task) => (
              <option key={task.task_id} value={task.task_id}>
                {task.title} ({task.difficulty})
              </option>
            ))}
          </FormField>
          <FormField
            as="select"
            id="gmail-launcher-variant"
            label="Degradation Variant"
            hint="Stress a specific cognitive primitive. Variants are filtered to the selected task."
            inputProps={{
              value: selectedVariant,
              onChange: (event: React.ChangeEvent<HTMLSelectElement>) =>
                setSelectedVariant(event.target.value),
            }}
          >
            <option value="">None — standard / healthy environment</option>
            {matchingVariants.map((v) => (
              <option key={v.filename} value={v.filename}>
                [{v.target_primitive}] {v.description.slice(0, 80)}
              </option>
            ))}
          </FormField>
          {selectedVariantEntry ? (
            <div className="gmail-launcher__variant-info">
              Primitive: {selectedVariantEntry.target_primitive} — {selectedVariantEntry.description}
            </div>
          ) : null}
          <FormField
            id="gmail-launcher-seed"
            label="Seed"
            hint="Same seed reproduces the same mailbox."
            inputProps={{
              value: seedText,
              onChange: (event: React.ChangeEvent<HTMLInputElement>) => setSeedText(event.target.value),
              inputMode: "numeric" as const,
            }}
          />
          {selectedTask ? (
            <div className="gmail-launcher__task-info">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.instruction_template}</span>
            </div>
          ) : null}
          {bootError ? <p className="gmail-launcher__error">{bootError}</p> : null}
          <div className="gmail-launcher__actions">
            <Button
              variant="secondary"
              aria-label="Reset to default task and seed"
              onClick={() => { setSelectedTaskId("gmail_thread_detective"); setSeedText("42"); setSelectedVariant(""); }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              aria-label="Launch selected Gmail benchmark task"
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
                    selectedVariant || undefined,
                  );
                  const nextPath = response.start_path ?? selectedTask.start_path ?? "/inbox";
                  window.location.assign(launcherUrl(nextPath, response.session_id));
                } catch {
                  setBootError("Unable to create session. Check that the FastAPI backend is running.");
                } finally {
                  setIsCreating(false);
                }
              }}
            >
              {isCreating ? "Launching…" : "Launch task"}
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
      <Route path="/" element={<GmailWorkspace />} />
      <Route element={<GmailShellWrapper />}>
        <Route path="inbox" element={<InboxPage />} />
        <Route path="thread/:emailId" element={<ThreadPage />} />
        <Route path="compose" element={<ComposePage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="labels" element={<LabelsPage />} />
        <Route path="contacts" element={<Navigate to="/labels" replace />} />
      </Route>
    </Routes>
  );
}

function GmailShellWrapper() {
  const { sessionId } = useSession("gmail");
  if (!sessionId) return <Navigate to="/" replace />;
  return <GmailShell sessionId={sessionId} />;
}
