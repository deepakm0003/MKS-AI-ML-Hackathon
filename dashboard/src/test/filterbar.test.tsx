import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { FUTURE } from "../router";
import { FilterBar } from "../filters/FilterBar";
import { FilterProvider } from "../filters/FilterContext";
import { OPTIONS, stubFetch } from "./fixtures";

function LocationProbe() {
  const l = useLocation();
  const text = [...new URLSearchParams(l.search)].map(([k, v]) => `${k}=${v}`).join("&");
  return <output data-testid="location">{text}</output>;
}

function renderBar(path = "/overview") {
  vi.stubGlobal("fetch", vi.fn(stubFetch({ "/meta/filters": { body: OPTIONS } }).fn));
  render(
    <MemoryRouter initialEntries={[path]} future={FUTURE}>
      <FilterProvider>
        <FilterBar />
        <LocationProbe />
      </FilterProvider>
    </MemoryRouter>,
  );
}

const trigger = (label: string) => screen.getByRole("button", { name: new RegExp(`^${label}`) });

describe("global filter bar", () => {
  it("loads options from /meta/filters and shows the series count", async () => {
    renderBar();
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText(/of 4 series/)).toBeInTheDocument();
    expect(trigger("Product family")).toBeEnabled();
  });

  it("selecting a family updates the URL, the count and cascades the SKU list", async () => {
    renderBar();
    await waitFor(() => expect(trigger("Product family")).toBeEnabled());
    await userEvent.click(trigger("Product family"));
    await userEvent.click(screen.getByText("Thermal Management"));
    expect(screen.getByTestId("location")).toHaveTextContent("family=Thermal Management");
    expect(screen.getByText(/of 4 series/).textContent).toMatch(/^1 of 4 series/);

    await userEvent.keyboard("{Escape}");
    await userEvent.click(trigger("SKU"));
    const list = screen.getByRole("listbox", { name: "SKU" });
    expect(within(list).getAllByRole("option")).toHaveLength(1);
    expect(within(list).getByText("THM-001 · Radiator 12")).toBeInTheDocument();
  });

  it("search narrows options and Clear all resets every filter", async () => {
    renderBar("/overview?region=Europe&channel=Aftermarket");
    await waitFor(() => expect(trigger("Region")).toBeEnabled());
    expect(screen.getByRole("button", { name: /Clear all \(2\)/ })).toBeEnabled();

    await userEvent.click(trigger("Customer"));
    await userEvent.type(screen.getByLabelText("Search Customer"), "cre");
    expect(within(screen.getByRole("listbox", { name: "Customer" })).getAllByRole("option")).toHaveLength(1);
    await userEvent.keyboard("{Escape}");

    await userEvent.click(screen.getByRole("button", { name: /Clear all/ }));
    expect(screen.getByTestId("location")).toHaveTextContent(/^$/);
  });

  it("falls back to an error state with retry when filter options fail", async () => {
    vi.stubGlobal("fetch", vi.fn(stubFetch({}).fn));
    render(<MemoryRouter future={FUTURE}><FilterProvider><FilterBar /></FilterProvider></MemoryRouter>);
    expect(await screen.findByText("Request failed (404)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });
});
