"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PrimitivePill } from "@/components/ui/PrimitivePill";
import { EvalCriteria } from "@/components/ui/EvalCriteria";
import { loadTaskDetail, type TaskDetail } from "@/lib/tasks";

export function TaskDetailClient({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTaskDetail(taskId).then((t) => {
      setTask(t);
      setLoading(false);
    });
  }, [taskId]);

  if (loading) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <p className="text-sm text-[var(--text-tertiary)]">Loading...</p>
      </div>
    );
  }

  if (!task) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <Link href="/tasks" className="text-sm text-[var(--text-secondary)] no-underline hover:text-[var(--text-primary)] transition-colors">
          &larr; Back to tasks
        </Link>
        <p className="text-sm text-[var(--text-tertiary)] mt-10">Task not found.</p>
      </div>
    );
  }

  const minutes = Math.floor(task.time_limit_seconds / 60);

  return (
    <div className="max-w-[720px] mx-auto px-12">
      <section className="pt-[120px] pb-20">
        <Link href="/tasks" className="text-sm text-[var(--text-secondary)] no-underline hover:text-[var(--text-primary)] transition-colors">
          &larr; Back to tasks
        </Link>

        <h1 className="text-[clamp(2rem,4vw,3.2rem)] font-medium tracking-tight leading-[1.15] mt-8 mb-4">
          {task.title}
        </h1>

        {/* Metadata row */}
        <div className="flex flex-wrap items-center gap-4 mb-8 text-[12px] text-[var(--text-tertiary)]">
          <span className="px-2.5 py-1 border border-[var(--border)] rounded-lg">
            {task.difficulty}
          </span>
          <span>{minutes} min time limit</span>
          <span>{task.expected_steps} expected steps</span>
        </div>

        {/* Primitives */}
        <div className="mb-10">
          <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-3">
            Primitives
          </p>
          <div className="flex flex-wrap gap-1.5">
            {(task.primary_primitives ?? []).map((p) => (
              <PrimitivePill key={p} name={p} />
            ))}
            {(task.secondary_primitives ?? []).map((p) => (
              <span
                key={p}
                className="text-[13px] px-4 py-[7px] border border-[var(--border)] rounded-xl text-[var(--text-tertiary)] opacity-60"
              >
                {p}
              </span>
            ))}
          </div>
        </div>

        <hr className="border-[var(--border)]" />

        {/* Instruction */}
        <div className="py-10">
          <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-4">
            Instruction
          </p>
          <p className="text-[15px] text-[var(--text-secondary)] leading-[1.75] whitespace-pre-wrap">
            {task.instruction}
          </p>
        </div>

        <hr className="border-[var(--border)]" />

        {/* Evaluation criteria */}
        {task.eval_check_descriptions && task.eval_check_descriptions.length > 0 && (
          <div className="py-10">
            <EvalCriteria
              criteria={task.eval_check_descriptions.map((desc) => ({ desc }))}
            />
          </div>
        )}

        <hr className="border-[var(--border)]" />

        {/* Action links */}
        <div className="flex gap-4 pt-10">
          <Link
            href={`/environment?task=${task.task_id}`}
            className="text-sm font-medium px-6 py-[10px] bg-[var(--text-primary)] text-[var(--bg)] rounded-xl no-underline hover:opacity-85 transition-opacity"
          >
            Try this environment
          </Link>
          <Link
            href={`/results/${task.task_id}`}
            className="text-sm font-medium px-6 py-[10px] border border-[var(--border)] text-[var(--text-secondary)] rounded-xl no-underline hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors"
          >
            Watch agent attempt
          </Link>
        </div>
      </section>
    </div>
  );
}
