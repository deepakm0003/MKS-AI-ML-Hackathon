/**
 * Chart theme shared by every view (Phase 2 onward). Values mirror styles/tokens.css so a
 * chart library can be fed plain strings. Rules from the dataviz method:
 *  - categorical hues in FIXED order, assigned by entity (a filter never repaints survivors);
 *  - one y-axis per chart (never dual-axis);
 *  - 2px lines, thin bars with 4px rounded data-ends, recessive grid;
 *  - legend whenever >= 2 series, direct labels for <= 4, a table view for every chart;
 *  - status colours only for status, always with icon + label.
 */
export const SERIES = ["#1a9fc8", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9"] as const;
export const SERIES_OTHER = "#5b6b85";

export const STATUS = {
  good: "#10b981",
  warning: "#f5a524",
  serious: "#ec835a",
  critical: "#e5534b",
} as const;

export const CHART = {
  surface: "#111a2b",
  grid: "rgba(169, 182, 203, 0.10)",
  axis: "#3a4a66",
  text: "#a9b6cb",
  textMuted: "#7d8ca6",
  history: "#a9b6cb",
  forecast: SERIES[0],
  band: "rgba(26, 159, 200, 0.18)",
  fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif',
  fontSize: 12,
  lineWidth: 2,
  barRadius: 4,
  markerSize: 8,
} as const;

/** Stable colour per entity: the order of the full domain decides, not the visible subset. */
export function colorFor(entity: string, domain: readonly string[]): string {
  const i = domain.indexOf(entity);
  return i >= 0 && i < SERIES.length ? SERIES[i] : SERIES_OTHER;
}
