import { api } from "./client";
import type { BreakdownView } from "./types";
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
