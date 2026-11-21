import { describe, expect, it } from "vitest";
import {
  activeCount, applyAction, buildIndex, emptyFilters, fromSearchParams, matchingSeries, optionsFor, prune,
  toApiQuery, toSearchParams, totalSeries,
} from "../filters/model";
import { OPTIONS } from "./fixtures";

const idx = buildIndex(OPTIONS);

describe("filter model", () => {
  it("decodes index-encoded combinations", () => {
    expect(idx.rows).toHaveLength(4);
    expect(idx.rows[3]).toEqual({ family: "Thermal Management", sku: "THM-001", region: "North America", channel: "Direct OEM", customer: "Orion" });
    expect(totalSeries(idx)).toBe(4);
  });

  it("cascades: a family filter narrows the SKU options, counts are matching series", () => {
    const f = { ...emptyFilters(), family: ["Brake & Safety Systems"] };
    expect(optionsFor("sku", idx, f).map((o) => o.value)).toEqual(["BSS-001", "BSS-002"]);
    const regions = optionsFor("region", idx, f);
    expect(regions.find((o) => o.value === "Europe")?.count).toBe(2);
    expect(regions.find((o) => o.value === "North America")?.count).toBe(1);
    expect(matchingSeries(idx, f)).toBe(3);
  });

  it("a dimension's own selection does not restrict its own options (faceted)", () => {
    const f = { ...emptyFilters(), family: ["Thermal Management"] };
    expect(optionsFor("family", idx, f).map((o) => o.value)).toEqual(["Brake & Safety Systems", "Thermal Management"]);
  });

  it("labels SKUs with their description", () => {
    expect(optionsFor("sku", idx, emptyFilters())[0].label).toBe("BSS-001 · Brake caliper 25");
  });

  it("prunes selections that no longer match, keeping the dimension just edited", () => {
    const f = { ...emptyFilters(), sku: ["BSS-001", "THM-001"] };
    const next = applyAction(f, { type: "set", dim: "family", values: ["Thermal Management"] }, idx);
    expect(next.family).toEqual(["Thermal Management"]);
    expect(next.sku).toEqual(["THM-001"]);
    expect(prune({ ...emptyFilters(), region: ["Europe"], customer: ["Orion"] }, idx, "region").customer).toEqual([]);
  });

  it("toggle, clear and clearAll", () => {
    let f = applyAction(emptyFilters(), { type: "toggle", dim: "region", value: "Europe" });
    expect(f.region).toEqual(["Europe"]);
    f = applyAction(f, { type: "toggle", dim: "region", value: "Europe" });
    expect(f.region).toEqual([]);
    f = applyAction({ ...f, channel: ["Aftermarket"], region: ["Europe"] }, { type: "clear", dim: "channel" });
    expect(f.channel).toEqual([]);
    expect(activeCount(f)).toBe(1);
    expect(activeCount(applyAction(f, { type: "clearAll" }))).toBe(0);
  });

  it("round-trips through the URL, including '&' in names, and keeps unrelated params", () => {
    const f = { ...emptyFilters(), family: ["Brake & Safety Systems", "Thermal Management"], region: ["Europe"] };
    const p = toSearchParams(f, new URLSearchParams("tab=history"));
    expect(p.get("tab")).toBe("history");
    expect(fromSearchParams(new URLSearchParams(p.toString()))).toEqual(f);
    expect(toSearchParams(emptyFilters(), p).get("family")).toBeNull();
  });

  it("maps single-valued filters to API query columns", () => {
    const f = { ...emptyFilters(), region: ["Europe"], family: ["A", "B"] };
    expect(toApiQuery(f)).toEqual({ Region: "Europe" });
  });
});
