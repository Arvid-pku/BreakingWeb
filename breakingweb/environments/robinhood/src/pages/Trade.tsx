import { useEffect, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { Position, Stock } from "../types";
import { OrderForm } from "../components/OrderForm";

export function TradePage() {
  const { symbol } = useParams<{ symbol: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { api, notify, refreshAccount } = useRobinhoodLayout();
  const [stock, setStock] = useState<Stock | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await api.getStock(symbol);
        if (!cancelled) setStock(s);
      } catch { /* skip */ }
      try {
        const p = await api.getPosition(symbol);
        if (!cancelled) setPosition(p);
      } catch { /* no position */ }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [api, symbol]);

  if (loading) return <div className="rh-loading">Loading...</div>;
  if (!stock || !symbol) return <div className="rh-empty">Stock not found</div>;

  const price = parseFloat(stock.price);
  const maxShares = position ? parseFloat(position.quantity) : 0;

  return (
    <div className="rh-trade-page" aria-label={`Trade ${symbol}`}>
      <div className="rh-trade-page__header">
        <button
          className="rh-back-btn"
          onClick={() => navigate(preserveQueryParams(`/stocks/${symbol}`, location.search))}
          aria-label="Back to stock detail"
        >
          ← {stock.name}
        </button>
        <h1>Trade {symbol}</h1>
        <div className="rh-trade-page__price">
          <span>${price.toFixed(2)}</span>
        </div>
      </div>
      <OrderForm
        symbol={symbol}
        currentPrice={price}
        maxShares={maxShares}
        onSubmit={async (order) => {
          try {
            const result = await api.placeOrder({
              symbol,
              ...order,
            });
            notify(
              "Order Placed",
              `${order.side === "buy" ? "Buy" : "Sell"} ${order.quantity} shares of ${symbol} — ${result.status}`,
            );
            await refreshAccount();
            navigate(preserveQueryParams(`/stocks/${symbol}`, location.search));
          } catch (err) {
            notify("Order Failed", err instanceof Error ? err.message : "Unknown error");
          }
        }}
      />
    </div>
  );
}
