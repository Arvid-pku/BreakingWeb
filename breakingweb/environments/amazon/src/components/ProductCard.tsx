import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Product } from "../types";
import { StarRating } from "./StarRating";
import { useFallbackImage } from "../imageFallbacks";

interface ProductCardProps {
  product: Product;
}

function getDeliveryDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 2);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function ProductCard({ product }: ProductCardProps) {
  const location = useLocation();
  const discount = product.list_price
    ? Math.round(((product.list_price - product.price) / product.list_price) * 100)
    : 0;
  const boughtCount = product.review_count > 1000
    ? `${Math.floor(product.review_count / 100) * 100}+`
    : null;

  return (
    <article className="product-card" aria-label={product.name}>
      <Link
        to={preserveQueryParams(`/product/${product.id}`, location.search)}
        className="product-card__link"
      >
        <div className="product-card__image">
          <img
            src={product.image_url}
            alt={product.name}
            loading="eager"
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
            onError={(e) => useFallbackImage(e, product)}
          />
          <span className="product-card__image-fallback">{product.category?.[0] ?? "P"}</span>
        </div>
        <div className="product-card__info">
          <h3 className="product-card__name">{product.name}</h3>
          <div className="product-card__brand">{product.brand}</div>
          <StarRating rating={product.rating} reviewCount={product.review_count} size="sm" />
          {boughtCount && (
            <div className="product-card__bought">{boughtCount} bought in past month</div>
          )}
          <div className="product-card__pricing">
            {discount > 0 && (
              <span className="product-card__discount">-{discount}%</span>
            )}
            <span className="product-card__price">
              <sup className="product-card__currency">$</sup>
              <span className="product-card__dollars">{Math.floor(product.price)}</span>
              <sup className="product-card__cents">
                {(product.price % 1).toFixed(2).slice(2)}
              </sup>
            </span>
            {product.list_price && (
              <span className="product-card__original-price">
                List: ${product.list_price.toFixed(2)}
              </span>
            )}
          </div>
          {product.prime_eligible && (
            <div className="prime-badge" aria-label="Prime eligible">
              <span className="prime-badge__text">prime</span>
              <span className="prime-badge__check">&#10003;</span>
            </div>
          )}
          <div className="product-card__delivery">
            FREE delivery <strong>{getDeliveryDate()}</strong>
          </div>
          {!product.in_stock && (
            <span className="product-card__out-of-stock">Currently unavailable</span>
          )}
        </div>
      </Link>
    </article>
  );
}
