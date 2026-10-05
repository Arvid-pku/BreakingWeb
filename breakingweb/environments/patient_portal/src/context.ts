import { createContext, useContext } from "react";

import type { createPatientPortalApi } from "./api";
import type { Patient, Provider } from "./types";

export interface PatientPortalContextValue {
  sessionId: string;
  profile: Patient | null;
  providers: Provider[];
  unreadCount: number;
  api: ReturnType<typeof createPatientPortalApi>;
  refreshProfile: () => Promise<void>;
  refreshProviders: () => Promise<void>;
  refreshUnread: () => Promise<void>;
  notify: (title: string, description?: string) => void;
}

export const PatientPortalContext = createContext<PatientPortalContextValue | null>(null);

export function usePatientPortal() {
  const ctx = useContext(PatientPortalContext);
  if (!ctx) throw new Error("usePatientPortal must be used within Patient Portal layout");
  return ctx;
}
