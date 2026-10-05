import Link from "next/link";
import { PrimitivePill } from "@/components/ui/PrimitivePill";
import type { TaskMeta } from "@/lib/tasks";

export function TaskCard({ task }: { task: TaskMeta }) {
  return (
    <Link
      href={`/tasks/${task.task_id}`}
      className="block py-5 border-b border-[var(--border)] no-underline group"
    >
      <div className="flex items-baseline justify-between mb-2">
        <span className="font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors duration-150">
          {task.title}
        </span>
        <span className="text-[12px] text-[var(--text-tertiary)] ml-4 shrink-0">
          {task.difficulty}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex flex-wrap gap-1.5">
          {(task.primary_primitives ?? []).map((p) => (
            <PrimitivePill key={p} name={p} />
          ))}
        </div>
        <span className="text-[12px] text-[var(--text-tertiary)] ml-auto shrink-0">
          {task.expected_steps} steps
        </span>
      </div>
    </Link>
  );
}
