import { useEffect, useState } from "react";

import { useRobinhoodLayout } from "../context";
import type { Transaction } from "../types";

export function TransactionsPage() {
  const { api } = useRobinhoodLayout();
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    const query: Record<string, string> = {};
    if (typeFilter) query.type = typeFilter;
    api.listTransactions(query)
      .then((items) => { if (!cancelled) setTransactions(items); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, typeFilter]);

  if (loading) return <div className="rh-loading">Loading...</div>;

  const types = ["buy", "sell", "dividend", "interest", "deposit", "withdrawal", "fee"];

  return (
    <div className="rh-transactions" aria-label="Transaction history">
      <h1>History</h1>

      <div className="rh-transactions__filters">
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setLoading(true); }}
          aria-label="Filter by transaction type"
        >
          <option value="">All Types</option>
          {types.map((t) => (
            <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
          ))}
        </select>
      </div>

      {transactions.length === 0 ? (
        <div className="rh-empty">No transactions found</div>
      ) : (
        <div className="rh-transactions__list">
          {transactions.map((tx) => {
            const amount = parseFloat(tx.amount);
            const isCredit = ["sell", "dividend", "interest", "deposit", "referral_bonus"].includes(tx.type);
            return (
              <div key={tx.id} className="rh-transactions__row" aria-label={tx.description}>
                <div className="rh-transactions__info">
                  <span className="rh-transactions__type">{tx.type.replace(/_/g, " ")}</span>
                  {tx.symbol && <span className="rh-transactions__symbol">{tx.symbol}</span>}
                </div>
                <div className="rh-transactions__desc">{tx.description}</div>
                <div className="rh-transactions__amount-col">
                  <span className={isCredit ? "rh-gain" : "rh-loss"}>
                    {isCredit ? "+" : "-"}${Math.abs(amount).toFixed(2)}
                  </span>
                  <span className="rh-transactions__date">
                    {new Date(tx.timestamp).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
