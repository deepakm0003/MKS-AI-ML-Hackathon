import { useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import type { SeasonalityView } from "../api/types";
import { useSeasonality } from "../api/views";
import { EChart } from "../charts/EChart";
import { ChartCard, Segmented } from "../components/ChartCard";
import { DataTable, type Column } from "../components/DataTable";
import { fmtUnits } from "../lib/format";
import { CHART, SERIES } from "../theme/chart";

type Mode = "profile" | "years";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Seasonal effect: % above / below an average month. Bars grow from a true zero line (history,
 *  last 36 months); the line is the first 12 forecast months on the same scale. */
const dev = (x: number | null) => (x === null ? null : Math.round((x - 1) * 1000) / 10);

export function seasonalityOption(v: SeasonalityView, mode: Mode): EChartsCoreOption {
  if (mode === "profile") {
    const pct = (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(0)}%`;
    return {
      grid: { left: 8, right: 12, top: 36, bottom: 8, containLabel: true },
      legend: { top: 0, left: 0, data: ["History (last 36 m)", "Forecast (next 12 m)"] },
      tooltip: { trigger: "axis", valueFormatter: (x: number) => (x === null || x === undefined ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(1)}% vs average month`) },
      xAxis: { type: "category", data: MONTHS, axisLine: { onZero: true } },
      yAxis: { type: "value", axisLabel: { formatter: pct } },
      series: [
        { name: "History (last 36 m)", type: "bar", data: v.by_month.map((m) => dev(m.hist_index)), barMaxWidth: 22,
          itemStyle: { color: "rgba(169, 182, 203, 0.45)", borderRadius: CHART.barRadius } },
        { name: "Forecast (next 12 m)", type: "line", data: v.by_month.map((m) => dev(m.forecast_index)), symbol: "circle", symbolSize: 7,
          itemStyle: { color: SERIES[0] }, lineStyle: { width: 2, color: SERIES[0] } },
      ],
    };
  }
  // year overlay: older history years fade, the latest is brightest; forecast years dashed in the accent
  const hist = v.years.filter((y) => y.kind === "history");
  const fc = v.years.filter((y) => y.kind === "forecast");
  const series = [
    ...hist.map((y, i) => ({
      name: y.year, type: "line", data: y.values, symbol: "none",
      lineStyle: { width: i === hist.length - 1 ? 2 : 1.5, color: CHART.history, opacity: 0.25 + 0.75 * ((i + 1) / hist.length) },
      itemStyle: { color: CHART.history, opacity: 0.25 + 0.75 * ((i + 1) / hist.length) },
    })),
    ...fc.map((y) => ({
      name: `${y.year} forecast`, type: "line", data: y.values, symbol: "none",
      lineStyle: { width: 2, type: "dashed", color: SERIES[0] }, itemStyle: { color: SERIES[0] },
    })),
  ];
  return {
    grid: { left: 8, right: 12, top: 36, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, type: "scroll" },
    tooltip: { trigger: "axis", valueFormatter: (x: number) => (x === null || x === undefined ? "—" : fmtUnits(x, 1)) },
    xAxis: { type: "category", data: MONTHS, boundaryGap: false },
    yAxis: { type: "value", scale: true, axisLabel: { formatter: (x: number) => fmtUnits(x, 1) } },
    series,
  };
}

const COLS: Column<SeasonalityView["by_month"][number]>[] = [
  { key: "m", label: "Month", value: (r) => r.month, render: (r) => r.label },
  { key: "ha", label: "Avg units (last 36 m)", value: (r) => r.hist_avg_units, render: (r) => fmtUnits(r.hist_avg_units, 1), align: "right" },
  { key: "hi", label: "History index", value: (r) => r.hist_index, render: (r) => r.hist_index?.toFixed(2) ?? "—", align: "right" },
  { key: "fu", label: "Forecast units", value: (r) => r.forecast_units, render: (r) => fmtUnits(r.forecast_units, 1), align: "right" },
  { key: "fi", label: "Forecast index", value: (r) => r.forecast_index, render: (r) => r.forecast_index?.toFixed(2) ?? "—", align: "right" },
];

export function SeasonalityCard() {
  const st = useSeasonality();
  const [mode, setMode] = useState<Mode>("profile");
  return (
    <ChartCard<SeasonalityView>
      title="Seasonality"
      subtitle={mode === "profile" ? "Each month vs an average month (history bars, forecast line)" : "Monthly demand by year, forecast years dashed"}
      state={st}
      height={260}
      controls={<Segmented label="Seasonality view" value={mode} onChange={setMode}
        options={[{ value: "profile", label: "Profile" }, { value: "years", label: "Year overlay" }]} />}
      chart={(d) => <EChart height={260} label={`Seasonality, ${mode}`} option={seasonalityOption(d, mode)} />}
      table={(d) => <DataTable columns={COLS} rows={d.by_month} caption="Seasonality by month" maxHeight={260} />}
      footnote={(d) => d.stats.peak_months.length
        ? `Peaks ${d.stats.peak_months.join(" and ")} · trough ${d.stats.trough_month}`
          + (d.stats.amplitude !== null ? ` · peak-to-trough ${d.stats.amplitude.toFixed(2)}×` : " · some months have no demand")
          + " · lifecycle rules (launch ramp, EOL run-down) shape the forecast line"
        : "Not enough history for a seasonal profile"}
    />
  );
}
