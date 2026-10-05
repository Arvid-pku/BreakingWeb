"use client";

/**
 * Evaluation criteria display — used in task detail (preview mode, no results)
 * and trajectory replay (with pass/fail results).
 */

interface Criterion {
  desc: string;
  passed?: boolean;
  penalty?: number;
}

interface EvalCriteriaProps {
  /** Section label — defaults to "Evaluation criteria" */
  label?: string;
  /** Overall score (0-1), shown as a colored bar */
  score?: number;
  /** Whether the overall evaluation passed */
  success?: boolean;
  /** Evaluator reasoning text */
  reasoning?: string;
  /** List of criteria with optional pass/fail results */
  criteria: Criterion[];
  /** Compact horizontal layout (for replay bottom bar) */
  compact?: boolean;
}

function ScoreBar({ score, success }: { score: number; success: boolean }) {
  const pct = Math.max(0, Math.min(100, score * 100));
  const color = success
    ? "var(--green)"
    : score > 0.5
      ? "var(--amber)"
      : "var(--red)";

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-[3px] bg-[var(--border)] rounded-full overflow-hidden max-w-[120px]">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="font-mono text-sm font-medium" style={{ color }}>
        {score.toFixed(2)}
      </span>
      <span
        className="text-[10px] font-medium px-2 py-0.5 rounded-lg"
        style={{
          color,
          background: success
            ? "oklch(78% 0.14 155 / 0.12)"
            : score > 0.5
              ? "oklch(75% 0.13 85 / 0.12)"
              : "oklch(72% 0.15 25 / 0.12)",
        }}
      >
        {success ? "Pass" : "Fail"}
      </span>
    </div>
  );
}

export function EvalCriteria({
  label = "Evaluation criteria",
  score,
  success,
  reasoning,
  criteria,
  compact = false,
}: EvalCriteriaProps) {
  if (criteria.length === 0 && score === undefined) return null;

  const hasResults = criteria.some((c) => c.passed !== undefined);
  const passCount = criteria.filter((c) => c.passed).length;
  const totalCount = criteria.length;

  const regularCount = criteria.filter((cr) => cr.penalty == null).length;
  const impliedWeight = regularCount > 0 ? 1 / regularCount : 0;

  if (compact) {
    return (
      <div className="flex items-start gap-6">
        {/* Score + pass/fail badge */}
        {score !== undefined && success !== undefined && (
          <div className="shrink-0">
            <ScoreBar score={score} success={success} />
          </div>
        )}

        {/* Criteria as horizontal chips */}
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 flex-1">
          {criteria.map((cr, i) => {
            const isPassed = cr.passed;
            const isFailed = cr.passed === false;
            const isNegativeCheck = cr.penalty != null;

            return (
              <div key={i} className="flex items-center gap-1.5">
                {hasResults && (
                  <span className={`text-[11px] font-mono ${isPassed ? "text-[var(--green)]" : isFailed ? "text-[var(--red)]" : "text-[var(--text-tertiary)]"}`}>
                    {isPassed ? "✓" : isFailed ? "✗" : "·"}
                  </span>
                )}
                <span className={`text-[12px] ${isFailed ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                  {cr.desc}
                </span>
                {isFailed && isNegativeCheck && (
                  <span className="font-mono text-[10px] text-[var(--red)] opacity-70">
                    penalty: -{cr.penalty}
                  </span>
                )}
                {isFailed && !isNegativeCheck && (
                  <span className="font-mono text-[10px] text-[var(--amber)] opacity-70">
                    weight: {impliedWeight.toFixed(2)}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header with label + optional tally */}
      <div className="flex items-baseline gap-3 mb-4">
        <p className="text-[12px] font-medium text-[var(--text-tertiary)]">
          {label}
        </p>
        {hasResults && (
          <span className="font-mono text-[11px] text-[var(--text-tertiary)]">
            {passCount}/{totalCount} passed
          </span>
        )}
      </div>

      {/* Score bar */}
      {score !== undefined && success !== undefined && (
        <div className="mb-5">
          <ScoreBar score={score} success={success} />
        </div>
      )}

      {/* Reasoning */}
      {reasoning && (
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5 max-w-[600px]">
          {reasoning}
        </p>
      )}

      {/* Criteria list */}
      <div className="flex flex-col gap-0">
        {criteria.map((cr, i) => {
          const isPassed = cr.passed;
          const isFailed = cr.passed === false;
          const isNegativeCheck = cr.penalty != null;

          return (
            <div
              key={i}
              className={`flex items-start gap-3 py-2.5 border-b border-[var(--border)] last:border-0 ${
                isFailed ? "bg-[oklch(72%_0.15_25_/_0.04)]" : ""
              }`}
            >
              {/* Status indicator */}
              <div className="shrink-0 w-5 pt-0.5">
                {hasResults ? (
                  <span
                    className={`font-mono text-xs ${
                      isPassed ? "text-[var(--green)]" : isFailed ? "text-[var(--red)]" : "text-[var(--text-tertiary)]"
                    }`}
                  >
                    {isPassed ? "✓" : isFailed ? "✗" : "·"}
                  </span>
                ) : (
                  <span className="font-mono text-xs text-[var(--text-tertiary)]">
                    {i + 1}.
                  </span>
                )}
              </div>

              {/* Description */}
              <div className="flex-1 min-w-0">
                <p className={`text-[14px] leading-[1.6] ${isFailed ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                  {cr.desc}
                </p>
              </div>

              {/* Penalty badge (negative check) */}
              {isFailed && isNegativeCheck && (
                <span className="shrink-0 font-mono text-[11px] text-[var(--red)] bg-[oklch(72%_0.15_25_/_0.08)] px-2 py-0.5 rounded">
                  penalty: -{cr.penalty}
                </span>
              )}

              {/* Implied weight badge (regular criterion) */}
              {isFailed && !isNegativeCheck && (
                <span className="shrink-0 font-mono text-[11px] text-[var(--amber)] bg-[oklch(75%_0.13_85_/_0.08)] px-2 py-0.5 rounded">
                  weight: {impliedWeight.toFixed(2)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
