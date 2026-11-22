/**
 * Professional chart theme - GitHub/modern SaaS inspired
 * Clean dark with cyan-blue accent, subtle grays
 */
export const SERIES = [
  "#58a6ff", // cyan-blue primary
  "#1f6feb", // dark blue
  "#79c0ff", // light cyan
  "#a5d6ff", // pale blue
  "#8b949e", // medium gray
  "#6e7681", // darker gray
  "#3fb950", // green accent
  "#bc8cff", // purple accent
  "#c9d1d9", // light gray
  "#484f58", // steel gray
] as const;
export const SERIES_OTHER = "#6e7681";

export const STATUS = {
  good: "#3fb950",
  warning: "#d29922",
  serious: "#f85149",
  critical: "#f85149",
  info: "#58a6ff",
  purple: "#bc8cff",
} as const;

export const CHART = {
  surface: "#161b22",
  grid: "rgba(139, 148, 158, 0.1)",
  axis: "#484f58",
  text: "#c9d1d9",
  textMuted: "#8b949e",
  history: "#8b949e",
  forecast: SERIES[0],
  band: "rgba(88, 166, 255, 0.15)",
  bandDark: "rgba(88, 166, 255, 0.08)",
  highlight: "rgba(88, 166, 255, 0.2)",
  fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif',
  fontSize: 12,
  lineWidth: 2,
  barRadius: 4,
  markerSize: 6,
  glowColor: "rgba(88, 166, 255, 0.3)",
} as const;

/** Subtle gradients */
export const GRADIENTS = {
  primary: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#58a6ff" },
    { offset: 1, color: "#1f6feb" },
  ]},
  success: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#3fb950" },
    { offset: 1, color: "#2ea043" },
  ]},
  warning: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#d29922" },
    { offset: 1, color: "#bb8009" },
  ]},
  danger: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#f85149" },
    { offset: 1, color: "#da3633" },
  ]},
  gray: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#8b949e" },
    { offset: 1, color: "#6e7681" },
  ]},
} as const;

/** Stable colour per entity: the order of the full domain decides, not the visible subset. */
export function colorFor(entity: string, domain: readonly string[]): string {
  const i = domain.indexOf(entity);
  return i >= 0 && i < SERIES.length ? SERIES[i] : SERIES_OTHER;
}
