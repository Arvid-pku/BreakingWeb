"use client";

const DIFFICULTIES = ["easy", "medium", "hard", "expert", "frontier"];

interface TaskFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  selectedDifficulties: Set<string>;
  onToggleDifficulty: (difficulty: string) => void;
}

export function TaskFilters({
  search,
  onSearchChange,
  selectedDifficulties,
  onToggleDifficulty,
}: TaskFiltersProps) {
  return (
    <div className="flex flex-col gap-4 mb-6">
      <input
        type="text"
        placeholder="Search tasks..."
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        className="w-full px-4 py-2 bg-[var(--surface)] border border-[var(--border)] rounded-xl text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] outline-none focus:border-[var(--text-tertiary)] transition-colors"
      />
      <div className="flex flex-wrap gap-2">
        {DIFFICULTIES.map((d) => {
          const active = selectedDifficulties.has(d);
          return (
            <button
              key={d}
              onClick={() => onToggleDifficulty(d)}
              className={`text-[12px] px-3 py-1.5 rounded-lg border transition-colors duration-150 ${
                active
                  ? "border-[var(--accent)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--text-tertiary)] hover:border-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {d}
            </button>
          );
        })}
      </div>
    </div>
  );
}
