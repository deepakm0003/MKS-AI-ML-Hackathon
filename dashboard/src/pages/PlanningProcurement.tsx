import { useMemo } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { useRecommendations } from "../api/views";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icon";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt, fmtPct, fmtUsd } from "../lib/format";
import { SERIES, STATUS } from "../theme/chart";

interface SegmentationRow {
  SKU_ID: string;
  Region: string;
  Revenue_next12: number;
  ABC: string;
  XYZ: string;
  Segment: string;
  Service_level: number;
  Planning_approach: string;
}

interface ProcurementNextRow {
  SKU_ID: string;
  Region: string;
  Segment: string;
  Leadtime_P50: number;
  Leadtime_cover: number;
  Safety_buffer: number;
  Cover_value_usd: number;
}

interface ProcurementPlanRow {
  Date: string;
  SKU_ID: string;
  Region: string;
  Forecast: number;
  P50: number;
  P90: number;
  Leadtime_cover: number;
  Safety_buffer: number;
  Order_release_month: string;
}

interface CapacityRow {
  Product_Family: string;
  Region: string;
  Demonstrated_3m_throughput: number;
  Peak_3m_load_P50: number;
  Peak_3m_load_P90: number;
  Utilisation_P50: number;
  Utilisation_P90: number;
  Capacity_flag: string;
}

/** Null-safe month formatter, e.g. 2.3 -> "2.3 mo" */
const fmtMo = (v: number | null | undefined): string =>
  v != null && Number.isFinite(v) ? `${v.toFixed(1)} mo` : "—";

/** Null-safe percent formatter, e.g. 85 -> "85%" */
const fmtPctRaw = (v: number | null | undefined): string =>
  v != null && Number.isFinite(v) ? `${v.toFixed(0)}%` : "—";

