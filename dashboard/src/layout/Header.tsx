import { useLocation } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Icon } from "../components/Icon";
import { Badge } from "../components/ui";
import { VIEWS } from "../routes";

export function formatModel(id: string): string {
  const [head, ...rest] = id.split("_");
  if (!head) return id;
  const h = head.charAt(0).toUpperCase() + head.slice(1);
  return rest.length ? `${h} · ${rest.join(" ")}` : h;
}

export function formatMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

export function Header({ onMenu }: { onMenu: () => void }) {
  const { pathname } = useLocation();
  const view = VIEWS.find((v) => pathname.startsWith(v.path));
  const health = useApi((s) => api.health(s), []);
  const brief = useApi((s) => api.briefing(s), []);

  return (
    <header className="header">
      <button type="button" className="header__menu btn btn--icon" onClick={onMenu} aria-label="Open navigation">
        <Icon name="menu" size={20} />
      </button>
      <div className="header__title">
        <h1>
          {view?.number && <span className="header__num">{view.number}</span>}
          {view?.label ?? "Celeris Control Tower"}
        </h1>
        <p>AI demand planning · forecast intelligence · 19-month planning horizon</p>
      </div>

      <div className="header__status" aria-label="System status">
        {brief.status === "success" && (
          <span className="statchip" title="Last month of cleaned history">
            <span className="statchip__k">Data through</span>
            <span className="statchip__v">{formatMonth(brief.data.kpis.history_end)}</span>
          </span>
        )}
        {health.status === "loading" && <span className="statchip statchip--loading">Connecting…</span>}
        {health.status === "success" && (
          <>
            <span className="statchip" title={`Frozen ${health.data.frozen_at}`}>
              <span className="statchip__k">Model</span>
              <span className="statchip__v mono">{formatModel(health.data.selected_model)}</span>
            </span>
            <Badge tone={health.data.validation === "PASS" ? "good" : "critical"}>
              Validation {health.data.validation}
            </Badge>
          </>
        )}
        {health.status === "error" && (
          <Badge tone="critical">{health.error.status === null ? "API offline" : "Backend not frozen"}</Badge>
        )}
      </div>
    </header>
  );
}
