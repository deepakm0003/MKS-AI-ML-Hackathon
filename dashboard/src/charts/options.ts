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
  const actualName = metric === "units" ? "Actual demand" : "Actual revenue";
  const shippedName = metric === "units" ? "Shipped" : "Invoiced";

  return {
    animationDuration: 400,
    animationEasing: "cubicOut",
    grid: { left: 12, right: 16, top: 40, bottom: 8, containLabel: true },
    legend: {
      top: 4, left: 0, itemGap: 16, textStyle: { fontSize: 12, color: CHART.text },
      data: [
        { name: actualName, icon: "circle" }, 
        ...(opts.showShipped ? [{ name: shippedName, icon: "rect" }] : []), 
        { name: "Forecast", icon: "circle" }, 
        { name: "P10–P90 range", icon: "rect" }
      ],
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", lineStyle: { color: CHART.highlight, width: 1, type: "dashed" } },
      backgroundColor: "rgba(20, 20, 20, 0.97)",
      borderColor: "#282828",
      borderWidth: 1,
      textStyle: { color: "#ffffff", fontSize: 12 },
      padding: [10, 14],
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0;
        const r = rows[i];
        const lines = [`<div style="font-weight:600;margin-bottom:6px;font-size:13px;">${fmtMonthShort(r.date)}</div>`];
        if (r.actual !== null) lines.push(`<span style="color:${CHART.history}">●</span> ${actualName}: <b>${fmt(r.actual)}</b>`);
        if (opts.showShipped && r.shipped !== null) lines.push(`<span style="color:${CHART.textMuted}">▬</span> ${shippedName}: ${fmt(r.shipped)}`);
        if (r.forecast !== null) lines.push(`<span style="color:${SERIES[0]}">●</span> Forecast: <b>${fmt(r.forecast)}</b>`);
        if (r.p10 !== null && r.p90 !== null) lines.push(`<span style="color:${CHART.band}">▬</span> Range: ${fmt(r.p10)} – ${fmt(r.p90)}`);
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "category", data: dates, boundaryGap: false,
      axisLabel: { formatter: (d: string) => fmtMonthShort(d), hideOverlap: true, color: CHART.textMuted, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART.axis } },
      axisTick: { show: false },
    },
    yAxis: { 
      type: "value", scale: true, 
      axisLabel: { formatter: (x: number) => fmt(x), color: CHART.textMuted, fontSize: 11 }, 
      splitNumber: 5,
      splitLine: { lineStyle: { color: CHART.grid, width: 1 } },
      axisLine: { show: false },
    },
    // Simple mouse wheel zoom - no slider, just scroll
    dataZoom: [
      { 
        type: "inside", 
        filterMode: "none", 
        zoomOnMouseWheel: true,      // Direct mouse wheel zoom
        moveOnMouseMove: true,        // Drag to pan
        moveOnMouseWheel: false,      // Scroll doesn't move page
        zoomLock: false,
        throttle: 50,
        minValueSpan: 5,              // Minimum 5 months visible
      },
    ],
    toolbox: {
      show: true,
      feature: {
        dataZoom: {
          yAxisIndex: "none",
          title: { zoom: "Zoom", back: "Reset" },
        },
        restore: { title: "Reset" },
        saveAsImage: { title: "Download", pixelRatio: 2, backgroundColor: CHART.surface },
      },
      iconStyle: { borderColor: CHART.textMuted },
      emphasis: { iconStyle: { borderColor: SERIES[0] } },
      top: 4,
      right: 4,
    },
    series: [
      { 
        name: "P10–P90 lower", 
        type: "line", 
        data: lower, 
        stack: "band", 
        lineStyle: { opacity: 0 }, 
        symbol: "none",
        tooltip: { show: false }, 
        silent: true, 
        legendHoverLink: false 
      },
      { 
        name: "P10–P90 range", 
        type: "line", 
        data: width, 
        stack: "band", 
        lineStyle: { opacity: 0 }, 
        symbol: "none",
        areaStyle: { color: CHART.band, opacity: 0.6 }, 
        itemStyle: { color: CHART.band }, 
        silent: true,
        emphasis: { disabled: true },
      },
      { 
        name: actualName, 
        type: "line", 
        data: rows.map((r) => r.actual), 
        itemStyle: { color: CHART.history },
        lineStyle: { width: 1.5, color: CHART.history },
        symbolSize: 0,
        smooth: false,
        emphasis: {
          focus: "series",
          lineStyle: { width: 2 },
        },
      },
      ...(opts.showShipped ? [{
        name: shippedName, 
        type: "line", 
        data: rows.map((r) => r.shipped),
        itemStyle: { color: CHART.textMuted }, 
        lineStyle: { width: 1, type: "dashed" as const, color: CHART.textMuted },
        symbolSize: 0,
        emphasis: { focus: "series" },
      }] : []),
      { 
        name: "Forecast", 
        type: "line", 
        data: forecast, 
        itemStyle: { color: SERIES[0] }, 
        lineStyle: { width: 2, color: SERIES[0] },
        symbolSize: 0,
        smooth: false,
        emphasis: {
          focus: "series",
          lineStyle: { width: 2.5 },
        },
        markArea: firstFc >= 0 ? { 
          silent: true, 
          itemStyle: { color: CHART.bandDark },
          data: [[{ xAxis: dates[firstFc] }, { xAxis: dates[dates.length - 1] }]] 
        } : undefined,
        markLine: firstFc >= 0 ? { 
          silent: true, 
          symbol: "none", 
          label: { 
            formatter: "Forecast →", 
            color: CHART.textMuted, 
            position: "insideEndTop", 
            fontSize: 11,
            fontWeight: 500,
          },
          lineStyle: { color: CHART.axis, type: "dashed" as const, width: 1 }, 
          data: [{ xAxis: dates[firstFc] }],
          emphasis: { disabled: true },
        } : undefined 
      },
    ],
  };
}

