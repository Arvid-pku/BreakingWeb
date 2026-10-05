import { useCallback, useMemo, useState } from "react";
import { apiRequest } from "./useApi";
import { useAdapterContext } from "./useAdapter";

interface SessionCreateResponse<T = Record<string, unknown>> {
  session_id: string;
  resolved_targets?: T;
  seed?: number;
  start_path?: string;
  title?: string;
  instruction?: string;
}

export function useSession(envId: string) {
  const adapter = useAdapterContext();

  const initialSessionId = useMemo(() => {
    if (adapter?.mode === "static") return "static-session";
    return new URLSearchParams(window.location.search).get("session");
  }, [adapter]);

  const [sessionId, setSessionId] = useState<string | null>(initialSessionId);

  const updateSessionInUrl = useCallback((nextSessionId: string | null) => {
    if (adapter?.mode === "static") return;
    const url = new URL(window.location.href);
    if (nextSessionId) {
      url.searchParams.set("session", nextSessionId);
    } else {
      url.searchParams.delete("session");
    }
    window.history.replaceState({}, "", url.toString());
  }, [adapter]);

  const createSession = useCallback(
    async <TResolved = Record<string, unknown>>(
      taskId: string,
      seed?: number,
      variantFilename?: string,
    ) => {
      if (adapter?.mode === "static") {
        const staticResponse: SessionCreateResponse<TResolved> = {
          session_id: "static-session",
          start_path: "/inbox",
        };
        setSessionId("static-session");
        return staticResponse;
      }
      const payload: Record<string, unknown> = { task_id: taskId, seed };
      if (variantFilename) {
        payload.variant_filename = variantFilename;
      }
      const response = await apiRequest<SessionCreateResponse<TResolved>>(envId, "session", {
        method: "POST",
        body: payload,
      });
      setSessionId(response.session_id);
      updateSessionInUrl(response.session_id);
      return response;
    },
    [adapter, envId, updateSessionInUrl],
  );

  const destroySession = useCallback(async () => {
    if (adapter?.mode === "static") {
      setSessionId(null);
      return;
    }
    if (!sessionId) return;
    await apiRequest<void>(envId, `session/${sessionId}`, { method: "DELETE" });
    setSessionId(null);
    updateSessionInUrl(null);
  }, [adapter, envId, sessionId, updateSessionInUrl]);

  return { sessionId, setSessionId, createSession, destroySession };
}
