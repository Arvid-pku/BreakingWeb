export function StatRow({ stats }: { stats: { value: string; label: string }[] }) {
  return (
    <div className="flex gap-16 py-16 border-t border-b border-[var(--border)]">
      {stats.map((stat) => (
        <div key={stat.label} className="flex flex-col">
          <span className="font-mono text-[32px] font-medium text-[var(--text-primary)] tracking-tight leading-none">
            {stat.value}
          </span>
          <span className="text-[13px] text-[var(--text-secondary)] mt-2">
            {stat.label}
          </span>
        </div>
      ))}
    </div>
  );
}
