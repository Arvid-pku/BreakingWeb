import { useState } from "react";
import { Button } from "@breakingweb/shared";

interface OrderFormProps {
  symbol: string;
  currentPrice: number;
  onSubmit: (order: {
    side: "buy" | "sell";
    order_type: string;
    quantity: number;
    limit_price?: number;
    stop_price?: number;
    trail_amount?: number;
    trail_pct?: number;
    time_in_force: string;
    extended_hours: boolean;
  }) => Promise<void>;
  defaultSide?: "buy" | "sell";
  maxShares?: number;
}

const ORDER_TYPES = [
  { value: "market", label: "Market Order" },
  { value: "limit", label: "Limit Order" },
  { value: "stop", label: "Stop Order" },
  { value: "stop_limit", label: "Stop Limit Order" },
  { value: "trailing_stop", label: "Trailing Stop Order" },
];

const TIF_OPTIONS = [
  { value: "gfd", label: "Good for Day" },
  { value: "gtc", label: "Good till Cancelled" },
];

export function OrderForm({ symbol, currentPrice, onSubmit, defaultSide = "buy", maxShares }: OrderFormProps) {
  const [side, setSide] = useState<"buy" | "sell">(defaultSide);
  const [orderType, setOrderType] = useState("market");
  const [quantity, setQuantity] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [trailAmount, setTrailAmount] = useState("");
  const [timeInForce, setTimeInForce] = useState("gfd");
  const [extendedHours, setExtendedHours] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showReview, setShowReview] = useState(false);

  const qty = parseFloat(quantity) || 0;
  const estimatedCost = qty * currentPrice;

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onSubmit({
        side,
        order_type: orderType,
        quantity: qty,
        limit_price: limitPrice ? parseFloat(limitPrice) : undefined,
        stop_price: stopPrice ? parseFloat(stopPrice) : undefined,
        trail_amount: trailAmount ? parseFloat(trailAmount) : undefined,
        time_in_force: timeInForce,
        extended_hours: extendedHours,
      });
    } finally {
      setIsSubmitting(false);
      setShowReview(false);
    }
  };

  return (
    <div className="rh-order-form">
      <div className="rh-order-form__tabs">
        <button
          className={`rh-order-form__tab ${side === "buy" ? "rh-order-form__tab--active rh-order-form__tab--buy" : ""}`}
          onClick={() => setSide("buy")}
        >
          Buy
        </button>
        <button
          className={`rh-order-form__tab ${side === "sell" ? "rh-order-form__tab--active rh-order-form__tab--sell" : ""}`}
          onClick={() => setSide("sell")}
        >
          Sell
        </button>
      </div>

      <div className="rh-order-form__field">
        <label htmlFor="order-type">Order Type</label>
        <select id="order-type" value={orderType} onChange={(e) => setOrderType(e.target.value)}>
          {ORDER_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div className="rh-order-form__field">
        <label htmlFor="order-qty">Shares</label>
        <input
          id="order-qty"
          type="number"
          min="0"
          step="1"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="0"
        />
        {maxShares !== undefined && side === "sell" && (
          <span className="rh-order-form__hint">{maxShares} shares available</span>
        )}
      </div>

      {(orderType === "limit" || orderType === "stop_limit") && (
        <div className="rh-order-form__field">
          <label htmlFor="limit-price">Limit Price</label>
          <input
            id="limit-price"
            type="number"
            min="0"
            step="0.01"
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            placeholder={currentPrice.toFixed(2)}
          />
        </div>
      )}

      {(orderType === "stop" || orderType === "stop_limit") && (
        <div className="rh-order-form__field">
          <label htmlFor="stop-price">Stop Price</label>
          <input
            id="stop-price"
            type="number"
            min="0"
            step="0.01"
            value={stopPrice}
            onChange={(e) => setStopPrice(e.target.value)}
          />
        </div>
      )}

      {orderType === "trailing_stop" && (
        <div className="rh-order-form__field">
          <label htmlFor="trail-amount">Trail Amount ($)</label>
          <input
            id="trail-amount"
            type="number"
            min="0"
            step="0.01"
            value={trailAmount}
            onChange={(e) => setTrailAmount(e.target.value)}
          />
        </div>
      )}

      <div className="rh-order-form__field">
        <label htmlFor="tif">Time in Force</label>
        <select id="tif" value={timeInForce} onChange={(e) => setTimeInForce(e.target.value)}>
          {TIF_OPTIONS.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div className="rh-order-form__field rh-order-form__field--checkbox">
        <label>
          <input
            type="checkbox"
            checked={extendedHours}
            onChange={(e) => setExtendedHours(e.target.checked)}
          />
          Extended hours
        </label>
      </div>

      <div className="rh-order-form__summary">
        <div className="rh-order-form__row">
          <span>Market Price</span>
          <span>${currentPrice.toFixed(2)}</span>
        </div>
        {qty > 0 && (
          <div className="rh-order-form__row">
            <span>Estimated {side === "buy" ? "Cost" : "Credit"}</span>
            <span>${estimatedCost.toFixed(2)}</span>
          </div>
        )}
      </div>

      {!showReview ? (
        <Button
          variant="primary"
          className={`rh-order-form__submit ${side === "buy" ? "rh-order-form__submit--buy" : "rh-order-form__submit--sell"}`}
          disabled={qty <= 0}
          onClick={() => setShowReview(true)}
          aria-label={`Review ${side} order`}
        >
          Review Order
        </Button>
      ) : (
        <div className="rh-order-form__review">
          <p>
            You are placing a {orderType.replace("_", " ")} order to {side} {qty} {qty === 1 ? "share" : "shares"} of {symbol}.
          </p>
          <div className="rh-order-form__review-actions">
            <Button variant="secondary" onClick={() => setShowReview(false)}>Edit</Button>
            <Button
              variant="primary"
              className={side === "buy" ? "rh-order-form__submit--buy" : "rh-order-form__submit--sell"}
              disabled={isSubmitting}
              onClick={handleSubmit}
              aria-label={`Confirm ${side} order`}
            >
              {isSubmitting ? "Submitting..." : `Submit ${side.charAt(0).toUpperCase() + side.slice(1)}`}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
