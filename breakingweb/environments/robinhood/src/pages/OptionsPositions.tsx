import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { OptionsOrder, OptionsPosition } from "../types";

function buildCloseLink(position: OptionsPosition, currentSearch: string): string {
  const params = new URLSearchParams();
  params.set("action", "close");
  params.set("contract_id", position.contract_id);
  params.set("position_side", position.position_side);
  params.set("strike", position.strike_price);
  params.set("expiration", position.expiration_date);
  params.set("option_type", position.option_type);
  params.set("quantity", String(position.quantity));
  return preserveQueryParams(
    `/stocks/${position.underlying_symbol}/options/trade?${params.toString()}`,
    currentSearch,
  );
}

function buildRollLink(position: OptionsPosition, currentSearch: string): string {
  const params = new URLSearchParams();
  params.set("action", "roll");
  params.set("contract_id", position.contract_id);
  params.set("position_side", position.position_side);
  params.set("strike", position.strike_price);
  params.set("expiration", position.expiration_date);
  params.set("option_type", position.option_type);
  params.set("quantity", String(position.quantity));
  return preserveQueryParams(
    `/stocks/${position.underlying_symbol}/options/trade?${params.toString()}`,
    currentSearch,
  );
}

export function OptionsPositionsPage() {
  const { api } = useRobinhoodLayout();
  const location = useLocation();
  const [positions, setPositions] = useState<OptionsPosition[]>([]);
  const [orders, setOrders] = useState<OptionsOrder[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getOptionsPositions(), api.listOptionsOrders()])
      .then(([nextPositions, nextOrders]) => {
        if (cancelled) return;
        setPositions(nextPositions);
        setOrders(nextOrders);
      })
      .catch(() => {
        // silently continue
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-options-positions" aria-label="Options positions">
      <div className="rh-page-header">
        <div>
          <h1>Options Positions</h1>
          <p className="rh-alerts__subtitle">Open contracts and recent multi-leg orders.</p>
        </div>
        <Link to={preserveQueryParams("/search", location.search)}>
          <Button variant="primary" aria-label="Browse stocks for options trading">
            Browse Chains
          </Button>
        </Link>
      </div>

      <section aria-label="Open options positions">
        <h2>Open Positions</h2>
        {positions.length === 0 ? (
          <div className="rh-empty">No open options positions</div>
        ) : (
          <div className="rh-options-positions__grid">
            {positions.map((position) => {
              const closeSide: "buy" | "sell" = position.position_side === "long" ? "sell" : "buy";
              const closeLabel = position.position_side === "long" ? "Sell to Close" : "Buy to Close";
              return (
                <div key={position.id} className="rh-options-positions__card">
                  <div className="rh-options-positions__card-top">
                    <Link
                      to={preserveQueryParams(`/stocks/${position.underlying_symbol}/options`, location.search)}
                      className="rh-link"
                    >
                      {position.underlying_symbol}
                    </Link>
                    <span>{position.option_type.toUpperCase()}</span>
                    <span aria-label={`Position side: ${position.position_side}`} style={{ fontWeight: 600, color: position.position_side === "long" ? "var(--rh-green)" : "var(--rh-red)" }}>
                      {position.position_side.toUpperCase()}
                    </span>
                  </div>
                  <div className="rh-options-positions__card-main">
                    <strong>${Number.parseFloat(position.strike_price).toFixed(2)}</strong>
                    <span>exp {position.expiration_date}</span>
                  </div>
                  <div className="rh-options-positions__card-grid">
                    <span>Quantity</span>
                    <span>{position.quantity}</span>
                    <span>Avg Cost</span>
                    <span>${Number.parseFloat(position.avg_cost).toFixed(2)}</span>
                    <span>Current Premium</span>
                    <span>${Number.parseFloat(position.current_premium).toFixed(2)}</span>
                    <span>Status</span>
                    <span>{position.status}</span>
                  </div>
                  <div className="rh-options-positions__card-actions">
                    <Link to={buildCloseLink(position, location.search)}>
                      <Button
                        variant="secondary"
                        aria-label={`${closeLabel} ${position.underlying_symbol} ${position.option_type} ${position.strike_price} ${position.expiration_date}`}
                        data-testid={`close-position-${position.id}`}
                      >
                        {closeLabel} ({closeSide})
                      </Button>
                    </Link>
                    <Link to={buildRollLink(position, location.search)}>
                      <Button
                        variant="secondary"
                        aria-label={`Roll ${position.underlying_symbol} ${position.option_type} ${position.strike_price} ${position.expiration_date}`}
                        data-testid={`roll-position-${position.id}`}
                      >
                        Roll
                      </Button>
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section aria-label="Options orders">
        <h2>Recent Orders</h2>
        {orders.length === 0 ? (
          <div className="rh-empty">No options orders yet</div>
        ) : (
          <table className="rh-table" aria-label="Options orders table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Legs</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td>{order.strategy.replace(/_/g, " ")}</td>
                  <td>
                    {order.legs.map((leg, index) => (
                      <div key={`${order.id}-${index}`} className="rh-options-positions__leg-summary">
                        {leg.side} {leg.quantity} {leg.option_type} {leg.strike} exp {leg.expiration}
                      </div>
                    ))}
                  </td>
                  <td>{order.status}</td>
                  <td>{new Date(order.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
