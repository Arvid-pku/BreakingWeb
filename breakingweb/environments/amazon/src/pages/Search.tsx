import { useEffect, useState } from "react";
import { useLocation, useSearchParams, Link } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Product, SearchResult } from "../types";
import { useAmazonLayout } from "../context";
import { StarRating } from "../components/StarRating";
import { useFallbackImage } from "../imageFallbacks";

const SORT_OPTIONS = [
  { value: "relevance", label: "Featured" },
  { value: "price_low", label: "Price: Low to High" },
  { value: "price_high", label: "Price: High to Low" },
  { value: "rating", label: "Avg. Customer Review" },
  { value: "review_count", label: "Most Reviewed" },
];

const PRICE_RANGES = [
  { label: "Under $25", min: 0, max: 25 },
  { label: "$25 to $50", min: 25, max: 50 },
  { label: "$50 to $100", min: 50, max: 100 },
  { label: "$100 to $200", min: 100, max: 200 },
  { label: "$200 & above", min: 200, max: undefined },
];

const RATING_FILTERS = [4, 3, 2, 1];

function getDeliveryDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 2);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function SearchResultItem({ product }: { product: Product }) {
  const location = useLocation();
  const discount = product.list_price
    ? Math.round(((product.list_price - product.price) / product.list_price) * 100)
    : 0;
  const boughtCount = product.review_count > 1000 ? `${Math.floor(product.review_count / 100) * 100}+` : null;
  const dollars = Math.floor(product.price);
  const cents = (product.price % 1).toFixed(2).slice(2);

  return (
    <article className="search-result-item" aria-label={product.name} data-product-id={product.id}>
      <div className="search-result-item__image">
        <Link to={preserveQueryParams(`/product/${product.id}`, location.search)} aria-label={`Open ${product.name}`} data-product-id={product.id}>
          <img
            src={product.image_url}
            alt={product.name}
            loading="eager"
            onError={(e) => useFallbackImage(e, product)}
          />
        </Link>
      </div>
      <div className="search-result-item__details">
        <div className="search-result-item__title">
          <Link to={preserveQueryParams(`/product/${product.id}`, location.search)} aria-label={`Open ${product.name} product page`} data-product-id={product.id}>
            {product.name}
          </Link>
        </div>
        {product.brand && (
          <div className="search-result-item__brand">by {product.brand}</div>
        )}
        <div className="search-result-item__rating">
          <StarRating rating={product.rating} reviewCount={product.review_count} size="sm" />
        </div>
        {boughtCount && (
          <div className="search-result-item__bought">{boughtCount} bought in past month</div>
        )}
        <div className="search-result-item__price-section">
          {discount > 0 && (
            <span className="search-result-item__discount">-{discount}%</span>
          )}
          <span className="search-result-item__price">
            <sup>$</sup>
            <span className="price-whole">{dollars}</span>
            <sup className="price-fraction">{cents}</sup>
          </span>
          {product.list_price && (
            <span className="search-result-item__list-price">
              List: ${product.list_price.toFixed(2)}
            </span>
          )}
        </div>
        {product.prime_eligible && (
          <div className="search-result-item__prime">
            <span className="search-result-item__prime-badge">prime</span>
            <span className="prime-badge__check">&#10003;</span>
          </div>
        )}
        <div className="search-result-item__delivery">
          FREE delivery <strong>{getDeliveryDate()}</strong>
        </div>
        {!product.in_stock && (
          <div className="search-result-item__oos">Currently unavailable</div>
        )}
      </div>
    </article>
  );
}

