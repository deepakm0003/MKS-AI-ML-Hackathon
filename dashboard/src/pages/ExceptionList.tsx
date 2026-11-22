import { useMemo, useState } from "react";
import { useRecommendations } from "../api/views";
import { Icon } from "../components/Icon";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtUsd } from "../lib/format";

type PriorityFilter = "ALL" | "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
type OwnerFilter = "ALL" | "Procurement" | "Production" | "Planning" | "Sales" | "Finance";

/** Exception List — all actionable exceptions with filters and CSV export. */
export function ExceptionList() {
  const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("ALL");
  const [ownerFilter, setOwnerFilter] = useState<OwnerFilter>("ALL");
  
  const recs = useRecommendations({ limit: 1000 });

  // Filter recommendations
  const filtered = useMemo(() => {
    if (recs.status !== "success") return [];
    let result = recs.data.cards;
    
    if (priorityFilter !== "ALL") {
      result = result.filter((c) => c.priority === priorityFilter);
    }
    
    if (ownerFilter !== "ALL") {
      result = result.filter((c) => c.owner === ownerFilter);
    }
    
    return result;
  }, [recs, priorityFilter, ownerFilter]);

  // Get unique owners and priorities
  const uniqueOwners = useMemo(() => {
    if (recs.status !== "success") return [];
    return Array.from(new Set(recs.data.cards.map((c) => c.owner))).sort();
  }, [recs]);

  const uniquePriorities = useMemo(() => {
    if (recs.status !== "success") return [];
    return Array.from(new Set(recs.data.cards.map((c) => c.priority))).sort();
  }, [recs]);

  // Export to CSV
  const exportToCsv = () => {
    if (filtered.length === 0) return;
    
    const headers = ["ID", "Priority", "Rule", "Scope", "Title", "Finding", "Action", "Owner", "Impact_USD", "Window", "Confidence"];
    const rows = filtered.map((c) => [
      c.id,
      c.priority,
      c.rule_id,
      c.scope,
      c.title,
      c.finding.replace(/"/g, '""'),
      c.action.replace(/"/g, '""'),
      c.owner,
      c.impact_usd,
      c.window,
      c.confidence,
    ]);
    
    const csv = [
      headers.join(","),
      ...rows.map((r) => r.map((v) => `"${v}"`).join(",")),
    ].join("\n");
    
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `exceptions_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Exception List · Actionable planning exceptions</p>
          <h2 className="page__title">All exceptions ranked by priority, impact and urgency</h2>
          <p className="page__lead">
            Every exception from the intelligence engine with its evidence, recommended action, owner and
            decision window. Filter by priority or owner, then export to share with your team.
          </p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="ov-grid" style={{ marginBottom: 24 }}>
        <div className="ov-grid__main">
          <Card>
            <div style={{ padding: "20px", display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 4 }}>Total exceptions</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: "var(--text-1)" }}>
                  {recs.status === "loading" ? "—" : recs.status === "success" ? recs.data.cards.length : "—"}
                </div>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 4 }}>Filtered results</div>
                <div style={{ fontSize: 32, fontWeight: 700, color: "var(--accent)" }}>
                  {recs.status === "success" ? filtered.length : "—"}
                </div>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, color: "var(--text-3)", marginBottom: 4 }}>Total impact</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text-1)" }}>
                  {recs.status === "success" ? fmtUsd(filtered.reduce((s, c) => s + (c.impact_usd ?? 0), 0), 1) : "—"}
                </div>
              </div>
            </div>
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card>
            <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 12 }}>
              <button
                type="button"
                className="btn btn--accent"
                onClick={exportToCsv}
                disabled={recs.status !== "success" || filtered.length === 0}
                style={{ width: "100%" }}
              >
                <Icon name="download" size={16} />
                Export filtered to CSV
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => {
                  setPriorityFilter("ALL");
                  setOwnerFilter("ALL");
                }}
                style={{ width: "100%" }}
              >
                Clear all filters
              </button>
            </div>
          </Card>
        </div>
      </div>

      {/* Filters */}
      <div className="ov-grid" style={{ marginBottom: 24 }}>
        <div className="ov-grid__main">
          <Card title="Filter by priority" subtitle="Show only exceptions at selected priority level">
            <div style={{ padding: "16px 20px 20px", display: "flex", flexWrap: "wrap", gap: 8 }}>
              <button
                type="button"
                className={`btn ${priorityFilter === "ALL" ? "btn--accent" : "btn--ghost"}`}
                onClick={() => setPriorityFilter("ALL")}
              >
                All
              </button>
              {uniquePriorities.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`btn ${priorityFilter === p ? "btn--accent" : "btn--ghost"}`}
                  onClick={() => setPriorityFilter(p as PriorityFilter)}
                >
                  {p}
                  {recs.status === "success" && (
                    <span style={{ marginLeft: 6, opacity: 0.7 }}>
                      ({recs.data.cards.filter((c) => c.priority === p).length})
                    </span>
                  )}
                </button>
              ))}
            </div>
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Filter by owner" subtitle="Show only exceptions assigned to selected owner">
            <div style={{ padding: "16px 20px 20px", display: "flex", flexWrap: "wrap", gap: 8 }}>
              <button
                type="button"
                className={`btn ${ownerFilter === "ALL" ? "btn--accent" : "btn--ghost"}`}
                onClick={() => setOwnerFilter("ALL")}
              >
                All
              </button>
              {uniqueOwners.map((o) => (
                <button
                  key={o}
                  type="button"
                  className={`btn ${ownerFilter === o ? "btn--accent" : "btn--ghost"}`}
                  onClick={() => setOwnerFilter(o as OwnerFilter)}
                >
                  {o}
                  {recs.status === "success" && (
                    <span style={{ marginLeft: 6, opacity: 0.7 }}>
                      ({recs.data.cards.filter((c) => c.owner === o).length})
                    </span>
                  )}
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* Exception list */}
      <Card title="Exceptions" subtitle={`${filtered.length} results — sorted by priority and impact`}>
        {recs.status === "loading" ? (
          <Skeleton height={600} />
        ) : recs.status === "error" ? (
          <ErrorState error={recs.error} onRetry={recs.retry} />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No exceptions match filters"
            message="Try adjusting your priority or owner filters."
            icon="filter"
          />
        ) : (
          <div style={{ padding: "8px 20px 20px" }}>
            <ol className="actions" style={{ padding: 0, listStyle: "none" }}>
              {filtered.map((c) => (
                <li key={c.id} className="action" style={{
                  borderLeftColor:
                    c.priority === "CRITICAL" ? "var(--critical)" :
                    c.priority === "HIGH" ? "var(--warning)" :
                    "var(--accent)",
                }}>
                  <div className="action__head">
                    <span className="action__rank mono">{c.id.replace("EX-", "#")}</span>
                    <span className="action__main">
                      <span className="action__title">{c.title}</span>
                      <span className="action__scope">{c.scope}</span>
                    </span>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                      <Badge tone={
                        c.priority === "CRITICAL" ? "critical" :
                        c.priority === "HIGH" ? "warning" :
                        c.priority === "MEDIUM" ? "accent" :
                        "neutral"
                      }>
                        {c.priority}
                      </Badge>
                      <span className="action__impact num">{fmtUsd(c.impact_usd, 1)}</span>
                    </div>
                  </div>
                  
                  <div style={{ padding: "12px 16px", background: "var(--surface-2)", borderRadius: 6, margin: "8px 0" }}>
                    <div style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase" }}>
                        Finding
                      </span>
                      <p style={{ fontSize: 13, color: "var(--text-2)", margin: "4px 0 0" }}>{c.finding}</p>
                    </div>
                    <div>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase" }}>
                        Recommended Action
                      </span>
                      <p style={{ fontSize: 13, color: "var(--text-1)", margin: "4px 0 0", fontWeight: 500 }}>{c.action}</p>
                    </div>
                  </div>

                  <div className="action__meta">
                    <span>
                      <Icon name="dot" size={10} /> Owner: <strong>{c.owner}</strong>
                    </span>
                    <span>
                      <Icon name="dot" size={10} /> Rule: {c.rule_id}
                    </span>
                    <span>
                      <Icon name="dot" size={10} /> Window: {c.window}
                    </span>
                    <span>
                      <Icon name="dot" size={10} /> Confidence: {c.confidence}
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Card>
    </div>
  );
}
