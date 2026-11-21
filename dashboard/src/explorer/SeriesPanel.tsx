import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge, Card, ErrorState, Skeleton } from "../components/ui";
import { fmtUsd } from "../lib/format";

// the explainable risk score: weights from celeris.intel.forecast_risk / intelligence.classify
const RISK_PARTS: { key: string; label: string; weight: number }[] = [
  { key: "risk_backtest_error", label: "Backtest error", weight: 0.35 },
  { key: "risk_band_width", label: "Band width", weight: 0.2 },
  { key: "risk_volatility", label: "Volatility", weight: 0.15 },
  { key: "risk_short_history", label: "Short history", weight: 0.1 },
  { key: "risk_data_issues", label: "Data issues", weight: 0.1 },
  { key: "risk_macro_sensitivity", label: "Macro sensitivity", weight: 0.1 },
];

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** One SKU x region: profile, lifecycle, explainable risk, reason codes and the recommendation. */
export function SeriesPanel({ sku, region }: { sku: string; region: string }) {
  const st = useApi((s) => api.series(sku, region, s), [sku, region]);
  return (
    <Card title={`${sku} · ${region}`} subtitle="Series profile, lifecycle and explainable forecast risk">
      {st.status === "loading" && <Skeleton lines={8} />}
      {st.status === "error" && <ErrorState error={st.error} onRetry={st.retry} />}
      {st.status === "success" && (() => {
        const { profile: p, lifecycle: l, risk: r, anomalies } = st.data;
        const score = num(r?.risk_score);
        const codes = typeof r?.reason_codes === "string" ? r.reason_codes.split("|").filter(Boolean) : [];
        return (
          <div className="series">
            <dl className="kv series__kv">
              {l && <div className="kv__row"><dt>Product</dt><dd>{l.SKU_Description}</dd></div>}
              {l && <div className="kv__row"><dt>Lifecycle</dt><dd>{l.Lifecycle_Status} · launched {l.Launch_Date}{l.EOL_Date ? ` · EOL ${l.EOL_Date}` : ""}
                {l.Replaces_SKU ? ` · replaces ${l.Replaces_SKU}` : ""}{l.Successor_SKU ? ` · successor ${l.Successor_SKU}` : ""}</dd></div>}
              {l && <div className="kv__row"><dt>Application</dt><dd>{l.Powertrain_Application} · {l.Size_Class}</dd></div>}
              {p && <div className="kv__row"><dt>Order pattern</dt><dd>{p.Demand_Class} · orders every {p.Cycle_Last12 ?? "—"} month(s) ·
                {p.Nonzero_Share_24 !== null ? ` ${Math.round(100 * (1 - p.Nonzero_Share_24))}% zero months` : ""} · history since {p.First_Month}</dd></div>}
              {r && <div className="kv__row"><dt>Planning segment</dt><dd>{String(r.Segment ?? "—")} · service level {num(r.Service_level) !== null ? `${Math.round(100 * (num(r.Service_level) as number))}%` : "—"}</dd></div>}
              <div className="kv__row"><dt>Anomalies flagged</dt><dd>{anomalies.length} months (see Anomaly Monitor)</dd></div>
            </dl>

            {r && (
              <div className="series__risk">
                <div className="series__riskhead">
                  <p className="kpi__label">Forecast risk</p>
                  <Badge tone={r.risk_level === "HIGH" ? "critical" : r.risk_level === "MEDIUM" ? "warning" : "good"}>
                    {String(r.risk_level)} · {score?.toFixed(0)} / 100
                  </Badge>
                  <Badge tone="neutral" icon={null}>Confidence {String(r.confidence ?? "—").toLowerCase()}</Badge>
                </div>
                <ul className="riskparts">
                  {RISK_PARTS.map((part) => {
                    const pct = num(r[part.key]) ?? 0;
                    return (
                      <li key={part.key}>
                        <span className="riskparts__name">{part.label}<span className="muted"> · weight {Math.round(part.weight * 100)}%</span></span>
                        <span className="riskparts__bar"><span style={{ width: `${pct * 100}%` }} /></span>
                        <span className="riskparts__pts num">{(100 * part.weight * pct).toFixed(1)}</span>
                      </li>
                    );
                  })}
                </ul>
                <p className="panel-foot">Points = weight × percentile among all 3,068 series; backtest WAPE {num(r.backtest_wape) !== null ? `${(100 * (num(r.backtest_wape) as number)).toFixed(0)}%` : "—"}.
                  Value at risk next 12 m: −{fmtUsd(num(r.revenue_downside_next12))} / +{fmtUsd(num(r.revenue_upside_next12))}.</p>
              </div>
            )}

            {codes.length > 0 && (
              <div className="badge-row">{codes.map((c) => <Badge key={c} tone="neutral" icon={null}>{c.replace(/_/g, " ").toLowerCase()}</Badge>)}</div>
            )}
            {r?.recommendation && <p className="series__rec"><span className="action__k">Recommendation</span>{String(r.recommendation)}</p>}
          </div>
        );
      })()}
    </Card>
  );
}
