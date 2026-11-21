import { useState } from "react";
import type { BreakdownRow, BreakdownView } from "../api/types";
import { useBreakdown } from "../api/views";
import { ChartCard, Segmented } from "../components/ChartCard";
import { DataTable, type Column } from "../components/DataTable";
import { fmtPctPoints, fmtUnits, fmtUsd } from "../lib/format";
import { EChart } from "./EChart";
import { rankedBarsOption, type BarValue } from "./options";

const COLUMNS: Column<BreakdownRow>[] = [
  { key: "member", label: "Member", value: (r) => r.Member },
  { key: "rev_next", label: "Revenue next 12 m", value: (r) => r.Revenue_next12, render: (r) => fmtUsd(r.Revenue_next12), align: "right" },
  { key: "rev_chg", label: "Revenue Δ", value: (r) => r.Revenue_change_pct, render: (r) => fmtPctPoints(r.Revenue_change_pct), align: "right" },
  { key: "units_next", label: "Units next 12 m", value: (r) => r.Units_next12, render: (r) => fmtUnits(r.Units_next12), align: "right" },
  { key: "units_last", label: "Units last 12 m", value: (r) => r.Units_last12, render: (r) => fmtUnits(r.Units_last12), align: "right" },
  { key: "units_chg", label: "Units Δ", value: (r) => r.Units_change_pct, render: (r) => fmtPctPoints(r.Units_change_pct), align: "right" },
  { key: "share", label: "Revenue share", value: (r) => r.Revenue_share_next12,
    render: (r) => (r.Revenue_share_next12 === null ? "—" : `${(100 * r.Revenue_share_next12).toFixed(1)}%`), align: "right" },
];

const DIM_TITLE: Record<BreakdownView["dim"], string> = {
  family: "product family", region: "region", channel: "channel", customer: "customer", sku: "SKU",
};
const DIM_PLURAL: Record<BreakdownView["dim"], string> = {
  family: "product families", region: "regions", channel: "channels", customer: "customers", sku: "SKUs",
};

/** Ranked bars of next-12-month revenue / units (with change vs last 12 m) by one dimension. */
export function BreakdownCard({ dim, top = 12, title }: { dim: BreakdownView["dim"]; top?: number; title?: string }) {
  const state = useBreakdown(dim, top);
  const [value, setValue] = useState<BarValue>("Revenue_next12");
  const t = title ?? `Next 12 months by ${DIM_TITLE[dim]}`;
  const height = Math.max(180, Math.min(top + 1, 14) * 30);
  return (
    <ChartCard<BreakdownView>
      title={t}
      subtitle="Forecast next 12 months, change vs the last 12 months (recovered demand)"
      state={state}
      height={height}
      controls={
        <Segmented label="Measure" value={value} onChange={setValue}
          options={[{ value: "Revenue_next12", label: "Revenue" }, { value: "Units_next12", label: "Units" },
            { value: "Units_change_pct", label: "Growth" }]} />
      }
      isEmpty={(d) => d.rows.length === 0}
      chart={(d) => <EChart height={height} label={`${t}, ranked`} option={rankedBarsOption(d.rows, value)} />}
      table={(d) => <DataTable columns={COLUMNS} rows={d.rows} caption={t} maxHeight={height}
        initialSort={{ key: "rev_next", dir: "desc" }} />}
      footnote={(d) => `${d.members.toLocaleString()} ${d.members === 1 ? DIM_TITLE[dim] : DIM_PLURAL[dim]} in the current filter`
        + (d.members > top ? ` · top ${top} shown, the rest folded into "Other"` : "")}
    />
  );
}
