import { createContext, useContext } from "react";

import type { createRobinhoodApi } from "./api";
import type { PriceData } from "./types";

export interface RobinhoodLayoutContextValue {
  sessionId: string;
  account: { cash_balance: string; buying_power: string; portfolio_value: string; margin_maintenance: string; day_trade_count: number } | null;
  api: ReturnType<typeof createRobinhoodApi>;
  refreshAccount: () => Promise<void>;
  notify: (title: string, description?: string) => void;
  searchValue: string;
  setSearchValue: (value: string) => void;
  livePrices: Record<string, PriceData>;
  liveTick: number;
}

export const RobinhoodLayoutContext = createContext<RobinhoodLayoutContextValue | null>(null);

export function useRobinhoodLayout() {
  const ctx = useContext(RobinhoodLayoutContext);
  if (!ctx) throw new Error("useRobinhoodLayout must be used within Robinhood layout");
  return ctx;
}
