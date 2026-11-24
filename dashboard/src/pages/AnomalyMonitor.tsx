import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { api } from "../api/client";
import type { AnomaliesView, AnomalyRegisterRow } from "../api/types";
import { useApi } from "../api/useApi";
import { useAnomaliesView } from "../api/views";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { DataTable, type Column } from "../components/DataTable";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { useFilters } from "../filters/FilterContext";
import { fmtInt, fmtMonthShort, fmtPctPoints } from "../lib/format";
import { CHART, SERIES, STATUS } from "../theme/chart";

interface EventImpactRow {
  Event_ID: string;
  Event_Type: string;
  Description: string;
  Shipped_Impact_Pct: number | null;
  Demand_Impact_Pct: number | null;
  Method: string;
  Verdict: string;
}

/* Category names exactly as the anomaly register writes them (src/celeris/anomalies.py). */
const CAT_LABEL: Record<string, string> = {
  stockout: "Stockout", real_event: "Real event", data_error: "Data error", gap: "Missing month",
  spike: "One-off spike", unknown: "Unexplained drop",
};
const CAT_COLOR: Record<string, string> = {
  stockout: STATUS.critical, real_event: SERIES[1], data_error: STATUS.warning, gap: SERIES[5],
  spike: SERIES[7], unknown: SERIES[2],
};
const CAT_TONE: Record<string, "critical" | "warning" | "accent" | "neutral" | "serious"> = {
  stockout: "critical", real_event: "accent", data_error: "warning", gap: "neutral", spike: "serious", unknown: "warning",
};
const label = (c: string) => CAT_LABEL[c] ?? c.replace(/_/g, " ");

/** Demand on the time series with every flagged month marked (exact points for one SKU x region). */
function flaggedSeriesOption(v: AnomaliesView): EChartsCoreOption {
  const dates = v.timeline.map((t) => t.Date);
  const demand = new Map(v.timeline.map((t) => [t.Date, t.Demand]));
  const series: unknown[] = [
    { name: "Recovered demand", type: "line", data: v.timeline.map((t) => t.Demand), symbol: "none",
      lineStyle: { width: 2, color: CHART.history }, itemStyle: { color: CHART.history } },
    { name: "Shipped", type: "line", data: v.timeline.map((t) => t.Shipped), symbol: "none",
      lineStyle: { width: 1, type: "dashed", color: CHART.textMuted }, itemStyle: { color: CHART.textMuted } },
  ];
  if (v.single_series && v.points) {
    const cats = [...new Set(v.points.map((p) => p.Category))];
    for (const c of cats) {
      const pts = v.points.filter((p) => p.Category === c);
      series.push({
        name: label(c), type: "scatter", symbolSize: 11, itemStyle: { color: CAT_COLOR[c] ?? SERIES[3] },
        data: pts.map((p) => ({ value: [p.Date, p.Demand ?? demand.get(p.Date) ?? 0], p })),
        tooltip: {
          formatter: (x: { data: { p: AnomaliesView["points"] extends (infer T)[] | null ? T : never } }) => {
            const p = x.data.p;
            return [`<b>${fmtMonthShort(p.Date)} · ${label(p.Category)}</b>`, p.Type.replace(/_/g, " "),
              `Shipped ${fmtInt(p.Units_Shipped)} · demand ${fmtInt(p.Demand)} · expected ${fmtInt(p.Expected)}`,
              `<span style="opacity:.8">${p.Reason}</span>`, `<span style="opacity:.8">Action: ${p.Action}</span>`].join("<br/>");
          },
        },
      });
    }
  } else {
    const maxCount = Math.max(1, ...v.flagged_months.map((f) => f.count));
    series.push({
      name: "Flagged months", type: "scatter", itemStyle: { color: STATUS.critical, opacity: 0.85 },
      symbolSize: (val: [string, number, number]) => 5 + 13 * Math.sqrt(val[2] / maxCount),
      data: v.flagged_months.map((f) => ({ value: [f.Date, demand.get(f.Date) ?? 0, f.count], f })),
      tooltip: {
        formatter: (x: { data: { f: AnomaliesView["flagged_months"][number] } }) => {
          const f = x.data.f;
          const parts = Object.entries(f.by_category).sort((a, b) => b[1] - a[1]).map(([c, n]) => `${label(c)}: ${fmtInt(n)}`);
          return [`<b>${fmtMonthShort(f.Date)} · ${fmtInt(f.count)} flagged series</b>`, ...parts].join("<br/>");
        },
      },
    });
  }
  return {
    grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0 },
    tooltip: { trigger: "item" },
    xAxis: { type: "category", data: dates, boundaryGap: false, axisLabel: { formatter: (d: string) => fmtMonthShort(d), hideOverlap: true } },
    yAxis: { type: "value", scale: true, axisLabel: { formatter: (x: number) => fmtInt(x) } },
    dataZoom: [{ type: "inside", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: false }],
    series,
  };
}

