import { useMemo, useState } from "react";
import type { TimelineView } from "../api/types";
import { useTimeline } from "../api/views";
import { ChartCard, Segmented } from "../components/ChartCard";
import { DataTable, type Column } from "../components/DataTable";
import { fmtMonthShort, fmtUnits, fmtUsd } from "../lib/format";
import { EChart } from "./EChart";
import { timelineOption, timelineRows, type Metric, type TimelineRow } from "./options";

type Range = "all" | "5y" | "3y";
const RANGE_START: Record<Range, string | undefined> = { all: undefined, "5y": "2021-11", "3y": "2023-11" };

/** History continuing into the forecast with its P10-P90 range - units or revenue - for the current filters. */
export function TimelineCard({ title = "Demand history and forecast", height = 340, defaultMetric = "units", allowShipped = false }: {
  title?: string; height?: number; defaultMetric?: Metric; allowShipped?: boolean;
}) {
  const state = useTimeline();
  const [metric, setMetric] = useState<Metric>(defaultMetric);
  const [range, setRange] = useState<Range>("5y");
  const [shipped, setShipped] = useState<"off" | "on">("off");
  const fmt = metric === "units" ? (v: number | null) => fmtUnits(v, 1) : (v: number | null) => fmtUsd(v, 2);

  const columns = useMemo<Column<TimelineRow>[]>(() => [
    { key: "date", label: "Month", value: (r) => r.date, render: (r) => fmtMonthShort(r.date) },
    { key: "actual", label: "Actual demand", value: (r) => r.actual, render: (r) => fmt(r.actual), align: "right" },
    { key: "shipped", label: "Shipped", value: (r) => r.shipped, render: (r) => fmt(r.shipped), align: "right" },
    { key: "forecast", label: "Forecast", value: (r) => r.forecast, render: (r) => fmt(r.forecast), align: "right" },
    { key: "p10", label: "P10", value: (r) => r.p10, render: (r) => fmt(r.p10), align: "right" },
    { key: "p90", label: "P90", value: (r) => r.p90, render: (r) => fmt(r.p90), align: "right" },
  ], [metric]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <ChartCard<TimelineView>
      title={title}
      subtitle={allowShipped && shipped === "on"
        ? "Recovered demand vs shipments (the gap is stockout-constrained demand), into the forecast"
        : "Recovered (unconstrained) demand into the 19-month forecast, P10–P90 range shaded"}
      state={state}
      height={height}
      controls={
        <>
          <Segmented label="Metric" value={metric} onChange={setMetric}
            options={[{ value: "units", label: "Units" }, { value: "revenue", label: "Revenue" }]} />
          <Segmented label="Range" value={range} onChange={setRange}
            options={[{ value: "3y", label: "3Y" }, { value: "5y", label: "5Y" }, { value: "all", label: "All" }]} />
          {allowShipped && (
            <Segmented label="Shipped overlay" value={shipped} onChange={setShipped}
              options={[{ value: "off", label: "Demand" }, { value: "on", label: "+ Shipped" }]} />
          )}
        </>
      }
      isEmpty={(d) => d.history.length === 0 && d.forecast.length === 0}
      chart={(d) => (
        <EChart height={height} label={`${title}: ${metric} by month, history and forecast`}
          option={timelineOption(d, metric, { fromMonth: RANGE_START[range], showShipped: shipped === "on" })} />
      )}
      table={(d) => <DataTable columns={columns} rows={timelineRows(d, metric).reverse()} caption={title} maxHeight={height} />}
      footnote={(d) => (
        <>
          {d.summary.forecast_series.toLocaleString()} forecast series · band: {d.band_method}
          {metric === "revenue" && " · revenue at the announced 2027 / 2028 list prices"}
        </>
      )}
    />
  );
}
