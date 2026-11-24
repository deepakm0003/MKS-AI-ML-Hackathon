import { api } from "./client";
import type { BreakdownView, DrillLevel } from "./types";
import { useApi } from "./useApi";
import { useFilters } from "../filters/FilterContext";
import { toViewQuery } from "../filters/model";

/** Filtered timeline for the current global filters (refetches when they change). */
export function useTimeline() {
  const { filters } = useFilters();
  const q = toViewQuery(filters);
  const key = JSON.stringify(q);
  return useApi((s) => api.timeline(q, s), [key]);
}

/** Last-12 vs next-12 breakdown by one dimension for the current global filters. */
export function useBreakdown(dim: BreakdownView["dim"], top = 25) {
  const { filters } = useFilters();
  const q = toViewQuery(filters);
  const key = JSON.stringify(q);
  return useApi((s) => api.breakdown(dim, q, top, s), [dim, top, key]);
}

/** Recommendation cards for the current global filters (direct matches first). */
export function useRecommendations(extra: Record<string, string | number> = {}) {
  const { filters } = useFilters();
  const q = { ...toViewQuery(filters), ...extra };
  const key = JSON.stringify(q);
  return useApi((s) => api.recommendations(q, s), [key]);
}

export function useSeasonality() {
  const { filters } = useFilters();
  const q = toViewQuery(filters);
  return useApi((s) => api.seasonality(q, s), [JSON.stringify(q)]);
}

export function useDrilldown(level: DrillLevel, top = 60) {
  const { filters } = useFilters();
  const q = toViewQuery(filters);
  return useApi((s) => api.drilldown(level, q, top, s), [level, top, JSON.stringify(q)]);
}

export function useLifecycle() {
  const { filters } = useFilters();
  const q = toViewQuery(filters);
  return useApi((s) => api.lifecycle(q, s), [JSON.stringify(q)]);
}

/** Server-side planning aggregation for the current global filters (full data, never a truncated slice). */
export function usePlanningView(top = 500) {
  const { filters } = useFilters();
  const q = toViewQuery(filters);
  return useApi((s) => api.planningView(q, top, s), [top, JSON.stringify(q)]);
}

/** Anomaly counts, flagged months and register rows for the current global filters. */
export function useAnomaliesView(top = 500) {
  const { filters } = useFilters();
  const q = toViewQuery(filters);
  return useApi((s) => api.anomaliesView(q, top, s), [top, JSON.stringify(q)]);
}
