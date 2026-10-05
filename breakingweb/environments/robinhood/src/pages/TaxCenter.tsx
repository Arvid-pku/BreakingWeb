import { useEffect, useState } from "react";

import { useRobinhoodLayout } from "../context";
import type { RealizedGainLoss, TaxDocument } from "../types";

export function TaxCenterPage() {
  const { api } = useRobinhoodLayout();
  const [documents, setDocuments] = useState<TaxDocument[]>([]);
  const [gains, setGains] = useState<RealizedGainLoss[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const query = selectedYear ? { year: selectedYear } : undefined;
    Promise.all([api.listTaxDocuments(query), api.listRealizedGains(query)])
      .then(([docs, g]) => {
        if (!cancelled) {
          setDocuments(docs);
          setGains(g);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, selectedYear]);

  if (loading) return <div className="rh-loading">Loading...</div>;

  const years = [...new Set(documents.map((d) => String(d.tax_year)))].sort().reverse();
  const totalGain = gains.reduce((sum, g) => sum + parseFloat(g.gain_loss), 0);

  return (
    <div className="rh-tax-center" aria-label="Tax center">
      <h1>Tax Center</h1>

      <div className="rh-transactions__filters">
        <select
          value={selectedYear}
          onChange={(e) => { setSelectedYear(e.target.value); setLoading(true); }}
          aria-label="Filter by tax year"
        >
          <option value="">All Years</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>

      <section aria-label="Tax documents">
        <h2>Documents</h2>
        {documents.length === 0 ? (
          <div className="rh-empty">No tax documents available</div>
        ) : (
          <div className="rh-tax-center__docs">
            {documents.map((doc) => (
              <div key={doc.id} className="rh-tax-center__doc-row" aria-label={`${doc.type} ${doc.tax_year}`}>
                <span className="rh-tax-center__doc-type">{doc.type}</span>
                <span>{doc.tax_year}</span>
                <span>Available: {doc.available_date}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section aria-label="Realized gains and losses">
        <h2>Realized Gains & Losses</h2>
        <div className="rh-tax-center__summary">
          <span>Total:</span>
          <span className={totalGain >= 0 ? "rh-gain" : "rh-loss"}>
            {totalGain >= 0 ? "+" : ""}${totalGain.toFixed(2)}
          </span>
        </div>
        {gains.length === 0 ? (
          <div className="rh-empty">No realized gains or losses</div>
        ) : (
          <table className="rh-table" aria-label="Realized gains table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Buy Date</th>
                <th>Sell Date</th>
                <th>Proceeds</th>
                <th>Cost Basis</th>
                <th>Gain/Loss</th>
                <th>Period</th>
                <th>Wash</th>
              </tr>
            </thead>
            <tbody>
              {gains.map((g, i) => {
                const gl = parseFloat(g.gain_loss);
                return (
                  <tr key={i}>
                    <td>{g.symbol}</td>
                    <td>{g.buy_date}</td>
                    <td>{g.sell_date}</td>
                    <td>${parseFloat(g.proceeds).toFixed(2)}</td>
                    <td>${parseFloat(g.cost_basis).toFixed(2)}</td>
                    <td className={gl >= 0 ? "rh-gain" : "rh-loss"}>${gl.toFixed(2)}</td>
                    <td>{g.holding_period}</td>
                    <td>{g.wash_sale ? "Yes" : "No"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
