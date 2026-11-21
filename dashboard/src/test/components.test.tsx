import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { ChartCard } from "../components/ChartCard";
import { DataTable } from "../components/DataTable";
import { KpiTile } from "../components/KpiTile";
import { FilterProvider } from "../filters/FilterContext";
import { FUTURE } from "../router";
import { OPTIONS, stubFetch } from "./fixtures";

// canvas charts do not run in jsdom - replace the chart with a labelled stand-in
vi.mock("../charts/EChart", () => ({ EChart: ({ label }: { label: string }) => <div data-testid="echart">{label}</div> }));

describe("KpiTile", () => {
  it("shows a skeleton while loading and never a placeholder number", () => {
    const { container } = render(<KpiTile label="Revenue" loading value="$1.61B" />);
    expect(screen.queryByText("$1.61B")).toBeNull();
    expect(container.querySelector(".skeleton")).not.toBeNull();
  });

  it("renders value, unit and a delta with arrow and tone", () => {
    const { container } = render(
      <KpiTile label="Demand" value="1.81M" unit="units" delta={{ text: "+6.1% vs last 12 m", trend: "up", goodWhen: "up" }} />,
    );
    expect(screen.getByText("1.81M")).toBeInTheDocument();
    expect(screen.getByText("units")).toBeInTheDocument();
    expect(container.querySelector(".kpi__delta--good")).toHaveTextContent("+6.1% vs last 12 m");
    expect(container.querySelector(".kpi__delta svg")).not.toBeNull();
  });

  it("marks an increase as bad when lower is better, and shows a dash for missing values", () => {
    const { container } = render(<KpiTile label="Risk" value={undefined} delta={{ text: "+3", trend: "up", goodWhen: "down" }} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(container.querySelector(".kpi__delta--critical")).not.toBeNull();
  });
});

describe("DataTable", () => {
  const rows = [{ n: "Europe", v: 3 }, { n: "India", v: 9 }, { n: "Mexico", v: 1 }];
  const cols = [
    { key: "n", label: "Name", value: (r: typeof rows[0]) => r.n },
    { key: "v", label: "Value", value: (r: typeof rows[0]) => r.v, align: "right" as const },
  ];
  it("sorts by a column and toggles direction", async () => {
    render(<DataTable columns={cols} rows={rows} initialSort={{ key: "v", dir: "desc" }} />);
    const firstCells = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);
    expect(firstCells()).toEqual(["India", "Europe", "Mexico"]);
    await userEvent.click(screen.getByRole("button", { name: /Value/ }));
    expect(firstCells()).toEqual(["Mexico", "Europe", "India"]);
  });
});

describe("ChartCard", () => {
  const ok = { status: "success" as const, data: [1, 2, 3], error: undefined };
  it("switches between the chart and its table view", async () => {
    render(<ChartCard title="Demo" state={ok} chart={() => <div>CHART</div>} table={(d) => <div>TABLE {d.length}</div>}
      footnote={() => "source: test"} />);
    expect(screen.getByText("CHART")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Table" }));
    expect(screen.getByText("TABLE 3")).toBeInTheDocument();
    expect(screen.getByText("source: test")).toBeInTheDocument();
  });

  it("shows the empty and error states instead of a chart", () => {
    const { rerender } = render(<ChartCard title="Demo" state={ok} isEmpty={() => true} chart={() => <div>CHART</div>} table={() => null} />);
    expect(screen.getByText("No data for these filters")).toBeInTheDocument();
    const err = { status: "error" as const, data: undefined, error: new ApiError("boom", 500, "/views/timeline") };
    rerender(<ChartCard title="Demo" state={err} chart={() => <div>CHART</div>} table={() => null} />);
    expect(screen.getByText("Request failed (500)")).toBeInTheDocument();
    expect(screen.queryByText("CHART")).toBeNull();
  });
});

describe("TimelineCard (live hook, stubbed fetch)", () => {
  it("requests /views/timeline with the global filters and shows the band method", async () => {
    const { TimelineCard } = await import("../charts/TimelineCard");
    const view = {
      filters: { region: ["Europe"] }, band_method: "calibrated region band (aggregate error model)",
      summary: { series: 1, forecast_series: 1, history_end: "2026-10", units_last12: 1, units_next12: 1, revenue_last12: 1,
        revenue_next12: 1, units_19m: 1, units_19m_p10: 1, units_19m_p90: 1, revenue_19m: 1, units_next12_vs_last12: 0, revenue_next12_vs_last12: 0 },
      history: [{ Date: "2026-10", Units_shipped: 5, Units_unconstrained: 6, Revenue_shipped: 50, Revenue_unconstrained: 60 }],
      forecast: [{ Date: "2026-11", Units_forecast: 7, Revenue_forecast: 70, Units_P10: 6, Units_P90: 8, Revenue_P10: 60, Revenue_P90: 80 }],
    };
    const stub = stubFetch({ "/meta/filters": { body: OPTIONS }, "/views/timeline": { body: view } });
    vi.stubGlobal("fetch", vi.fn(stub.fn));
    render(<MemoryRouter initialEntries={["/system?region=Europe"]} future={FUTURE}><FilterProvider><TimelineCard /></FilterProvider></MemoryRouter>);
    expect(await screen.findByTestId("echart")).toBeInTheDocument();
    expect(screen.getByText(/calibrated region band/)).toBeInTheDocument();
    expect(stub.calls.some((c) => c.startsWith("/views/timeline?region=Europe"))).toBe(true);
    await userEvent.click(screen.getByRole("radio", { name: "Table" }));
    expect(screen.getByText("Nov 26")).toBeInTheDocument();
  });
});
