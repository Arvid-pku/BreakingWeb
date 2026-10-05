import { useEffect, useState } from "react";

import type { EarningsEvent, Stock } from "../types";
import { useRobinhoodLayout } from "../context";
import { NewsCard, generateNews } from "./NewsCard";
import { CategoryChips, getRelatedLists } from "./CategoryChips";

/* ── Deterministic seed helper ──────────────────────────────── */
function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/* ── About Section ──────────────────────────────────────────── */
interface AboutProps { stock: Stock }

const COMPANY_META: Record<string, { ceo: string; employees: string; hq: string; founded: string }> = {};

function getCompanyMeta(symbol: string, sector: string) {
  if (COMPANY_META[symbol]) return COMPANY_META[symbol];
  const h = hash(symbol);
  const ceos = ["Tim Cook", "Satya Nadella", "Elon Musk", "Andy Jassy", "Jensen Huang", "Mark Zuckerberg", "Sundar Pichai", "Jamie Dimon"];
  const cities = ["San Francisco, CA", "Austin, TX", "Seattle, WA", "New York, NY", "Cupertino, CA", "Menlo Park, CA", "Mountain View, CA", "Redmond, WA"];
  const result = {
    ceo: ceos[h % ceos.length],
    employees: ((h % 200 + 5) * 1000).toLocaleString(),
    hq: cities[h % cities.length],
    founded: String(1960 + (h % 55)),
  };
  COMPANY_META[symbol] = result;
  return result;
}

export function AboutSection({ stock }: AboutProps) {
  const meta = getCompanyMeta(stock.symbol, stock.sector);
  return (
    <section className="rh-section" aria-label="About">
      <h2>About</h2>
      <p className="rh-section__text">{stock.about}</p>
      <div className="rh-about-grid">
        <div className="rh-about-grid__item">
          <span className="rh-about-grid__label">CEO</span>
          <span className="rh-about-grid__value">{meta.ceo}</span>
        </div>
        <div className="rh-about-grid__item">
          <span className="rh-about-grid__label">Employees</span>
          <span className="rh-about-grid__value">{meta.employees}</span>
        </div>
        <div className="rh-about-grid__item">
          <span className="rh-about-grid__label">Headquarters</span>
          <span className="rh-about-grid__value">{meta.hq}</span>
        </div>
        <div className="rh-about-grid__item">
          <span className="rh-about-grid__label">Founded</span>
          <span className="rh-about-grid__value">{meta.founded}</span>
        </div>
      </div>
    </section>
  );
}

/* ── Key Statistics Section ─────────────────────────────────── */
interface KeyStatsProps { stock: Stock }

