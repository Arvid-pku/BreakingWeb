import Link from "next/link";
import { PrimitivePill } from "@/components/ui/PrimitivePill";

const primitives = [
  {
    name: "memory",
    definition:
      "Maintaining and retrieving relevant context across many steps, pages, or interaction phases.",
    example:
      "Finding a name in one email, then referencing it when composing a reply several steps later.",
  },
  {
    name: "planning",
    definition:
      "Decomposing a complex task into sub-goals and coordinating constraints across steps.",
    example:
      "Applying interdependent filters in the correct order when the sequence matters.",
  },
  {
    name: "attention",
    definition:
      "Maintaining goal-directed behavior despite popups, modals, overlays, and distractions.",
    example:
      "Dismissing a newsletter modal, cookie banner, and chat widget to reach the actual content.",
  },
  {
    name: "exploration",
    definition:
      "Systematically searching through alternatives when the initial approach fails.",
    example:
      "Loading additional search results and expanding collapsed sections to find hidden data.",
  },
  {
    name: "backtracking",
    definition:
      "Detecting that a chosen path is wrong and reverting to a prior decision point.",
    example:
      "Navigating back through a multi-step wizard after discovering a coverage gap.",
  },
  {
    name: "adversarial",
    definition:
      "Resisting dark patterns, misleading labels, confirmshaming, and deliberate UI deceptions.",
    example:
      "Recognizing that a prominently placed button subscribes rather than completes purchase.",
  },
  {
    name: "patience",
    definition:
      "Waiting for asynchronous content to load and not acting prematurely on incomplete information.",
    example:
      "Waiting for a spinner to finish loading additional results before concluding a search.",
  },
  {
    name: "verification",
    definition:
      "Confirming that an action achieved its intended effect, especially with misleading feedback.",
    example:
      "Checking the sidebar after a success banner to verify settings were actually saved.",
  },
  {
    name: "arithmetic",
    definition:
      "Performing numerical calculations correctly within multi-step workflows.",
    example:
      "Summing invoice line items and verifying the total matches across documents.",
  },
  {
    name: "comprehension",
    definition:
      "Extracting meaning from complex, multi-part text and following nuanced instructions.",
    example:
      "Parsing a long email thread to identify which of several proposed times is conflict-free.",
  },
  {
    name: "composition",
    definition:
      "Combining multiple primitives within a single task to achieve a complex goal.",
    example:
      "A task requiring exploration to find data, memory to retain it, and planning to act on it.",
  },
  {
    name: "resilience",
    definition:
      "Handling failures gracefully — interpreting errors, retrying with modifications, preserving progress.",
    example:
      "Persisting through form submission errors and saving a draft before a session-clearing failure.",
  },
];

export default function PrimitivesPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Cognitive Primitives
      </p>
      <h1 className="text-[clamp(1.8rem,3vw,2.5rem)] font-medium tracking-tight leading-[1.2] mb-4">
        Cognitive Primitives
      </h1>
      <p className="text-[16px] text-[var(--text-secondary)] leading-[1.75] max-w-[600px] mb-12">
        BreakingWeb organizes web agent capabilities into 12 cognitive primitives — the atomic
        skills required to complete realistic browser tasks. Each benchmark page is designed to
        stress one or more of these primitives, enabling precise diagnosis of where and why agents
        fail.
      </p>

      {/* Pill row */}
      <div className="flex flex-wrap gap-2 mb-14">
        {primitives.map((p) => (
          <Link key={p.name} href={`#${p.name}`} className="no-underline">
            <PrimitivePill name={p.name} />
          </Link>
        ))}
      </div>

      {/* Taxonomy */}
      <h2
        id="taxonomy"
        className="text-[1.25rem] font-medium tracking-tight mb-8 scroll-mt-[100px]"
      >
        Taxonomy
      </h2>

      <div className="flex flex-col gap-0 mb-16">
        {primitives.map((p, i) => (
          <section
            key={p.name}
            id={p.name}
            className={`scroll-mt-[100px] py-6 ${i < primitives.length - 1 ? "border-b border-[var(--border)]" : ""}`}
          >
            <div className="mb-3">
              <PrimitivePill name={p.name} />
            </div>
            <p className="text-[15px] text-[var(--text-primary)] leading-[1.7] mb-3">
              {p.definition}
            </p>
            <p className="text-[13px] text-[var(--text-secondary)] leading-[1.65] border-l-2 border-[var(--border)] pl-4 italic">
              {p.example}
            </p>
          </section>
        ))}
      </div>

      {/* Research basis */}
      <h2
        id="research-basis"
        className="text-[1.25rem] font-medium tracking-tight mb-6 scroll-mt-[100px]"
      >
        Research Basis
      </h2>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-4">
        The primitives taxonomy is grounded in published findings on web agent failure modes:
      </p>
      <ul className="flex flex-col gap-3 mb-8">
        {[
          "Agents achieve only 30–61% on realistic web tasks (Online-Mind2Web, COLM 2025)",
          "Injecting realistic network errors causes 70–95% performance drops (WAREX, 2025)",
          "Vision-language agents click adversarial pop-ups 86–100% of the time (PopupAttack, ACL 2025)",
          "A single dark pattern compromises agent intent in 41% of runs (Ersoy et al., IEEE S&P 2026)",
          "Explicit backtracking improves success by ~7.6% on GUI benchmarks (BacktrackAgent, EMNLP 2025)",
          "Separating planning from execution improves WebArena-Lite to 57.58% (Plan-and-Act, ICML 2025)",
        ].map((finding) => (
          <li
            key={finding}
            className="flex gap-3 text-[14px] text-[var(--text-secondary)] leading-[1.65]"
          >
            <span className="mt-[6px] shrink-0 w-[5px] h-[5px] rounded-full bg-[var(--text-tertiary)]" />
            {finding}
          </li>
        ))}
      </ul>
    </>
  );
}
