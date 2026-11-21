import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { FilterProvider } from "../filters/FilterContext";
import { ExecutiveOverview } from "../pages/ExecutiveOverview";
import { FUTURE } from "../router";
import { OPTIONS, stubFetch } from "./fixtures";

vi.mock("../charts/EChart", () => ({ EChart: ({ label }: { label: string }) => <div data-testid="echart">{label}</div> }));

const SUMMARY = {
  series: 515, forecast_series: 514, history_end: "2026-10", units_last12: 509000, units_next12: 540000,
  revenue_last12: 278700000, revenue_next12: 308250000, units_19m: 540000 * 1.58, units_19m_p10: 501000, units_19m_p90: 617000,
  revenue_19m: 490160000, units_next12_vs_last12: 0.06, revenue_next12_vs_last12: 0.106,
};
const TIMELINE = {
  filters: { region: ["Europe"] }, band_method: "calibrated region band (aggregate error model)", summary: SUMMARY,
  history: [{ Date: "2026-10", Units_shipped: 1, Units_unconstrained: 1, Revenue_shipped: 1, Revenue_unconstrained: 1 }],
  forecast: [{ Date: "2026-11", Units_forecast: 1, Revenue_forecast: 1, Units_P10: 1, Units_P90: 1, Revenue_P10: 1, Revenue_P90: 1 }],
};
const card = (id: string, title: string, match: "direct" | "context") => ({
  id, priority: "CRITICAL", priority_score: 80, rule_id: "SUPPLY_RISK_ON_GROWING_DEMAND", title, level: "family_region",
  scope: "Precision Machined Parts | Europe", owner: "Procurement", finding: "PMP in Europe grows 7.2%.",
  action: "Raise safety stock.", trade_off: "Buffer cost.", window: "release now", confidence: "MEDIUM",
  impact_usd: 11500000, evidence: {}, match,
});
const RECS = { total: 3, direct: 2, by_priority: { CRITICAL: 3 },
  cards: [card("EX-0003", "Growing demand on a fragile supply base", "direct"), card("EX-0010", "Demand surge", "direct"),
    card("EX-0001", "Demand shifting from ICE to EV", "context")] };
const preset = (pct: number, rev: number) => ({ method: "exact", shocks: {}, total: { base_units: 1, scenario_units: 1, change_units: 1, change_pct: pct, change_revenue: rev }, by_family: [], by_region: [], planning_risks: [], responses: [] });
const PRESETS = { "Base case": preset(0, 0), Downside: preset(-6.88, -178.5e6), Upside: preset(4.86, 142.1e6), "PMI -3": preset(-2.33, -68.4e6) };
const BRIEF = { kpis: {}, briefing: [{ topic: "outlook", text: "Demand for the next 12 months is forecast at 1,808,156 units.", sources: ["forecast_detail"] }] };
const BREAKDOWN = { dim: "region", filters: {}, members: 1, rows: [{ Member: "Europe", Units_last12: 1, Revenue_last12: 1, Units_next12: 1, Revenue_next12: 1, Units_change_pct: 1, Revenue_change_pct: 1, Revenue_share_next12: 1 }] };

function renderOverview(path = "/overview?region=Europe") {
  const stub = stubFetch({
    "/meta/filters": { body: OPTIONS }, "/views/timeline": { body: TIMELINE }, "/intelligence/recommendations": { body: RECS },
    "/scenario/presets": { body: PRESETS }, "/intelligence/briefing": { body: BRIEF }, "/views/breakdown": { body: BREAKDOWN },
  });
  vi.stubGlobal("fetch", vi.fn(stub.fn));
  render(<MemoryRouter initialEntries={[path]} future={FUTURE}><FilterProvider><ExecutiveOverview /></FilterProvider></MemoryRouter>);
  return stub;
}

describe("Executive Overview", () => {
  it("answers the five-second questions from the filtered API data", async () => {
    const stub = renderOverview();
    const kpis = await screen.findByRole("region", { name: "Headline figures" });
    await waitFor(() => expect(within(kpis).getByText("$308.25M")).toBeInTheDocument());
    expect(within(kpis).getByText("853K")).toBeInTheDocument();                         // 19-month units
    expect(within(kpis).getByText("501K – 617K")).toBeInTheDocument();                  // P10-P90 range
    expect(within(kpis).getByText("+10.6% vs last 12 m")).toBeInTheDocument();
    expect(within(kpis).getByText("2")).toBeInTheDocument();                            // direct critical actions
    expect(within(kpis).getByText(/1 broader context items/)).toBeInTheDocument();
    expect(stub.calls.some((c) => c.startsWith("/intelligence/recommendations?region=Europe&priority=CRITICAL"))).toBe(true);
    expect(stub.calls.filter((c) => c.startsWith("/views/timeline")).length).toBe(1);   // shared by KPI row and both timelines
  });

  it("lists critical actions with expandable evidence and marks broader context", async () => {
    renderOverview();
    const first = await screen.findByText("Growing demand on a fragile supply base");
    expect(screen.getByText("· context", { exact: false })).toBeInTheDocument();
    await userEvent.click(first);
    expect(screen.getByText("PMP in Europe grows 7.2%.")).toBeInTheDocument();
    expect(screen.getByText("Raise safety stock.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /All exceptions/ })).toHaveAttribute("href", "/risk?region=Europe");
  });

  it("shows exact scenario impacts in a fixed order and flags the briefing as company-wide", async () => {
    renderOverview();
    const scen = (await screen.findByText("Macro scenario impact")).closest("section")!;
    await waitFor(() => expect(within(scen).getByText("Downside")).toBeInTheDocument());
    const names = within(scen).getAllByText(/^(Downside|PMI -3|Upside)$/).map((n) => n.textContent);
    expect(names).toEqual(["Downside", "PMI -3", "Upside"]);
    expect(within(scen).getByText("−6.9%")).toBeInTheDocument();
    expect(within(scen).queryByText("Base case")).toBeNull();
    expect(await screen.findByText("Company-wide")).toBeInTheDocument();
    expect(screen.getByText(/1,808,156 units/)).toBeInTheDocument();
  });
});
