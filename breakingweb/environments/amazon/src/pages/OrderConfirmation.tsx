import { useEffect, useState } from "react";
import { Link, useParams, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Address, Order } from "../types";
import { useAmazonLayout } from "../context";
import { useFallbackImage } from "../imageFallbacks";

const CANCELLABLE_STATUSES = new Set(["pending", "confirmed", "processing"]);

export function OrderConfirmationPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const { api, notify } = useAmazonLayout();
  const location = useLocation();

  const [order, setOrder] = useState<Order | null>(null);
  const [address, setAddress] = useState<Address | null>(null);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    if (!orderId) return;
    let cancelled = false;

    Promise.all([
      api.getOrder(orderId),
      api.getAddresses(),
    ])
      .then(([o, addresses]) => {
        if (cancelled) return;
        setOrder(o);
        const addr = addresses.find((a) => a.id === o.shipping_address_id);
        setAddress(addr ?? null);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [api, orderId]);

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading order confirmation...</p>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="amazon-error">
        <h2>Order not found</h2>
        <p>Could not find order details.</p>
      </div>
    );
  }

  return (
    <div className="order-confirmation">
      <div className="order-confirmation__simulation-banner" role="alert">
        SIMULATED ORDER - This is a simulated order in a benchmark environment. No real purchase was made. No charges have been applied.
      </div>

      <div className="order-confirmation__card">
        <div className="order-confirmation__header">
          <div className="order-confirmation__check" aria-hidden="true">&#10003;</div>
          <div>
            <h1 className="order-confirmation__title">Order placed, thank you!</h1>
            <p className="order-confirmation__subtitle">
              Confirmation will be sent to your email address.
            </p>
          </div>
        </div>

        <div className="order-confirmation__details">
          <div className="order-confirmation__detail-row">
            <span className="order-confirmation__label">Order number:</span>
            <span className="order-confirmation__value">{order.id}</span>
          </div>
          <div className="order-confirmation__detail-row">
            <span className="order-confirmation__label">Order date:</span>
            <span className="order-confirmation__value">{new Date(order.placed_at).toLocaleDateString()}</span>
          </div>
          <div className="order-confirmation__detail-row">
            <span className="order-confirmation__label">Status:</span>
            <span className="order-confirmation__value order-confirmation__status">{order.status}</span>
          </div>
          {order.estimated_delivery && (
            <div className="order-confirmation__detail-row">
              <span className="order-confirmation__label">Estimated delivery:</span>
              <span className="order-confirmation__value">{order.estimated_delivery}</span>
            </div>
          )}
          <div className="order-confirmation__detail-row">
            <span className="order-confirmation__label">Order total:</span>
            <span className="order-confirmation__value"><strong>${order.total.toFixed(2)}</strong></span>
          </div>
        </div>

        <hr />

        <h2>Items ordered</h2>
        <div className="order-confirmation__items">
          {(order.items ?? []).map((item, i) => (
            <div key={i} className="order-confirmation__item">
              <div className="order-confirmation__item-image">
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
              <div className="order-confirmation__item-info">
                <div className="order-confirmation__item-name">{item.product_name}</div>
                {item.variant_name && <div className="order-confirmation__item-variant">Variant: {item.variant_name}</div>}
                <div>Qty: {item.quantity}</div>
                <div>${(item.unit_price ?? 0).toFixed(2)}</div>
              </div>
            </div>
          ))}
        </div>

        <hr />

        <h2>Shipping address</h2>
        <div className="order-confirmation__address">
          {address ? (
            <>
              <p>{address.full_name}</p>
              <p>{address.street_address}</p>
              <p>{address.city}, {address.state} {address.zip_code}</p>
              <p>{address.country}</p>
            </>
          ) : (
            <p>Address ID: {order.shipping_address_id}</p>
          )}
        </div>

        <hr />

        <h2>Payment summary</h2>
        <div className="order-confirmation__payment-summary">
          <div className="checkout-summary-box__row">
            <span>Subtotal:</span><span>${(order.subtotal ?? 0).toFixed(2)}</span>
          </div>
          <div className="checkout-summary-box__row">
            <span>Shipping:</span><span>${(order.shipping_cost ?? 0).toFixed(2)}</span>
          </div>
          <div className="checkout-summary-box__row">
            <span>Tax:</span><span>${(order.tax ?? 0).toFixed(2)}</span>
          </div>
          <div className="checkout-summary-box__row checkout-summary-box__row--total">
            <strong>Total:</strong><strong>${(order.total ?? 0).toFixed(2)}</strong>
          </div>
        </div>

        <div className="order-confirmation__actions">
          <Link
            to={preserveQueryParams("/orders", location.search)}
            className="amazon-btn amazon-btn--add-to-cart"
          >
            View all orders
          </Link>
          <Link
            to={preserveQueryParams("/home", location.search)}
            className="amazon-btn amazon-btn--wishlist"
          >
            Continue shopping
          </Link>
          {CANCELLABLE_STATUSES.has(order.status.toLowerCase()) && (
            <button
              type="button"
              className="amazon-btn amazon-btn--cancel"
              data-action="cancel-order"
              data-order-id={order.id}
              aria-label={`Cancel order ${order.id}`}
              disabled={cancelling}
              onClick={async () => {
                if (!order) return;
                setCancelling(true);
                try {
                  const updated = await api.cancelOrder(order.id);
                  setOrder(updated);
                  notify(
                    "Order Cancelled",
                    `Order #${order.id} has been cancelled.`,
                  );
                } catch {
                  setOrder({ ...order, status: "cancelled" });
                  notify(
                    "Order Cancelled (simulated)",
                    `Order #${order.id} has been cancelled.`,
                  );
                } finally {
                  setCancelling(false);
                }
              }}
            >
              {cancelling ? "Cancelling..." : "Cancel Order"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
