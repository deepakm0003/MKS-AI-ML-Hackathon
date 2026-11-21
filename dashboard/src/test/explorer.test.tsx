import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Sparkline } from "../components/Sparkline";
import { crumbs, explorerMode } from "../explorer/drill";
import { DrillTable } from "../explorer/DrillTable";
import { seasonalityOption } from "../explorer/SeasonalityCard";
import { FilterProvider } from "../filters/FilterContext";
import { emptyFilters } from "../filters/model";
import { FUTURE } from "../router";
import { OPTIONS, stubFetch } from "./fixtures";

vi.mock("../charts/EChart", () => ({ EChart: ({ label }: { label: string }) => <div data-testid="echart">{label}</div> }));

describe("drill path", () => {
  it("picks the first unpinned level and switches to a single series once SKU and region are pinned", () => {
    expect(explorerMode(emptyFilters())).toEqual({ kind: "level", level: "family" });
    expect(explorerMode({ ...emptyFilters(), family: ["A"] })).toEqual({ kind: "level", level: "sku" });
    expect(explorerMode({ ...emptyFilters(), family: ["A", "B"] })).toEqual({ kind: "level", level: "family" });
    expect(explorerMode({ ...emptyFilters(), sku: ["S"] })).toEqual({ kind: "level", level: "family" });
    expect(explorerMode({ ...emptyFilters(), family: ["A"], sku: ["S"] })).toEqual({ kind: "level", level: "region" });
    expect(explorerMode({ ...emptyFilters(), sku: ["S"], region: ["Europe"] })).toEqual({ kind: "series", sku: "S", region: "Europe" });
  });

  it("builds breadcrumbs that clear everything deeper", () => {
    const c = crumbs({ ...emptyFilters(), family: ["Thermal"], sku: ["THM-001"] });
    expect(c.map((x) => x.label)).toEqual(["All products", "Thermal", "THM-001"]);
    expect(c[1].clear).toEqual(["sku", "region", "customer"]);
    expect(c[0].clear).toEqual(["family", "sku", "region", "customer"]);
  });
});

describe("seasonality option", () => {
  const v = {
    filters: {}, years: [{ year: "2025", kind: "history" as const, values: Array(12).fill(10) }, { year: "2027", kind: "forecast" as const, values: Array(12).fill(12) }],
    by_month: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, label: "x", hist_avg_units: 1, hist_index: i === 7 ? 0.8 : 1.1, forecast_units: 1, forecast_index: 1 })),
    stats: { peak_months: [], trough_month: null, amplitude: null, zero_month_share_24m: 0, series_with_30pct_zero_months: 0, series_observed_24m: 0, demand_classes: {}, median_order_cycle_months: 1 },
  };
  it("plots % vs an average month from a zero baseline", () => {
    const o = seasonalityOption(v, "profile") as { series: { data: (number | null)[] }[]; yAxis: { scale?: boolean } };
    expect(o.series[0].data[7]).toBe(-20);
    expect(o.series[0].data[0]).toBe(10);
    expect(o.yAxis.scale).toBeUndefined();               // bars start at zero
  });
  it("draws history years and dashed forecast years in the overlay", () => {
    const o = seasonalityOption(v, "years") as { series: { name: string; lineStyle: { type?: string } }[] };
    expect(o.series.map((s) => s.name)).toEqual(["2025", "2027 forecast"]);
    expect(o.series[1].lineStyle.type).toBe("dashed");
  });
});

describe("Sparkline", () => {
  it("draws history and a bridged forecast path", () => {
    const { container } = render(<Sparkline history={[1, 2, 3]} forecast={[4, 5]} />);
    const paths = container.querySelectorAll("path");
    expect(paths).toHaveLength(2);
    expect(paths[1].getAttribute("d")!.split("L")).toHaveLength(3);   // last actual + 2 forecast points
  });
});

function Probe() {
  const l = useLocation();
  return <output data-testid="loc">{decodeURIComponent(l.search).replace(/\+/g, " ")}</output>;
}

describe("DrillTable", () => {
  it("drills into a row by setting the global filter", async () => {
    const view = {
      level: "family", next_level: "sku", filters: {}, members: 1, spark_months: { history: [], forecast: [] },
      rows: [{ Member: "Thermal Management", Series: 413, Units_last12: 257000, Units_next12: 274000, Revenue_next12: 252e6,
        Units_change_pct: 6.7, Zero_share_24m: 0.155, spark_history: [1, 2], spark_forecast: [3] }],
    };
    vi.stubGlobal("fetch", vi.fn(stubFetch({ "/meta/filters": { body: OPTIONS }, "/views/drilldown": { body: view } }).fn));
    render(<MemoryRouter initialEntries={["/explorer"]} future={FUTURE}><FilterProvider><DrillTable level="family" /><Probe /></FilterProvider></MemoryRouter>);
    const row = await screen.findByRole("button", { name: "Drill into Thermal Management" });
    expect(screen.getByText("+6.7%")).toBeInTheDocument();
    expect(screen.getByText("16%")).toBeInTheDocument();
    await userEvent.click(row);
    await waitFor(() => expect(screen.getByTestId("loc")).toHaveTextContent("family=Thermal Management"));
  });
});
