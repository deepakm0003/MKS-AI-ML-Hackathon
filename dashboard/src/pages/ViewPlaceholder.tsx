import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Icon } from "../components/Icon";
import { Badge, Card, ErrorState, Skeleton } from "../components/ui";
import { useFilters } from "../filters/FilterContext";
import { DIMS, DIM_LABEL } from "../filters/model";
import type { ViewDef } from "../routes";

/**
 * Phase-1 route placeholder. It shows what the view will answer and which contract
 * datasets feed it, with their LIVE availability from GET /datasets - never invented numbers.
 */
export function ViewPlaceholder({ view }: { view: ViewDef }) {
  const ds = useApi((s) => api.datasets(s), []);
  const { filters, active } = useFilters();

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">{view.number ? `Section ${view.number}` : "Required view"}</p>
          <h2 className="page__title">{view.label}</h2>
          <p className="page__lead">{view.purpose}</p>
        </div>
        <Badge tone="accent" icon="info">Build phase {view.phase}</Badge>
      </div>

      <div className="grid grid--3">
        <Card title="Questions this view answers">
          <ul className="checklist">
            {view.questions.map((q) => (
              <li key={q}><Icon name="dot" size={14} className="checklist__dot" />{q}</li>
            ))}
          </ul>
        </Card>

        <Card title="Problem-statement coverage" subtitle="Required and optional views delivered here">
          <div className="badge-row">
            {view.covers.required.map((r) => <Badge key={r} tone="good">Required · {r}</Badge>)}
            {view.covers.optional.map((o) => <Badge key={o} tone="accent" icon={null}>Optional · {o}</Badge>)}
            {!view.covers.required.length && !view.covers.optional.length && <span className="muted">—</span>}
          </div>
        </Card>

        <Card title="Active filters" subtitle="Shared by every view (family, SKU, region, channel, customer)">
          {active === 0 ? <p className="muted">None - all series.</p> : (
            <dl className="kv">
              {DIMS.filter((d) => filters[d].length).map((d) => (
                <div key={d} className="kv__row">
                  <dt>{DIM_LABEL[d]}</dt>
                  <dd>{filters[d].join(", ")}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>
      </div>

      <Card title="Data readiness" subtitle="Live check of the frozen backend for every source this view will read">
        {ds.status === "loading" && <Skeleton lines={4} />}
        {ds.status === "error" && <ErrorState error={ds.error} onRetry={ds.retry} />}
        {ds.status === "success" && (
          <table className="table">
            <thead>
              <tr><th>Source</th><th>Kind</th><th>Path / route</th><th>Status</th></tr>
            </thead>
            <tbody>
              {view.sources.map((src) => {
                const info = ds.data[src];
                const isEndpoint = src.startsWith("/") || src.startsWith("POST");
                return (
                  <tr key={src}>
                    <td className="mono">{src}</td>
                    <td>{isEndpoint ? "API endpoint" : "Contract dataset"}</td>
                    <td className="mono muted">{info?.path ?? (isEndpoint ? src : "not in contract")}</td>
                    <td>
                      {isEndpoint ? <Badge tone="neutral" icon={null}>Served live</Badge>
                        : info ? (info.available ? <Badge tone="good">Available</Badge> : <Badge tone="warning">Not generated</Badge>)
                          : <Badge tone="critical">Missing</Badge>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

export function NotFound() {
  return (
    <div className="page">
      <Card>
        <div className="state state--empty">
          <span className="state__icon"><Icon name="search" size={22} /></span>
          <p className="state__title">View not found</p>
          <p className="state__text">Use the navigation to open one of the planning views.</p>
        </div>
      </Card>
    </div>
  );
}
