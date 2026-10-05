import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { CartItem as CartItemType } from "../types";
import { useAmazonLayout } from "../context";
import { useFallbackImage } from "../imageFallbacks";

interface CartItemProps {
  item: CartItemType;
}

export function CartItemRow({ item }: CartItemProps) {
  const { api, refreshCart, notify } = useAmazonLayout();
  const location = useLocation();
  const [updating, setUpdating] = useState(false);

  const handleQuantityChange = async (newQty: number) => {
    if (newQty < 1 || updating) return;
    setUpdating(true);
    try {
      await api.updateCartItem(item.id, newQty);
      await refreshCart();
    } catch {
      notify("Error", "Failed to update quantity.");
    } finally {
      setUpdating(false);
    }
  };

  const handleRemove = async () => {
    if (updating) return;
    setUpdating(true);
    try {
      await api.removeFromCart(item.id);
      await refreshCart();
      notify("Removed", `${item.product_name} removed from cart.`);
    } catch {
      notify("Error", "Failed to remove item.");
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="cart-item" aria-label={`Cart item: ${item.product_name}`}>
      <div className="cart-item__image">
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
        ) : null}
        <div className={`cart-item__image-placeholder ${item.image_url ? "" : "visible"}`}>
          <span>{(item.product_name ?? "P")[0]}</span>
        </div>
      </div>
      <div className="cart-item__details">
        <Link
          to={preserveQueryParams(`/product/${item.product_id}`, location.search)}
          className="cart-item__name"
        >
          {item.product_name}
        </Link>
        {item.variant_name && (
          <div className="cart-item__variant">Variant: {item.variant_name}</div>
        )}
        {item.prime_eligible && (
          <span className="product-card__prime" aria-label="Prime eligible">prime</span>
        )}
        {item.in_stock === false && (
          <div className="cart-item__oos" style={{ color: "#b12704", fontSize: "0.8125rem", fontWeight: 600, marginBottom: 4 }}>
            Currently unavailable
          </div>
        )}
        <div className="cart-item__price">${(item.unit_price ?? 0).toFixed(2)}</div>
        <div className="cart-item__actions">
          <div className="cart-item__quantity">
            <label htmlFor={`qty-${item.id}`}>Qty:</label>
            <select
              id={`qty-${item.id}`}
              value={item.quantity}
              disabled={updating}
              onChange={(e) => handleQuantityChange(Number(e.target.value))}
              aria-label={`Quantity for ${item.product_name}`}
            >
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <span className="cart-item__separator">|</span>
          <button
            className="cart-item__remove"
            onClick={handleRemove}
            disabled={updating}
            aria-label={`Remove ${item.product_name} from cart`}
          >
            Delete
          </button>
        </div>
      </div>
      <div className="cart-item__total">
        <strong>${((item.unit_price ?? 0) * (item.quantity ?? 1)).toFixed(2)}</strong>
      </div>
    </div>
  );
}
