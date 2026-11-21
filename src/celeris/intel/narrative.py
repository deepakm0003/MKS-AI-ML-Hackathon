"""Executive briefing - sentences assembled from computed facts (templates, no LLM).

Each bullet carries the source fields it was built from, so the dashboard can show where
every number comes from. An LLM may later rephrase these; it does not create them.
"""
from __future__ import annotations

import pandas as pd


def _pct(x: float) -> str:
    return f"{100 * x:+.1f}%"


def briefing(kpi: dict, segs: pd.DataFrame, cap: pd.DataFrame, cards: list[dict], seg_matrix: pd.DataFrame,
             stress: pd.DataFrame | None, nc_value: float, nc_buffer: float) -> list[dict]:
    out = []
    tot = segs[segs["Level"] == "total"].iloc[0]
    out.append({"topic": "outlook", "text": (
        f"Demand for the next 12 months is forecast at {kpi['units_next12']:,.0f} units "
        f"({_pct(kpi['units_next12_vs_last12'])} vs the last 12 months) and ${kpi['revenue_next12'] / 1e9:.2f} B revenue "
        f"at the announced 2027 list prices; the 19-month total is {kpi['units_19m'] / 1e6:.2f} M units "
        f"(P10 {kpi['units_19m_p10'] / 1e6:.2f} M - P90 {kpi['units_19m_p90'] / 1e6:.2f} M)."),
        "sources": ["forecast_detail", "price_book", "forecast_hierarchy"]})
    out.append({"topic": "market", "text": (
        f"The market is in an upturn: orders over the last 3 months are {_pct(tot['YoY_last3m'])} year on year "
        f"against {_pct(tot['YoY_last12m'])} over 12 months; peak months are {tot['Peak_months']}."),
        "sources": ["demand_signals"]})
    fam = segs[segs["Level"] == "family"]
    up = fam[fam["Signal"] == "OUTPACING_MARKET"]["Member"].tolist()
    dn = fam[fam["Signal"] == "LAGGING_MARKET"]["Member"].tolist()
    if up or dn:
        out.append({"topic": "mix", "text": (
            f"Relative to the market, {', '.join(up) or 'no family'} {'is' if len(up) == 1 else 'are'} outpacing and "
            f"{', '.join(dn) or 'no family'} {'is' if len(dn) == 1 else 'are'} lagging."), "sources": ["demand_signals"]})
    pt = segs[segs["Level"] == "powertrain"].set_index("Member")
    if {"EV", "ICE"} <= set(pt.index):
        out.append({"topic": "ev_shift", "text": (
            f"The EV shift continues: EV SKUs {_pct(pt.at['EV', 'Forecast_next12_vs_last12'])} next 12 months "
            f"(share {100 * pt.at['EV', 'Share_last12']:.1f}% -> {100 * pt.at['EV', 'Share_next12']:.1f}%), ICE SKUs "
            f"{_pct(pt.at['ICE', 'Forecast_next12_vs_last12'])}."), "sources": ["demand_signals"]})
    above = cap[cap["Capacity_flag"] == "ABOVE_DEMONSTRATED_THROUGHPUT"]
    if len(above):
        top = above.sort_values("Utilisation_P50", ascending=False).iloc[0]
        out.append({"topic": "capacity", "text": (
            f"{len(above)} family-region(s) are forecast above their highest 3-month volume shipped in the last 3 years; "
            f"the largest gap is {top['Product_Family']} in {top['Region']} at {100 * top['Utilisation_P50']:.0f}% "
            f"from the window ending {top['First_window_above_throughput']}."), "sources": ["capacity_check"]})
    out.append({"topic": "procurement", "text": (
        f"Next procurement cycle (deliveries in the next 3 months): ${nc_value / 1e6:.0f} M of supply at each "
        f"segment's service level, of which ${nc_buffer / 1e6:.0f} M is safety buffer above the median forecast."),
        "sources": ["procurement_plan"]})
    a = seg_matrix[seg_matrix["ABC"] == "A"]
    out.append({"topic": "segmentation", "text": (
        f"{int(a['Series'].sum()):,} A-class series carry {100 * a['Revenue_share'].sum():.0f}% of next-year revenue; "
        f"{int(seg_matrix.loc[seg_matrix['XYZ'] == 'Z', 'Series'].sum())} series are hard to forecast (Z) and are "
        f"planner-owned."), "sources": ["segmentation"]})
    if stress is not None and len(stress):
        s = stress.set_index("Scenario")
        out.append({"topic": "macro_risk", "text": (
            f"Macro risk: a combined downside (PMI -3, auto production -2 pp, orders -5%, raw materials +10%) cuts the "
            f"19-month forecast by {abs(s.at['Combined downside', 'Total_vs_base_pct']):.1f}%; the upside adds "
            f"{s.at['Combined upside', 'Total_vs_base_pct']:.1f}%."), "sources": ["macro_stress"]})
    crit = [c for c in cards if c["priority"] == "CRITICAL"]
    if crit:
        out.append({"topic": "actions", "text": (
            f"{len(crit)} critical actions this cycle; the top one: {crit[0]['title']} - {crit[0]['scope']} "
            f"(owner: {crit[0]['owner']})."), "sources": ["recommendations"]})
    return out
