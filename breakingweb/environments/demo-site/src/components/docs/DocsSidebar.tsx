"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const sections = [
  { href: "/docs", label: "Overview", exact: true },
  { href: "/docs/scoring", label: "Scoring" },
  { href: "/docs/primitives", label: "Cognitive Primitives" },
  { href: "/docs/architecture", label: "Architecture" },
  { href: "/docs/benchmark", label: "Benchmark" },
];

export function DocsSidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-0.5">
      <p className="text-[11px] font-medium text-[var(--text-tertiary)] mb-3 px-3">
        Documentation
      </p>
      {sections.map((s) => {
        const active = "exact" in s ? pathname === s.href : pathname.startsWith(s.href);
        return (
          <Link
            key={s.href}
            href={s.href}
            className={`text-[13px] px-3 py-[6px] rounded-lg no-underline transition-colors duration-150 ${
              active
                ? "text-[var(--text-primary)] font-medium bg-[var(--surface)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)]"
            }`}
          >
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}
