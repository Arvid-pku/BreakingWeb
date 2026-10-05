import { createContext, useContext } from "react";

import type { ToastMessage } from "@breakingweb/shared";

import type { MailboxSummary } from "./types";
import type { createGmailApi } from "./api";

export interface GmailLayoutContextValue {
  sessionId: string;
  summary: MailboxSummary | null;
  isRefreshing: boolean;
  api: ReturnType<typeof createGmailApi>;
  refreshMailbox: () => Promise<void>;
  notify: (title: string, description?: string, onUndo?: () => void) => void;
  searchValue: string;
  setSearchValue: (value: string) => void;
  toasts: ToastMessage[];
}

export const GmailLayoutContext = createContext<GmailLayoutContextValue | null>(null);

export function useGmailLayout() {
  const value = useContext(GmailLayoutContext);
  if (!value) {
    throw new Error("useGmailLayout must be used within the Gmail layout.");
  }
  return value;
}
