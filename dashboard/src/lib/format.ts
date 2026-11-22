/** Number formatting used everywhere a figure is shown (compact, signed where it is a change). */

const compact = (v: number, digits: number) => {
  const a = Math.abs(v);
  if (a >= 1e9) return `${(v / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${(v / 1e6).toFixed(digits)}M`;
  if (a >= 1e4) return `${(v / 1e3).toFixed(a >= 1e5 ? 0 : 1)}K`;
  return Math.round(v).toLocaleString("en-US");
};

const ok = (v: number | null | undefined): v is number => v !== null && v !== undefined && Number.isFinite(v);

export function fmtUnits(v: number | null | undefined, digits = 2): string {
  return ok(v) ? compact(v, digits) : "—";
}

export function fmtUsd(v: number | null | undefined, digits = 2): string {
  if (!ok(v)) return "—";
  return `${v < 0 ? "−" : ""}$${compact(Math.abs(v), digits)}`;
}

/** Fraction (0.061) -> "+6.1%". */
export function fmtPctChange(v: number | null | undefined, digits = 1): string {
  if (!ok(v)) return "—";
  const p = v * 100;
  const s = Math.abs(p).toFixed(digits);
  if (Number(s) === 0) return `${s}%`;
  return p > 0 ? `+${s}%` : `−${s}%`;
}

/** Percent already in % (6.0) -> "+6.0%". */
export function fmtPctPoints(v: number | null | undefined, digits = 1): string {
  return ok(v) ? fmtPctChange(v / 100, digits) : "—";
}

export function fmtInt(v: number | null | undefined): string {
  return ok(v) ? Math.round(v).toLocaleString("en-US") : "—";
}

/** "2026-10" -> "Oct 26". */
export function fmtMonthShort(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  const name = new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${name} ${String(y).slice(2)}`;
}

/** Format as percentage (0.28 -> "28%") */
export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (!ok(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
