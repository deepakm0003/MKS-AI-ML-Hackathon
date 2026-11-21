import { useTimeline } from "../api/views";
import { BreakdownCard } from "../charts/BreakdownCard";
import { TimelineCard } from "../charts/TimelineCard";
import { KpiTile, type Trend } from "../components/KpiTile";
import { Badge, Card, ErrorState } from "../components/ui";
import { fmtPctChange, fmtUnits, fmtUsd } from "../lib/format";
import { SERIES, STATUS } from "../theme/chart";

const trend = (v: number | null | undefined): Trend => (v === null || v === undefined || Math.abs(v) < 0.0005 ? "flat" : v > 0 ? "up" : "down");

/** Phase-2 review page: every shared component on live, filter-aware data (route /system, not in the nav). */
export function SystemPage() {
  const tl = useTimeline();
  const s = tl.status === "success" ? tl.data.summary : undefined;
  const loading = tl.status === "loading";

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Phase 2 · component foundation</p>
          <h2 className="page__title">Design system and chart components</h2>
          <p className="page__lead">
            Shared building blocks for every view, rendered on the real API with the global filters applied.
          </p>
        </div>
        <Badge tone="accent" icon="palette">Review page</Badge>
      </div>

      {tl.status === "error" ? <Card><ErrorState error={tl.error} onRetry={tl.retry} /></Card> : (
        <div className="kpi-row">
          <KpiTile label="19-month forecast" loading={loading} value={fmtUnits(s?.units_19m)} unit="units"
            sub={s && <>Range {fmtUnits(s.units_19m_p10)} – {fmtUnits(s.units_19m_p90)} (P10–P90)</>} />
          <KpiTile label="Revenue, next 12 months" loading={loading} value={fmtUsd(s?.revenue_next12)} emphasis="accent"
            delta={s ? { text: `${fmtPctChange(s.revenue_next12_vs_last12)} vs last 12 m`, trend: trend(s.revenue_next12_vs_last12), goodWhen: "up" } : undefined} />
          <KpiTile label="Demand, next 12 months" loading={loading} value={fmtUnits(s?.units_next12)} unit="units"
            delta={s ? { text: `${fmtPctChange(s.units_next12_vs_last12)} vs last 12 m`, trend: trend(s.units_next12_vs_last12), goodWhen: "up" } : undefined} />
          <KpiTile label="Series in view" loading={loading} value={s ? s.forecast_series.toLocaleString() : undefined}
            sub={s ? `of ${s.series.toLocaleString()} with history or forecast` : undefined} />
        </div>
      )}

      <TimelineCard />

      <div className="grid grid--2">
        <BreakdownCard dim="region" top={6} />
        <BreakdownCard dim="family" top={7} />
      </div>

      <Card title="Colour tokens" subtitle="Categorical slots (fixed order, validated for colour-vision deficiency on the dark surface) and reserved status colours">
        <div className="swatches">
          {SERIES.map((c, i) => (
            <div key={c} className="swatch"><span className="swatch__chip" style={{ background: c }} /><span className="mono">{i + 1} · {c}</span></div>
          ))}
        </div>
        <div className="badge-row" style={{ marginTop: 16 }}>
          {Object.entries(STATUS).map(([k, c]) => (
            <Badge key={k} tone={k === "good" ? "good" : k === "warning" ? "warning" : k === "serious" ? "serious" : "critical"}>
              {k} <span className="mono">{c}</span>
            </Badge>
          ))}
        </div>
      </Card>
    </div>
  );
}
