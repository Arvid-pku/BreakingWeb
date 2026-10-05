import { useCallback, useEffect } from "react";

declare global {
  interface Window {
    __benchmarkState?: {
      pageId: string;
      completed: boolean;
      success: boolean;
      startTime: number;
      endTime: number | null;
      data: Record<string, unknown>;
      events: Array<{ type: string; detail: Record<string, unknown>; timestamp: number }>;
    };
    __benchmarkUpdate?: (data: Record<string, unknown>) => void;
    __benchmarkLog?: (eventType: string, detail?: Record<string, unknown>) => void;
    __benchmarkComplete?: (success: boolean, data?: Record<string, unknown>) => void;
  }
}

export function useBenchmarkState(pageId: string) {
  useEffect(() => {
    if (window.__benchmarkState) {
      window.__benchmarkState.pageId = pageId;
    }
  }, [pageId]);

  const update = useCallback((data: Record<string, unknown>) => {
    window.__benchmarkUpdate?.(data);
  }, []);

  const log = useCallback((eventType: string, detail?: Record<string, unknown>) => {
    window.__benchmarkLog?.(eventType, detail);
  }, []);

  const complete = useCallback((success: boolean, data?: Record<string, unknown>) => {
    window.__benchmarkComplete?.(success, data);
  }, []);

  return { update, log, complete };
}
