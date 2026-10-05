import { CodeBlock } from "@/components/docs/CodeBlock";

export default function EnvironmentsPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Environments
      </p>

      <h1 className="text-2xl font-medium tracking-tight mb-3">
        Environments
      </h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-12 max-w-[580px]">
        BreakingWeb uses fully interactive environment simulations with in-memory state.
        The adapter pattern allows new domains to be added without changing the agent or
        evaluation infrastructure.
      </p>

      {/* Adapter Architecture */}
      <section className="mb-12">
        <h2 id="adapter-architecture" className="text-lg font-medium tracking-tight mb-4">
          Adapter Architecture
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Each environment exposes the same interface through an adapter. Two adapter modes exist:
        </p>
        <div className="flex flex-col gap-3 mb-6">
          <div className="border border-[var(--border)] rounded-xl p-5">
            <div className="flex items-center gap-3 mb-2">
              <span className="font-mono text-[13px] text-[var(--accent)]">StaticAdapter</span>
              <span className="text-[11px] px-2 py-0.5 rounded-md bg-[var(--surface)] text-[var(--text-tertiary)]">
                demo site
              </span>
            </div>
            <p className="text-[13px] text-[var(--text-secondary)] leading-[1.6]">
              In-memory state mutation using a route mutator function. No server needed —
              all state transitions happen client-side. Used by the demo site to simulate
              Gmail without a backend.
            </p>
          </div>
          <div className="border border-[var(--border)] rounded-xl p-5">
            <div className="flex items-center gap-3 mb-2">
              <span className="font-mono text-[13px] text-[var(--accent)]">LiveAdapter</span>
              <span className="text-[11px] px-2 py-0.5 rounded-md bg-[var(--surface)] text-[var(--text-tertiary)]">
                evaluation
              </span>
            </div>
            <p className="text-[13px] text-[var(--text-secondary)] leading-[1.6]">
              Makes real HTTP requests to the FastAPI backend. Automatically injects{" "}
              <code className="font-mono text-[12px] text-[var(--text-primary)]">session_id</code>{" "}
              into request bodies. Used during live evaluation with Playwright.
            </p>
          </div>
        </div>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          This pattern means the same React frontend code runs in both the demo site (static)
          and evaluation (live) without any forking. Adding a new environment means implementing
          a state model, a route mutator, and a React frontend.
        </p>
      </section>

      {/* Gmail */}
      <section className="mb-12">
        <h2 id="gmail" className="text-lg font-medium tracking-tight mb-4">
          Gmail Environment
        </h2>
        <div className="flex items-center gap-3 mb-5">
          <span className="text-[12px] font-medium px-2 py-0.5 rounded-md"
            style={{ color: "var(--green)", backgroundColor: "color-mix(in oklch, var(--green) 15%, transparent)" }}>
            Live
          </span>
          <span className="font-mono text-[12px] text-[var(--text-tertiary)]">80 tasks · 153 variants</span>
        </div>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          A fully interactive React simulation of Gmail supporting compose, reply, forward,
          labelling, archiving, starring, search, and contact management. The simulation
          maintains live in-memory state so every agent action has observable consequences.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Tasks range from simple single-step operations (star an email, create a label) to
          complex multi-step workflows (budget reconciliation, compliance audit) spanning
          all seven cognitive primitives.
        </p>

        <h3 className="text-[14px] font-medium text-[var(--text-primary)] mb-3">
          Key capabilities
        </h3>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px] mb-5">
          <table className="w-full">
            <tbody>
              {[
                ["Compose / Reply / Forward", "Full email composition with To, CC, BCC, subject, and rich body"],
                ["Labels", "Create, apply, and remove custom labels; filter by label"],
                ["Archive / Star", "Thread-level archive and star operations with sidebar updates"],
                ["Search", "Full-text search across sender, subject, and body content"],
                ["Navigation", "Inbox, Starred, Sent, Drafts, Trash, and custom label views"],
                ["Contacts", "Contact list management with email address resolution"],
              ].map(([feature, desc], i, arr) => (
                <tr key={feature} className={i < arr.length - 1 ? "border-b border-[var(--border)]" : ""}>
                  <td className="px-4 py-2.5 font-medium text-[var(--text-primary)] w-[200px]">{feature}</td>
                  <td className="px-4 py-2.5 text-[var(--text-secondary)]">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Robinhood */}
      <section className="mb-12">
        <h2 id="robinhood" className="text-lg font-medium tracking-tight mb-4">
          Robinhood Environment
        </h2>
        <div className="flex items-center gap-3 mb-5">
          <span className="text-[12px] font-medium px-2 py-0.5 rounded-md"
            style={{ color: "var(--amber)", backgroundColor: "color-mix(in oklch, var(--amber) 15%, transparent)" }}>
            Beta
          </span>
          <span className="font-mono text-[12px] text-[var(--text-tertiary)]">50 tasks · 5 difficulty tiers</span>
        </div>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          A brokerage environment modelling Robinhood&apos;s core workflows. The data model
          includes 26 Pydantic models covering positions, orders, stocks, options, watchlists,
          transfers, recurring investments, tax documents, price alerts, notifications, and
          account settings.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          The Robinhood environment expands the benchmark from communication workflows (Gmail)
          into financial application workflows, testing whether agents can handle domain-specific
          operations like placing orders, managing positions, and interpreting portfolio data.
        </p>

        <h3 className="text-[14px] font-medium text-[var(--text-primary)] mb-3">
          State model capabilities
        </h3>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <tbody>
              {[
                ["Positions & Orders", "Query positions, place market/limit orders, cancel pending orders"],
                ["Stocks & Options", "Search stocks, view quotes, browse option chains"],
                ["Watchlists", "Create, modify, and delete watchlists with stock symbols"],
                ["Transfers", "Initiate deposits and withdrawals between linked accounts"],
                ["Recurring Investments", "Set up and manage dollar-cost averaging schedules"],
                ["Tax Documents", "Access 1099 forms and tax summaries by year"],
              ].map(([feature, desc], i, arr) => (
                <tr key={feature} className={i < arr.length - 1 ? "border-b border-[var(--border)]" : ""}>
                  <td className="px-4 py-2.5 font-medium text-[var(--text-primary)] w-[200px]">{feature}</td>
                  <td className="px-4 py-2.5 text-[var(--text-secondary)]">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Adding a New Environment */}
      <section className="mb-12">
        <h2 id="adding-environments" className="text-lg font-medium tracking-tight mb-4">
          Adding a New Environment
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          The adapter pattern makes adding new environments systematic. Each environment needs
          three components:
        </p>
        <ol className="list-decimal list-inside space-y-3 text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          <li>
            <span className="font-medium text-[var(--text-primary)]">State model</span> —
            a Pydantic model defining the environment&apos;s data structures, query methods,
            and mutation methods. This is the source of truth for what the environment can do.
          </li>
          <li>
            <span className="font-medium text-[var(--text-primary)]">Route mutator</span> —
            a function that maps API requests (method, path, body) to state transitions. This
            bridges the REST-like adapter interface to the state model.
          </li>
          <li>
            <span className="font-medium text-[var(--text-primary)]">React frontend</span> —
            the UI layer consumed by both the demo site (via StaticAdapter) and live evaluation
            (via LiveAdapter). Uses the shared{" "}
            <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">useAdapterContext()</code>{" "}
            hook for data fetching.
          </li>
        </ol>
        <CodeBlock code={`# Environment structure
breakingweb/environments/
├── shared/          # Adapter system, hooks, shared components
│   └── src/adapters/
│       ├── types.ts      # EnvAdapter, RouteMutator interfaces
│       ├── static.ts     # In-memory state adapter
│       └── live.ts       # HTTP request adapter
├── gmail/           # Gmail environment
│   ├── src/         # React frontend
│   └── state.py     # Pydantic state model
└── robinhood/       # Robinhood environment
    └── state.py     # Pydantic state model (26 models)`} language="text" />
      </section>
    </>
  );
}
