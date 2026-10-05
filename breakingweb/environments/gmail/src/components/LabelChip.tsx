import type { Label } from "../types";

interface LabelChipProps {
  label: Label;
}

/**
 * Return true when the hex colour is perceptually dark (luminance < 0.5).
 * Accepts "#rrggbb" or "#rgb".
 */
function isDark(hex: string): boolean {
  let r: number, g: number, b: number;
  const h = hex.replace("#", "");
  if (h.length === 3) {
    r = parseInt(h[0] + h[0], 16);
    g = parseInt(h[1] + h[1], 16);
    b = parseInt(h[2] + h[2], 16);
  } else {
    r = parseInt(h.substring(0, 2), 16);
    g = parseInt(h.substring(2, 4), 16);
    b = parseInt(h.substring(4, 6), 16);
  }
  // Relative luminance (simplified sRGB)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance < 0.5;
}

export function LabelChip({ label }: LabelChipProps) {
  const textColor = isDark(label.color) ? "#ffffff" : "#202124";

  return (
    <span
      className="gmail-label-chip"
      aria-label={`Label: ${label.name}`}
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "999px",
        background: label.color,
        color: textColor,
        fontSize: "12px",
        fontWeight: 500,
        lineHeight: "20px",
        whiteSpace: "nowrap",
      }}
    >
      {label.name}
    </span>
  );
}
