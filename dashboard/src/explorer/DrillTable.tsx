import type { DrilldownView, DrillLevel, DrillRow } from "../api/types";
import { useDrilldown } from "../api/views";
import { Icon } from "../components/Icon";
import { Sparkline } from "../components/Sparkline";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { useFilters } from "../filters/FilterContext";
import { fmtPctPoints, fmtUnits, fmtUsd } from "../lib/format";
import { LEVEL_LABEL } from "./drill";

const LIFECYCLE_TONE: Record<string, "good" | "warning" | "serious" | "neutral" | "accent"> = {
  Active: "neutral", "EOL Announced": "warning", Discontinued: "serious", "Planned Launch": "accent",
};

function Status({ r }: { r: DrillRow }) {
  if (r.Lifecycle_Status) {
    const text = r.EOL_Date ? `EOL ${r.EOL_Date}${r.Successor_SKU ? ` → ${r.Successor_SKU}` : ""}`
      : r.Lifecycle_Status === "Planned Launch" && r.Launch_Date ? `Launch ${r.Launch_Date}` : r.Lifecycle_Status;
    return <Badge tone={LIFECYCLE_TONE[r.Lifecycle_Status] ?? "neutral"} icon={null}>{text}</Badge>;
  }
  if (r.Demand_Class) return <Badge tone="neutral" icon={null}>{r.Demand_Class}{r.Order_cycle_months ? ` · every ${r.Order_cycle_months} m` : ""}</Badge>;
  return null;
}

/** Members of the current drill level; clicking a row drills into it (sets that global filter). */
export function DrillTable({ level }: { level: DrillLevel }) {
  const st = useDrilldown(level, 60);
  const { dispatch } = useFilters();
  const drill = (d: DrilldownView, member: string) => dispatch({ type: "set", dim: d.level, values: [member] });

  return (
    <Card
      title={`${LEVEL_LABEL[level]} in this selection`}
      subtitle="Recovered demand last 12 months vs forecast next 12 months · click a row to drill down"
      padded={false}
    >
      {st.status === "loading" && <div className="card__body"><Skeleton lines={8} /></div>}
      {st.status === "error" && <div className="card__body"><ErrorState error={st.error} onRetry={st.retry} /></div>}
      {st.status === "success" && (st.data.rows.length === 0
        ? <div className="card__body"><EmptyState title="Nothing at this level" message="Widen the filters." icon="filter" /></div>
        : (
          <div className="drill">
            <table className="table drill__table">
              <thead>
                <tr>
                  <th>{level === "sku" ? "SKU" : level.charAt(0).toUpperCase() + level.slice(1)}</th>
                  <th className="hide-sm">Trend (24 m + 12 m forecast)</th>
                  <th className="ta-r">Last 12 m</th>
                  <th className="ta-r">Next 12 m</th>
                  <th className="ta-r">Change</th>
                  <th className="ta-r hide-sm">Revenue next 12 m</th>
                  <th className="ta-r hide-sm">Zero months</th>
                  <th className="hide-sm">{level === "sku" ? "Lifecycle" : level === "region" || level === "customer" ? "Demand class" : "Series"}</th>
                  <th aria-label="Drill down" />
                </tr>
              </thead>
              <tbody>
                {st.data.rows.map((r) => (
                  <tr key={r.Member} className="drill__row" tabIndex={0} role="button"
                    aria-label={`Drill into ${r.Member}`}
                    onClick={() => drill(st.data, r.Member)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); drill(st.data, r.Member); } }}>
                    <td className="c-main">
                      <span className="drill__member">{r.Member}</span>
                      {r.Label && <span className="drill__label">{r.Label}</span>}
                    </td>
                    <td className="hide-sm"><Sparkline history={r.spark_history} forecast={r.spark_forecast} label={`${r.Member} trend`} /></td>
                    <td className="ta-r num">{fmtUnits(r.Units_last12, 1)}</td>
                    <td className="ta-r num c-next">{fmtUnits(r.Units_next12, 1)}</td>
                    <td className={`ta-r num c-chg ${(r.Units_change_pct ?? 0) < 0 ? "is-neg" : "is-pos"}`}>{fmtPctPoints(r.Units_change_pct)}</td>
                    <td className="ta-r num hide-sm">{fmtUsd(r.Revenue_next12, 1)}</td>
                    <td className="ta-r num hide-sm">{r.Zero_share_24m === null ? "—" : `${Math.round(100 * r.Zero_share_24m)}%`}</td>
                    <td className="hide-sm">{level === "family" ? <span className="muted">{r.Series} series</span> : <Status r={r} />}</td>
                    <td className="drill__go"><Icon name="chevronDown" size={14} className="rot-90" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="panel-foot drill__foot">
              {st.data.members > st.data.rows.length
                ? `Top ${st.data.rows.length} of ${st.data.members} by next-12-month revenue`
                : `${st.data.members} ${LEVEL_LABEL[level].toLowerCase()}`} · zero months = share of observed months with no order (last 24 months)
            </p>
          </div>
        ))}
    </Card>
  );
}
