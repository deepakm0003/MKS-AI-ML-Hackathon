import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { RecommendationCard } from "../api/types";
import { useApi } from "../api/useApi";
import { useRecommendations } from "../api/views";
import { useFilters } from "../filters/FilterContext";
import { EChart } from "../charts/EChart";
import { verticalBarsOption } from "../charts/options";
import { WorldMap, type RegionData } from "../charts/WorldMap";
import { DataTable, type Column } from "../components/DataTable";
import { Icon } from "../components/Icon";
import { KpiTile } from "../components/KpiTile";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt, fmtUsd } from "../lib/format";
import { CHART, SERIES, STATUS } from "../theme/chart";

interface CapacityRow {
  Product_Family: string;
  Region: string;
  Demonstrated_3m_throughput: number;
  Peak_3m_load_P50: number;
  Peak_3m_load_P90: number;
  Utilisation_P50: number;   // decimal e.g. 0.978
  Utilisation_P90: number;   // decimal e.g. 1.134
  Capacity_flag: string;
}

interface SupplyRiskRow {
  Product_Family: string;
  Region: string;
  Shortage_months_36m: number;
  Lost_units_36m: number;
  Supply_risk_score: number;
  Supply_risk_level: string;
}

type PriorityFilter = "all" | "CRITICAL" | "HIGH" | "MEDIUM";

const CONF_TONE: Record<string, "good" | "warning" | "serious"> = { HIGH: "good", MEDIUM: "warning", LOW: "serious" };
const PRIO_TONE: Record<string, "critical" | "serious" | "warning"> = { CRITICAL: "critical", HIGH: "serious", MEDIUM: "warning" };
const PRIO_COLOR: Record<string, string> = { CRITICAL: STATUS.serious, HIGH: STATUS.warning, MEDIUM: SERIES[2] };

// Capacity utilisation is stored as a decimal (1.13 = 113%) — multiply by 100 to get %
const utilPct = (v: number) => Math.round(v * 100);

/** Mini horizontal stacked bar for breakdowns */
function ImpactBar({ segments }: { segments: { label: string; value: number; color: string }[] }) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  if (!total) return null;
  return (
    <div style={{ display: "flex", height: 6, borderRadius: 4, overflow: "hidden", gap: 1, marginTop: 4 }}>
      {segments.filter((s) => s.value > 0).map((s) => (
        <div key={s.label} title={`${s.label}: ${fmtInt(s.value)}`}
          style={{ flex: s.value / total, background: s.color, minWidth: 3 }} />
      ))}
    </div>
  );
}

/** Inline risk meter 0–100 */
function RiskMeter({ score, level }: { score: number; level: string }) {
  const color = level === "HIGH" ? STATUS.serious : level === "MEDIUM" ? STATUS.warning : STATUS.good;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 110 }}>
      <div style={{ flex: 1, height: 5, borderRadius: 3, background: "var(--surface-3)" }}>
        <div style={{ width: `${Math.min(100, score)}%`, height: "100%", borderRadius: 3, background: color }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, minWidth: 24, textAlign: "right" }}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

