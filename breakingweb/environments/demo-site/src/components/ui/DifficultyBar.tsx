interface BarItem {
  label: string;
  value: number;
}

export function DifficultyBar({ items }: { items: BarItem[] }) {
  const max = Math.max(...items.map((i) => i.value), 1);

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-3">
          <span className="text-[13px] text-[var(--text-secondary)] w-[80px] text-right shrink-0">
            {item.label}
          </span>
          <div className="flex-1 h-[4px] rounded-full bg-[var(--border)] overflow-hidden">
            <div
              className="h-full rounded-full bg-[var(--text-secondary)] transition-all duration-500"
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
          <span className="font-mono text-[13px] text-[var(--text-primary)] w-[48px] shrink-0">
            {(item.value * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  );
}
