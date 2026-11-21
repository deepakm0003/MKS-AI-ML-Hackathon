/** Inline sparkline: 24 months of history (neutral) continuing into 12 forecast months (accent). */
export function Sparkline({ history, forecast, width = 120, height = 28, label }: {
  history: (number | null)[]; forecast: (number | null)[]; width?: number; height?: number; label?: string;
}) {
  const all = [...history, ...forecast].map((v) => v ?? 0);
  const n = all.length;
  if (n < 2) return null;
  const max = Math.max(...all, 1);
  const min = Math.min(...all, 0);
  const x = (i: number) => (i / (n - 1)) * (width - 2) + 1;
  const y = (v: number) => height - 2 - ((v - min) / (max - min || 1)) * (height - 4);
  const path = (vals: number[], offset: number) =>
    vals.map((v, i) => `${i ? "L" : "M"}${x(i + offset).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const h = history.map((v) => v ?? 0);
  const f = forecast.map((v) => v ?? 0);
  const bridge = h.length ? [h[h.length - 1], ...f] : f;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label ?? "trend"} className="spark">
      <path d={path(h, 0)} fill="none" stroke="var(--chart-history)" strokeWidth={1.5} strokeLinejoin="round" />
      {f.length > 0 && (
        <path d={path(bridge, Math.max(h.length - 1, 0))} fill="none" stroke="var(--series-1)" strokeWidth={1.75} strokeLinejoin="round" />
      )}
    </svg>
  );
}
