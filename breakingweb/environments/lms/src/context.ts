import { createContext, useContext } from "react";

import type { createLmsApi } from "./api";
import type { Student } from "./types";

export interface LmsLayoutContextValue {
  sessionId: string;
  student: Student | null;
  api: ReturnType<typeof createLmsApi>;
  refreshStudent: () => Promise<void>;
  notify: (title: string, description?: string) => void;
}

export const LmsLayoutContext = createContext<LmsLayoutContextValue | null>(null);

export function useLmsLayout() {
  const ctx = useContext(LmsLayoutContext);
  if (!ctx) throw new Error("useLmsLayout must be used within LMS layout");
  return ctx;
}
