"""ABC-XYZ segmentation -> planning policy per SKU-region.

ABC = value: next-12-month forecast revenue, cumulative share 80% / 15% / 5%.
XYZ = forecastability measured by the model's OWN backtest error (WAPE over 6 cutoffs), not by
raw CV - raw CV mislabels seasonal series that the model forecasts well. Thresholds match the
reliability tiers: X < 0.25, Y < 0.40, Z >= 0.40. Series without a backtest (launches) = N.

Each cell gets a cycle-service-level target; supply.py plans lead-time demand at that quantile.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KEY = ["SKU_ID", "Region"]
ABC_CUTS = (0.80, 0.95)
XYZ_CUTS = (0.25, 0.40)
SERVICE_LEVEL = {"AX": 0.95, "AY": 0.95, "AZ": 0.90, "BX": 0.90, "BY": 0.90, "BZ": 0.85,
                 "CX": 0.85, "CY": 0.80, "CZ": 0.80, "AN": 0.90, "BN": 0.90, "CN": 0.85}
APPROACH = {
    "X": "stable and forecastable: automate replenishment to the forecast, lean buffer, monthly review",
    "Y": "moderately forecastable: forecast-driven with a calibrated buffer, monthly review",
    "Z": "hard to forecast: planner-owned, buffer at the service quantile, review every cycle with sales",
    "N": "new launch: plan to the ramp-up curve with a launch buffer, track actuals monthly",
}


def backtest_wape(pred: pd.DataFrame) -> pd.Series:
    g = pred.assign(a=(pred["f"] - pred["y"]).abs()).groupby(["SKU_ID", "Region"], observed=True)[["a", "y"]].sum()
    s = g["a"] / g["y"].where(g["y"] > 0)
    s.index = pd.MultiIndex.from_arrays([s.index.get_level_values(0), s.index.get_level_values(1).astype(str)],
                                        names=KEY)
    return s


def segment(rev_fc: pd.DataFrame, pred: pd.DataFrame) -> pd.DataFrame:
    """rev_fc: forecast rows with Revenue (pricing.revenue_forecast); pred: final model backtest."""
    v = rev_fc[rev_fc["h"] <= 12].groupby(KEY)["Revenue"].sum().sort_values(ascending=False)
    share = v.cumsum() / v.sum()
    abc = np.where(share <= ABC_CUTS[0], "A", np.where(share <= ABC_CUTS[1], "B", "C"))
    s = pd.DataFrame({"Revenue_next12": v.round(0), "Revenue_share_cum": share.round(4), "ABC": abc})
    w = backtest_wape(pred).reindex(s.index)
    s["Backtest_WAPE"] = w.round(4)
    s["XYZ"] = np.where(w.isna(), "N", np.where(w < XYZ_CUTS[0], "X", np.where(w < XYZ_CUTS[1], "Y", "Z")))
    s["Segment"] = s["ABC"] + s["XYZ"]
    s["Service_level"] = s["Segment"].map(SERVICE_LEVEL)
    s["Planning_approach"] = s["XYZ"].map(APPROACH)
    return s.reset_index()


def matrix(seg: pd.DataFrame) -> pd.DataFrame:
    """3x4 matrix: series count, revenue share and service level per cell."""
    g = seg.groupby(["ABC", "XYZ"]).agg(Series=("SKU_ID", "size"), Revenue_next12=("Revenue_next12", "sum"))
    g["Revenue_share"] = (g["Revenue_next12"] / g["Revenue_next12"].sum()).round(4)
    g["Service_level"] = [SERVICE_LEVEL[a + x] for a, x in g.index]
    return g.reset_index()
