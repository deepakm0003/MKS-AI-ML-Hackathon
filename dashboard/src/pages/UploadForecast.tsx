import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { ScoreJob, ScoreMetrics, ScoreResult, ScoreSeriesRow, ScoreUpload } from "../api/types";
import { EChart } from "../charts/EChart";
import { timelineOption, verticalBarsOption, type Metric } from "../charts/options";
import { Segmented } from "../components/ChartCard";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icon";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState } from "../components/ui";
import { fmtInt, fmtPct, fmtPctChange, fmtUnits, fmtUsd } from "../lib/format";
import { CHART, SERIES, STATUS } from "../theme/chart";

type Kind = "history" | "request";
type Slot = { status: "empty" } | { status: "uploading"; name: string } | { status: "ready"; info: ScoreUpload }
  | { status: "error"; name: string; message: string };

const SLOT_COPY: Record<Kind, { title: string; format: string; template: string; hint: string; empty: string }> = {
  history: {
    title: "Sales history", format: "train.csv format", template: "train_format_sample.csv",
    hint: "Monthly sales rows: Date, SKU_ID, Region, Units_Sold (+ the other train.csv columns). Goes through the full cleaning and demand-recovery pipeline.",
    empty: "Optional — without it the official cleaned history (2019-01 … 2026-10) is used.",
  },
  request: {
    title: "Rows to forecast", format: "test.csv format", template: "test_format_sample.csv",
    hint: "Date, SKU_ID, Region rows to score. Add a Units_Sold column with the real outcome to measure accuracy.",
    empty: "Optional — without it every active series is forecast for the next 19 months.",
  },
};

const msg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : String(e));

