/**
 * Calendar Forecast & Date Range Explorer
 *
 * Forecast horizon: 2026-11 → 2028-05 (19 months, monthly granularity).
 * Breakdowns and the CSV download come from /datasets/forecast_detail (58 k rows, cached) with the
 * global filters applied in the browser. Monthly P10 / P90, revenue and the comparison with the
 * previous period come from /views/timeline, so they use the calibrated aggregate bands (a sum of
 * SKU-level P10 / P90 would overstate the range) and real history for prior periods.
 * Date selection is month-based — the model produces monthly forecasts, not daily ones.
 */
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { useTimeline } from "../api/views";
import { useFilters } from "../filters/FilterContext";
import { DIMS, type Dim } from "../filters/model";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { Icon } from "../components/Icon";
import { KpiTile } from "../components/KpiTile";
import { Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt, fmtMonthShort, fmtPct, fmtUsd as _fmtUsd } from "../lib/format";
import { SERIES } from "../theme/chart";

/* ── Types ────────────────────────────────────────────────── */
interface ForecastRow {
  Date: string; Year: number; Month: number;
  Product_Family: string; SKU_ID: string;
  Region: string; Sales_Channel: string; Customer_Name: string;
  Forecast: number; P10: number; P50: number; P90: number;
}

/* ── Constants ───────────────────────────────────────────── */
const FORECAST_MONTHS = [
  "2026-11","2026-12",
  "2027-01","2027-02","2027-03","2027-04","2027-05","2027-06",
  "2027-07","2027-08","2027-09","2027-10","2027-11","2027-12",
  "2028-01","2028-02","2028-03","2028-04","2028-05",
] as const;

const FIRST = FORECAST_MONTHS[0];
const LAST  = FORECAST_MONTHS[FORECAST_MONTHS.length - 1];

type YM = string; // "YYYY-MM"

