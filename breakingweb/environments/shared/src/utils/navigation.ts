// Defense-in-depth: keep every flag the harness sets at session boot. Dropping
// even one of these on internal SPA navigation has caused real bugs:
//   - control=on    : env tab's BenchmarkToolbar gates its recorder + heartbeat
//                     on this; losing it on nav silently kills event capture
//                     (patient_portal had a custom preserveSession that only
//                     kept "session" — recorder died on every NavLink click).
//   - human_mode=1  : marks human-recording sessions; toolbar checks this
//                     alongside hide_toolbar to short-circuit.
//   - hide_toolbar=1: explicit "do not render the toolbar in env tab" flag set
//                     by human launcher / control panel. SessionStorage sticky
//                     in BenchmarkToolbar covers this if it's lost, but we
//                     preserve it on URL too so a fresh tab from a kept link
//                     starts in the right state.
//   - agent_mode=1  : agent-flow legacy flag.
const DEFAULT_PRESERVED_KEYS = [
  "session",
  "agent_mode",
  "control",
  "hide_toolbar",
  "human_mode",
];

export function preserveQueryParams(
  to: string,
  currentSearch: string,
  keys: string[] = DEFAULT_PRESERVED_KEYS,
): string {
  const hashIndex = to.indexOf("#");
  const withoutHash = hashIndex >= 0 ? to.slice(0, hashIndex) : to;
  const hash = hashIndex >= 0 ? to.slice(hashIndex) : "";
  const qIndex = withoutHash.indexOf("?");
  const pathname = qIndex >= 0 ? withoutHash.slice(0, qIndex) : withoutHash;
  const targetParams = new URLSearchParams(qIndex >= 0 ? withoutHash.slice(qIndex + 1) : "");
  const currentParams = new URLSearchParams(currentSearch);

  for (const key of keys) {
    const currentValue = currentParams.get(key);
    if (currentValue !== null && !targetParams.has(key)) {
      targetParams.set(key, currentValue);
    }
  }

  const query = targetParams.toString();
  return `${pathname}${query ? `?${query}` : ""}${hash}`;
}
