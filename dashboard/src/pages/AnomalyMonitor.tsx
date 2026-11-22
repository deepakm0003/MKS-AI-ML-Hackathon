import { useMemo } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { DataTable, type Column } from "../components/DataTable";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt, fmtMonthShort, fmtPct } from "../lib/format";
import { SERIES } from "../theme/chart";

interface AnomalyRow {
  Date: string;
  SKU_ID: string;
  Region: string;
  Product_Family: string;
  Units_Shipped: number;
  Demand: number;
  Expected: number;
  Type: string;
  Category: string;
  Detection: string;
  Reason: string;
  Action: string;
  Confidence: string;
}

interface StructuralRow {
  Type: string;
  Date: string;
  SKU_ID: string;
  Region: string;
  Detail: string;
  Evidence: string;
  Action: string;
}

interface EventImpactRow {
  Event_ID: string;
  Event_Type: string;
  Description: string;
  Shipped_Impact_Pct: number;
  Demand_Impact_Pct: number;
  Method: string;
  Verdict: string;
}

const CAT_TONE: Record<string, "critical" | "warning" | "good" | "accent"> = {
  stockout: "critical", spike: "warning", drop: "warning",
  real_event: "accent", gap: "warning",
};

/** 08 Anomaly Monitor — flagged points on the time series with type, reason and the action taken. */
export function AnomalyMonitor() {
  const anomalies = useApi((s) => api.dataset<AnomalyRow>("anomaly_register", { limit: 10000 }, s), []);
  const structural = useApi((s) => api.dataset<StructuralRow>("structural_register", { limit: 10000 }, s), []);
  const events = useApi((s) => api.dataset<EventImpactRow>("event_impact", {}, s), []);

  const rows = anomalies.status === "success" ? anomalies.data.rows : [];

  // KPI computations
  const catCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.Category] = (counts[r.Category] ?? 0) + 1;
    return counts;
  }, [rows]);

  const totalAnomalies = anomalies.status === "success" ? anomalies.data.total : 0;
  const spikeCount = catCounts["spike"] ?? 0;
  const dropCount = catCounts["drop"] ?? 0;
  const stockoutCount = catCounts["stockout"] ?? 0;

  // Anomaly count by category
  const categoryChart = useMemo(() => {
    if (!rows.length) return null;
    const sorted = Object.entries(catCounts).sort((a, b) => b[1] - a[1]);
    return verticalBarsOption(
      sorted.map(([k]) => k),
      [{ name: "Anomalies", data: sorted.map(([, v]) => v) }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true },
    );
  }, [rows, catCounts]);

  // Anomaly count by month
  const monthChart = useMemo(() => {
    if (!rows.length) return null;
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.Date] = (counts[r.Date] ?? 0) + 1;
    const sorted = Object.entries(counts).sort((a, b) => a[0].localeCompare(b[0]));
    return verticalBarsOption(
      sorted.map(([k]) => fmtMonthShort(k)),
      [{ name: "Anomalies", data: sorted.map(([, v]) => v), color: SERIES[2] }],
      { valueFormatter: (v) => fmtInt(v), rotateLabels: true, yAxisName: "Count" },
    );
  }, [rows]);

  // Anomaly register columns
  const anomalyCols = useMemo<Column<AnomalyRow>[]>(() => [
    { key: "date", label: "Month", value: (r) => r.Date, render: (r) => fmtMonthShort(r.Date) },
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID, render: (r) => <span className="mono">{r.SKU_ID}</span> },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "family", label: "Family", value: (r) => r.Product_Family },
    { key: "category", label: "Category", value: (r) => r.Category, render: (r) => (
      <Badge tone={CAT_TONE[r.Category] ?? "neutral"}>{r.Category}</Badge>
    ) },
    { key: "type", label: "Type", value: (r) => r.Type },
    { key: "shipped", label: "Shipped", value: (r) => r.Units_Shipped, render: (r) => fmtInt(r.Units_Shipped), align: "right" },
    { key: "demand", label: "Demand", value: (r) => r.Demand, render: (r) => fmtInt(r.Demand), align: "right" },
    { key: "expected", label: "Expected", value: (r) => r.Expected, render: (r) => fmtInt(r.Expected), align: "right" },
    { key: "reason", label: "Reason", value: (r) => r.Reason, render: (r) => (
      <span style={{ fontSize: 12, color: "var(--text-3)" }}>{r.Reason}</span>
    ) },
    { key: "action", label: "Action", value: (r) => r.Action, render: (r) => (
      <span style={{ fontSize: 12, color: "var(--text-2)" }}>{r.Action}</span>
    ) },
    { key: "confidence", label: "Confidence", value: (r) => r.Confidence, render: (r) => (
      <Badge tone={r.Confidence === "HIGH" ? "good" : r.Confidence === "MEDIUM" ? "warning" : "serious"}>{r.Confidence}</Badge>
    ) },
  ], []);

  // Event impact columns
  const eventCols = useMemo<Column<EventImpactRow>[]>(() => [
    { key: "id", label: "Event ID", value: (r) => r.Event_ID, render: (r) => <span className="mono">{r.Event_ID}</span> },
    { key: "type", label: "Type", value: (r) => r.Event_Type },
    { key: "desc", label: "Description", value: (r) => r.Description },
    { key: "ship_impact", label: "Shipped impact", value: (r) => r.Shipped_Impact_Pct, render: (r) => fmtPct(r.Shipped_Impact_Pct, 1), align: "right" },
    { key: "demand_impact", label: "Demand impact", value: (r) => r.Demand_Impact_Pct, render: (r) => fmtPct(r.Demand_Impact_Pct, 1), align: "right" },
    { key: "method", label: "Method", value: (r) => r.Method, render: (r) => <span style={{ fontSize: 12 }} className="mono">{r.Method}</span> },
    { key: "verdict", label: "Verdict", value: (r) => r.Verdict, render: (r) => (
      <Badge tone={r.Verdict === "confirmed" || r.Verdict === "CONFIRMED" ? "good" : "warning"}>{r.Verdict}</Badge>
    ) },
  ], []);

  // Structural register columns
  const structCols = useMemo<Column<StructuralRow>[]>(() => [
    { key: "type", label: "Type", value: (r) => r.Type, render: (r) => <Badge tone="accent">{r.Type}</Badge> },
    { key: "date", label: "Date", value: (r) => r.Date },
    { key: "sku", label: "SKU", value: (r) => r.SKU_ID, render: (r) => <span className="mono">{r.SKU_ID}</span> },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "detail", label: "Detail", value: (r) => r.Detail },
    { key: "evidence", label: "Evidence", value: (r) => r.Evidence, render: (r) => (
      <span style={{ fontSize: 12, color: "var(--text-3)" }}>{r.Evidence}</span>
    ) },
    { key: "action", label: "Action", value: (r) => r.Action },
  ], []);

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Anomaly Monitor · Flagged points & structural changes</p>
          <h2 className="page__title">Which months were errors, which were real events, and how was demand recovered</h2>
          <p className="page__lead">
            Every flagged month with its type, category, reason and the action taken to recover
            unconstrained demand. Structural changes and event impacts tracked separately.
          </p>
        </div>
      </div>

      {/* KPI row */}
      <section className="kpi-row" aria-label="Anomaly summary">
        <KpiTile
          label="Total anomalies" emphasis="accent" loading={anomalies.status === "loading"}
          value={fmtInt(totalAnomalies)} unit="flagged"
          sub="Across all SKU × region × month"
          footnote="From the anomaly register"
        />
        <KpiTile
          label="Spikes" loading={anomalies.status === "loading"}
          value={fmtInt(spikeCount)} unit="months"
          sub="Demand well above expected"
          footnote="Investigated and categorized"
        />
        <KpiTile
          label="Drops" loading={anomalies.status === "loading"}
          value={fmtInt(dropCount)} unit="months"
          sub="Demand well below expected"
          footnote="Investigated and categorized"
        />
        <KpiTile
          label="Stockouts" loading={anomalies.status === "loading"}
          value={fmtInt(stockoutCount)} unit="months" emphasis={stockoutCount > 0 ? "critical" : undefined}
          sub="Constrained supply, demand recovered"
          footnote="Lost sales recovered from files"
        />
      </section>

      {/* Category + month distribution */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Anomalies by category" subtitle="Count of flagged months per category type">
            {anomalies.status === "loading" ? <Skeleton height={260} /> :
              anomalies.status === "error" ? <ErrorState error={anomalies.error} onRetry={anomalies.retry} /> :
                categoryChart ? (
                  <div style={{ padding: "16px 20px 20px" }}>
                    <EChart height={260} label="Anomalies by category" option={categoryChart} />
                  </div>
                ) : <EmptyState title="No anomalies" icon="check" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Anomalies over time" subtitle="Flagged months across the history">
            {anomalies.status === "loading" ? <Skeleton height={260} /> :
              monthChart ? (
                <div style={{ padding: "16px 20px 20px" }}>
                  <EChart height={260} label="Anomalies by month" option={monthChart} />
                </div>
              ) : <EmptyState title="No anomalies" icon="check" />}
          </Card>
        </div>
      </div>

      {/* Event impact */}
      <Card title="Event impact" subtitle="Real-world events that moved demand — shipped and demand impact, method and verdict">
        {events.status === "loading" ? <Skeleton height={280} /> :
          events.status === "error" ? <ErrorState error={events.error} onRetry={events.retry} /> :
            events.data.rows.length > 0 ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={eventCols} rows={events.data.rows} caption="Event impact"
                  maxHeight={280} />
              </div>
            ) : <EmptyState title="No events" message="No real-world events required demand recovery." icon="check" />}
      </Card>

      {/* Anomaly register table */}
      <Card title="Anomaly register" subtitle="Every flagged month — type, category, detection method, reason and the action taken to recover demand">
        {anomalies.status === "loading" ? <Skeleton height={420} /> :
          anomalies.status === "error" ? <ErrorState error={anomalies.error} onRetry={anomalies.retry} /> :
            rows.length > 0 ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={anomalyCols} rows={rows} caption="Anomaly register"
                  maxHeight={480} initialSort={{ key: "date", dir: "desc" }} />
              </div>
            ) : <EmptyState title="No anomalies" message="No months were flagged in the history." icon="check" />}
      </Card>

      {/* Structural register */}
      <Card title="Structural changes" subtitle="Ordering-cycle changes, product transitions and other structural breaks — with evidence and action">
        {structural.status === "loading" ? <Skeleton height={320} /> :
          structural.status === "error" ? <ErrorState error={structural.error} onRetry={structural.retry} /> :
            structural.data.rows.length > 0 ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={structCols} rows={structural.data.rows} caption="Structural register"
                  maxHeight={360} initialSort={{ key: "date", dir: "desc" }} />
              </div>
            ) : <EmptyState title="No structural changes" icon="check" />}
      </Card>
    </div>
  );
}
