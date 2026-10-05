import { useCallback, useState } from "react";
import { useAdapterContext } from "./useAdapter";

export interface ApiError extends Error {
  status?: number;
  detail?: unknown;
}

export interface ApiRequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, unknown>;
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
}

function buildUrl(envId: string, path: string, query?: Record<string, unknown>) {
  const url = new URL(`/api/env/${envId}/${path.replace(/^\/+/, "")}`, window.location.origin);
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    url.searchParams.set(key, String(value));
  });
  return url.toString();
}

export async function apiRequest<T>(
  envId: string,
  path: string,
  { method = "GET", query, body, headers, signal }: ApiRequestOptions = {},
): Promise<T> {
  const response = await fetch(buildUrl(envId, path, query), {
    method,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    const error = new Error(`API request failed: ${response.status}`) as ApiError;
    error.status = response.status;
    error.detail = detail;
    throw error;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function useApi(envId: string, sessionId?: string | null) {
  const adapter = useAdapterContext();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const request = useCallback(
    async <T,>(path: string, options: ApiRequestOptions = {}) => {
      setIsLoading(true);
      setError(null);
      try {
        if (adapter) {
          return await adapter.request<T>(path, options);
        }
        // Fallback: direct fetch (original behavior)
        const method = options.method ?? "GET";
        const body =
          sessionId && method !== "GET"
            ? options.body === undefined
              ? { session_id: sessionId }
              : typeof options.body === "object" && options.body !== null && !Array.isArray(options.body)
                ? { session_id: sessionId, ...(options.body as Record<string, unknown>) }
                : options.body
            : options.body;

        return await apiRequest<T>(envId, path, {
          ...options,
          method,
          body,
          query: {
            session_id: sessionId ?? undefined,
            ...options.query,
          },
        });
      } catch (caught) {
        const apiError = caught as ApiError;
        setError(apiError);
        throw apiError;
      } finally {
        setIsLoading(false);
      }
    },
    [adapter, envId, sessionId],
  );

  return { request, isLoading, error };
}
