import { createContext, useContext } from "react";

import type { ToastMessage } from "@breakingweb/shared";

import type { MyProfile, RedditSettings } from "./types";
import type { createRedditApi } from "./api";

export interface RedditLayoutContextValue {
  sessionId: string;
  profile: MyProfile | null;
  settings: RedditSettings | null;
  isRefreshing: boolean;
  api: ReturnType<typeof createRedditApi>;
  refreshProfile: () => Promise<void>;
  refreshSettings: () => Promise<RedditSettings>;
  updateSettings: (updates: Partial<RedditSettings>) => Promise<RedditSettings>;
  notify: (title: string, description?: string) => void;
  searchValue: string;
  setSearchValue: (value: string) => void;
  toasts: ToastMessage[];
}

export const RedditLayoutContext = createContext<RedditLayoutContextValue | null>(null);

export function useRedditLayout() {
  const value = useContext(RedditLayoutContext);
  if (!value) {
    throw new Error("useRedditLayout must be used within the Reddit layout.");
  }
  return value;
}
