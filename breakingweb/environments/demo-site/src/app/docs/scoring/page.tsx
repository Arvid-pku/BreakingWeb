import Link from "next/link";
import { CodeBlock } from "@/components/docs/CodeBlock";

export default function ScoringDocsPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Scoring
      </p>

      <h1 className="text-2xl font-medium tracking-tight mb-3">
        Scoring
      </h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-12 max-w-[580px]">
        How BreakingWeb turns a trajectory into a single number between 0 and 1.
      </p>

      {/* Formula */}
      <section className="mb-12">
        <h2 id="formula" className="text-lg font-medium tracking-tight mb-4">
          The Score Formula
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Every task produces a final score in the range [0, 1]. The formula combines a base score
          derived from positive criteria, any penalties from negative checks, and a small trajectory
          efficiency modifier:
        </p>
        <CodeBlock code="final_score = clamp(0-1, base_score - penalties + trajectory_mod)" language="python" />
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          The result is always clamped to [0, 1], so penalties can never push the score below zero
          and the trajectory modifier can never push it above one.
        </p>
      </section>

      {/* Base Score */}
      <section className="mb-12">
        <h2 id="base-score" className="text-lg font-medium tracking-tight mb-4">
          Base Score
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          The base score is the fraction of positive criteria the agent satisfied:
        </p>
        <CodeBlock code="base_score = passed_criteria / total_criteria" language="python" />
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          Each criterion carries an implied weight of <span className="font-mono">1 / total_criteria</span>.
          Criteria are defined per-task in the benchmark manifest and cover observable outcomes such
          as sent emails, filled form fields, clicked buttons, and navigated states.
        </p>
      </section>

      {/* Negative Checks */}
      <section className="mb-12">
        <h2 id="negative-checks" className="text-lg font-medium tracking-tight mb-4">
          Negative Checks (Penalties)
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          In addition to positive criteria, tasks may define negative checks — guard-rail assertions
          that test for behaviours the agent must <em>avoid</em>. Each failing negative check
          subtracts an explicit penalty value from the base score.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Negative checks model real-world constraints such as privacy requirements, data integrity
          rules, and interaction boundaries. An agent that completes the task but violates a
          guard-rail should score lower than one that stops cleanly.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          For a full list of negative checks used across the benchmark, see the{" "}
          <Link
            href="/results/negative-checks"
            className="text-[var(--accent)] no-underline hover:underline"
          >
            negative checks reference
          </Link>
          .
        </p>
      </section>

      {/* Trajectory Modifier */}
      <section className="mb-12">
        <h2 id="trajectory-modifier" className="text-lg font-medium tracking-tight mb-4">
          Trajectory Modifier
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          A small modifier rewards agents that complete tasks efficiently and penalises those that
          wander. It is computed from the ratio of steps taken to the task&apos;s reference step
          count, then clamped to [−0.10, +0.10]:
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden mb-5">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Category</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Condition</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Modifier</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Efficient</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">steps ≤ 70% of reference</td>
                <td className="px-4 py-2.5 font-mono text-[var(--green)]">+0.03</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Normal</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">70% &lt; steps ≤ 180%</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">0.00</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Excessive</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">steps &gt; 180% of reference</td>
                <td className="px-4 py-2.5 font-mono text-[var(--red)]">−0.05</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          The modifier is clamped to [−0.10, +0.10] before being added to the score, so no single
          efficiency signal can dominate the final result.
        </p>
      </section>

      {/* Worked Example */}
      <section className="mb-12">
        <h2 id="example" className="text-lg font-medium tracking-tight mb-4">
          Worked Example
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Consider the <strong className="font-medium text-[var(--text-primary)]">Thread Detective</strong> task,
          which has 5 positive criteria and 2 negative checks. The agent passed 4 of 5 positive
          criteria and all negative checks, completing the task in the normal step range.
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden mb-5">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Check</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Type</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Result</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Impact</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Exactly one email was sent</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Positive</td>
                <td className="px-4 py-2.5 text-[var(--green)]">✓</td>
                <td className="px-4 py-2.5 font-mono text-[var(--green)]">+0.20</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Reply sent to correct sender</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Positive</td>
                <td className="px-4 py-2.5 text-[var(--green)]">✓</td>
                <td className="px-4 py-2.5 font-mono text-[var(--green)]">+0.20</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Contains correct time</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Positive</td>
                <td className="px-4 py-2.5 text-[var(--green)]">✓</td>
                <td className="px-4 py-2.5 font-mono text-[var(--green)]">+0.20</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Reply is threaded</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Positive</td>
                <td className="px-4 py-2.5 text-[var(--green)]">✓</td>
                <td className="px-4 py-2.5 font-mono text-[var(--green)]">+0.20</td>
              </tr>
              <tr className="border-b border-[var(--border)] bg-[var(--red)]/5">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Targets most recent thread</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Positive</td>
                <td className="px-4 py-2.5 text-[var(--red)]">✗</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-tertiary)]">+0.00</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 text-[var(--text-primary)]">No conflicting times mentioned</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Negative</td>
                <td className="px-4 py-2.5 text-[var(--green)]">✓</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-tertiary)]">0.00</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 text-[var(--text-primary)]">Not Reply All</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Negative</td>
                <td className="px-4 py-2.5 text-[var(--green)]">✓</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-tertiary)]">0.00</td>
              </tr>
            </tbody>
          </table>
        </div>
        <CodeBlock code={`base_score     = 4 / 5 = 0.80
penalties      = 0.00
trajectory_mod = 0.00

final_score    = clamp(0-1, 0.80 - 0.00 + 0.00) = 0.80`} language="python" />
      </section>

      {/* Pass/Fail */}
      <section className="mb-12">
        <h2 id="pass-fail" className="text-lg font-medium tracking-tight mb-4">
          Pass / Fail
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-4">
          A task is considered <span className="text-[var(--green)] font-medium">passed</span> only
          when the agent satisfies <em>all</em> positive criteria <em>and</em> all negative checks.
          Partial credit is reflected in the numeric score, but the binary pass/fail label requires
          a perfect run.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          This strict definition ensures that leaderboard pass-rates measure complete, safe task
          completion rather than partial progress, making them a more reliable signal for comparing
          agents.
        </p>
      </section>
    </>
  );
}
