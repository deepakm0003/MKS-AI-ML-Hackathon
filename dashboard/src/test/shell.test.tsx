import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { FUTURE } from "../router";
import { AppRoutes } from "../App";
import { formatModel, formatMonth } from "../layout/Header";
import { VIEWS } from "../routes";
import { BRIEFING, DATASETS, HEALTH, OPTIONS, stubFetch } from "./fixtures";

function LocationProbe() {
  const l = useLocation();
  return <output data-testid="location">{l.pathname + l.search}</output>;
}

function renderApp(path = "/", routes = {
  "/health": { body: HEALTH }, "/intelligence/briefing": { body: BRIEFING },
  "/meta/filters": { body: OPTIONS }, "/datasets": { body: DATASETS },
}) {
  const stub = stubFetch(routes);
  vi.stubGlobal("fetch", vi.fn(stub.fn));
  render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
  return stub;
}

describe("app shell", () => {
  it("redirects to the Executive Overview and lists every planned view", async () => {
    renderApp("/");
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/overview"));
    const nav = screen.getByRole("navigation");
    for (const v of VIEWS) expect(within(nav).getByText(v.label)).toBeInTheDocument();
    expect(within(nav).getByText("Data Health")).toBeInTheDocument();
    expect(within(nav).getByText("Anomaly Monitor")).toBeInTheDocument();
  });

  it("shows live backend status in the header", async () => {
    renderApp("/overview");
    expect(await screen.findByText("Validation PASS")).toBeInTheDocument();
    expect(screen.getByText("C9c · keep pull forward")).toBeInTheDocument();
    expect(screen.getByText("Oct 2026")).toBeInTheDocument();
  });

  it("navigates between views and keeps the global filters in the URL", async () => {
    renderApp("/overview?region=Europe");
    const nav = screen.getByRole("navigation");
    await userEvent.click(within(nav).getByText("Scenario Lab"));
    expect(screen.getByTestId("location")).toHaveTextContent("/scenarios?region=Europe");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Scenario Lab");
  });

  it("reports data readiness from GET /datasets without inventing values", async () => {
    renderApp("/overview");
    const table = await screen.findByRole("table");
    const row = (name: string) => within(table).getByText(name).closest("tr")!;
    expect(within(row("intelligence_report")).getByText("Available")).toBeInTheDocument();
    expect(within(row("timeline")).getByText("Not generated")).toBeInTheDocument();
    expect(within(row("mix")).getByText("Missing")).toBeInTheDocument();
  });

  it("shows explicit error states when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    render(<MemoryRouter initialEntries={["/overview"]} future={FUTURE}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByText("API offline")).toBeInTheDocument();
    expect((await screen.findAllByText("API unreachable")).length).toBeGreaterThan(0);
  });

  it("shows a not-generated state (503) distinctly from a crash", async () => {
    renderApp("/trust", {
      "/health": { body: HEALTH }, "/intelligence/briefing": { body: BRIEFING }, "/meta/filters": { body: OPTIONS },
      "/datasets": { status: 503, body: { detail: "manifest not generated yet - run the pipeline" } },
    } as never);
    expect(await screen.findByText("Data not generated yet")).toBeInTheDocument();
  });

  it("renders a not-found view for unknown routes", async () => {
    renderApp("/nope");
    expect(await screen.findByText("View not found")).toBeInTheDocument();
  });
});

describe("formatters", () => {
  it("formats model ids and months", () => {
    expect(formatModel("c9c_keep_pull_forward")).toBe("C9c · keep pull forward");
    expect(formatModel("champion")).toBe("Champion");
    expect(formatMonth("2026-10")).toBe("Oct 2026");
  });
});
