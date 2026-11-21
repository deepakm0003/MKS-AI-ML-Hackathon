import type {
  Briefing, BreakdownView, DatasetIndex, FilterOptions, Health, Kpis, Paged, PresetResult, Recommendations,
  ScenarioConfig, ScenarioResult, TimelineView,
} from "./types";

/** Base URL of the read-only API. Dev and preview proxy /api to FastAPI (vite.config.ts). */
export const API_BASE: string = (import.meta.env?.VITE_API_BASE as string | undefined) ?? "/api";

/** A failed API call, with enough detail for the error state to explain itself. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,          // null = network / server unreachable
    readonly path: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** 503 = the pipeline stage that produces this data has not been run yet. */
  get notGenerated(): boolean {
    return this.status === 503;
  }
}

type Query = Record<string, string | number | undefined | null>;
export type FilterQuery = Partial<Record<"family" | "sku" | "region" | "channel" | "customer", string>>;

function url(path: string, query?: Query): string {
  const q = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const s = q.toString();
  return `${API_BASE}${path}${s ? `?${s}` : ""}`;
}

/*
 * GET responses are shared: identical concurrent requests (several panels on one page asking for
 * the same timeline) become one network call, and a response is reused for CACHE_MS. The backend
 * is frozen, so this never shows stale model output - only avoids duplicate work.
 */
const CACHE_MS = 60_000;
const cache = new Map<string, { at: number; p: Promise<unknown> }>();

export function clearApiCache(): void {
  cache.clear();
}

export function request<T>(path: string, init?: RequestInit & { query?: Query }): Promise<T> {
  const { query, signal, ...rest } = init ?? {};
  const u = url(path, query);
  if ((rest.method ?? "GET").toUpperCase() !== "GET") return send<T>(path, u, { ...rest, signal });
  const hit = cache.get(u);
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.p as Promise<T>;
  // the shared request is not tied to one caller's AbortSignal; callers ignore results after abort
  const p = send<T>(path, u, rest);
  cache.set(u, { at: Date.now(), p });
  p.catch(() => cache.delete(u));
  return p;
}

async function send<T>(path: string, u: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(u, { headers: { Accept: "application/json" }, ...init });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("The API is unreachable. Start it with: uvicorn api.app:app", null, path);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail || `HTTP ${res.status}`, res.status, path);
  }
  return (await res.json()) as T;
}

/** Typed endpoints - one function per route the dashboard uses. */
export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal }),
  kpis: (signal?: AbortSignal) => request<Kpis>("/kpis", { signal }),
  datasets: (signal?: AbortSignal) => request<DatasetIndex>("/datasets", { signal }),
  dataset: <R>(name: string, query?: Query, signal?: AbortSignal) =>
    request<Paged<R>>(`/datasets/${encodeURIComponent(name)}`, { query, signal }),
  filters: (signal?: AbortSignal) => request<FilterOptions>("/meta/filters", { signal }),
  briefing: (signal?: AbortSignal) => request<Briefing>("/intelligence/briefing", { signal }),
  recommendations: (query?: Query, signal?: AbortSignal) =>
    request<Recommendations>("/intelligence/recommendations", { query, signal }),
  /** Global filters as {family, sku, region, channel, customer} -> pipe-joined query values. */
  timeline: (filters: FilterQuery, signal?: AbortSignal) => request<TimelineView>("/views/timeline", { query: filters, signal }),
  breakdown: (dim: BreakdownView["dim"], filters: FilterQuery, top = 25, signal?: AbortSignal) =>
    request<BreakdownView>("/views/breakdown", { query: { dim, top, ...filters }, signal }),
  scenarioPresets: (signal?: AbortSignal) => request<Record<string, PresetResult>>("/scenario/presets", { signal }),
  scenarioConfig: (signal?: AbortSignal) => request<ScenarioConfig>("/scenario/config", { signal }),
  scenario: (body: { shocks: Record<string, number>; region_overlay?: Record<string, number> }, signal?: AbortSignal) =>
    request<ScenarioResult>("/scenario", {
      method: "POST", body: JSON.stringify(body), signal, headers: { "Content-Type": "application/json", Accept: "application/json" },
    }),
};
