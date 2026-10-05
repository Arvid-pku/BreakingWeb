import { classNames } from "../utils/format";

interface AvatarProps {
  name: string;
  size?: number;
  color?: string;
  className?: string;
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function Avatar({ name, size = 40, color = "#5f63f2", className }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      className={classNames("wab-avatar", className)}
      style={{ width: size, height: size, backgroundColor: color }}
    >
      {initials(name)}
    </span>
  );
}
