import { useState } from "react";

interface ChartProps {
  data: Array<{ date: string; close: string }>;
  positive?: boolean;
}

const RANGES = ["1D", "1W", "1M", "3M", "YTD", "1Y", "MAX"] as const;

export function StockChart({ data, positive = true }: ChartProps) {
  const [range, setRange] = useState<string>("1M");

  const filteredData = filterByRange(data, range);
  const values = filteredData.map((d) => parseFloat(d.close));

  if (values.length < 2) {
    return (
      <div className="rh-chart">
        <div className="rh-chart__empty">No chart data available</div>
        <TimeRangeButtons range={range} onRange={setRange} />
      </div>
    );
  }

  const width = 680;
  const height = 200;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const rng = max - min || 1;
  const pad = 8;

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = pad + ((max - v) / rng) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const color = positive ? "#00C805" : "#FF5000";

  return (
    <div className="rh-chart">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        aria-label="Stock price chart"
      >
        <defs>
          <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.15" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon
          fill="url(#chartFill)"
          points={`0,${height} ${points} ${width},${height}`}
        />
        <polyline fill="none" stroke={color} strokeWidth="2" points={points} />
      </svg>
      <TimeRangeButtons range={range} onRange={setRange} />
    </div>
  );
}

function TimeRangeButtons({ range, onRange }: { range: string; onRange: (r: string) => void }) {
  return (
    <div className="rh-time-range">
      {RANGES.map((r) => (
        <button
          key={r}
          className={`rh-time-range__btn ${range === r ? "rh-time-range__btn--active" : ""}`}
          onClick={() => onRange(r)}
          aria-label={`Show ${r} range`}
        >
          {r}
        </button>
      ))}
    </div>
  );
}

function filterByRange(data: Array<{ date: string; close: string }>, range: string) {
  if (!data.length || range === "MAX") return data;
  const now = new Date();
  let cutoff: Date;
  switch (range) {
    case "1D": cutoff = new Date(now.getTime() - 86400000); break;
    case "1W": cutoff = new Date(now.getTime() - 7 * 86400000); break;
    case "1M": cutoff = new Date(now.getTime() - 30 * 86400000); break;
    case "3M": cutoff = new Date(now.getTime() - 90 * 86400000); break;
    case "YTD": cutoff = new Date(now.getFullYear(), 0, 1); break;
    case "1Y": cutoff = new Date(now.getTime() - 365 * 86400000); break;
    default: return data;
  }
  const filtered = data.filter((d) => new Date(d.date) >= cutoff);
  return filtered.length >= 2 ? filtered : data;
}
