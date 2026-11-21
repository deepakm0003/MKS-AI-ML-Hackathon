import type { FilterOptions } from "../api/types";

/** Small, hand-made filter options for unit tests (never used by the app). */
export const OPTIONS: FilterOptions = {
  families: ["Brake & Safety Systems", "Thermal Management"],
  regions: ["Europe", "North America"],
  channels: ["Direct OEM", "Aftermarket"],
  customers: ["Crestline", "Orion"],
  skus: [
    { id: "BSS-001", description: "Brake caliper 25", family: 0 },
    { id: "BSS-002", description: "Brake disc 45", family: 0 },
    { id: "THM-001", description: "Radiator 12", family: 1 },
  ],
  // [sku, region, channel, customer]
  combos: [
    [0, 0, 0, 0],
    [0, 1, 0, 1],
    [1, 0, 1, 0],
    [2, 1, 0, 1],
  ],
  combo_fields: ["sku", "region", "channel", "customer"],
};

type Route = { status?: number; body: unknown };

/** fetch stub that answers by path (after the /api prefix). Unknown paths -> 404. */
export function stubFetch(routes: Record<string, Route | (() => Route)>) {
  const calls: string[] = [];
  const fn = async (input: RequestInfo | URL) => {
    const u = new URL(String(input), "http://localhost");
    const path = u.pathname.replace(/^\/api/, "");
    calls.push(path + u.search);
    const r = routes[path];
    const route = typeof r === "function" ? r() : r;
    if (!route) return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    return new Response(JSON.stringify(route.body), { status: route.status ?? 200, headers: { "Content-Type": "application/json" } });
  };
  return { fn, calls };
}

export const HEALTH = { status: "ok", validation: "PASS", selected_model: "c9c_keep_pull_forward", frozen_at: "2026-11-21 14:40" };
export const BRIEFING = {
  kpis: {
    forecast_model: "c9c_keep_pull_forward", history_end: "2026-10", units_next12: 1, units_next12_vs_last12: 0,
    revenue_next12: 1, revenue_next12_vs_last12: 0, units_19m: 1, units_19m_p10: 1, units_19m_p90: 1, revenue_19m: 1,
    series: 4, exceptions: 0, exceptions_by_priority: {}, capacity_flags: {}, high_supply_risk_family_regions: 0,
  },
  briefing: [],
};
export const DATASETS = {
  intelligence_report: { path: "outputs/intelligence/intelligence_report.json", view: "executive", description: "", available: true },
  timeline: { path: "outputs/intelligence/timeline.csv", view: "executive", description: "", available: false },
};