/* ── Helpers ───────────────────────────��─────────────────── */
function ymLabel(ym: YM): string {
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

function monthsInRange(start: YM, end: YM): YM[] {
  return FORECAST_MONTHS.filter((m) => m >= start && m <= end) as YM[];
}

function prevEquivPeriod(months: YM[]): { start: YM; end: YM } | null {
  if (!months.length) return null;
  const shift = (ym: YM, n: number): string => {
    const [y, m] = ym.split("-").map(Number);
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  };
  const len = months.length;
  return { start: shift(months[0], -len), end: shift(months[months.length - 1], -len) };
}

function aggregate(rows: ForecastRow[], months: YM[]) {
  const set = new Set(months);
  const filtered = rows.filter((r) => set.has(r.Date));
  const units   = filtered.reduce((s, r) => s + r.Forecast, 0);
  const p10     = filtered.reduce((s, r) => s + r.P10,      0);
  const p50     = filtered.reduce((s, r) => s + r.P50,      0);
  const p90     = filtered.reduce((s, r) => s + r.P90,      0);
  // revenue proxy: Forecast / P50 ratio applied to known timeline revenue
  // We don't have per-row revenue in forecast_detail, so proxy = units (revenue shown separately)
  return { units, p10, p50, p90, rows: filtered };
}

function byDim(rows: ForecastRow[], dim: keyof ForecastRow) {
  const m = new Map<string, number>();
  for (const r of rows) {
    const k = r[dim] as string;
    m.set(k, (m.get(k) ?? 0) + r.Forecast);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

/* ── Quick presets ───────────────────────────────────────── */
const PRESETS: { label: string; months: number | "all" }[] = [
  { label: "Next 3 months",        months: 3 },
  { label: "Next 6 months",        months: 6 },
  { label: "Next 12 months",       months: 12 },
  { label: "Full horizon (19 m)",  months: "all" },
];

function presetRange(months: number | "all"): { start: YM; end: YM } {
  if (months === "all") return { start: FIRST, end: LAST };
  const end = FORECAST_MONTHS[Math.min(months - 1, FORECAST_MONTHS.length - 1)];
  return { start: FIRST, end };
}

/* ── CSV export ──────────────────────────────────────────── */
function downloadCsv(rows: ForecastRow[], start: YM, end: YM) {
  const headers = ["Date","Product_Family","SKU_ID","Region","Sales_Channel","Customer_Name","Forecast","P10","P50","P90"];
  const lines   = rows.map((r) =>
    [r.Date, r.Product_Family, r.SKU_ID, r.Region, r.Sales_Channel, r.Customer_Name,
     r.Forecast.toFixed(2), r.P10.toFixed(2), r.P50.toFixed(2), r.P90.toFixed(2)].join(",")
  );
  const csv  = [headers.join(","), ...lines].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `celeris_forecast_${start}_${end}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ── Component ───────────────────────────────────────────── */
export function CalendarForecast() {
  const [rangeStart, setRangeStart] = useState<YM>(FORECAST_MONTHS[0]);
  const [rangeEnd,   setRangeEnd]   = useState<YM>(FORECAST_MONTHS[11]);
  const [hoverMonth, setHoverMonth] = useState<YM | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<YM | null>(null);
  const [chartView, setChartView] = useState<"chart" | "table">("chart");

  const all = useApi((s) => api.dataset<ForecastRow>("forecast_detail", { limit: 100000 }, s), []);
  const tl = useTimeline();
  const { filters } = useFilters();

  // ── computed ──────────────────────────────────────────────
  const COL: Record<Dim, keyof ForecastRow> = {
    family: "Product_Family", sku: "SKU_ID", region: "Region", channel: "Sales_Channel", customer: "Customer_Name",
  };
  const rows = useMemo(() => (all.status === "success" ? all.data.rows : []).filter((r) =>
    DIMS.every((d) => !filters[d].length || filters[d].includes(String(r[COL[d]])))),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [all.status, all.data, filters]);

  // calibrated monthly band, revenue and history for the current filters
  const tlMonth = useMemo(() => {
    const m = new Map<YM, { units: number; p10: number; p90: number; revenue: number }>();
    if (tl.status === "success") for (const f of tl.data.forecast)
      m.set(f.Date, { units: f.Units_forecast, p10: f.Units_P10 ?? 0, p90: f.Units_P90 ?? 0, revenue: f.Revenue_forecast });
    return m;
  }, [tl.status, tl.data]);
  const histMonth = useMemo(() => {
    const m = new Map<YM, number>();
    if (tl.status === "success") for (const h of tl.data.history) m.set(h.Date, h.Units_unconstrained);
    return m;
  }, [tl.status, tl.data]);

  const selectedMonths = useMemo(() => monthsInRange(rangeStart, rangeEnd), [rangeStart, rangeEnd]);

  const { units, rows: periodRows } = useMemo(() => aggregate(rows, selectedMonths), [rows, selectedMonths]);
  const p10 = selectedMonths.reduce((s, m) => s + (tlMonth.get(m)?.p10 ?? 0), 0);
  const p90 = selectedMonths.reduce((s, m) => s + (tlMonth.get(m)?.p90 ?? 0), 0);
  const p50 = units;
  const revenue = selectedMonths.reduce((s, m) => s + (tlMonth.get(m)?.revenue ?? 0), 0);

  // per-month totals for calendar cells + chart
  const byMonth = useMemo(() => {
    const m = new Map<YM, { units: number; p10: number; p90: number }>();
    for (const r of rows) {
      const e = m.get(r.Date) ?? { units: 0, p10: 0, p90: 0 };
      e.units += r.Forecast;
      m.set(r.Date, e);
    }
    for (const [ym, e] of m) {             // calibrated band for the filtered aggregate
      e.p10 = tlMonth.get(ym)?.p10 ?? e.units;
      e.p90 = tlMonth.get(ym)?.p90 ?? e.units;
    }
    return m;
  }, [rows, tlMonth]);

  const maxUnits = useMemo(
    () => Math.max(...FORECAST_MONTHS.map((m) => byMonth.get(m)?.units ?? 0), 1),
    [byMonth],
  );

  // prev period for growth
  const prev = useMemo(() => prevEquivPeriod(selectedMonths), [selectedMonths]);
  const prevUnits = useMemo(() => {
    if (!prev) return null;
    // the previous window may be history, forecast or both: recovered demand for history months,
    // the forecast for forecast months
    const out: YM[] = [];
    const [y0, m0] = prev.start.split("-").map(Number);
    const [y1, m1] = prev.end.split("-").map(Number);
    for (let i = y0 * 12 + m0 - 1; i <= y1 * 12 + m1 - 1; i++) out.push(`${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);
    let total = 0;
    for (const ym of out) {
      const v = histMonth.get(ym) ?? byMonth.get(ym)?.units;
      if (v === undefined) return null;
      total += v;
    }
    return total;
  }, [prev, histMonth, byMonth]);

  const growth = prevUnits && prevUnits > 0 ? (units - prevUnits) / prevUnits : null;

  // family breakdown for the period
  const familyBreakdown = useMemo(() => byDim(periodRows, "Product_Family"), [periodRows]);
  const regionBreakdown = useMemo(() => byDim(periodRows, "Region"),         [periodRows]);

  // chart option — monthly bars
  const chartOption = useMemo(() => {
    if (!selectedMonths.length) return null;
    const vals = selectedMonths.map((m) => byMonth.get(m)?.units ?? 0);
    const p10s  = selectedMonths.map((m) => byMonth.get(m)?.p10  ?? 0);
    const p90s  = selectedMonths.map((m) => byMonth.get(m)?.p90  ?? 0);
    return verticalBarsOption(
      selectedMonths.map(fmtMonthShort),
      [
        { name: "P10",      data: p10s, color: "rgba(199,255,50,0.3)" },
        { name: "Forecast", data: vals, color: SERIES[0] },
        { name: "P90",      data: p90s, color: "rgba(199,255,50,0.15)" },
      ],
      { valueFormatter: (v) => fmtInt(v), rotateLabels: true, yAxisName: "Units" },
    );
  }, [selectedMonths, byMonth]);

  // family bar chart
  const familyChart = useMemo(() => {
    if (!familyBreakdown.length) return null;
    return {
      grid: { left: 12, right: 90, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: "item", backgroundColor: "rgba(20,20,20,0.97)", borderColor: "#282828",
        textStyle: { color: "#fff", fontSize: 12 }, padding: [8, 12] },
      xAxis: { type: "value", show: false },
      yAxis: { type: "category", data: familyBreakdown.map(([k]) => k).reverse(),
        axisLabel: { color: "#a1a1a1", fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false } },
      series: [{ type: "bar",
        data: familyBreakdown.map(([, v]) => v).reverse().map((v) => ({
          value: v, itemStyle: { color: SERIES[0], borderRadius: [0, 3, 3, 0] },
        })),
        barMaxWidth: 18,
        label: { show: true, position: "right", color: "#a1a1a1", fontSize: 11,
          formatter: (p: { value: number }) => fmtInt(p.value) },
        emphasis: { focus: "self", itemStyle: { opacity: 0.5 } },
      }],
    };
  }, [familyBreakdown]);

  // region bar chart
  const regionChart = useMemo(() => {
    if (!regionBreakdown.length) return null;
    return {
      grid: { left: 12, right: 80, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: "item", backgroundColor: "rgba(20,20,20,0.97)", borderColor: "#282828",
        textStyle: { color: "#fff", fontSize: 12 }, padding: [8, 12] },
      xAxis: { type: "value", show: false },
      yAxis: { type: "category", data: regionBreakdown.map(([k]) => k).reverse(),
        axisLabel: { color: "#a1a1a1", fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false } },
      series: [{ type: "bar",
        data: regionBreakdown.map(([, v]) => v).reverse().map((v) => ({
          value: v, itemStyle: { color: SERIES[1], borderRadius: [0, 3, 3, 0] },
        })),
        barMaxWidth: 18,
        label: { show: true, position: "right", color: "#a1a1a1", fontSize: 11,
          formatter: (p: { value: number }) => fmtInt(p.value) },
        emphasis: { focus: "self", itemStyle: { opacity: 0.5 } },
      }],
    };
  }, [regionBreakdown]);

  // selected month detail
  const monthDetail = useMemo(() => {
    if (!selectedMonth) return null;
    const monthRows = rows.filter((r) => r.Date === selectedMonth);
    return {
      units:   monthRows.reduce((s, r) => s + r.Forecast, 0),
      p10:     tlMonth.get(selectedMonth)?.p10 ?? 0,
      p90:     tlMonth.get(selectedMonth)?.p90 ?? 0,
      byFamily: byDim(monthRows, "Product_Family"),
      byRegion: byDim(monthRows, "Region"),
      topSKUs:  byDim(monthRows, "SKU_ID").slice(0, 8),
    };
  }, [rows, selectedMonth, tlMonth]);

  /* ── range validation ────────────────────────────────────── */
  const setStart = (v: YM) => {
    setRangeStart(v);
    if (v > rangeEnd) setRangeEnd(v);
  };
  const setEnd = (v: YM) => {
    setRangeEnd(v);
    if (v < rangeStart) setRangeStart(v);
  };

  /* ── demand intensity colour ────────────────────────────── */
  const intensityColor = (ym: YM) => {
    const u = byMonth.get(ym)?.units ?? 0;
    const pct = u / maxUnits;
    if (pct > 0.8)  return "rgba(199,255,50,0.9)";
    if (pct > 0.6)  return "rgba(199,255,50,0.65)";
    if (pct > 0.4)  return "rgba(199,255,50,0.4)";
    if (pct > 0.2)  return "rgba(199,255,50,0.2)";
    return "rgba(199,255,50,0.08)";
  };

  const isInRange    = (ym: YM) => ym >= rangeStart && ym <= rangeEnd;
  const isEdge       = (ym: YM) => ym === rangeStart || ym === rangeEnd;
  const isHover      = (ym: YM) => ym === hoverMonth;
  const isSelected   = (ym: YM) => ym === selectedMonth;

  /* ── render ───────────────────────────────────────────────── */
  return (
    <div className="page">

      {/* ── Header ─────────────────────────────────────────── */}
      <div className="page__intro">
        <div>
          <p className="eyebrow">Calendar Forecast · Date Range Explorer</p>
          <h2 className="page__title">Explore demand and revenue for any forecast period</h2>
          <p className="page__lead">
            Select a date range within the 19-month horizon (Nov 2026 – May 2028). All values are
            monthly model outputs — no daily extrapolation.
          </p>
        </div>
      </div>

      {/* ── Preset quick-select ────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, color: "var(--text-3)", marginRight: 4 }}>Quick select:</span>
        {PRESETS.map((p) => {
          const { start, end } = presetRange(p.months);
          const active = rangeStart === start && rangeEnd === end;
          return (
            <button key={p.label} type="button"
              onClick={() => { setRangeStart(start); setRangeEnd(end); }}
              style={{
                height: 28, padding: "0 12px", borderRadius: "var(--radius-md)",
                border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                background: active ? "var(--accent-soft)" : "transparent",
                color: active ? "var(--accent)" : "var(--text-3)",
                fontSize: 12, fontWeight: active ? 600 : 400, cursor: "pointer",
                transition: "all 0.12s",
              }}>
              {p.label}
            </button>
          );
        })}
      </div>

      {/* ── Date range picker + calendar ───────────────────── */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Forecast calendar" subtitle="Click a month to view details · drag endpoints to change range">
            <div style={{ padding: "16px 20px 20px" }}>
              {/* Year labels + 4-column calendar grid */}
              {[
                { year: 2026, months: FORECAST_MONTHS.filter((m) => m.startsWith("2026")) },
                { year: 2027, months: FORECAST_MONTHS.filter((m) => m.startsWith("2027")) },
                { year: 2028, months: FORECAST_MONTHS.filter((m) => m.startsWith("2028")) },
              ].map(({ year, months }) => (
                <div key={year} style={{ marginBottom: 20 }}>
                  {/* Year header */}
                  <div style={{
                    fontSize: 11, fontWeight: 700, color: "var(--text-3)",
                    textTransform: "uppercase", letterSpacing: "0.1em",
                    marginBottom: 8, paddingBottom: 6,
                    borderBottom: "1px solid var(--border)",
                  }}>
                    {year}
                  </div>
                  {/* Month cells */}
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(4, 1fr)",
                    gap: 8,
                  }}>
                    {months.map((ym) => {
                      const data  = byMonth.get(ym);
                      const pct   = data && maxUnits > 0 ? data.units / maxUnits : 0;
                      const inR   = isInRange(ym);
                      const edge  = isEdge(ym);
                      const hover = isHover(ym);
                      const sel   = isSelected(ym);
                      return (
                        <div
                          key={ym}
                          onClick={() => setSelectedMonth(sel ? null : ym)}
                          onMouseEnter={() => setHoverMonth(ym)}
                          onMouseLeave={() => setHoverMonth(null)}
                          style={{
                            position: "relative",
                            padding: "12px 14px",
                            borderRadius: "var(--radius-md)",
                            border: `1px solid ${
                              edge ? "var(--accent)" :
                              sel  ? "var(--accent)" :
                              inR  ? "rgba(199,255,50,0.3)" :
                              "var(--border)"
                            }`,
                            background: sel
                              ? "rgba(199,255,50,0.1)"
                              : hover
                                ? "var(--surface-2)"
                                : inR
                                  ? "rgba(199,255,50,0.03)"
                                  : "var(--surface-1)",
                            cursor: "pointer",
                            transition: "border-color 0.1s, background 0.1s",
                            minHeight: 90,
                          }}
                        >
                          {/* Month name */}
                          <div style={{
                            fontSize: 13, fontWeight: 600,
                            color: inR ? "var(--text-1)" : "var(--text-3)",
                            marginBottom: 8,
                          }}>
                            {new Date(Date.UTC(...(ym.split("-").map((x, i) => i === 1 ? +x - 1 : +x) as [number, number]))).toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })}
                          </div>

                          {/* Demand bar */}
                          <div style={{ height: 3, borderRadius: 2, background: "var(--surface-3)", marginBottom: 8, overflow: "hidden" }}>
                            <div style={{
                              height: "100%",
                              width: `${pct * 100}%`,
                              background: inR ? intensityColor(ym) : "rgba(255,255,255,0.1)",
                              borderRadius: 2,
                              transition: "width 0.4s",
                            }} />
                          </div>

                          {/* Units */}
                          {all.status === "loading" ? (
                            <div style={{ height: 14, width: 60, background: "var(--surface-3)", borderRadius: 3 }} />
                          ) : data ? (
                            <div style={{ fontSize: 12, fontWeight: inR ? 600 : 400, color: inR ? "var(--accent)" : "var(--text-3)", fontVariantNumeric: "tabular-nums" }}>
                              {fmtInt(data.units)}
                              <span style={{ fontSize: 10, fontWeight: 400, color: "var(--text-3)", marginLeft: 3 }}>u</span>
                            </div>
                          ) : (
                            <div style={{ fontSize: 11, color: "var(--text-3)" }}>—</div>
                          )}

                          {/* START / END badge */}
                          {(ym === rangeStart || ym === rangeEnd) && (
                            <div style={{
                              position: "absolute", bottom: 6, right: 8,
                              fontSize: 9, fontWeight: 700, color: "var(--accent)",
                              letterSpacing: "0.06em", textTransform: "uppercase",
                            }}>
                              {ym === rangeStart && ym === rangeEnd ? "S/E" : ym === rangeStart ? "Start" : "End"}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {/* Range hint */}
              <p style={{ marginTop: 4, fontSize: 11, color: "var(--text-3)" }}>
                Selected: <strong style={{ color: "var(--text-2)" }}>{ymLabel(rangeStart)} → {ymLabel(rangeEnd)}</strong>
                {" · "}<span style={{ color: "var(--accent)" }}>{selectedMonths.length} month{selectedMonths.length !== 1 ? "s" : ""}</span>
                {" · "}Click a cell for month detail
              </p>
            </div>
          </Card>
        </div>

        {/* ── Range pickers ──────────────────────────────── */}
        <div className="ov-grid__side" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card title="Date range" subtitle="Adjust the forecast period">
            <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                  Start month
                </label>
                <select
                  value={rangeStart}
                  onChange={(e) => setStart(e.target.value)}
                  style={{
                    width: "100%", height: 36, padding: "0 10px",
                    background: "var(--surface-2)", border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)", color: "var(--text-1)", fontSize: 13,
                  }}
                >
                  {FORECAST_MONTHS.map((m) => (
                    <option key={m} value={m}>{ymLabel(m)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                  End month
                </label>
                <select
                  value={rangeEnd}
                  onChange={(e) => setEnd(e.target.value)}
                  style={{
                    width: "100%", height: 36, padding: "0 10px",
                    background: "var(--surface-2)", border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)", color: "var(--text-1)", fontSize: 13,
                  }}
                >
                  {FORECAST_MONTHS.filter((m) => m >= rangeStart).map((m) => (
                    <option key={m} value={m}>{ymLabel(m)}</option>
                  ))}
                </select>
              </div>
              <div style={{ padding: "10px 12px", background: "var(--surface-2)", borderRadius: "var(--radius-md)", fontSize: 12, color: "var(--text-3)", lineHeight: 1.6 }}>
                <div>Months selected: <strong style={{ color: "var(--accent)" }}>{selectedMonths.length}</strong></div>
                <div>Horizon: <strong style={{ color: "var(--text-2)" }}>Nov 2026 – May 2028</strong></div>
                <div style={{ marginTop: 6, fontSize: 11 }}>Forecasts are monthly — no daily extrapolation.</div>
              </div>
              <button
                type="button"
                className="btn btn--accent"
                disabled={all.status !== "success" || !selectedMonths.length}
                onClick={() => downloadCsv(periodRows, rangeStart, rangeEnd)}
                style={{ width: "100%", marginTop: 4 }}
              >
                <Icon name="download" size={15} />
                Export CSV · {selectedMonths.length}m selected
              </button>
            </div>
          </Card>

          {/* Month detail panel */}
          {selectedMonth && monthDetail && (
            <Card title={ymLabel(selectedMonth)} subtitle="Month detail — click any calendar cell">
              <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  {[
                    { k: "Forecast", v: fmtInt(monthDetail.units) },
                    { k: "P10",      v: fmtInt(monthDetail.p10) },
                    { k: "P90",      v: fmtInt(monthDetail.p90) },
                    { k: "Band width", v: `±${fmtInt((monthDetail.p90 - monthDetail.p10) / 2)}` },
                  ].map(({ k, v }) => (
                    <div key={k} style={{ padding: "8px 10px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                      <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{k}</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-1)", marginTop: 2 }}>{v}</div>
                    </div>
                  ))}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>By family</div>
                  {monthDetail.byFamily.slice(0, 5).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-2)", padding: "3px 0", borderBottom: "1px solid var(--border)" }}>
                      <span>{k}</span>
                      <span style={{ color: "var(--accent)", fontWeight: 600 }}>{fmtInt(v)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>By region</div>
                  {monthDetail.byRegion.slice(0, 5).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-2)", padding: "3px 0", borderBottom: "1px solid var(--border)" }}>
                      <span>{k}</span>
                      <span style={{ color: SERIES[1], fontWeight: 600 }}>{fmtInt(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* ── KPI row ────────────────────────────────────────── */}
      {all.status === "loading" ? (
        <div className="kpi-row"><Skeleton height={128} /></div>
      ) : all.status === "error" ? (
        <Card><ErrorState error={all.error} onRetry={all.retry} /></Card>
      ) : (
        <section className="kpi-row" aria-label="Period summary">
          <KpiTile
            label="Total forecast demand" emphasis="accent"
            value={fmtInt(units)} unit="units"
            sub={`${selectedMonths.length}m period · ${ymLabel(rangeStart)} – ${ymLabel(rangeEnd)} · ${tl.status === "success" ? _fmtUsd(revenue, 2) : "…"} revenue`}
            footnote="Sum of monthly forecasts · revenue at the announced list prices"
          />
          <KpiTile
            label="Demand growth"
            emphasis={growth !== null && growth >= 0 ? "accent" : undefined}
            value={growth !== null ? fmtPct(growth, 1) : "—"}
            sub={growth !== null
              ? `vs the previous ${selectedMonths.length} months (actual demand where in history)`
              : "Previous period not available"}
            footnote="Previous equivalent window"
          />
          <KpiTile
            label="P10 – P90 range"
            value={`${fmtInt(p10)} – ${fmtInt(p90)}`}
            sub={`Band width: ±${fmtInt((p90 - p10) / 2)}`}
            footnote={tl.status === "success" ? `Sum of monthly bands · ${tl.data.band_method}` : "Calibrated uncertainty bounds"}
          />
          <KpiTile
            label="SKU-regions"
            value={String(new Set(periodRows.map((r) => `${r.SKU_ID}|${r.Region}`)).size)}
            unit="active"
            sub={`across ${new Set(periodRows.map((r) => r.Product_Family)).size} families, ${new Set(periodRows.map((r) => r.Region)).size} regions`}
            footnote="Distinct series in the period"
          />
        </section>
      )}

      {/* ── Forecast chart ─────────────────────────────────── */}
      {selectedMonths.length > 0 && (
        <Card
          title="Monthly forecast for selected period"
          subtitle={`${ymLabel(rangeStart)} – ${ymLabel(rangeEnd)} · units (Forecast, P10, P90)`}
        >
          <div style={{ padding: "12px 20px 8px", display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end" }}>
            {(["chart", "table"] as const).map((v) => (
              <button key={v} type="button"
                onClick={() => setChartView(v)}
                style={{
                  height: 28, padding: "0 12px", borderRadius: "var(--radius-md)",
                  border: `1px solid ${chartView === v ? "var(--accent)" : "var(--border)"}`,
                  background: chartView === v ? "var(--accent-soft)" : "transparent",
                  color: chartView === v ? "var(--accent)" : "var(--text-3)",
                  fontSize: 12, fontWeight: chartView === v ? 600 : 400, cursor: "pointer",
                  transition: "all 0.12s",
                }}>
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          {chartView === "chart" ? (
            <div style={{ padding: "0 20px 20px" }}>
              {all.status === "loading" ? <Skeleton height={280} /> :
                chartOption ? <EChart height={280} label="Monthly forecast" option={chartOption} /> :
                  <EmptyState title="No data for period" icon="database" />}
            </div>
          ) : (
            <div style={{ padding: "0 20px 20px", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr>
                    {["Month", "P10", "Forecast", "P90", "Band width"].map((h) => (
                      <th key={h} style={{ textAlign: h === "Month" ? "left" : "right", padding: "8px 10px", borderBottom: "1px solid var(--border)", fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {selectedMonths.map((ym) => {
                    const d = byMonth.get(ym);
                    return (
                      <tr key={ym} style={{ borderBottom: "1px solid var(--border)" }}
                        onMouseEnter={(e) => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                        onMouseLeave={(e) => (e.currentTarget as HTMLElement).style.background = ""}
                      >
                        <td style={{ padding: "8px 10px", color: "var(--text-1)", fontWeight: 500 }}>{ymLabel(ym)}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", color: "var(--text-3)" }}>{d ? fmtInt(d.p10) : "—"}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", color: "var(--accent)", fontWeight: 600 }}>{d ? fmtInt(d.units) : "—"}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", color: "var(--text-3)" }}>{d ? fmtInt(d.p90) : "—"}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", color: "var(--text-2)" }}>{d ? `±${fmtInt((d.p90 - d.p10) / 2)}` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* ── Family + Region breakdown ───────────────────────── */}
      {periodRows.length > 0 && (
        <div className="ov-grid">
          <div className="ov-grid__main">
            <Card title="Demand by product family" subtitle="Forecast units for the selected period">
              {all.status === "loading" ? <Skeleton height={240} /> :
                familyChart ? <div style={{ padding: "12px 20px 20px" }}><EChart height={240} label="By family" option={familyChart} /></div>
                  : <EmptyState title="No data" icon="database" />}
            </Card>
          </div>
          <div className="ov-grid__side">
            <Card title="Demand by region" subtitle="Forecast units for the selected period">
              {all.status === "loading" ? <Skeleton height={240} /> :
                regionChart ? <div style={{ padding: "12px 20px 20px" }}><EChart height={240} label="By region" option={regionChart} /></div>
                  : <EmptyState title="No data" icon="database" />}
            </Card>
          </div>
        </div>
      )}

      {/* ── Period insights ─────────────────────────────────── */}
      {periodRows.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>

          {/* Demand insights */}
          <Card title="Demand insights" subtitle="Computed from selected period">
            <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 8, fontSize: 13 }}>
              {[
                {
                  k: "Total demand",
                  v: `${fmtInt(units)} units over ${selectedMonths.length} months`,
                  col: "var(--accent)",
                },
                {
                  k: "Monthly average",
                  v: `${fmtInt(units / selectedMonths.length)} units / month`,
                  col: "var(--text-2)",
                },
                {
                  k: "Growth vs prior period",
                  v: growth !== null ? `${fmtPct(growth, 1)} vs the previous ${selectedMonths.length} months` : "Previous period not available",
                  col: growth !== null ? (growth >= 0 ? "var(--accent)" : "var(--critical)") : "var(--text-3)",
                },
                {
                  k: "Peak month",
                  v: (() => {
                    const best = [...selectedMonths].sort((a, b) => (byMonth.get(b)?.units ?? 0) - (byMonth.get(a)?.units ?? 0))[0];
                    return best ? `${ymLabel(best)} · ${fmtInt(byMonth.get(best)?.units ?? 0)} units` : "—";
                  })(),
                  col: "var(--text-2)",
                },
                {
                  k: "Lowest month",
                  v: (() => {
                    const worst = [...selectedMonths].sort((a, b) => (byMonth.get(a)?.units ?? 0) - (byMonth.get(b)?.units ?? 0))[0];
                    return worst ? `${ymLabel(worst)} · ${fmtInt(byMonth.get(worst)?.units ?? 0)} units` : "—";
                  })(),
                  col: "var(--text-3)",
                },
                {
                  k: "Band width",
                  v: `P90 is ${fmtPct((p90 - p50) / p50, 1)} above forecast`,
                  col: "var(--text-2)",
                },
              ].map(({ k, v, col }) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 10px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)", gap: 12 }}>
                  <span style={{ color: "var(--text-3)", flexShrink: 0 }}>{k}</span>
                  <span style={{ color: col, fontWeight: 500, textAlign: "right" }}>{v}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Product insights */}
          <Card title="Product insights" subtitle="Top families and growth signals">
            <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Highest demand families</div>
              {familyBreakdown.slice(0, 4).map(([k, v], i) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 10px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                  <span style={{ color: "var(--text-2)" }}>
                    <span style={{ color: "var(--text-3)", marginRight: 8, fontFamily: "var(--font-mono)", fontSize: 11 }}>#{i + 1}</span>
                    {k}
                  </span>
                  <span style={{ color: "var(--accent)", fontWeight: 600 }}>{fmtInt(v)}</span>
                </div>
              ))}
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 8, marginBottom: 4 }}>Family share</div>
              {familyBreakdown.slice(0, 4).map(([k, v]) => (
                <div key={k} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                  <span style={{ color: "var(--text-3)", width: 170, flexShrink: 0 }}>{k}</span>
                  <div style={{ flex: 1, height: 6, background: "var(--surface-3)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${(v / units) * 100}%`, background: "var(--accent)", borderRadius: 3 }} />
                  </div>
                  <span style={{ color: "var(--text-3)", width: 40, textAlign: "right", fontSize: 11 }}>{fmtPct(v / units, 0)}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Regional insights */}
          <Card title="Regional insights" subtitle="Demand split by region">
            <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
              {regionBreakdown.map(([k, v], i) => (
                <div key={k} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ color: "var(--text-3)", fontFamily: "var(--font-mono)", fontSize: 11, width: 20 }}>#{i + 1}</span>
                  <span style={{ color: "var(--text-2)", flex: 1 }}>{k}</span>
                  <div style={{ width: 80, height: 5, background: "var(--surface-3)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${(v / units) * 100}%`, background: SERIES[1], borderRadius: 2 }} />
                  </div>
                  <span style={{ color: SERIES[1], fontWeight: 600, width: 72, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmtInt(v)}</span>
                  <span style={{ color: "var(--text-3)", width: 40, textAlign: "right", fontSize: 11 }}>{fmtPct(v / units, 0)}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Procurement insights */}
          <Card title="Procurement guidance" subtitle="P90-based requirements for the selected period">
            <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 8, fontSize: 13 }}>
              {[
                {
                  k: "P90 procurement quantity",
                  v: `${fmtInt(p90)} units (conservative)`,
                  col: "var(--warning)",
                },
                {
                  k: "Safety buffer vs P50",
                  v: `+${fmtInt(p90 - p50)} units (${fmtPct((p90 - p50) / p50, 1)} above forecast)`,
                  col: "var(--text-2)",
                },
                {
                  k: "Months covered",
                  v: `${selectedMonths.length} delivery months`,
                  col: "var(--text-2)",
                },
                {
                  k: "Largest family need (P50)",
                  v: familyBreakdown[0] ? `${familyBreakdown[0][0]}: ${fmtInt(familyBreakdown[0][1])} units` : "—",
                  col: "var(--accent)",
                },
                {
                  k: "Planning basis",
                  v: "Global LightGBM · Tweedie loss · frozen C9c",
                  col: "var(--text-3)",
                },
              ].map(({ k, v, col }) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 10px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)", gap: 12 }}>
                  <span style={{ color: "var(--text-3)", flexShrink: 0 }}>{k}</span>
                  <span style={{ color: col, fontWeight: 500, textAlign: "right" }}>{v}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────── */}
      {all.status === "loading" && <Card><Skeleton height={300} /></Card>}
      {all.status === "error"   && <Card><ErrorState error={all.error} onRetry={all.retry} /></Card>}
      {all.status === "success" && selectedMonths.length === 0 && (
        <Card><EmptyState title="Select a date range to begin" icon="calendar" /></Card>
      )}
    </div>
  );
}
