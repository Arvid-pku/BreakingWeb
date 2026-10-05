interface NewsCardProps {
  headline: string;
  source: string;
  timestamp: string;
  snippet: string;
  tickers: string[];
  imageColor: string;
}

export function NewsCard({ headline, source, timestamp, snippet, tickers, imageColor }: NewsCardProps) {
  return (
    <div className="rh-news-card" aria-label={headline}>
      <div className="rh-news-card__text">
        <div className="rh-news-card__meta">
          <span className="rh-news-card__source">{source}</span>
          <span className="rh-news-card__dot">·</span>
          <span className="rh-news-card__time">{timestamp}</span>
        </div>
        <h3 className="rh-news-card__headline">{headline}</h3>
        <p className="rh-news-card__snippet">{snippet}</p>
        <div className="rh-news-card__tickers">
          {tickers.map((t) => (
            <span key={t} className="rh-news-card__ticker">{t}</span>
          ))}
        </div>
      </div>
      <div className="rh-news-card__image" style={{ background: imageColor }} />
    </div>
  );
}

// Deterministic fake news generator seeded from stock symbol
export function generateNews(symbol: string, sector: string, name: string): NewsCardProps[] {
  const hash = simpleHash(symbol);
  const sources = ["Reuters", "Bloomberg", "CNBC", "MarketWatch", "Barron's", "WSJ"];
  const times = ["2h ago", "4h ago", "6h ago"];
  const colors = ["#2d4a7a", "#4a2d7a", "#7a4a2d", "#2d7a4a", "#7a2d4a", "#4a7a2d"];

  const headlines: Record<string, string[]> = {
    Technology: [
      `${name} announces major AI partnership to boost cloud services`,
      `Analysts raise price target for ${symbol} citing strong enterprise growth`,
      `${name} CEO outlines five-year technology roadmap at investor day`,
    ],
    Healthcare: [
      `${name} receives FDA fast-track designation for new treatment`,
      `${symbol} reports strong clinical trial data, shares surge`,
      `${name} expands partnership with major hospital network`,
    ],
    "Financial Services": [
      `${name} posts record quarterly revenue amid rate environment`,
      `${symbol} announces $2B stock buyback program`,
      `${name} launches new digital banking platform for retail customers`,
    ],
    default: [
      `${name} beats earnings expectations for Q3, raises guidance`,
      `Wall Street analysts maintain bullish outlook on ${symbol}`,
      `${name} announces strategic expansion into new markets`,
    ],
  };

  const sectorHeadlines = headlines[sector] || headlines["default"];

  return sectorHeadlines.map((headline, i) => ({
    headline,
    source: sources[(hash + i) % sources.length],
    timestamp: times[i],
    snippet: `${name} (${symbol}) continues to show momentum in the ${sector.toLowerCase()} space as market participants assess the outlook for the company heading into next quarter.`,
    tickers: [symbol, ...(i === 0 ? [getRelatedTicker(hash, i)] : [])],
    imageColor: colors[(hash + i) % colors.length],
  }));
}

function getRelatedTicker(hash: number, offset: number): string {
  const tickers = ["SPY", "QQQ", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA"];
  return tickers[(hash + offset) % tickers.length];
}

function simpleHash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}
