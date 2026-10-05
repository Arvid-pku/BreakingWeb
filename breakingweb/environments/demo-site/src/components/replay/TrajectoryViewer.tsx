"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TrajectoryStep } from "@/lib/results";
import { StepControls } from "./StepControls";

interface TrajectoryViewerProps {
  steps: TrajectoryStep[];
  current: number;
  onStep: (index: number) => void;
  onCopyAll?: () => void;
  isBusy?: boolean;
}

export function TrajectoryViewer({
  steps,
  current,
  onStep,
  onCopyAll,
  isBusy = false,
}: TrajectoryViewerProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const [copiedStep, setCopiedStep] = useState<number | null>(null);

  const handleStep = useCallback(
    (idx: number) => onStep(Math.max(0, Math.min(steps.length - 1, idx))),
    [onStep, steps.length],
  );

  // Auto-scroll to active step
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-step="${current}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [current]);

  const copyStepData = useCallback(
    (idx: number, e: React.MouseEvent) => {
      e.stopPropagation();
      const s = steps[idx];
      const payload = { thought: s.thought, action: s.action };
      navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setCopiedStep(idx);
      setTimeout(() => setCopiedStep(null), 1500);
    },
    [steps],
  );

  if (steps.length === 0) return null;

  const actionColor: Record<string, string> = {
    click: "var(--accent)",
    fill: "var(--green)",
    scroll: "var(--amber)",
    select: "var(--red)",
  };

  return (
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="shrink-0 px-3 py-1.5">
        <StepControls current={current} total={steps.length} onStep={handleStep} isBusy={isBusy} />
      </div>

      {/* Scrollable card list in recessed well */}
      <div
        ref={listRef}
        className={`flex-1 overflow-y-auto min-h-0 mx-2 mb-2 p-1.5 rounded-xl bg-[var(--bg)] flex flex-col gap-[3px] transition-opacity duration-150 ${
          isBusy ? "opacity-90" : "opacity-100"
        }`}
      >
        {steps.map((s, i) => {
          const isActive = i === current;
          const elapsed = Number.isFinite(s.elapsed_seconds) ? s.elapsed_seconds : 0;
          const target =
            s.targets?.ref
            ?? s.targets?.from_ref
            ?? s.targets?.to_ref
            ?? null;
          const targetLabel =
            target?.role || target?.name
              ? `${target.role ?? "element"}${target.name ? ` "${target.name}"` : ""}`
              : null;
          const actionType = (s.action?.action as string | undefined) ?? "action";
          const color = actionColor[actionType] ?? "var(--text-secondary)";

          return (
            <button
              key={s.step}
              data-step={i}
              onClick={() => handleStep(i)}
              className="text-left w-full rounded-[9px] border-none transition-all duration-200"
              style={{
                background: isActive
                  ? `color-mix(in oklch, ${color} 7%, var(--card-bg))`
                  : "var(--card-bg)",
                boxShadow: isActive
                  ? `inset 0 0 0 1.5px color-mix(in oklch, ${color} 20%, transparent)`
                  : "none",
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.background = "var(--card-hover)";
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.background = "var(--card-bg)";
              }}
            >
              {/* Summary row */}
              <div className="flex items-center gap-2 px-2.5 py-[7px] min-w-0">
                <span
                  className="flex items-center justify-center w-[22px] h-[22px] rounded-md text-[11px] font-semibold shrink-0 tabular-nums"
                  style={isActive
                    ? { color, background: `color-mix(in oklch, ${color} 10%, transparent)` }
                    : { color: "var(--text-tertiary)" }
                  }
                >
                  {s.step}
                </span>
                <span
                  className="text-[10px] font-semibold uppercase tracking-wide px-[7px] py-[2px] rounded-[5px] shrink-0"
                  style={{
                    color,
                    background: `color-mix(in oklch, ${color} 10%, transparent)`,
                  }}
                >
                  {actionType}
                </span>
                {targetLabel && (
                  <span className={`text-[12px] flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap ${
                    isActive ? "text-[var(--text-secondary)]" : "text-[var(--text-tertiary)]"
                  }`}>
                    {targetLabel}
                  </span>
                )}
                {!targetLabel && <span className="flex-1" />}
                <span className="text-[10px] text-[var(--text-tertiary)] tabular-nums shrink-0">
                  {elapsed.toFixed(1)}s
                </span>
              </div>

              {/* Expanded detail — active step only */}
              {isActive && (
                <div className="px-2.5 pb-2.5 flex flex-col gap-2">
                  {/* Thought */}
                  {s.thought && (
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                          Thought
                        </span>
                        <button
                          onClick={(e) => copyStepData(i, e)}
                          className="text-[10px] font-medium text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg)] bg-transparent border-none rounded-[5px] px-2 py-[2px] cursor-pointer transition-all duration-150"
                        >
                          {copiedStep === i ? "Copied!" : "Copy step"}
                        </button>
                      </div>
                      <p className="text-[12px] leading-[1.5] text-[var(--text-secondary)] break-words">
                        {s.thought}
                      </p>
                    </div>
                  )}

                  {/* Action JSON */}
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                      Action
                    </span>
                    <code className="font-mono text-[11px] leading-[1.5] text-[var(--accent)] bg-[var(--bg)] rounded-md px-2.5 py-2 whitespace-pre-wrap break-all">
                      {JSON.stringify(s.action, null, 2)}
                    </code>
                  </div>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
