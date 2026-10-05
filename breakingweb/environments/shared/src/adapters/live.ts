import { apiRequest, type ApiRequestOptions } from "../hooks/useApi";
import type { EnvAdapter } from "./types";

export function createLiveAdapter(envId: string, sessionId?: string | null): EnvAdapter {
  return {
    mode: "live",
    envId,
    request: async <T,>(path: string, options: ApiRequestOptions = {}) => {
      const method = options.method ?? "GET";
      const body =
        sessionId && method !== "GET"
          ? options.body === undefined
            ? { session_id: sessionId }
            : typeof options.body === "object" && options.body !== null && !Array.isArray(options.body)
              ? { session_id: sessionId, ...(options.body as Record<string, unknown>) }
              : options.body
          : options.body;

      return apiRequest<T>(envId, path, {
        ...options,
        method,
        body,
        query: {
          session_id: sessionId ?? undefined,
          ...options.query,
        },
      });
    },
  };
}
