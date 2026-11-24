import { useMemo } from "react";
import type { PlanningView } from "../api/types";
import { usePlanningView, useRecommendations } from "../api/views";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icon";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { useFilters } from "../filters/FilterContext";
import { fmtInt, fmtMonthShort, fmtPct, fmtUnits, fmtUsd } from "../lib/format";
import { SERIES, STATUS } from "../theme/chart";

type NextRow = PlanningView["next_cycle"]["rows"][number];
type SegRow = PlanningView["segmentation"]["rows"][number];
type CapRow = PlanningView["capacity"][number];
type MonthRow = PlanningView["monthly"][number];

/* Capacity flags exactly as src/celeris/intel/supply.py writes them. */
const FLAG: Record<string, { label: string; tone: "critical" | "warning" | "serious" | "good" }> = {
  ABOVE_DEMONSTRATED_THROUGHPUT: { label: "Above demonstrated throughput", tone: "critical" },
  TIGHT: { label: "Tight (≥ 95%)", tone: "warning" },
  UPSIDE_ABOVE_THROUGHPUT: { label: "Upside (P90) above throughput", tone: "serious" },
  OK: { label: "OK", tone: "good" },
};

/** 04 Planning & Procurement — P90 procurement plan, ABC-XYZ policy, capacity and lead-time buffers. */
export function PlanningProcurement() {
  const st = usePlanningView(500);
  const recs = useRecommendations({ limit: 8 });
  const { active } = useFilters();
  const d = st.status === "success" ? st.data : undefined;
  const k = d?.kpis;

  const planChart = useMemo(() => d && d.monthly.length ? verticalBarsOption(
    d.monthly.map((m) => fmtMonthShort(m.Date)),
    [{ name: "Forecast", data: d.monthly.map((m) => m.Forecast), color: SERIES[0] },
      { name: "Sum of SKU P90", data: d.monthly.map((m) => m.P90), color: SERIES[1] }],
    { valueFormatter: (v) => fmtInt(v), rotateLabels: true, yAxisName: "Units" }) : null, [d]);

  const segChart = useMemo(() => {
    if (!d || !d.segments.length) return null;
    const s = [...d.segments].sort((a, b) => b.Revenue_next12 - a.Revenue_next12);
    return verticalBarsOption(s.map((r) => r.Segment), [{ name: "Revenue share next 12 m", data: s.map((r) => 100 * (r.Revenue_share ?? 0)) }],
      { valueFormatter: (v) => `${v.toFixed(1)}%`, showLabels: true });
  }, [d]);

  const capChart = useMemo(() => {
    if (!d || !d.capacity.length) return null;
    const rows = [...d.capacity].sort((a, b) => b.Utilisation_P50 - a.Utilisation_P50).slice(0, 14);
    // utilisation is stored as a ratio (1.06 = 106% of the demonstrated 3-month throughput)
    return verticalBarsOption(rows.map((r) => `${r.Product_Family} · ${r.Region}`),
      [{ name: "Forecast load (P50)", data: rows.map((r) => 100 * r.Utilisation_P50), color: SERIES[0] },
        { name: "Upside load (P90)", data: rows.map((r) => 100 * r.Utilisation_P90), color: STATUS.warning }],
      { valueFormatter: (v) => `${v.toFixed(0)}%`, rotateLabels: true, yAxisName: "% of demonstrated throughput" });
  }, [d]);

  const nextCols = useMemo<Column<NextRow>[]>(() => [
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID, render: (r) => <span className="mono">{r.SKU_ID}</span> },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "segment", label: "Segment", value: (r) => r.Segment, render: (r) => <Badge tone="accent" icon={null}>{r.Segment}</Badge> },
    { key: "sl", label: "Service level", value: (r) => r.Service_level, render: (r) => fmtPct(r.Service_level, 0), align: "right" },
    { key: "p50", label: "Forecast, next 3 m", value: (r) => r.Leadtime_P50, render: (r) => fmtInt(r.Leadtime_P50), align: "right" },
    { key: "cover", label: "Cover at service level", value: (r) => r.Leadtime_cover, render: (r) => fmtInt(r.Leadtime_cover), align: "right" },
    { key: "buffer", label: "Safety buffer", value: (r) => r.Safety_buffer, render: (r) => fmtInt(r.Safety_buffer), align: "right" },
    { key: "value", label: "Cover value", value: (r) => r.Cover_value_usd, render: (r) => fmtUsd(r.Cover_value_usd), align: "right" },
  ], []);

  const segCols = useMemo<Column<SegRow>[]>(() => [
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID, render: (r) => <span className="mono">{r.SKU_ID}</span> },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "rev", label: "Revenue next 12 m", value: (r) => r.Revenue_next12, render: (r) => fmtUsd(r.Revenue_next12), align: "right" },
    { key: "segment", label: "Segment", value: (r) => r.Segment, render: (r) => <Badge tone="accent" icon={null}>{r.Segment}</Badge> },
    { key: "sl", label: "Service level", value: (r) => r.Service_level, render: (r) => fmtPct(r.Service_level, 0), align: "right" },
    { key: "approach", label: "Planning approach", value: (r) => r.Planning_approach ?? "—" },
  ], []);

  const monthCols = useMemo<Column<MonthRow>[]>(() => [
    { key: "date", label: "Delivery month", value: (r) => r.Date, render: (r) => fmtMonthShort(r.Date) },
    { key: "fc", label: "Forecast units", value: (r) => r.Forecast, render: (r) => fmtInt(r.Forecast), align: "right" },
    { key: "p90", label: "Sum of SKU P90", value: (r) => r.P90, render: (r) => fmtInt(r.P90), align: "right" },
    { key: "rev", label: "Forecast revenue", value: (r) => r.Revenue, render: (r) => fmtUsd(r.Revenue), align: "right" },
  ], []);

  const capCols = useMemo<Column<CapRow>[]>(() => [
    { key: "fam", label: "Family", value: (r) => r.Product_Family },
    { key: "reg", label: "Region", value: (r) => r.Region },
    { key: "thr", label: "Demonstrated 3-m throughput", value: (r) => r.Demonstrated_3m_throughput, render: (r) => fmtInt(r.Demonstrated_3m_throughput), align: "right" },
    { key: "p50", label: "Peak 3-m load (P50)", value: (r) => r.Peak_3m_load_P50, render: (r) => fmtInt(r.Peak_3m_load_P50), align: "right" },
    { key: "u50", label: "Utilisation P50", value: (r) => r.Utilisation_P50, render: (r) => fmtPct(r.Utilisation_P50, 0), align: "right" },
    { key: "u90", label: "Utilisation P90", value: (r) => r.Utilisation_P90, render: (r) => fmtPct(r.Utilisation_P90, 0), align: "right" },
    { key: "flag", label: "Flag", value: (r) => r.Capacity_flag, render: (r) => {
      const f = FLAG[r.Capacity_flag] ?? { label: r.Capacity_flag, tone: "warning" as const };
      return <Badge tone={f.tone}>{f.label}</Badge>;
    } },
  ], []);

  const flagCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of d?.capacity ?? []) c[r.Capacity_flag] = (c[r.Capacity_flag] ?? 0) + 1;
    return c;
  }, [d]);

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Planning & Procurement · 19-month horizon</p>
          <h2 className="page__title">What to order, how much buffer, and who owns each action</h2>
          <p className="page__lead">
            Procurement plan from the frozen forecast with calibrated 3-month lead-time buffers, ABC-XYZ service-level policy
            and a capacity check against demonstrated throughput{active > 0 ? " — for the current filters" : ""}.
          </p>
        </div>
      </div>

      {st.status === "error" ? <Card><ErrorState error={st.error} onRetry={st.retry} /></Card> : (
        <section className="kpi-row" aria-label="Procurement summary">
          <KpiTile label="Next-cycle cover value" emphasis="accent" loading={!k} value={fmtUsd(k?.cover_value_usd, 1)}
            sub={k ? `${fmtUnits(k.cover_units, 1)} units for deliveries in the next 3 months` : undefined}
            footnote="At each segment's service level" />
          <KpiTile label="Safety buffer" loading={!k} value={fmtUnits(k?.buffer_units, 1)} unit="units"
            sub={k ? `${fmtUsd(k.buffer_value_usd, 1)} above the forecast of ${fmtUnits(k.forecast_units_next3, 1)} units` : undefined}
            footnote="Calibrated 3-month lead-time quantiles" />
          <KpiTile label="Procurement lines" loading={!k} value={k ? fmtInt(k.lines) : undefined} unit="SKU × region"
            sub={k?.make_to_order_lines ? `${fmtInt(k.make_to_order_lines)} make-to-order lines (< 1 unit / month)` : "Lines in the next cycle"} />
          <KpiTile label="Service level" loading={!k} value={fmtPct(k?.service_level_revenue_weighted, 1)}
            sub="Revenue-weighted target across ABC-XYZ segments" footnote="A-X/Y 95% … C-Y/Z 80%" />
        </section>
      )}

      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Procurement plan by month" subtitle="Forecast units and the sum of SKU-level P90 per delivery month (all lines in the selection)">
            {st.status === "loading" ? <Skeleton height={280} /> : planChart ? (
              <div style={{ padding: "16px 20px 20px" }}><EChart height={280} label="Procurement plan by month" option={planChart} /></div>
            ) : st.status === "success" ? <EmptyState title="No plan data for these filters" icon="filter" /> : null}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="ABC-XYZ segments" subtitle="Share of next-12-month revenue by segment">
            {st.status === "loading" ? <Skeleton height={280} /> : segChart ? (
              <div style={{ padding: "16px 20px 20px" }}><EChart height={280} label="Revenue share by ABC-XYZ segment" option={segChart} /></div>
            ) : st.status === "success" ? <EmptyState title="No segments" icon="filter" /> : null}
          </Card>
        </div>
      </div>

      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Procurement — next cycle"
            subtitle={d ? `Largest ${fmtInt(d.next_cycle.rows.length)} of ${fmtInt(d.next_cycle.total)} lines by cover value · units cover deliveries in the next 3 months` : "Next cycle"}>
            {st.status === "loading" ? <Skeleton height={320} /> : d && d.next_cycle.rows.length ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={nextCols} rows={d.next_cycle.rows} caption="Procurement next cycle" maxHeight={400}
                  initialSort={{ key: "value", dir: "desc" }} exportable exportFilename="procurement_next_cycle" />
              </div>
            ) : st.status === "success" ? <EmptyState title="No next-cycle lines" icon="filter" /> : null}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Recommended actions" subtitle="Top planner actions for the current filters">
            {recs.status === "loading" ? <Skeleton height={320} /> :
              recs.status === "error" ? <ErrorState error={recs.error} onRetry={recs.retry} /> :
                recs.data.cards.length > 0 ? (
                  <div style={{ padding: "8px 20px 20px" }}>
                    <ol className="actions" style={{ padding: 0, listStyle: "none" }}>
                      {recs.data.cards.slice(0, 6).map((c) => (
                        <li key={c.id} className="action" style={{ borderLeftColor: "var(--accent)" }}>
                          <div className="action__head" style={{ cursor: "default" }}>
                            <span className="action__rank mono">{c.id.replace("EX-", "#")}</span>
                            <span className="action__main">
                              <span className="action__title">{c.title}</span>
                              <span className="action__scope">{c.scope}</span>
                            </span>
                            <span className="action__impact num">{fmtUsd(c.impact_usd, 1)}</span>
                          </div>
                          <div className="action__meta">
                            <span><Icon name="dot" size={10} /> {c.owner}</span>
                            <span>{c.window}</span>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : <EmptyState title="No recommendations" icon="check" />}
          </Card>
        </div>
      </div>

      <Card title="Capacity check" subtitle="Peak 3-month forecast load as % of the highest 3-month volume shipped in the last 3 years (a labelled proxy — there is no capacity table)">
        {st.status === "loading" ? <Skeleton height={320} /> : d && capChart ? (
          <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
            <EChart height={300} label="Capacity utilisation by family and region" option={capChart} />
            <div className="badge-row">
              {Object.entries(flagCounts).map(([flag, n]) => {
                const f = FLAG[flag] ?? { label: flag, tone: "warning" as const };
                return <Badge key={flag} tone={f.tone}>{f.label}: {n}</Badge>;
              })}
            </div>
            <DataTable columns={capCols} rows={d.capacity} caption="Capacity check" maxHeight={320}
              initialSort={{ key: "u50", dir: "desc" }} exportable exportFilename="capacity_check" />
          </div>
        ) : st.status === "success" ? <EmptyState title="No capacity rows for these filters" icon="filter" /> : null}
      </Card>

      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="ABC-XYZ segmentation"
            subtitle={d ? `Largest ${fmtInt(d.segmentation.rows.length)} of ${fmtInt(d.segmentation.total)} series by revenue — service level and planning approach` : "Segmentation"}>
            {st.status === "loading" ? <Skeleton height={400} /> : d && d.segmentation.rows.length ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={segCols} rows={d.segmentation.rows} caption="ABC-XYZ segmentation" maxHeight={420}
                  initialSort={{ key: "rev", dir: "desc" }} exportable exportFilename="abc_xyz_segmentation" />
              </div>
            ) : st.status === "success" ? <EmptyState title="No segmentation rows" icon="filter" /> : null}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Monthly plan" subtitle="Totals per delivery month">
            {st.status === "loading" ? <Skeleton height={400} /> : d && d.monthly.length ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={monthCols} rows={d.monthly} caption="Monthly procurement plan" maxHeight={420}
                  exportable exportFilename="procurement_plan_monthly" />
              </div>
            ) : st.status === "success" ? <EmptyState title="No plan rows" icon="filter" /> : null}
          </Card>
        </div>
      </div>
    </div>
  );
}
