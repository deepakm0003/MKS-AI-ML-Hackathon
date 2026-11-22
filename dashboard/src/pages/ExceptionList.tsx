import { useMemo, useState } from "react";
import { EChart } from "../charts/EChart";
import { verticalBarsOption, genericRankedBarsOption } from "../charts/options";
import { useRecommendations } from "../api/views";
import { Icon } from "../components/Icon";
import { Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt, fmtUsd } from "../lib/format";
import { SERIES } from "../theme/chart";
import type { RecommendationCard } from "../api/types";

type PriorityFilter = "ALL" | "CRITICAL" | "HIGH" | "MEDIUM";
type OwnerFilter = "ALL" | string;

/* ── colour helpers ──────────────────────────────────────────── */
function priorityColor(p: string) {
  if (p === "CRITICAL") return "var(--critical)";
  if (p === "HIGH")     return "var(--warning)";
  return "var(--accent)"; // MEDIUM → lime
}

function priorityBg(p: string) {
  if (p === "CRITICAL") return "rgba(255,92,92,0.08)";
  if (p === "HIGH")     return "rgba(245,185,66,0.08)";
  return "rgba(199,255,50,0.07)";
}

/** Exception List — charts + filterable cards with CSV export. */
export function ExceptionList() {
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("ALL");
  const [ownerFilter, setOwnerFilter]       = useState<OwnerFilter>("ALL");

  const recs = useRecommendations({ limit: 1000 });

  /* ── derived data ─────────────────────────────────────────── */
  const allCards: RecommendationCard[] = recs.status === "success" ? recs.data.cards : [];

  const filtered = useMemo(() => {
    let r = allCards;
    if (priorityFilter !== "ALL") r = r.filter((c) => c.priority === priorityFilter);
    if (ownerFilter    !== "ALL") r = r.filter((c) => c.owner    === ownerFilter);
    return r;
  }, [allCards, priorityFilter, ownerFilter]);

  const uniqueOwners    = useMemo(() => Array.from(new Set(allCards.map((c) => c.owner))).sort(), [allCards]);
  const uniquePriorities: PriorityFilter[] = useMemo(
    () => (["CRITICAL", "HIGH", "MEDIUM"] as PriorityFilter[]).filter((p) => allCards.some((c) => c.priority === p)),
    [allCards],
  );

  /* ── chart: by_priority bars ──────────────────────────────── */
  const priorityChart = useMemo(() => {
    if (!allCards.length) return null;
    const counts: Record<string, number> = {};
    for (const c of allCards) counts[c.priority] = (counts[c.priority] ?? 0) + 1;
    const order = ["CRITICAL", "HIGH", "MEDIUM"];
    const cats  = order.filter((p) => counts[p]);
    return verticalBarsOption(
      cats,
      [{
        name: "Exceptions",
        data: cats.map((p) => counts[p]),
        color: undefined, // will be overridden per bar below
      }],
      { valueFormatter: (v) => fmtInt(v), showLabels: true },
    );
  }, [allCards]);

  // Override bar colours after the option is built
  const priorityChartColored = useMemo(() => {
    if (!allCards.length) return null;
    const counts: Record<string, number> = {};
    for (const c of allCards) counts[c.priority] = (counts[c.priority] ?? 0) + 1;
    const order  = ["CRITICAL", "HIGH", "MEDIUM"];
    const cats   = order.filter((p) => counts[p]);
    const colors = { CRITICAL: "var(--critical)", HIGH: "var(--warning)", MEDIUM: SERIES[0] };
    return {
      ...priorityChart,
      series: [{
        type: "bar",
        data: cats.map((p) => ({
          value: counts[p],
          itemStyle: { color: colors[p as keyof typeof colors] ?? SERIES[0], borderRadius: [3, 3, 0, 0] },
        })),
        barMaxWidth: 56,
        label: { show: true, position: "top", color: "#a1a1a1", fontSize: 12, fontWeight: 600 },
      }],
    };
  }, [allCards, priorityChart]);

  /* ── chart: top owners by impact ─────────────────────────── */
  const ownerImpactChart = useMemo(() => {
    if (!allCards.length) return null;
    const impact: Record<string, number> = {};
    for (const c of allCards) impact[c.owner] = (impact[c.owner] ?? 0) + (c.impact_usd ?? 0);
    const items = Object.entries(impact)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([label, value]) => ({ label, value }));
    return genericRankedBarsOption(items, {
      valueFormatter: (v) => fmtUsd(v, 1),
      color: SERIES[1], // blue for owner breakdown
    });
  }, [allCards]);

  /* ── chart: by rule_id ─────────────────────────────────────── */
  const ruleChart = useMemo(() => {
    if (!allCards.length) return null;
    const counts: Record<string, number> = {};
    for (const c of allCards) counts[c.rule_id] = (counts[c.rule_id] ?? 0) + 1;
    const items = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([label, value]) => ({ label, value }));
    return genericRankedBarsOption(items, {
      valueFormatter: (v) => fmtInt(v),
      color: SERIES[0], // lime
    });
  }, [allCards]);

  /* ── totals ──────────────────────────────────────────────────*/
  const totalImpact    = filtered.reduce((s, c) => s + (c.impact_usd ?? 0), 0);
  const criticalCount  = allCards.filter((c) => c.priority === "CRITICAL").length;
  const highCount      = allCards.filter((c) => c.priority === "HIGH").length;

  /* ── csv export ──────────────────────────────────────────── */
  const exportToCsv = () => {
    if (!filtered.length) return;
    const headers = ["ID","Priority","Rule","Scope","Title","Finding","Action","Owner","Impact_USD","Window","Confidence"];
    const rows = filtered.map((c) => [
      c.id, c.priority, c.rule_id, c.scope,
      c.title, c.finding.replace(/"/g, '""'), c.action.replace(/"/g, '""'),
      c.owner, c.impact_usd, c.window, c.confidence,
    ]);
    const csv  = [headers.join(","), ...rows.map((r) => r.map((v) => `"${v}"`).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `exceptions_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const clearFilters = () => { setPriorityFilter("ALL"); setOwnerFilter("ALL"); };
  const hasFilters   = priorityFilter !== "ALL" || ownerFilter !== "ALL";

  return (
    <div className="page">

      {/* ── Page header ──────────────────────────────────────── */}
      <div className="page__intro">
        <div>
          <p className="eyebrow">Exception List · Actionable planning exceptions</p>
          <h2 className="page__title">All exceptions ranked by priority, impact and urgency</h2>
          <p className="page__lead">
            Every exception from the intelligence engine — finding, recommended action, owner and
            decision window. Filter by priority or owner, export to share with your team.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          {hasFilters && (
            <button type="button" className="btn btn--ghost" onClick={clearFilters}>
              <Icon name="close" size={14} /> Clear filters
            </button>
          )}
          <button
            type="button" className="btn btn--accent"
            onClick={exportToCsv}
            disabled={recs.status !== "success" || !filtered.length}
          >
            <Icon name="download" size={14} /> Export CSV
          </button>
        </div>
      </div>

      {/* ── Summary KPI row ──────────────────────────────────── */}
      <section className="kpi-row" aria-label="Exception summary">
        <div className="kpi" style={{ borderColor: "var(--critical)", background: "rgba(255,92,92,0.06)" }}>
          <span className="kpi__label">Critical</span>
          <div className="kpi__value" style={{ color: "var(--critical)" }}>
            {recs.status === "loading" ? "—" : fmtInt(criticalCount)}
          </div>
          <span className="kpi__sub">Requires immediate action</span>
        </div>
        <div className="kpi" style={{ borderColor: "var(--warning)", background: "rgba(245,185,66,0.06)" }}>
          <span className="kpi__label">High priority</span>
          <div className="kpi__value" style={{ color: "var(--warning)" }}>
            {recs.status === "loading" ? "—" : fmtInt(highCount)}
          </div>
          <span className="kpi__sub">Action within this week</span>
        </div>
        <div className="kpi kpi--accent">
          <span className="kpi__label">Filtered shown</span>
          <div className="kpi__value">{recs.status === "loading" ? "—" : fmtInt(filtered.length)}</div>
          <span className="kpi__sub">of {fmtInt(allCards.length)} total</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">Impact at stake</span>
          <div className="kpi__value" style={{ fontSize: "var(--fs-24)" }}>
            {recs.status === "loading" ? "—" : fmtUsd(totalImpact, 1)}
          </div>
          <span className="kpi__sub">Filtered exceptions</span>
        </div>
      </section>

      {/* ── Charts row ───────────────────────────────────────── */}
      {recs.status !== "loading" && allCards.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20 }}>
          <Card title="By priority" subtitle="Count of exceptions at each severity level">
            <div style={{ padding: "12px 20px 20px" }}>
              <EChart height={200} label="Exceptions by priority" option={priorityChartColored ?? {}} />
            </div>
          </Card>
          <Card title="Impact by owner" subtitle="Total revenue at stake per owner team">
            {ownerImpactChart ? (
              <div style={{ padding: "12px 20px 20px" }}>
                <EChart height={200} label="Impact by owner" option={ownerImpactChart} />
              </div>
            ) : <EmptyState title="No data" icon="database" />}
          </Card>
          <Card title="By rule type" subtitle="Top 10 exception rule types triggered">
            {ruleChart ? (
              <div style={{ padding: "12px 20px 20px" }}>
                <EChart height={200} label="Exceptions by rule" option={ruleChart} />
              </div>
            ) : <EmptyState title="No data" icon="database" />}
          </Card>
        </div>
      )}
      {recs.status === "loading" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20 }}>
          <Card><Skeleton height={240} /></Card>
          <Card><Skeleton height={240} /></Card>
          <Card><Skeleton height={240} /></Card>
        </div>
      )}

      {/* ── Filter controls ──────────────────────────────────── */}
      <div className="ov-grid">
        {/* Priority filter */}
        <div className="ov-grid__main">
          <Card title="Filter by priority" subtitle="Show only exceptions at selected severity level">
            <div style={{ padding: "12px 20px 20px", display: "flex", flexWrap: "wrap", gap: 8 }}>
              {(["ALL", ...uniquePriorities] as const).map((p) => {
                const active = priorityFilter === p;
                const col    = p === "ALL" ? "var(--accent)" : priorityColor(p);
                return (
                  <button
                    key={p} type="button"
                    onClick={() => setPriorityFilter(p as PriorityFilter)}
                    style={{
                      height: 34, padding: "0 14px", borderRadius: "var(--radius-md)",
                      border: `1px solid ${active ? col : "var(--border)"}`,
                      background: active ? (p === "ALL" ? "var(--accent-soft)" : priorityBg(p)) : "transparent",
                      color: active ? col : "var(--text-3)",
                      fontWeight: active ? 600 : 400, fontSize: 13, cursor: "pointer",
                      transition: "all 0.12s",
                    }}
                  >
                    {p === "ALL" ? "All" : p}
                    {p !== "ALL" && recs.status === "success" && (
                      <span style={{ marginLeft: 7, opacity: 0.65, fontWeight: 400 }}>
                        {allCards.filter((c) => c.priority === p).length}
                      </span>
                    )}
                    {p === "ALL" && recs.status === "success" && (
                      <span style={{ marginLeft: 7, opacity: 0.65, fontWeight: 400 }}>{allCards.length}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </Card>
        </div>

        {/* Owner filter */}
        <div className="ov-grid__side">
          <Card title="Filter by owner" subtitle="Show only exceptions assigned to this team">
            <div style={{ padding: "12px 20px 20px", display: "flex", flexWrap: "wrap", gap: 8 }}>
              {(["ALL", ...uniqueOwners]).map((o) => {
                const active = ownerFilter === o;
                return (
                  <button
                    key={o} type="button"
                    onClick={() => setOwnerFilter(o)}
                    style={{
                      height: 30, padding: "0 12px", borderRadius: "var(--radius-md)",
                      border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                      background: active ? "var(--accent-soft)" : "transparent",
                      color: active ? "var(--accent)" : "var(--text-3)",
                      fontWeight: active ? 600 : 400, fontSize: 12, cursor: "pointer",
                      transition: "all 0.12s",
                    }}
                  >
                    {o === "ALL" ? "All" : o}
                    {recs.status === "success" && (
                      <span style={{ marginLeft: 6, opacity: 0.6, fontWeight: 400 }}>
                        {o === "ALL" ? allCards.length : allCards.filter((c) => c.owner === o).length}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </Card>
        </div>
      </div>

      {/* ── Exception cards ──────────────────────────────────── */}
      <Card
        title={`Exceptions${hasFilters ? " (filtered)" : ""}`}
        subtitle={`${filtered.length} result${filtered.length !== 1 ? "s" : ""} · sorted by priority and impact`}
      >
        {recs.status === "loading" ? (
          <Skeleton height={500} />
        ) : recs.status === "error" ? (
          <ErrorState error={recs.error} onRetry={recs.retry} />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No exceptions match the current filters"
            message="Try selecting All priority or clearing the owner filter."
            icon="filter"
          />
        ) : (
          <div style={{ padding: "8px 20px 20px" }}>
            <ol style={{ padding: 0, margin: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 8 }}>
              {filtered.map((c) => {
                const col = priorityColor(c.priority);
                return (
                  <li
                    key={c.id}
                    style={{
                      border: `1px solid var(--border)`,
                      borderLeft: `3px solid ${col}`,
                      borderRadius: "var(--radius-md)",
                      background: "var(--surface-1)",
                      transition: "background 0.12s, border-color 0.12s",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.background = `color-mix(in srgb, ${col} 7%, var(--surface-1))`;
                      (e.currentTarget as HTMLElement).style.borderColor = col;
                      (e.currentTarget as HTMLElement).style.borderLeftColor = col;
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background = "var(--surface-1)";
                      (e.currentTarget as HTMLElement).style.borderColor = "var(--border)";
                      (e.currentTarget as HTMLElement).style.borderLeftColor = col;
                    }}
                  >
                    {/* head row */}
                    <div style={{
                      display: "grid", gridTemplateColumns: "auto minmax(0,1fr) auto",
                      alignItems: "center", gap: 12, padding: "12px 16px 8px",
                    }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-3)" }}>
                        {c.id.replace("EX-", "#")}
                      </span>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-1)" }}>{c.title}</div>
                        <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {c.scope}
                        </div>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
                        <span style={{
                          display: "inline-flex", alignItems: "center", height: 22, padding: "0 8px",
                          borderRadius: "var(--radius-pill)", border: `1px solid ${col}`,
                          background: priorityBg(c.priority),
                          color: col, fontSize: 11, fontWeight: 700, letterSpacing: "0.04em",
                        }}>
                          {c.priority}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)", fontVariantNumeric: "tabular-nums" }}>
                          {fmtUsd(c.impact_usd, 1)}
                        </span>
                      </div>
                    </div>

                    {/* finding + action */}
                    <div style={{ margin: "0 16px 10px", padding: "10px 14px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                      <div style={{ marginBottom: 8 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Finding</span>
                        <p style={{ fontSize: 13, color: "var(--text-2)", margin: "3px 0 0", lineHeight: 1.5 }}>{c.finding}</p>
                      </div>
                      <div>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Action</span>
                        <p style={{ fontSize: 13, color: "var(--text-1)", margin: "3px 0 0", fontWeight: 500, lineHeight: 1.5 }}>{c.action}</p>
                      </div>
                    </div>

                    {/* meta footer */}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 20px", padding: "0 16px 10px", fontSize: 11, color: "var(--text-3)" }}>
                      <span>Owner: <strong style={{ color: "var(--text-2)" }}>{c.owner}</strong></span>
                      <span>Rule: {c.rule_id}</span>
                      <span>Window: {c.window}</span>
                      <span>Confidence: <span style={{ color: c.confidence === "HIGH" ? "var(--accent)" : "var(--text-2)" }}>{c.confidence}</span></span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}
      </Card>
    </div>
  );
}
