import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./client";

export type ApiState<T> =
  | { status: "loading"; data: undefined; error: undefined }
  | { status: "success"; data: T; error: undefined }
  | { status: "error"; data: undefined; error: ApiError };

/**
 * Fetch hook with abort on unmount / dependency change and a retry function.
 * It never substitutes placeholder data: a view gets loading, the real data, or an error.
 */
export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<ApiState<T>>({ status: "loading", data: undefined, error: undefined });
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const ctrl = new AbortController();
    setState({ status: "loading", data: undefined, error: undefined });
    fetcherRef
      .current(ctrl.signal)
      .then((data) => {
        if (!ctrl.signal.aborted) setState({ status: "success", data, error: undefined });
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted || (e as Error)?.name === "AbortError") return;
        const err = e instanceof ApiError ? e : new ApiError(String((e as Error)?.message ?? e), null, "");
        setState({ status: "error", data: undefined, error: err });
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  const retry = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, retry };
}
