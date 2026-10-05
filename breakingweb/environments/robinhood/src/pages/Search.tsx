import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { SearchBar, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { Stock } from "../types";

export function SearchPage() {
  const { api } = useRobinhoodLayout();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [results, setResults] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setResults([]);
        return;
      }
      setLoading(true);
      try {
        const items = await api.searchStocks(q.trim());
        setResults(items);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    const q = searchParams.get("q") ?? "";
    setQuery(q);
    void doSearch(q);
  }, [searchParams, doSearch]);

  const handleSubmit = () => {
    const params = new URLSearchParams(searchParams);
    params.set("q", query);
    setSearchParams(params);
  };

  return (
    <div className="rh-search-page" aria-label="Stock search">
      <div className="rh-search-page__input">
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={handleSubmit}
          placeholder="Search stocks by name or symbol"
          ariaLabel="Search stocks"
        />
      </div>

      {loading && <div className="rh-loading">Searching...</div>}

      {!loading && results.length === 0 && query.trim() && (
        <div className="rh-empty">No stocks found for "{query}"</div>
      )}

      <div className="rh-search-page__results">
        {results.map((stock) => {
          const price = parseFloat(stock.price);
          const changePct = parseFloat(stock.day_change_pct);
          const isPositive = changePct >= 0;
          return (
            <Link
              key={stock.symbol}
              to={preserveQueryParams(`/stocks/${stock.symbol}`, location.search)}
              className="rh-search-page__result"
            >
              <div className="rh-search-page__result-info">
                <span className="rh-search-page__symbol">{stock.symbol}</span>
                <span className="rh-search-page__name">{stock.name}</span>
              </div>
              <div className="rh-search-page__result-price">
                <span>${price.toFixed(2)}</span>
                <span className={isPositive ? "rh-gain" : "rh-loss"}>
                  {isPositive ? "+" : ""}{changePct.toFixed(2)}%
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
