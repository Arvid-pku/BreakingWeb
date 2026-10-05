import { createContext, useContext } from "react";
import type { BookingApi } from "./api";

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
}

export interface BookingLayoutContextValue {
  sessionId: string;
  api: BookingApi;
  notify: (title: string, description?: string) => void;
  toasts: ToastMessage[];
}

export const BookingLayoutContext = createContext<BookingLayoutContextValue | null>(null);

export function useBookingLayout(): BookingLayoutContextValue {
  const ctx = useContext(BookingLayoutContext);
  if (!ctx) throw new Error("useBookingLayout must be used within BookingLayoutContext.Provider");
  return ctx;
}
