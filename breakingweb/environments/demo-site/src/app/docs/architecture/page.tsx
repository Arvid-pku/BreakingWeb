export default function ArchitecturePage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Architecture
      </p>
      <h1 className="text-2xl font-medium tracking-tight mb-3">Architecture</h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-12">
        BreakingWeb is organized around a seeded-session runtime: YAML tasks define goals and
        checks, Python backends materialize environment state, and React frontends expose live UIs
        that agents operate through the browser.
      </p>

      <section className="mb-14">
        <h2 id="runtime-layers" className="text-lg font-medium tracking-tight mb-3">
          Runtime Layers
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          The benchmark is split into four layers so task authoring, state management, browser
          interaction, and scoring can evolve independently.
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
                <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
                  Layer
                </th>
                <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
                  Responsibility
                </th>
                <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
                  Examples
                </th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">Task registry</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  Defines instructions, seed targets, positive checks, and negative checks.
                </td>
                <td className="px-4 py-3 font-mono text-[var(--accent)]">
                  tasks/&lt;env&gt;/*.yaml
                </td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">Session backend</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  Materializes seeded state, serves session APIs, and records audit events.
                </td>
                <td className="px-4 py-3 font-mono text-[var(--accent)]">
                  backend/routes/, backend/seeders/
                </td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">Environment UI</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  Renders the live task surface and sends user actions to the backend.
                </td>
                <td className="px-4 py-3 font-mono text-[var(--accent)]">
                  environments/&lt;env&gt;/src/
                </td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">
                  Harness and scoring
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  Runs agents, captures trajectories, evaluates outcomes, and generates reports.
                </td>
                <td className="px-4 py-3 font-mono text-[var(--accent)]">
                  agent_eval.py, evaluator.py, visualize.py
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-14">
        <h2 id="observation-contract" className="text-lg font-medium tracking-tight mb-3">
          Observation Contract
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Agents act on indexed accessibility trees extracted from the live page. Each visible
          element receives a stable numeric reference within the current observation, and actions
          point back to those references.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
          Observations are rendered as indented trees with numeric reference indices:
        </p>
        <div className="border border-[var(--border)] rounded-xl bg-[var(--surface-raised)] p-5 font-mono text-[13px] mb-5 leading-[1.8]">
          <span className="text-[var(--text-tertiary)]">[1]</span>{" "}
          <span className="text-[var(--accent)]">button</span>{" "}
          <span className="text-[var(--text-primary)]">&quot;Settings&quot;</span>
          <br />
          <span className="text-[var(--text-tertiary)]">[2]</span>{" "}
          <span className="text-[var(--accent)]">textbox</span>{" "}
          <span className="text-[var(--text-primary)]">&quot;Search&quot;</span>
          <br />
          {"  "}
          <span className="text-[var(--text-tertiary)]">[3]</span>{" "}
          <span className="text-[var(--accent)]">option</span>{" "}
          <span className="text-[var(--text-primary)]">&quot;Option A&quot;</span>
        </div>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
          Actions are JSON-shaped commands that reference those elements by index:
        </p>
        <div className="border border-[var(--border)] rounded-xl bg-[var(--surface-raised)] p-5 font-mono text-[13px] leading-[1.8]">
          <div className="mb-1">
            <span className="text-[var(--text-tertiary)]">{"// click"}</span>
          </div>
          <div className="mb-3">
            {"{"}
            <span className="text-[var(--accent)]">&quot;action&quot;</span>
            {": "}
            <span className="text-[var(--text-primary)]">&quot;click&quot;</span>
            {", "}
            <span className="text-[var(--accent)]">&quot;ref&quot;</span>
            {": "}
            <span className="text-[var(--text-primary)]">1</span>
            {"}"}
          </div>
          <div className="mb-1">
            <span className="text-[var(--text-tertiary)]">{"// fill"}</span>
          </div>
          <div>
            {"{"}
            <span className="text-[var(--accent)]">&quot;action&quot;</span>
            {": "}
            <span className="text-[var(--text-primary)]">&quot;fill&quot;</span>
            {", "}
            <span className="text-[var(--accent)]">&quot;ref&quot;</span>
            {": "}
            <span className="text-[var(--text-primary)]">2</span>
            {", "}
            <span className="text-[var(--accent)]">&quot;value&quot;</span>
            {": "}
            <span className="text-[var(--text-primary)]">&quot;hello&quot;</span>
            {"}"}
          </div>
        </div>
      </section>

      <section className="mb-14">
        <h2 id="session-lifecycle" className="text-lg font-medium tracking-tight mb-3">
          Session Lifecycle
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          Each benchmark run follows the same seeded-session lifecycle, regardless of environment.
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          {[
            { label: "Materialize", desc: "Resolve seed targets" },
            { label: "Create session", desc: "Seed backend state" },
            { label: "Interact", desc: "Drive the live UI" },
            { label: "Evaluate", desc: "Score outcomes" },
          ].map((step, i, arr) => (
            <div key={step.label} className="flex items-center gap-2">
              <div className="border border-[var(--border)] rounded-xl bg-[var(--surface-raised)] px-4 py-3 text-center min-w-[124px]">
                <p className="text-[13px] font-medium text-[var(--text-primary)]">{step.label}</p>
                <p className="text-[11px] text-[var(--text-tertiary)] mt-0.5">{step.desc}</p>
              </div>
              {i < arr.length - 1 && (
                <span className="text-[var(--text-tertiary)] text-[18px] leading-none select-none">
                  →
                </span>
              )}
            </div>
          ))}
        </div>
        <p className="text-[13px] text-[var(--text-tertiary)] mt-4 leading-[1.6]">
          Reset reuses the same task contract to rebuild the session deterministically, while
          evaluate inspects the final server state, audit log, and any task-specific client-side
          evidence required by the YAML checks.
        </p>
      </section>

      <section className="mb-14">
        <h2 id="state-and-audits" className="text-lg font-medium tracking-tight mb-3">
          State And Audits
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          The benchmark grades outcomes against canonical backend state, not just what appears on
          screen. Backends also emit structured audit events so evals can detect harmful actions,
          ordering mistakes, and forbidden side effects.
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
                <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
                  Signal
                </th>
                <th className="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
                  Used for
                </th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">Server state</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  Source of truth for emails, bookings, carts, payment methods, portfolio state,
                  forum posts, and other environment-specific records.
                </td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">Audit log</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  Verifies that required actions occurred and negative checks can penalize specific
                  prohibited events.
                </td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">
                  Client benchmark state
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  Optional evidence for interaction-sensitive tasks, such as search terms,
                  navigation state, or transient UI choices not stored in the backend model.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-14">
        <h2 id="trajectories-and-viz" className="text-lg font-medium tracking-tight mb-3">
          Trajectories And Visualization
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          Evaluation runs emit step-by-step trajectories that include observations, parsed actions,
          targets, and terminal outcomes. These artifacts power the launcher replay screen and the
          standalone visualization workflow.
        </p>
        <div className="flex flex-col gap-3">
          <div className="border border-[var(--border)] rounded-xl p-5">
            <p className="font-mono text-[13px] text-[var(--accent)] mb-2">results/*.json</p>
            <p className="text-[13px] text-[var(--text-secondary)] leading-[1.6]">
              Stores run summaries, task-level scores, and captured trajectories for each episode.
            </p>
          </div>
          <div className="border border-[var(--border)] rounded-xl p-5">
            <p className="font-mono text-[13px] text-[var(--accent)] mb-2">visualize.py</p>
            <p className="text-[13px] text-[var(--text-secondary)] leading-[1.6]">
              Generates replayable HTML visualizations and embedded trajectory views for debugging.
            </p>
          </div>
          <div className="border border-[var(--border)] rounded-xl p-5">
            <p className="font-mono text-[13px] text-[var(--accent)] mb-2">/launch</p>
            <p className="text-[13px] text-[var(--text-secondary)] leading-[1.6]">
              Surfaces the current benchmark, evaluation controls, saved trajectories, and
              interactive replay from the same backend session contract.
            </p>
          </div>
        </div>
      </section>

      <section className="mb-14">
        <h2 id="model-providers" className="text-lg font-medium tracking-tight mb-3">
          Model Providers
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          The evaluation harness supports multiple model backends behind the same task runtime.
        </p>
        <div className="flex flex-col gap-3">
          {[
            {
              name: "openai",
              flag: "--provider openai",
              desc: "OpenAI models through the standard API.",
            },
            {
              name: "gemini",
              flag: "--provider gemini",
              desc: "Google Gemini models through the Gemini API.",
            },
            {
              name: "bedrock",
              flag: "--provider bedrock",
              desc: "AWS Bedrock-hosted models for managed evaluation runs.",
            },
            {
              name: "vllm",
              flag: "--provider vllm",
              desc: "OpenAI-compatible self-hosted endpoints, including local or cluster-backed serving.",
            },
          ].map((provider) => (
            <div key={provider.name} className="border border-[var(--border)] rounded-xl p-5">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-[13px] text-[var(--accent)]">
                  {provider.name}
                </span>
                <span className="font-mono text-[11px] text-[var(--text-tertiary)] bg-[var(--surface)] px-2 py-0.5 rounded-md">
                  {provider.flag}
                </span>
              </div>
              <p className="text-[13px] text-[var(--text-secondary)] leading-[1.6]">
                {provider.desc}
              </p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
