import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { PriceAlert } from "../types";

export function AlertsPage() {
  const { api, notify } = useRobinhoodLayout();
  const location = useLocation();
  const query = new URLSearchParams(location.search);
  const querySymbol = query.get("symbol")?.toUpperCase() ?? "";

  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol] = useState(querySymbol);
  const [condition, setCondition] = useState<"above" | "below">("above");
  const [targetPrice, setTargetPrice] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = async () => {
    try {
      const items = await api.listAlerts();
      setAlerts(items);
    } catch {
      // silently continue
    }
    setLoading(false);
  };

  useEffect(() => {
    setSymbol(querySymbol);
  }, [querySymbol]);

  useEffect(() => {
    void load();
  }, [api]);

  const handleCreate = async () => {
    if (!symbol.trim() || !targetPrice.trim()) return;
    setIsSubmitting(true);
    try {
      await api.createAlert({
        symbol: symbol.trim().toUpperCase(),
        condition,
        target_price: Number.parseFloat(targetPrice),
      });
      notify("Alert Created", `${symbol.trim().toUpperCase()} ${condition} $${targetPrice}`);
      setTargetPrice("");
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to create alert");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (alertId: string) => {
    try {
      const removed = await api.deleteAlert(alertId);
      notify("Alert Removed", `${removed.symbol} ${removed.condition} $${removed.target_price}`);
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to delete alert");
    }
  };

  const filteredAlerts = querySymbol
    ? alerts.filter((alert) => alert.symbol === querySymbol)
    : alerts;

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-alerts" aria-label="Price alerts">
      <div className="rh-page-header">
        <div>
          <h1>Price Alerts</h1>
          {querySymbol ? (
            <p className="rh-alerts__subtitle">
              Managing alerts for {querySymbol}.{" "}
              <Link to={preserveQueryParams("/alerts", location.search)} className="rh-link">
                View all alerts
              </Link>
            </p>
          ) : null}
        </div>
      </div>

      <section className="rh-alerts__composer" aria-label="Create alert">
        <div className="rh-order-form__field">
          <label htmlFor="alert-symbol">Symbol</label>
          <input
            id="alert-symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="AAPL"
          />
        </div>
        <div className="rh-order-form__field">
          <label htmlFor="alert-condition">Condition</label>
          <select
            id="alert-condition"
            value={condition}
            onChange={(e) => setCondition(e.target.value as "above" | "below")}
          >
            <option value="above">Above</option>
            <option value="below">Below</option>
          </select>
        </div>
        <div className="rh-order-form__field">
          <label htmlFor="alert-target-price">Target Price</label>
          <input
            id="alert-target-price"
            type="number"
            min="0"
            step="0.01"
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder="180.00"
          />
        </div>
        <Button
          variant="primary"
          disabled={isSubmitting || !symbol.trim() || !targetPrice.trim()}
          onClick={handleCreate}
          aria-label="Create price alert"
        >
          {isSubmitting ? "Creating..." : "Create Alert"}
        </Button>
      </section>

      {filteredAlerts.length === 0 ? (
        <div className="rh-empty">
          {querySymbol ? `No alerts for ${querySymbol}` : "No price alerts yet"}
        </div>
      ) : (
        <table className="rh-table" aria-label="Price alerts table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Condition</th>
              <th>Target</th>
              <th>Status</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filteredAlerts.map((alert) => (
              <tr key={alert.id}>
                <td>
                  <Link to={preserveQueryParams(`/stocks/${alert.symbol}`, location.search)} className="rh-link">
                    {alert.symbol}
                  </Link>
                </td>
                <td>{alert.condition}</td>
                <td>${Number.parseFloat(alert.target_price).toFixed(2)}</td>
                <td>{alert.status}</td>
                <td>{new Date(alert.created_at).toLocaleString()}</td>
                <td className="rh-alerts__actions-cell">
                  <Button
                    variant="secondary"
                    onClick={() => handleDelete(alert.id)}
                    aria-label={`Delete alert for ${alert.symbol}`}
                  >
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
