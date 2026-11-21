import type { ReactNode } from "react";
import { Icon } from "./Icon";
import { Skeleton } from "./ui";

export type Trend = "up" | "down" | "flat";

export interface KpiDelta {
  /** Display text, e.g. "+6.1% vs last 12 m". */
  text: string;
  trend: Trend;
  /** Whether "up" is good (demand, revenue) or bad (risk, errors); "neutral" = no judgement. */
  goodWhen?: "up" | "down" | "neutral";
}

function tone(d: KpiDelta): "good" | "critical" | "neutral" {
  if (!d.goodWhen || d.goodWhen === "neutral" || d.trend === "flat") return "neutral";
  return (d.trend === "up") === (d.goodWhen === "up") ? "good" : "critical";
}

/**
 * Headline number. Renders a skeleton while loading and "—" when the value is missing -
 * never a placeholder figure. The delta carries an arrow and a sign, not colour alone.
 */
export function KpiTile({ label, value, unit, sub, delta, loading, emphasis, footnote }: {
  label: string; value?: string; unit?: string; sub?: ReactNode; delta?: KpiDelta; loading?: boolean;
  emphasis?: "critical" | "accent"; footnote?: string;
}) {
  return (
    <div className={`kpi ${emphasis ? `kpi--${emphasis}` : ""}`} aria-busy={loading || undefined}>
      <p className="kpi__label">{label}</p>
      {loading ? (
        <div className="kpi__loading"><Skeleton height={34} /><Skeleton lines={1} /></div>
      ) : (
        <>
          <p className="kpi__value num">
            {value ?? "—"}
            {unit && value && <span className="kpi__unit">{unit}</span>}
          </p>
          {delta && (
            <p className={`kpi__delta kpi__delta--${tone(delta)}`}>
              <Icon name={delta.trend === "down" ? "arrowDown" : delta.trend === "up" ? "arrowUp" : "minus"} size={14} />
              {delta.text}
            </p>
          )}
          {sub && <p className="kpi__sub">{sub}</p>}
        </>
      )}
      {footnote && !loading && <p className="kpi__foot">{footnote}</p>}
    </div>
  );
}
