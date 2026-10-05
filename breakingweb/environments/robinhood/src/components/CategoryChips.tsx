interface CategoryChipsProps {
  chips: string[];
  onChipClick?: (chip: string) => void;
}

export function CategoryChips({ chips, onChipClick }: CategoryChipsProps) {
  return (
    <div className="rh-category-chips" aria-label="Categories">
      {chips.map((chip) => (
        <button
          key={chip}
          className="rh-category-chip"
          onClick={() => onChipClick?.(chip)}
          aria-label={chip}
        >
          {chip}
        </button>
      ))}
    </div>
  );
}

export function getRelatedLists(sector: string, industry: string): string[] {
  const base = ["100 Most Popular"];
  if (sector) base.push(sector);
  if (industry && industry !== sector) base.push(industry);
  const extras: Record<string, string[]> = {
    Technology: ["Tech Giants", "Cloud Computing", "Software"],
    Healthcare: ["Biotech", "Pharma", "Health & Wellness"],
    "Financial Services": ["Banking", "Fintech", "Insurance"],
    "Consumer Cyclical": ["Consumer Services & Retail", "E-Commerce"],
    Energy: ["Oil & Gas", "Renewable Energy", "Utilities"],
    "Communication Services": ["Social Media", "Streaming", "Telecom"],
    Industrials: ["Aerospace & Defense", "Manufacturing"],
    "Consumer Defensive": ["Food & Beverage", "Consumer Staples"],
    "Real Estate": ["REITs", "Commercial Real Estate"],
    Automotive: ["Electric Vehicles", "Autonomous Driving"],
  };
  const sectorExtras = extras[sector] || ["Growth", "Large Cap"];
  return [...base, ...sectorExtras].slice(0, 6);
}

export function getDiscoverChips(): string[] {
  return [
    "100 Most Popular",
    "Daily Movers",
    "Technology",
    "ETFs",
    "Energy",
    "Healthcare",
    "Cannabis",
    "Pharma",
    "Crypto",
    "China",
    "Automotive",
    "Banking",
    "Real Estate",
    "Food & Drink",
    "Entertainment",
  ];
}