export type BarValue = "Revenue_next12" | "Units_next12" | "Units_change_pct" | "Revenue_change_pct";

/** Horizontal ranked bars - clean, professional style */
export function rankedBarsOption(rows: BreakdownRow[], value: BarValue): EChartsCoreOption {
  const isPct = value.endsWith("_pct");
  const fmt = isPct ? (x: number) => fmtPctPoints(x) : value.startsWith("Revenue") ? (x: number) => fmtUsd(x, 1) : (x: number) => fmtUnits(x, 1);
  const sorted = [...rows].sort((a, b) => ((b[value] ?? -Infinity) as number) - ((a[value] ?? -Infinity) as number)).reverse();
  const change = value.startsWith("Revenue") ? "Revenue_change_pct" : "Units_change_pct";
  
  return {
    animationDuration: 400,
    animationEasing: "cubicOut",
    grid: { left: 12, right: isPct ? 48 : 120, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(20, 20, 20, 0.97)",
      borderColor: "#282828",
      borderWidth: 1,
      textStyle: { color: "#ffffff", fontSize: 12 },
      padding: [10, 14],
      formatter: (p: { dataIndex: number }) => {
        const r = sorted[p.dataIndex];
        return [
          `<div style="font-weight:600;margin-bottom:8px;">${r.Member}</div>`,
          `<div>Revenue: <b>${fmtUsd(r.Revenue_next12, 1)}</b></div>`,
          `<div>Units: <b>${fmtUnits(r.Units_next12, 1)}</b></div>`,
          `<div style="margin-top:6px;">vs Last 12m</div>`,
          `<div>Units: <b>${fmtPctPoints(r.Units_change_pct)}</b></div>`,
          `<div>Revenue: <b>${fmtPctPoints(r.Revenue_change_pct)}</b></div>`,
        ].join("");
      },
    },
    xAxis: { 
      type: "value", 
      show: isPct, 
      axisLabel: { formatter: (x: number) => fmt(x), color: CHART.textMuted, fontSize: 11 }, 
      splitLine: { show: isPct, lineStyle: { color: CHART.grid } },
      axisLine: { show: false },
    },
    yAxis: { 
      type: "category", 
      data: sorted.map((r) => r.Member), 
      axisLabel: { color: CHART.text, width: 150, overflow: "truncate", fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [{
      type: "bar", 
      data: sorted.map((r) => ({
        value: r[value],
        itemStyle: {
          color: SERIES[0],
          borderRadius: [0, CHART.barRadius, CHART.barRadius, 0],
        },
      })),
      barMaxWidth: 20,
      label: {
        show: true, 
        position: "right", 
        color: CHART.text, 
        fontSize: 12,
        fontWeight: 500,
        formatter: (p: { dataIndex: number; value: number }) =>
          isPct 
            ? fmt(p.value) 
            : `${fmt(p.value)}  ${fmtPctPoints(sorted[p.dataIndex][change])}`,
      },
      emphasis: {
        focus: "self",
        itemStyle: {
          opacity: 0.5,
        },
      },
    }],
  };
}

export interface BarSeries {
  name: string;
  data: (number | null)[];
  color?: string;
}

/** Vertical bar chart - one or more series of bars on a shared category axis. */
export function verticalBarsOption(
  categories: string[],
  series: BarSeries[],
  opts: {
    valueFormatter?: (v: number) => string;
    showLabels?: boolean;
    rotateLabels?: boolean;
    yAxisName?: string;
    barMaxWidth?: number;
  } = {},
): EChartsCoreOption {
  const fmt = opts.valueFormatter ?? ((v: number) => String(v));
  const multi = series.length > 1;
  return {
    animationDuration: 400,
    animationEasing: "cubicOut",
    grid: { left: 12, right: 16, top: multi ? 40 : 16, bottom: 8, containLabel: true },
    legend: multi ? {
      top: 4, left: 0, itemGap: 16, textStyle: { fontSize: 12, color: CHART.text },
      data: series.map((s) => ({ name: s.name, icon: "circle" })),
    } : undefined,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(20, 20, 20, 0.97)",
      borderColor: "#282828",
      borderWidth: 1,
      textStyle: { color: "#ffffff", fontSize: 12 },
      padding: [10, 14],
      formatter: (params: { seriesName: string; color: string; value: number; axisValueLabel: string }[]) => {
        const lines = [`<div style="font-weight:600;margin-bottom:6px;font-size:13px;">${params[0].axisValueLabel}</div>`];
        for (const p of params) lines.push(`<span style="color:${p.color}">●</span> ${p.seriesName}: <b>${fmt(p.value)}</b>`);
        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "category", data: categories, boundaryGap: true,
      axisLabel: { color: CHART.textMuted, fontSize: 11, rotate: opts.rotateLabels ? 30 : 0, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.axis } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value", name: opts.yAxisName,
      nameTextStyle: { color: CHART.textMuted, fontSize: 11, padding: [0, 0, 0, 40] },
      axisLabel: { color: CHART.textMuted, fontSize: 11, formatter: (v: number) => fmt(v) },
      splitLine: { lineStyle: { color: CHART.grid, width: 1 } },
      axisLine: { show: false },
    },
    series: series.map((s, i) => ({
      name: s.name,
      type: "bar" as const,
      data: s.data,
      barMaxWidth: opts.barMaxWidth ?? 40,
      itemStyle: { color: s.color ?? SERIES[i % SERIES.length], borderRadius: [4, 4, 0, 0] },
      label: opts.showLabels ? {
        show: true, position: "top", color: CHART.text, fontSize: 11, fontWeight: 500,
        formatter: (p: { value: number }) => fmt(p.value),
      } : undefined,
      emphasis: { focus: "series" as const, itemStyle: { opacity: 0.5 } },
    })),
  };
}

/** Generic horizontal ranked bars - works with any {label, value, sub?} data. */
export function genericRankedBarsOption(
  items: { label: string; value: number; sub?: string | number }[],
  opts: { valueFormatter?: (v: number) => string; subFormatter?: (v: number) => string; color?: string } = {},
): EChartsCoreOption {
  const fmt = opts.valueFormatter ?? ((v: number) => String(v));
  const sorted = [...items].sort((a, b) => b.value - a.value).reverse();
  return {
    animationDuration: 400,
    animationEasing: "cubicOut",
    grid: { left: 12, right: opts.subFormatter ? 120 : 60, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(20, 20, 20, 0.97)",
      borderColor: "#282828",
      borderWidth: 1,
      textStyle: { color: "#ffffff", fontSize: 12 },
      padding: [10, 14],
      formatter: (p: { dataIndex: number }) => {
        const r = sorted[p.dataIndex];
        return `<div style="font-weight:600;margin-bottom:4px;">${r.label}</div>` +
          `<div>Value: <b>${fmt(r.value)}</b></div>` +
          (r.sub !== undefined ? `<div style="color:#8b949e;">${opts.subFormatter ? opts.subFormatter(r.sub as unknown as number) : r.sub}</div>` : "");
      },
    },
    xAxis: { type: "value", show: false, axisLine: { show: false }, splitLine: { show: false } },
    yAxis: {
      type: "category", data: sorted.map((r) => r.label),
      axisLabel: { color: CHART.text, width: 150, overflow: "truncate", fontSize: 12 },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: sorted.map((r) => ({ value: r.value, itemStyle: { color: opts.color ?? SERIES[0], borderRadius: [0, 4, 4, 0] } })),
      barMaxWidth: 22,
      label: {
        show: true, position: "right", color: CHART.text, fontSize: 12, fontWeight: 500,
        formatter: (p: { dataIndex: number; value: number }) => {
          const r = sorted[p.dataIndex];
          const base = fmt(p.value);
          return r.sub !== undefined && opts.subFormatter ? `${base}  ${opts.subFormatter(r.sub as unknown as number)}` : base;
        },
      },
      emphasis: { focus: "self", itemStyle: { opacity: 0.5 } },
    }],
  };
}

/** Scatter chart for 2-D point clouds (e.g. ABC-XYZ segmentation matrix). */
export function scatterOption(
  points: { name: string; x: number; y: number; size?: number; color?: string }[],
  opts: { xLabel?: string; yLabel?: string; xMin?: number; xMax?: number; yMin?: number; yMax?: number } = {},
): EChartsCoreOption {
  return {
    animationDuration: 400,
    animationEasing: "cubicOut",
    grid: { left: 12, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(20, 20, 20, 0.97)",
      borderColor: "#282828",
      borderWidth: 1,
      textStyle: { color: "#ffffff", fontSize: 12 },
      padding: [10, 14],
      formatter: (p: { dataIndex: number }) => {
        const pt = points[p.dataIndex];
        return `<div style="font-weight:600;margin-bottom:4px;">${pt.name}</div>` +
          `<div>${opts.xLabel ?? "X"}: <b>${pt.x.toFixed(2)}</b></div>` +
          `<div>${opts.yLabel ?? "Y"}: <b>${pt.y.toFixed(2)}</b></div>`;
      },
    },
    xAxis: {
      type: "value", name: opts.xLabel, nameLocation: "middle", nameGap: 30,
      nameTextStyle: { color: CHART.textMuted, fontSize: 11 },
      min: opts.xMin, max: opts.xMax,
      axisLabel: { color: CHART.textMuted, fontSize: 11 },
      splitLine: { lineStyle: { color: CHART.grid } },
      axisLine: { lineStyle: { color: CHART.axis } },
    },
    yAxis: {
      type: "value", name: opts.yLabel, nameLocation: "middle", nameGap: 40,
      nameTextStyle: { color: CHART.textMuted, fontSize: 11 },
      min: opts.yMin, max: opts.yMax,
      axisLabel: { color: CHART.textMuted, fontSize: 11 },
      splitLine: { lineStyle: { color: CHART.grid } },
      axisLine: { lineStyle: { color: CHART.axis } },
    },
    series: [{
      type: "scatter",
      data: points.map((p) => [p.x, p.y, p.size ?? 12]),
      symbolSize: (val: number[]) => Math.max(6, val[2] || 12),
      itemStyle: { color: SERIES[0], opacity: 0.75, borderColor: "transparent" },
      emphasis: { itemStyle: { opacity: 1, shadowBlur: 10, shadowColor: "rgba(88, 166, 255, 0.5)" } },
    }],
  };
}
