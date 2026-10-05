import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useRobinhoodLayout } from "../context";
import type { Position, Stock } from "../types";
import { StockChart } from "../components/StockChart";
import { BuyCard } from "../components/BuyCard";
import {
  AboutSection,
  KeyStatsSection,
  RelatedListsSection,
  NewsSection,
  TradingTrendsSection,
  AnalystRatingsSection,
  EarningsSection,
  PeopleAlsoOwnSection,
} from "../components/StockSections";

export function StockDetailPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const { api, liveTick } = useRobinhoodLayout();
  const [stock, setStock] = useState<Stock | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await api.getStock(symbol);
        if (!cancelled) setStock(s);
      } catch { /* skip */ }
      try {
        const p = await api.getPosition(symbol);
        if (!cancelled) setPosition(p);
      } catch { /* no position */ }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [api, symbol, liveTick]);

  if (loading) return <div className="rh-loading">Loading...</div>;
  if (!stock) return <div className="rh-empty">Stock not found: {symbol}</div>;

  const price = parseFloat(stock.price);
  const dayChange = parseFloat(stock.day_change);
  const dayChangePct = parseFloat(stock.day_change_pct);
  const isPositive = dayChange >= 0;

  return (
    <div className="rh-stock-detail-layout" aria-label={`${stock.name} stock details`}>
      <div className="rh-stock-detail__main">
        {/* Header: name + price */}
        <div className="rh-stock-detail__header">
          <h1 className="rh-stock-detail__name">{stock.name}</h1>
          <div className="rh-stock-detail__price">
            <span className="rh-stock-detail__price-value">${price.toFixed(2)}</span>
          </div>
          <div className={`rh-stock-detail__day-change ${isPositive ? "rh-gain" : "rh-loss"}`}>
            {isPositive ? "+" : ""}${dayChange.toFixed(2)} ({isPositive ? "+" : ""}{dayChangePct.toFixed(2)}%) Today
          </div>
          <div className="rh-stock-detail__bid-ask" aria-label={`Bid and ask quote for ${stock.symbol}`}>
            Bid ${parseFloat(stock.bid).toFixed(2)} / Ask ${parseFloat(stock.ask).toFixed(2)}
          </div>
        </div>

        {/* Chart */}
        <StockChart data={stock.historical_prices} positive={isPositive} />

        {/* Position (if held) */}
        {position && (
          <section className="rh-section" aria-label="Your position">
            <h2>Your Position</h2>
            <div className="rh-key-stats-grid">
              <div className="rh-key-stats-grid__item">
                <span className="rh-key-stats-grid__label">Shares</span>
                <span className="rh-key-stats-grid__value">{parseFloat(position.quantity)}</span>
              </div>
              <div className="rh-key-stats-grid__item">
                <span className="rh-key-stats-grid__label">Avg Cost</span>
                <span className="rh-key-stats-grid__value">${parseFloat(position.avg_cost_basis).toFixed(2)}</span>
              </div>
              <div className="rh-key-stats-grid__item">
                <span className="rh-key-stats-grid__label">Total Return</span>
                <span className={`rh-key-stats-grid__value ${parseFloat(position.total_return) >= 0 ? "rh-gain" : "rh-loss"}`}>
                  ${parseFloat(position.total_return).toFixed(2)} ({parseFloat(position.total_return_pct).toFixed(2)}%)
                </span>
              </div>
              <div className="rh-key-stats-grid__item">
                <span className="rh-key-stats-grid__label">Equity</span>
                <span className="rh-key-stats-grid__value">
                  ${(parseFloat(position.quantity) * parseFloat(position.current_price)).toFixed(2)}
                </span>
              </div>
            </div>
          </section>
        )}

        {/* About */}
        <AboutSection stock={stock} />

        {/* Key Statistics */}
        <KeyStatsSection stock={stock} />

        {/* Related Lists */}
        <RelatedListsSection sector={stock.sector} industry={stock.industry} />

        {/* News */}
        <NewsSection symbol={stock.symbol} sector={stock.sector} name={stock.name} />

        {/* Trading Trends */}
        <TradingTrendsSection symbol={stock.symbol} />

        {/* Analyst Ratings */}
        <AnalystRatingsSection symbol={stock.symbol} />

        {/* Earnings */}
        <EarningsSection symbol={stock.symbol} eps={stock.eps} />

        {/* People Also Own */}
        <PeopleAlsoOwnSection symbol={stock.symbol} sector={stock.sector} />
      </div>

      <aside className="rh-stock-detail__sidebar">
        <BuyCard symbol={stock.symbol} price={price} name={stock.name} />
      </aside>
    </div>
  );
}
