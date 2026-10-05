import Link from "next/link";
import { StatRow } from "@/components/ui/StatRow";
import { PrimitivePill } from "@/components/ui/PrimitivePill";

const PRIMITIVES = [
  "memory", "planning", "attention", "exploration", "backtracking", "adversarial",
  "patience", "verification", "arithmetic", "comprehension", "composition", "resilience",
];

export default function LandingPage() {
  return (
    <div className="max-w-[720px] mx-auto px-12">
      {/* Hero */}
      <section className="pt-[120px] pb-20">
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
          Research
        </p>
        <h1 className="text-[clamp(2rem,4vw,3.2rem)] font-medium tracking-tight leading-[1.15] mb-7">
          Benchmarking web agents on cognitive primitives
        </h1>
        <p className="text-[17px] text-[var(--text-secondary)] leading-[1.75] max-w-[540px]">
          70 tasks that test whether AI agents can navigate complex web interfaces — requiring
          memory, planning, backtracking, and adversarial robustness, not just clicking buttons.
        </p>
        <div className="flex gap-4 mt-10">
          <Link
            href="/environment"
            className="text-sm font-medium px-6 py-[10px] bg-[var(--text-primary)] text-[var(--bg)] rounded-xl no-underline hover:opacity-85 transition-opacity"
          >
            Explore environment
          </Link>
          <a
            href="#"
            className="text-sm font-medium px-6 py-[10px] border border-[var(--border)] text-[var(--text-secondary)] rounded-xl no-underline hover:text-[var(--text-primary)] hover:border-[var(--text-tertiary)] transition-colors"
          >
            Read paper
          </a>
        </div>
      </section>

      <hr className="border-[var(--border)]" />

      <StatRow
        stats={[
          { value: "70", label: "tasks" },
          { value: "12", label: "cognitive primitives" },
          { value: "5", label: "difficulty tiers" },
        ]}
      />

      <hr className="border-[var(--border)]" />

      {/* Environment preview */}
      <section className="py-20">
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-4">
          Environment
        </p>
        <h2 className="text-2xl font-medium tracking-tight mb-3">
          Agents see structure, not pixels
        </h2>
        <p className="text-[15px] text-[var(--text-secondary)] leading-[1.7] max-w-[540px]">
          Each task presents a fully interactive Gmail simulation. The agent perceives the interface
          as an indexed accessibility tree and acts through structured commands.
        </p>
        <div className="mt-10 border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)] font-mono text-[13px] text-[var(--text-secondary)]">
            <span className="w-[7px] h-[7px] rounded-full bg-[var(--green)]" />
            accessibility tree · gmail_thread_detective
          </div>
          <div className="p-6 bg-[var(--surface-raised)] font-mono text-[13px] text-[var(--text-secondary)] leading-8">
            <span className="text-[var(--text-tertiary)] mr-1">[1]</span>{" "}
            <span className="text-[var(--accent)]">button</span>{" "}
            <span className="text-[var(--text-primary)]">&quot;Compose&quot;</span>
            <br />
            <span className="text-[var(--text-tertiary)] mr-1">[2]</span>{" "}
            <span className="text-[var(--accent)]">navigation</span>{" "}
            <span className="text-[var(--text-primary)]">&quot;Inbox (23)&quot;</span>
            <br />
            <span className="text-[var(--text-tertiary)] mr-1">[3]</span>{" "}
            <span className="text-[var(--accent)]">navigation</span>{" "}
            <span className="text-[var(--text-primary)]">&quot;Starred&quot;</span>
            <br />
            <span className="text-[var(--text-tertiary)] mr-1">[4]</span>{" "}
            <span className="text-[var(--accent)]">navigation</span>{" "}
            <span className="text-[var(--text-primary)]">&quot;Sent&quot;</span>
            <br />
            <span className="text-[var(--text-tertiary)] mr-1">[5]</span>{" "}
            <span className="text-[var(--accent)]">row</span>{" "}
            <span className="text-[var(--text-primary)]">
              &quot;Dr. Sarah Chen · Re: Lab meeting rescheduled — Hi team, given the...&quot;
            </span>
            <br />
            <span className="text-[var(--text-tertiary)]">···</span>
          </div>
        </div>
      </section>

      <hr className="border-[var(--border)]" />

      {/* Primitives */}
      <section className="py-20">
        <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-4">
          Taxonomy
        </p>
        <h2 className="text-2xl font-medium tracking-tight mb-3">
          Twelve cognitive primitives
        </h2>
        <p className="text-[15px] text-[var(--text-secondary)] leading-[1.7] max-w-[540px]">
          Tasks are designed to isolate specific capabilities. Each task targets 2–3 primary
          primitives, exposing where agents succeed and where they break down.
        </p>
        <div className="flex flex-wrap gap-2 mt-8">
          {PRIMITIVES.map((p) => (
            <PrimitivePill key={p} name={p} />
          ))}
        </div>
      </section>

      <hr className="border-[var(--border)]" />

      {/* Footer */}
      <footer className="flex justify-between py-16 text-xs text-[var(--text-secondary)]">
        <div className="flex gap-6">
          <a href="#" className="no-underline text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">Paper</a>
          <a href="#" className="no-underline text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">GitHub</a>
          <a href="#" className="no-underline text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">Contact</a>
        </div>
        <span>v10</span>
      </footer>
    </div>
  );
}