export function KeyStatsSection({ stock }: KeyStatsProps) {
  const fmt = (v: string | null) => v ? parseFloat(v).toLocaleString("en-US", { maximumFractionDigits: 2 }) : "--";
  const price = parseFloat(stock.price);
  const highToday = (price * 1.012).toFixed(2);
  const lowToday = (price * 0.988).toFixed(2);
  const openPrice = parseFloat(stock.previous_close).toFixed(2);

  const stats = [
    { label: "Market Cap", value: stock.market_cap ? `$${fmt(stock.market_cap)}` : "--" },
    { label: "P/E Ratio", value: fmt(stock.pe_ratio) },
    { label: "Dividend Yield", value: stock.dividend_yield ? `${fmt(stock.dividend_yield)}%` : "--" },
    { label: "Average Volume", value: stock.avg_volume.toLocaleString() },
    { label: "High Today", value: `$${highToday}` },
    { label: "Low Today", value: `$${lowToday}` },
    { label: "Open Price", value: `$${openPrice}` },
    { label: "Volume", value: stock.volume.toLocaleString() },
    { label: "52 Week High", value: `$${fmt(stock.fifty_two_week_high)}` },
    { label: "52 Week Low", value: `$${fmt(stock.fifty_two_week_low)}` },
  ];

  return (
    <section className="rh-section" aria-label="Key statistics">
      <h2>Key Statistics</h2>
      <div className="rh-key-stats-grid">
        {stats.map((s) => (
          <div key={s.label} className="rh-key-stats-grid__item">
            <span className="rh-key-stats-grid__label">{s.label}</span>
            <span className="rh-key-stats-grid__value">{s.value}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── Related Lists Section ──────────────────────────────────── */
interface RelatedListsProps { sector: string; industry: string }

export function RelatedListsSection({ sector, industry }: RelatedListsProps) {
  const chips = getRelatedLists(sector, industry);
  return (
    <section className="rh-section" aria-label="Related lists">
      <h2>Related Lists</h2>
      <CategoryChips chips={chips} />
    </section>
  );
}

/* ── News Section ───────────────────────────────────────────── */
interface NewsSectionProps { symbol: string; sector: string; name: string }

export function NewsSection({ symbol, sector, name }: NewsSectionProps) {
  const articles = generateNews(symbol, sector, name);
  return (
    <section className="rh-section" aria-label="News">
      <h2>News</h2>
      {articles.map((a, i) => (
        <NewsCard key={i} {...a} />
      ))}
    </section>
  );
}

/* ── Trading Trends Section ─────────────────────────────────── */
interface TradingTrendsProps { symbol: string }

export function TradingTrendsSection({ symbol }: TradingTrendsProps) {
  const h = hash(symbol);
  const buyPct = 50 + (h % 30);
  const holdPct = Math.floor((100 - buyPct) * 0.6);
  const sellPct = 100 - buyPct - holdPct;

  return (
    <section className="rh-section" aria-label="Trading trends">
      <h2>Trading Trends</h2>
      <div className="rh-trends__tabs">
        <button className="rh-tab rh-tab--active">Robinhood</button>
        <button className="rh-tab">Hedge Funds</button>
        <button className="rh-tab">Insiders</button>
      </div>
      <div className="rh-trends__bar-container">
        <div className="rh-trends__bar">
          <div className="rh-trends__bar-buy" style={{ width: `${buyPct}%` }} />
          <div className="rh-trends__bar-hold" style={{ width: `${holdPct}%` }} />
          <div className="rh-trends__bar-sell" style={{ width: `${sellPct}%` }} />
        </div>
        <div className="rh-trends__labels">
          <span><span className="rh-trends__dot rh-trends__dot--buy" />{buyPct}% Buy</span>
          <span><span className="rh-trends__dot rh-trends__dot--hold" />{holdPct}% Hold</span>
          <span><span className="rh-trends__dot rh-trends__dot--sell" />{sellPct}% Sell</span>
        </div>
      </div>
      <p className="rh-section__text">
        Our customers&apos; sell volume percentage decreased by 1% vs the last trading day.
      </p>
    </section>
  );
}

/* ── Analyst Ratings Section ────────────────────────────────── */
interface AnalystRatingsProps { symbol: string }

export function AnalystRatingsSection({ symbol }: AnalystRatingsProps) {
  const h = hash(symbol);
  const total = 60 + (h % 60);
  const buyPct = 40 + (h % 30);
  const holdPct = Math.floor((100 - buyPct) * 0.5);
  const sellPct = 100 - buyPct - holdPct;

  return (
    <section className="rh-section" aria-label="Analyst ratings">
      <h2>Analyst Ratings</h2>
      <div className="rh-analyst">
        <div className="rh-analyst__summary">
          <span className="rh-analyst__pct">{buyPct}%</span>
          <span className="rh-analyst__count">of {total} ratings</span>
        </div>
        <div className="rh-analyst__bar-container">
          <div className="rh-analyst__row">
            <span className="rh-analyst__label">Buy</span>
            <div className="rh-analyst__bar"><div className="rh-analyst__fill rh-analyst__fill--buy" style={{ width: `${buyPct}%` }} /></div>
            <span className="rh-analyst__val">{buyPct}%</span>
          </div>
          <div className="rh-analyst__row">
            <span className="rh-analyst__label">Hold</span>
            <div className="rh-analyst__bar"><div className="rh-analyst__fill rh-analyst__fill--hold" style={{ width: `${holdPct}%` }} /></div>
            <span className="rh-analyst__val">{holdPct}%</span>
          </div>
          <div className="rh-analyst__row">
            <span className="rh-analyst__label">Sell</span>
            <div className="rh-analyst__bar"><div className="rh-analyst__fill rh-analyst__fill--sell" style={{ width: `${sellPct}%` }} /></div>
            <span className="rh-analyst__val">{sellPct}%</span>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Earnings Section ───────────────────────────────────────── */
interface EarningsProps { symbol: string; eps: string | null }

function HistoricalEarningsChart({ symbol, eps }: { symbol: string; eps: string | null }) {
  const h = hash(symbol);
  const baseEps = eps ? parseFloat(eps) : 1.5;
  const quarters = ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024"];
  const data = quarters.map((q, i) => {
    const estimate = baseEps * (0.9 + ((h + i) % 20) / 100);
    const actual = estimate * (0.95 + ((h + i * 3) % 15) / 100);
    return { quarter: q, estimate: estimate.toFixed(2), actual: actual.toFixed(2) };
  });

  const maxVal = Math.max(...data.map((d) => Math.max(parseFloat(d.estimate), parseFloat(d.actual))));

  return (
    <>
      <div className="rh-earnings">
        {data.map((d) => {
          const estH = (parseFloat(d.estimate) / maxVal) * 100;
          const actH = (parseFloat(d.actual) / maxVal) * 100;
          const beat = parseFloat(d.actual) >= parseFloat(d.estimate);
          return (
            <div key={d.quarter} className="rh-earnings__quarter">
              <div className="rh-earnings__bars">
                <div className="rh-earnings__bar rh-earnings__bar--est" style={{ height: `${estH}%` }} title={`Est: $${d.estimate}`} />
                <div className={`rh-earnings__bar ${beat ? "rh-earnings__bar--beat" : "rh-earnings__bar--miss"}`} style={{ height: `${actH}%` }} title={`Act: $${d.actual}`} />
              </div>
              <span className="rh-earnings__label">{d.quarter}</span>
            </div>
          );
        })}
      </div>
      <div className="rh-earnings__legend">
        <span><span className="rh-earnings__legend-box rh-earnings__legend-box--est" />Estimate</span>
        <span><span className="rh-earnings__legend-box rh-earnings__legend-box--act" />Actual</span>
      </div>
    </>
  );
}

function formatEarningsTime(time: "before_market" | "after_market"): string {
  return time === "before_market" ? "Before Market Open" : "After Market Close";
}

export function EarningsSection({ symbol, eps }: EarningsProps) {
  const { api } = useRobinhoodLayout();
  const [upcomingEvents, setUpcomingEvents] = useState<EarningsEvent[]>([]);

  useEffect(() => {
    let cancelled = false;
    api.getStockEarnings(symbol).then((events) => {
      if (!cancelled) setUpcomingEvents(events);
    }).catch(() => {
      /* silently fall back to historical-only view */
    });
    return () => { cancelled = true; };
  }, [api, symbol]);

  return (
    <section className="rh-section" aria-label="Earnings">
      <h2>Earnings</h2>
      {upcomingEvents.length > 0 && (
        <div className="rh-earnings__upcoming" aria-label="Upcoming Earnings">
          <h3 className="rh-earnings__upcoming-title">Upcoming Earnings</h3>
          {upcomingEvents.map((event) => (
            <div key={`${event.symbol}-${event.date}`} className="rh-earnings__upcoming-event">
              <div className="rh-earnings__upcoming-date">
                <span className="rh-earnings__upcoming-date-value">{event.date}</span>
                <span className="rh-earnings__upcoming-date-time">{formatEarningsTime(event.time)}</span>
              </div>
              {event.eps_estimate && (
                <div className="rh-earnings__upcoming-detail">
                  <span className="rh-earnings__upcoming-label">EPS Estimate</span>
                  <span className="rh-earnings__upcoming-value">${event.eps_estimate}</span>
                </div>
              )}
              {event.revenue_estimate && (
                <div className="rh-earnings__upcoming-detail">
                  <span className="rh-earnings__upcoming-label">Revenue Estimate</span>
                  <span className="rh-earnings__upcoming-value">${event.revenue_estimate}</span>
                </div>
              )}
              {event.eps_actual && (
                <div className="rh-earnings__upcoming-detail">
                  <span className="rh-earnings__upcoming-label">EPS Actual</span>
                  <span className="rh-earnings__upcoming-value">${event.eps_actual}</span>
                </div>
              )}
              {event.revenue_actual && (
                <div className="rh-earnings__upcoming-detail">
                  <span className="rh-earnings__upcoming-label">Revenue Actual</span>
                  <span className="rh-earnings__upcoming-value">${event.revenue_actual}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <HistoricalEarningsChart symbol={symbol} eps={eps} />
    </section>
  );
}

/* ── People Also Own Section ────────────────────────────────── */
interface PeopleAlsoOwnProps { symbol: string; sector: string }

export function PeopleAlsoOwnSection({ symbol, sector }: PeopleAlsoOwnProps) {
  const h = hash(symbol);
  const sectorStocks: Record<string, Array<{ sym: string; name: string; price: number; change: number }>> = {
    Technology: [
      { sym: "AAPL", name: "Apple", price: 178.72, change: 1.24 },
      { sym: "MSFT", name: "Microsoft", price: 378.91, change: 0.85 },
      { sym: "GOOGL", name: "Alphabet", price: 141.80, change: -0.32 },
      { sym: "NVDA", name: "NVIDIA", price: 495.22, change: 2.15 },
      { sym: "META", name: "Meta", price: 355.67, change: 0.95 },
    ],
    Healthcare: [
      { sym: "JNJ", name: "Johnson & Johnson", price: 156.74, change: -0.45 },
      { sym: "PFE", name: "Pfizer", price: 28.31, change: -1.22 },
      { sym: "UNH", name: "UnitedHealth", price: 527.49, change: 0.72 },
      { sym: "ABBV", name: "AbbVie", price: 154.83, change: 0.31 },
      { sym: "MRK", name: "Merck", price: 108.45, change: -0.18 },
    ],
    default: [
      { sym: "SPY", name: "S&P 500 ETF", price: 456.78, change: 0.55 },
      { sym: "QQQ", name: "Nasdaq ETF", price: 388.90, change: 0.82 },
      { sym: "AAPL", name: "Apple", price: 178.72, change: 1.24 },
      { sym: "AMZN", name: "Amazon", price: 153.42, change: 1.05 },
      { sym: "TSLA", name: "Tesla", price: 248.50, change: -0.67 },
    ],
  };

  const stocks = (sectorStocks[sector] || sectorStocks["default"])
    .filter((s) => s.sym !== symbol)
    .slice(0, 4);

  return (
    <section className="rh-section" aria-label="People also own">
      <h2>People Also Own</h2>
      <div className="rh-also-own">
        {stocks.map((s) => (
          <div key={s.sym} className="rh-also-own__card">
            <span className="rh-also-own__symbol">{s.sym}</span>
            <span className="rh-also-own__price">${s.price.toFixed(2)}</span>
            <span className={`rh-also-own__change ${s.change >= 0 ? "rh-gain" : "rh-loss"}`}>
              {s.change >= 0 ? "+" : ""}{s.change.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