/** 04 Planning & Procurement — P90 procurement plan, ABC-XYZ segmentation, capacity, lead-time buffers. */
export function PlanningProcurement() {
  const seg = useApi((s) => api.dataset<SegmentationRow>("segmentation", {}, s), []);
  const nextCycle = useApi((s) => api.dataset<ProcurementNextRow>("procurement_next_cycle", {}, s), []);
  const plan = useApi((s) => api.dataset<ProcurementPlanRow>("procurement_plan", { limit: 500 }, s), []);
  const cap = useApi((s) => api.dataset<CapacityRow>("capacity_check", {}, s), []);
  const recs = useRecommendations({ limit: 8 });

  // KPI computations
  const totalCover = nextCycle.status === "success" ? nextCycle.data.rows.reduce((s, r) => s + (r.Cover_value_usd ?? 0), 0) : 0;
  const totalBuffer = nextCycle.status === "success" ? nextCycle.data.rows.reduce((s, r) => s + (r.Safety_buffer ?? 0), 0) : 0;
  const itemCount = nextCycle.status === "success" ? nextCycle.data.total : 0;
  const avgService = seg.status === "success" && seg.data.rows.length > 0
    ? seg.data.rows.reduce((s, r) => s + (r.Service_level ?? 0), 0) / seg.data.rows.length : 0;

  // Segment distribution bar chart
  const segChart = useMemo(() => {
    if (seg.status !== "success" || !seg.data.rows.length) return null;
    const counts: Record<string, number> = {};
    for (const r of seg.data.rows) counts[r.Segment] = (counts[r.Segment] ?? 0) + 1;
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return verticalBarsOption(
      sorted.map(([k]) => k),
      [{ name: "SKUs", data: sorted.map(([, v]) => v) }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true },
    );
  }, [seg]);

  // Procurement plan by month chart
  const planChart = useMemo(() => {
    if (plan.status !== "success" || !plan.data.rows.length) return null;
    const byMonth: Record<string, { forecast: number; p90: number }> = {};
    for (const r of plan.data.rows) {
      if (!byMonth[r.Date]) byMonth[r.Date] = { forecast: 0, p90: 0 };
      byMonth[r.Date].forecast += r.Forecast ?? 0;
      byMonth[r.Date].p90 += r.P90 ?? 0;
    }
    const dates = Object.keys(byMonth).sort();
    return verticalBarsOption(
      dates,
      [
        { name: "Forecast", data: dates.map((d) => byMonth[d].forecast), color: SERIES[0] },
        { name: "P90", data: dates.map((d) => byMonth[d].p90), color: SERIES[4] },
      ],
      { valueFormatter: (v) => fmtInt(v), rotateLabels: true, yAxisName: "Units" },
    );
  }, [plan]);

  // Capacity utilization chart
  const capChart = useMemo(() => {
    if (cap.status !== "success" || !cap.data.rows.length) return null;
    const rows = [...cap.data.rows]
      .filter((r) => r.Utilisation_P90 != null && r.Utilisation_P50 != null)
      .sort((a, b) => (b.Utilisation_P90 ?? 0) - (a.Utilisation_P90 ?? 0))
      .slice(0, 12);
    if (!rows.length) return null;
    return verticalBarsOption(
      rows.map((r) => `${r.Product_Family} · ${r.Region}`),
      [
        { name: "P50", data: rows.map((r) => r.Utilisation_P50), color: SERIES[2] },
        { name: "P90", data: rows.map((r) => r.Utilisation_P90), color: STATUS.serious },
      ],
      { valueFormatter: (v) => fmtPctRaw(v), rotateLabels: true, yAxisName: "Utilisation" },
    );
  }, [cap]);

  // Table columns — all formatters are null-safe
  const segCols = useMemo<Column<SegmentationRow>[]>(() => [
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "rev", label: "Revenue next 12m", value: (r) => r.Revenue_next12, render: (r) => fmtUsd(r.Revenue_next12), align: "right" },
    { key: "abc", label: "ABC", value: (r) => r.ABC, render: (r) => <Badge tone="accent">{r.ABC}</Badge> },
    { key: "xyz", label: "XYZ", value: (r) => r.XYZ, render: (r) => <Badge tone="neutral">{r.XYZ}</Badge> },
    { key: "segment", label: "Segment", value: (r) => r.Segment },
    { key: "sl", label: "Service level", value: (r) => r.Service_level, render: (r) => fmtPct(r.Service_level, 0), align: "right" },
    { key: "approach", label: "Planning approach", value: (r) => r.Planning_approach ?? "—" },
  ], []);

  const nextCols = useMemo<Column<ProcurementNextRow>[]>(() => [
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "segment", label: "Segment", value: (r) => r.Segment, render: (r) => <Badge tone="accent">{r.Segment}</Badge> },
    { key: "lt", label: "Leadtime P50", value: (r) => r.Leadtime_P50, render: (r) => fmtMo(r.Leadtime_P50), align: "right" },
    { key: "cover", label: "Leadtime cover", value: (r) => r.Leadtime_cover, render: (r) => fmtMo(r.Leadtime_cover), align: "right" },
    { key: "buffer", label: "Safety buffer", value: (r) => r.Safety_buffer, render: (r) => fmtInt(r.Safety_buffer), align: "right" },
    { key: "value", label: "Cover value", value: (r) => r.Cover_value_usd, render: (r) => fmtUsd(r.Cover_value_usd), align: "right" },
  ], []);

  const planCols = useMemo<Column<ProcurementPlanRow>[]>(() => [
    { key: "date", label: "Delivery month", value: (r) => r.Date },
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "forecast", label: "Forecast", value: (r) => r.Forecast, render: (r) => fmtInt(r.Forecast), align: "right" },
    { key: "p90", label: "P90", value: (r) => r.P90, render: (r) => fmtInt(r.P90), align: "right" },
    { key: "cover", label: "Leadtime cover", value: (r) => r.Leadtime_cover, render: (r) => fmtMo(r.Leadtime_cover), align: "right" },
    { key: "buffer", label: "Safety buffer", value: (r) => r.Safety_buffer, render: (r) => fmtInt(r.Safety_buffer), align: "right" },
    { key: "order", label: "Order release", value: (r) => r.Order_release_month, render: (r) => (
      <span style={{ color: "var(--accent)" }}>{r.Order_release_month ?? "—"}</span>
    ) },
  ], []);

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Planning & Procurement · 19-month horizon</p>
          <h2 className="page__title">What to order, how much buffer, and who owns each action</h2>
          <p className="page__lead">
            P90 procurement plan from the frozen forecast, calibrated lead-time buffers, ABC-XYZ
            segmentation with service-level policy, and capacity check against demonstrated throughput.
          </p>
        </div>
      </div>

      {/* KPI row */}
      <section className="kpi-row" aria-label="Procurement summary">
        <KpiTile
          label="Total cover value" emphasis="accent" loading={nextCycle.status === "loading"}
          value={fmtUsd(totalCover, 1)}
          sub="3-month delivery cover at segment service levels"
          footnote="From the procurement_next_cycle plan"
        />
        <KpiTile
          label="Total safety buffer" loading={nextCycle.status === "loading"}
          value={fmtInt(totalBuffer)} unit="units"
          sub="Sum of P90 safety buffers across all SKUs"
          footnote="Calibrated to demand uncertainty"
        />
        <KpiTile
          label="Items to order" loading={nextCycle.status === "loading"}
          value={itemCount ? String(itemCount) : "—"} unit="SKU × region"
          sub="Distinct procurement lines in the next cycle"
          footnote="From the procurement plan"
        />
        <KpiTile
          label="Avg service level" loading={seg.status === "loading"}
          value={avgService ? fmtPct(avgService, 0) : "—"}
          sub="Weighted by ABC-XYZ segment policy"
          footnote="Segment-specific service targets"
        />
      </section>

      {/* Segment distribution + Procurement plan by month */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Procurement plan by month" subtitle="Total forecast and P90 units per delivery month, all SKUs">
            {plan.status === "loading" ? <Skeleton height={280} /> :
              plan.status === "error" ? <ErrorState error={plan.error} onRetry={plan.retry} /> :
                planChart ? (
                  <div style={{ padding: "16px 20px 20px" }}>
                    <EChart height={280} label="Procurement plan by month, forecast and P90" option={planChart} />
                  </div>
                ) : <EmptyState title="No plan data" icon="database" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="ABC-XYZ segmentation" subtitle="Distribution of SKU × region across inventory segments">
            {seg.status === "loading" ? <Skeleton height={280} /> :
              seg.status === "error" ? <ErrorState error={seg.error} onRetry={seg.retry} /> :
                segChart ? (
                  <div style={{ padding: "16px 20px 20px" }}>
                    <EChart height={280} label="ABC-XYZ segment distribution" option={segChart} />
                  </div>
                ) : <EmptyState title="No segmentation data" icon="database" />}
          </Card>
        </div>
      </div>

      {/* Procurement next cycle + Recommended actions */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Procurement — next cycle" subtitle="Deliveries in the next 3 months at each segment's service level">
            {nextCycle.status === "loading" ? <Skeleton height={320} /> :
              nextCycle.status === "error" ? <ErrorState error={nextCycle.error} onRetry={nextCycle.retry} /> :
                nextCycle.data.rows.length > 0 ? (
                  <div style={{ padding: "8px 20px 20px" }}>
                    <DataTable columns={nextCols} rows={nextCycle.data.rows} caption="Procurement next cycle"
                      maxHeight={400} initialSort={{ key: "value", dir: "desc" }} />
                  </div>
                ) : <EmptyState title="No next-cycle data" icon="database" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Recommended actions" subtitle="Top planner actions from the intelligence engine">
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

      {/* Segmentation table */}
      <Card title="ABC-XYZ segmentation matrix" subtitle="Revenue share, variability class and planning approach per SKU × region">
        {seg.status === "loading" ? <Skeleton height={400} /> :
          seg.status === "error" ? <ErrorState error={seg.error} onRetry={seg.retry} /> :
            seg.data.rows.length > 0 ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={segCols} rows={seg.data.rows} caption="ABC-XYZ segmentation"
                  maxHeight={420} initialSort={{ key: "rev", dir: "desc" }} />
              </div>
            ) : <EmptyState title="No segmentation data" icon="database" />}
      </Card>

      {/* Capacity check */}
      <Card title="Capacity check" subtitle="Demonstrated 3-month throughput vs peak forecast load, P50 and P90 utilization">
        {cap.status === "loading" ? <Skeleton height={320} /> :
          cap.status === "error" ? <ErrorState error={cap.error} onRetry={cap.retry} /> :
            cap.data.rows.length > 0 && capChart ? (
              <div style={{ padding: "16px 20px 20px" }}>
                <EChart height={300} label="Capacity utilization by family and region, P50 and P90" option={capChart} />
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
                  {[...new Set(cap.data.rows.map((r) => r.Capacity_flag))].map((flag) => {
                    const count = cap.data.rows.filter((r) => r.Capacity_flag === flag).length;
                    return (
                      <Badge key={flag} tone={flag === "AT_RISK" ? "critical" : flag === "WATCH" ? "warning" : "good"}>
                        {flag}: {count}
                      </Badge>
                    );
                  })}
                </div>
              </div>
            ) : <EmptyState title="No capacity data" icon="database" />}
      </Card>

      {/* Procurement plan table */}
      <Card title="Procurement plan detail" subtitle="P90 forecast per SKU × region × delivery month, with order release month and lead-time cover">
        {plan.status === "loading" ? <Skeleton height={400} /> :
          plan.status === "error" ? <ErrorState error={plan.error} onRetry={plan.retry} /> :
            plan.data.rows.length > 0 ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={planCols} rows={plan.data.rows} caption="Procurement plan"
                  maxHeight={420} initialSort={{ key: "date", dir: "asc" }} />
              </div>
            ) : <EmptyState title="No plan data" icon="database" />}
      </Card>
    </div>
  );
}
