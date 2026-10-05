"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

let gmailStylesPromise: Promise<string> | null = null;
let gmailStylesText: string | null = null;

async function loadGmailStyles() {
  if (gmailStylesText !== null) {
    return gmailStylesText;
  }

  if (!gmailStylesPromise) {
    gmailStylesPromise = fetch("/vendor/gmail-shadow.css", { cache: "force-cache" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Failed to load Gmail styles (${response.status})`);
        }
        const css = await response.text();
        gmailStylesText = css;
        return css;
      });
  }

  return gmailStylesPromise;
}

interface ShadowRootPortalProps {
  children: React.ReactNode;
  className?: string;
  fallback?: React.ReactNode;
  onShadowRoot?: (shadowRoot: ShadowRoot | null) => void;
}

export function ShadowRootPortal({
  children,
  className,
  fallback,
  onShadowRoot,
}: ShadowRootPortalProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const styleRef = useRef<HTMLStyleElement | null>(null);
  const [mountNode, setMountNode] = useState<HTMLDivElement | null>(null);
  const [stylesLoaded, setStylesLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    loadGmailStyles()
      .then((css) => {
        if (cancelled) {
          return;
        }
        if (styleRef.current) {
          styleRef.current.textContent = css;
        }
        setStylesLoaded(true);
      })
      .catch(() => {
        if (!cancelled) {
          setStylesLoaded(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) {
      return;
    }

    const shadowRoot = host.shadowRoot ?? host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    const mount = document.createElement("div");

    style.dataset.gmailShadow = "true";
    mount.className = "gmail-shadow-root";

    shadowRoot.append(style, mount);
    styleRef.current = style;
    setMountNode(mount);
    onShadowRoot?.(shadowRoot);

    if (gmailStylesText !== null) {
      style.textContent = gmailStylesText;
      setStylesLoaded(true);
    }

    return () => {
      onShadowRoot?.(null);
      shadowRoot.replaceChildren();
      styleRef.current = null;
    };
  }, [onShadowRoot]);

  return (
    <div ref={hostRef} className={className}>
      {mountNode && stylesLoaded ? createPortal(children, mountNode) : fallback}
    </div>
  );
}
