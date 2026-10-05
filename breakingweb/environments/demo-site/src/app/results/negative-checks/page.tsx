"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchNegativeChecks, type NegativeChecksData, type NegativeCheckEntry } from "@/lib/negativeChecks";

type Filter = "all" | "triggered" | "clear";

export default function NegativeChecksPage() {
  const [data, setData] = useState<NegativeChecksData | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchNegativeChecks().then((d) => {
      setData(d);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <p className="text-sm text-[var(--text-tertiary)]">Loading...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-[720px] mx-auto px-12 pt-[120px]">
        <p className="text-[var(--text-secondary)]">No negative checks data available.</p>
      </div>
    );
  }

  const filtered = data.checks.filter((c) => {
    if (filter === "triggered" && !c.triggered) return false;
    if (filter === "clear" && c.triggered) return false;
    if (search && !c.desc.toLowerCase().includes(search.toLowerCase()) && !c.task_title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    if (a.triggered !== b.triggered) return a.triggered ? -1 : 1;
    return b.penalty - a.penalty;
  });

  const triggerRate = data.total_negative_checks > 0
    ? ((data.triggered_count / data.total_negative_checks) * 100).toFixed(0)
    : "0";

  const filters: { key: Filter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "triggered", label: "Triggered" },
    { key: "clear", label: "Clear" },
  ];

  return (
    <div className="max-w-[720px] mx-auto px-12 pt-[120px] pb-24">
      <div className="flex items-center gap-2 mb-8">
        <Link href="/results" className="text-[12px] font-medium text-[var(--text-tertiary)] no-underline hover:text-[var(--text-secondary)] transition-colors">
          Results
        </Link>
        <span className="text-[12px] text-[var(--text-tertiary)]">/</span>
        <span className="text-[12px] font-medium text-[var(--text-tertiary)]">Negative Checks</span>
      </div>

      <h1 className="text-2xl font-medium tracking-tight mb-3">Negative Checks</h1>
      <p className="text-[14px] text-[var(--text-secondary)] leading-[1.7] mb-10 max-w-[540px]">
        Guard-rail checks that penalize undesirable agent behaviors — replying to the wrong person,
        leaking sensitive data, or mentioning incorrect values.
      </p>

      <div className="flex gap-12 mb-10">
        <div>
          <p className="font-mono text-[28px] font-medium tracking-tight text-[var(--text-primary)]">
            {data.total_negative_checks}
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">total checks</p>
        </div>
        <div>
          <p className="font-mono text-[28px] font-medium tracking-tight text-[var(--red)]">
            {data.triggered_count}
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">triggered</p>
        </div>
        <div>
          <p className="font-mono text-[28px] font-medium tracking-tight text-[var(--text-primary)]">
            {triggerRate}%
          </p>
          <p className="text-xs text-[var(--text-tertiary)]">trigger rate</p>
        </div>
      </div>

      <hr className="border-[var(--border)] mb-6" />

      <div className="flex items-center gap-4 mb-6">
        <div className="flex bg-[var(--surface-raised)] rounded-xl p-1 gap-0.5">
          {filters.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-4 py-[5px] rounded-[10px] text-[13px] transition-colors duration-150 ${
                filter === f.key
                  ? "bg-[var(--surface)] text-[var(--text-primary)] font-medium"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search checks..."
          className="flex-1 bg-[var(--bg)] border border-[var(--border)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] px-3 py-[7px] rounded-[10px] text-[13px] focus:outline-none focus:border-[var(--text-tertiary)] transition-colors"
        />
      </div>

      <table className="w-full text-[14px] border-collapse">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] py-2">Status</th>
            <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] py-2">Task</th>
            <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] py-2">Description</th>
            <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] py-2">Penalty</th>
            <th className="text-left text-[12px] font-medium text-[var(--text-tertiary)] py-2">Diff</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c, i) => (
            <tr
              key={`${c.task_id}-${i}`}
              className={`border-b border-[var(--border)] transition-colors ${
                c.triggered ? "bg-[oklch(72%_0.15_25_/_0.04)]" : ""
              }`}
            >
              <td className="py-3 pr-3">
                <span className={`font-mono text-xs ${c.triggered ? "text-[var(--red)]" : "text-[var(--green)]"}`}>
                  {c.triggered ? "✗" : "✓"}
                </span>
              </td>
              <td className="py-3 pr-3">
                <Link
                  href={`/results/${c.task_id}`}
                  className="text-[var(--text-primary)] no-underline hover:text-[var(--accent)] transition-colors text-[13px]"
                >
                  {c.task_title}
                </Link>
              </td>
              <td className="py-3 pr-3 text-[13px] text-[var(--text-secondary)]">
                {c.desc}
              </td>
              <td className="py-3 pr-3">
                <span className="font-mono text-[12px] text-[var(--red)]">
                  -{c.penalty}
                </span>
              </td>
              <td className="py-3 text-[13px] text-[var(--text-secondary)]">
                {c.difficulty}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {sorted.length === 0 && (
        <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
          No checks match the current filter.
        </p>
      )}
    </div>
  );
}
