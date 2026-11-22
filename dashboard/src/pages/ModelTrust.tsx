import { useMemo } from "react";
import { api, request } from "../api/client";
import { useApi } from "../api/useApi";
import { EChart } from "../charts/EChart";
import { genericRankedBarsOption, verticalBarsOption } from "../charts/options";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icon";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtPct } from "../lib/format";
import { STATUS } from "../theme/chart";

interface ManifestData {
  selected_model: string;
  selection_reason: string;
  spec: Record<string, unknown>;
  features: Record<string, unknown>;
  backtest: { WAPE: number; Bias: number; family_month_WAPE: number; total_month_WAPE: number };
  validation: string;
  frozen_at: string;
}

interface BacktestMetrics {
  overall: { WAPE: number; Bias: number; MAE: number; RMSE: number };
  by_horizon_bucket: Record<string, number>;
  by_Product_Family: Record<string, number>;
  by_Region: Record<string, number>;
  by_Demand_Class: Record<string, number>;
  by_Volume_Band: Record<string, number>;
  by_Lifecycle: Record<string, number>;
  family_month: { WAPE: number };
  total_month: { WAPE: number };
  seasonal_naive_overall: number;
}

interface ExperimentRow {
  experiment: string;
  description: string;
  WAPE: number;
  Bias: number;
  MAE: number;
  RMSE: number;
  "WAPE_1-3m": number;
  "WAPE_4-6m": number;
  "WAPE_7-12m": number;
  "WAPE_13-19m": number;
  WAPE_family_month: number;
  WAPE_total_month: number;
  verdict: string;
}

interface BandCoverageRow {
  Level: string;
  Held_Out_Cutoff: string;
  Points: number;
  Coverage_P10_P90: number;
}

interface HorizonReliabilityRow {
  h: number;
  WAPE_series: number;
  Bias_series: number;
  WAPE_family_month: number;
  WAPE_total_month: number;
}

interface IntervalReliabilityRow {
  Segment: string;
  Value: string;
  Rows: number;
  Coverage_P10_P90: number;
}

