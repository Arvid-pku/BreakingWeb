"use client";

import { useEffect, useState, useCallback } from "react";
import { loadTaskManifest, loadTaskDetail, type TaskMeta, type TaskDetail } from "@/lib/tasks";
import { GmailWrapper } from "@/components/gmail-wrapper";
import type { GmailFixture } from "@breakingweb/gmail/mutator";

interface EnvInfo {
  id: string;
  label: string;
  available: boolean;
}

const ENVIRONMENTS: EnvInfo[] = [
  { id: "gmail", label: "Gmail", available: true },
  { id: "robinhood", label: "Robinhood", available: false },
  { id: "project-manager", label: "Project Manager", available: false },
  { id: "social-media", label: "Social Media", available: false },
  { id: "amazon", label: "Amazon", available: false },
];

const FREE_EXPLORATION = "__free__";

export default function EnvironmentPage() {
  const [selectedEnv, setSelectedEnv] = useState("gmail");
  const [tasks, setTasks] = useState<TaskMeta[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string>(FREE_EXPLORATION);
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null);
  const [defaultFixture, setDefaultFixture] = useState<TaskDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load manifest on mount
  useEffect(() => {
    loadTaskManifest().then((items) => {
      setTasks(items);
      // Load first task fixture as the default state for free exploration
      if (items.length > 0) {
        loadTaskDetail(items[0].task_id).then((detail) => {
          setDefaultFixture(detail);
          setIsLoading(false);
        });
      } else {
        setIsLoading(false);
      }
    });
  }, []);

  // Load fixture when task changes
  const loadFixture = useCallback(async (taskId: string) => {
    if (taskId === FREE_EXPLORATION) {
      setTaskDetail(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    setTaskDetail(null);
    try {
      const detail = await loadTaskDetail(taskId);
      if (!detail) {
        setError(`Could not load fixture for task "${taskId}".`);
      } else {
        setTaskDetail(detail);
      }
    } catch {
      setError("Failed to load task fixture.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFixture(selectedTaskId);
  }, [selectedTaskId, loadFixture]);

  const selectedMeta = tasks.find((t) => t.task_id === selectedTaskId);
  const activeFixture = taskDetail ?? defaultFixture;
  const isTaskSelected = selectedTaskId !== FREE_EXPLORATION;
  const env = ENVIRONMENTS.find((e) => e.id === selectedEnv)!;

  return (
    <div className="w-full flex flex-col" style={{ height: "calc(100vh - 57px)" }}>
      {/* Environment selector strip */}
      <div className="shrink-0 flex items-center gap-2 px-6 py-3 border-b border-[var(--border)] bg-[var(--surface)]">
        {ENVIRONMENTS.map((e) => (
          <button
            key={e.id}
            onClick={() => e.available && setSelectedEnv(e.id)}
            disabled={!e.available}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] transition-colors duration-150 border ${
              e.id === selectedEnv
                ? "bg-[var(--bg)] border-[var(--border)] font-medium text-[var(--text-primary)]"
                : e.available
                  ? "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
                  : "border-transparent opacity-35 cursor-not-allowed text-[var(--text-secondary)]"
            }`}
          >
            <span
              className="w-[7px] h-[7px] rounded-full"
              style={{ background: e.available ? "var(--green)" : "var(--border)" }}
            />
            {e.label}
          </button>
        ))}

        <div className="flex-1" />

        {/* Task selector */}
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-[var(--text-tertiary)]">Task</span>
          <select
            value={selectedTaskId}
            onChange={(e) => setSelectedTaskId(e.target.value)}
            className="bg-[var(--bg)] border border-[var(--border)] text-[var(--text-primary)] px-3 py-[7px] rounded-[10px] text-[13px] focus:outline-none focus:border-[var(--text-tertiary)] transition-colors min-w-[220px]"
          >
            <option value={FREE_EXPLORATION}>Free exploration (no task)</option>
            {tasks.map((t) => (
              <option key={t.task_id} value={t.task_id}>
                {t.title} ({t.difficulty})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Instruction bar — only when task selected */}
      {isTaskSelected && taskDetail && (
        <div className="shrink-0 flex items-center gap-3 px-6 py-2.5 border-b border-[var(--border)]">
          <span className="text-[11px] font-medium text-[var(--text-tertiary)] shrink-0">Instruction</span>
          <span className="text-[13px] text-[var(--text-secondary)] leading-[1.5] flex-1">
            {taskDetail.instruction}
          </span>
          {selectedMeta && (
            <div className="shrink-0 flex gap-2 ml-auto">
              <span className="text-[11px] text-[var(--text-tertiary)] bg-[var(--surface)] px-2.5 py-1 rounded-lg">
                {selectedMeta.difficulty}
              </span>
              <span className="text-[11px] text-[var(--text-tertiary)] bg-[var(--surface)] px-2.5 py-1 rounded-lg">
                ~{selectedMeta.expected_steps} steps
              </span>
            </div>
          )}
        </div>
      )}

      {/* Loading / error states */}
      {isLoading && (
        <div className="flex-1 flex items-center justify-center text-sm text-[var(--text-tertiary)]">
          Loading environment...
        </div>
      )}

      {error && (
        <div className="shrink-0 mx-6 my-3 border border-[var(--red)] rounded-xl p-4 text-sm text-[var(--red)]">
          {error}
        </div>
      )}

      {/* Environment embed */}
      {!isLoading && !error && env.available && activeFixture && (
        <div className="flex-1 min-h-0">
          <GmailWrapper
            key={isTaskSelected ? taskDetail?.task_id : "free"}
            fixture={activeFixture.state as unknown as GmailFixture}
            initialRoute={activeFixture.start_path ?? "/inbox?label=inbox"}
          />
        </div>
      )}

      {/* Placeholder for unavailable environments */}
      {!isLoading && !error && !env.available && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-lg font-medium text-[var(--text-secondary)] mb-2">{env.label}</p>
            <p className="text-sm text-[var(--text-tertiary)]">Coming soon</p>
          </div>
        </div>
      )}
    </div>
  );
}
