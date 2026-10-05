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
  useParams,
} from "react-router-dom";

import { LmsShell } from "./Shell";
import { DashboardPage } from "./pages/Dashboard";
import { CoursesPage } from "./pages/Courses";
import { CourseViewPage } from "./pages/CourseView";
import { AssignmentPage } from "./pages/Assignment";
import { DiscussionPage } from "./pages/Discussion";
import { GradesPage } from "./pages/Grades";
import { CalendarPage } from "./pages/Calendar";
import { MessagesPage } from "./pages/Messages";
import { PeerReviewsPage } from "./pages/PeerReviews";

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

function LmsWorkspace() {
  const { sessionId, createSession } = useSession("lms");
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
          (e: { env_id: string }) => e.env_id === "lms",
        );
        const nextTasks = (env?.tasks ?? []) as ManifestTask[];
        setTasks(nextTasks);
        if (nextTasks.length > 0 && !nextTasks.some((t) => t.task_id === selectedTaskId)) {
          setSelectedTaskId(nextTasks[0].task_id);
        }
      })
      .catch(() => {
        if (!cancelled) setBootError("Unable to load LMS task definitions from the benchmark manifest.");
      });
    return () => { cancelled = true; };
  }, []);

  if (sessionId) {
    return <Navigate to={{ pathname: "/", search: location.search }} replace />;
  }

  const selectedTask = tasks.find((t) => t.task_id === selectedTaskId);

  return (
    <section className="lms-launcher" aria-label="No active LMS session">
      <div className="lms-launcher__card">
        <div className="lms-launcher__header">
          <h1 className="lms-launcher__title">LMS Benchmark</h1>
          <p className="lms-launcher__subtitle">Select a task, set a seed, then launch.</p>
        </div>
        <div className="lms-launcher__form">
          <FormField
            as="select"
            id="lms-launcher-task"
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
            id="lms-launcher-seed"
            label="Seed"
            hint="Same seed reproduces the same LMS state."
            inputProps={{
              value: seedText,
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => setSeedText(e.target.value),
              inputMode: "numeric" as const,
            }}
          />
          {selectedTask ? (
            <div className="lms-launcher__task-info">
              <strong>{selectedTask.title}</strong>
              <span>{selectedTask.instruction_template}</span>
            </div>
          ) : null}
          {bootError ? <p className="lms-launcher__error">{bootError}</p> : null}
          <div className="lms-launcher__actions">
            <Button
              variant="secondary"
              aria-label="Reset to defaults"
              onClick={() => { setSeedText("42"); }}
            >
              Reset
            </Button>
            <Button
              variant="primary"
              aria-label="Launch selected LMS benchmark task"
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

function PeerReviewsPageWithId() {
  const { reviewId } = useParams<{ reviewId: string }>();
  return <PeerReviewsPage initialReviewId={reviewId} />;
}

export function App() {
  return (
    <Routes>
      <Route path="/launch" element={<LmsWorkspace />} />
      <Route element={<LmsShellWrapper />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/courses" element={<CoursesPage />} />
        <Route path="/courses/:id/assignments" element={<CourseViewPage />} />
        <Route path="/courses/:id/discussions" element={<CourseViewPage />} />
        <Route path="/courses/:id/modules" element={<CourseViewPage />} />
        <Route path="/courses/:id/modules/:moduleId" element={<CourseViewPage />} />
        <Route path="/courses/:id/syllabus" element={<CourseViewPage />} />
        <Route path="/courses/:id" element={<CourseViewPage />} />
        <Route path="/courses/:id/assignments/:aid" element={<AssignmentPage />} />
        <Route path="/courses/:id/discussions/:did" element={<DiscussionPage />} />
        <Route path="/courses/:id/grades" element={<GradesPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/peer-reviews" element={<PeerReviewsPage />} />
        <Route path="/peer-reviews/:reviewId" element={<PeerReviewsPageWithId />} />
        <Route path="/messages" element={<MessagesPage />} />
      </Route>
    </Routes>
  );
}

function LmsShellWrapper() {
  const { sessionId } = useSession("lms");
  if (!sessionId) return <Navigate to="/launch" replace />;
  return <LmsShell sessionId={sessionId} />;
}
