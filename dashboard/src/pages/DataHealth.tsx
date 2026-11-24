import { useMemo } from "react";
import { api, request } from "../api/client";
import type { DataHealthView } from "../api/types";
import { useApi } from "../api/useApi";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { DataTable, type Column } from "../components/DataTable";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt } from "../lib/format";
import { SERIES } from "../theme/chart";

interface RunReport {
  validation_status: string;
  [k: string]: unknown;
}

type IssueRow = DataHealthView["rows"][number];
type RuleRow = DataHealthView["rule_summary"][number];
type FileProfile = DataHealthView["before_after"][number];

const CAT_TONE: Record<string, "critical" | "warning" | "neutral" | "accent"> = {
  error: "critical", gap: "warning", reference: "accent", info: "neutral",
};

/** Data Health — what was wrong with the raw ERP extract, what cleaning changed (before vs after), and why. */
export function DataHealth() {
  const st = useApi((s) => api.dataHealthView({ top: 500 }, s), []);
  const runReport = useApi((s) => request<RunReport>("/datasets/run_report", { signal: s }), []);
  const d = st.status === "success" ? st.data : undefined;
  const validation = runReport.status === "success" ? runReport.data.validation_status : undefined;

  const typeChart = useMemo(() => d && verticalBarsOption(
    d.by_issue_type.slice(0, 14).map((t) => t.issue_type.replace(/_/g, " ")),
    [{ name: "Issues", data: d.by_issue_type.slice(0, 14).map((t) => t.count) }],
    { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true }), [d]);

  const fileChart = useMemo(() => {
    if (!d) return null;
    const files = Object.entries(d.by_file).sort((a, b) => b[1] - a[1]);
    return verticalBarsOption(files.map(([k]) => k), [{ name: "Issues", data: files.map(([, v]) => v), color: SERIES[1] }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true });
  }, [d]);

  // before vs after: null cells per file on one axis (rows differ by orders of magnitude, so they go in the table)
  const nullChart = useMemo(() => {
    if (!d) return null;
    const files = d.before_after.filter((f) => (f.null_cells_before ?? 0) + (f.null_cells_after ?? 0) > 0);
    return verticalBarsOption(files.map((f) => f.file),
      [{ name: "Empty cells before", data: files.map((f) => f.null_cells_before ?? 0), color: SERIES[5] },
        { name: "Empty cells after", data: files.map((f) => f.null_cells_after ?? 0), color: SERIES[0] }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true });
  }, [d]);

  const profileCols = useMemo<Column<FileProfile>[]>(() => [
    { key: "file", label: "File", value: (r) => r.file, render: (r) => <span className="mono">{r.file}</span> },
    { key: "rb", label: "Rows before", value: (r) => r.rows_before, render: (r) => fmtInt(r.rows_before), align: "right" },
    { key: "ra", label: "Rows after", value: (r) => r.rows_after, render: (r) => fmtInt(r.rows_after), align: "right" },
    { key: "rd", label: "Δ rows", value: (r) => (r.rows_after ?? 0) - (r.rows_before ?? 0),
      render: (r) => fmtInt((r.rows_after ?? 0) - (r.rows_before ?? 0)), align: "right" },
    { key: "cols", label: "Columns", value: (r) => r.columns_after, render: (r) => `${r.columns_before} → ${r.columns_after}`, align: "right" },
    { key: "nb", label: "Empty cells before", value: (r) => r.null_cells_before, render: (r) => fmtInt(r.null_cells_before), align: "right" },
    { key: "na", label: "Empty cells after", value: (r) => r.null_cells_after, render: (r) => fmtInt(r.null_cells_after), align: "right" },
    { key: "cols_fixed", label: "Columns with gaps (before → after)", value: (r) => Object.keys(r.nulls_by_column_before ?? {}).length,
      render: (r) => {
        const b = Object.entries(r.nulls_by_column_before ?? {});
        if (!b.length) return <span className="muted">none</span>;
        return <span style={{ fontSize: 12 }}>{b.map(([c, n]) => `${c} ${fmtInt(n)} → ${fmtInt((r.nulls_by_column_after ?? {})[c] ?? 0)}`).join(" · ")}</span>;
      }, sortable: false },
  ], []);

  const ruleCols = useMemo<Column<RuleRow>[]>(() => [
    { key: "file", label: "File", value: (r) => r.file, render: (r) => <span className="mono">{r.file}</span> },
    { key: "cat", label: "Category", value: (r) => r.category, render: (r) => <Badge tone={CAT_TONE[r.category] ?? "neutral"} icon={null}>{r.category}</Badge> },
    { key: "type", label: "Issue", value: (r) => r.issue_type, render: (r) => r.issue_type.replace(/_/g, " ") },
    { key: "action", label: "Action", value: (r) => r.action },
    { key: "rows", label: "Rows", value: (r) => r.rows, render: (r) => fmtInt(r.rows), align: "right" },
  ], []);

  const issueCols = useMemo<Column<IssueRow>[]>(() => [
    { key: "file", label: "File", value: (r) => r.file, render: (r) => <span style={{ fontSize: 12 }} className="mono">{r.file}</span> },
    { key: "row_ref", label: "Row", value: (r) => r.row_ref, render: (r) => <span style={{ fontSize: 12 }} className="mono">{r.row_ref}</span> },
    { key: "issue_type", label: "Issue", value: (r) => r.issue_type, render: (r) => r.issue_type.replace(/_/g, " ") },
    { key: "category", label: "Category", value: (r) => r.category, render: (r) => <Badge tone={CAT_TONE[r.category] ?? "neutral"} icon={null}>{r.category}</Badge> },
    { key: "field", label: "Field", value: (r) => r.field },
    { key: "original", label: "Original", value: (r) => r.original, render: (r) => <span style={{ fontSize: 12 }} className="mono">{r.original}</span> },
    { key: "corrected", label: "Corrected", value: (r) => r.corrected, render: (r) => <span style={{ fontSize: 12, color: "var(--text-1)" }} className="mono">{r.corrected}</span> },
    { key: "action", label: "Action", value: (r) => r.action },
    { key: "rule", label: "Rule", value: (r) => r.rule, render: (r) => <span style={{ fontSize: 12 }}>{r.rule}</span> },
  ], []);

  const train = d?.before_after.find((f) => f.file === "train.csv");

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Data Health · cleaning & validation</p>
          <h2 className="page__title">What was wrong with the raw ERP extract, and what cleaning changed</h2>
          <p className="page__lead">
            Every correction logged with the original value, the corrected value and the rule applied — and the state of
            each raw file before and after cleaning. (Issues concern raw files, so the product filters do not apply here.)
          </p>
        </div>
      </div>

      {st.status === "error" ? <Card><ErrorState error={st.error} onRetry={st.retry} /></Card> : (
        <section className="kpi-row" aria-label="Data quality summary">
          <KpiTile label="Issues fixed" emphasis="accent" loading={!d} value={fmtInt(d?.total_all_files)}
            sub={d ? `${Object.keys(d.by_file).length} raw files corrected` : undefined} footnote="Full data-quality log" />
          <KpiTile label="Rows touched" loading={!d} value={fmtInt(d?.rows_affected)} unit="rows"
            sub="Distinct raw rows with at least one correction" />
          <KpiTile label="train.csv before → after" loading={!d}
            value={train ? `${fmtInt(train.rows_before)} → ${fmtInt(train.rows_after)}` : undefined}
            sub={train ? `Empty cells ${fmtInt(train.null_cells_before)} → ${fmtInt(train.null_cells_after)} · duplicates removed, one row per date-SKU-region` : undefined} />
          <KpiTile label="Validation" loading={runReport.status === "loading"} emphasis={validation === "PASS" ? "accent" : "critical"}
            value={validation ?? (runReport.status === "error" ? "—" : undefined)}
            sub={runReport.status === "success" ? "Run report of the cleaning stage" : runReport.status === "error" ? "Run report unavailable" : undefined} />
        </section>
      )}

      <Card title="Before vs after cleaning" subtitle="Rows, columns and empty cells of every raw file — as delivered and after the cleaning pipeline">
        {st.status === "loading" ? <Skeleton height={300} /> : d ? (
          <div style={{ padding: "8px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
            {nullChart && <EChart height={240} label="Empty cells per file before and after cleaning" option={nullChart} />}
            <DataTable columns={profileCols} rows={d.before_after} caption="Before vs after cleaning" maxHeight={320}
              exportable exportFilename="before_after_cleaning" />
          </div>
        ) : null}
      </Card>

      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Issues by type" subtitle="Full issue log, largest first">
            {st.status === "loading" ? <Skeleton height={260} /> : typeChart ? (
              <div style={{ padding: "16px 20px 20px" }}><EChart height={260} label="Issues by type" option={typeChart} /></div>
            ) : <EmptyState title="No issues logged" icon="check" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Issues by file" subtitle="Where the raw data was dirtiest">
            {st.status === "loading" ? <Skeleton height={260} /> : fileChart ? (
              <div style={{ padding: "16px 20px 20px" }}><EChart height={260} label="Issues by file" option={fileChart} /></div>
            ) : <EmptyState title="No issues logged" icon="check" />}
          </Card>
        </div>
      </div>

      <Card title="Cleaning rules applied" subtitle="Each rule, the file it touched, the action taken and the rows affected">
        {st.status === "loading" ? <Skeleton height={300} /> : d && d.rule_summary.length ? (
          <div style={{ padding: "8px 20px 20px" }}>
            <DataTable columns={ruleCols} rows={d.rule_summary} caption="Cleaning rules" maxHeight={360}
              initialSort={{ key: "rows", dir: "desc" }} exportable exportFilename="cleaning_rules" />
          </div>
        ) : <EmptyState title="No rules logged" icon="check" />}
      </Card>

      <Card title="Data quality issue log"
        subtitle={d ? `First ${fmtInt(d.rows.length)} of ${fmtInt(d.total)} corrections — original → corrected, rule and action` : "Every correction"}>
        {st.status === "loading" ? <Skeleton height={400} /> : d && d.rows.length > 0 ? (
          <div style={{ padding: "8px 20px 20px" }}>
            <DataTable columns={issueCols} rows={d.rows} caption="Data quality issue log" maxHeight={420}
              exportable exportFilename="dq_issue_log" />
          </div>
        ) : <EmptyState title="No issues" icon="check" />}
      </Card>
    </div>
  );
}