export function SearchPage() {
  const { api } = useAmazonLayout();
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const query = searchParams.get("q") ?? "";
  const category = searchParams.get("category") ?? "";
  const sort = searchParams.get("sort") ?? "relevance";
  const minPrice = searchParams.get("min_price") ?? "";
  const maxPrice = searchParams.get("max_price") ?? "";
  const minRating = searchParams.get("min_rating") ?? "";
  const page = Number(searchParams.get("page") ?? "1");

  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(() => {});
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const params: Record<string, unknown> = {
      page,
      page_size: 12,
      sort_by: sort,
    };
    if (category) params.category = category;
    if (minPrice) params.min_price = Number(minPrice);
    if (maxPrice) params.max_price = Number(maxPrice);
    if (minRating) params.min_rating = Number(minRating);

    const fetcher = query
      ? api.searchProducts(query, params)
      : api.getProducts(params);

    fetcher
      .then((result) => {
        if (!cancelled) setResults(result);
      })
      .catch(() => {
        if (!cancelled) setResults({ items: [], page: 1, total: 0, page_size: 12, pages: 0 });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [api, query, category, sort, minPrice, maxPrice, minRating, page]);

  const updateFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    // Reset to page 1 when changing filters, but not when changing page itself
    if (key !== "page") {
      next.set("page", "1");
    }
    // Preserve session
    const session = searchParams.get("session");
    if (session) next.set("session", session);
    setSearchParams(next);
  };

  return (
    <div className="search-page">
      {/* Sidebar filters */}
      <aside className="search-filters" aria-label="Search filters">
        {/* Category filter */}
        <div className="search-filter-group">
          <h3 className="search-filter-group__title">Department</h3>
          <ul className="search-filter-group__list">
            <li>
              <button
                className={`search-filter__btn ${!category ? "search-filter__btn--active" : ""}`}
                onClick={() => updateFilter("category", "")}
              >
                All Departments
              </button>
            </li>
            {categories.map((cat) => (
              <li key={cat}>
                <button
                  className={`search-filter__btn ${category === cat ? "search-filter__btn--active" : ""}`}
                  onClick={() => updateFilter("category", cat)}
                >
                  {cat}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Rating filter */}
        <div className="search-filter-group">
          <h3 className="search-filter-group__title">Customer Review</h3>
          <ul className="search-filter-group__list">
            {RATING_FILTERS.map((r) => (
              <li key={r}>
                <button
                  className={`search-filter__btn ${minRating === String(r) ? "search-filter__btn--active" : ""}`}
                  onClick={() => updateFilter("min_rating", minRating === String(r) ? "" : String(r))}
                  aria-label={`${r} stars and up`}
                >
                  {"★".repeat(r)}{"☆".repeat(5 - r)} & Up
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Price filter */}
        <div className="search-filter-group">
          <h3 className="search-filter-group__title">Price</h3>
          <ul className="search-filter-group__list">
            {PRICE_RANGES.map((range) => {
              const isActive =
                minPrice === String(range.min) &&
                (range.max === undefined ? !maxPrice : maxPrice === String(range.max));
              return (
                <li key={range.label}>
                  <button
                    className={`search-filter__btn ${isActive ? "search-filter__btn--active" : ""}`}
                    onClick={() => {
                      if (isActive) {
                        const next = new URLSearchParams(searchParams);
                        next.delete("min_price");
                        next.delete("max_price");
                        next.set("page", "1");
                        const session = searchParams.get("session");
                        if (session) next.set("session", session);
                        setSearchParams(next);
                      } else {
                        const next = new URLSearchParams(searchParams);
                        next.set("min_price", String(range.min));
                        if (range.max !== undefined) {
                          next.set("max_price", String(range.max));
                        } else {
                          next.delete("max_price");
                        }
                        next.set("page", "1");
                        const session = searchParams.get("session");
                        if (session) next.set("session", session);
                        setSearchParams(next);
                      }
                    }}
                  >
                    {range.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </aside>

      {/* Results area */}
      <div className="search-results">
        <div className="search-results__header">
          <div className="search-results__count">
            {loading ? (
              "Searching..."
            ) : results ? (
              <>
                {results.total > 0
                  ? `1-${Math.min(results.page * results.page_size, results.total)} of ${results.total} results`
                  : "No results found"}
                {query && ` for "${query}"`}
              </>
            ) : null}
          </div>
          <div className="search-results__sort">
            <label htmlFor="sort-select">Sort by: </label>
            <select
              id="sort-select"
              value={sort}
              onChange={(e) => updateFilter("sort", e.target.value)}
              aria-label="Sort results"
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>

        {loading && (
          <div className="amazon-loading">
            <div className="amazon-spinner" />
            <p>Loading results...</p>
          </div>
        )}

        {!loading && results && results.items.length > 0 && (
          <>
            <div className="search-results__list">
              {results.items.map((product) => (
                <SearchResultItem key={product.id} product={product} />
              ))}
            </div>

            {/* Pagination */}
            {results.pages > 1 && (
              <nav className="search-pagination" aria-label="Search results pagination">
                <button
                  className="search-pagination__btn"
                  disabled={page <= 1}
                  onClick={() => updateFilter("page", String(page - 1))}
                >
                  Previous
                </button>
                <span className="search-pagination__info">
                  Page {results.page} of {results.pages}
                </span>
                <button
                  className="search-pagination__btn"
                  disabled={page >= results.pages}
                  onClick={() => updateFilter("page", String(page + 1))}
                >
                  Next
                </button>
              </nav>
            )}
          </>
        )}

        {!loading && results && results.items.length === 0 && (
          <div className="search-empty">
            <h2>No results found</h2>
            <p>Try checking your spelling or use more general terms.</p>
          </div>
        )}
      </div>
    </div>
  );
}
