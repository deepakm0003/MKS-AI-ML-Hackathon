import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { Recommendations, RecommendationCard } from "../api/types";
import type { ApiState } from "../api/useApi";
import { Icon } from "../components/Icon";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtUsd } from "../lib/format";

const CONF_TONE = { HIGH: "good", MEDIUM: "warning", LOW: "serious" } as const;

function ActionItem({ c }: { c: RecommendationCard }) {
  const [open, setOpen] = useState(false);
  return (
    <li className={`action ${open ? "action--open" : ""}`}>
      <button type="button" className="action__head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
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
      </div>
      {open && (
        <div className="action__body">
          <p><span className="action__k">Finding</span>{c.finding}</p>
          <p><span className="action__k">Suggested action</span>{c.action}</p>
          <p><span className="action__k">Trade-off</span>{c.trade_off}</p>
          <div className="badge-row">
            <Badge tone={CONF_TONE[c.confidence]} icon={null}>Confidence {c.confidence.toLowerCase()}</Badge>
            <Badge tone="neutral" icon={null}>Rule {c.rule_id}</Badge>
          </div>
        </div>
      )}
    </li>
  );
}

/** "What should I do now?" - the top critical recommendations for the current filters. */
export function ActNowPanel({ state, max = 5 }: { state: ApiState<Recommendations> & { retry: () => void }; max?: number }) {
  const { search } = useLocation();
  return (
    <Card
      title="Act now"
      subtitle="Critical recommendations, ranked by impact × severity × urgency × confidence"
      className="actnow"
      actions={<Link className="btn btn--text" to={{ pathname: "/risk", search }}>All exceptions <Icon name="chevronDown" size={12} className="rot-90" /></Link>}
    >
      {state.status === "loading" && <Skeleton lines={6} />}
      {state.status === "error" && <ErrorState error={state.error} onRetry={state.retry} />}
      {state.status === "success" && (state.data.cards.length === 0
        ? <EmptyState title="No critical actions" message="Nothing critical in the current selection." icon="check" />
        : (
          <>
            <ol className="actions">
              {state.data.cards.slice(0, max).map((c) => <ActionItem key={c.id} c={c} />)}
            </ol>
            <p className="panel-foot">
              Suggested actions - every figure comes from the forecast, backtest or history (evidence on each card). Impact = value at stake.
            </p>
          </>
        ))}
    </Card>
  );
}
