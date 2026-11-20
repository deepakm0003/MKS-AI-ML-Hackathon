"""Macro-driven top-down alignment.

The SKU-level model is good at shape (seasonality, ordering cycles, mix) but, like every
bottom-up model, slow to see a market-wide turn: in 2024 demand rose 13% and all models
under-forecast it. Family demand growth, however, follows the leading indicators closely
(r = 0.75-0.88 at a 3-4 month lead). So:

1. Family model: YoY log-growth of each family's monthly demand ~ a + b * indicator at
   its lead (the family's best indicator), fitted on data up to the cutoff only.
2. Family forecast for month T: family demand 12 months earlier x exp(predicted growth)
   (chained for T more than 12 months ahead).
3. Alignment: each SKU-region forecast in that family-month is scaled by
   (family forecast / sum of SKU forecasts) ** alpha. alpha = 0 keeps the bottom-up model,
   alpha = 1 forces the family total; alpha is chosen in the backtest.
The result is coherent by construction: SKU forecasts still add up to the family.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import MONTHS

FAMILY_DRIVER = {
    "Brake & Safety Systems": ("Auto_Production_YoY_Pct", 3, "level"),
    "Chassis & Structural": ("Auto_Production_YoY_Pct", 4, "level"),
    "Thermal Management": ("Auto_Production_YoY_Pct", 4, "level"),
    "Electrical Assemblies": ("New_Vehicle_Orders_Index", 3, "yoy"),
    "Hydraulic Systems": ("New_Vehicle_Orders_Index", 4, "yoy"),
    "Powertrain Components": ("New_Vehicle_Orders_Index", 4, "yoy"),
    "Precision Machined Parts": ("New_Vehicle_Orders_Index", 4, "yoy"),
}


def _signal(macro: pd.DataFrame, ind: str, kind: str) -> pd.Series:
    s = macro.set_index("Date")[ind].reindex(MONTHS).astype(float)
    return s if kind == "level" else 100 * np.log(s / s.shift(12))


def family_forecast(demand: pd.DataFrame, macro: pd.DataFrame, cutoff: str,
                    horizon: int = 19, fit_from: str = "2021-01") -> pd.DataFrame:
    """Family x month forecast of total demand for cutoff+1 .. cutoff+horizon."""
    fam = demand.groupby(["Date", "Product_Family"])["Demand_Model"].sum().unstack()
    fam = fam.reindex(MONTHS)
    ci = MONTHS.index(cutoff)
    rows = []
    for f, (ind, lag, kind) in FAMILY_DRIVER.items():
        y = fam[f]
        sig = _signal(macro, ind, kind).shift(lag)
        g = np.log(y / y.shift(12))
        fit = pd.DataFrame({"g": g, "x": sig}).loc[fit_from:cutoff].dropna()
        fit = fit[np.isfinite(fit["g"])]
        b, a = np.polyfit(fit["x"], fit["g"], 1)
        pred_g = a + b * sig
        level = y.copy()
        for k in range(1, horizon + 1):
            t = ci + k
            if t >= len(MONTHS):
                break
            level.iloc[t] = level.iloc[t - 12] * np.exp(pred_g.iloc[t])
            rows.append({"Product_Family": f, "target_month": MONTHS[t], "fam_fc": level.iloc[t],
                         "pred_growth": pred_g.iloc[t], "slope": b})
    return pd.DataFrame(rows)


def align(df: pd.DataFrame, fam_fc: pd.DataFrame, col: str, alpha: float, out: str) -> pd.DataFrame:
    """Scale SKU forecasts in `col` toward the family forecast (partial pooling by alpha)."""
    s = df.groupby(["Product_Family", "target_month"])[col].transform("sum")
    m = df[["Product_Family", "target_month"]].merge(fam_fc, how="left",
                                                     on=["Product_Family", "target_month"])["fam_fc"]
    ratio = (m.to_numpy() / np.where(s > 0, s, np.nan))
    ratio = np.clip(np.nan_to_num(ratio, nan=1.0), 0.7, 1.4)
    df[out] = df[col] * ratio ** alpha
    return df
