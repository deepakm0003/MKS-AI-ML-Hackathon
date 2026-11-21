/**
 * Drill-down path family -> SKU -> region -> customer, derived from the global filters (so the
 * path is shareable and the other views see the same selection). The current level is the first
 * dimension in that order that is not pinned to exactly one value; once a SKU and a region are
 * pinned, the explorer shows that single series.
 */
import type { DrillLevel } from "../api/types";
import type { Dim, FilterState } from "../filters/model";

export const DRILL_ORDER: DrillLevel[] = ["family", "sku", "region", "customer"];

export type ExplorerMode = { kind: "level"; level: DrillLevel } | { kind: "series"; sku: string; region: string };

export function explorerMode(f: FilterState): ExplorerMode {
  if (f.sku.length === 1 && f.region.length === 1) return { kind: "series", sku: f.sku[0], region: f.region[0] };
  const level = DRILL_ORDER.find((d) => f[d].length !== 1) ?? "customer";
  return { kind: "level", level };
}

export interface Crumb {
  label: string;
  /** dimensions to clear when this crumb is clicked (everything deeper than it) */
  clear: Dim[];
}

export function crumbs(f: FilterState): Crumb[] {
  const out: Crumb[] = [{ label: "All products", clear: [...DRILL_ORDER] }];
  for (let i = 0; i < DRILL_ORDER.length; i++) {
    const d = DRILL_ORDER[i];
    if (f[d].length !== 1) break;
    out.push({ label: f[d][0], clear: DRILL_ORDER.slice(i + 1) });
  }
  return out;
}

export const LEVEL_LABEL: Record<DrillLevel, string> = {
  family: "Product families", sku: "SKUs", region: "Regions", customer: "Customers",
};
