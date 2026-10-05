import { CodeBlock } from "@/components/docs/CodeBlock";

export default function BenchmarkDocsPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Benchmark
      </p>

      <h1 className="text-2xl font-medium tracking-tight mb-3">
        Benchmark
      </h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-12 max-w-[580px]">
        Task structure, seeded environments, difficulty tiers, version history, and how to run
        the current BreakingWeb stack.
      </p>

      {/* Task Structure */}
      <section className="mb-12">
        <h2 id="task-structure" className="text-lg font-medium tracking-tight mb-4">
          Task Structure
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Each task is defined as a YAML document with four top-level sections. Together they
          specify what the agent must do, what the environment looks like, and how success is
          measured.
        </p>

        <div className="flex flex-col gap-4">
          {/* metadata */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">metadata</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
                Identifies the task: <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">id</code>,{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">page</code>,{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">difficulty</code>, and the list of{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">primitives</code> the task exercises. The
                primitives list links each task to the cognitive taxonomy and is used by the results
                dashboard to break down performance by skill area.
              </p>
            </div>
          </div>

          {/* instruction */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">instruction</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                A natural-language template shown to the agent. Placeholders of the form{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">{"{{target.field}}"}</code> are
                resolved against the seed&apos;s target object at runtime. This keeps the instruction
                human-readable in the YAML while remaining parametric across fixture variations.
              </p>
              <CodeBlock code={`Open billing settings and add the card ending in
{{target.last4}} with expiry {{target.expiry}}.`} language="yaml" />
            </div>
          </div>

          {/* seed */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">seed</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                Drives the fixture generator. Contains three sub-sections:
              </p>
              <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
                <table className="w-full">
                  <thead>
                    <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                      <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Key</th>
                      <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Purpose</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-[var(--border)]">
                      <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">actors</td>
                      <td className="px-4 py-2.5 text-[var(--text-secondary)]">Named entities with task roles: customers, sellers, senders, patients, moderators, and other environment-specific identities.</td>
                    </tr>
                    <tr className="border-b border-[var(--border)]">
                      <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">steps</td>
                      <td className="px-4 py-2.5 text-[var(--text-secondary)]">Ordered seeder operations that build the initial environment state: create messages, bookings, payment methods, products, posts, or portfolio records.</td>
                    </tr>
                    <tr>
                      <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">distractors</td>
                      <td className="px-4 py-2.5 text-[var(--text-secondary)]">Additional records or UI elements injected to test attention and filtering. Controlled by count, similarity, and placement parameters.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* eval */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="font-mono text-[13px] text-[var(--text-primary)]">eval</span>
            </div>
            <div className="px-4 py-3">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
                Defines the scoring criteria as two lists. <strong className="font-medium text-[var(--text-primary)]">Positive checks</strong> are
                assertions that must be true for the agent to receive credit — each contributes{" "}
                <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">1 / total</code> to the base score.{" "}
                <strong className="font-medium text-[var(--text-primary)]">Negative checks</strong> are
                guard-rail assertions — behaviours the agent must avoid — each carrying an explicit
                penalty subtracted from the base score.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Seeded Environments */}
      <section className="mb-12">
        <h2 id="seeded-environments" className="text-lg font-medium tracking-tight mb-4">
          Seeded Environments
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Current benchmark environments include Amazon, Booking, Gmail, LMS, Patient Portal,
          Reddit, and Robinhood. Each environment exposes a live task surface backed by a seeded
          session API rather than a static mock page.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          The exact state model differs by environment, but the contract is consistent: a task
          materializes targets, a backend seeds canonical state, the frontend renders that state,
          and evaluation checks the resulting records and audit trail after the agent acts.
        </p>

        <h3 className="text-[14px] font-medium text-[var(--text-primary)] mb-3">
          Fixture Generation Pipeline
        </h3>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Stage</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">What happens</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">1. Actor and target generation</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Seed roles are resolved to concrete identities and targets. The same role maps consistently within a session so instructions and evals remain deterministic.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">2. Seeder steps</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Each step is executed against environment-specific state stores to create the starting world for the task.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">3. Distractor and variant injection</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Optional distractors and degradation variants are layered in to stress specific primitives without changing the core task objective.</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">4. Session handoff</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">The backend returns the start path, resolved instruction text, and metadata needed by the frontend, evaluator, and trajectory tools.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Difficulty Tiers */}
      <section className="mb-12">
        <h2 id="difficulty-tiers" className="text-lg font-medium tracking-tight mb-4">
          Difficulty Tiers
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Tasks are grouped into four difficulty tiers based on expected step count and the number
          of cognitive primitives exercised simultaneously. The tiers are calibrated against
          human baselines, not model performance.
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Tier</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Steps</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Primitives</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Description</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Easy</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">5 – 10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Single-primitive</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Isolated skill test. Straightforward instruction, minimal distractors, short action chain.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Medium</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">10 – 20</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">2 – 3 primitives</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Requires combining skills such as memory with attention, or patience with backtracking.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Hard</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">20 – 35</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Complex reasoning</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Multi-step plans, conditional logic, and adversarial distractors designed to mislead.</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Expert</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">30 – 50</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">All primitives</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Full-coverage gauntlet. Requires near-perfect planning, resistance to distraction, and recovery from dead ends.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Version History */}
      <section className="mb-12">
        <h2 id="version-history" className="text-lg font-medium tracking-tight mb-4">
          Version History
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          BreakingWeb has gone through ten versioned releases. Major milestones are listed below.
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Version</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Pages</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Summary</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v1</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Initial release. Core page set with basic task definitions and programmatic scoring.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v2 – v4</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Iterative scoring refinement: negative checks added in v2, trajectory modifier in v3, calibrated weights in v4.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v5</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">12</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Major redesign. Two new pages, unified YAML task format, and the actor/seed/distractor fixture pipeline.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v6 – v8</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">15</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Environment expansion and harder interaction patterns, including frontier tasks designed to expose weak planning and attention behavior.</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v9</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">15</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Hardening release. Tightened eval criteria, distractor density increased, seed stability test suite added.</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-mono text-[var(--text-primary)]">v10</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">15</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Unified runtime release. Indexed accessibility-tree observations, shared task metadata, and trajectory tooling were standardized across environments.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Running the Benchmark */}
      <section className="mb-12">
        <h2 id="running" className="text-lg font-medium tracking-tight mb-4">
          Running the Benchmark
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          BreakingWeb evaluations are driven by{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">breakingweb/agent_eval.py</code>. It
          spins up a local FastAPI server, initializes seeded sessions, then runs the agent against
          the live DOM via Playwright.
        </p>
        <CodeBlock code={`# Evaluate the full benchmark
python -m breakingweb.agent_eval --model gpt-4o --provider openai

# Restrict to specific environments
python -m breakingweb.agent_eval --model gpt-4o --provider openai \\
    --environments amazon booking reddit

# Run specific tasks only
python -m breakingweb.agent_eval --model gpt-4o --provider openai \\
    --tasks booking_add_payment gmail_thread_detective

# With visible browser (useful for debugging)
python -m breakingweb.agent_eval --model gpt-4o --provider openai --no-headless`} language="bash" />
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mt-5">
          Results are written to{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">results/breakingweb/results.json</code>{" "}
          and can be visualised with{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">python -m breakingweb.visualize results/breakingweb/results.json</code>.
        </p>
      </section>
    </>
  );
}
