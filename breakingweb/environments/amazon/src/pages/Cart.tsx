import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useAmazonLayout } from "../context";
import { CartItemRow } from "../components/CartItem";
import type { CartItem } from "../types";

export function CartPage() {
  const { api, cartSummary, refreshCart } = useAmazonLayout();
  const location = useLocation();
  const [loading, setLoading] = useState(!cartSummary);

  useEffect(() => {
    if (!cartSummary) {
      refreshCart().finally(() => setLoading(false));
    }
  }, [cartSummary, refreshCart]);

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading cart...</p>
      </div>
    );
  }

  const items = cartSummary?.items ?? [];
  const subtotal = cartSummary?.totals?.subtotal ?? 0;
  const itemCount = cartSummary?.item_count ?? 0;

  return (
    <div className="cart-page">
      <div className="cart-page__main">
        <div className="cart-page__header">
          <h1>Shopping Cart</h1>
          <span className="cart-page__price-label">Price</span>
        </div>

        <hr />

        {items.length === 0 ? (
          <div className="cart-empty">
            <h2>Your Amazon Cart is empty</h2>
            <p>
              Check your Wishlist for saved items, or{" "}
              <Link to={preserveQueryParams("/home", location.search)}>continue shopping</Link>.
            </p>
          </div>
        ) : (
          <div className="cart-items">
            {items.map((item) => (
              <CartItemRow key={item.id} item={item} />
            ))}
          </div>
        )}

        {items.length > 0 && (
          <div className="cart-page__subtotal-row">
            Subtotal ({itemCount} {itemCount === 1 ? "item" : "items"}):{" "}
            <strong>${subtotal.toFixed(2)}</strong>
          </div>
        )}
      </div>

      {items.length > 0 && (
        <aside className="cart-page__sidebar" aria-label="Cart summary">
          <div className="cart-summary-box">
            <div className="cart-summary-box__subtotal">
              Subtotal ({itemCount} {itemCount === 1 ? "item" : "items"}):{" "}
              <strong>${subtotal.toFixed(2)}</strong>
            </div>
            <Link
              to={preserveQueryParams("/checkout", location.search)}
              className="amazon-btn amazon-btn--add-to-cart cart-summary-box__checkout"
              aria-label="Proceed to checkout"
            >
              Proceed to checkout
            </Link>
          </div>
        </aside>
      )}
    </div>
  );
}
