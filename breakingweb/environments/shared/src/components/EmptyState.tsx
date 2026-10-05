import type { PropsWithChildren, ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: PropsWithChildren<EmptyStateProps>) {
  return (
    <section className="wab-empty-state wab-card" aria-label={title}>
      {icon}
      <div>
        <h2 style={{ marginBottom: "0.45rem" }}>{title}</h2>
        <p style={{ margin: 0 }}>{description}</p>
      </div>
      {action}
    </section>
  );
}
