import { TimelineCard } from "../charts/TimelineCard";
import { Icon } from "../components/Icon";
import { crumbs, explorerMode, LEVEL_LABEL } from "../explorer/drill";
import { DrillTable } from "../explorer/DrillTable";
import { DemandProfileCard, LifecycleCard } from "../explorer/ProfilePanels";
import { SeasonalityCard } from "../explorer/SeasonalityCard";
import { SeriesPanel } from "../explorer/SeriesPanel";
import { useFilters } from "../filters/FilterContext";

/**
 * 02 Demand Explorer - what happened and how the forecast continues it, at any level of the
 * hierarchy: drill family -> SKU -> region -> customer (through the global filters), with
 * seasonality, zero-order months, demand classes and lifecycle for the current selection.
 */
export function DemandExplorer() {
  const { filters, dispatch } = useFilters();
  const mode = explorerMode(filters);
  const path = crumbs(filters);

  return (
    <div className="page explorer">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Demand explorer · history 2019-01 → forecast 2028-05</p>
          <h2 className="page__title">How demand behaved, and how the forecast continues it</h2>
          <nav className="drillpath" aria-label="Drill-down path">
            {path.map((c, i) => (
              <span key={c.label} className="drillpath__item">
                {i > 0 && <Icon name="chevronDown" size={12} className="rot-90 drillpath__sep" />}
                {i === path.length - 1 ? <span className="drillpath__here" aria-current="page">{c.label}</span> : (
                  <button type="button" className="linkish" onClick={() => c.clear.forEach((d) => dispatch({ type: "clear", dim: d }))}>
                    {c.label}
                  </button>
                )}
              </span>
            ))}
            {mode.kind === "level" && <span className="drillpath__next">→ {LEVEL_LABEL[mode.level].toLowerCase()}</span>}
          </nav>
        </div>
      </div>

      <TimelineCard title="History and forecast" height={340} allowShipped />

      <div className="ex-grid">
        <div className="ex-grid__season"><SeasonalityCard /></div>
        <DemandProfileCard />
        <LifecycleCard />
      </div>

      {mode.kind === "series" ? <SeriesPanel sku={mode.sku} region={mode.region} /> : <DrillTable level={mode.level} />}
    </div>
  );
}
