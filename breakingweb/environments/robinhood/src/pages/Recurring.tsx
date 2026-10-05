import { useEffect, useState } from "react";
import { Button } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { RecurringInvestment } from "../types";

export function RecurringPage() {
  const { api, notify } = useRobinhoodLayout();
  const [items, setItems] = useState<RecurringInvestment[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ symbol: "", amount: "", frequency: "weekly", next_execution_date: "" });

  const load = async () => {
    try {
      const data = await api.listRecurring();
      setItems(data);
    } catch { /* skip */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [api]);

  const handleCreate = async () => {
    if (!form.symbol || !form.amount) return;
    try {
      await api.createRecurring({
        symbol: form.symbol.toUpperCase(),
        amount: parseFloat(form.amount),
        frequency: form.frequency,
        next_execution_date: form.next_execution_date || new Date().toISOString().slice(0, 10),
      });
      notify("Created", `Recurring investment in ${form.symbol.toUpperCase()}`);
      setShowCreate(false);
      setForm({ symbol: "", amount: "", frequency: "weekly", next_execution_date: "" });
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to create");
    }
  };

  const handleToggle = async (ri: RecurringInvestment) => {
    try {
      const newStatus = ri.status === "active" ? "paused" : "active";
      await api.updateRecurring(ri.id, { status: newStatus });
      notify(newStatus === "active" ? "Resumed" : "Paused", `${ri.symbol} recurring investment`);
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to update");
    }
  };

  const handleDelete = async (ri: RecurringInvestment) => {
    try {
      await api.deleteRecurring(ri.id);
      notify("Deleted", `${ri.symbol} recurring investment`);
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to delete");
    }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-recurring" aria-label="Recurring investments">
      <div className="rh-page-header">
        <h1>Recurring Investments</h1>
        <Button variant="primary" onClick={() => setShowCreate(true)} aria-label="Create recurring investment">
          + Create
        </Button>
      </div>

      {showCreate && (
        <div className="rh-recurring__create">
          <div className="rh-order-form__field">
            <label htmlFor="ri-symbol">Symbol</label>
            <input id="ri-symbol" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} placeholder="AAPL" />
          </div>
          <div className="rh-order-form__field">
            <label htmlFor="ri-amount">Amount ($)</label>
            <input id="ri-amount" type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} placeholder="50" />
          </div>
          <div className="rh-order-form__field">
            <label htmlFor="ri-freq">Frequency</label>
            <select id="ri-freq" value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="biweekly">Biweekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </div>
          <div className="rh-order-form__field">
            <label htmlFor="ri-next-date">Next execution date</label>
            <input
              id="ri-next-date"
              type="date"
              value={form.next_execution_date}
              onChange={(e) => setForm({ ...form, next_execution_date: e.target.value })}
            />
          </div>
          <div className="rh-watchlists__create-actions">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button variant="primary" onClick={handleCreate}>Create</Button>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="rh-empty">No recurring investments</div>
      ) : (
        <div className="rh-recurring__list">
          {items.map((ri) => (
            <div key={ri.id} className="rh-recurring__row" aria-label={`${ri.symbol} recurring`}>
              <div className="rh-recurring__info">
                <span className="rh-recurring__symbol">{ri.symbol}</span>
                <span className="rh-recurring__amount">${parseFloat(ri.amount).toFixed(2)}</span>
                <span className="rh-recurring__freq">{ri.frequency}</span>
              </div>
              {ri.history && ri.history.length > 0 && (
                <div className="rh-recurring__history" style={{ fontSize: "0.75rem", color: "var(--rh-gray-500)", marginTop: 2 }}>
                  {(() => {
                    const avgPrice = ri.history.reduce((sum, e) => sum + parseFloat(e.price), 0) / ri.history.length;
                    return (
                      <span aria-label={`${ri.symbol} avg purchase price`}>
                        Avg cost: <strong style={{ color: "var(--rh-text)" }}>${avgPrice.toFixed(2)}</strong>
                        {" · "}{ri.history.length} execution{ri.history.length !== 1 ? "s" : ""}
                      </span>
                    );
                  })()}
                </div>
              )}
              <div className="rh-recurring__meta">
                <span className={`rh-recurring__status ${ri.status === "active" ? "rh-gain" : ""}`}>
                  {ri.status}
                </span>
                <span>Next: {ri.next_execution_date}</span>
              </div>
              <div className="rh-recurring__actions">
                <Button variant="secondary" onClick={() => handleToggle(ri)}>
                  {ri.status === "active" ? "Pause" : "Resume"}
                </Button>
                <Button variant="secondary" onClick={() => handleDelete(ri)} aria-label={`Delete ${ri.symbol} recurring`}>
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
