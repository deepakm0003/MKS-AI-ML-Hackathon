import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { ApiError } from "../api/client";
import { useApi } from "../api/useApi";
import {
  activeCount, applyAction, buildIndex, fromSearchParams, matchingSeries, toSearchParams, totalSeries,
  type FilterAction, type FilterIndex, type FilterState,
} from "./model";

interface FilterContextValue {
  filters: FilterState;
  dispatch: (a: FilterAction) => void;
  index: FilterIndex | null;
  status: "loading" | "success" | "error";
  error?: ApiError;
  retry: () => void;
  active: number;
  matching: number | null;
  total: number | null;
}

const Ctx = createContext<FilterContextValue | null>(null);

/** Global filter state. The URL query string is the single source of truth (shareable, back-button safe). */
export function FilterProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const opts = useApi((s) => api.filters(s), []);
  const index = useMemo(() => (opts.status === "success" ? buildIndex(opts.data) : null), [opts.status, opts.data]);
  const filters = useMemo(() => fromSearchParams(params), [params]);

  const dispatch = useCallback(
    (a: FilterAction) => {
      setParams((prev) => toSearchParams(applyAction(fromSearchParams(prev), a, index ?? undefined), prev));
    },
    [setParams, index],
  );

  const value = useMemo<FilterContextValue>(
    () => ({
      filters, dispatch, index, status: opts.status, error: opts.error, retry: opts.retry,
      active: activeCount(filters),
      matching: index ? matchingSeries(index, filters) : null,
      total: index ? totalSeries(index) : null,
    }),
    [filters, dispatch, index, opts.status, opts.error, opts.retry],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useFilters(): FilterContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useFilters must be used inside <FilterProvider>");
  return v;
}