/** Capacity heatmap grid — colours derived from utilisation × 100 */
function CapacityHeatmap({ rows }: { rows: CapacityRow[] }) {
  if (!rows.length) return <EmptyState title="No capacity data" icon="database" />;

  const families = [...new Set(rows.map((r) => r.Product_Family))].sort();
  const regions  = [...new Set(rows.map((r) => r.Region))].sort();
  const lookup   = new Map(rows.map((r) => [`${r.Product_Family}|${r.Region}`, r]));

  const cellColor = (pct: number) => {
    if (pct >= 100) return STATUS.serious;
    if (pct >= 85)  return STATUS.warning;
    return STATUS.good;
  };
  const textColor = (pct: number) => (pct >= 85 ? "#fff" : "#fff");

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "separate", borderSpacing: 3, fontSize: 11, width: "100%" }}>
          <thead>
            <tr>
              <th style={{ color: "var(--text-3)", fontWeight: 500, textAlign: "left", padding: "0 4px 8px", whiteSpace: "nowrap" }} />
              {regions.map((r) => (
                <th key={r} style={{ color: "var(--text-3)", fontWeight: 500, textAlign: "center", padding: "0 2px 8px", fontSize: 10 }}>
                  {r.replace("Middle East & Africa", "ME & Africa").replace("Asia Pacific", "Asia Pac.")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {families.map((fam) => (
              <tr key={fam}>
                <td style={{ color: "var(--text-2)", padding: "2px 6px 2px 0", whiteSpace: "nowrap", fontWeight: 500, fontSize: 11 }}>
                  {fam}
                </td>
                {regions.map((reg) => {
                  const row = lookup.get(`${fam}|${reg}`);
                  const pct = row ? utilPct(row.Utilisation_P90) : null;
                  return (
                    <td key={reg}
                      title={row ? `${fam} · ${reg}\nP90 utilisation: ${pct}%\nFlag: ${row.Capacity_flag}` : "No data"}
                      style={{
                        background: pct != null ? cellColor(pct) : "var(--surface-2)",
                        borderRadius: 4,
                        padding: "6px 4px",
                        textAlign: "center",
                        color: pct != null ? textColor(pct) : "var(--text-3)",
                        fontWeight: 700,
                        fontSize: 11,
                        opacity: row ? 1 : 0.3,
                        minWidth: 42,
                      }}>
                      {pct != null ? `${pct}%` : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 10, fontSize: 11, color: "var(--text-3)" }}>
        {[
          { label: "< 85%", color: STATUS.good },
          { label: "85–100%", color: STATUS.warning },
          { label: "≥ 100%", color: STATUS.serious },
        ].map((l) => (
          <span key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: l.color, display: "inline-block" }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Impact-by-owner horizontal bars */
function ownerImpactOption(cards: RecommendationCard[]) {
  const byOwner: Record<string, number> = {};
  for (const c of cards) byOwner[c.owner] = (byOwner[c.owner] ?? 0) + c.impact_usd;
  const sorted = Object.entries(byOwner).sort((a, b) => b[1] - a[1]).slice(0, 8).reverse();
  return {
    animationDuration: 400,
    grid: { left: 10, right: 80, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(22,27,34,0.95)", borderColor: "#30363d", borderWidth: 1,
      textStyle: { color: "#f0f6fc", fontSize: 12 }, padding: [8, 12],
      formatter: (p: { name: string; value: number }) => `${p.name}: <b>${fmtUsd(p.value, 1)}</b>`,
    },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category", data: sorted.map(([k]) => k),
      axisLabel: { color: CHART.text, fontSize: 11, width: 130, overflow: "truncate" },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: sorted.map(([, v]) => ({ value: v, itemStyle: { color: SERIES[0], borderRadius: [0, 4, 4, 0] } })),
      barMaxWidth: 18,
      label: {
        show: true, position: "right", color: CHART.text, fontSize: 11, fontWeight: 500,
        formatter: (p: { value: number }) => fmtUsd(p.value, 1),
      },
    }],
  };
}

/** 03 Risk & Exceptions */
export function RiskExceptions() {
  const [priority, setPriority] = useState<PriorityFilter>("all");
  const [open, setOpen]         = useState<string | null>(null);

  const recs    = useRecommendations(priority === "all" ? {} : { priority });
  // totals and counts must cover EVERY card, not the default first page of 50
  const allRecs = useRecommendations({ limit: 1000 });
  const capAll    = useApi((s) => api.dataset<CapacityRow>("capacity_check", { limit: 1000 }, s), []);
  const supplyAll = useApi((s) => api.dataset<SupplyRiskRow>("supply_risk", { limit: 1000 }, s), []);
  // capacity and supply risk are per family x region: apply those two global filters
  const { filters } = useFilters();
  const keep = <T extends { Product_Family: string; Region: string }>(rows: T[]) => rows.filter((r) =>
    (!filters.family.length || filters.family.includes(r.Product_Family)) &&
    (!filters.region.length || filters.region.includes(r.Region)));
  const cap = capAll.status === "success" ? { ...capAll, data: { ...capAll.data, rows: keep(capAll.data.rows) } } : capAll;
  const supply = supplyAll.status === "success" ? { ...supplyAll, data: { ...supplyAll.data, rows: keep(supplyAll.data.rows) } } : supplyAll;

  const cards    = recs.status    === "success" ? recs.data.cards    : [];
  const allCards = allRecs.status === "success" ? allRecs.data.cards : [];

  const totalImpact   = allCards.reduce((s, c) => s + c.impact_usd, 0);
  const criticalCount = allRecs.status === "success" ? (allRecs.data.by_priority.CRITICAL ?? 0) : 0;
  const highConfCount = allCards.filter((c) => c.confidence === "HIGH").length;

  const impactByPrio = useMemo(() => {
    const t: Record<string, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0 };
    for (const c of allCards) t[c.priority] = (t[c.priority] ?? 0) + c.impact_usd;
    return t;
  }, [allCards]);

  // Build region bubble data from capacity + supply risk
  const regionBubbles = useMemo<RegionData[]>(() => {
    if (cap.status !== "success" && supply.status !== "success") return [];

    // Always include all 6 known regions even with no data
    const REGIONS = ["North America","Latin America","Europe","India","Asia Pacific","Middle East & Africa"];
    const regionMap: Record<string, { exceptions: number; capPct: number; capCount: number; supplyScore: number; supplyCount: number }> = {};
    for (const reg of REGIONS) regionMap[reg] = { exceptions: 0, capPct: 0, capCount: 0, supplyScore: 0, supplyCount: 0 };

    // Count exceptions per region from recommendation scope text
    for (const c of allCards) {
      const scope = c.scope ?? "";
      for (const reg of REGIONS) {
        if (scope.includes(reg)) regionMap[reg].exceptions++;
      }
    }

    // Aggregate capacity utilisation per region (values are already 0–1 decimals, e.g. 1.13 = 113%)
    if (cap.status === "success") {
      for (const r of cap.data.rows) {
        if (!regionMap[r.Region]) continue;
        regionMap[r.Region].capPct += r.Utilisation_P90; // keep as decimal
        regionMap[r.Region].capCount++;
      }
    }

    // Aggregate supply risk score 0–100 per region
    if (supply.status === "success") {
      for (const r of supply.data.rows) {
        if (!regionMap[r.Region]) continue;
        regionMap[r.Region].supplyScore += r.Supply_risk_score;
        regionMap[r.Region].supplyCount++;
      }
    }

    return REGIONS.map((region) => {
      const d = regionMap[region];
      // avgCapUtil: decimal ratio (1.0 = 100%, 1.1 = 110%)
      const avgCapUtil  = d.capCount  > 0 ? d.capPct  / d.capCount  : 0.85;
      // avgSupply: 0–100 score
      const avgSupply   = d.supplyCount > 0 ? d.supplyScore / d.supplyCount : 20;

      // Normalise cap: 0 = 60% util, 1 = 120%+ util
      const capNorm = Math.min(1, Math.max(0, (avgCapUtil - 0.60) / 0.60));
      // Normalise supply: 0 = score 0, 1 = score 80+
      const supplyNorm = Math.min(1, avgSupply / 80);

      const riskScore = capNorm * 0.6 + supplyNorm * 0.4;
      const label = `Cap P90: ${Math.round(avgCapUtil * 100)}% · Supply risk: ${avgSupply.toFixed(0)} · Exceptions: ${d.exceptions}`;
      // Use exception count + 5 as a stable, reasonably-sized value
      return { region, value: d.exceptions + 5, riskScore, label };
    });
  }, [cap, supply, allCards]);

  // Urgency / window chart
  const urgencyChart = useMemo(() => {
    if (!allCards.length) return null;
    const counts: Record<string, number> = {};
    for (const c of allCards) counts[c.window ?? "Unknown"] = (counts[c.window ?? "Unknown"] ?? 0) + 1;
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return verticalBarsOption(
      entries.map(([k]) => k),
      [{ name: "Exceptions", data: entries.map(([, v]) => v) }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true, rotateLabels: true },
    );
  }, [allCards]);

  const prioCountChart = useMemo(() => {
    if (allRecs.status !== "success") return null;
    const bp = allRecs.data.by_priority;
    const colors = [STATUS.serious, STATUS.warning, SERIES[2]];
    return verticalBarsOption(
      ["CRITICAL", "HIGH", "MEDIUM"],
      (["CRITICAL", "HIGH", "MEDIUM"] as const).map((p, i) => ({
        name: p,
        data: ["CRITICAL", "HIGH", "MEDIUM"].map((q) => (q === p ? (bp[p] ?? 0) : null)),
        color: colors[i],
      })),
      { valueFormatter: (v) => fmtInt(v), showLabels: true },
    );
  }, [allRecs]);

  const ownerChart = useMemo(() => allCards.length ? ownerImpactOption(allCards) : null, [allCards]);

  const supplyCols = useMemo<Column<SupplyRiskRow>[]>(() => [
    { key: "family", label: "Family", value: (r) => r.Product_Family },
    { key: "region", label: "Region", value: (r) => r.Region },
    { key: "shortage", label: "Shortage mo", value: (r) => r.Shortage_months_36m, render: (r) => fmtInt(r.Shortage_months_36m), align: "right" },
    { key: "lost", label: "Lost units", value: (r) => r.Lost_units_36m, render: (r) => fmtInt(r.Lost_units_36m), align: "right" },
    { key: "meter", label: "Risk", value: (r) => r.Supply_risk_score,
      render: (r) => <RiskMeter score={r.Supply_risk_score} level={r.Supply_risk_level} /> },
    { key: "level", label: "Level", value: (r) => r.Supply_risk_level,
      render: (r) => (
        <Badge tone={r.Supply_risk_level === "HIGH" ? "critical" : r.Supply_risk_level === "MEDIUM" ? "warning" : "good"}>
          {r.Supply_risk_level}
        </Badge>
      ) },
  ], []);

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Risk & Exceptions · Ranked by business impact</p>
          <h2 className="page__title">What needs a decision, and where could it go wrong</h2>
          <p className="page__lead">
            Ranked exceptions from the forecast and history, capacity risks from demonstrated throughput,
            and fragile supply bases — every card carries its evidence.
          </p>
        </div>
      </div>

      {/* KPI row */}
      {allRecs.status === "loading" ? (
        <div className="kpi-row"><Skeleton height={128} /></div>
      ) : allRecs.status === "error" ? (
        <Card><ErrorState error={allRecs.error} onRetry={allRecs.retry} /></Card>
      ) : (
        <section className="kpi-row" aria-label="Risk summary">
          <KpiTile
            label="Total exceptions" value={fmtInt(allRecs.data.total)} unit="open"
            sub={
              <ImpactBar segments={[
                { label: "Critical", value: allRecs.data.by_priority.CRITICAL ?? 0, color: STATUS.serious },
                { label: "High",     value: allRecs.data.by_priority.HIGH     ?? 0, color: STATUS.warning },
                { label: "Medium",   value: allRecs.data.by_priority.MEDIUM   ?? 0, color: SERIES[2] },
              ]} />
            }
            footnote={`${allRecs.data.direct} in current selection`}
          />
          <KpiTile
            label="Critical" emphasis="critical" value={fmtInt(criticalCount)} unit="items"
            sub={`High: ${allRecs.data.by_priority.HIGH ?? 0} · Medium: ${allRecs.data.by_priority.MEDIUM ?? 0}`}
            footnote="Need action this planning cycle"
          />
          <KpiTile
            label="Total value at stake" emphasis="accent" value={fmtUsd(totalImpact, 1)}
            sub={
              <ImpactBar segments={[
                { label: "Critical", value: impactByPrio.CRITICAL, color: STATUS.serious },
                { label: "High",     value: impactByPrio.HIGH,     color: STATUS.warning },
                { label: "Medium",   value: impactByPrio.MEDIUM,   color: SERIES[2] },
              ]} />
            }
            footnote="Value at risk from the forecast"
          />
          <KpiTile
            label="High confidence" value={fmtInt(highConfCount)} unit="items"
            sub={`${allCards.length - highConfCount} with medium/low confidence`}
            footnote="Evidence from backtest or history"
          />
        </section>
      )}

      {/* World map — full width, regional risk bubbles */}
      <Card
        title="Regional risk map"
        subtitle="Scroll to zoom · drag to pan · bubble colour = composite risk (capacity + supply)"
        padded={false}
      >
        {cap.status === "loading" || allRecs.status === "loading" ? (
          <div style={{ padding: "0 20px 20px" }}><Skeleton height={500} /></div>
        ) : (
          <div style={{ width: "85%", margin: "0 auto", paddingBottom: 12 }}>
            <WorldMap regions={regionBubbles} height={500} title="Regional risk map" />
          </div>
        )}
      </Card>

      {/* Exceptions by priority + Value by owner */}
      <div className="grid grid--2">
        <Card title="Exceptions by priority" subtitle="Count and value at stake per tier">
          {allRecs.status === "loading" ? <Skeleton height={200} /> :
            prioCountChart ? (
              <div style={{ padding: "12px 20px 20px" }}>
                <EChart height={180} label="Exception count by priority" option={prioCountChart} />
                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  {(["CRITICAL", "HIGH", "MEDIUM"] as const).map((p) => (
                    <div key={p} style={{
                      display: "flex", alignItems: "center", gap: 6, padding: "4px 10px",
                      borderRadius: 6, background: "var(--surface-2)", border: "1px solid var(--border)",
                    }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: PRIO_COLOR[p], flexShrink: 0 }} />
                      <span style={{ fontSize: 12, color: "var(--text-3)" }}>{p}</span>
                      <strong style={{ fontSize: 12, color: "var(--text-1)" }}>{fmtUsd(impactByPrio[p], 1)}</strong>
                    </div>
                  ))}
                </div>
              </div>
            ) : <EmptyState title="No exceptions" icon="check" />}
        </Card>

        <Card title="Value at stake by owner" subtitle="Who owns the most at-risk value">
          {allRecs.status === "loading" ? <Skeleton height={200} /> :
            ownerChart ? (
              <div style={{ padding: "12px 20px 20px" }}>
                <EChart height={200} label="Impact by owner" option={ownerChart} />
              </div>
            ) : <EmptyState title="No owner data" icon="database" />}
        </Card>
      </div>

      {/* Capacity heatmap + planning window */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Capacity utilisation heatmap" subtitle="P90 utilisation by family × region (values > 100% = above demonstrated throughput)">
            {cap.status === "loading" ? <Skeleton height={220} /> :
              cap.status === "error" ? <ErrorState error={cap.error} onRetry={cap.retry} compact /> :
                <div style={{ padding: "12px 20px 20px" }}>
                  <CapacityHeatmap rows={cap.data.rows} />
                </div>
            }
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Exceptions by planning window" subtitle="When does each exception need a decision?">
            {allRecs.status === "loading" ? <Skeleton height={220} /> :
              urgencyChart ? (
                <div style={{ padding: "12px 20px 20px" }}>
                  <EChart height={220} label="Exceptions by planning window" option={urgencyChart} />
                </div>
              ) : <EmptyState title="No data" icon="database" />}
          </Card>
        </div>
      </div>

      {/* Exception queue */}
      <Card
        title="Exception resolution queue"
        subtitle="Ranked by impact × severity × urgency × confidence — expand a card for finding, action and evidence"
        actions={
          <div style={{ display: "flex", gap: "6px" }}>
            {(["all", "CRITICAL", "HIGH", "MEDIUM"] as const).map((p) => (
              <button key={p} type="button"
                className={`btn btn--sm ${priority === p ? "btn--accent" : "btn--ghost"}`}
                onClick={() => setPriority(p)}>
                {p === "all" ? "All" : p}
                {p !== "all" && allRecs.status === "success" && (allRecs.data.by_priority[p as "CRITICAL" | "HIGH" | "MEDIUM"] ?? 0) > 0
                  ? ` (${allRecs.data.by_priority[p as "CRITICAL" | "HIGH" | "MEDIUM"]})` : ""}
              </button>
            ))}
          </div>
        }
      >
        <div style={{ padding: "8px 20px 20px" }}>
          {recs.status === "loading" ? <Skeleton lines={6} /> :
            recs.status === "error" ? <ErrorState error={recs.error} onRetry={recs.retry} /> :
              cards.length === 0 ? <EmptyState title="No exceptions in this filter" icon="check" /> : (
                <ol className="actions" style={{ padding: 0, listStyle: "none" }}>
                  {cards.map((c) => (
                    <li key={c.id} className={`action ${open === c.id ? "action--open" : ""}`}
                      style={{ borderLeftColor: PRIO_COLOR[c.priority] ?? "var(--border-strong)" }}>
                      <button type="button" className="action__head"
                        onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id}>
                        <span className="action__rank mono">{c.id.replace("EX-", "#")}</span>
                        <span className="action__main">
                          <span className="action__title">{c.title}</span>
                          <span className="action__scope">{c.scope}{c.match === "context" && <span className="muted"> · context</span>}</span>
                        </span>
                        <span className="action__impact num">{fmtUsd(c.impact_usd, 1)}</span>
                        <Icon name="chevronDown" size={14} className="action__chev" />
                      </button>
                      <div className="action__meta">
                        <span><Icon name="dot" size={10} /> {c.owner}</span>
                        <span>{c.window}</span>
                        <Badge tone={PRIO_TONE[c.priority]} icon={null}>{c.priority}</Badge>
                        <Badge tone={CONF_TONE[c.confidence]} icon={null}>Conf {c.confidence.toLowerCase()}</Badge>
                      </div>
                      {open === c.id && (
                        <div className="action__body">
                          <p><span className="action__k">Finding</span>{c.finding}</p>
                          <p><span className="action__k">Suggested action</span>{c.action}</p>
                          {c.trade_off && <p><span className="action__k">Trade-off</span>{c.trade_off}</p>}
                          <div className="badge-row">
                            <Badge tone="neutral" icon={null}>Rule {c.rule_id}</Badge>
                            <Badge tone="neutral" icon={null}>Level {c.level}</Badge>
                          </div>
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              )
          }
        </div>
      </Card>

      {/* Supply risk */}
      <Card title="Supply risk register" subtitle="Shortage history and lost demand by family × region (36-month window)">
        {supply.status === "loading" ? <Skeleton height={240} /> :
          supply.status === "error" ? <ErrorState error={supply.error} onRetry={supply.retry} /> :
            supply.data.rows.length > 0 ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <DataTable columns={supplyCols} rows={supply.data.rows} caption="Supply risk"
                  maxHeight={300} initialSort={{ key: "meter", dir: "desc" }} />
              </div>
            ) : (
              <div style={{ padding: "24px 20px", display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ color: STATUS.good, fontSize: 20 }}>✓</span>
                <span style={{ color: "var(--text-2)", fontSize: 13 }}>
                  No supply risk entries — all supply bases look healthy over the 36-month window.
                </span>
              </div>
            )
        }
      </Card>
    </div>
  );
}
