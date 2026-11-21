"""Forecast risk per SKU-region - every score is a sum of named, percentile-ranked parts.

Base risk score (celeris.intelligence.classify): backtest error 35%, band width 20%,
volatility 15%, short history 10%, recent data issues 10%, macro sensitivity 10%, +10 for
launch / EOL / customer shutdown. Added here:

  * new-product risk  series with < 24 months of history: volatility of the last 6 months
                      (CV) and distance of the latest 3 months from the series' own 6-month mean
  * forecast anomaly  the forecast breaks with recent actuals: the next-3-month forecast is
                      > 60% away (same direction) from BOTH the last 3 months and the same 3
                      months a year earlier (>= 30 units), or next 12 vs last 12 > 50%; only for
                      regularly ordering series (< 30% zero months) not explained by a
                      lifecycle or shutdown rule
  * value at risk     revenue between forecast and P10 (downside) and P90 (upside), next 12 m
  * confidence        HIGH / MEDIUM / LOW from forecastability (XYZ), band width and risk level
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import HISTORY_END

KEY = ["SKU_ID", "Region"]
JUMP_3M, JUMP_12M, MIN_UNITS = 0.60, 0.50, 30


def _months(end: str, n: int) -> list[str]:
    p = pd.Period(end, "M")
    return [(p - i).strftime("%Y-%m") for i in range(n - 1, -1, -1)]


def enrich(sig: pd.DataFrame, history: pd.DataFrame, rev_fc: pd.DataFrame, seg: pd.DataFrame) -> pd.DataFrame:
    """sig: classified series signals (index SKU_ID, Region) -> adds risk extensions."""
    s = sig.copy()
    h = history[history["Date"] <= HISTORY_END]
    last6 = h[h["Date"].isin(_months(HISTORY_END, 6))].groupby(KEY)["Demand"]
    last3 = h[h["Date"].isin(_months(HISTORY_END, 3))].groupby(KEY)["Demand"].sum()
    s["actual_last3"] = last3.reindex(s.index).fillna(0)
    s["fc_next3"] = rev_fc[rev_fc["h"] <= 3].groupby(KEY)["Forecast"].sum().reindex(s.index).fillna(0)

    # new-product risk (young series with some history)
    young = (s["history_months"] > 0) & (s["history_months"] < 24)
    cv6 = (last6.std() / last6.mean().where(last6.mean() > 0)).reindex(s.index)
    m6 = last6.mean().reindex(s.index)
    drift = (s["actual_last3"] / 3 / m6.where(m6 > 0) - 1).abs()
    s["ramp_cv_6m"] = cv6.where(young)
    s["ramp_drift_3m"] = drift.where(young)
    s["new_product_risk"] = np.where(young, (100 * (0.6 * cv6.rank(pct=True) + 0.4 * drift.rank(pct=True))).round(1), np.nan)

    # forecast anomalies not explained by lifecycle / shutdown rules
    explained = s["new_launch"] | s["eol_in_window"] | s["predecessor_rundown"] | s["customer_shutdown_in_window"]
    j3 = s["fc_next3"] / s["actual_last3"].where(s["actual_last3"] >= MIN_UNITS) - 1
    ly3_months = [(pd.Period(m, "M") + 9).strftime("%Y-%m") for m in _months(HISTORY_END, 3)]   # same months LY as next 3
    ly3 = h[h["Date"].isin(ly3_months)].groupby(KEY)["Demand"].sum().reindex(s.index).fillna(0)
    jly = s["fc_next3"] / ly3.where(ly3 >= MIN_UNITS) - 1
    s["forecast_jump_3m"] = j3.round(3)
    s["forecast_jump_vs_ly"] = jly.round(3)
    regular = s["zero_share_24"].fillna(0) < 0.3                  # intermittent series jump by nature
    short_break = (j3.abs() > JUMP_3M) & (jly.abs() > JUMP_3M) & (np.sign(j3) == np.sign(jly))
    long_break = (s["forecast_change_vs_last12"].abs() > JUMP_12M) & (s["hist_last12"] >= 4 * MIN_UNITS)
    s["forecast_anomaly"] = ~explained & regular & (short_break | long_break)

    # value at risk (next 12 months, USD)
    r = rev_fc[rev_fc["h"] <= 12].groupby(KEY)[["Revenue", "Revenue_P10", "Revenue_P90"]].sum().reindex(s.index)
    s["revenue_next12"] = r["Revenue"].round(0)
    s["revenue_downside_next12"] = (r["Revenue"] - r["Revenue_P10"]).clip(lower=0).round(0)
    s["revenue_upside_next12"] = (r["Revenue_P90"] - r["Revenue"]).clip(lower=0).round(0)

    # segment and confidence
    sg = seg.set_index(KEY)[["Segment", "ABC", "XYZ", "Service_level"]]
    s = s.join(sg)
    wide = s["band_width"] > s["band_width"].median()
    s["confidence"] = np.select(
        [s["XYZ"].isin(["Z", "N"]) | s["risk_level"].eq("HIGH"),
         s["XYZ"].eq("X") & ~wide & s["risk_level"].eq("LOW")],
        ["LOW", "HIGH"], "MEDIUM")
    return s


def risk_explanation(r: pd.Series) -> list[dict]:
    """The named parts of one series' risk score, largest first (for the drill-down card)."""
    w = {"backtest_error": 0.35, "band_width": 0.20, "volatility": 0.15, "short_history": 0.10,
         "data_issues": 0.10, "macro_sensitivity": 0.10}
    parts = [{"component": k, "weight": v, "percentile": float(r[f"risk_{k}"]),
              "points": round(100 * v * float(r[f"risk_{k}"]), 1)} for k, v in w.items()]
    return sorted(parts, key=lambda d: -d["points"])
