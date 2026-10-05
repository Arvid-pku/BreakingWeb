"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  AdapterProvider,
  createStaticAdapter,
} from "@breakingweb/shared";
import { GmailShell } from "@breakingweb/gmail/Shell";
import { gmailMutator, type GmailFixture } from "@breakingweb/gmail/mutator";
import { InboxPage } from "@breakingweb/gmail/pages/Inbox";
import { ThreadPage } from "@breakingweb/gmail/pages/Thread";
import { ComposePage } from "@breakingweb/gmail/pages/Compose";
import { SearchPage } from "@breakingweb/gmail/pages/Search";
import { SettingsPage } from "@breakingweb/gmail/pages/Settings";
import { LabelsPage } from "@breakingweb/gmail/pages/Labels";

import type { TrajectoryTarget } from "@/lib/results";
import "@breakingweb/shared/styles/base.css";
import "@breakingweb/gmail/gmail.css";
import "./gmail-scope.css";

interface GmailWrapperProps {
  fixture: GmailFixture;
  initialRoute?: string;
  route?: string;
  highlightTarget?: TrajectoryTarget | null;
  className?: string;
  onSettled?: () => void;
}

interface HighlightBox {
  top: number;
  left: number;
  width: number;
  height: number;
}

function GmailRouteSync({
  route,
  onRouteChange,
}: {
  route?: string;
  onRouteChange?: (route: string) => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const currentRoute = `${location.pathname}${location.search}`;

  useEffect(() => {
    onRouteChange?.(currentRoute);
  }, [currentRoute, onRouteChange]);

  useEffect(() => {
    if (!route || currentRoute === route) {
      return;
    }
    navigate(route, { replace: true });
  }, [currentRoute, navigate, route]);

  return null;
}

function normalizeText(value: string | null | undefined): string {
  return (value ?? "")
    .replace(/\s+/g, " ")
    .replace(/[“”]/g, "\"")
    .trim()
    .toLowerCase();
}

function isVisibleElement(el: HTMLElement): boolean {
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function buildSelectorCandidates(selector?: string): string[] {
  if (!selector) {
    return [];
  }

  const stripped = selector.replace(/:nth-of-type\(\d+\)/g, "").trim();
  const parts = stripped.split(">").map((part) => part.trim()).filter(Boolean);
  const selectors = new Set<string>([selector, stripped]);

  for (let i = 0; i < parts.length; i += 1) {
    selectors.add(parts.slice(i).join(" > "));
  }

  if (parts.length > 0) {
    selectors.add(parts[parts.length - 1]);
  }

  return Array.from(selectors).filter(Boolean);
}

function roleSelector(role?: string): string {
  switch (role) {
    case "button":
      return "button, [role='button']";
    case "link":
      return "a, [role='link']";
    case "tab":
      return "[role='tab'], button";
    case "textbox":
    case "searchbox":
      return "input, textarea, [role='textbox'], [contenteditable='true']";
    case "checkbox":
      return "input[type='checkbox'], [role='checkbox']";
    case "row":
      return "article, [role='row'], li";
    default:
      return "button, a, input, textarea, article, [role], [aria-label], [title]";
  }
}

function scoreElement(el: HTMLElement, target: TrajectoryTarget): number {
  let score = 0;
  const targetName = normalizeText(target.name);
  const descriptors = [
    el.getAttribute("aria-label"),
    el.getAttribute("title"),
    el.getAttribute("placeholder"),
    el.getAttribute("value"),
    el.textContent,
  ].map(normalizeText);

  if (targetName) {
    if (descriptors.some((value) => value === targetName)) {
      score += 120;
    } else if (descriptors.some((value) => value.includes(targetName))) {
      score += 80;
    } else {
      const targetTokens = targetName.split(" ").filter(Boolean);
      const matchedTokens = targetTokens.filter((token) =>
        descriptors.some((value) => value.includes(token)),
      );
      score += matchedTokens.length * 12;
    }
  }

  const role = target.role?.toLowerCase();
  if (role) {
    const tag = el.tagName.toLowerCase();
    const ariaRole = (el.getAttribute("role") ?? "").toLowerCase();
    if (
      (role === "button" && (tag === "button" || ariaRole === "button"))
      || (role === "link" && (tag === "a" || ariaRole === "link"))
      || (role === "tab" && ariaRole === "tab")
      || ((role === "textbox" || role === "searchbox") && (tag === "input" || tag === "textarea" || ariaRole === "textbox"))
      || (role === "checkbox" && ((el as HTMLInputElement).type === "checkbox" || ariaRole === "checkbox"))
    ) {
      score += 30;
    }
  }

  if (isVisibleElement(el)) {
    score += 10;
  }

  return score;
}

function queryElements(container: HTMLElement, selector: string): HTMLElement[] {
  try {
    return Array.from(container.querySelectorAll(selector)).filter(
      (el): el is HTMLElement => el instanceof HTMLElement,
    );
  } catch {
    return [];
  }
}

function pickBestMatch(elements: Iterable<HTMLElement>, target: TrajectoryTarget): HTMLElement | null {
  let best: HTMLElement | null = null;
  let bestScore = 0;

  for (const el of elements) {
    const score = scoreElement(el, target);
    if (score > bestScore) {
      best = el;
      bestScore = score;
    }
  }

  return bestScore >= 20 ? best : null;
}

function findTargetElement(container: HTMLElement, target: TrajectoryTarget): HTMLElement | null {
  for (const selector of buildSelectorCandidates(target.selector)) {
    const match = pickBestMatch(queryElements(container, selector), target);
    if (match) {
      return match;
    }
  }

  const roleMatch = pickBestMatch(queryElements(container, roleSelector(target.role)), target);
  if (roleMatch) {
    return roleMatch;
  }

  return null;
}

export function GmailWrapper({
  fixture,
  initialRoute = "/inbox?label=inbox",
  route,
  highlightTarget,
  className,
  onSettled,
}: GmailWrapperProps) {
  const adapter = useMemo(
    () => createStaticAdapter("gmail", fixture, gmailMutator),
    [fixture],
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const activeElementRef = useRef<HTMLElement | null>(null);
  const settleFrameRef = useRef<number | null>(null);
  const settleTimerRef = useRef<number | null>(null);
  const settleKeyRef = useRef<string>("");
  const [highlightBox, setHighlightBox] = useState<HighlightBox | null>(null);
  const startingRoute = route ?? initialRoute;
  const [renderedRoute, setRenderedRoute] = useState(startingRoute);
  const settleKey = `${route ?? startingRoute}|${highlightTarget?.role ?? ""}|${highlightTarget?.name ?? ""}|${highlightTarget?.selector ?? ""}`;

  const notifySettled = useCallback(() => {
    if (!onSettled || settleKeyRef.current === settleKey) {
      return;
    }

    settleKeyRef.current = settleKey;
    if (settleFrameRef.current !== null) {
      cancelAnimationFrame(settleFrameRef.current);
    }
    if (settleTimerRef.current !== null) {
      window.clearTimeout(settleTimerRef.current);
    }

    settleFrameRef.current = requestAnimationFrame(() => {
      settleTimerRef.current = window.setTimeout(() => {
        onSettled();
      }, 90);
    });
  }, [onSettled, settleKey]);

  const resolveHighlight = useCallback(() => {
    const container = containerRef.current;
    if (!container || !highlightTarget) {
      return false;
    }

    const el = findTargetElement(container, highlightTarget);
    if (!el) {
      return false;
    }

    activeElementRef.current = el;
    el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });
    return true;
  }, [highlightTarget]);

  useEffect(() => {
    settleKeyRef.current = "";
    return () => {
      if (settleFrameRef.current !== null) {
        cancelAnimationFrame(settleFrameRef.current);
        settleFrameRef.current = null;
      }
      if (settleTimerRef.current !== null) {
        window.clearTimeout(settleTimerRef.current);
        settleTimerRef.current = null;
      }
    };
  }, [settleKey]);

  useEffect(() => {
    if (!highlightTarget && (!route || renderedRoute === route)) {
      notifySettled();
    }
  }, [highlightTarget, notifySettled, renderedRoute, route]);

  useEffect(() => {
    setHighlightBox(null);
    activeElementRef.current = null;

    const container = containerRef.current;
    if (!container || !highlightTarget) {
      return;
    }

    if (route && renderedRoute !== route) {
      return;
    }

    let cancelled = false;
    let retryTimer: number | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let mutationObserver: MutationObserver | null = null;

    const updateBox = () => {
      const root = containerRef.current;
      const active = activeElementRef.current;
      if (!root || !active || !active.isConnected) {
        setHighlightBox(null);
        return;
      }

      const rootRect = root.getBoundingClientRect();
      const rect = active.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) {
        setHighlightBox(null);
        return;
      }

      setHighlightBox({
        top: rect.top - rootRect.top,
        left: rect.left - rootRect.left,
        width: rect.width,
        height: rect.height,
      });
    };

    const attachTracking = () => {
      const root = containerRef.current;
      const active = activeElementRef.current;
      if (!root || !active) {
        return;
      }

      updateBox();
      root.addEventListener("scroll", updateBox, true);
      window.addEventListener("resize", updateBox);
      if ("ResizeObserver" in window) {
        resizeObserver = new ResizeObserver(updateBox);
        resizeObserver.observe(root);
        resizeObserver.observe(active);
      }
    };

    const cleanupTracking = () => {
      const root = containerRef.current;
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer);
      }
      mutationObserver?.disconnect();
      resizeObserver?.disconnect();
      if (root) {
        root.removeEventListener("scroll", updateBox, true);
      }
      window.removeEventListener("resize", updateBox);
    };

    const tryResolve = () => {
      if (cancelled) {
        return true;
      }

      if (resolveHighlight()) {
        attachTracking();
        notifySettled();
        return true;
      }

      return false;
    };

    if (!tryResolve()) {
      let attempts = 0;
      mutationObserver = new MutationObserver(() => {
        if (activeElementRef.current && !activeElementRef.current.isConnected) {
          activeElementRef.current = null;
        }
        if (!activeElementRef.current) {
          tryResolve();
        } else {
          updateBox();
        }
      });
      mutationObserver.observe(container, {
        subtree: true,
        childList: true,
        attributes: true,
      });

      const retry = () => {
        if (cancelled || tryResolve()) {
          return;
        }
        if (attempts < 16) {
          attempts += 1;
          retryTimer = window.setTimeout(retry, Math.min(120 + attempts * 60, 500));
        } else {
          notifySettled();
        }
      };

      retry();
    }

    return () => {
      cancelled = true;
      cleanupTracking();
      activeElementRef.current = null;
      setHighlightBox(null);
    };
  }, [highlightTarget, notifySettled, renderedRoute, resolveHighlight, route]);

  return (
    <div ref={containerRef} className={`gmail-scope relative ${className ?? ""}`}>
      <AdapterProvider adapter={adapter}>
        <MemoryRouter initialEntries={[startingRoute]}>
          <GmailRouteSync route={route} onRouteChange={setRenderedRoute} />
          <Routes>
            <Route element={<GmailShell sessionId="static-session" />}>
              <Route path="inbox" element={<InboxPage />} />
              <Route path="thread/:emailId" element={<ThreadPage />} />
              <Route path="compose" element={<ComposePage />} />
              <Route path="search" element={<SearchPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="labels" element={<LabelsPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AdapterProvider>
      {highlightBox ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute z-50 rounded-[10px] border-2 border-[#1a73e8] shadow-[0_0_0_4px_rgba(26,115,232,0.14),0_0_14px_rgba(26,115,232,0.18)] transition-all duration-200 ease-out"
          style={{
            top: highlightBox.top - 4,
            left: highlightBox.left - 4,
            width: highlightBox.width + 8,
            height: highlightBox.height + 8,
          }}
        />
      ) : null}
    </div>
  );
}
