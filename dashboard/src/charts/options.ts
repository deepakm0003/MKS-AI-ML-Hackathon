/**
 * Pure ECharts option builders (unit-tested). Rules applied: one y-axis per chart, history in
 * neutral ink and forecast in the accent series, the P10-P90 band as a translucent stacked area,
 * the forecast window shaded and marked, compact axis labels, crosshair tooltip.
 */
import type { EChartsCoreOption } from "echarts/core";
import type { BreakdownRow, TimelineView } from "../api/types";
import { fmtMonthShort, fmtPctPoints, fmtUnits, fmtUsd } from "../lib/format";
import { CHART, SERIES } from "../theme/chart";

export type Metric = "units" | "revenue";

export interface TimelineRow {
  date: string;
  actual: number | null;      // recovered (unconstrained) demand
  shipped: number | null;     // shipped units / invoiced revenue
  forecast: number | null;
  p10: number | null;
  p90: number | null;
}

/** Merge history and forecast into one continuous monthly series for the chosen metric. */
export function timelineRows(v: TimelineView, metric: Metric): TimelineRow[] {
  const rows = new Map<string, TimelineRow>();
  const get = (d: string) => {
    if (!rows.has(d)) rows.set(d, { date: d, actual: null, shipped: null, forecast: null, p10: null, p90: null });
    return rows.get(d)!;
  };
  for (const h of v.history) {
    const r = get(h.Date);
    r.actual = metric === "units" ? h.Units_unconstrained : h.Revenue_unconstrained;
    r.shipped = metric === "units" ? h.Units_shipped : h.Revenue_shipped;
  }
  for (const f of v.forecast) {
    const r = get(f.Date);
    r.forecast = metric === "units" ? f.Units_forecast : f.Revenue_forecast;
    r.p10 = metric === "units" ? f.Units_P10 : f.Revenue_P10;
    r.p90 = metric === "units" ? f.Units_P90 : f.Revenue_P90;
  }
  return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function timelineOption(v: TimelineView, metric: Metric, opts: { showShipped?: boolean; fromMonth?: string } = {}): EChartsCoreOption {
  const fmt = metric === "units" ? (x: number) => fmtUnits(x, 1) : (x: number) => fmtUsd(x, 1);
  let rows = timelineRows(v, metric);
  if (opts.fromMonth) rows = rows.filter((r) => r.date >= opts.fromMonth!);
  const firstFc = rows.findIndex((r) => r.forecast !== null);
  const lastHist = firstFc > 0 ? firstFc - 1 : -1;
  const dates = rows.map((r) => r.date);
  // bridge: the forecast line starts at the last actual so history and forecast read as one line
  const forecast = rows.map((r, i) => (i === lastHist ? r.actual : r.forecast));
  const lower = rows.map((r) => r.p10);
  const width = rows.map((r) => (r.p10 !== null && r.p90 !== null ? r.p90 - r.p10 : null));

  return {
    animationDuration: 400,
    grid: { left: 8, right: 16, top: 44, bottom: 8, containLabel: true },
    legend: {
      top: 0, left: 0,
      data: [{ name: "Actual demand" }, ...(opts.showShipped ? [{ name: "Shipped" }] : []), { name: "Forecast" }, { name: "P10–P90 range" }],
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0;
        const r = rows[i];
        const lines = [`<b>${fmtMonthShort(r.date)}</b>`];
        if (r.actual !== null) lines.push(`Actual demand <b>${fmt(r.actual)}</b>`);
        if (opts.showShipped && r.shipped !== null) lines.push(`Shipped ${fmt(r.shipped)}`);
        if (r.forecast !== null) lines.push(`Forecast <b>${fmt(r.forecast)}</b>`);
        if (r.p10 !== null && r.p90 !== null) lines.push(`Range ${fmt(r.p10)} – ${fmt(r.p90)}`);
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "category", data: dates, boundaryGap: false,
      axisLabel: { formatter: (d: string) => fmtMonthShort(d), hideOverlap: true, color: CHART.textMuted },
    },
    // line chart: the axis follows the data (scale) so month-to-month movement stays visible
    yAxis: { type: "value", scale: true, axisLabel: { formatter: (x: number) => fmt(x) }, splitNumber: 4 },
    // zoom with Ctrl + wheel or drag; a plain wheel keeps scrolling the page
    dataZoom: [{ type: "inside", filterMode: "none", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false, moveOnMouseMove: true }],
    series: [
      { name: "P10–P90 lower", type: "line", data: lower, stack: "band", lineStyle: { opacity: 0 }, symbol: "none",
        tooltip: { show: false }, silent: true, legendHoverLink: false },
      { name: "P10–P90 range", type: "line", data: width, stack: "band", lineStyle: { opacity: 0 }, symbol: "none",
        areaStyle: { color: CHART.band }, itemStyle: { color: CHART.band }, silent: true },
      { name: "Actual demand", type: "line", data: rows.map((r) => r.actual), itemStyle: { color: CHART.history },
        lineStyle: { width: 2, color: CHART.history } },
      ...(opts.showShipped ? [{ name: "Shipped", type: "line", data: rows.map((r) => r.shipped),
        itemStyle: { color: CHART.textMuted }, lineStyle: { width: 1, type: "dashed", color: CHART.textMuted } }] : []),
      { name: "Forecast", type: "line", data: forecast, itemStyle: { color: SERIES[0] }, lineStyle: { width: 2, color: SERIES[0] },
        markArea: firstFc >= 0 ? { silent: true, itemStyle: { color: "rgba(34, 211, 238, 0.04)" },
          data: [[{ xAxis: dates[firstFc] }, { xAxis: dates[dates.length - 1] }]] } : undefined,
        markLine: firstFc >= 0 ? { silent: true, symbol: "none", label: { formatter: "Forecast", color: CHART.textMuted, position: "end", fontSize: 11 },
          lineStyle: { color: CHART.axis, type: "dashed", width: 1 }, data: [{ xAxis: dates[firstFc] }] } : undefined },
    ],
  };
}

export type BarValue = "Revenue_next12" | "Units_next12" | "Units_change_pct" | "Revenue_change_pct";

/** Horizontal ranked bars - one series, one hue; the change % rides along as a label. */
export function rankedBarsOption(rows: BreakdownRow[], value: BarValue): EChartsCoreOption {
  const isPct = value.endsWith("_pct");
  const fmt = isPct ? (x: number) => fmtPctPoints(x) : value.startsWith("Revenue") ? (x: number) => fmtUsd(x, 1) : (x: number) => fmtUnits(x, 1);
  const sorted = [...rows].sort((a, b) => ((b[value] ?? -Infinity) as number) - ((a[value] ?? -Infinity) as number)).reverse();
  const change = value.startsWith("Revenue") ? "Revenue_change_pct" : "Units_change_pct";
  return {
    animationDuration: 400,
    grid: { left: 8, right: isPct ? 48 : 116, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "item",
      formatter: (p: { dataIndex: number }) => {
        const r = sorted[p.dataIndex];
        return [`<b>${r.Member}</b>`, `Next 12 m: ${fmtUsd(r.Revenue_next12, 1)} · ${fmtUnits(r.Units_next12, 1)} units`,
          `vs last 12 m: ${fmtPctPoints(r.Units_change_pct)} units · ${fmtPctPoints(r.Revenue_change_pct)} revenue`].join("<br/>");
      },
    },
    xAxis: { type: "value", show: isPct, axisLabel: { formatter: (x: number) => fmt(x) }, splitLine: { show: isPct } },
    yAxis: { type: "category", data: sorted.map((r) => r.Member), axisLabel: { color: CHART.text, width: 150, overflow: "truncate" } },
    series: [{
      type: "bar", data: sorted.map((r) => r[value]), barMaxWidth: 18,
      itemStyle: { color: SERIES[0], borderRadius: [0, CHART.barRadius, CHART.barRadius, 0] },
      label: {
        show: true, position: "right", color: CHART.text, fontSize: 12,
        formatter: (p: { dataIndex: number; value: number }) =>
          isPct ? fmt(p.value) : `${fmt(p.value)}  ${fmtPctPoints(sorted[p.dataIndex][change])}`,
      },
    }],
  };
}
