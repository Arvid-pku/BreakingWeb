import type { ApiRequestOptions } from "../hooks/useApi";

export type AdapterMode = "live" | "static";

export interface EnvAdapter {
  mode: AdapterMode;
  envId: string;
  request: <T>(path: string, options?: ApiRequestOptions) => Promise<T>;
}

export type RouteMutator<TState> = (
  state: TState,
  method: string,
  path: string,
  body?: unknown,
  query?: Record<string, unknown>,
) => { state: TState; response: unknown };
