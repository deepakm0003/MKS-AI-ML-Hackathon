import { useMemo } from "react";
import { api, request } from "../api/client";
import { useApi } from "../api/useApi";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { DataTable, type Column } from "../components/DataTable";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt } from "../lib/format";
import { SERIES } from "../theme/chart";

interface DqIssueRow {
  file: string;
  row_ref: string;
  issue_type: string;
  category: string;
  field: string;
  original: string;
  corrected: string;
  action: string;
  rule: string;
}

interface RunReport {
  validation_status: string;
  [k: string]: unknown;
}

/** 07 Data Health — what was wrong with the raw ERP extract, what cleaning changed, and why. */
export function DataHealth() {
  const issues = useApi((s) => api.dataset<DqIssueRow>("dq_issue_log", { limit: 10000 }, s), []);
  const runReport = useApi((s) => request<RunReport>("/datasets/run_report", { signal: s }), []);

  // KPI computations
  const rows = issues.status === "success" ? issues.data.rows : [];
  const uniqueRows = new Set(rows.map((r) => r.row_ref)).size;
  const uniqueFiles = new Set(rows.map((r) => r.file)).size;
  const validation = runReport.status === "success" ? runReport.data.validation_status : "—";

  // Issues by type bar chart
  const typeChart = useMemo(() => {
    if (!rows.length) return null;
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.issue_type] = (counts[r.issue_type] ?? 0) + 1;
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return verticalBarsOption(
      sorted.map(([k]) => k),
      [{ name: "Issues", data: sorted.map(([, v]) => v) }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true },
    );
  }, [rows]);

  // Issues by category bar chart
  const categoryChart = useMemo(() => {
    if (!rows.length) return null;
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.category] = (counts[r.category] ?? 0) + 1;
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return verticalBarsOption(
      sorted.map(([k]) => k),
      [{ name: "Issues", data: sorted.map(([, v]) => v), color: SERIES[2] }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true },
    );
  }, [rows]);

  // Issues by file bar chart
  const fileChart = useMemo(() => {
    if (!rows.length) return null;
    const counts: Record<string, number> = {};
    for (const r of rows) counts[r.file] = (counts[r.file] ?? 0) + 1;
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return verticalBarsOption(
      sorted.map(([k]) => k.split("/").pop() || k),
      [{ name: "Issues", data: sorted.map(([, v]) => v), color: SERIES[4] }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true },
    );
  }, [rows]);

  // Table columns
  const issueCols = useMemo<Column<DqIssueRow>[]>(() => [
    { key: "file", label: "File", value: (r) => r.file, render: (r) => (
      <span style={{ fontSize: 12 }} className="mono">{r.file.split("/").pop() || r.file}</span>
    ) },
    { key: "row_ref", label: "Row", value: (r) => r.row_ref, render: (r) => (
      <span style={{ fontSize: 12 }} className="mono">{r.row_ref}</span>
    ) },
    { key: "issue_type", label: "Type", value: (r) => r.issue_type, render: (r) => (
      <Badge tone={r.issue_type.includes("error") || r.issue_type.includes("invalid") ? "critical" : "warning"}>{r.issue_type}</Badge>
    ) },
    { key: "category", label: "Category", value: (r) => r.category },
    { key: "field", label: "Field", value: (r) => r.field },
    { key: "original", label: "Original", value: (r) => r.original, render: (r) => (
      <span style={{ fontSize: 12, color: "var(--critical)" }} className="mono">{r.original}</span>
    ) },
    { key: "corrected", label: "Corrected", value: (r) => r.corrected, render: (r) => (
      <span style={{ fontSize: 12, color: "var(--good)" }} className="mono">{r.corrected}</span>
    ) },
    { key: "action", label: "Action", value: (r) => r.action },
    { key: "rule", label: "Rule", value: (r) => r.rule, render: (r) => (
      <span style={{ fontSize: 12 }} className="mono">{r.rule}</span>
    ) },
  ], []);

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Data Health · Cleaning & validation</p>
          <h2 className="page__title">What was wrong with the raw ERP extract, and what cleaning changed</h2>
          <p className="page__lead">
            Every data-quality correction logged with the original value, the corrected value, the rule
            applied and the action taken. Validation status from the frozen pipeline run.
          </p>
        </div>
      </div>

      {/* KPI row */}
      <section className="kpi-row" aria-label="Data quality summary">
        <KpiTile
          label="Total issues fixed" emphasis="accent" loading={issues.status === "loading"}
          value={issues.status === "success" ? fmtInt(issues.data.total) : "—"}
          sub="Corrections applied during cleaning"
          footnote="From the DQ issue log"
        />
        <KpiTile
          label="Rows affected" loading={issues.status === "loading"}
          value={fmtInt(uniqueRows)} unit="rows"
          sub={`${uniqueFiles} files touched`}
          footnote="Distinct rows with at least one correction"
        />
        <KpiTile
          label="Files affected" loading={issues.status === "loading"}
          value={fmtInt(uniqueFiles)} unit="files"
          sub="Source files with corrections"
          footnote="Raw ERP extracts and inputs"
        />
        <KpiTile
          label="Validation" loading={runReport.status === "loading"}
          emphasis={validation === "PASS" || validation === "pass" ? "accent" : "critical"}
          value={validation}
          sub={runReport.status === "success" ? "Contract checks passed" : runReport.status === "error" ? "Report unavailable" : "Checking…"}
          footnote="Frozen pipeline run report"
        />
      </section>

      {issues.status === "error" && <Card><ErrorState error={issues.error} onRetry={issues.retry} /></Card>}

      {/* Issues by type + category */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Issues by type" subtitle="Count of each issue type found in the raw data">
            {issues.status === "loading" ? <Skeleton height={260} /> :
              typeChart ? (
                <div style={{ padding: "16px 20px 20px" }}>
                  <EChart height={260} label="Data quality issues by type" option={typeChart} />
                </div>
              ) : <EmptyState title="No issues logged" icon="check" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Issues by category" subtitle="Corrections grouped by category">
            {issues.status === "loading" ? <Skeleton height={260} /> :
              categoryChart ? (
                <div style={{ padding: "16px 20px 20px" }}>
                  <EChart height={260} label="Data quality issues by category" option={categoryChart} />
                </div>
              ) : <EmptyState title="No issues logged" icon="check" />}
          </Card>
        </div>
      </div>

      {/* Issues by file */}
      <Card title="Issues by file" subtitle="Corrections per source file — where the raw data was dirtiest">
        {issues.status === "loading" ? <Skeleton height={260} /> :
          fileChart ? (
            <div style={{ padding: "16px 20px 20px" }}>
              <EChart height={260} label="Data quality issues by file" option={fileChart} />
            </div>
          ) : <EmptyState title="No issues logged" icon="check" />}
      </Card>

      {/* DQ issue log table */}
      <Card title="Data quality issue log" subtitle="Every correction: original → corrected, the rule applied and the action taken">
        {issues.status === "loading" ? <Skeleton height={400} /> :
          rows.length > 0 ? (
            <div style={{ padding: "8px 20px 20px" }}>
              <DataTable columns={issueCols} rows={rows} caption="DQ issue log"
                maxHeight={500} initialSort={{ key: "file", dir: "asc" }} />
            </div>
          ) : <EmptyState title="No issues" message="No data quality corrections were needed." icon="check" />}
      </Card>
    </div>
  );
}
