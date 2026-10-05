import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { Stock, Watchlist } from "../types";

export function WatchlistDetailPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { api, notify } = useRobinhoodLayout();
  const [watchlist, setWatchlist] = useState<Watchlist | null>(null);
  const [stocks, setStocks] = useState<Record<string, Stock>>({});
  const [loading, setLoading] = useState(true);
  const [addSymbol, setAddSymbol] = useState("");

  const load = async () => {
    if (!id) return;
    try {
      const wls = await api.listWatchlists();
      const wl = wls.find((w) => w.id === id);
      if (!wl) { setLoading(false); return; }
      setWatchlist(wl);
      const stockMap: Record<string, Stock> = {};
      await Promise.all(
        wl.symbols.map(async (sym) => {
          try {
            stockMap[sym] = await api.getStock(sym);
          } catch { /* skip */ }
        }),
      );
      setStocks(stockMap);
    } catch { /* skip */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [api, id]);

  if (loading) return <div className="rh-loading">Loading...</div>;
  if (!watchlist) return <div className="rh-empty">Watchlist not found</div>;

  const handleAdd = async () => {
    if (!addSymbol.trim() || !id) return;
    try {
      await api.addToWatchlist(id, addSymbol.trim().toUpperCase());
      setAddSymbol("");
      notify("Added", `${addSymbol.toUpperCase()} added to ${watchlist.name}`);
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to add symbol");
    }
  };

  const handleRemove = async (sym: string) => {
    if (!id) return;
    try {
      await api.removeFromWatchlist(id, sym);
      notify("Removed", `${sym} removed from ${watchlist.name}`);
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to remove symbol");
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    try {
      await api.deleteWatchlist(id);
      notify("Deleted", `${watchlist.name} deleted`);
      navigate(preserveQueryParams("/lists", location.search));
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to delete list");
    }
  };

  return (
    <div className="rh-watchlist-detail" aria-label={`Watchlist: ${watchlist.name}`}>
      <div className="rh-page-header">
        <h1>{watchlist.name}</h1>
        <Button variant="secondary" onClick={handleDelete} aria-label="Delete watchlist">Delete List</Button>
      </div>

      <div className="rh-watchlist-detail__add">
        <input
          type="text"
          value={addSymbol}
          onChange={(e) => setAddSymbol(e.target.value)}
          placeholder="Add symbol (e.g. AAPL)"
          aria-label="Add symbol to watchlist"
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <Button variant="primary" onClick={handleAdd}>Add</Button>
      </div>

      {watchlist.symbols.length === 0 ? (
        <div className="rh-empty">No symbols in this list</div>
      ) : (
        <div className="rh-watchlist-detail__list">
          {watchlist.symbols.map((sym) => {
            const stock = stocks[sym];
            const price = stock ? parseFloat(stock.price) : 0;
            const changePct = stock ? parseFloat(stock.day_change_pct) : 0;
            const isPositive = changePct >= 0;
            return (
              <div key={sym} className="rh-watchlist-detail__row">
                <Link
                  to={preserveQueryParams(`/stocks/${sym}`, location.search)}
                  className="rh-watchlist-detail__stock"
                >
                  <span className="rh-watchlist-detail__symbol">{sym}</span>
                  <span className="rh-watchlist-detail__name">{stock?.name ?? sym}</span>
                </Link>
                <span className="rh-watchlist-detail__price">${price.toFixed(2)}</span>
                <span className={`rh-watchlist-detail__change ${isPositive ? "rh-gain" : "rh-loss"}`}>
                  {isPositive ? "+" : ""}{changePct.toFixed(2)}%
                </span>
                <button
                  className="rh-watchlist-detail__remove"
                  onClick={() => handleRemove(sym)}
                  aria-label={`Remove ${sym}`}
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
