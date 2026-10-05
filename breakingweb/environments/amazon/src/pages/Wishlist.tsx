import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Product } from "../types";
import { useAmazonLayout } from "../context";
import { StarRating } from "../components/StarRating";
import { useFallbackImage } from "../imageFallbacks";

export function WishlistPage() {
  const { api, refreshCart, notify } = useAmazonLayout();
  const location = useLocation();
  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  const loadWishlist = async () => {
    try {
      const data = await api.getWishlist();
      setItems(data);
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWishlist();
  }, [api]);

  const handleAddToCart = async (item: Product) => {
    try {
      await api.addToCart(item.id, 1);
      await refreshCart();
      notify("Added to Cart", `${item.name} has been added to your cart.`);
    } catch {
      notify("Error", "Failed to add item to cart.");
    }
  };

  const handleRemove = async (item: Product) => {
    try {
      await api.removeFromWishlist(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      notify("Removed", `${item.name} removed from wishlist.`);
    } catch {
      notify("Error", "Failed to remove item.");
    }
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading wishlist...</p>
      </div>
    );
  }

  return (
    <div className="wishlist-page">
      <h1>Your Wishlist</h1>
      <p className="wishlist-page__count">{items.length} {items.length === 1 ? "item" : "items"}</p>

      {items.length === 0 ? (
        <div className="wishlist-empty">
          <h2>Your wishlist is empty</h2>
          <p>
            <Link to={preserveQueryParams("/home", location.search)}>Browse products</Link> and add items you love.
          </p>
        </div>
      ) : (
        <div className="wishlist-list">
          {items.map((item) => {
            const product = item;
            const productName = product.name || "Unknown Product";
            return (
              <article key={item.id} className="wishlist-card" aria-label={productName}>
                <div className="wishlist-card__image">
                  {product.image_url ? (
                    <img
                      src={product.image_url}
                      alt={productName}
                      style={{ width: "100%", height: "100%", objectFit: "contain" }}
                      onError={(e) => useFallbackImage(e, product)}
                    />
                  ) : (
                    <div className="cart-item__image-placeholder visible"><span>{productName[0]}</span></div>
                  )}
                </div>
                <div className="wishlist-card__info">
                  <Link
                    to={preserveQueryParams(`/product/${item.id}`, location.search)}
                    className="wishlist-card__name"
                  >
                    {productName}
                  </Link>
                  {product.brand && <div className="wishlist-card__brand">{product.brand}</div>}
                  {product.rating != null && (
                    <StarRating rating={product.rating} reviewCount={product.review_count ?? 0} size="sm" />
                  )}
                  <div className="wishlist-card__price">${(product.price ?? 0).toFixed(2)}</div>
                  {product.prime_eligible && (
                    <span className="product-card__prime">prime</span>
                  )}
                  <div className="wishlist-card__stock">
                    {product.in_stock ? (
                      <span className="product-detail__in-stock">In Stock</span>
                    ) : (
                      <span className="product-detail__out-of-stock">Currently unavailable</span>
                    )}
                  </div>
                </div>
                <div className="wishlist-card__actions">
                  {product.in_stock && (
                    <button
                      className="amazon-btn amazon-btn--add-to-cart"
                      onClick={() => handleAddToCart(item)}
                      aria-label={`Add ${productName} to cart`}
                    >
                      Add to Cart
                    </button>
                  )}
                  <button
                    className="amazon-btn amazon-btn--wishlist"
                    onClick={() => handleRemove(item)}
                    aria-label={`Remove ${productName} from wishlist`}
                  >
                    Remove
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
