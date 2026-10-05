import { useEffect, useRef, useState, useCallback } from "react";
import { Link, useSearchParams, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import { useBookingLayout } from "../context";
import type { PropertyBrief, SearchResults as SearchResultsType } from "../types";

/* ---------- helpers ---------- */

function stars(n: number): string {
  return "\u2605".repeat(n);
}

function scoreLabel(score: number): string {
  if (score >= 9) return "Wonderful";
  if (score >= 8) return "Very Good";
  if (score >= 7) return "Good";
  if (score >= 6) return "Pleasant";
  return "Review score";
}

function formatCurrency(amount: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/* ---------- constants ---------- */

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "popularity", label: "Popularity" },
  { value: "price_low", label: "Price (low to high)" },
  { value: "price_high", label: "Price (high to low)" },
  { value: "rating", label: "Rating" },
  { value: "stars", label: "Stars" },
  { value: "distance", label: "Distance" },
];

const STAR_RATINGS = [5, 4, 3, 2, 1];

const PROPERTY_TYPES = [
  "Hotel",
  "Apartment",
  "Resort",
  "Villa",
  "Hostel",
  "Guest House",
  "B&B",
];

const AMENITIES_LIST = [
  "Free WiFi",
  "Parking",
  "Pool",
  "Spa",
  "Fitness Center",
  "Restaurant",
  "Airport Shuttle",
  "Air Conditioning",
  "Pet Friendly",
];

const MEAL_OPTIONS = [
  { value: "", label: "Any" },
  { value: "breakfast", label: "Breakfast included" },
  { value: "half_board", label: "Half board" },
  { value: "full_board", label: "Full board" },
  { value: "all_inclusive", label: "All inclusive" },
];

const PAGE_SIZE = 10;

/* ---------- component ---------- */

