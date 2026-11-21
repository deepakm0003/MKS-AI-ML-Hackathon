import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Icon } from "../components/Icon";
import { Card, ErrorState, Skeleton } from "../components/ui";
import { fmtPctPoints, fmtUsd } from "../lib/format";

const ORDER = ["Downside", "Auto slowdown", "PMI -3", "Raw-material spike", "EV acceleration", "Upside"];

/** Macro scenario impact on the 19-month forecast - exact model re-forecasts, company-wide. */
export function ScenarioImpactPanel() {
  const st = useApi((s) => api.scenarioPresets(s), []);
  return (
    <Card
      title="Macro scenario impact"
      subtitle="19-month demand vs base case, company-wide"
      actions={<Link className="btn btn--text" to="/scenarios">Scenario Lab</Link>}
    >
      {st.status === "loading" && <Skeleton lines={6} />}
      {st.status === "error" && <ErrorState error={st.error} onRetry={st.retry} />}
      {st.status === "success" && (() => {
        const rows = ORDER.filter((n) => st.data[n]).map((n) => ({ name: n, ...st.data[n].total }));
        const span = Math.max(1, ...rows.map((r) => Math.abs(r.change_pct)));
        return (
          <>
            <ul className="scen">
              {rows.map((r) => {
                const neg = r.change_pct < 0;
                const w = `${(50 * Math.abs(r.change_pct)) / span}%`;
                return (
                  <li key={r.name} className="scen__row">
                    <span className="scen__name">{r.name}</span>
                    <span className="scen__bar" aria-hidden>
                      <span className="scen__zero" />
                      <span className={`scen__fill ${neg ? "scen__fill--neg" : "scen__fill--pos"}`}
                        style={neg ? { right: "50%", width: w } : { left: "50%", width: w }} />
                    </span>
                    <span className={`scen__val num ${neg ? "is-neg" : "is-pos"}`}>
                      <Icon name={neg ? "arrowDown" : "arrowUp"} size={12} />{fmtPctPoints(r.change_pct)}
                    </span>
                    <span className="scen__rev num">{r.change_revenue !== undefined ? fmtUsd(r.change_revenue, 0) : "—"}</span>
                  </li>
                );
              })}
            </ul>
            <p className="panel-foot">Exact re-forecasts of the frozen model with shifted macro inputs; revenue at the announced list prices.</p>
          </>
        );
      })()}
    </Card>
  );
}
