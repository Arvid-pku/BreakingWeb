import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";
import { useRobinhoodLayout } from "../context";
import type { Watchlist } from "../types";

interface BuyCardProps {
  symbol: string;
  price: number;
  name: string;
}

export function BuyCard({ symbol, price, name }: BuyCardProps) {
  const location = useLocation();
  const { api, account, notify } = useRobinhoodLayout();
  const [shares, setShares] = useState("1");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [showListPicker, setShowListPicker] = useState(false);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [newWatchlistName, setNewWatchlistName] = useState("");
  const [listError, setListError] = useState("");
  const [isSavingList, setIsSavingList] = useState(false);

  const qty = parseFloat(shares) || 0;
  const estimatedCost = qty * price;
  const buyingPower = account ? parseFloat(account.buying_power) : 0;

  useEffect(() => {
    if (!showListPicker) return;
    let cancelled = false;
    api.listWatchlists()
      .then((items) => {
        if (cancelled) return;
        setWatchlists(items);
        if (!selectedWatchlistId && items.length > 0) {
          setSelectedWatchlistId(items[0].id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setListError("Unable to load your lists.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, selectedWatchlistId, showListPicker]);

  const handleSubmit = async () => {
    if (qty <= 0) return;
    setError("");
    try {
      await api.placeOrder({
        symbol,
        side,
        order_type: "market",
        quantity: qty,
      });
      setSubmitted(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Order failed");
    }
  };

  const handleSaveToList = async () => {
    setListError("");
    if (!newWatchlistName.trim() && !selectedWatchlistId) {
      setListError("Choose an existing list or create a new one.");
      return;
    }
    setIsSavingList(true);
    try {
      if (newWatchlistName.trim()) {
        await api.createWatchlist(newWatchlistName.trim(), [symbol]);
        notify("List Created", `${symbol} added to ${newWatchlistName.trim()}`);
      } else {
        const targetWatchlist = watchlists.find((watchlist) => watchlist.id === selectedWatchlistId);
        await api.addToWatchlist(selectedWatchlistId, symbol);
        notify("Added to List", `${symbol} added to ${targetWatchlist?.name ?? "selected list"}`);
      }
      setNewWatchlistName("");
      setShowListPicker(false);
    } catch (e: unknown) {
      setListError(e instanceof Error ? e.message : "Unable to update lists.");
    } finally {
      setIsSavingList(false);
    }
  };

  if (submitted) {
    return (
      <div className="rh-buy-card" aria-label={`${side} ${symbol}`}>
        <div className="rh-buy-card__success">
          <h3>Order Placed</h3>
          <p>
            Your market {side} order for {qty} share{qty !== 1 ? "s" : ""} of {symbol} has been submitted.
          </p>
          <Button variant="primary" className="rh-btn--buy" onClick={() => setSubmitted(false)}>
            Done
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="rh-buy-card" aria-label={`${side} ${symbol}`}>
      <div className="rh-buy-card__tabs">
        <button
          className={`rh-buy-card__tab ${side === "buy" ? "rh-buy-card__tab--active" : ""}`}
          onClick={() => setSide("buy")}
        >
          Buy {symbol}
        </button>
        <button
          className={`rh-buy-card__tab ${side === "sell" ? "rh-buy-card__tab--active rh-buy-card__tab--sell" : ""}`}
          onClick={() => setSide("sell")}
        >
          Sell {symbol}
        </button>
      </div>

      <div className="rh-buy-card__field">
        <label>Shares</label>
        <input
          type="number"
          min="0"
          step="1"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          aria-label="Number of shares"
        />
      </div>

      <div className="rh-buy-card__field">
        <label>Market Price</label>
        <span className="rh-buy-card__price">${price.toFixed(2)}</span>
      </div>

      <div className="rh-buy-card__divider" />

      <div className="rh-buy-card__estimate">
        <span>Estimated {side === "buy" ? "Cost" : "Credit"}</span>
        <span>${estimatedCost.toFixed(2)}</span>
      </div>

      {error && <p className="rh-buy-card__error">{error}</p>}

      <Button
        variant="primary"
        className={`rh-buy-card__submit ${side === "buy" ? "rh-btn--buy" : "rh-order-form__submit--sell"}`}
        onClick={handleSubmit}
        aria-label={`${side === "buy" ? "Buy" : "Sell"} ${symbol}`}
      >
        {side === "buy" ? "Buy" : "Sell"}
      </Button>

      <div className="rh-buy-card__buying-power">
        ${buyingPower.toLocaleString("en-US", { minimumFractionDigits: 2 })} buying power available
      </div>

      <div className="rh-buy-card__actions">
        <Link to={preserveQueryParams(`/stocks/${symbol}/trade`, location.search)}>
          <Button variant="secondary" className="rh-buy-card__advanced" aria-label={`Advanced trade ${symbol}`}>
            More Options
          </Button>
        </Link>
        <Link to={preserveQueryParams(`/stocks/${symbol}/options`, location.search)}>
          <Button
            variant="secondary"
            className="rh-buy-card__advanced"
            aria-label={`Trade options on ${symbol}`}
            data-testid={`buy-card-trade-options-${symbol}`}
          >
            Trade Options
          </Button>
        </Link>
        <Link to={preserveQueryParams(`/alerts?symbol=${encodeURIComponent(symbol)}`, location.search)}>
          <Button variant="secondary" className="rh-buy-card__advanced" aria-label={`Set alert for ${symbol}`}>
            Set Alert
          </Button>
        </Link>
      </div>

      <Button
        variant="secondary"
        className="rh-buy-card__add-list"
        aria-label={`Add ${name} to lists`}
        onClick={() => {
          setListError("");
          setShowListPicker((current) => !current);
        }}
      >
        Add to Lists
      </Button>

      {showListPicker ? (
        <div className="rh-buy-card__list-picker" aria-label={`Add ${symbol} to a watchlist`}>
          {watchlists.length > 0 ? (
            <div className="rh-order-form__field">
              <label htmlFor={`buy-card-list-${symbol}`}>Existing List</label>
              <select
                id={`buy-card-list-${symbol}`}
                value={selectedWatchlistId}
                onChange={(e) => setSelectedWatchlistId(e.target.value)}
              >
                {watchlists.map((watchlist) => (
                  <option key={watchlist.id} value={watchlist.id}>
                    {watchlist.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          <div className="rh-order-form__field">
            <label htmlFor={`buy-card-new-list-${symbol}`}>New List</label>
            <input
              id={`buy-card-new-list-${symbol}`}
              value={newWatchlistName}
              onChange={(e) => setNewWatchlistName(e.target.value)}
              placeholder="Create a new list"
            />
          </div>

          {listError ? <p className="rh-buy-card__error">{listError}</p> : null}

          <div className="rh-buy-card__list-actions">
            <Button variant="secondary" onClick={() => setShowListPicker(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={isSavingList} onClick={handleSaveToList}>
              {isSavingList ? "Saving..." : "Save to List"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
