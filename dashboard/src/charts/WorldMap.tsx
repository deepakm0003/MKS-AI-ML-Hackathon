/**
 * WorldMap — dark ECharts world map, fills its container 100% width × fixed height.
 * Mouse-wheel zoom, drag to pan, reset button, animated region bubbles.
 */
import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { MapChart, EffectScatterChart } from "echarts/charts";
import { GeoComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { CHART, STATUS } from "../theme/chart";

echarts.use([MapChart, EffectScatterChart, GeoComponent, TooltipComponent, CanvasRenderer]);

const REGION_COORDS: Record<string, [number, number]> = {
  "North America":        [-100,  44],
  "Latin America":        [ -60, -12],
  "Europe":               [  15,  54],
  "India":                [  80,  22],
  "Asia Pacific":         [ 128,  30],
  "Middle East & Africa": [  38,   6],
};

const SHORT: Record<string, string> = {
  "Middle East & Africa": "ME & Africa",
  "Asia Pacific":         "Asia Pac.",
  "Latin America":        "Lat. Am.",
  "North America":        "N. Am.",
  "Europe":               "Europe",
  "India":                "India",
};

export interface RegionData {
  region: string;
  value: number;
  riskScore: number; // 0–1
  label?: string;
}

function riskColor(s: number) {
  if (s >= 0.65) return STATUS.serious;
  if (s >= 0.35) return STATUS.warning;
  return STATUS.good;
}

let mapRegistered = false;
async function ensureMap(): Promise<boolean> {
  if (mapRegistered) return true;
  try {
    const [topoMod, worldRaw] = await Promise.all([
      import("topojson-client"),
      import("world-atlas/countries-110m.json"),
    ]);
    const topo  = topoMod as typeof import("topojson-client");
    const world = worldRaw as unknown as TopoJSON.Topology;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const geo = topo.feature(world, (world.objects as any).countries) as unknown as GeoJSON.FeatureCollection;
    echarts.registerMap("world", geo as Parameters<typeof echarts.registerMap>[1]);
    mapRegistered = true;
    return true;
  } catch { return false; }
}

export function WorldMap({ regions, height = 340, title }: {
  regions: RegionData[];
  height?: number;
  title?: string;
}) {
  const wrapRef  = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const [ready,  setReady]  = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    ensureMap().then((ok) => ok ? setReady(true) : setFailed(true));
  }, []);

  const resetZoom = () => {
    chartRef.current?.setOption({ geo: { center: [20, 20], zoom: 1.1 } });
  };

  useEffect(() => {
    if (!ready || !wrapRef.current) return;

    // Init on the wrapper div itself — it already has the right size
    const chart = echarts.init(wrapRef.current, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(wrapRef.current);

    const bubbles = regions
      .filter((r) => REGION_COORDS[r.region])
      .map((r) => ({
        name: r.region,
        value: [...REGION_COORDS[r.region], r.value],
        _risk: r.riskScore,
        _label: r.label ?? "",
        itemStyle: {
          color: riskColor(r.riskScore),
          shadowBlur: 8,
          shadowColor: riskColor(r.riskScore) + "55",
        },
      }));

    chart.setOption({
      backgroundColor: "transparent",

      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(22,27,34,0.96)",
        borderColor: "#30363d",
        borderWidth: 1,
        textStyle: { color: "#f0f6fc", fontSize: 12 },
        padding: [10, 14],
        formatter(p: { name: string; data?: { _risk: number; _label: string } }) {
          if (!p.data) return p.name;
          const pct   = Math.round((p.data._risk ?? 0) * 100);
          const color = riskColor(p.data._risk ?? 0);
          return [
            `<b style="font-size:13px">${p.name}</b>`,
            p.data._label ? `<div style="color:#8b949e;font-size:11px;margin-top:4px">${p.data._label}</div>` : "",
            `<div style="margin-top:4px">Risk: <b style="color:${color}">${pct}%</b></div>`,
          ].join("");
        },
      },

      geo: {
        map: "world",
        roam: true,            // scroll = zoom, drag = pan
        // Key: use pixel offsets so the map fills exactly the canvas
        left: 0, right: 0, top: 0, bottom: 0,
        // Initial view — centred on populated world, zoom slightly past 1 to crop poles
        center: [20, 20],
        zoom: 1.1,
        scaleLimit: { min: 0.8, max: 20 },
        itemStyle: {
          areaColor: "#1c2128",
          borderColor: "#2d333b",
          borderWidth: 0.5,
        },
        emphasis: {
          itemStyle: { areaColor: "#22272e" },
          label: { show: false },
        },
        label: { show: false },
      },

      series: [{
        type: "effectScatter",
        coordinateSystem: "geo",
        data: bubbles,
        symbolSize: 12,
        showEffectOn: "render",
        rippleEffect: { brushType: "stroke", scale: 2.5, period: 3.5 },
        label: {
          show: true,
          position: "bottom",
          distance: 5,
          fontSize: 10,
          fontWeight: 600,
          color: CHART.text,
          formatter: (p: { name: string }) => SHORT[p.name] ?? p.name,
        },
        zlevel: 2,
      }],
    });

    return () => { ro.disconnect(); chart.dispose(); chartRef.current = null; };
  }, [ready, regions]);

  if (failed) return null;

  if (!ready) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
        <span className="spinner" aria-hidden />
        <span style={{ fontSize: 13, color: "var(--text-3)" }}>Loading map…</span>
      </div>
    );
  }

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      {/* The chart mounts here — full width × exact height, zero padding */}
      <div
        ref={wrapRef}
        style={{ position: "absolute", inset: 0 }}
        role="img"
        aria-label={title ?? "World map showing regional risk"}
      />

      {/* Reset zoom */}
      <button type="button" onClick={resetZoom}
        style={{
          position: "absolute", top: 8, right: 8, zIndex: 10,
          width: 26, height: 26, borderRadius: 6,
          background: "rgba(22,27,34,0.85)", border: "1px solid #30363d",
          color: "#8b949e", fontSize: 14, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}
        title="Reset zoom"
      >⟳</button>

      {/* Legend */}
      <div style={{
        position: "absolute", bottom: 8, left: 8, zIndex: 10,
        display: "flex", gap: 10, fontSize: 11, color: "#8b949e",
        background: "rgba(13,17,23,0.8)", padding: "4px 10px", borderRadius: 6,
        pointerEvents: "none",
      }}>
        {([
          { label: "Low",    color: STATUS.good },
          { label: "Medium", color: STATUS.warning },
          { label: "High",   color: STATUS.serious },
        ] as const).map((l) => (
          <span key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: l.color, display: "inline-block" }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}
