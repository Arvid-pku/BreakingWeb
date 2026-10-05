import { useEffect, useState } from "react";
import { Button } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { Order } from "../types";

type TabKey = "pending" | "filled" | "cancelled";

export function OrdersPage() {
  const { api, notify } = useRobinhoodLayout();
  const [orders, setOrders] = useState<Order[]>([]);
  const [marketPrices, setMarketPrices] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>("pending");

  const load = async () => {
    try {
      const items = await api.listOrders();
      setOrders(items);
      const symbols = [...new Set(items.map((o) => o.symbol))];
      const priceEntries = await Promise.all(
        symbols.map((sym) => api.getStock(sym).then((s) => [sym, s.price] as [string, string]).catch(() => [sym, ""] as [string, string]))
      );
      setMarketPrices(Object.fromEntries(priceEntries));
    } catch { /* skip */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [api]);

  const filtered = orders.filter((o) => {
    if (activeTab === "pending") return o.status === "pending" || o.status === "partially_filled";
    if (activeTab === "filled") return o.status === "filled";
    return o.status === "cancelled" || o.status === "rejected";
  });

  const handleCancel = async (orderId: string) => {
    try {
      await api.cancelOrder(orderId);
      notify("Order Cancelled");
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to cancel order");
    }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-orders" aria-label="Orders">
      <h1>Orders</h1>
      <div className="rh-tabs">
        {(["pending", "filled", "cancelled"] as TabKey[]).map((tab) => (
          <button
            key={tab}
            className={`rh-tab ${activeTab === tab ? "rh-tab--active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="rh-empty">No {activeTab} orders</div>
      ) : (
        <div className="rh-orders__list">
          {filtered.map((order) => (
            <div key={order.id} className="rh-orders__row" aria-label={`${order.side} ${order.symbol} order`}>
              <div className="rh-orders__info">
                <span className="rh-orders__symbol">{order.symbol}</span>
                <span className={`rh-orders__side ${order.side === "buy" ? "rh-gain" : "rh-loss"}`}>
                  {order.side.toUpperCase()}
                </span>
                <span className="rh-orders__type">{order.order_type.replace("_", " ")}</span>
              </div>
              <div className="rh-orders__details">
                <span>{parseFloat(order.filled_quantity)}/{parseFloat(order.quantity)} shares</span>
                {order.limit_price && <span>Limit: ${parseFloat(order.limit_price).toFixed(2)}</span>}
                {order.stop_price && <span>Stop: ${parseFloat(order.stop_price).toFixed(2)}</span>}
                {marketPrices[order.symbol] && <span aria-label={`Current market price: $${parseFloat(marketPrices[order.symbol]).toFixed(2)}`}>Market: ${parseFloat(marketPrices[order.symbol]).toFixed(2)}</span>}
                <span className="rh-orders__status">{order.status}</span>
              </div>
              <div className="rh-orders__meta">
                <span>{new Date(order.created_at).toLocaleDateString()}</span>
                {order.status === "pending" && (
                  <Button variant="secondary" onClick={() => handleCancel(order.id)} aria-label={`Cancel ${order.symbol} order`}>
                    Cancel
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
