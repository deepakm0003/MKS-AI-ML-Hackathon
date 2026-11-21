import { useSeasonality, useLifecycle } from "../api/views";
import { Badge, Card, ErrorState, Skeleton } from "../components/ui";
import { useFilters } from "../filters/FilterContext";
import { fmtUnits } from "../lib/format";

const CLASS_HELP: Record<string, string> = {
  smooth: "regular orders, stable size",
  intermittent: "frequent zero months, stable size",
  erratic: "regular orders, volatile size",
  lumpy: "zero months and volatile size",
};

function Bar({ parts }: { parts: { label: string; value: number; tone: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <div className="stackbar" role="img" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(", ")}>
      {parts.filter((p) => p.value > 0).map((p) => (
        <span key={p.label} className="stackbar__seg" style={{ width: `${(100 * p.value) / total}%`, background: p.tone }} />
      ))}
    </div>
  );
}

/** Zero-order months and demand classes - how forecastable the selection is. */
export function DemandProfileCard() {
  const st = useSeasonality();
  return (
    <Card title="Order pattern" subtitle="Zero months and demand class (Syntetos–Boylan, last 24 months)">
      {st.status === "loading" && <Skeleton lines={6} />}
      {st.status === "error" && <ErrorState error={st.error} onRetry={st.retry} />}
      {st.status === "success" && (() => {
        const s = st.data.stats;
        const cls = ["smooth", "intermittent", "erratic", "lumpy"];
        const tones = ["var(--series-1)", "var(--series-3)", "var(--series-4)", "var(--series-2)"];
        const total = cls.reduce((n, c) => n + (s.demand_classes[c] ?? 0), 0);
        return (
          <div className="profile">
            <div className="profile__stats">
              <div><p className="profile__v num">{s.zero_month_share_24m === null ? "—" : `${Math.round(100 * s.zero_month_share_24m)}%`}</p>
                <p className="profile__k">of observed months had no order</p></div>
              <div><p className="profile__v num">{s.series_with_30pct_zero_months.toLocaleString()}</p>
                <p className="profile__k">of {s.series_observed_24m.toLocaleString()} series order in ≤ 70% of months</p></div>
              <div><p className="profile__v num">{s.median_order_cycle_months ?? "—"} m</p>
                <p className="profile__k">median ordering cycle</p></div>
            </div>
            <Bar parts={cls.map((c, i) => ({ label: c, value: s.demand_classes[c] ?? 0, tone: tones[i] }))} />
            <ul className="legend-list">
              {cls.map((c, i) => (
                <li key={c}>
                  <span className="legend-dot" style={{ background: tones[i] }} />
                  <span className="legend-name">{c}</span>
                  <span className="num">{(s.demand_classes[c] ?? 0).toLocaleString()}</span>
                  <span className="muted">{total ? `${Math.round((100 * (s.demand_classes[c] ?? 0)) / total)}%` : ""}</span>
                  <span className="legend-help">{CLASS_HELP[c]}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })()}
    </Card>
  );
}

const STATUS_TONE: Record<string, "neutral" | "warning" | "serious" | "accent"> = {
  Active: "neutral", "EOL Announced": "warning", Discontinued: "serious", "Planned Launch": "accent",
};

/** Lifecycle intelligence: status mix, series age and the launch / EOL handovers in the forecast window. */
export function LifecycleCard() {
  const st = useLifecycle();
  const { dispatch } = useFilters();
  return (
    <Card title="Lifecycle" subtitle="Status of the SKUs in view, series age and handovers in the forecast window">
      {st.status === "loading" && <Skeleton lines={6} />}
      {st.status === "error" && <ErrorState error={st.error} onRetry={st.retry} />}
      {st.status === "success" && (() => {
        const d = st.data;
        const age = Object.entries(d.series_age);
        return (
          <div className="lifecycle">
            <div className="badge-row">
              {Object.entries(d.status_counts).map(([k, v]) => (
                <Badge key={k} tone={STATUS_TONE[k] ?? "neutral"} icon={null}>{k} · {v}</Badge>
              ))}
            </div>
            <Bar parts={age.map(([k, v], i) => ({ label: k, value: v, tone: ["var(--series-5)", "var(--series-7)", "var(--chart-history)"][i] }))} />
            <ul className="legend-list legend-list--inline">
              {age.map(([k, v], i) => (
                <li key={k}><span className="legend-dot" style={{ background: ["var(--series-5)", "var(--series-7)", "var(--chart-history)"][i] }} />
                  <span className="legend-name">{k}</span><span className="num">{v.toLocaleString()}</span></li>
              ))}
            </ul>
            {d.events.length === 0 ? <p className="muted">No launches or end-of-life dates inside the forecast window for this selection.</p> : (
              <ol className="events">
                {d.events.map((e) => (
                  <li key={`${e.type}-${e.sku}`} className={`event event--${e.type.toLowerCase()}`}>
                    <span className="event__date mono">{e.date}</span>
                    <span className="event__main">
                      <button type="button" className="linkish" onClick={() => dispatch({ type: "set", dim: "sku", values: [e.sku] })}>
                        {e.type === "LAUNCH" ? "Launch" : "End of life"} · {e.sku}
                      </button>
                      <span className="event__sub">
                        {e.type === "LAUNCH" ? `replaces ${e.related_sku ?? "—"}` : `successor ${e.related_sku ?? "none"}`}
                        {e.powertrain ? ` · ${e.powertrain}` : ""} · {e.regions} regions · {fmtUnits(e.forecast_units, 1)} units
                        {e.type === "LAUNCH" ? " forecast" : " until EOL"}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        );
      })()}
    </Card>
  );
}
