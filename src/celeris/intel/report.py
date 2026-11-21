"""Consolidated planning-intelligence run -> outputs/intelligence/ (the dashboard contract).

Reads only pipeline outputs (cleaned history, frozen forecast and bands, the final model's
backtest, stockout file, events, macro stress) - never re-forecasts - so it is reproducible
and the API can serve it as is.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from ..config import HISTORY_END, PROCESSED, RAW, ROOT
from . import supply as S
from .demand_signals import ev_shift, signals
from .exceptions import evaluate
from .forecast_risk import enrich
from .narrative import briefing
from .pricing import history_revenue, price_book, price_rise_check, revenue_forecast
from .recommendations import render
from .segmentation import matrix, segment

OUT = ROOT / "outputs" / "intelligence"
EMULATOR = ROOT / "artifacts" / "scenarios" / "emulator.json"


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, float) and np.isnan(o):
        return None
    return str(o)


def timeline(hist_rev: pd.DataFrame, rev_fc: pd.DataFrame, hier: pd.DataFrame) -> pd.DataFrame:
    """Company-level monthly units and revenue, history (shipped and unconstrained) into forecast."""
    h = hist_rev[hist_rev["Date"] <= HISTORY_END].groupby("Date").agg(
        Units_shipped=("Units_Sold", "sum"), Units_unconstrained=("Demand", "sum"),
        Revenue_shipped=("Revenue_shipped", "sum"), Revenue_unconstrained=("Revenue_unconstrained", "sum")).reset_index()
    h["Part"] = "history"
    f = rev_fc.groupby("Date").agg(Units_forecast=("Forecast", "sum"), Revenue_forecast=("Revenue", "sum")).reset_index()
    t = hier[hier["Level"] == "total"].set_index("Date")
    f["Units_P10"], f["Units_P90"] = f["Date"].map(t["P10"]), f["Date"].map(t["P90"])
    ratio = f["Revenue_forecast"] / f["Units_forecast"]
    f["Revenue_P10"], f["Revenue_P90"] = f["Units_P10"] * ratio, f["Units_P90"] * ratio
    f["Part"] = "forecast"
    return pd.concat([h, f], ignore_index=True).round(2)


def mix(hist_rev: pd.DataFrame, rev_fc: pd.DataFrame) -> pd.DataFrame:
    """Units and revenue by family / region / channel: last 12 months vs next 12 months."""
    l12 = hist_rev[hist_rev["Date"] > (pd.Period(HISTORY_END, "M") - 12).strftime("%Y-%m")]
    l12 = l12[l12["Date"] <= HISTORY_END]
    n12 = rev_fc[rev_fc["h"] <= 12]
    rows = []
    for dim in ["Product_Family", "Region", "Sales_Channel"]:
        a = l12.groupby(dim).agg(Units_last12=("Demand", "sum"), Revenue_last12=("Revenue_unconstrained", "sum"))
        b = n12.groupby(dim).agg(Units_next12=("Forecast", "sum"), Revenue_next12=("Revenue", "sum"))
        g = a.join(b, how="outer").reset_index().rename(columns={dim: "Member"})
        g.insert(0, "Dimension", dim)
        rows.append(g)
    m = pd.concat(rows, ignore_index=True)
    m["Units_change_pct"] = 100 * (m["Units_next12"] / m["Units_last12"] - 1)
    m["Revenue_change_pct"] = 100 * (m["Revenue_next12"] / m["Revenue_last12"] - 1)
    return m.round(2)


def run_report(sig: pd.DataFrame, fc: pd.DataFrame, pred: pd.DataFrame, model_name: str,
               hier: pd.DataFrame, log=print) -> dict:
    t0 = time.time()
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    demand, sku, stockouts = rd("demand"), rd("sku_master"), rd("stockouts")
    events = pd.read_csv(RAW / "events_calendar.csv")
    OUT.mkdir(parents=True, exist_ok=True)

    book = price_book(demand, sku, events)
    rev_fc = revenue_forecast(fc, book)
    hist_rev = history_revenue(demand)
    seg = segment(rev_fc, pred)
    seg_m = matrix(seg)
    win = S.backtest_windows(pred)
    q = S.fit_window_quantiles(win)
    plan = S.procurement_plan(rev_fc, seg, q)
    nc = S.next_cycle(plan)
    cap = S.capacity_check(demand, fc, S.load_upside_multiplier(pred))
    sr = S.supply_risk(stockouts, demand)
    segs = signals(demand, fc, sku)
    series = enrich(sig, demand, rev_fc, seg)
    exc = evaluate(dict(rev_fc=rev_fc, capacity=cap, supply=sr, segments=segs, sku=sku, series=series, next_cycle=nc))
    cards = render(exc)

    stress_p = ROOT / "artifacts" / "reports" / "macro_stress.csv"
    stress = pd.read_csv(stress_p) if stress_p.exists() else None
    tl = timeline(hist_rev, rev_fc, hier)
    l12 = tl[(tl["Part"] == "history")].tail(12)
    n12 = tl[(tl["Part"] == "forecast")].head(12)
    f19 = tl[tl["Part"] == "forecast"]
    kpi = {"forecast_model": model_name, "history_end": HISTORY_END,
           "units_next12": float(n12["Units_forecast"].sum()),
           "units_next12_vs_last12": float(n12["Units_forecast"].sum() / l12["Units_unconstrained"].sum() - 1),
           "revenue_next12": float(n12["Revenue_forecast"].sum()),
           "revenue_next12_vs_last12": float(n12["Revenue_forecast"].sum() / l12["Revenue_unconstrained"].sum() - 1),
           "units_19m": float(f19["Units_forecast"].sum()), "units_19m_p10": float(f19["Units_P10"].sum()),
           "units_19m_p90": float(f19["Units_P90"].sum()), "revenue_19m": float(f19["Revenue_forecast"].sum()),
           "series": int(len(series)), "exceptions": int(len(exc)),
           "exceptions_by_priority": exc["priority"].value_counts().to_dict(),
           "capacity_flags": cap["Capacity_flag"].value_counts().to_dict(),
           "high_supply_risk_family_regions": int((sr["Supply_risk_level"] == "HIGH").sum())}
    brief = briefing(kpi, segs, cap, cards, seg_m, stress, float(nc["Cover_value_usd"].sum()),
                     float(nc["Buffer_value_usd"].sum()))

    scen = None
    if EMULATOR.exists():
        from . import scenarios as SC
        emu = SC.load(EMULATOR)
        price = rev_fc.groupby(["Product_Family", "Region", "Date"])[["Revenue", "Forecast"]].sum()
        price = (price["Revenue"] / price["Forecast"]).rename("Avg_price").reset_index()
        price.to_csv(OUT / "scenario_prices.csv", index=False)
        sims_p = EMULATOR.parent / "simulations.parquet"
        sims = pd.read_parquet(sims_p) if sims_p.exists() else None
        scen = {}
        for n, s in SC.PRESETS.items():
            exact = None
            if sims is not None and (n == "Base case" or f"preset_{n}" in set(sims["scenario_id"])):
                exact = SC.simulated_cells(sims, "base" if n == "Base case" else f"preset_{n}")
            scen[n] = SC.evaluate(emu, s, price=price, capacity=cap, cells=exact)
        (OUT / "scenario_presets.json").write_text(json.dumps(scen, indent=1, default=_jsonable), encoding="utf-8")

    # ---- write
    # lifecycle and demand-profile reference for the Demand Explorer (copies, no new calculation)
    life = sku.copy()
    succ = life.dropna(subset=["Replaces_SKU"]).set_index("Replaces_SKU")["SKU_ID"]
    life["Successor_SKU"] = life["SKU_ID"].map(succ)
    life.to_csv(OUT / "sku_lifecycle.csv", index=False)
    prof = pd.read_parquet(PROCESSED / "series_profile.parquet")
    prof[["SKU_ID", "Region", "First_Month", "Last_Month", "Months", "Cycle_Last12", "Cycle_Last24",
          "Months_Since_Order", "Nonzero_Share_24", "ADI", "CV2", "Demand_Class", "Mean_12"]].to_csv(
        OUT / "series_profile.csv", index=False)
    book.to_csv(OUT / "price_book.csv", index=False)
    price_rise_check(demand, events).to_csv(OUT / "price_rise_check.csv", index=False)
    tl.to_csv(OUT / "timeline.csv", index=False)
    mix(hist_rev, rev_fc).to_csv(OUT / "mix.csv", index=False)
    seg.to_csv(OUT / "segmentation.csv", index=False)
    seg_m.to_csv(OUT / "segment_matrix.csv", index=False)
    S.window_coverage(pred).to_csv(OUT / "leadtime_calibration.csv", index=False)
    plan.to_csv(OUT / "procurement_plan.csv", index=False)
    nc.round(2).to_csv(OUT / "procurement_next_cycle.csv", index=False)
    cap.to_csv(OUT / "capacity_check.csv", index=False)
    sr.round(2).to_csv(OUT / "supply_risk.csv", index=False)
    segs.to_csv(OUT / "demand_signals.csv", index=False)
    ev_shift(demand, fc, sku).to_csv(OUT / "ev_shift.csv", index=False)
    sr_cols = [c for c in series.columns if c != "reason_codes"]
    sv = series[sr_cols].copy()
    sv["reason_codes"] = series["reason_codes"].map(lambda c: "|".join(c) if isinstance(c, list) else c)
    sv.reset_index().round(4).to_csv(OUT / "series_risk.csv", index=False)
    ex = exc.copy()
    ex["evidence"] = ex["evidence"].map(lambda d: json.dumps(d, default=_jsonable))
    ex.to_csv(OUT / "exceptions_ranked.csv", index=False)
    (OUT / "recommendations.json").write_text(json.dumps(cards, indent=1, default=_jsonable), encoding="utf-8")
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "kpis": kpi, "briefing": brief,
              "top_recommendations": cards[:30],
              "rule_counts": exc.groupby(["rule_id", "priority"]).size().unstack(fill_value=0).to_dict("index"),
              "segment_matrix": seg_m.to_dict("records"),
              "capacity": cap[cap["Capacity_flag"] != "OK"].to_dict("records"),
              "market": segs[segs["Level"].isin(["total", "family", "region", "channel", "powertrain"])].to_dict("records"),
              "scenario_presets": {n: {"total": r["total"], "responses": r["responses"]} for n, r in scen.items()} if scen else None}
    (OUT / "intelligence_report.json").write_text(json.dumps(report, indent=1, default=_jsonable), encoding="utf-8")
    log(f"planning intelligence: {len(exc)} exceptions ({kpi['exceptions_by_priority']}), "
        f"{len(cards)} recommendations, briefing {len(brief)} bullets, {time.time() - t0:.0f}s")
    return {"report": report, "cards": cards, "series": series, "exceptions": exc}
