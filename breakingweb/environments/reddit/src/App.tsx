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

import { FeedPage } from "./pages/Feed";
import { SubredditPage } from "./pages/Subreddit";
import { PostPage } from "./pages/Post";
import { SubmitPage } from "./pages/Submit";
import { ProfilePage } from "./pages/Profile";
import { MessagesPage } from "./pages/Messages";
import { SearchPage } from "./pages/Search";
import { SettingsPage } from "./pages/Settings";
import { NotificationsPage } from "./pages/Notifications";
import { SavedPage } from "./pages/Saved";
import { RedditShell } from "./Shell";

interface RedditManifestTask {
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

function RedditWorkspace() {
  const { sessionId, createSession } = useSession("reddit");
  const location = useLocation();
  const [tasks, setTasks] = useState<RedditManifestTask[]>([]);
  const [variants, setVariants] = useState<VariantEntry[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
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
        const redditEnv = (manifest.environments ?? []).find(
          (env: { env_id: string }) => env.env_id === "reddit",
        );
        const nextTasks = (redditEnv?.tasks ?? []) as RedditManifestTask[];
        setTasks(nextTasks);
        if (nextTasks.length > 0) {
          setSelectedTaskId(nextTasks[0].task_id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBootError("Unable to load Reddit task definitions from the benchmark manifest.");
        }
      });
    fetch("/api/env/reddit/variants")
      .then((response) => response.json())
      .then((data) => { if (!cancelled) setVariants(data as VariantEntry[]); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (sessionId) {
    return <Navigate to={{ pathname: "/", search: location.search }} replace />;
  }

  const selectedTask = tasks.find((task) => task.task_id === selectedTaskId);
  const matchingVariants = variants.filter((v) => v.base_task_id === selectedTaskId);
  const isStressMode = selectedVariant !== "";
  const selectedVariantEntry = variants.find((v) => v.filename === selectedVariant);

  return (
    <section className="reddit-launcher" aria-label="No active Reddit session">
      <div className="reddit-launcher__card">
        <div className="reddit-launcher__header">
          <div className="reddit-logo">
            <svg viewBox="0 0 20 20" width="32" height="32" xmlns="http://www.w3.org/2000/svg">
              <circle cx="10" cy="10" r="10" fill="#FF4500" />
              <path d="M16.67 10a1.46 1.46 0 0 0-2.47-1 7.12 7.12 0 0 0-3.85-1.23l.65-3.12 2.16.45a1 1 0 1 0 .13-.61l-2.42-.52a.27.27 0 0 0-.32.2l-.73 3.47a7.14 7.14 0 0 0-3.89 1.23 1.46 1.46 0 1 0-1.61 2.39 2.87 2.87 0 0 0 0 .44c0 2.24 2.61 4.06 5.83 4.06s5.83-1.82 5.83-4.06a2.87 2.87 0 0 0 0-.44 1.46 1.46 0 0 0 .68-1.26zM7.27 11.17a1 1 0 1 1 1 1 1 1 0 0 1-1-1zm5.75 2.72a3.69 3.69 0 0 1-2.52.75 3.67 3.67 0 0 1-2.51-.75.18.18 0 0 1 .25-.26 3.33 3.33 0 0 0 2.26.65 3.35 3.35 0 0 0 2.27-.65.18.18 0 1 1 .25.26zm-.19-1.72a1 1 0 1 1 1-1 1 1 0 0 1-1 1z" fill="#FFF" />
            </svg>
          </div>
          <h1 className="reddit-launcher__title">
            Reddit Benchmark{" "}
            <span className={`reddit-launcher__mode-badge ${isStressMode ? "reddit-launcher__mode-badge--stress" : ""}`}>
              {isStressMode ? "Stress Test" : "Standard"}
            </span>
          </h1>
          <p className="reddit-launcher__subtitle">Select a task, optionally add a stress-test variant, then launch.</p>
        </div>
        <div className="reddit-launcher__form">
          <FormField
            as="select"
            id="reddit-launcher-task"
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
            id="reddit-launcher-variant"
            label="Degradation Variant"
            hint="Stress a specific cognitive primitive."
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
            <div className="reddit-launcher__variant-info">
              Primitive: {selectedVariantEntry.target_primitive} — {selectedVariantEntry.description}
            </div>
          ) : null}
          <FormField
            id="reddit-launcher-seed"
            label="Seed"
            hint="Same seed reproduces the same state."
            inputProps={{
              value: seedText,
              onChange: (event: React.ChangeEvent<HTMLInputElement>) => setSeedText(event.target.value),
              inputMode: "numeric" as const,
            }}
          />
          {selectedTask ? (
            <div className="reddit-launcher__task-info">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.instruction_template}</span>
            </div>
          ) : null}
          {bootError ? <p className="reddit-launcher__error">{bootError}</p> : null}
          <div className="reddit-launcher__actions">
            <Button
              variant="secondary"
              aria-label="Reset to default task and seed"
              onClick={() => { setSelectedTaskId(tasks[0]?.task_id ?? ""); setSeedText("42"); setSelectedVariant(""); }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              aria-label="Launch selected Reddit benchmark task"
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
      <Route path="/" element={<RedditWorkspaceOrShell />} />
      <Route element={<RedditShellWrapper />}>
        <Route path="feed" element={<FeedPage />} />
        <Route path="r/:subredditName" element={<SubredditPage />} />
        <Route path="post/:postId" element={<PostPage />} />
        <Route path="submit" element={<SubmitPage />} />
        <Route path="u/:username" element={<ProfilePage />} />
        <Route path="messages" element={<MessagesPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="saved" element={<SavedPage />} />
      </Route>
    </Routes>
  );
}

function RedditWorkspaceOrShell() {
  const { sessionId } = useSession("reddit");
  const location = useLocation();
  if (sessionId) {
    return <Navigate to={{ pathname: "/feed", search: location.search }} replace />;
  }
  return <RedditWorkspace />;
}

function RedditShellWrapper() {
  const { sessionId } = useSession("reddit");
  if (!sessionId) return <Navigate to="/" replace />;
  return <RedditShell sessionId={sessionId} />;
}
