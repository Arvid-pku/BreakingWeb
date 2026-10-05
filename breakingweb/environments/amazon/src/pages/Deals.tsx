import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Product } from "../types";
import { useAmazonLayout } from "../context";
import { StarRating } from "../components/StarRating";
import { useFallbackImage } from "../imageFallbacks";

export function DealsPage() {
  const { api } = useAmazonLayout();
  const location = useLocation();
  const [deals, setDeals] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDeals = () => {
    setLoading(true);
    return api.getDeals()
      .then((result) => {
        const items = result?.items ?? [];
        const discounted = items.filter(
          (p) => p.list_price && p.list_price > p.price
        );
        setDeals(discounted.length > 0 ? discounted : items);
      })
      .catch(() =>
        api.getProducts({ page_size: 50 })
          .then((result) => {
            const discounted = result.items.filter(
              (p) => p.list_price && p.list_price > p.price
            );
            setDeals(discounted);
          })
          .catch(() => setDeals([]))
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDeals();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading deals...</p>
      </div>
    );
  }

  return (
    <div className="deals-page">
      <div className="deals-page__hero">
        <h1>Today's Deals</h1>
        <p>Great savings on top products</p>
      </div>

      {deals.length === 0 ? (
        <div className="deals-empty">
          <h2>No deals available</h2>
          <p>Check back later for new deals and discounts.</p>
          <button
            type="button"
            className="amazon-btn amazon-btn--add-to-cart"
            onClick={loadDeals}
            aria-label="Retry loading deals"
          >
            Retry
          </button>
        </div>
      ) : (
        <div className="deals-grid">
          {deals.map((product) => {
            const discount = product.list_price
              ? Math.round(((product.list_price - product.price) / product.list_price) * 100)
              : 0;

            return (
              <Link
                key={product.id}
                to={preserveQueryParams(`/product/${product.id}`, location.search)}
                className="deals-card"
              >
                <div className="deals-card__image">
                  {product.image_url ? (
                    <img
                      className="deals-card__product-image"
                      src={product.image_url}
                      alt={product.name}
                      loading="eager"
                      onError={(e) => useFallbackImage(e, product)}
                    />
                  ) : (
                    <div className="product-card__image-placeholder visible">
                      {product.category.charAt(0).toUpperCase()}
                    </div>
                  )}
                  {discount > 0 && (
                    <div className="deals-card__badge">-{discount}%</div>
                  )}
                </div>
                <div className="deals-card__info">
                  <h3 className="deals-card__name">{product.name}</h3>
                  <div className="deals-card__rating">
                    <StarRating rating={product.rating} reviewCount={product.review_count} size="sm" />
                  </div>
                  <div className="deals-card__pricing">
                    <span className="deals-card__sale-price">${product.price.toFixed(2)}</span>
                    {product.list_price && (
                      <span className="deals-card__original-price">${product.list_price.toFixed(2)}</span>
                    )}
                  </div>
                  {discount > 0 && (
                    <div className="deals-card__savings">
                      You save: ${((product.list_price ?? 0) - product.price).toFixed(2)} ({discount}%)
                    </div>
                  )}
                  {product.prime_eligible && (
                    <span className="product-card__prime">prime</span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