export default function SearchResults() {
  const { sessionId, api } = useBookingLayout();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const qp = (to: string) => preserveQueryParams(to, location.search);

  /* --- read URL params --- */
  const destination = searchParams.get("destination") || "";
  const checkIn = searchParams.get("check_in") || "";
  const checkOut = searchParams.get("check_out") || "";
  const guestsParam = searchParams.get("guests");
  const guests = guestsParam ? Number(guestsParam) : undefined;
  const currentPage = Number(searchParams.get("page") || "1");
  const sortBy = searchParams.get("sort_by") || "popularity";

  /* --- local filter state (applied on change) --- */
  const [minPrice, setMinPrice] = useState<string>(searchParams.get("min_price") || "");
  const [maxPrice, setMaxPrice] = useState<string>(searchParams.get("max_price") || "");
  const [starFilter, setStarFilter] = useState<number[]>(() => {
    const s = searchParams.get("star_rating");
    return s ? s.split(",").map(Number).filter(Boolean) : [];
  });
  const [minRating, setMinRating] = useState<string>(searchParams.get("min_rating") || "");
  const [propertyType, setPropertyType] = useState<string>(searchParams.get("property_type") || "");
  const [amenities, setAmenities] = useState<string[]>(() => {
    const a = searchParams.get("amenities");
    return a ? a.split(",") : [];
  });
  const [freeCancellation, setFreeCancellation] = useState(searchParams.get("free_cancellation") === "true");
  const [mealsIncluded, setMealsIncluded] = useState<string>(searchParams.get("meals_included") || "");
  const [nameFilter, setNameFilter] = useState("");

  /* --- data state --- */
  const [results, setResults] = useState<SearchResultsType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* --- debounced name filter --- */
  const [debouncedName, setDebouncedName] = useState(nameFilter);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedName(nameFilter), 350);
    return () => clearTimeout(timer);
  }, [nameFilter]);
  // Reset to page 1 when the debounced name filter actually changes — otherwise
  // typing a name on page>1 can yield "No properties found" even when total>0.
  // Skip first render so navigating directly to ?page=2 with no name filter is preserved.
  const prevDebouncedNameRef = useRef(debouncedName);
  useEffect(() => {
    if (prevDebouncedNameRef.current === debouncedName) return;
    prevDebouncedNameRef.current = debouncedName;
    if (Number(searchParams.get("page") || "1") !== 1) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("page", "1");
        return next;
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedName]);

  /* --- fetch data --- */
  const fetchResults = useCallback(
    async (page: number) => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.searchProperties({
          destination: destination || undefined,
          name: debouncedName || undefined,
          check_in: checkIn || undefined,
          check_out: checkOut || undefined,
          guests,
          min_price: minPrice ? Number(minPrice) : undefined,
          max_price: maxPrice ? Number(maxPrice) : undefined,
          min_rating: minRating ? Number(minRating) : undefined,
          star_ratings: starFilter.length > 0 ? starFilter : undefined,
          property_type: propertyType || undefined,
          amenities: amenities.length > 0 ? amenities : undefined,
          free_cancellation: freeCancellation || undefined,
          meals_included: mealsIncluded || undefined,
          sort_by: sortBy || undefined,
          page,
          page_size: PAGE_SIZE,
        });
        setResults(data);
      } catch {
        setError("Failed to load search results. Please try again.");
      } finally {
        setLoading(false);
      }
    },
    [
      api,
      sessionId,
      destination,
      debouncedName,
      checkIn,
      checkOut,
      guests,
      minPrice,
      maxPrice,
      minRating,
      starFilter,
      propertyType,
      amenities,
      freeCancellation,
      mealsIncluded,
      sortBy,
    ],
  );

  useEffect(() => {
    fetchResults(currentPage);
  }, [fetchResults, currentPage]);

  /* --- param helpers --- */
  function updateParam(key: string, value: string | undefined) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      // reset to page 1 on filter change
      if (key !== "page") next.set("page", "1");
      return next;
    });
  }

  function handleSortChange(value: string) {
    updateParam("sort_by", value);
  }

  function handlePageChange(page: number) {
    updateParam("page", String(page));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* --- filter apply helpers --- */
  function handleStarToggle(star: number) {
    setStarFilter((prev) => {
      const next = prev.includes(star) ? prev.filter((s) => s !== star) : [...prev, star];
      updateParam("star_rating", next.length > 0 ? next.sort((a, b) => b - a).join(",") : undefined);
      return next;
    });
  }

  function handleAmenityToggle(amenity: string) {
    setAmenities((prev) => {
      const next = prev.includes(amenity) ? prev.filter((a) => a !== amenity) : [...prev, amenity];
      updateParam("amenities", next.length > 0 ? next.join(",") : undefined);
      return next;
    });
  }

  function handleFreeCancellationToggle() {
    const next = !freeCancellation;
    setFreeCancellation(next);
    updateParam("free_cancellation", next ? "true" : undefined);
  }

  function handleMealsChange(value: string) {
    setMealsIncluded(value);
    updateParam("meals_included", value || undefined);
  }

  function handlePriceApply() {
    updateParam("min_price", minPrice || undefined);
    updateParam("max_price", maxPrice || undefined);
  }

  function handleMinRatingApply() {
    updateParam("min_rating", minRating || undefined);
  }

  function handlePropertyTypeChange(value: string) {
    setPropertyType(value);
    updateParam("property_type", value || undefined);
  }

  /* --- render --- */
  const properties = results?.results ?? [];
  const totalResults = results?.total ?? 0;
  const totalPages = results?.total_pages ?? 0;

  return (
    <div className="bk-search-layout">
      {/* ============ SIDEBAR FILTERS ============ */}
      <aside className="bk-filters" aria-label="Search filters">
        {/* Destination summary */}
        {destination && (
          <div className="bk-filter-group">
            <h3>Searching: {destination}</h3>
            {checkIn && checkOut && (
              <p style={{ fontSize: 12, color: "var(--bk-gray-600)", marginTop: 4 }}>
                {new Date(checkIn).toLocaleDateString()} &ndash; {new Date(checkOut).toLocaleDateString()}
              </p>
            )}
            {guests && (
              <p style={{ fontSize: 12, color: "var(--bk-gray-600)", marginTop: 2 }}>
                {guests} {guests === 1 ? "guest" : "guests"}
              </p>
            )}
          </div>
        )}

        {/* Property name search */}
        <div className="bk-filter-group">
          <h3>Search by property name</h3>
          <input
            type="text"
            className="bk-input"
            placeholder="e.g. Kensington Hotel"
            value={nameFilter}
            onChange={(e) => setNameFilter(e.target.value)}
            aria-label="Filter by property name"
          />
        </div>

        {/* Price range */}
        <div className="bk-filter-group">
          <h3>Your budget (per night)</h3>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="number"
              className="bk-input"
              placeholder="Min"
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value)}
              onBlur={handlePriceApply}
              onKeyDown={(e) => e.key === "Enter" && handlePriceApply()}
              aria-label="Minimum price"
              style={{ width: "45%" }}
              min={0}
            />
            <span style={{ color: "var(--bk-gray-300)" }}>&ndash;</span>
            <input
              type="number"
              className="bk-input"
              placeholder="Max"
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
              onBlur={handlePriceApply}
              onKeyDown={(e) => e.key === "Enter" && handlePriceApply()}
              aria-label="Maximum price"
              style={{ width: "45%" }}
              min={0}
            />
          </div>
        </div>

        {/* Star rating */}
        <div className="bk-filter-group">
          <h3>Star rating</h3>
          {STAR_RATINGS.map((s) => (
            <label key={s} className="bk-filter-option">
              <input
                type="checkbox"
                checked={starFilter.includes(s)}
                onChange={() => handleStarToggle(s)}
              />
              <span className="bk-stars">{stars(s)}</span>
              <span>{s} star{s !== 1 ? "s" : ""}</span>
            </label>
          ))}
        </div>

        {/* Review score */}
        <div className="bk-filter-group">
          <h3>Review score</h3>
          {[9, 8, 7, 6].map((score) => (
            <label key={score} className="bk-filter-option">
              <input
                type="radio"
                name="min_rating"
                checked={minRating === String(score)}
                onChange={() => {
                  setMinRating(String(score));
                  updateParam("min_rating", String(score));
                }}
              />
              <span>{scoreLabel(score)} {score}+</span>
            </label>
          ))}
          <label className="bk-filter-option">
            <input
              type="radio"
              name="min_rating"
              checked={!minRating}
              onChange={() => {
                setMinRating("");
                updateParam("min_rating", undefined);
              }}
            />
            <span>Any</span>
          </label>
        </div>

        {/* Property type */}
        <div className="bk-filter-group">
          <h3>Property type</h3>
          <label className="bk-filter-option">
            <input
              type="radio"
              name="property_type"
              checked={!propertyType}
              onChange={() => handlePropertyTypeChange("")}
            />
            <span>Any type</span>
          </label>
          {PROPERTY_TYPES.map((pt) => (
            <label key={pt} className="bk-filter-option">
              <input
                type="radio"
                name="property_type"
                checked={propertyType === pt}
                onChange={() => handlePropertyTypeChange(pt)}
              />
              <span>{pt}</span>
            </label>
          ))}
        </div>

        {/* Amenities */}
        <div className="bk-filter-group">
          <h3>Amenities</h3>
          {AMENITIES_LIST.map((am) => (
            <label key={am} className="bk-filter-option">
              <input
                type="checkbox"
                checked={amenities.includes(am)}
                onChange={() => handleAmenityToggle(am)}
              />
              <span>{am}</span>
            </label>
          ))}
        </div>

        {/* Free cancellation */}
        <div className="bk-filter-group">
          <h3>Cancellation</h3>
          <label className="bk-filter-option">
            <input
              type="checkbox"
              checked={freeCancellation}
              onChange={handleFreeCancellationToggle}
            />
            <span>Free cancellation</span>
          </label>
        </div>

        {/* Meals included */}
        <div className="bk-filter-group">
          <h3>Meals</h3>
          {MEAL_OPTIONS.map((opt) => (
            <label key={opt.value} className="bk-filter-option">
              <input
                type="radio"
                name="meals_included"
                checked={mealsIncluded === opt.value}
                onChange={() => handleMealsChange(opt.value)}
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </div>
      </aside>

      {/* ============ RESULTS AREA ============ */}
      <div className="bk-search-results">
        {/* Result count */}
        <div className="bk-result-count">
          {destination ? `${destination}: ` : ""}
          {totalResults.toLocaleString()} {totalResults === 1 ? "property" : "properties"} found
        </div>

        {/* Sort bar */}
        <div className="bk-sort-bar" role="group" aria-label="Sort results">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`bk-sort-btn ${sortBy === opt.value ? "active" : ""}`}
              onClick={() => handleSortChange(opt.value)}
              aria-pressed={sortBy === opt.value}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && <div className="bk-loading">Searching...</div>}

        {/* Error */}
        {error && (
          <div className="bk-empty">
            <h3>Something went wrong</h3>
            <p>{error}</p>
            <button
              className="bk-btn bk-btn--primary"
              style={{ marginTop: 12 }}
              onClick={() => fetchResults(currentPage)}
            >
              Try again
            </button>
          </div>
        )}

        {/* Empty */}
        {!loading && !error && properties.length === 0 && (
          <div className="bk-empty">
            <h3>No properties found</h3>
            <p>Try adjusting your search or filters to find available properties.</p>
            <Link to={qp("/home")} className="bk-btn bk-btn--primary" style={{ marginTop: 12 }}>
              Back to home
            </Link>
          </div>
        )}

        {/* Property cards */}
        {!loading && !error && properties.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {properties.map((prop) => (
              <PropertyCard key={prop.id} property={prop} qp={qp} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {!loading && totalPages > 1 && (
          <nav className="bk-pagination" aria-label="Search results pages">
            <button
              className="bk-page-btn"
              disabled={currentPage <= 1}
              onClick={() => handlePageChange(currentPage - 1)}
              aria-label="Previous page"
            >
              &laquo; Prev
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => {
                // Show first, last, and pages near current
                if (p === 1 || p === totalPages) return true;
                if (Math.abs(p - currentPage) <= 2) return true;
                return false;
              })
              .reduce<(number | "ellipsis")[]>((acc, p, idx, arr) => {
                if (idx > 0 && typeof arr[idx - 1] === "number" && p - (arr[idx - 1] as number) > 1) {
                  acc.push("ellipsis");
                }
                acc.push(p);
                return acc;
              }, [])
              .map((item, idx) =>
                item === "ellipsis" ? (
                  <span
                    key={`ellipsis-${idx}`}
                    style={{ padding: "8px 6px", color: "var(--bk-gray-300)" }}
                  >
                    ...
                  </span>
                ) : (
                  <button
                    key={item}
                    className={`bk-page-btn ${currentPage === item ? "active" : ""}`}
                    onClick={() => handlePageChange(item as number)}
                    aria-label={`Page ${item}`}
                    aria-current={currentPage === item ? "page" : undefined}
                  >
                    {item}
                  </button>
                ),
              )}
            <button
              className="bk-page-btn"
              disabled={currentPage >= totalPages}
              onClick={() => handlePageChange(currentPage + 1)}
              aria-label="Next page"
            >
              Next &raquo;
            </button>
          </nav>
        )}
      </div>
    </div>
  );
}

/* ---------- Property Card ---------- */

function PropertyCard({
  property: prop,
  qp,
}: {
  property: PropertyBrief;
  qp: (to: string) => string;
}) {
  return (
    <Link
      to={qp(`/property/${prop.id}`)}
      style={{ textDecoration: "none", color: "inherit" }}
      aria-label={`View ${prop.name}`}
    >
      <div className="bk-card bk-card-horizontal">
        {/* Image */}
        <div className="bk-card-image">
          {prop.images?.[0] ? (
            <img
              src={prop.images[0]}
              alt={prop.name}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : (
            <span aria-hidden="true">&#128246;</span>
          )}
        </div>

        {/* Details */}
        <div className="bk-card-body">
          {/* Name + stars */}
          <div>
            <span style={{ fontWeight: 700, fontSize: 16 }}>{prop.name}</span>
            {prop.star_rating > 0 && (
              <span className="bk-stars" style={{ marginLeft: 8 }}>{stars(prop.star_rating)}</span>
            )}
          </div>

          {/* Location */}
          <div style={{ fontSize: 12, color: "var(--bk-blue-light)" }}>
            {prop.neighborhood ? `${prop.neighborhood}, ` : ""}
            {prop.city}, {prop.country}
            <span style={{ color: "var(--bk-gray-600)", marginLeft: 8 }}>
              {prop.distance_from_center_km.toFixed(1)} km from center
            </span>
          </div>

          {/* Review score */}
          <div className="bk-score" style={{ marginTop: 4 }}>
            <span className="bk-score-badge">{prop.review_score.toFixed(1)}</span>
            <span className="bk-score-label">{prop.review_score_label || scoreLabel(prop.review_score)}</span>
            <span className="bk-score-count">{prop.review_count.toLocaleString()} reviews</span>
          </div>

          {/* Popular facilities */}
          {prop.popular_facilities.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
              {prop.popular_facilities.slice(0, 5).map((f) => (
                <span key={f} className="bk-facility-tag">{f}</span>
              ))}
            </div>
          )}

          {/* Badges row */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {prop.is_genius_property && (
              <span className="bk-badge bk-badge--genius">
                Genius
                {prop.genius_discount_pct > 0 && <> &ndash; {prop.genius_discount_pct}% off</>}
              </span>
            )}
            {prop.free_cancellation && (
              <span className="bk-badge bk-badge--green">Free cancellation</span>
            )}
            {prop.breakfast_included && (
              <span className="bk-badge bk-badge--green">Breakfast included</span>
            )}
          </div>
        </div>

        {/* Pricing */}
        <div className="bk-card-pricing">
          <div style={{ textAlign: "right" }}>
            {prop.property_type && (
              <div style={{ fontSize: 12, color: "var(--bk-gray-600)", marginBottom: 4 }}>
                {prop.property_type}
              </div>
            )}
          </div>

          <div style={{ textAlign: "right" }}>
            {prop.original_price_from != null &&
              prop.price_from != null &&
              prop.original_price_from > prop.price_from && (
                <div className="bk-price-original">
                  {formatCurrency(prop.original_price_from, prop.currency)}
                </div>
              )}
            {prop.price_from != null ? (
              <div className="bk-price">{formatCurrency(prop.price_from, prop.currency)}</div>
            ) : (
              <div className="bk-price" style={{ fontSize: 14, color: "var(--bk-gray-600)" }}>
                Price unavailable
              </div>
            )}
            <div className="bk-price-note">per night</div>

            {prop.rooms_available != null && prop.rooms_available > 0 && prop.rooms_available <= 5 && (
              <div style={{ marginTop: 8 }}>
                <span className="bk-badge bk-badge--red">
                  Only {prop.rooms_available} {prop.rooms_available === 1 ? "room" : "rooms"} left!
                </span>
              </div>
            )}

            <button
              className="bk-btn bk-btn--primary bk-btn--sm"
              style={{ marginTop: 8, width: "100%" }}
              tabIndex={-1}
            >
              See availability
            </button>
          </div>
        </div>
      </div>
    </Link>
  );
}
