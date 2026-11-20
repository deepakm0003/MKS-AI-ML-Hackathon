"""Stage 3a - demand drivers.

* macro lead/lag: which indicator leads which family, at what lag, and is it stable?
* EV shift: how fast EV parts replace ICE parts, and how that tracks EV adoption.

Method (lead/lag): family demand growth = log of a 3-month demand total vs the same
3 months a year earlier (removes seasonality and level). Each indicator is turned into
a comparable "change" signal (PMI and YoY-% are used as levels, index series as their
own YoY % change) and shifted 0..12 months ahead of demand. COVID months (2020) are
left out because they would dominate every correlation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEVEL_INDICATORS = {"ISM_Manufacturing_PMI", "Auto_Production_YoY_Pct", "Industrial_Util_Rate_Pct"}
MAX_LAG = 12


def indicator_signals(macro: pd.DataFrame) -> pd.DataFrame:
    m = macro.set_index("Date").drop(columns=["Year", "Month"])
    out = {}
    for c in m.columns:
        out[c] = m[c] if c in LEVEL_INDICATORS else 100 * np.log(m[c] / m[c].shift(12))
    return pd.DataFrame(out)


def family_growth(demand: pd.DataFrame) -> pd.DataFrame:
    fam = demand.groupby(["Date", "Product_Family"])["Demand_Model"].sum().unstack()
    roll = fam.rolling(3).sum()
    return 100 * np.log(roll / roll.shift(12))


def lead_lag(demand: pd.DataFrame, macro: pd.DataFrame, start="2021-01", end="2026-10") -> pd.DataFrame:
    sig = indicator_signals(macro)
    g = family_growth(demand)
    rows = []
    for fam in g.columns:
        y = g[fam].loc[start:end]
        for ind in sig.columns:
            for lag in range(0, MAX_LAG + 1):
                x = sig[ind].shift(lag).reindex(y.index)
                ok = x.notna() & y.notna()
                r = np.corrcoef(x[ok], y[ok])[0, 1] if ok.sum() > 12 else np.nan
                rows.append({"Product_Family": fam, "Indicator": ind, "Lag": lag, "Corr": r, "N": int(ok.sum())})
    return pd.DataFrame(rows)


def best_lags(ll: pd.DataFrame) -> pd.DataFrame:
    i = ll.dropna(subset=["Corr"]).assign(a=lambda x: x["Corr"].abs())
    best = i.loc[i.groupby(["Product_Family", "Indicator"])["a"].idxmax()].drop(columns="a")
    return best.sort_values(["Product_Family", "Corr"], key=lambda s: s.abs() if s.name == "Corr" else s,
                            ascending=[True, False]).reset_index(drop=True)


def lag_stability(demand: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    """Best lag and correlation in two halves of the post-COVID period."""
    a = best_lags(lead_lag(demand, macro, "2021-01", "2023-10")).rename(
        columns={"Lag": "Lag_2021_23", "Corr": "Corr_2021_23"})
    b = best_lags(lead_lag(demand, macro, "2023-11", "2026-10")).rename(
        columns={"Lag": "Lag_2024_26", "Corr": "Corr_2024_26"})
    s = a.drop(columns="N").merge(b.drop(columns="N"), on=["Product_Family", "Indicator"])
    s["Lag_Shift"] = s["Lag_2024_26"] - s["Lag_2021_23"]
    s["Stable"] = (s["Lag_Shift"].abs() <= 2) & (np.sign(s["Corr_2021_23"]) == np.sign(s["Corr_2024_26"])) \
        & (s[["Corr_2021_23", "Corr_2024_26"]].abs().min(axis=1) >= 0.3)
    return s


def ev_shift(demand: pd.DataFrame, sku: pd.DataFrame, macro: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    pt = sku.set_index("SKU_ID")["Powertrain_Application"]
    d = demand.assign(PT=demand["SKU_ID"].map(pt))
    yearly = d.groupby([d["Date"].str[:4], "PT"])["Demand"].sum().unstack().fillna(0)
    share = yearly.div(yearly.sum(axis=1), axis=0)
    monthly = d.groupby(["Date", "PT"])["Demand_Model"].sum().unstack().fillna(0)
    ev_idx = macro.set_index("Date")["EV_Adoption_Index"].reindex(monthly.index)
    ice_share = (monthly["ICE"] / monthly.sum(axis=1)).rolling(12).mean()
    ev_share = (monthly["EV"] / monthly.sum(axis=1)).rolling(12).mean()
    ok = ice_share.notna() & (monthly.index >= "2021-01")
    slope_ice = np.polyfit(ev_idx[ok], 100 * ice_share[ok], 1)[0]
    slope_ev = np.polyfit(ev_idx[ok], 100 * ev_share[ok], 1)[0]
    stats = {
        "ice_share_pct_by_year": (100 * share["ICE"]).round(1).to_dict(),
        "ev_share_pct_by_year": (100 * share["EV"]).round(1).to_dict(),
        "ice_share_pts_per_ev_index_pt": round(float(slope_ice), 3),
        "ev_share_pts_per_ev_index_pt": round(float(slope_ev), 3),
        "corr_ev_index_vs_ev_share": round(float(np.corrcoef(ev_idx[ok], ev_share[ok])[0, 1]), 3),
    }
    table = (100 * share).round(2).reset_index().rename(columns={"Date": "Year"})
    return table, stats
