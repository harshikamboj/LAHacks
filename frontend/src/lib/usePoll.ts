import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface Polled<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  refresh: () => void;
}

/** Calls `fn` now and every `intervalMs` while `enabled`; keeps the last good data while showing the latest error. */
export function usePoll<T>(fn: () => Promise<T>, intervalMs = 1000, enabled = true): Polled<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e)));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    run();
    const id = window.setInterval(run, intervalMs);
    return () => window.clearInterval(id);
  }, [run, intervalMs, enabled]);

  return { data, error, loading, refresh: run };
}
