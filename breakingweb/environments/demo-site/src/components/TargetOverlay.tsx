"use client";

import { useEffect, useRef, useState } from "react";
import type { TrajectoryTarget } from "@/lib/results";

interface TargetOverlayProps {
  target: TrajectoryTarget | null;
  /** Ref to the container element the overlay is positioned relative to */
  containerRef: React.RefObject<HTMLDivElement | null>;
  /** Original viewport width during recording (default: 1280) */
  originalWidth?: number;
  /** Original viewport height during recording (default: 720) */
  originalHeight?: number;
}

/**
 * Renders a pulsing highlight overlay at the bbox position of the target element,
 * scaled proportionally to the current container size.
 */
export function TargetOverlay({
  target,
  containerRef,
  originalWidth = 1280,
  originalHeight = 720,
}: TargetOverlayProps) {
  const [rect, setRect] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const bbox = target?.bbox;
    const container = containerRef.current;
    if (!bbox || !container) {
      setRect(null);
      return;
    }

    const update = () => {
      const containerRect = container.getBoundingClientRect();
      const scaleX = containerRect.width / originalWidth;
      const scaleY = containerRect.height / originalHeight;

      setRect({
        left: bbox.x * scaleX,
        top: bbox.y * scaleY,
        width: Math.max(bbox.width * scaleX, 24),
        height: Math.max(bbox.height * scaleY, 24),
      });
    };

    // Delay to let layout settle after route change
    const timer = window.setTimeout(update, 200);

    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(rafRef.current);
    };
  }, [target, containerRef, originalWidth, originalHeight]);

  if (!rect) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: `${rect.left}px`,
        top: `${rect.top}px`,
        width: `${rect.width}px`,
        height: `${rect.height}px`,
        pointerEvents: "none",
        zIndex: 9999,
        border: "2px solid #1a73e8",
        borderRadius: "4px",
        boxShadow: "0 0 0 4px rgba(26, 115, 232, 0.2), 0 0 12px rgba(26, 115, 232, 0.3)",
        transition: "all 200ms ease-out",
      }}
    >
      {/* Pulsing dot in top-right corner */}
      <div
        style={{
          position: "absolute",
          top: "-5px",
          right: "-5px",
          width: "10px",
          height: "10px",
          borderRadius: "50%",
          background: "#1a73e8",
          animation: "wab-pulse 1.5s ease-in-out infinite",
        }}
      />
      <style>{`
        @keyframes wab-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(1.4); }
        }
      `}</style>
    </div>
  );
}
