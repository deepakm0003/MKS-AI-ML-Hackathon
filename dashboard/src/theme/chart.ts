/** Celeris chart theme — Black / Lime / Blue */

export const SERIES = [
  "#c7ff32", // lime   — primary forecast / accent
  "#3478f6", // blue   — secondary / comparison
  "#77aaff", // light blue
  "#a5d6ff", // pale blue
  "#d9d9d9", // light gray — actual demand
  "#858585", // mid gray
  "#f5b942", // amber
  "#bc8cff", // purple
  "#ffffff",  // white
  "#484848", // dark gray
] as const;

export const SERIES_OTHER = "#484848";

export const STATUS = {
  good:     "#34d399",   // emerald - distinct from the lime forecast series / accent
  warning:  "#f5b942",
  serious:  "#ff5c5c",
  critical: "#ff5c5c",
  info:     "#3478f6",
  purple:   "#bc8cff",
} as const;

export const CHART = {
  surface:    "#141414",
  grid:       "#242424",
  axis:       "#3a3a3a",
  text:       "#a1a1a1",
  textMuted:  "#707070",
  history:    "#d9d9d9",
  forecast:   "#c7ff32",
  band:       "rgba(199, 255, 50, 0.12)",
  bandDark:   "rgba(199, 255, 50, 0.05)",
  highlight:  "rgba(199, 255, 50, 0.2)",
  fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif',
  fontSize:   12,
  lineWidth:  2,
  barRadius:  3,
  markerSize: 5,
  glowColor:  "rgba(199, 255, 50, 0.2)",
} as const;

export const GRADIENTS = {
  primary: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#c7ff32" },
    { offset: 1, color: "#a3d416" },
  ]},
  success: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#c7ff32" },
    { offset: 1, color: "#a3d416" },
  ]},
  warning: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#f5b942" },
    { offset: 1, color: "#d49520" },
  ]},
  danger: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#ff5c5c" },
    { offset: 1, color: "#e03a3a" },
  ]},
  gray: { type: "linear" as const, x: 0, y: 0, x2: 1, y2: 0, colorStops: [
    { offset: 0, color: "#858585" },
    { offset: 1, color: "#484848" },
  ]},
} as const;

export function colorFor(entity: string, domain: readonly string[]): string {
  const i = domain.indexOf(entity);
  return i >= 0 && i < SERIES.length ? SERIES[i] : SERIES_OTHER;
}
