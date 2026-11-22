import { describe, expect, it } from "vitest";
import type { BreakdownRow, TimelineView } from "../api/types";
import { rankedBarsOption, timelineOption, timelineRows } from "../charts/options";
import { fmtMonthShort, fmtPctChange, fmtPctPoints, fmtUnits, fmtUsd } from "../lib/format";

const VIEW: TimelineView = {
  filters: {},
  band_method: "calibrated company band (aggregate error model)",
  summary: {
    series: 2, forecast_series: 2, history_end: "2026-10", units_last12: 1, units_next12: 1, revenue_last12: 1,
    revenue_next12: 1, units_19m: 1, units_19m_p10: 1, units_19m_p90: 1, revenue_19m: 1,
    units_next12_vs_last12: 0, revenue_next12_vs_last12: 0,
  },
  history: [
    { Date: "2026-09", Units_shipped: 90, Units_unconstrained: 100, Revenue_shipped: 900, Revenue_unconstrained: 1000 },
    { Date: "2026-10", Units_shipped: 110, Units_unconstrained: 120, Revenue_shipped: 1100, Revenue_unconstrained: 1200 },
  ],
  forecast: [
    { Date: "2026-11", Units_forecast: 130, Revenue_forecast: 1400, Units_P10: 110, Units_P90: 150, Revenue_P10: 1200, Revenue_P90: 1600 },
    { Date: "2026-12", Units_forecast: 125, Revenue_forecast: 1350, Units_P10: 100, Units_P90: 160, Revenue_P10: 1100, Revenue_P90: 1700 },
  ],
};

describe("formatters", () => {
  it("formats compact units, currency and signed changes", () => {
    expect(fmtUnits(2818669)).toBe("2.82M");
    expect(fmtUnits(52285)).toBe("52.3K");
    expect(fmtUnits(950)).toBe("950");
    expect(fmtUsd(1609864090)).toBe("$1.61B");
    expect(fmtUsd(-5e6, 1)).toBe("−$5.0M");
    expect(fmtPctChange(0.061)).toBe("+6.1%");
    expect(fmtPctChange(-0.044)).toBe("−4.4%");
    expect(fmtPctChange(0.0001)).toBe("0.0%");
    expect(fmtPctPoints(12.5)).toBe("+12.5%");
    expect(fmtUnits(null)).toBe("—");
    expect(fmtMonthShort("2026-11")).toBe("Nov 26");
  });
});

describe("timeline option", () => {
  it("merges history and forecast into one continuous series per metric", () => {
    const rows = timelineRows(VIEW, "units");
    expect(rows.map((r) => r.date)).toEqual(["2026-09", "2026-10", "2026-11", "2026-12"]);
    expect(rows[1]).toMatchObject({ actual: 120, shipped: 110, forecast: null });
    expect(rows[2]).toMatchObject({ actual: null, forecast: 130, p10: 110, p90: 150 });
    expect(timelineRows(VIEW, "revenue")[3].forecast).toBe(1350);
  });

  it("bridges the forecast line from the last actual and stacks the band as P10 + width", () => {
    const o = timelineOption(VIEW, "units") as { series: { name: string; data: (number | null)[] }[] };
    const byName = Object.fromEntries(o.series.map((s) => [s.name, s.data]));
    expect(byName["Forecast"]).toEqual([null, 120, 130, 125]);          // starts at the last actual
    expect(byName["P10–P90 lower"]).toEqual([null, null, 110, 100]);
    expect(byName["P10–P90 range"]).toEqual([null, null, 40, 60]);
    expect(byName["Actual demand"]).toEqual([100, 120, null, null]);
    expect(byName["Shipped"]).toBeUndefined();                          // only on request
  });

  it("uses a single y-axis that follows the data and can start later", () => {
    const o = timelineOption(VIEW, "units", { fromMonth: "2026-10", showShipped: true }) as {
      yAxis: { scale: boolean }; xAxis: { data: string[] }; series: { name: string }[];
    };
    expect(Array.isArray(o.yAxis)).toBe(false);
    expect(o.yAxis.scale).toBe(true);
    expect(o.xAxis.data[0]).toBe("2026-10");
    expect(o.series.map((s) => s.name)).toContain("Shipped");
  });
});

describe("ranked bars option", () => {
  const rows: BreakdownRow[] = [
    { Member: "India", Units_last12: 10, Revenue_last12: 100, Units_next12: 12, Revenue_next12: 130, Units_change_pct: 20, Revenue_change_pct: 30, Revenue_share_next12: 0.3 },
    { Member: "Europe", Units_last12: 20, Revenue_last12: 300, Units_next12: 21, Revenue_next12: 310, Units_change_pct: 5, Revenue_change_pct: 3.3, Revenue_share_next12: 0.7 },
  ];
  it("ranks by the chosen measure with the largest bar on top and one hue", () => {
    const o = rankedBarsOption(rows, "Revenue_next12") as {
      yAxis: { data: string[] }; series: { data: Array<{ value: number; itemStyle: unknown }> }[];
    };
    expect(o.yAxis.data).toEqual(["India", "Europe"]);                  // ECharts draws the last category on top
    expect(o.series[0].data.map(d => d.value)).toEqual([130, 310]);
    expect(typeof o.series[0].data[0].itemStyle).toBe("object");
    const g = rankedBarsOption(rows, "Units_change_pct") as { yAxis: { data: string[] } };
    expect(g.yAxis.data).toEqual(["Europe", "India"]);
  });
});
