import { useEffect, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Order } from "../types";
import { useAmazonLayout } from "../context";
import { useFallbackImage } from "../imageFallbacks";

const RETURN_REASONS = [
  { value: "defective", label: "Item is defective or doesn't work" },
  { value: "wrong_item", label: "Wrong item was sent" },
  { value: "not_as_described", label: "Item not as described" },
  { value: "missing_parts", label: "Missing parts or accessories" },
  { value: "quality_below_expectations", label: "Quality below expectations" },
  { value: "no_longer_needed", label: "No longer needed" },
  { value: "changed_mind", label: "Changed my mind" },
  { value: "arrived_too_late", label: "Item arrived too late" },
  { value: "other", label: "Other reason (write your own)" },
];

export function ReturnFormPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const { api, notify } = useAmazonLayout();
  const navigate = useNavigate();
  const location = useLocation();

  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState(orderId || "");
  const [selectedItemIndex, setSelectedItemIndex] = useState(0);
  const [reason, setReason] = useState("");
  const [otherReason, setOtherReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const isOther = reason === "other";
  const submittedReason = isOther ? otherReason.trim() : reason;

  useEffect(() => {
    let cancelled = false;
    api.getOrders()
      .then((items) => {
        if (cancelled) return;
        setOrders(items);
        if (orderId && items.find((o) => o.id === orderId)) {
          setSelectedOrderId(orderId);
        } else if (items.length > 0) {
          setSelectedOrderId(items[0].id);
        }
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [api, orderId]);

  const selectedOrder = orders.find((o) => o.id === selectedOrderId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrderId || !submittedReason) {
      notify("Error", "Please select an order, item, and reason.");
      return;
    }
    setSubmitting(true);
    try {
      await api.createReturn(selectedOrderId, selectedItemIndex, submittedReason);
      notify("Return Requested", "Your return request has been submitted.");
      navigate(preserveQueryParams("/returns", location.search));
    } catch {
      notify("Error", "Failed to submit your return request.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading orders...</p>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="returns-empty">
        <h1>Request a Return</h1>
        <p>You have no orders to return.</p>
      </div>
    );
  }

  return (
    <div className="return-form-page">
      <h1>Request a Return</h1>

      <div className="return-form-page__card">
        <form onSubmit={handleSubmit}>
          <div className="return-form__field">
            <label htmlFor="return-order">Select Order</label>
            <select
              id="return-order"
              value={selectedOrderId}
              onChange={(e) => {
                setSelectedOrderId(e.target.value);
                setSelectedItemIndex(0);
              }}
              aria-label="Select order for return"
            >
              {orders.map((order) => (
                <option key={order.id} value={order.id}>
                  Order #{order.id} - {new Date(order.placed_at).toLocaleDateString()} - ${(order.total ?? 0).toFixed(2)} ({order.status})
                </option>
              ))}
            </select>
          </div>

          {selectedOrder && (selectedOrder.items ?? []).length > 0 && (
            <div className="return-form__field">
              <label htmlFor="return-item">Select Item</label>
              <select
                id="return-item"
                value={selectedItemIndex}
                onChange={(e) => setSelectedItemIndex(Number(e.target.value))}
                aria-label="Select item to return"
              >
                {selectedOrder.items.map((item, index) => (
                  <option key={index} value={index}>
                    {item.product_name} {item.variant_name ? `(${item.variant_name})` : ""} - Qty: {item.quantity} - ${(item.unit_price ?? 0).toFixed(2)}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="return-form__field">
            <label htmlFor="return-reason">Reason for Return</label>
            <select
              id="return-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              aria-label="Reason for return"
            >
              <option value="">-- Select a reason --</option>
              {RETURN_REASONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>

          {isOther && (
            <div className="return-form__field">
              <label htmlFor="return-reason-other">Describe your reason</label>
              <input
                id="return-reason-other"
                type="text"
                value={otherReason}
                onChange={(e) => setOtherReason(e.target.value)}
                placeholder="e.g. Upgrading to a newer model"
                aria-label="Other return reason"
              />
            </div>
          )}

          {selectedOrder && selectedItemIndex < selectedOrder.items.length && (
            <div className="return-form__preview">
              <h3>Return Preview</h3>
              <div className="return-form__preview-item">
                <div className="return-form__preview-image">
                  {selectedOrder.items[selectedItemIndex].image_url ? (
                    <img
                      src={selectedOrder.items[selectedItemIndex].image_url}
                      alt={selectedOrder.items[selectedItemIndex].product_name}
                      onError={(e) => useFallbackImage(e, {
                        name: selectedOrder.items[selectedItemIndex].product_name,
                        category: selectedOrder.items[selectedItemIndex].category,
                        subcategory: selectedOrder.items[selectedItemIndex].subcategory,
                      })}
                    />
                  ) : (
                    <div className="cart-item__image-placeholder visible">
                      <span>{(selectedOrder.items[selectedItemIndex].product_name ?? "P")[0]}</span>
                    </div>
                  )}
                </div>
                <div>
                  <strong>{selectedOrder.items[selectedItemIndex].product_name}</strong>
                  <div>Price: ${(selectedOrder.items[selectedItemIndex].unit_price ?? 0).toFixed(2)}</div>
                  <div>Quantity: {selectedOrder.items[selectedItemIndex].quantity}</div>
                </div>
              </div>
            </div>
          )}

          <div className="return-form__actions">
            <button
              type="button"
              className="amazon-btn amazon-btn--wishlist"
              onClick={() => navigate(preserveQueryParams("/returns", location.search))}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="amazon-btn amazon-btn--add-to-cart"
              disabled={submitting || !submittedReason}
            >
              {submitting ? "Submitting..." : "Submit Return Request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
