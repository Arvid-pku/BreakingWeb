import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "./Button";

interface DropdownItem {
  label: string;
  onSelect: () => void;
  tone?: "default" | "danger";
}

interface DropdownProps {
  label: string;
  items: DropdownItem[];
  buttonLabel?: string;
  icon?: ReactNode;
}

export function Dropdown({ label, items, buttonLabel = "Actions", icon }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onMouseDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onMouseDown);
    return () => window.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  return (
    <div className="wab-dropdown" ref={rootRef}>
      <Button
        variant="ghost"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((value) => !value)}
      >
        {icon}
        {buttonLabel}
      </Button>
      {open ? (
        <div className="wab-dropdown__menu" role="menu" aria-label={label}>
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className="wab-dropdown__item"
              style={item.tone === "danger" ? { color: "var(--color-danger)" } : undefined}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
