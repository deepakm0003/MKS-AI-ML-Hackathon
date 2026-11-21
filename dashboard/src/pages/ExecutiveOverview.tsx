import { useRecommendations, useTimeline } from "../api/views";
import { BreakdownCard } from "../charts/BreakdownCard";
import { TimelineCard } from "../charts/TimelineCard";
import { KpiTile, type Trend } from "../components/KpiTile";
import { Card, ErrorState } from "../components/ui";
import { useFilters } from "../filters/FilterContext";
import { DIMS } from "../filters/model";
import { fmtPctChange, fmtUnits, fmtUsd } from "../lib/format";
import { ActNowPanel } from "../overview/ActNowPanel";
import { BriefingPanel } from "../overview/BriefingPanel";
import { ScenarioImpactPanel } from "../overview/ScenarioImpactPanel";

const trend = (v: number | null | undefined): Trend =>
  v === null || v === undefined || Math.abs(v) < 0.0005 ? "flat" : v > 0 ? "up" : "down";

/**
 * 01 Executive Overview - answers in five seconds: how much demand, how much revenue, which
 * direction, what could go wrong, what to do now. Everything follows the global filters except the
 * company-wide scenario and briefing panels, which say so.
 */
export function ExecutiveOverview() {
  const { filters, active } = useFilters();
  const tl = useTimeline();
  const crit = useRecommendations({ priority: "CRITICAL", limit: 8 });
  const s = tl.status === "success" ? tl.data.summary : undefined;
  const scopeText = active === 0 ? "All products, regions and customers"
    : DIMS.filter((d) => filters[d].length).map((d) => filters[d].length === 1 ? filters[d][0] : `${filters[d].length} ${d}s`).join(" · ");

  return (
    <div className="page overview">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Executive overview · 19-month planning horizon</p>
          <h2 className="page__title">Demand, revenue and the decisions that matter</h2>
          <p className="page__lead">{scopeText}</p>
        </div>
      </div>

      {tl.status === "error" ? <Card><ErrorState error={tl.error} onRetry={tl.retry} /></Card> : (
        <section className="kpi-row" aria-label="Headline figures">
          <KpiTile
            label="19-month forecast" loading={!s} value={fmtUnits(s?.units_19m)} unit="units"
            delta={s ? { text: `${fmtPctChange(s.units_next12_vs_last12)} next 12 m vs last 12 m`, trend: trend(s.units_next12_vs_last12), goodWhen: "up" } : undefined}
            footnote="Nov 2026 – May 2028 · unconstrained demand"
          />
          <KpiTile
            label="Revenue · next 12 months" loading={!s} value={fmtUsd(s?.revenue_next12)} emphasis="accent"
            delta={s ? { text: `${fmtPctChange(s.revenue_next12_vs_last12)} vs last 12 m`, trend: trend(s.revenue_next12_vs_last12), goodWhen: "up" } : undefined}
            footnote="At the announced 2027 list prices"
          />
          <KpiTile
            label="Forecast confidence range" loading={!s}
            value={s ? `${fmtUnits(s.units_19m_p10)} – ${fmtUnits(s.units_19m_p90)}` : undefined}
            sub={s ? `P10–P90 of the 19-month total · ${fmtUsd(s.revenue_19m)} revenue at P50` : undefined}
            footnote={tl.status === "success" ? tl.data.band_method : undefined}
          />
          <KpiTile
            label="Critical actions" loading={crit.status === "loading"} emphasis="critical"
            value={crit.status === "success" ? String(crit.data.direct) : crit.status === "error" ? undefined : undefined}
            sub={crit.status === "success" ? (crit.data.total > crit.data.direct
              ? `in this selection · ${crit.data.total - crit.data.direct} broader context items` : "open, ranked by value at stake") : crit.status === "error" ? "Recommendations unavailable" : undefined}
            footnote="Rule-based, evidence on every card"
          />
        </section>
      )}

      <div className="ov-grid">
        <div className="ov-grid__main"><TimelineCard title="Demand: history and forecast" height={330} /></div>
        <div className="ov-grid__side"><ActNowPanel state={crit} max={5} /></div>
      </div>

      <div className="ov-grid">
        <div className="ov-grid__main"><TimelineCard title="Revenue: history and forecast" height={300} defaultMetric="revenue" /></div>
        <div className="ov-grid__side"><ScenarioImpactPanel /></div>
      </div>

      <div className="grid grid--3">
        <BreakdownCard dim="region" top={6} title="Demand by region" />
        <BreakdownCard dim="family" top={7} title="Demand by product family" />
        <BreakdownCard dim="channel" top={4} title="Demand by channel" />
      </div>

      <BriefingPanel filtered={active > 0} />
    </div>
  );
}
