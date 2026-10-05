import { CodeBlock } from "@/components/docs/CodeBlock";

export default function StressTestingPage() {
  return (
    <>
      <p className="text-[12px] font-medium text-[var(--text-tertiary)] mb-8">
        Documentation / Stress Testing
      </p>

      <h1 className="text-2xl font-medium tracking-tight mb-3">
        Stress Testing
      </h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-12 max-w-[580px]">
        153 degradation variants inject controlled failures at four independent layers of the
        web stack, isolating which cognitive primitive breaks under each type of pressure.
      </p>

      {/* Overview */}
      <section className="mb-12">
        <h2 id="overview" className="text-lg font-medium tracking-tight mb-4">
          Overview
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Normal benchmark evaluation tells you <em>whether</em> an agent fails. Stress testing tells
          you <em>why</em>. Each variant targets a specific cognitive primitive by degrading one layer
          of the stack while leaving the others intact. If an agent passes the base task but fails
          the stress variant, the failure is attributable to the targeted primitive.
        </p>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7]">
          Variants are defined as YAML configs in{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">
            breakingweb/injector/variants/
          </code>. Each specifies a{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">base_task_id</code>,{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">target_primitive</code>, and a list of{" "}
          <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">injections</code> with layer and parameters.
        </p>
      </section>

      {/* Four Layers */}
      <section className="mb-12">
        <h2 id="injection-layers" className="text-lg font-medium tracking-tight mb-4">
          Four Injection Layers
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          Degradations are injected at four independent layers. Each layer targets different
          aspects of the agent&apos;s capability:
        </p>

        <div className="flex flex-col gap-4">
          {/* Seed */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="w-2 h-2 rounded-full bg-[var(--green)]" />
              <span className="font-mono text-[14px] font-medium text-[var(--text-primary)]">Seed Layer</span>
              <span className="text-[12px] text-[var(--text-tertiary)] ml-auto">Data content</span>
            </div>
            <div className="px-5 py-4">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                Mutates the data content that populates the environment — emails, contacts,
                timestamps, thread relationships. Tests <strong className="text-[var(--text-primary)]">state_tracking</strong> and{" "}
                <strong className="text-[var(--text-primary)]">grounding</strong>.
              </p>
              <div className="text-[13px] text-[var(--text-tertiary)] leading-[1.6]">
                Examples: scramble email timestamps, redistribute information across threads,
                duplicate sender names with different content, inject conflicting dates.
              </div>
            </div>
          </div>

          {/* Server */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
              <span className="font-mono text-[14px] font-medium text-[var(--text-primary)]">Server Layer</span>
              <span className="text-[12px] text-[var(--text-tertiary)] ml-auto">State structure</span>
            </div>
            <div className="px-5 py-4">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                Alters the structural state of the environment — hidden prerequisites, shuffled
                entity relationships, modified server responses. Tests{" "}
                <strong className="text-[var(--text-primary)]">planning</strong> and{" "}
                <strong className="text-[var(--text-primary)]">exploration</strong>.
              </p>
              <div className="text-[13px] text-[var(--text-tertiary)] leading-[1.6]">
                Examples: add hidden filter rules, require prerequisite actions before main task,
                shuffle category assignments, change pagination boundaries.
              </div>
            </div>
          </div>

          {/* Client */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="w-2 h-2 rounded-full bg-[var(--amber)]" />
              <span className="font-mono text-[14px] font-medium text-[var(--text-primary)]">Client Layer</span>
              <span className="text-[12px] text-[var(--text-tertiary)] ml-auto">DOM / JS mutations</span>
            </div>
            <div className="px-5 py-4">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                Injects DOM and JavaScript mutations that alter what the agent perceives.
                Tests <strong className="text-[var(--text-primary)]">grounding</strong> and{" "}
                <strong className="text-[var(--text-primary)]">verification</strong>.
              </p>
              <div className="text-[13px] text-[var(--text-tertiary)] leading-[1.6]">
                Examples: swap button labels, add decoy interactive elements, hide real
                affordances behind CSS, inject misleading aria attributes.
              </div>
            </div>
          </div>

          {/* Network */}
          <div className="border border-[var(--border)] rounded-xl overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-3 bg-[var(--surface-raised)] border-b border-[var(--border)]">
              <span className="w-2 h-2 rounded-full bg-[var(--red)]" />
              <span className="font-mono text-[14px] font-medium text-[var(--text-primary)]">Network Layer</span>
              <span className="text-[12px] text-[var(--text-tertiary)] ml-auto">HTTP transport</span>
            </div>
            <div className="px-5 py-4">
              <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-3">
                Degrades the HTTP transport between client and server.
                Tests <strong className="text-[var(--text-primary)]">patience</strong> and{" "}
                <strong className="text-[var(--text-primary)]">backtracking</strong>.
              </p>
              <div className="text-[13px] text-[var(--text-tertiary)] leading-[1.6]">
                Examples: add response delays, inject stale cached data, simulate transient
                server errors, return partial responses, silent request failures.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Degradation Modes */}
      <section className="mb-12">
        <h2 id="degradation-modes" className="text-lg font-medium tracking-tight mb-4">
          Degradation Modes
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-6">
          Injections operate in three temporal modes, controlling how the degradation
          manifests over the course of an episode:
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--surface-raised)] border-b border-[var(--border)]">
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Mode</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Behaviour</th>
                <th className="text-left px-4 py-2.5 font-medium text-[var(--text-secondary)]">Tests</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono font-medium text-[var(--text-primary)]">progressive</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Degradation starts mild and escalates over time. The agent must detect the worsening conditions.</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">state_tracking, verification</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-mono font-medium text-[var(--text-primary)]">intermittent</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Degradation occurs probabilistically. The agent must handle unreliable conditions without overreacting.</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">patience, backtracking</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-mono font-medium text-[var(--text-primary)]">persistent</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">Degradation is constant throughout the episode. SPA-aware — persists across client-side navigation.</td>
                <td className="px-4 py-2.5 text-[var(--text-secondary)]">grounding, exploration</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Variant Configuration */}
      <section className="mb-12">
        <h2 id="variant-config" className="text-lg font-medium tracking-tight mb-4">
          Variant Configuration
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Each variant is a YAML file specifying which base task to degrade, which primitive
          to target, and the injection parameters:
        </p>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)] font-mono text-[13px] text-[var(--text-secondary)]">
            <span className="w-[7px] h-[7px] rounded-full bg-[var(--amber)]" />
            gmail_compliance_settings__patience.yaml
          </div>
          <div className="p-5 bg-[var(--surface-raised)] font-mono text-[13px] text-[var(--text-secondary)] leading-[1.8]">
            <span className="text-[var(--accent)]">base_task_id</span>: gmail_compliance_settings<br />
            <span className="text-[var(--accent)]">target_primitive</span>: patience<br />
            <span className="text-[var(--accent)]">injections</span>:<br />
            {"  "}- <span className="text-[var(--accent)]">layer</span>: network<br />
            {"    "}<span className="text-[var(--accent)]">type</span>: delay<br />
            {"    "}<span className="text-[var(--accent)]">params</span>:<br />
            {"      "}<span className="text-[var(--accent)]">min_ms</span>: 2000<br />
            {"      "}<span className="text-[var(--accent)]">max_ms</span>: 5000<br />
            {"      "}<span className="text-[var(--accent)]">mode</span>: progressive
          </div>
        </div>
      </section>

      {/* Running Stress Tests */}
      <section className="mb-12">
        <h2 id="running" className="text-lg font-medium tracking-tight mb-4">
          Running Stress Tests
        </h2>
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-5">
          Pass the <code className="font-mono text-[13px] text-[var(--text-primary)] bg-[var(--surface)] px-1.5 py-0.5 rounded">--degradation</code> flag
          to apply a stress variant during evaluation:
        </p>
        <CodeBlock code={`python -m breakingweb.agent_eval \\
    --model gpt-4o --provider openai \\
    --degradation gmail_compliance_settings__patience.yaml`} language="bash" />
        <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mt-5">
          The evaluator automatically applies the injection configuration, runs the agent
          against the degraded environment, and reports the primitive-specific failure mode
          alongside the standard score.
        </p>
      </section>

      {/* Statistics */}
      <section className="mb-12">
        <h2 id="statistics" className="text-lg font-medium tracking-tight mb-4">
          Suite Statistics
        </h2>
        <div className="border border-[var(--border)] rounded-xl overflow-hidden text-[13px]">
          <table className="w-full">
            <tbody>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Base tasks</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">80</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Stress variants</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">153</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Positive checks</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">566</td>
              </tr>
              <tr className="border-b border-[var(--border)]">
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Negative checks</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">235</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-[var(--text-primary)]">Cognitive primitives covered</td>
                <td className="px-4 py-2.5 font-mono text-[var(--text-secondary)]">7 / 7</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
