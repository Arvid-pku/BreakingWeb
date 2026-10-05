import { useEffect, type PropsWithChildren, type ReactNode } from "react";

import { Button } from "./Button";

interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  footer?: ReactNode;
}

export function Modal({
  open,
  title,
  description,
  onClose,
  footer,
  children,
}: PropsWithChildren<ModalProps>) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div className="wab-modal-backdrop" role="presentation" onClick={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="wab-modal wab-card"
        onClick={(event) => event.stopPropagation()}
      >
        <header style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "start" }}>
          <div>
            <h2 style={{ margin: 0 }}>{title}</h2>
            {description ? (
              <p style={{ marginBottom: 0, color: "var(--color-text-muted)" }}>{description}</p>
            ) : null}
          </div>
          <Button variant="ghost" aria-label={`Close ${title}`} onClick={onClose}>
            Close
          </Button>
        </header>
        <div style={{ marginTop: "1rem" }}>{children}</div>
        {footer ? (
          <footer style={{ marginTop: "1.2rem", display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
            {footer}
          </footer>
        ) : null}
      </section>
    </div>
  );
}
