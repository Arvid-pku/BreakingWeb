import type { ApiRequestOptions } from "../hooks/useApi";
import type { EnvAdapter, RouteMutator } from "./types";

export function createStaticAdapter<TState>(
  envId: string,
  initialState: TState,
  mutator: RouteMutator<TState>,
): EnvAdapter & { getState: () => TState; reset: (state: TState) => void } {
  let currentState = structuredClone(initialState);

  return {
    mode: "static",
    envId,
    request: async <T,>(path: string, options: ApiRequestOptions = {}) => {
      const method = options.method ?? "GET";
      const body = options.body as Record<string, unknown> | undefined;
      const query = options.query;

      try {
        const result = mutator(currentState, method, path, body, query);
        currentState = result.state;
        return result.response as T;
      } catch (err) {
        console.error(`[static-adapter] ${method} ${path} failed:`, err);
        return { error: String(err) } as T;
      }
    },
    getState: () => currentState,
    reset: (state: TState) => {
      currentState = structuredClone(state);
    },
  };
}
