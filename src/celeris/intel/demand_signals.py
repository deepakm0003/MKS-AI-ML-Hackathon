"""Demand intelligence at every planning level.

Levels: total, family, region, family x region, customer, channel, powertrain (EV / ICE /
Universal - the shift to electric vehicles). Per member:

  * momentum      YoY of the last 3 / 12 months (recovered demand) and acceleration = 3m - 12m;
  * outlook       forecast next 6 / 12 months vs the same months a year earlier;
  * mix shift     share of company demand next 12 months vs last 12 months (points);
  * seasonality   monthly index over the last 36 months: peak / trough months, amplitude;
  * direction     GROWING / STABLE / DECLINING (forecast next 12 vs last 12, +-3%);
  * signal        relative to the whole market (the market itself is in an upturn, so absolute
                  growth flags everything): OUTPACING_MARKET if the 12-month outlook is >= 2 pts
                  or the 3-month momentum >= 5 pts above the market, LAGGING_MARKET mirror,
                  MIXED when outlook and momentum point opposite ways (forecast vs recent
                  orders - a planner review item), else IN_LINE; the total row gets
                  MARKET_UPTURN / DOWNTURN / STEADY.

SKU-region signals (surges, declines, statuses) come from celeris.intelligence and are reused.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import HISTORY_END

LEVELS = {"total": [], "family": ["Product_Family"], "region": ["Region"],
          "family_region": ["Product_Family", "Region"], "customer": ["Customer_Name"],
          "channel": ["Sales_Channel"], "powertrain": ["Powertrain"]}
ACCEL, GROW, DECL = 0.05, 0.03, -0.03
OUTLOOK_GAP, MOMENTUM_GAP = 0.02, 0.05      # points vs the whole market
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _months(end: str, n: int, shift: int = 0) -> list[str]:
    p = pd.Period(end, "M") - shift
    return [(p - i).strftime("%Y-%m") for i in range(n - 1, -1, -1)]


def _ratio(a, b):
    return float(a / b - 1) if b > 0 else np.nan


def signals(history: pd.DataFrame, fc: pd.DataFrame, sku: pd.DataFrame) -> pd.DataFrame:
    pt = sku.set_index("SKU_ID")["Powertrain_Application"]
    h = history[history["Date"] <= HISTORY_END].assign(Powertrain=lambda d: d["SKU_ID"].map(pt))
    f = fc.assign(Powertrain=lambda d: d["SKU_ID"].map(pt))
    l3, l12 = _months(HISTORY_END, 3), _months(HISTORY_END, 12)
    p3, p12 = _months(HISTORY_END, 3, 12), _months(HISTORY_END, 12, 12)
    s36 = _months(HISTORY_END, 36)
    n6 = sorted(f.loc[f["h"] <= 6, "Date"].unique())
    ly6 = [(pd.Period(m, "M") - 12).strftime("%Y-%m") for m in n6]
    tot_l12 = h.loc[h["Date"].isin(l12), "Demand"].sum()
    tot_n12 = f.loc[f["h"] <= 12, "Forecast"].sum()
    rows = []
    for level, by in LEVELS.items():
        hk = h.assign(_k=h[by].astype(str).agg(" | ".join, axis=1) if by else "Total")
        fk = f.assign(_k=f[by].astype(str).agg(" | ".join, axis=1) if by else "Total")
        hs = hk.groupby(["_k", "Date"])["Demand"].sum().unstack().fillna(0)
        fs = fk.groupby(["_k", "Date"])["Forecast"].sum().unstack().fillna(0)
        for k in hs.index:
            hr = hs.loc[k]
            fr = fs.loc[k] if k in fs.index else pd.Series(dtype=float)
            g = lambda ms, src=hr: float(src.reindex(ms).fillna(0).sum())
            y3, y12 = _ratio(g(l3), g(p3)), _ratio(g(l12), g(p12))
            n12 = float(fr[fr.index.isin(sorted(fs.columns)[:12])].sum()) if len(fr) else 0.0
            n6v = float(fr.reindex(n6).fillna(0).sum()) if len(fr) else 0.0
            seas = hr.reindex(s36).fillna(0)
            idx = seas.groupby(pd.PeriodIndex(seas.index, freq="M").month).mean()
            idx = idx / idx.mean() if idx.mean() > 0 else idx * np.nan
            row = {"Level": level, "Member": k,
                   "Demand_last12": round(g(l12)), "Forecast_next12": round(n12),
                   "YoY_last3m": y3, "YoY_last12m": y12,
                   "Acceleration": (y3 - y12) if np.isfinite(y3) and np.isfinite(y12) else np.nan,
                   "Forecast_next6_vs_LY": _ratio(n6v, g(ly6)),
                   "Forecast_next12_vs_last12": _ratio(n12, g(l12)),
                   "Share_last12": g(l12) / tot_l12, "Share_next12": n12 / tot_n12 if tot_n12 else np.nan,
                   "Peak_months": ", ".join(MONTH_NAMES[m - 1] for m in idx.nlargest(2).index) if idx.notna().all() else "",
                   "Trough_month": MONTH_NAMES[idx.idxmin() - 1] if idx.notna().all() else "",
                   "Seasonal_amplitude": float(idx.max() / idx.min()) if idx.notna().all() and idx.min() > 0 else np.nan}
            rows.append(row)
    s = pd.DataFrame(rows)
    s["Mix_shift_pts"] = 100 * (s["Share_next12"] - s["Share_last12"])
    tot = s[s["Level"] == "total"].iloc[0]
    s["Momentum_vs_market"] = s["YoY_last3m"] - tot["YoY_last3m"]
    s["Outlook_vs_market"] = s["Forecast_next12_vs_last12"] - tot["Forecast_next12_vs_last12"]
    out12 = s["Forecast_next12_vs_last12"]
    s["Direction"] = np.select([out12 >= GROW, out12 <= DECL], ["GROWING", "DECLINING"], "STABLE")
    up_o, dn_o = s["Outlook_vs_market"] >= OUTLOOK_GAP, s["Outlook_vs_market"] <= -OUTLOOK_GAP
    up_m, dn_m = s["Momentum_vs_market"] >= MOMENTUM_GAP, s["Momentum_vs_market"] <= -MOMENTUM_GAP
    rel = np.select([(up_o & dn_m) | (dn_o & up_m), up_o | up_m, dn_o | dn_m],
                    ["MIXED", "OUTPACING_MARKET", "LAGGING_MARKET"], "IN_LINE")
    mkt = np.where(tot["Acceleration"] >= ACCEL, "MARKET_UPTURN",
                   np.where(tot["Acceleration"] <= -ACCEL, "MARKET_DOWNTURN", "MARKET_STEADY"))
    s["Signal"] = np.where(s["Level"] == "total", mkt, rel)
    return s.round(4)


def ev_shift(history: pd.DataFrame, fc: pd.DataFrame, sku: pd.DataFrame) -> pd.DataFrame:
    """Share of demand by powertrain application per year, history and forecast."""
    pt = sku.set_index("SKU_ID")["Powertrain_Application"]
    h = history.assign(Year=history["Date"].str[:4], P=history["SKU_ID"].map(pt))
    f = fc.assign(Year=fc["Date"].str[:4], P=fc["SKU_ID"].map(pt))
    a = h.groupby(["Year", "P"])["Demand"].sum().unstack().fillna(0)
    b = f.groupby(["Year", "P"])["Forecast"].sum().unstack().fillna(0)
    b.index = [f"{y} (forecast)" for y in b.index]
    t = pd.concat([a, b])
    return (t.div(t.sum(1), axis=0)).round(4).reset_index().rename(columns={"index": "Year"})
