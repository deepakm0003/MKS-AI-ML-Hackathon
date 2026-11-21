/**
 * Global filter model - pure functions, no React.
 *
 * Five dimensions shared by every view (problem statement §5): product family, SKU, region,
 * channel, customer. Each holds a list of selected values; an empty list means "all".
 * Options cascade faceted-search style: a dimension's options (and their counts) are the
 * values present in the valid combinations that match every OTHER active filter. After a
 * change, selections that no longer match anything are pruned - the latest choice wins.
 * The state is serialised to the URL so a filtered view can be shared as a link.
 */
import type { FilterOptions } from "../api/types";

export const DIMS = ["family", "sku", "region", "channel", "customer"] as const;
export type Dim = (typeof DIMS)[number];
export type FilterState = Record<Dim, string[]>;

export const DIM_LABEL: Record<Dim, string> = {
  family: "Product family",
  sku: "SKU",
  region: "Region",
  channel: "Channel",
  customer: "Customer",
};

/** Query-string key per dimension (stable public URL format). */
export const URL_KEY: Record<Dim, string> = {
  family: "family",
  sku: "sku",
  region: "region",
  channel: "channel",
  customer: "customer",
};
const SEP = "|";

export const emptyFilters = (): FilterState => ({ family: [], sku: [], region: [], channel: [], customer: [] });

export interface ComboRow {
  family: string;
  sku: string;
  region: string;
  channel: string;
  customer: string;
}

export interface FilterIndex {
  rows: ComboRow[];
  skuLabel: Map<string, string>;
}

export function buildIndex(o: FilterOptions): FilterIndex {
  const rows = o.combos.map(([s, r, c, u]) => {
    const sku = o.skus[s];
    return { family: o.families[sku.family], sku: sku.id, region: o.regions[r], channel: o.channels[c], customer: o.customers[u] };
  });
  const skuLabel = new Map(o.skus.map((s) => [s.id, s.description ? `${s.id} · ${s.description}` : s.id]));
  return { rows, skuLabel };
}

function matches(row: ComboRow, f: FilterState, except?: Dim): boolean {
  for (const d of DIMS) {
    if (d === except) continue;
    const sel = f[d];
    if (sel.length && !sel.includes(row[d])) return false;
  }
  return true;
}

export interface Option {
  value: string;
  label: string;
  count: number;
}

/** Options for one dimension given the other active filters; counts = matching series. */
export function optionsFor(dim: Dim, idx: FilterIndex, f: FilterState): Option[] {
  const seen = new Map<string, Set<string>>();
  for (const r of idx.rows) {
    if (!matches(r, f, dim)) continue;
    const k = r[dim];
    if (!seen.has(k)) seen.set(k, new Set());
    seen.get(k)!.add(`${r.sku}\u0000${r.region}`);
  }
  for (const v of f[dim]) if (!seen.has(v)) seen.set(v, new Set());     // keep selected values visible
  return [...seen.entries()]
    .map(([value, s]) => ({ value, label: dim === "sku" ? idx.skuLabel.get(value) ?? value : value, count: s.size }))
    .sort((a, b) => a.value.localeCompare(b.value));
}

/** Number of distinct SKU x region series matching the whole filter. */
export function matchingSeries(idx: FilterIndex, f: FilterState): number {
  const s = new Set<string>();
  for (const r of idx.rows) if (matches(r, f)) s.add(`${r.sku}\u0000${r.region}`);
  return s.size;
}

export function totalSeries(idx: FilterIndex): number {
  return matchingSeries(idx, emptyFilters());
}

/** Drop selections that match nothing given the other filters; `keep` (the dim just edited) is never pruned. */
export function prune(f: FilterState, idx: FilterIndex, keep?: Dim): FilterState {
  let out = f;
  for (const d of DIMS) {
    if (d === keep || !out[d].length) continue;
    const valid = new Set(idx.rows.filter((r) => matches(r, out, d)).map((r) => r[d]));
    const kept = out[d].filter((v) => valid.has(v));
    if (kept.length !== out[d].length) out = { ...out, [d]: kept };
  }
  return out;
}

export type FilterAction =
  | { type: "set"; dim: Dim; values: string[] }
  | { type: "toggle"; dim: Dim; value: string }
  | { type: "clear"; dim: Dim }
  | { type: "clearAll" };

export function applyAction(f: FilterState, a: FilterAction, idx?: FilterIndex): FilterState {
  let next: FilterState;
  switch (a.type) {
    case "set":
      next = { ...f, [a.dim]: [...new Set(a.values)] };
      break;
    case "toggle":
      next = { ...f, [a.dim]: f[a.dim].includes(a.value) ? f[a.dim].filter((v) => v !== a.value) : [...f[a.dim], a.value] };
      break;
    case "clear":
      next = { ...f, [a.dim]: [] };
      break;
    case "clearAll":
      return emptyFilters();
  }
  return idx ? prune(next, idx, a.dim) : next;
}

export function activeCount(f: FilterState): number {
  return DIMS.reduce((n, d) => n + f[d].length, 0);
}

export function toSearchParams(f: FilterState, base?: URLSearchParams): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const d of DIMS) {
    if (f[d].length) p.set(URL_KEY[d], f[d].join(SEP));
    else p.delete(URL_KEY[d]);
  }
  return p;
}

export function fromSearchParams(p: URLSearchParams): FilterState {
  const f = emptyFilters();
  for (const d of DIMS) {
    const v = p.get(URL_KEY[d]);
    if (v) f[d] = [...new Set(v.split(SEP).filter(Boolean))];
  }
  return f;
}

/** Query parameters for API calls that accept the global filters (single-valued dims only). */
export function toApiQuery(f: FilterState): Record<string, string> {
  const col: Record<Dim, string> = {
    family: "Product_Family", sku: "SKU_ID", region: "Region", channel: "Sales_Channel", customer: "Customer_Name",
  };
  const q: Record<string, string> = {};
  for (const d of DIMS) if (f[d].length === 1) q[col[d]] = f[d][0];
  return q;
}
