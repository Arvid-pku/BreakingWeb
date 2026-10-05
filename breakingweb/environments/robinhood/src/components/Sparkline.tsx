interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  positive?: boolean;
}

export function Sparkline({ data, width = 60, height = 24, positive = true }: SparklineProps) {
  if (data.length < 2) {
    return (
      <svg width={width} height={height} aria-hidden="true">
        <line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke="#ccc" strokeWidth="1.5" />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 2;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = pad + ((max - v) / range) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} className="rh-sparkline" aria-hidden="true">
      <polyline
        fill="none"
        stroke={positive ? "#00C805" : "#FF5000"}
        strokeWidth="1.5"
        points={points}
      />
    </svg>
  );
}
