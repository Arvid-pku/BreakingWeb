"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTheme } from "./ThemeProvider";

const links = [
  { href: "/", label: "Home", exact: true },
  { href: "/environment", label: "Environment", exact: false },
  { href: "/tasks", label: "Tasks", exact: false },
  { href: "/docs", label: "Docs", exact: false },
  { href: "/results", label: "Results", exact: false },
];

const external = [
  { href: "#", label: "Paper" },
  { href: "#", label: "GitHub" },
];

const SCROLL_THRESHOLD = 10;

function isActive(pathname: string, link: { href: string; exact: boolean }) {
  if (link.exact) return pathname === link.href;
  return pathname.startsWith(link.href);
}

export function Nav() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const linkRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null);

  const [scrolled, setScrolled] = useState(false);
  const [hidden, setHidden] = useState(false);
  const lastScrollY = useRef(0);

  const updatePill = useCallback(() => {
    const activeIdx = links.findIndex((l) => isActive(pathname, l));
    const el = linkRefs.current[activeIdx];
    const container = containerRef.current;
    if (!el || !container) {
      setPill(null);
      return;
    }
    const cRect = container.getBoundingClientRect();
    const eRect = el.getBoundingClientRect();
    setPill({ left: eRect.left - cRect.left, width: eRect.width });
  }, [pathname]);

  useEffect(() => {
    updatePill();
  }, [updatePill]);

  useEffect(() => {
    window.addEventListener("resize", updatePill);
    return () => window.removeEventListener("resize", updatePill);
  }, [updatePill]);

  const scrolledRef = useRef(false);
  const hiddenRef = useRef(false);

  useEffect(() => {
    const handleScroll = () => {
      const currentY = window.scrollY;
      const nowScrolled = currentY > 20;
      if (nowScrolled !== scrolledRef.current) {
        scrolledRef.current = nowScrolled;
        setScrolled(nowScrolled);
      }
      const delta = currentY - lastScrollY.current;
      if (delta > SCROLL_THRESHOLD && currentY > 80 && !hiddenRef.current) {
        hiddenRef.current = true;
        setHidden(true);
      } else if (delta < -SCROLL_THRESHOLD && hiddenRef.current) {
        hiddenRef.current = false;
        setHidden(false);
      }
      lastScrollY.current = currentY;
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav className={`sticky top-0 z-50 flex justify-between items-center w-full px-6 backdrop-blur-lg transition-all duration-300 ease-out ${
      scrolled ? "py-2.5 bg-[var(--bg)]/90 shadow-[0_1px_0_0_var(--border)]" : "py-4 bg-[var(--bg)]/80"
    } ${hidden ? "-translate-y-full" : "translate-y-0"}`}>
      <Link href="/" className="text-[15px] font-semibold text-[var(--text-primary)] tracking-tight no-underline">
        BreakingWeb
      </Link>
      <div ref={containerRef} className="relative flex items-center gap-1 bg-[var(--surface-raised)] rounded-xl p-1">
        {/* Sliding pill indicator */}
        {pill && (
          <div
            className="absolute top-1 bottom-1 rounded-[10px] bg-[var(--surface)] transition-all duration-300 ease-out"
            style={{ left: pill.left, width: pill.width }}
          />
        )}
        {links.map((link, i) => (
          <Link
            key={link.href}
            href={link.href}
            ref={(el) => { linkRefs.current[i] = el; }}
            className={`relative z-10 no-underline text-[13px] px-4 py-[6px] rounded-[10px] transition-colors duration-150 ${
              isActive(pathname, link)
                ? "text-[var(--text-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>
      <div className="flex items-center gap-6 text-[13px] text-[var(--text-secondary)]">
        {external.map((link) => (
          <a
            key={link.label}
            href={link.href}
            className="no-underline text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors duration-150"
          >
            {link.label}
          </a>
        ))}
        <button
          onClick={toggle}
          aria-label="Toggle theme"
          className="p-1.5 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)] transition-colors duration-150"
        >
          {theme === "dark" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>
      </div>
    </nav>
  );
}
