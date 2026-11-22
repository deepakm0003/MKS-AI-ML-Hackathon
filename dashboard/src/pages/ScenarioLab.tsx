import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ScenarioResult } from "../api/types";
import { useApi } from "../api/useApi";
import { EChart } from "../charts/EChart";
import { genericRankedBarsOption, verticalBarsOption } from "../charts/options";
import { KpiTile } from "../components/KpiTile";
import { Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fmtInt, fmtPctChange, fmtPctPoints, fmtUsd } from "../lib/format";
import { SERIES } from "../theme/chart";

const PRESET_LABELS: Record<string, string> = {
  "Base case": "Base case",
  Downside: "Downside",
  "Auto slowdown": "Auto slowdown",
  "PMI -3": "PMI −3",
  "Raw-material spike": "Raw-material spike",
  "EV acceleration": "EV acceleration",
  Upside: "Upside",
};

/** 05 Scenario Lab — change macro assumptions, see demand, revenue and planning risks respond. */
export function ScenarioLab() {
  const config = useApi((s) => api.scenarioConfig(s), []);
  const presets = useApi((s) => api.scenarioPresets(s), []);

  const [shocks, setShocks] = useState<Record<string, number>>({});
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [activePreset, setActivePreset] = useState<string>("");
  const abortRef = useRef<AbortController | null>(null);
  const hasInitialized = useRef(false);

  // Base shock values from config
  const baseShocks = useMemo(() => {
    if (config.status !== "success") return {};
    const base: Record<string, number> = {};
    for (const [key, sl] of Object.entries(config.data.sliders)) {
      base[key] = sl.kind === "add" ? 0 : 1;
    }
    return base;
  }, [config]);

  // Initialize sliders once when config loads
  useEffect(() => {
    if (config.status === "success" && !hasInitialized.current) {
      hasInitialized.current = true;
      setShocks(baseShocks);
      runScenario(baseShocks);
    }
  }, [config.status, baseShocks]); // eslint-disable-line react-hooks/exhaustive-deps

  // Run scenario with abort support
  const runScenario = useCallback(async (s: Record<string, number>) => {
    // Cancel any in-flight request
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const r = await api.scenario({ shocks: s }, ctrl.signal);
      if (!ctrl.signal.aborted) {
        setResult(r);
      }
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setError(e instanceof ApiError ? e : new ApiError(String(e), null, "/scenario"));
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, []);

  // Slider change — just update state, no auto-run
  const onSliderChange = useCallback((key: string, val: number) => {
    setShocks((prev) => ({ ...prev, [key]: val }));
    setActivePreset("");
  }, []);

  // Apply preset — immediately run
  const applyPreset = useCallback((name: string, presetShocks: Record<string, number>) => {
    setShocks(presetShocks);
    setActivePreset(name);
    runScenario(presetShocks);
  }, [runScenario]);

  // Charts from result
  const monthChart = useMemo(() => {
    if (!result?.by_month?.length) return null;
    const months = result.by_month.map((r) => r.Date);
    return verticalBarsOption(
      months,
      [
        { name: "Base", data: result.by_month.map((r) => r.Base), color: SERIES[4] },
        { name: "Scenario", data: result.by_month.map((r) => r.Scenario), color: SERIES[0] },
      ],
      { valueFormatter: (v) => fmtInt(v), rotateLabels: true, yAxisName: "Units" },
    );
  }, [result]);

  const familyChart = useMemo(() => {
    if (!result?.by_family?.length) return null;
    return genericRankedBarsOption(
      result.by_family.map((r) => ({ label: r.Product_Family, value: r.Change_pct, sub: String(r.Change_units) })),
      { valueFormatter: (v) => fmtPctPoints(v), subFormatter: (v) => fmtInt(v) + " units" },
    );
  }, [result]);

  const regionChart = useMemo(() => {
    if (!result?.by_region?.length) return null;
    return genericRankedBarsOption(
      result.by_region.map((r) => ({ label: r.Region, value: r.Change_pct, sub: String(r.Change_units) })),
      { valueFormatter: (v) => fmtPctPoints(v), subFormatter: (v) => fmtInt(v) + " units" },
    );
  }, [result]);

  // Cleanup on unmount
  useEffect(() => () => abortRef.current?.abort(), []);

  if (config.status === "loading") return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Scenario Lab · What-if analysis</p>
          <h2 className="page__title">Change macro assumptions, see demand respond</h2>
        </div>
      </div>
      <Skeleton height={400} />
    </div>
  );

  if (config.status === "error") return (
    <div className="page"><Card><ErrorState error={config.error} onRetry={config.retry} /></Card></div>
  );

  const cfg = config.data;
  const total = result?.total;

  return (
    <div className="page">
      <div className="page__intro">
        <div>
          <p className="eyebrow">Scenario Lab · What-if analysis</p>
          <h2 className="page__title">Change macro assumptions, see demand and revenue respond</h2>
          <p className="page__lead">
            Instant emulated re-forecast of the frozen model with shifted macro inputs.
            Company-wide; revenue at the announced 2027/2028 list prices.
          </p>
        </div>
      </div>

      {/* KPI row */}
      <section className="kpi-row" aria-label="Scenario totals">
        <KpiTile
          label="Base 19m demand" value={total ? fmtInt(total.base_units) : "—"} unit="units"
          sub="Frozen forecast at current macro inputs"
          footnote="No shocks applied"
        />
        <KpiTile
          label="Scenario 19m demand" emphasis="accent" loading={loading}
          value={total ? fmtInt(total.scenario_units) : "—"} unit="units"
          sub={total ? `${fmtUsd(total.scenario_revenue ?? 0, 1)} revenue` : undefined}
          footnote="With current shocks applied"
        />
        <KpiTile
          label="Change" emphasis={total && total.change_pct < 0 ? "critical" : "accent"} loading={loading}
          value={total ? fmtPctChange(total.change_pct / 100, 1) : "—"}
          sub={total ? `${total.change_units >= 0 ? "+" : ""}${fmtInt(total.change_units)} units` : undefined}
          footnote="Scenario vs base"
        />
        <KpiTile
          label="Revenue change" loading={loading}
          value={total && total.change_revenue != null ? fmtUsd(total.change_revenue, 1) : "—"}
          sub={total && total.change_revenue != null ? `${fmtPctChange(total.change_revenue / (total.base_revenue ?? 1) * 100, 1)}` : undefined}
          footnote="At announced list prices"
        />
      </section>

      {/* Controls + Presets */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Macro shock controls" subtitle="Adjust sliders, then click Run to see the scenario">
            <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 20 }}>
              {Object.entries(cfg.sliders).map(([key, sl]) => (
                <div key={key}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                    <label style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                      {key.replace(/_/g, " ")}
                      <span style={{ fontSize: 11, fontWeight: 400, color: "var(--text-3)", marginLeft: 6 }}>
                        {sl.kind === "add" ? `add ${sl.unit}` : `× ${sl.unit}`}
                      </span>
                    </label>
                    <span className="num" style={{ fontSize: 14, fontWeight: 600, color: "var(--accent)", fontFamily: "var(--font-mono)" }}>
                      {shocks[key] != null ? (sl.kind === "add" ? `${shocks[key] >= 0 ? "+" : ""}${shocks[key].toFixed(sl.unit === "%" ? 1 : 2)}${sl.unit}` : `${shocks[key].toFixed(2)}×`) : "—"}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={sl.min} max={sl.max} step={sl.kind === "add" ? (sl.unit === "%" ? 0.5 : 0.1) : 0.01}
                    value={shocks[key] ?? (sl.kind === "add" ? 0 : 1)}
                    onChange={(e) => onSliderChange(key, parseFloat(e.target.value))}
                    style={{ width: "100%", accentColor: "var(--accent)" }}
                  />
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-3)", marginTop: 2 }}>
                    <span>{sl.min}{sl.unit}</span>
                    <span>{sl.max}{sl.unit}</span>
                  </div>
                </div>
              ))}
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button type="button" className="btn btn--accent" disabled={loading || !Object.keys(shocks).length}
                  onClick={() => runScenario(shocks)}>
                  {loading ? "Running…" : "Run scenario"}
                </button>
                <button type="button" className="btn btn--ghost"
                  onClick={() => { setShocks(baseShocks); setActivePreset(""); runScenario(baseShocks); }}>
                  Reset to base
                </button>
              </div>
            </div>
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Preset scenarios" subtitle="Pre-configured macro shocks — click to apply">
            <div style={{ padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
              {Object.entries(cfg.presets).map(([name, presetShocks]) => (
                <button key={name} type="button"
                  className={`btn ${activePreset === name ? "btn--accent" : "btn--ghost"}`}
                  style={{ justifyContent: "space-between", width: "100%" }}
                  onClick={() => applyPreset(name, presetShocks)}>
                  <span>{PRESET_LABELS[name] ?? name}</span>
                  {presets.status === "success" && presets.data[name]?.total && (
                    <span className="num" style={{ fontSize: 12, fontWeight: 600,
                      color: presets.data[name].total.change_pct < 0 ? "var(--critical)" : "var(--good)" }}>
                      {fmtPctPoints(presets.data[name].total.change_pct)}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {error && <Card><ErrorState error={error} /></Card>}

      {/* Base vs Scenario by month */}
      {monthChart && (
        <Card title="Demand: base vs scenario by month" subtitle="19-month units, base case and current scenario">
          <div style={{ padding: "16px 20px 20px" }}>
            <EChart height={300} label="Base vs scenario demand by month" option={monthChart} />
          </div>
        </Card>
      )}

      {/* Impact by family + region */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Impact by product family" subtitle="Change % vs base, ranked">
            {familyChart ? (
              <div style={{ padding: "16px 20px 20px" }}>
                <EChart height={320} label="Scenario impact by product family" option={familyChart} />
              </div>
            ) : <EmptyState title="No family data" icon="database" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Impact by region" subtitle="Change % vs base, ranked">
            {regionChart ? (
              <div style={{ padding: "16px 20px 20px" }}>
                <EChart height={320} label="Scenario impact by region" option={regionChart} />
              </div>
            ) : <EmptyState title="No region data" icon="database" />}
          </Card>
        </div>
      </div>

      {/* Planning risks + responses */}
      <div className="ov-grid">
        <div className="ov-grid__main">
          <Card title="Planning risks triggered" subtitle="Capacity and supply risks exposed by this scenario">
            {result?.planning_risks?.length ? (
              <div style={{ padding: "8px 20px 20px" }}>
                <ul style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                  {result.planning_risks.map((r, i) => (
                    <li key={i} style={{
                      display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 16px",
                      borderRadius: 8, background: "var(--surface-2)", border: "1px solid var(--border)",
                    }}>
                      <span style={{ flexShrink: 0, width: 24, height: 24, borderRadius: "50%",
                        background: "var(--critical-soft)", color: "var(--critical)",
                        display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700 }}>
                        {i + 1}
                      </span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-1)" }}>{r.type}</div>
                        <div style={{ fontSize: 12, color: "var(--text-3)" }}>{r.scope}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : <EmptyState title="No planning risks" message="This scenario does not trigger capacity or supply risks." icon="check" />}
          </Card>
        </div>
        <div className="ov-grid__side">
          <Card title="Model responses" subtitle="What the emulator did with these shocks">
            {result?.responses?.length ? (
              <div style={{ padding: "12px 20px 20px" }}>
                <ul style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                  {result.responses.map((r, i) => (
                    <li key={i} style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.5,
                      paddingLeft: 16, borderLeft: "2px solid var(--accent-border)" }}>
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            ) : <EmptyState title="No responses" icon="info" />}
          </Card>
        </div>
      </div>

      {/* Capacity impact */}
      {result?.capacity?.length ? (
        <Card title="Capacity impact" subtitle="Utilisation by family × region under this scenario">
          <div style={{ padding: "16px 20px 20px" }}>
            <EChart height={280} label="Capacity utilization under scenario"
              option={verticalBarsOption(
                result.capacity.map((c) => `${c.Product_Family} · ${c.Region}`),
                [{ name: "Utilisation", data: result.capacity.map((c) => c.Utilisation_pct) }],
                { valueFormatter: (v) => `${v.toFixed(0)}%`, rotateLabels: true, showLabels: true, yAxisName: "%" },
              )} />
          </div>
        </Card>
      ) : null}
    </div>
  );
}
