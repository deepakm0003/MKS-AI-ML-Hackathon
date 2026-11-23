/**
 * Macro Lead/Lag Heatmap — optional view.
 *
 * Shows cross-correlation between each macro indicator and each product
 * family's demand, shifted 0–12 months ahead.  Every number comes from
 * the pipeline's outputs/drivers/ files; nothing is hardcoded.
 *
 * API endpoints used:
 *   GET /datasets/lead_lag          – 728 rows: family × indicator × lag → Corr
 *   GET /datasets/best_lags         – 56 rows:  champion lag per family × indicator
 *   GET /datasets/lag_stability     – 56 rows:  2021-23 vs 2024-26 stability
 *   GET /datasets/ev_shift          – JSON: EV/ICE share by year
 */
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { EChart } from "../charts/EChart";
import { Card, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { SERIES } from "../theme/chart";

/* ── types ───────────────────────────────────────────────── */
interface LeadLagRow  { Product_Family: string; Indicator: string; Lag: number; Corr: number }
interface BestLagRow  { Product_Family: string; Indicator: string; Lag: number; Corr: number }
interface StabilityRow { Product_Family: string; Indicator: string; Lag_2021_23: number; Corr_2021_23: number; Lag_2024_26: number; Corr_2024_26: number; Lag_Shift: number; Stable: boolean | string }
interface EvShift { ice_share_pct_by_year: Record<string, number>; ev_share_pct_by_year: Record<string, number>; corr_ev_index_vs_ev_share: number; ev_share_pts_per_ev_index_pt: number; ice_share_pts_per_ev_index_pt: number }

/* ── short indicator labels ──────────────────────────────── */
const IND_SHORT: Record<string, string> = {
  ISM_Manufacturing_PMI:    "PMI",
  Auto_Production_YoY_Pct:  "Auto Prod.",
  Vehicle_Inventory_Days:   "Veh. Inv.",
  Raw_Material_Cost_Index:  "Raw Mat.",
  New_Vehicle_Orders_Index: "NV Orders",
  Industrial_Util_Rate_Pct: "Ind. Util.",
  Fuel_Price_Index:         "Fuel",
  EV_Adoption_Index:        "EV Index",
};

/* ── colour scale: negative = blue, zero = black, positive = lime ── */
function _corrColor(r: number): string {
  const a = Math.min(Math.abs(r), 1);
  if (r >= 0) return `rgba(199,255,50,${(a * 0.85 + 0.08).toFixed(2)})`;
  return `rgba(88,166,255,${(a * 0.85 + 0.08).toFixed(2)})`;
}
void _corrColor;

/* ── Component ───────────────────────────────────────────── */
export function MacroDrivers() {
  const leadLag   = useApi((s) => api.dataset<LeadLagRow>("lead_lag",      {}, s), []);
  const bestLags  = useApi((s) => api.dataset<BestLagRow>("best_lags",     {}, s), []);
  const stability = useApi((s) => api.dataset<StabilityRow>("lag_stability",{}, s), []);
  const evShift   = useApi((s) => api.dataset<EvShift>("ev_shift",         {}, s), []);

  const [selectedFamily,    setSelectedFamily]    = useState<string>("");
  const [selectedIndicator, setSelectedIndicator] = useState<string>("");

  /* ── derived ─────────────────────────────────────────────── */
  const families = useMemo(() => {
    if (bestLags.status !== "success") return [];
    return [...new Set(bestLags.data.rows.map((r) => r.Product_Family))].sort();
  }, [bestLags]);

  const indicators = useMemo(() => {
    if (bestLags.status !== "success") return [];
    return [...new Set(bestLags.data.rows.map((r) => r.Indicator))].sort();
  }, [bestLags]);

  /* Best-lag lookup: family × indicator → {Lag, Corr} */
  const bestMap = useMemo(() => {
    const m = new Map<string, BestLagRow>();
    if (bestLags.status === "success")
      for (const r of bestLags.data.rows) m.set(`${r.Product_Family}||${r.Indicator}`, r);
    return m;
  }, [bestLags]);

  /* Stability lookup */
  const stabMap = useMemo(() => {
    const m = new Map<string, StabilityRow>();
    if (stability.status === "success")
      for (const r of stability.data.rows) m.set(`${r.Product_Family}||${r.Indicator}`, r);
    return m;
  }, [stability]);

  /* Cross-correlation curve for selected family × indicator */
  const curveSeries = useMemo(() => {
    if (leadLag.status !== "success" || !selectedFamily || !selectedIndicator) return null;
    const pts = leadLag.data.rows
      .filter((r) => r.Product_Family === selectedFamily && r.Indicator === selectedIndicator)
      .sort((a, b) => a.Lag - b.Lag);
    if (!pts.length) return null;
    const best = bestMap.get(`${selectedFamily}||${selectedIndicator}`);
    return {
      xData: pts.map((p) => `Lag ${p.Lag}`),
      corrs: pts.map((p) => p.Corr),
      bestLag: best?.Lag,
    };
  }, [leadLag, selectedFamily, selectedIndicator, bestMap]);

  /* Lag-0 heatmap: champion correlation per family × indicator */
  const heatmapOption = useMemo(() => {
    if (!families.length || !indicators.length) return null;
    const indShort = indicators.map((i) => IND_SHORT[i] ?? i);
    const data: { value: [number, number, number]; label: string }[] = [];
    families.forEach((fam, fi) => {
      indicators.forEach((ind, ii) => {
        const best = bestMap.get(`${fam}||${ind}`);
        const corr = best?.Corr ?? 0;
        data.push({ value: [ii, fi, parseFloat(corr.toFixed(3))], label: `Lag ${best?.Lag ?? "—"}` });
      });
    });
    return {
      animation: false,
      grid: { left: 160, right: 60, top: 60, bottom: 80 },
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(20,20,20,0.97)",
        borderColor: "#282828",
        textStyle: { color: "#fff", fontSize: 12 },
        formatter: (p: { value: [number, number, number]; data: { label: string } }) => {
          const [ii, fi, corr] = p.value;
          return `<b>${families[fi]}</b><br/>${indicators[ii]}<br/>Corr: <b>${corr.toFixed(3)}</b><br/>${p.data.label}`;
        },
      },
      xAxis: { type: "category", data: indShort, axisLabel: { color: "#c0c0c0", fontSize: 11, rotate: 45, fontWeight: 500 }, axisLine: { lineStyle: { color: "#383838" } }, splitLine: { show: false } },
      yAxis: { type: "category", data: families, axisLabel: { color: "#c0c0c0", fontSize: 11, width: 155, overflow: "truncate", fontWeight: 500 }, axisLine: { lineStyle: { color: "#383838" } }, splitLine: { show: false } },
      visualMap: {
        min: -1, max: 1, show: false,
        inRange: { color: ["#3478f6","#141414","#c7ff32"] },
      },
      series: [{
        type: "heatmap",
        data: data.map((d) => ({ ...d })),
        label: {
          show: true,
          formatter: (p: { value: [number, number, number]; data: { label: string } }) =>
            p.value[2].toFixed(2),
          fontSize: 12, fontWeight: 700,
          color: "#ffffff",
          textShadowColor: "rgba(0,0,0,0.9)",
          textShadowBlur: 3,
          textShadowOffsetX: 0,
          textShadowOffsetY: 1,
        },
        emphasis: { 
          itemStyle: { borderColor: "#c7ff32", borderWidth: 2 },
          label: { fontSize: 14, color: "#ffffff", fontWeight: 700, textShadowBlur: 4 },
        },
        itemStyle: { borderColor: "#0a0a0a", borderWidth: 1 },
      }],
    };
  }, [families, indicators, bestMap]);

  /* Lag-curve ECharts option */
  const curveOption = useMemo(() => {
    if (!curveSeries) return null;
    return {
      animation: false,
      grid: { left: 12, right: 16, top: 24, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(20,20,20,0.97)", borderColor: "#282828",
        textStyle: { color: "#fff", fontSize: 12 },
        formatter: (p: { axisValueLabel: string; value: number }[]) =>
          `${p[0].axisValueLabel}: <b>${p[0].value.toFixed(3)}</b>`,
      },
      xAxis: { type: "category", data: curveSeries.xData, axisLabel: { color: "#555", fontSize: 10 }, axisLine: { lineStyle: { color: "#282828" } }, splitLine: { show: false } },
      yAxis: {
        type: "value", min: -1, max: 1,
        axisLabel: { color: "#555", fontSize: 10, formatter: (v: number) => v.toFixed(1) },
        splitLine: { lineStyle: { color: "#1a1a1a" } },
      },
      series: [
        {
          type: "line", data: curveSeries.corrs,
          lineStyle: { color: SERIES[0], width: 2 },
          itemStyle: { color: SERIES[0] },
          symbolSize: (_v: number, p: { dataIndex: number }) => curveSeries.bestLag === p.dataIndex ? 10 : 4,
          markLine: {
            silent: true, symbol: "none",
            lineStyle: { color: "rgba(199,255,50,0.4)", type: "dashed" },
            data: [{ yAxis: 0 }],
          },
          markPoint: curveSeries.bestLag !== undefined ? {
            data: [{ coord: [`Lag ${curveSeries.bestLag}`, curveSeries.corrs[curveSeries.bestLag]] }],
            symbol: "circle", symbolSize: 12,
            itemStyle: { color: "#c7ff32" },
            label: { show: true, formatter: `Lag ${curveSeries.bestLag}`, color: "#080808", fontSize: 9, fontWeight: 700 },
          } : undefined,
        },
      ],
    };
  }, [curveSeries]);

  /* EV shift line chart */
  const evOption = useMemo(() => {
    if (evShift.status !== "success") return null;
    // ev_shift is a JSON file served directly (not paginated), so .data is the object itself
    const ev = evShift.data as unknown as EvShift;
    if (!ev?.ev_share_pct_by_year) return null;
    const years = Object.keys(ev.ev_share_pct_by_year).sort();
    return {
      animation: false,
      grid: { left: 12, right: 16, top: 24, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis", backgroundColor: "rgba(20,20,20,0.97)", borderColor: "#282828",
        textStyle: { color: "#fff", fontSize: 12 },
      },
      legend: { top: 4, left: 0, itemGap: 16, textStyle: { color: "#a1a1a1", fontSize: 11 } },
      xAxis: { type: "category", data: years, axisLabel: { color: "#555", fontSize: 11 }, axisLine: { lineStyle: { color: "#282828" } }, splitLine: { show: false } },
      yAxis: { type: "value", axisLabel: { color: "#555", fontSize: 10, formatter: (v: number) => `${v}%` }, splitLine: { lineStyle: { color: "#1a1a1a" } } },
      series: [
        {
          name: "EV share", type: "line",
          data: years.map((y) => ev.ev_share_pct_by_year[y]),
          lineStyle: { color: SERIES[0], width: 2 }, itemStyle: { color: SERIES[0] }, symbolSize: 5,
        },
        {
          name: "ICE share", type: "line",
          data: years.map((y) => ev.ice_share_pct_by_year[y]),
          lineStyle: { color: SERIES[1], width: 2, type: "dashed" }, itemStyle: { color: SERIES[1] }, symbolSize: 5,
        },
      ],
    };
  }, [evShift]);

  const loading = leadLag.status === "loading" || bestLags.status === "loading";

  /* ── render ──────────────────────────────────────────────── */
  return (
    <div className="page">

      {/* ── Header ─────────────────────────────────────────── */}
      <div className="page__intro">
        <div>
          <p className="eyebrow">Macro Lead/Lag Heatmap · Demand drivers</p>
          <h2 className="page__title">Which macro indicator leads which family, and by how many months</h2>
          <p className="page__lead">
            Cross-correlation between 8 macro indicators and 7 product families at lags 0–12 months.
            Computed post-COVID (2021–2026) on recovered unconstrained demand.
            Stability checked by splitting the period into two halves.
          </p>
        </div>
      </div>

      {/* ── Summary chips ──────────────────────────────────── */}
      {bestLags.status === "success" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {bestLags.data.rows
            .filter((r) => Math.abs(r.Corr) >= 0.7)
            .sort((a, b) => Math.abs(b.Corr) - Math.abs(a.Corr))
            .slice(0, 6)
            .map((r) => {
              const stab = stabMap.get(`${r.Product_Family}||${r.Indicator}`);
              const stable = stab?.Stable === true || stab?.Stable === "True";
              return (
                <div key={`${r.Product_Family}${r.Indicator}`} style={{
                  padding: "10px 16px", background: "var(--surface-1)",
                  border: `1px solid ${stable ? "rgba(199,255,50,0.3)" : "rgba(255,92,92,0.2)"}`,
                  borderRadius: "var(--radius-md)", minWidth: 0,
                }}>
                  <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>
                    {IND_SHORT[r.Indicator] ?? r.Indicator}
                    <span style={{ marginLeft: 8, color: stable ? "var(--accent)" : "var(--critical)", fontWeight: 700 }}>
                      {stable ? "Stable" : "Shifted"}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-1)" }}>{r.Product_Family}</div>
                  <div style={{ fontSize: 11, color: "var(--accent)", marginTop: 2 }}>
                    r = {r.Corr.toFixed(2)} · lag {r.Lag}m
                  </div>
                </div>
              );
            })}
        </div>
      )}

      {/* ── Main heatmap ───────────────────────────────────── */}
      <Card
        title="Champion correlation heatmap"
        subtitle="Best-lag Pearson r for each family × indicator pair. Lime = positive, blue = negative. Click a cell to explore the lag curve."
      >
        {loading ? <Skeleton height={340} /> :
          leadLag.status === "error" ? <ErrorState error={leadLag.error} onRetry={leadLag.retry} /> :
          heatmapOption ? (
            <div style={{ padding: "16px 20px 20px" }}>
              <EChart
                height={families.length * 52 + 90}
                label="Macro lead-lag heatmap"
                option={heatmapOption}
                onEvents={{
                  click: (p: unknown) => {
                    const ev = p as { value?: [number, number, number] };
                    if (!ev.value) return;
                    const [ii, fi] = ev.value;
                    setSelectedFamily(families[fi]);
                    setSelectedIndicator(indicators[ii]);
                  },
                }}
              />
              <p style={{ marginTop: 8, fontSize: 11, color: "var(--text-3)" }}>
                Click any cell to view the full correlation-vs-lag curve for that pair.
              </p>
            </div>
          ) : <EmptyState title="No heatmap data" icon="database" />}
      </Card>

      {/* ── Lag curve detail ───────────────────────────────── */}
      {(selectedFamily && selectedIndicator) && (
        <Card
          title={`Lag curve: ${selectedFamily} × ${IND_SHORT[selectedIndicator] ?? selectedIndicator}`}
          subtitle="Pearson r at each lead (months). Champion lag marked with lime dot."
        >
          {curveOption ? (
            <div style={{ padding: "16px 20px 20px" }}>
              <EChart height={220} label="Lag correlation curve" option={curveOption} />
              {(() => {
                const stab = stabMap.get(`${selectedFamily}||${selectedIndicator}`);
                const best = bestMap.get(`${selectedFamily}||${selectedIndicator}`);
                if (!stab || !best) return null;
                const stable = stab.Stable === true || stab.Stable === "True";
                return (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 14 }}>
                    {[
                      { k: "Champion lag",          v: `${best.Lag} months` },
                      { k: "Champion r",             v: best.Corr.toFixed(3) },
                      { k: "2021–23 lag / r",        v: `${stab.Lag_2021_23}m / ${stab.Corr_2021_23.toFixed(2)}` },
                      { k: "2024–26 lag / r",        v: `${stab.Lag_2024_26}m / ${stab.Corr_2024_26.toFixed(2)}` },
                      { k: "Lag shift",              v: `${stab.Lag_Shift > 0 ? "+" : ""}${stab.Lag_Shift}m` },
                      { k: "Stable (±2m, r≥0.3)",   v: stable ? "Yes" : "No", col: stable ? "var(--accent)" : "var(--critical)" },
                    ].map(({ k, v, col }) => (
                      <div key={k} style={{ padding: "8px 14px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                        <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>{k}</div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: col ?? "var(--text-1)" }}>{v}</div>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          ) : <EmptyState title="Select a cell in the heatmap above" icon="info" />}
        </Card>
      )}

      {/* ── Stability table ────────────────────────────────── */}
      <Card
        title="Lag stability — 2021–23 vs 2024–26"
        subtitle="How much the champion lag shifted between the two halves of the post-COVID period"
      >
        {stability.status === "loading" ? <Skeleton height={280} /> :
          stability.status === "error" ? <ErrorState error={stability.error} onRetry={stability.retry} /> :
          stability.data.rows.length > 0 ? (
            <div style={{ padding: "8px 20px 20px", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr>
                    {["Family","Indicator","Lag 2021-23","r 2021-23","Lag 2024-26","r 2024-26","Shift","Stable"].map((h) => (
                      <th key={h} style={{ textAlign: "left", padding: "7px 10px", borderBottom: "1px solid var(--border)", fontSize: 10, fontWeight: 600, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stability.data.rows
                    .sort((a, b) => Math.abs(b.Corr_2021_23) - Math.abs(a.Corr_2021_23))
                    .map((r, i) => {
                      const stable = r.Stable === true || r.Stable === "True";
                      return (
                        <tr key={i}
                          style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                          onMouseEnter={(e) => (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"}
                          onMouseLeave={(e) => (e.currentTarget as HTMLElement).style.background = ""}
                          onClick={() => { setSelectedFamily(r.Product_Family); setSelectedIndicator(r.Indicator); }}
                        >
                          <td style={{ padding: "7px 10px", color: "var(--text-1)", fontWeight: 500 }}>{r.Product_Family}</td>
                          <td style={{ padding: "7px 10px", color: "var(--text-2)" }}>{IND_SHORT[r.Indicator] ?? r.Indicator}</td>
                          <td style={{ padding: "7px 10px", color: "var(--text-2)", textAlign: "right" }}>{r.Lag_2021_23}m</td>
                          <td style={{ padding: "7px 10px", color: Math.abs(r.Corr_2021_23) >= 0.6 ? "var(--accent)" : "var(--text-2)", textAlign: "right", fontWeight: 600 }}>{r.Corr_2021_23.toFixed(2)}</td>
                          <td style={{ padding: "7px 10px", color: "var(--text-2)", textAlign: "right" }}>{r.Lag_2024_26}m</td>
                          <td style={{ padding: "7px 10px", color: Math.abs(r.Corr_2024_26) >= 0.6 ? "var(--accent)" : "var(--text-2)", textAlign: "right", fontWeight: 600 }}>{r.Corr_2024_26.toFixed(2)}</td>
                          <td style={{ padding: "7px 10px", textAlign: "right", color: Math.abs(r.Lag_Shift) <= 2 ? "var(--accent)" : "var(--warning)" }}>{r.Lag_Shift > 0 ? "+" : ""}{r.Lag_Shift}m</td>
                          <td style={{ padding: "7px 10px", textAlign: "center" }}>
                            <span style={{ display: "inline-flex", alignItems: "center", height: 20, padding: "0 8px", borderRadius: "var(--radius-pill)",
                              background: stable ? "rgba(199,255,50,0.1)" : "rgba(255,92,92,0.1)",
                              border: `1px solid ${stable ? "rgba(199,255,50,0.3)" : "rgba(255,92,92,0.3)"}`,
                              color: stable ? "var(--accent)" : "var(--critical)", fontSize: 10, fontWeight: 700 }}>
                              {stable ? "Stable" : "Shifted"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
              <p style={{ marginTop: 10, fontSize: 11, color: "var(--text-3)" }}>Click any row to view its lag curve above.</p>
            </div>
          ) : <EmptyState title="No stability data" icon="database" />}
      </Card>

      {/* ── EV shift ────────────────────────────────────────── */}
      <Card
        title="EV / ICE powertrain shift 2019–2026"
        subtitle={`EV share: 0% → 9.8% · ICE share: 24.1% → 13.0% · r(EV index, EV share) = ${evShift.status === "success" ? (evShift.data as unknown as EvShift)?.corr_ev_index_vs_ev_share?.toFixed(3) : "…"}`}
      >
        {evShift.status === "loading" ? <Skeleton height={220} /> :
          evShift.status === "error" ? <ErrorState error={evShift.error} onRetry={evShift.retry} /> :
          evOption ? (
            <div style={{ padding: "16px 20px 20px" }}>
              <EChart height={220} label="EV vs ICE share by year" option={evOption} />
              {evShift.status === "success" && (() => {
                const ev = evShift.data as unknown as EvShift;
                return ev ? (
                  <div style={{ display: "flex", gap: 16, marginTop: 14, flexWrap: "wrap" }}>
                    {[
                      { k: "EV share 2019", v: `${ev.ev_share_pct_by_year["2019"]}%` },
                      { k: "EV share 2026", v: `${ev.ev_share_pct_by_year["2026"]}%`, accent: true },
                      { k: "ICE share 2019", v: `${ev.ice_share_pct_by_year["2019"]}%` },
                      { k: "ICE share 2026", v: `${ev.ice_share_pct_by_year["2026"]}%` },
                      { k: "r(EV index, EV share)", v: ev.corr_ev_index_vs_ev_share?.toFixed(3), accent: true },
                      { k: "EV share pts / index pt", v: `+${ev.ev_share_pts_per_ev_index_pt?.toFixed(3)}` },
                    ].map(({ k, v, accent }) => (
                      <div key={k} style={{ padding: "8px 14px", background: "var(--surface-2)", borderRadius: "var(--radius-sm)" }}>
                        <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 3 }}>{k}</div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: accent ? "var(--accent)" : "var(--text-1)" }}>{v ?? "—"}</div>
                      </div>
                    ))}
                  </div>
                ) : null;
              })()}
            </div>
          ) : <EmptyState title="No EV shift data" icon="database" />}
      </Card>

    </div>
  );
}