/** 06 Model Trust — accuracy, backtests, uncertainty calibration, experiment registry. */
export function ModelTrust() {
  const manifest = useApi((s) => request<ManifestData>("/datasets/manifest", { signal: s }), []);
  const backtest = useApi((s) => request<BacktestMetrics>("/datasets/backtest_metrics", { signal: s }), []);
  const experiments = useApi((s) => api.dataset<ExperimentRow>("experiment_registry", {}, s), []);
  const bandCoverage = useApi((s) => api.dataset<BandCoverageRow>("band_coverage", {}, s), []);
  const horizonRel = useApi((s) => api.dataset<HorizonReliabilityRow>("horizon_reliability", {}, s), []);
  const intervalRel = useApi((s) => api.dataset<IntervalReliabilityRow>("interval_reliability", {}, s), []);

  const loading = manifest.status === "loading" || backtest.status === "loading";
  const bt = backtest.status === "success" ? backtest.data : undefined;
  const model = manifest.status === "success" ? manifest.data.selected_model : "—";

  // WAPE by horizon bucket chart
  const horizonChart = useMemo(() => {
    if (!bt?.by_horizon_bucket) return null;
    const order = ["1-3m", "4-6m", "7-12m", "13-19m"];
    const cats = order.filter((k) => bt.by_horizon_bucket[k] != null);
    if (!cats.length) return null;
    return verticalBarsOption(
      cats,
      [{ name: "WAPE", data: cats.map((k) => bt.by_horizon_bucket[k]) }],
      { valueFormatter: (v) => fmtPct(v, 1), showLabels: true, yAxisName: "WAPE" },
    );
  }, [bt]);

  // Experiment comparison ranked bars
  const expChart = useMemo(() => {
    if (experiments.status !== "success" || !experiments.data.rows.length) return null;
    return genericRankedBarsOption(
      experiments.data.rows.map((r) => ({ label: r.experiment, value: r.WAPE })),
      { valueFormatter: (v) => fmtPct(v, 1) },
    );
  }, [experiments]);

  // Experiment table columns
  const expCols = useMemo<Column<ExperimentRow>[]>(() => [
    { key: "experiment", label: "Experiment", value: (r) => r.experiment, render: (r) => (
      <div>
        <div style={{ fontWeight: 600 }}>{r.experiment}</div>
        <div style={{ fontSize: 12, color: "var(--text-3)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.description}</div>
      </div>
    ) },
    { key: "WAPE", label: "WAPE", value: (r) => r.WAPE, render: (r) => fmtPct(r.WAPE, 1), align: "right" },
    { key: "Bias", label: "Bias", value: (r) => r.Bias, render: (r) => fmtPct(r.Bias, 1), align: "right" },
    { key: "MAE", label: "MAE", value: (r) => r.MAE, render: (r) => r.MAE.toFixed(2), align: "right" },
    { key: "RMSE", label: "RMSE", value: (r) => r.RMSE, render: (r) => r.RMSE.toFixed(2), align: "right" },
    { key: "WAPE_1-3m", label: "1–3m", value: (r) => r["WAPE_1-3m"], render: (r) => fmtPct(r["WAPE_1-3m"], 1), align: "right" },
    { key: "WAPE_4-6m", label: "4–6m", value: (r) => r["WAPE_4-6m"], render: (r) => fmtPct(r["WAPE_4-6m"], 1), align: "right" },
    { key: "WAPE_7-12m", label: "7–12m", value: (r) => r["WAPE_7-12m"], render: (r) => fmtPct(r["WAPE_7-12m"], 1), align: "right" },
    { key: "WAPE_13-19m", label: "13–19m", value: (r) => r["WAPE_13-19m"], render: (r) => fmtPct(r["WAPE_13-19m"], 1), align: "right" },
    { key: "verdict", label: "Verdict", value: (r) => r.verdict, render: (r) => (
      <Badge tone={r.verdict === "champion" || r.verdict === "PROMOTED" ? "good" : "warning"}>{r.verdict}</Badge>
    ) },
  ], []);

  // Band coverage columns
  const bandCols = useMemo<Column<BandCoverageRow>[]>(() => [
    { key: "level", label: "Level", value: (r) => r.Level },
    { key: "cutoff", label: "Held-out cutoff", value: (r) => r.Held_Out_Cutoff },
    { key: "points", label: "Points", value: (r) => r.Points, align: "right" },
    { key: "coverage", label: "P10–P90 coverage", value: (r) => r.Coverage_P10_P90,
      render: (r) => (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          {fmtPct(r.Coverage_P10_P90, 0)}
          {r.Coverage_P10_P90 >= 0.75 ? <Icon name="check" size={12} style={{ color: STATUS.good }} /> : <Icon name="alert" size={12} style={{ color: STATUS.warning }} />}
        </span>
      ), align: "right" },
  ], []);

  // Horizon reliability columns
  const horizonCols = useMemo<Column<HorizonReliabilityRow>[]>(() => [
    { key: "h", label: "Horizon (m)", value: (r) => r.h, align: "right" },
    { key: "wape_series", label: "WAPE series", value: (r) => r.WAPE_series, render: (r) => fmtPct(r.WAPE_series, 1), align: "right" },
    { key: "bias", label: "Bias series", value: (r) => r.Bias_series, render: (r) => fmtPct(r.Bias_series, 1), align: "right" },
    { key: "wape_fm", label: "WAPE family-mo", value: (r) => r.WAPE_family_month, render: (r) => fmtPct(r.WAPE_family_month, 1), align: "right" },
    { key: "wape_tm", label: "WAPE total-mo", value: (r) => r.WAPE_total_month, render: (r) => fmtPct(r.WAPE_total_month, 1), align: "right" },
  ], []);

  // Interval reliability columns
  const intervalCols = useMemo<Column<IntervalReliabilityRow>[]>(() => [
    { key: "segment", label: "Segment", value: (r) => r.Segment },
    { key: "value", label: "Value", value: (r) => r.Value },
    { key: "rows", label: "Rows", value: (r) => r.Rows, align: "right" },
    { key: "coverage", label: "P10–P90 coverage", value: (r) => r.Coverage_P10_P90,
      render: (r) => fmtPct(r.Coverage_P10_P90, 0), align: "right" },
  ], []);

  if (loading) return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Model Trust · Accuracy & Methodology</p>
          <h2 className="page__title">Forecast model validation</h2>
          <p className="page__lead">Loading model accuracy, backtests and experiment registry…</p>
        </div>
      </div>
      <div className="kpi-row"><Skeleton height={128} /></div>
      <Skeleton height={300} />
    </div>
  );

  if (manifest.status === "error") return <div className="page"><Card><ErrorState error={manifest.error} onRetry={manifest.retry} /></Card></div>;
  if (backtest.status === "error") return <div className="page"><Card><ErrorState error={backtest.error} onRetry={backtest.retry} /></Card></div>;

  const overall = bt?.overall;
  const expCount = experiments.status === "success" ? experiments.data.total : 0;

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Model Trust · Accuracy & Methodology</p>
          <h2 className="page__title">How accurate is the forecast, and why this model</h2>
          <p className="page__lead">
            Selected model: <span className="mono" style={{ fontWeight: 600 }}>{model}</span> ·
            6-cutoff rolling-origin backtest · 19-month horizon · {expCount} experiments compared on identical folds
          </p>
        </div>
      </div>

      {/* KPI row */}
      <section className="kpi-row" aria-label="Backtest headline">
        <KpiTile
          label="Overall WAPE" emphasis="accent"
          value={overall ? fmtPct(overall.WAPE, 1) : "—"}
          sub={`MAE ${overall?.MAE?.toFixed(0) ?? "—"} · RMSE ${overall?.RMSE?.toFixed(0) ?? "—"}`}
          footnote="Weighted absolute % error across all 6 cutoffs"
        />
        <KpiTile
          label="Bias"
          value={overall ? fmtPct(overall.Bias, 1) : "—"}
          sub={overall && Math.abs(overall.Bias) < 0.01 ? "Unbiased" : overall && overall.Bias > 0 ? "Over-forecasting" : "Under-forecasting"}
          footnote="Systematic over/under prediction"
        />
        <KpiTile
          label="Experiments tested"
          value={expCount ? String(expCount) : "—"}
          sub="Champion vs challengers on identical folds"
          footnote="Promotion criteria applied to each"
        />
        <KpiTile
          label="Validation"
          emphasis={manifest.data.validation === "PASS" ? "accent" : "critical"}
          value={manifest.data.validation}
          sub={manifest.data.frozen_at}
          footnote="Contract checks on all frozen outputs"
        />
      </section>

      {/* WAPE by horizon + Experiment comparison */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="WAPE by forecast horizon" subtitle="How accuracy degrades over the 19-month horizon">
            {horizonChart ? (
              <div style={{ padding: "16px 20px 20px" }}>
                <EChart height={260} label="WAPE by forecast horizon bucket" option={horizonChart} />
              </div>
            ) : <EmptyState title="No horizon data" icon="database" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Experiment comparison" subtitle="WAPE for every experiment on identical folds">
            {experiments.status === "loading" ? <Skeleton height={260} /> :
              experiments.status === "error" ? <ErrorState error={experiments.error} onRetry={experiments.retry} /> :
                expChart ? (
                  <div style={{ padding: "16px 20px 20px" }}>
                    <EChart height={260} label="Experiment WAPE comparison" option={expChart} />
                  </div>
                ) : <EmptyState title="No experiments" icon="database" />}
          </Card>
        </div>
      </div>

      {/* Backtest detail by segment + Model selection */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Backtest accuracy by segment" subtitle="WAPE by family, region, demand class, volume band and lifecycle stage">
            {bt ? (
              <div style={{ padding: "12px 20px 20px" }}>
                {[
                  { title: "By product family", data: bt.by_Product_Family },
                  { title: "By region", data: bt.by_Region },
                  { title: "By demand class", data: bt.by_Demand_Class },
                  { title: "By volume band", data: bt.by_Volume_Band },
                  { title: "By lifecycle stage", data: bt.by_Lifecycle },
                ].filter((s) => s.data && Object.keys(s.data).length > 0).map((s) => (
                  <div key={s.title} style={{ marginBottom: 16 }}>
                    <h4 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-2)", marginBottom: 8 }}>{s.title}</h4>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {Object.entries(s.data).sort((a, b) => a[1] - b[1]).map(([k, v]) => (
                        <div key={k} style={{
                          display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 10px",
                          borderRadius: 6, background: "var(--surface-2)", fontSize: 12,
                        }}>
                          <span style={{ color: "var(--text-3)" }}>{k}</span>
                          <strong style={{ color: v < 0.1 ? STATUS.good : v < 0.2 ? STATUS.warning : STATUS.serious }}>{fmtPct(v as number, 1)}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : <EmptyState title="No segment data" icon="database" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Why this model" subtitle="Selection criteria and promotion rules">
            <div style={{ padding: "16px 20px 20px", fontSize: 13, lineHeight: 1.6 }}>
              <p style={{ marginBottom: 12 }}>
                <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-3)" }}>Selected</span><br />
                <span className="mono" style={{ fontWeight: 600 }}>{model}</span>
              </p>
              <p style={{ marginBottom: 12, color: "var(--text-2)" }}>
                {manifest.data.selection_reason}
              </p>
              <div style={{ fontSize: 12, color: "var(--text-3)" }}>
                <p style={{ marginBottom: 8, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>Promotion criteria</p>
                <ul style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                  <li>1. Mean WAPE gain ≥ 0.2 pp</li>
                  <li>2. No horizon worse by &gt; 0.3 pp</li>
                  <li>3. Bias not worse by &gt; 1 pp</li>
                  <li>4. Better on ≥ 67% of cutoffs</li>
                  <li>5. No segment worse by &gt; 0.5 pp</li>
                  <li>6. All tests pass</li>
                </ul>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Experiment registry full table */}
      {experiments.status === "success" && experiments.data.rows.length > 0 && (
        <Card title="Experiment registry" subtitle={`${expCount} experiments tested on identical validation folds, with promotion verdicts`}>
          <div style={{ padding: "8px 20px 20px" }}>
            <DataTable columns={expCols} rows={experiments.data.rows} caption="Experiment registry"
              maxHeight={500} initialSort={{ key: "WAPE", dir: "asc" }} />
          </div>
        </Card>
      )}

      {/* Band coverage + Horizon reliability */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="P10–P90 band coverage" subtitle="Leave-one-cutoff-out coverage of the aggregate uncertainty bands (target 80%)">
            {bandCoverage.status === "loading" ? <Skeleton height={260} /> :
              bandCoverage.status === "error" ? <ErrorState error={bandCoverage.error} onRetry={bandCoverage.retry} /> :
                bandCoverage.data.rows.length > 0 ? (
                  <div style={{ padding: "8px 20px 20px" }}>
                    <DataTable columns={bandCols} rows={bandCoverage.data.rows} caption="Band coverage"
                      maxHeight={260} />
                  </div>
                ) : <EmptyState title="No band coverage data" icon="database" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Horizon reliability" subtitle="WAPE and bias at each forecast horizon">
            {horizonRel.status === "loading" ? <Skeleton height={260} /> :
              horizonRel.status === "error" ? <ErrorState error={horizonRel.error} onRetry={horizonRel.retry} /> :
                horizonRel.data.rows.length > 0 ? (
                  <div style={{ padding: "8px 20px 20px" }}>
                    <DataTable columns={horizonCols} rows={horizonRel.data.rows} caption="Horizon reliability"
                      maxHeight={260} />
                  </div>
                ) : <EmptyState title="No horizon data" icon="database" />}
          </Card>
        </div>
      </div>

      {/* Interval reliability */}
      {intervalRel.status === "success" && intervalRel.data.rows.length > 0 && (
        <Card title="Interval reliability by segment" subtitle="P10–P90 coverage broken down by family, region, demand class and volume band">
          <div style={{ padding: "8px 20px 20px" }}>
            <DataTable columns={intervalCols} rows={intervalRel.data.rows} caption="Interval reliability"
              maxHeight={360} initialSort={{ key: "coverage", dir: "asc" }} />
          </div>
        </Card>
      )}
    </div>
  );
}
