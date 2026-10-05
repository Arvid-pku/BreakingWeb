import { useEffect, useState } from "react";

import { useRobinhoodLayout } from "../context";
import type { DividendEntry } from "../types";

export function DividendsPage() {
  const { api } = useRobinhoodLayout();
  const [dividends, setDividends] = useState<DividendEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api.listDividends()
      .then((items) => { if (!cancelled) setDividends(items); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api]);

  if (loading) return <div className="rh-loading">Loading...</div>;

  const upcoming = dividends.filter((d) => d.status === "upcoming");
  const paid = dividends.filter((d) => d.status === "paid");

  return (
    <div className="rh-dividends" aria-label="Dividends">
      <h1>Dividends</h1>

      <section aria-label="Upcoming dividends">
        <h2>Upcoming</h2>
        {upcoming.length === 0 ? (
          <div className="rh-empty">No upcoming dividends</div>
        ) : (
          <table className="rh-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Ex-Date</th>
                <th>Pay Date</th>
                <th>Per Share</th>
                <th>Est. Total</th>
              </tr>
            </thead>
            <tbody>
              {upcoming.map((d, i) => (
                <tr key={i}>
                  <td>{d.symbol}</td>
                  <td>{d.ex_date}</td>
                  <td>{d.pay_date}</td>
                  <td>${parseFloat(d.amount_per_share).toFixed(4)}</td>
                  <td className="rh-gain">${parseFloat(d.estimated_total).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-label="Past dividends">
        <h2>Paid</h2>
        {paid.length === 0 ? (
          <div className="rh-empty">No paid dividends</div>
        ) : (
          <table className="rh-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Ex-Date</th>
                <th>Pay Date</th>
                <th>Per Share</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {paid.map((d, i) => (
                <tr key={i}>
                  <td>{d.symbol}</td>
                  <td>{d.ex_date}</td>
                  <td>{d.pay_date}</td>
                  <td>${parseFloat(d.amount_per_share).toFixed(4)}</td>
                  <td className="rh-gain">${parseFloat(d.estimated_total).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
