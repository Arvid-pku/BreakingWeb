import { createContext, useContext, type ReactNode } from "react";
import type { EnvAdapter } from "../adapters/types";

const AdapterContext = createContext<EnvAdapter | null>(null);

export function useAdapterContext(): EnvAdapter | null {
  return useContext(AdapterContext);
}

export function AdapterProvider({
  adapter,
  children,
}: {
  adapter: EnvAdapter;
  children: ReactNode;
}) {
  return (
    <AdapterContext.Provider value={adapter}>
      {children}
    </AdapterContext.Provider>
  );
}
