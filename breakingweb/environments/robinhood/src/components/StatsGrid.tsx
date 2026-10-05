interface Stat {
  label: string;
  value: string | null | undefined;
}

interface StatsGridProps {
  stats: Stat[];
}

export function StatsGrid({ stats }: StatsGridProps) {
  return (
    <div className="rh-stats-grid" aria-label="Key statistics">
      {stats.map((s) => (
        <div key={s.label} className="rh-stats-grid__item">
          <span className="rh-stats-grid__label">{s.label}</span>
          <span className="rh-stats-grid__value">{s.value ?? "--"}</span>
        </div>
      ))}
    </div>
  );
}