/** Anomaly Monitor — flagged points on the time series with type, reason and the action taken. */
export function AnomalyMonitor() {
  const st = useAnomaliesView(500);
  const events = useApi((s) => api.dataset<EventImpactRow>("event_impact", {}, s), []);
  const { active } = useFilters();
  const d = st.status === "success" ? st.data : undefined;
  const cat = d?.by_category ?? {};

  const categoryChart = useMemo(() => {
    if (!d || !d.total) return null;
    const sorted = Object.entries(d.by_category).sort((a, b) => b[1] - a[1]);
    return verticalBarsOption(sorted.map(([k]) => label(k)),
      [{ name: "Flagged months", data: sorted.map(([, v]) => v) }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true });
  }, [d]);

  const anomalyCols = useMemo<Column<AnomalyRegisterRow>[]>(() => [
    { key: "date", label: "Month", value: (r) => r.Date, render: (r) => fmtMonthShort(r.Date) },
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID, render: (r) => <span className="mono">{r.SKU_ID}</span> },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "category", label: "Category", value: (r) => r.Category, render: (r) => <Badge tone={CAT_TONE[r.Category] ?? "neutral"} icon={null}>{label(r.Category)}</Badge> },
    { key: "type", label: "Type", value: (r) => r.Type, render: (r) => r.Type.replace(/_/g, " ") },
    { key: "shipped", label: "Shipped", value: (r) => r.Units_Shipped, render: (r) => fmtInt(r.Units_Shipped), align: "right" },
    { key: "demand", label: "Demand", value: (r) => r.Demand, render: (r) => fmtInt(r.Demand), align: "right" },
    { key: "expected", label: "Expected", value: (r) => r.Expected, render: (r) => fmtInt(r.Expected), align: "right" },
    { key: "reason", label: "Reason", value: (r) => r.Reason, render: (r) => <span style={{ fontSize: 12, color: "var(--text-3)" }}>{r.Reason}</span> },
    { key: "action", label: "Action", value: (r) => r.Action, render: (r) => <span style={{ fontSize: 12, color: "var(--text-2)" }}>{r.Action}</span> },
    { key: "confidence", label: "Confidence", value: (r) => r.Confidence, render: (r) => {
      const c = (r.Confidence ?? "").toLowerCase();
      return <Badge tone={c === "high" ? "good" : c === "medium" ? "warning" : "serious"} icon={null}>{c || "—"}</Badge>;
    } },
  ], []);

  const eventCols = useMemo<Column<EventImpactRow>[]>(() => [
    { key: "id", label: "Event", value: (r) => r.Event_ID, render: (r) => <span className="mono">{r.Event_ID}</span> },
    { key: "type", label: "Type", value: (r) => r.Event_Type },
    { key: "desc", label: "Description", value: (r) => r.Description },
    // the impact columns are already percentages (-35.6 = -35.6%)
    { key: "ship_impact", label: "Shipped impact", value: (r) => r.Shipped_Impact_Pct, render: (r) => fmtPctPoints(r.Shipped_Impact_Pct), align: "right" },
    { key: "demand_impact", label: "Demand impact", value: (r) => r.Demand_Impact_Pct, render: (r) => fmtPctPoints(r.Demand_Impact_Pct), align: "right" },
    { key: "method", label: "Method", value: (r) => r.Method, render: (r) => <span style={{ fontSize: 12 }}>{r.Method}</span> },
    { key: "verdict", label: "Verdict", value: (r) => r.Verdict, render: (r) => (
      <Badge tone={String(r.Verdict).toLowerCase() === "material" ? "accent" : "neutral"} icon={null}>{r.Verdict}</Badge>
    ) },
  ], []);

  type StructRow = AnomaliesView["structural"]["rows"][number];
  const structCols = useMemo<Column<StructRow>[]>(() => [
    { key: "type", label: "Type", value: (r) => r.Type, render: (r) => <Badge tone="accent" icon={null}>{r.Type.replace(/_/g, " ")}</Badge> },
    { key: "date", label: "Date", value: (r) => r.Date },
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID, render: (r) => <span className="mono">{r.SKU_ID ?? "—"}</span> },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "detail", label: "Detail", value: (r) => r.Detail },
    { key: "evidence", label: "Evidence", value: (r) => r.Evidence, render: (r) => <span style={{ fontSize: 12, color: "var(--text-3)" }}>{r.Evidence}</span> },
    { key: "action", label: "Action", value: (r) => r.Action },
  ], []);

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Anomaly Monitor · flagged points & structural changes</p>
          <h2 className="page__title">Which months were errors, which were real events, and how demand was recovered</h2>
          <p className="page__lead">
            Every flagged month with its type, category, reason and the action taken. Counts cover the full register
            {active > 0 ? " for the current filters" : ""}; pin one SKU and one region to see each flagged point on its own series.
          </p>
        </div>
      </div>

      {st.status === "error" ? <Card><ErrorState error={st.error} onRetry={st.retry} /></Card> : (
        <section className="kpi-row" aria-label="Anomaly summary">
          <KpiTile label="Flagged months" emphasis="accent" loading={!d} value={fmtInt(d?.total)}
            sub={d ? `${fmtInt(d.series_affected)} SKU × region series affected` : undefined} footnote="Full anomaly register" />
          <KpiTile label="Stockouts recovered" loading={!d} value={fmtInt(cat.stockout ?? 0)} unit="months" emphasis={(cat.stockout ?? 0) > 0 ? "critical" : undefined}
            sub="Shipments below demand; demand recovered from the stockout file" />
          <KpiTile label="One-off spikes" loading={!d} value={fmtInt(cat.spike ?? 0)} unit="months"
            sub="Orders far above the usual size; kept in history, excluded from training" />
          <KpiTile label="Unexplained drops" loading={!d} value={fmtInt(cat.unknown ?? 0)} unit="months"
            sub={d ? `Plus ${fmtInt(cat.data_error ?? 0)} data errors and ${fmtInt(cat.gap ?? 0)} missing months` : undefined} />
        </section>
      )}

      <Card title={d?.single_series ? "Flagged points on the time series" : "Flagged months on the demand time series"}
        subtitle={d?.single_series
          ? "Each marker is a flagged month of this SKU × region, coloured by category — hover for type, reason and action"
          : "Recovered demand and shipments for the selection; marker size = number of flagged series that month"}>
        {st.status === "loading" ? <Skeleton height={320} /> : d && d.timeline.length ? (
          <div style={{ padding: "8px 20px 16px" }}>
            <EChart height={320} label="Demand time series with flagged months marked" option={flaggedSeriesOption(d)} />
          </div>
        ) : st.status === "success" ? <EmptyState title="No history for these filters" icon="filter" /> : null}
      </Card>

      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Flagged months by category" subtitle="Full register for the current filters">
            {st.status === "loading" ? <Skeleton height={260} /> : categoryChart ? (
              <div style={{ padding: "16px 20px 20px" }}><EChart height={260} label="Flagged months by category" option={categoryChart} /></div>
            ) : st.status === "success" ? <EmptyState title="No anomalies" icon="check" /> : null}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="By detection type" subtitle="How each flag was raised">
            {st.status === "loading" ? <Skeleton lines={8} /> : d ? (
              <ul className="legend-list">
                {d.by_type.slice(0, 10).map((t) => (
                  <li key={t.type}><span className="legend-dot" style={{ background: "var(--accent)" }} />
                    <span className="legend-name">{t.label}</span><span className="num">{fmtInt(t.count)}</span><span /></li>
                ))}
              </ul>
            ) : null}
          </Card>
        </div>
      </div>

      <Card title="Event impact" subtitle="Calendar events and their measured effect on shipments and recovered demand">
        {events.status === "loading" ? <Skeleton height={280} /> :
          events.status === "error" ? <ErrorState error={events.error} onRetry={events.retry} /> :
            events.data.rows.length > 0 ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={eventCols} rows={events.data.rows} caption="Event impact" maxHeight={280}
                  exportable exportFilename="event_impact" />
              </div>
            ) : <EmptyState title="No events" icon="check" />}
      </Card>

      <Card title="Anomaly register"
        subtitle={d ? `Most recent ${fmtInt(d.rows.length)} of ${fmtInt(d.total)} flagged months — type, reason and the action taken` : "Every flagged month"}>
        {st.status === "loading" ? <Skeleton height={420} /> : d && d.rows.length > 0 ? (
          <div style={{ padding: "8px 20px 20px" }}>
            <DataTable columns={anomalyCols} rows={d.rows} caption="Anomaly register" maxHeight={480}
              initialSort={{ key: "date", dir: "desc" }} exportable exportFilename="anomaly_register" />
          </div>
        ) : st.status === "success" ? <EmptyState title="No anomalies" message="No months were flagged for these filters." icon="check" /> : null}
      </Card>

      <Card title="Structural changes" subtitle="Ordering-cycle changes, customer switches, launches and exits — with evidence and action">
        {st.status === "loading" ? <Skeleton height={320} /> : d && d.structural.rows.length > 0 ? (
          <div style={{ padding: "8px 20px 20px" }}>
            <DataTable columns={structCols} rows={d.structural.rows} caption="Structural register" maxHeight={360}
              initialSort={{ key: "date", dir: "desc" }} exportable exportFilename="structural_register" />
          </div>
        ) : st.status === "success" ? <EmptyState title="No structural changes" icon="check" /> : null}
      </Card>
    </div>
  );
}
