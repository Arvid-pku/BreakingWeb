import React, { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { preserveQueryParams } from "@breakingweb/shared";

import { usePatientPortal } from "../context";
import type { LabResult } from "../types";

// Use shared preserveQueryParams — see Shell.tsx for the bug-history note.
const preserveSession = preserveQueryParams;

export function LabsPage() {
  const location = useLocation();
  const { api, providers } = usePatientPortal();
  const [labs, setLabs] = useState<LabResult[]>([]);
  const [sortBy, setSortBy] = useState<"date" | "name" | "flag">("date");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [trendData, setTrendData] = useState<LabResult[]>([]);
  const [trendName, setTrendName] = useState("");

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;

  const loadLabs = useCallback(async () => {
    try {
      const items = await api.listLabs();
      setLabs(items);
    } catch {
      // silently continue
    }
  }, [api]);

  useEffect(() => { void loadLabs(); }, [loadLabs]);

  const sortedLabs = [...labs].sort((a, b) => {
    if (sortBy === "date") return new Date(b.collected_at).getTime() - new Date(a.collected_at).getTime();
    if (sortBy === "name") return a.test_name.localeCompare(b.test_name);
    // flag: critical > abnormal > normal
    const flagOrder: Record<string, number> = { critical: 0, abnormal: 1, normal: 2 };
    return (flagOrder[a.flag] ?? 3) - (flagOrder[b.flag] ?? 3);
  });

  const resulted = sortedLabs.filter((l) => l.status === "resulted" || l.status === "reviewed");
  const pending = sortedLabs.filter((l) => l.status !== "resulted" && l.status !== "reviewed");

  const toggleExpand = async (lab: LabResult) => {
    if (expandedId === lab.id) {
      setExpandedId(null);
      setTrendData([]);
      setTrendName("");
      return;
    }
    setExpandedId(lab.id);
    try {
      const result = await api.getLabTrend(lab.test_name);
      setTrendData(result.items);
      setTrendName(result.test_name);
    } catch {
      setTrendData([]);
      setTrendName(lab.test_name);
    }
  };

  const flagLabel = (flag: string) => {
    if (flag === "critical") return "Critical";
    if (flag === "abnormal") return "Abnormal";
    return "Normal";
  };

  // Simple sparkline as inline SVG
  const renderSparkline = (data: LabResult[]) => {
    if (data.length < 2) return null;
    const values = data.map((d) => parseFloat(d.value)).filter((v) => !isNaN(v));
    if (values.length < 2) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const w = 120;
    const h = 30;
    const points = values
      .map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / range) * h}`)
      .join(" ");
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label={`Trend sparkline for ${trendName}`}>
        <polyline fill="none" stroke="#1976d2" strokeWidth="2" points={points} />
      </svg>
    );
  };

  return (
    <div aria-label="Lab Results Page">
      <h2>Lab Results</h2>

      <section aria-label="Completed Lab Results" className="pp-section">
        <h3>Results</h3>
        <div className="pp-sort-controls">
          <label htmlFor="lab-sort">Sort by:</label>
          <select
            id="lab-sort"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "date" | "name" | "flag")}
            aria-label="Sort lab results"
          >
            <option value="date">Date</option>
            <option value="name">Test Name</option>
            <option value="flag">Flag</option>
          </select>
        </div>

        {resulted.length === 0 ? (
          <p>No lab results available.</p>
        ) : (
          <table aria-label="Lab Results">
            <thead>
              <tr>
                <th>Lab ID</th>
                <th>Test Name</th>
                <th>Date</th>
                <th>Value</th>
                <th>Unit</th>
                <th>Reference Range</th>
                <th>Flag</th>
                <th>Status</th>
                <th>Ordered By</th>
              </tr>
            </thead>
            <tbody>
              {resulted.map((lab) => (
                <React.Fragment key={lab.id}>
                  <tr
                    className={expandedId === lab.id ? "pp-row--expanded" : "pp-row--clickable"}
                    onClick={() => toggleExpand(lab)}
                    role="button"
                    aria-label={`View details for ${lab.test_name}`}
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter") toggleExpand(lab); }}
                  >
                    <td>{lab.id}</td>
                    <td>{lab.test_name}</td>
                    <td>{new Date(lab.collected_at).toLocaleDateString()}</td>
                    <td>{lab.value}</td>
                    <td>{lab.unit}</td>
                    <td>{lab.reference_range}</td>
                    <td>
                      <span className={`pp-flag-badge pp-flag-badge--${lab.flag}`} aria-label={`Flag: ${flagLabel(lab.flag)}`}>
                        {flagLabel(lab.flag)}
                      </span>
                    </td>
                    <td>{lab.status}</td>
                    <td>{providerName(lab.ordered_by)}</td>
                  </tr>
                  {expandedId === lab.id && (
                    <tr key={`${lab.id}-detail`} className="pp-detail-row">
                      <td colSpan={9}>
                        <div className="pp-lab-detail" aria-label={`Details for ${lab.test_name}`}>
                          <div className="pp-lab-detail__id">
                            <strong>Lab ID:</strong> {lab.id}
                          </div>
                          <div className="pp-lab-detail__range">
                            <strong>Reference Range:</strong> {lab.reference_range}
                          </div>
                          <div className="pp-lab-detail__value">
                            <strong>Your Value:</strong> {lab.value} {lab.unit}
                          </div>
                          <div className="pp-lab-detail__appointment">
                            <strong>Linked Appointment:</strong> {lab.linked_appointment_id ?? "None documented"}
                          </div>
                          {trendData.length > 1 && (
                            <div className="pp-lab-detail__trend">
                              <strong>Trend:</strong>
                              {renderSparkline(trendData)}
                            </div>
                          )}
                          <a
                            href={preserveSession("/messages", location.search)}
                            className="pp-btn pp-btn--secondary pp-btn--sm"
                            aria-label={`Message provider about ${lab.test_name}`}
                          >
                            Message Provider
                          </a>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {pending.length > 0 && (
        <section aria-label="Pending Labs" className="pp-section">
          <h3>Pending Labs</h3>
          <table aria-label="Pending lab orders">
            <thead>
              <tr>
                <th>Lab ID</th>
                <th>Test Name</th>
                <th>Status</th>
                <th>Ordered By</th>
                <th>Linked Appointment</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((lab) => (
                <tr key={lab.id}>
                  <td>{lab.id}</td>
                  <td>{lab.test_name}</td>
                  <td><span className={`pp-status-badge pp-status-badge--${lab.status}`}>{lab.status}</span></td>
                  <td>{providerName(lab.ordered_by)}</td>
                  <td>{lab.linked_appointment_id ?? "None documented"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
