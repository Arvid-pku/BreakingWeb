import { createContext, useContext } from "react";

import type { ToastMessage } from "@breakingweb/shared";

import type { CartSummary } from "./types";
import type { createAmazonApi } from "./api";

export interface AmazonLayoutContextValue {
  sessionId: string;
  cartSummary: CartSummary | null;
  isRefreshing: boolean;
  api: ReturnType<typeof createAmazonApi>;
  refreshCart: () => Promise<void>;
  notify: (title: string, description?: string) => void;
  searchValue: string;
  setSearchValue: (value: string) => void;
  toasts: ToastMessage[];
}

export const AmazonLayoutContext = createContext<AmazonLayoutContextValue | null>(null);

export function useAmazonLayout() {
  const value = useContext(AmazonLayoutContext);
  if (!value) {
    throw new Error("useAmazonLayout must be used within the Amazon layout.");
  }
  return value;
}
