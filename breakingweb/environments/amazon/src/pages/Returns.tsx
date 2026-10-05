import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { ReturnRequest, Order } from "../types";
import { useAmazonLayout } from "../context";
import { useFallbackImage } from "../imageFallbacks";

function statusColor(status: string): string {
  switch (status.toLowerCase()) {
    case "pending": return "returns-badge--pending";
    case "approved": return "returns-badge--approved";
    case "denied": return "returns-badge--denied";
    case "refund_issued": return "returns-badge--refunded";
    default: return "";
  }
}

export function ReturnsPage() {
  const { api } = useAmazonLayout();
  const location = useLocation();
  const [returns, setReturns] = useState<ReturnRequest[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getReturns().catch(() => [] as ReturnRequest[]),
      api.getOrders().catch(() => [] as Order[]),
    ]).then(([rets, ords]) => {
      if (cancelled) return;
      setReturns(rets);
      setOrders(ords);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [api]);

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading returns...</p>
      </div>
    );
  }

  const deliveredOrders = orders.filter((o) => o.status.toLowerCase() === "delivered");

  return (
    <div className="returns-page">
      <div className="returns-page__header">
        <h1>Your Returns</h1>
        {deliveredOrders.length > 0 && (
          <Link
            to={preserveQueryParams(`/returns/new/${deliveredOrders[0].id}`, location.search)}
            className="amazon-btn amazon-btn--add-to-cart"
          >
            Request a Return
          </Link>
        )}
      </div>

      {returns.length === 0 ? (
        <div className="returns-empty">
          <h2>No returns yet</h2>
          <p>You have not requested any returns. If you need to return an item, visit your <Link to={preserveQueryParams("/orders", location.search)}>Orders</Link> page.</p>
        </div>
      ) : (
        <div className="returns-list">
          {returns.map((ret) => (
            <article key={ret.id} className="returns-card" aria-label={`Return ${ret.id}`}>
              <div className="returns-card__header">
                <div className="returns-card__col">
                  <span className="returns-card__label">RETURN ID</span>
                  <span>{ret.id}</span>
                </div>
                <div className="returns-card__col">
                  <span className="returns-card__label">ORDER</span>
                  <Link to={preserveQueryParams(`/order-confirmation/${ret.order_id}`, location.search)}>
                    {ret.order_id}
                  </Link>
                </div>
                <div className="returns-card__col">
                  <span className="returns-card__label">CREATED</span>
                  <span>{new Date(ret.created_at).toLocaleDateString()}</span>
                </div>
                <div className="returns-card__col">
                  <span className="returns-card__label">STATUS</span>
                  <span className={`returns-badge ${statusColor(ret.status)}`}>
                    {ret.status.replace(/_/g, " ")}
                  </span>
                </div>
              </div>
              <div className="returns-card__body">
                <div className="returns-card__product">
                  <div className="returns-card__product-image">
                    {ret.image_url ? (
                      <img
                        src={ret.image_url}
                        alt={ret.product_name}
                        onError={(e) => useFallbackImage(e, {
                          name: ret.product_name,
                          category: ret.category,
                          subcategory: ret.subcategory,
                        })}
                      />
                    ) : (
                      <div className="cart-item__image-placeholder visible">
                        <span>{(ret.product_name ?? "P")[0]}</span>
                      </div>
                    )}
                  </div>
                  <strong>{ret.product_name}</strong>
                </div>
                <div className="returns-card__reason">
                  <span className="returns-card__label-inline">Reason:</span> {ret.reason.replace(/_/g, " ")}
                </div>
                <div className="returns-card__refund">
                  <span className="returns-card__label-inline">Refund amount:</span> ${(ret.refund_amount ?? 0).toFixed(2)}
                </div>
                {ret.resolution_note && (
                  <div className="returns-card__note">
                    <span className="returns-card__label-inline">Note:</span> {ret.resolution_note}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
