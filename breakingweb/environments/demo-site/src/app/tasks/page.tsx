"use client";

import { useEffect, useState, useCallback } from "react";
import { TaskCard } from "@/components/tasks/TaskCard";
import { TaskFilters } from "@/components/tasks/TaskFilters";
import { loadTaskManifest, type TaskMeta } from "@/lib/tasks";

export default function TaskLibraryPage() {
  const [tasks, setTasks] = useState<TaskMeta[]>([]);
  const [search, setSearch] = useState("");
  const [selectedDifficulties, setSelectedDifficulties] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadTaskManifest().then(setTasks);
  }, []);

  const toggleDifficulty = useCallback((d: string) => {
    setSelectedDifficulties((prev) => {
      const next = new Set(prev);
      if (next.has(d)) next.delete(d);
      else next.add(d);
      return next;
    });
  }, []);

  const filtered = tasks.filter((t) => {
    if (selectedDifficulties.size > 0 && !selectedDifficulties.has(t.difficulty)) return false;
    if (search && !t.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="max-w-[720px] mx-auto px-12">
      <section className="pt-[120px] pb-10">
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
          Tasks
        </p>
        <h1 className="text-[clamp(2rem,4vw,3.2rem)] font-medium tracking-tight leading-[1.15] mb-3">
          Task library
        </h1>
        <p className="text-[15px] text-[var(--text-secondary)] mb-10">
          {tasks.length > 0 ? `${filtered.length} of ${tasks.length} tasks` : "Loading..."}
        </p>

        <TaskFilters
          search={search}
          onSearchChange={setSearch}
          selectedDifficulties={selectedDifficulties}
          onToggleDifficulty={toggleDifficulty}
        />

        <div>
          {filtered.map((t) => (
            <TaskCard key={t.task_id} task={t} />
          ))}
          {tasks.length > 0 && filtered.length === 0 && (
            <p className="text-sm text-[var(--text-tertiary)] py-10">
              No tasks match the current filters.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
