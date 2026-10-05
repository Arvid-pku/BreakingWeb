import { PropsWithChildren } from "react";

import { classNames } from "../utils/format";

interface BadgeProps {
  tone?: "default" | "primary" | "success" | "danger";
  className?: string;
}

const TONES: Record<NonNullable<BadgeProps["tone"]>, { background: string; color: string }> = {
  default: { background: "rgba(32, 48, 88, 0.08)", color: "#374151" },
  primary: { background: "rgba(26, 115, 232, 0.12)", color: "#1a73e8" },
  success: { background: "rgba(24, 128, 56, 0.14)", color: "#188038" },
  danger: { background: "rgba(217, 48, 37, 0.12)", color: "#d93025" },
};

export function Badge({ tone = "default", className, children }: PropsWithChildren<BadgeProps>) {
  const palette = TONES[tone];
  return (
    <span
      className={classNames("wab-badge", className)}
      style={{ background: palette.background, color: palette.color }}
    >
      {children}
    </span>
  );
}
