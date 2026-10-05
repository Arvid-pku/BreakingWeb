import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Order, Address } from "../types";
import { useAmazonLayout } from "../context";
import { useFallbackImage } from "../imageFallbacks";

export function OrdersPage() {
  const { api, notify } = useAmazonLayout();
  const location = useLocation();
  const navigate = useNavigate();
  const [orders, setOrders] = useState<Order[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getOrders().catch(() => [] as Order[]),
      api.getAddresses().catch(() => [] as Address[]),
    ]).then(([items, addrs]) => {
      if (!cancelled) {
        setOrders(items ?? []);
        setAddresses(addrs ?? []);
      }
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api]);

  const handleCancelOrder = async (orderId: string) => {
    setCancellingId(orderId);
    try {
      const updated = await api.cancelOrder(orderId);
      setOrders((prev) => prev.map((o) => (o.id === orderId ? updated : o)));
      notify("Order Cancelled", `Order #${orderId} has been cancelled.`);
    } catch {
      setOrders((prev) =>
        prev.map((o) => (o.id === orderId ? { ...o, status: "cancelled" } : o))
      );
      notify("Order Cancelled (simulated)", `Order #${orderId} has been cancelled.`);
    }
    setCancellingId(null);
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading orders...</p>
      </div>
    );
  }

  const statusTimeline = (status: string) => {
    const steps = ["confirmed", "shipped", "out_for_delivery", "delivered"];
    const labels = ["Confirmed", "Shipped", "Out for Delivery", "Delivered"];
    const currentIndex = steps.indexOf(status.toLowerCase());

    if (status.toLowerCase() === "cancelled") {
      return (
        <div className="order-timeline">
          <div className="order-timeline__step order-timeline__step--cancelled">
            <div className="order-timeline__dot" />
            <span>Cancelled</span>
          </div>
        </div>
      );
    }

    return (
      <div className="order-timeline">
        {steps.map((step, i) => (
          <div
            key={step}
            className={`order-timeline__step ${i <= currentIndex ? "order-timeline__step--complete" : ""} ${i === currentIndex ? "order-timeline__step--current" : ""}`}
          >
            <div className="order-timeline__dot" />
            <span>{labels[i]}</span>
            {i < steps.length - 1 && <div className="order-timeline__line" />}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="orders-page">
      <h1>Your Orders</h1>

      {orders.length === 0 ? (
        <div className="orders-empty">
          <h2>No orders yet</h2>
          <p>You haven't placed any orders. <Link to={preserveQueryParams("/home", location.search)}>Start shopping</Link>.</p>
        </div>
      ) : (
        <div className="orders-list">
          {orders.map((order) => {
            const isCancelled = order.status.toLowerCase() === "cancelled";

            return (
              <article key={order.id} className="order-card" aria-label={`Order ${order.id}`}>
                <div className="order-card__header">
                  <div className="order-card__header-col">
                    <span className="order-card__label">ORDER PLACED</span>
                    <span>{new Date(order.placed_at).toLocaleDateString()}</span>
                  </div>
                  <div className="order-card__header-col">
                    <span className="order-card__label">TOTAL</span>
                    <span>${(order.total ?? 0).toFixed(2)}</span>
                  </div>
                  <div className="order-card__header-col">
                    <span className="order-card__label">SHIP TO</span>
                    <span>{addresses.find((a) => a.id === order.shipping_address_id)?.full_name ?? "Address on file"}</span>
                  </div>
                  <div className="order-card__header-col order-card__header-col--right">
                    <span className="order-card__label">ORDER # {order.id}</span>
                    <Link
                      to={preserveQueryParams(`/order-confirmation/${order.id}`, location.search)}
                      className="order-card__detail-link"
                    >
                      View order details
                    </Link>
                  </div>
                </div>

                <div className="order-card__body">
                  <div className="order-card__status">
                    <strong>{order.status}</strong>
                    {order.estimated_delivery && (
                      <span> - Estimated delivery: {order.estimated_delivery}</span>
                    )}
                    {order.is_simulated && (
                      <span className="order-card__simulated"> (Simulated)</span>
                    )}
                  </div>

                  {statusTimeline(order.status)}

                  <div className="order-card__items">
                    {(order.items ?? []).map((item, i) => (
                      <div key={i} className="order-card__item">
                        <div className="order-card__item-image">
                          {item.image_url ? (
                            <img
                              src={item.image_url}
                              alt={item.product_name}
                              style={{ width: "100%", height: "100%", objectFit: "contain" }}
                              onError={(e) => useFallbackImage(e, {
                                name: item.product_name,
                                category: item.category,
                                subcategory: item.subcategory,
                              })}
                            />
                          ) : (
                            <div className="cart-item__image-placeholder visible"><span>{(item.product_name ?? "P")[0]}</span></div>
                          )}
                        </div>
                        <div className="order-card__item-info">
                          <Link
                            to={preserveQueryParams(`/product/${item.product_id}`, location.search)}
                            className="order-card__item-name"
                          >
                            {item.product_name}
                          </Link>
                          {item.variant_name && <div>Variant: {item.variant_name}</div>}
                          <div>Qty: {item.quantity} - ${(item.unit_price ?? 0).toFixed(2)} each</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="order-card__actions" data-order-id={order.id}>
                    <Link
                      to={preserveQueryParams(`/order-confirmation/${order.id}`, location.search)}
                      className="amazon-btn amazon-btn--wishlist"
                      data-action="track-order"
                      data-order-id={order.id}
                      aria-label={`Track order ${order.id}`}
                    >
                      Track Order
                    </Link>

                    {/* The /returns endpoint accepts any status that isn't
                        cancelled; showing Return Item for confirmed/shipped
                        orders too matches the backend and unblocks tasks
                        (e.g. full_order_lifecycle) that ask the agent to
                        return an item from a freshly-placed order. */}
                    {!isCancelled && order.status.toLowerCase() !== "pending" && (
                      <button
                        className="amazon-btn amazon-btn--add-to-cart"
                        onClick={() => navigate(preserveQueryParams(`/returns/new/${order.id}`, location.search))}
                        data-action="return-item"
                        data-order-id={order.id}
                        aria-label={`Return item from order ${order.id}`}
                      >
                        Return Item
                      </button>
                    )}

                    {/* Cancel is allowed by the backend for any status that is
                        not yet shipped/delivered/cancelled. The previous gate
                        (``isConfirmed`` only) hid the affordance for orders in
                        ``pending`` state, which annotators reported as
                        "didn't find a place to cancel it". */}
                    {!isCancelled &&
                      !["shipped", "out_for_delivery", "delivered"].includes(
                        order.status.toLowerCase(),
                      ) && (
                      <button
                        className="amazon-btn amazon-btn--cancel"
                        onClick={() => handleCancelOrder(order.id)}
                        disabled={cancellingId === order.id}
                        data-action="cancel-order"
                        data-order-id={order.id}
                        aria-label={`Cancel order ${order.id}`}
                      >
                        {cancellingId === order.id ? "Cancelling..." : "Cancel Order"}
                      </button>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