/** Upload & Forecast — score your own CSV files with the frozen model, on one page. */
export function UploadForecast() {
  const [params, setParams] = useSearchParams();
  const jobId = params.get("job");
  const [slots, setSlots] = useState<Record<Kind, Slot>>({ history: { status: "empty" }, request: { status: "empty" } });
  const [cutoff, setCutoff] = useState("");
  const [job, setJob] = useState<ScoreJob | null>(null);
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());

  const upload = async (kind: Kind, file: File) => {
    setSlots((s) => ({ ...s, [kind]: { status: "uploading", name: file.name } }));
    try {
      const info = await api.scoreUpload(file, kind);
      setSlots((s) => ({ ...s, [kind]: { status: "ready", info } }));
    } catch (e) {
      setSlots((s) => ({ ...s, [kind]: { status: "error", name: file.name, message: msg(e) } }));
    }
  };

  // poll the job until it finishes, then load the result
  useEffect(() => {
    if (!jobId) return;
    let stop = false;
    const ctl = new AbortController();
    setResult(null);
    setError(null);
    const tick = async () => {
      try {
        const s = await api.scoreStatus(jobId, ctl.signal);
        if (stop) return;
        setJob(s);
        if (s.status === "done") {
          const r = await api.scoreResult(jobId, ctl.signal);
          if (!stop) { setResult(r); setStartedAt(null); }
          return;
        }
        if (s.status === "error") { setError(s.error ?? "scoring failed"); setStartedAt(null); return; }
        window.setTimeout(tick, 700);
      } catch (e) {
        if (!stop && (e as Error).name !== "AbortError") setError(msg(e));
      }
    };
    tick();
    return () => { stop = true; ctl.abort(); };
  }, [jobId]);

  useEffect(() => {
    if (!startedAt) return;
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, [startedAt]);

  const ready = (k: Kind) => (slots[k].status === "ready" ? (slots[k] as { info: ScoreUpload }).info : null);
  const blocked = (["history", "request"] as Kind[]).some((k) => slots[k].status === "uploading"
    || (slots[k].status === "ready" && !(slots[k] as { info: ScoreUpload }).info.ok));
  const running = job !== null && (job.status === "queued" || job.status === "running") && !!jobId;

  const run = async () => {
    setError(null);
    setResult(null);
    try {
      const j = await api.scoreStart({
        history_upload: ready("history")?.upload_id, request_upload: ready("request")?.upload_id, cutoff: cutoff || undefined,
      });
      setJob(j);
      setStartedAt(Date.now());
      setParams({ job: j.job_id });
    } catch (e) {
      setError(msg(e));
    }
  };

  const histInfo = ready("history");
  const defaultOrigin = histInfo?.date_to ?? "2026-10";

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Upload & Forecast · the frozen model on your data</p>
          <h2 className="page__title">Upload a CSV, get the forecast, the bands and the accuracy</h2>
          <p className="page__lead">
            Your file goes through the same pipeline as the official data — cleaning, stockout and anomaly recovery,
            features — and is scored by the frozen model with the same business rules and calibrated P10–P90 bands.
            Include actual Units_Sold and the forecast is scored against them. Nothing is retrained.
          </p>
        </div>
      </div>

      <Card title="1 · Your data" subtitle="Both files are optional: leave one out and the official data takes its place">
        <div className="upl-grid">
          {(["history", "request"] as Kind[]).map((k) => (
            <DropSlot key={k} kind={k} slot={slots[k]} onFile={(f) => upload(k, f)}
              onClear={() => setSlots((s) => ({ ...s, [k]: { status: "empty" } }))} />
          ))}
        </div>
        <div className="upl-run">
          <label className="upl-origin">
            <span className="upl-origin__label">Forecast origin (last history month)</span>
            <input type="month" value={cutoff} min="2020-12" max={defaultOrigin}
              onChange={(e) => setCutoff(e.target.value)} aria-label="Forecast origin" />
            <span className="upl-origin__hint">
              Empty = {defaultOrigin}. An earlier month holds the later history out and scores the forecast against it.
            </span>
          </label>
          <button type="button" className="btn btn--accent" onClick={run} disabled={blocked || running}>
            <Icon name="refresh" size={14} /> {running ? "Scoring…" : "Score with the frozen model"}
          </button>
        </div>
      </Card>

      {jobId && job && job.steps.length > 0 && !result && (
        <Card title="2 · Running" subtitle={startedAt ? `${Math.round((now - startedAt) / 1000)} s elapsed` : undefined}>
          <ol className="upl-steps">
            {job.steps.map((s) => (
              <li key={s.id} className={`upl-step upl-step--${s.state}`}>
                <span className="upl-step__dot" aria-hidden>
                  {s.state === "done" ? <Icon name="check" size={12} /> : s.state === "failed" ? <Icon name="close" size={12} /> : null}
                </span>
                <span>{s.label}</span>
                <span className="muted num">{s.seconds !== null ? `${s.seconds}s` : s.state === "running" ? "…" : ""}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {error && (
        <div className="upl-banner upl-banner--error" role="alert">
          <Icon name="alert" size={16} /> <span><strong>Could not score:</strong> {error}</span>
        </div>
      )}

      {result && <Results r={result} jobId={jobId!} />}
    </div>
  );
}

/* ------------------------------------------------------------------ upload slot */
function DropSlot({ kind, slot, onFile, onClear }: { kind: Kind; slot: Slot; onFile: (f: File) => void; onClear: () => void }) {
  const c = SLOT_COPY[kind];
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const pick = useCallback((files: FileList | null) => { if (files?.[0]) onFile(files[0]); }, [onFile]);
  const info = slot.status === "ready" ? slot.info : null;
  const mismatch = info && info.detected_kind !== kind;

  return (
    <div className={`upl-slot ${over ? "upl-slot--over" : ""} ${info ? (info.ok ? "upl-slot--ok" : "upl-slot--bad") : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}>
      <div className="upl-slot__head">
        <div>
          <p className="upl-slot__title">{c.title} <span className="muted">· {c.format}</span></p>
          <p className="upl-slot__hint">{c.hint}</p>
        </div>
        <a className="btn btn--ghost btn--sm" href={api.scoreTemplateUrl(c.template)} download>
          <Icon name="download" size={13} /> Sample
        </a>
      </div>
      <input ref={input} type="file" accept=".csv,text/csv" hidden onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />

      {slot.status === "empty" && (
        <button type="button" className="upl-drop" onClick={() => input.current?.click()}>
          <Icon name="upload" size={20} />
          <span><strong>Drop a CSV here</strong> or click to choose</span>
          <span className="muted">{c.empty}</span>
        </button>
      )}
      {slot.status === "uploading" && <div className="upl-drop"><span className="spinner" aria-hidden /> Reading {slot.name}…</div>}
      {slot.status === "error" && (
        <div className="upl-file">
          <Badge tone="critical">{slot.name}</Badge>
          <p className="upl-file__problem">{slot.message}</p>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClear}>Choose another file</button>
        </div>
      )}
      {info && (
        <div className="upl-file">
          <div className="upl-file__row">
            <span className="mono">{info.filename}</span>
            <Badge tone={info.ok ? "good" : "critical"}>{info.ok ? "Ready" : "Cannot use"}</Badge>
            <button type="button" className="btn btn--ghost btn--sm" onClick={onClear} aria-label={`Remove ${info.filename}`}>
              <Icon name="close" size={13} /> Remove
            </button>
          </div>
          <dl className="upl-facts">
            <div><dt>Rows</dt><dd>{fmtInt(info.rows)}</dd></div>
            <div><dt>Months</dt><dd>{info.date_from ?? "—"} → {info.date_to ?? "—"}</dd></div>
            <div><dt>Series</dt><dd>{fmtInt(info.series)}</dd></div>
            {kind === "request" && <div><dt>Actuals</dt><dd>{info.has_actuals ? `${fmtInt(info.actual_rows)} rows` : "none"}</dd></div>}
          </dl>
          {info.problem && <p className="upl-file__problem">{info.problem}</p>}
          {mismatch && <p className="upl-file__note">This looks like a {info.detected_kind === "history" ? "sales history (train.csv)" : "rows-to-forecast (test.csv)"} file.</p>}
          {info.ok && info.optional_columns_missing.length > 0 && (
            <p className="upl-file__note">Not in the file (filled by the pipeline): {info.optional_columns_missing.join(", ")}</p>
          )}
          {!!info.unparseable_dates && <p className="upl-file__note">{fmtInt(info.unparseable_dates)} dates are not standard; the cleaning rules repair what they can.</p>}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ results */
function Results({ r, jobId }: { r: ScoreResult; jobId: string }) {
  const [metric, setMetric] = useState<Metric>("units");
  const [pdfState, setPdfState] = useState<"idle" | "building" | "error">("idle");
  const downloadPdf = async () => {
    setPdfState("building");
    try {
      const { buildScoreReport } = await import("./uploadReport");
      const blob = await buildScoreReport(r, jobId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `celeris_forecast_report_${r.inputs.cutoff}_${jobId.slice(0, 8)}.pdf`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
      setPdfState("idle");
    } catch {
      setPdfState("error");
    }
  };
  const pdfButton = (
    <button type="button" className="btn btn--accent btn--sm" onClick={downloadPdf} disabled={pdfState === "building"}>
      <Icon name="download" size={13} /> {pdfState === "building" ? "Building PDF…" : pdfState === "error" ? "PDF failed — retry" : "Download PDF report"}
    </button>
  );
  const acc = r.accuracy;
  const fc = r.frozen_comparison;
  const k = r.kpis;

  const tlOption = useMemo(() => timelineOption(r.timeline, metric, { showShipped: true }), [r, metric]);
  const famOption = useMemo(() => verticalBarsOption(r.by_family.map((x) => x.Member),
    [{ name: "Forecast units", data: r.by_family.map((x) => x.Units) }],
    { valueFormatter: (v) => fmtUnits(v, 1), showLabels: true, rotateLabels: true }), [r]);
  const regOption = useMemo(() => verticalBarsOption(r.by_region.map((x) => x.Member),
    [{ name: "Forecast units", data: r.by_region.map((x) => x.Units), color: SERIES[1] }],
    { valueFormatter: (v) => fmtUnits(v, 1), showLabels: true, rotateLabels: true }), [r]);
  const accOption = useMemo(() => acc && accuracyOption(acc.monthly), [acc]);

  const metricCols = useMemo<Column<ScoreMetrics>[]>(() => [
    { key: "m", label: "Segment", value: (x) => x.Member ?? "" },
    { key: "a", label: "Actual", value: (x) => x.actual, render: (x) => fmtInt(x.actual), align: "right" },
    { key: "f", label: "Forecast", value: (x) => x.forecast, render: (x) => fmtInt(x.forecast), align: "right" },
    { key: "w", label: "WAPE", value: (x) => x.WAPE, render: (x) => fmtPct(x.WAPE), align: "right" },
    { key: "n", label: "Seasonal naive WAPE", value: (x) => x.Naive_WAPE, render: (x) => fmtPct(x.Naive_WAPE), align: "right" },
    { key: "b", label: "Bias", value: (x) => x.Bias, render: (x) => fmtPctChange(x.Bias), align: "right" },
    { key: "c", label: "P10–P90 coverage", value: (x) => x.Coverage_P10_P90, render: (x) => fmtPct(x.Coverage_P10_P90, 0), align: "right" },
  ], []);

  const seriesCols = useMemo<Column<ScoreSeriesRow>[]>(() => {
    const cols: Column<ScoreSeriesRow>[] = [
      { key: "sku", label: "SKU", value: (x) => x.SKU_ID, render: (x) => <span className="mono">{x.SKU_ID}</span> },
      { key: "reg", label: "Region", value: (x) => x.Region },
      { key: "fam", label: "Family", value: (x) => x.Product_Family },
      { key: "u", label: "Forecast", value: (x) => x.Units, render: (x) => fmtInt(x.Units), align: "right" },
      { key: "band", label: "P10 – P90", value: (x) => x.P90 - x.P10, render: (x) => `${fmtInt(x.P10)} – ${fmtInt(x.P90)}`, align: "right" },
      { key: "l12", label: "Demand, last 12 m", value: (x) => x.Demand_last12, render: (x) => fmtInt(x.Demand_last12), align: "right" },
      { key: "rev", label: "Revenue", value: (x) => x.Revenue, render: (x) => fmtUsd(x.Revenue, 1), align: "right" },
    ];
    if (acc) {
      cols.push({ key: "act", label: "Actual", value: (x) => x.Actual ?? null, render: (x) => fmtInt(x.Actual), align: "right" });
      cols.push({ key: "wape", label: "WAPE", value: (x) => x.WAPE ?? null, render: (x) => fmtPct(x.WAPE), align: "right" });
    }
    cols.push({ key: "meth", label: "Method", value: (x) => x.Method, render: (x) => <span style={{ fontSize: 12 }}>{x.Method}</span> });
    return cols;
  }, [acc]);

  const ch = r.checks;
  const better = acc?.overall.WAPE != null && acc.overall.Naive_WAPE ? 1 - acc.overall.WAPE / acc.overall.Naive_WAPE : null;

  return (
    <>
      <div className="upl-summary">
        <span className="eyebrow">3 · Results</span>
        <span className="muted">
          {r.inputs.history === "uploaded" ? "Your history" : "Official history"} to {r.inputs.cutoff} ·{" "}
          {r.inputs.rows_to_forecast === "uploaded" ? "your rows" : r.inputs.rows_to_forecast} ·
          {" "}{r.inputs.horizon[0]} → {r.inputs.horizon[1]} · model {r.model.name.replace(/_/g, " ")} · {r.seconds}s
        </span>
        <span className="upl-summary__pdf">{pdfButton}</span>
      </div>

      {r.warnings.map((w) => (
        <div key={w} className="upl-banner upl-banner--warn"><Icon name="alert" size={16} /> <span>{w}</span></div>
      ))}
      {fc && (
        <div className={`upl-banner ${fc.identical ? "upl-banner--ok" : "upl-banner--info"}`}>
          <Icon name={fc.identical ? "check" : "info"} size={16} />
          <span>{fc.identical
            ? <>Identical to the frozen submission on all {fmtInt(fc.rows)} overlapping rows (largest difference {fc.max_abs_diff.toExponential(1)} units) — the pipeline is reproducible.</>
            : <>On the {fmtInt(fc.rows)} rows that are also in the frozen forecast, your data moves the total by <strong>{fmtPctChange(fc.change_pct)}</strong> ({fmtInt(fc.total_frozen)} → {fmtInt(fc.total)} units).</>}
          </span>
        </div>
      )}

      <section className="kpi-row" aria-label="Scoring summary">
        <KpiTile label="Rows forecast" value={fmtInt(k.rows)} sub={`${fmtInt(k.series)} SKU × region series · ${r.inputs.horizon_months} months`}
          footnote={k.zero_by_lifecycle ? `${fmtInt(k.zero_by_lifecycle)} rows set to 0 by the lifecycle rule` : "Lifecycle, launch and shutdown rules applied"} />
        <KpiTile label="Forecast demand" emphasis="accent" value={fmtUnits(k.units, 2)} unit="units"
          sub={`P10–P90 ${fmtUnits(k.units_p10, 2)} – ${fmtUnits(k.units_p90, 2)}`} footnote={k.band_method} />
        <KpiTile label="Forecast revenue" value={fmtUsd(k.revenue, 2)} sub="At the list prices of each forecast year"
          footnote="Price book from the history + announced rises" />
        {acc ? (
          <KpiTile label="Accuracy (WAPE)" emphasis={acc.in_sample ? undefined : "accent"} value={fmtPct(acc.overall.WAPE)}
            sub={better !== null ? `${fmtPct(better, 0)} lower error than seasonal naive (${fmtPct(acc.overall.Naive_WAPE)})` : undefined}
            footnote={`${fmtInt(acc.overall.rows)} rows with actuals · ${acc.in_sample ? "in-sample" : "out-of-sample"}`} />
        ) : (
          <KpiTile label={ch.cleaning ? "Data fixed" : "History checks"} value={fmtInt(ch.cleaning?.issues ?? ch.anomalies.flagged)}
            sub={ch.cleaning ? `${fmtInt(ch.cleaning.rows_in)} → ${fmtInt(ch.cleaning.rows_clean)} rows after cleaning` : `${fmtInt(ch.anomalies.flagged)} months flagged in the official history`}
            footnote={ch.cleaning ? "Every fix is in the issue log download" : "Add actual Units_Sold to see accuracy"} />
        )}
      </section>

      <Card title="Forecast" subtitle={`History to ${r.inputs.cutoff} and the forecast with its P10–P90 band · ${r.timeline.band_method}`}
        actions={<Segmented label="Metric" value={metric} onChange={setMetric}
          options={[{ value: "units", label: "Units" }, { value: "revenue", label: "Revenue" }]} />}>
        <div style={{ padding: "8px 20px 20px" }}><EChart height={340} label="History and forecast" option={tlOption} /></div>
      </Card>

      {acc && (
        <Card title="Forecast vs actual"
          subtitle={`${fmtInt(acc.overall.rows)} rows with actuals (${acc.source}) · SKU-month WAPE ${fmtPct(acc.overall.WAPE)} · family-month ${fmtPct(acc.family_month_WAPE)} · total-month ${fmtPct(acc.total_month_WAPE)} · bias ${fmtPctChange(acc.overall.Bias)} · P10–P90 coverage ${fmtPct(acc.overall.Coverage_P10_P90, 0)}`}>
          <div style={{ padding: "8px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
            {accOption && <EChart height={300} label="Forecast vs actual by month" option={accOption} />}
            <DataTable columns={metricCols} rows={[...acc.by_horizon.map((x) => ({ ...x, Member: `Horizon ${x.Member}` })),
              ...acc.by_family, ...acc.by_region]} caption="Accuracy by horizon, family and region" maxHeight={360}
              exportable exportFilename="accuracy_by_segment" />
          </div>
        </Card>
      )}

      <div className="grid grid--2">
        <Card title="By product family" subtitle="Forecast units over the horizon">
          <div style={{ padding: "12px 20px 20px" }}><EChart height={260} label="Forecast by family" option={famOption} /></div>
        </Card>
        <Card title="By region" subtitle="Forecast units over the horizon">
          <div style={{ padding: "12px 20px 20px" }}><EChart height={260} label="Forecast by region" option={regOption} /></div>
        </Card>
      </div>

      <Card title="What the pipeline did to your data" subtitle="Cleaning, demand recovery and row checks — the same rules as the official run">
        <div className="upl-checks">
          <div>
            <p className="upl-checks__h">Cleaning</p>
            {ch.cleaning ? (
              <>
                <p>{fmtInt(ch.cleaning.rows_in)} rows in → {fmtInt(ch.cleaning.rows_clean)} clean rows · {fmtInt(ch.cleaning.issues)} fixes logged
                  {ch.cleaning.null_cells_before != null && ` · empty cells ${fmtInt(ch.cleaning.null_cells_before)} → ${fmtInt(ch.cleaning.null_cells_after)}`}</p>
                <ul className="upl-list">
                  {ch.cleaning.by_type.slice(0, 8).map((t) => (
                    <li key={t.issue_type + t.action}><span>{t.issue_type.replace(/_/g, " ")}</span><span className="muted">{t.action}</span><strong className="num">{fmtInt(t.rows)}</strong></li>
                  ))}
                </ul>
              </>
            ) : <p className="muted">No history uploaded — the official cleaned history was used.</p>}
          </div>
          <div>
            <p className="upl-checks__h">Demand recovery</p>
            <p>{fmtInt(ch.anomalies.flagged)} months flagged in the history</p>
            <ul className="upl-list">
              {Object.entries(ch.anomalies.by_category).map(([c, n]) => (
                <li key={c}><span>{c.replace(/_/g, " ")}</span><span /><strong className="num">{fmtInt(n)}</strong></li>
              ))}
            </ul>
          </div>
          <div>
            <p className="upl-checks__h">Rows to forecast</p>
            <p>{fmtInt(ch.request.accepted)} accepted · {fmtInt(ch.request.rejected)} rejected</p>
            <ul className="upl-list">
              {Object.entries(ch.request.rejected_by_reason).map(([c, n]) => (
                <li key={c}><span>{c}</span><span /><strong className="num">{fmtInt(n)}</strong></li>
              ))}
              {!ch.request.rejected && <li><span>Every row passed the checks</span><span /><Icon name="check" size={13} style={{ color: STATUS.good }} /></li>}
            </ul>
            <p className="muted" style={{ fontSize: 12 }}>Methods: {Object.entries(k.methods).map(([m, n]) => `${m} ${fmtInt(n)}`).join(" · ")}</p>
          </div>
        </div>
      </Card>

      <Card title="Series" subtitle={`Top ${fmtInt(r.series.length)} of ${fmtInt(r.series_total)} series by forecast units — every row is in the downloads`}>
        <div style={{ padding: "8px 20px 20px" }}>
          {r.series.length ? <DataTable columns={seriesCols} rows={r.series} caption="Series forecast" maxHeight={420}
            initialSort={{ key: "u", dir: "desc" }} exportable exportFilename="series_forecast" />
            : <EmptyState title="No series" />}
        </div>
      </Card>

      <Card title="Downloads" subtitle="Full outputs of this run — and the whole page as a PDF report in the same design">
        <div className="upl-downloads">
          {pdfButton}
          {r.files.map((f) => (
            <a key={f} className={`btn btn--sm ${f === "submission.csv" ? "btn--accent" : "btn--ghost"}`} href={api.scoreFileUrl(jobId, f)} download>
              <Icon name="download" size={13} /> {FILE_LABEL[f] ?? f}
            </a>
          ))}
        </div>
      </Card>
    </>
  );
}

const FILE_LABEL: Record<string, string> = {
  "submission.csv": "Submission (Date, SKU_ID, Region, Units_Sold_Forecast)",
  "forecast_detail.csv": "Forecast detail with P10/P50/P90 and revenue",
  "series_summary.csv": "Series summary",
  "dq_issue_log.csv": "Data-quality issue log",
  "anomaly_register.csv": "Anomaly register",
  "rejected_rows.csv": "Rejected rows with reasons",
};

export function accuracyOption(rows: NonNullable<ScoreResult["accuracy"]>["monthly"]) {
  const dates = rows.map((x) => x.Date);
  return {
    animationDuration: 400,
    grid: { left: 12, right: 16, top: 40, bottom: 8, containLabel: true },
    legend: { top: 0, textStyle: { color: CHART.text }, data: ["Actual", "Forecast", "Seasonal naive"] },
    tooltip: { trigger: "axis", valueFormatter: (v: number) => fmtInt(v) },
    xAxis: { type: "category", data: dates, axisLabel: { color: CHART.text } },
    yAxis: { type: "value", axisLabel: { color: CHART.text, formatter: (v: number) => fmtUnits(v, 0) },
      splitLine: { lineStyle: { color: CHART.grid } } },
    series: [
      { name: "P10", type: "line", data: rows.map((x) => x.P10), stack: "band", lineStyle: { opacity: 0 }, symbol: "none",
        itemStyle: { color: SERIES[0] }, tooltip: { show: false } },
      { name: "P10–P90", type: "line", data: rows.map((x) => (x.P10 != null && x.P90 != null ? x.P90 - x.P10 : null)), stack: "band",
        lineStyle: { opacity: 0 }, symbol: "none", itemStyle: { color: SERIES[0] }, areaStyle: { color: SERIES[0], opacity: 0.12 }, tooltip: { show: false } },
      { name: "Actual", type: "line", data: rows.map((x) => x.Actual), symbolSize: 5, lineStyle: { width: 2, color: SERIES[4] },
        itemStyle: { color: SERIES[4] } },
      { name: "Forecast", type: "line", data: rows.map((x) => x.Forecast), symbolSize: 5, lineStyle: { width: 2, color: SERIES[0] },
        itemStyle: { color: SERIES[0] } },
      { name: "Seasonal naive", type: "line", data: rows.map((x) => x.Naive), symbol: "none",
        lineStyle: { width: 1.5, type: "dashed", color: SERIES[2] }, itemStyle: { color: SERIES[2] } },
    ],
  };
}
