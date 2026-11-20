"""Cross-series market features.

The champion knows what *this* SKU-region has done. These features add what is happening
right now to its family, its region, its customer, its family-in-region and the whole
market - so a market-wide turn (like the 2024 upswing) is visible before the SKU's own
lags react.

Every value is computed at the forecast origin o from months <= o only (the panel's
filled history `X`), independently for every origin. Nothing is pre-aggregated over the
full history, so the feature-level scramble test covers these features too.

Per group:
  growth_3m   last 3 months vs the 3 before                (short-term momentum)
  growth_6m   last 6 months vs the 6 before
  accel       growth_3m - growth_6m                         (is momentum speeding up?)
  yoy_3m      last 3 months vs the same 3 months a year ago (seasonality-neutral)
  yoy_12m     last 12 months vs the 12 before
  yoy_accel   yoy_3m - yoy_12m                              (turning point signal)
  vol_12      volatility of month-on-month log changes, last 12 months
Per series within its group:
  share_12    series' share of the group, last 12 months
  share_trend share in the last 3 months / share_12        (gaining or losing ground)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

GROUPS = {
    "fam": ["Product_Family"],
    "reg": ["Region"],
    "cust": ["Customer_Name"],
    "famreg": ["Product_Family", "Region"],
    "custreg": ["Customer_Name", "Region"],
    "mkt": [],
}
CLIP = (-1.0, 3.0)


def _win(M: np.ndarray, o: int, a: int, b: int) -> np.ndarray:
    """Sum over months o-b+1 .. o-a (a=0, b=3 -> the last 3 months)."""
    lo, hi = max(0, o - b + 1), o - a + 1
    if hi <= lo:
        return np.full(M.shape[0], np.nan)
    return M[:, lo:hi].sum(1)


def _ratio(a, b):
    with np.errstate(all="ignore"):
        r = np.where(b > 0, a / b - 1, np.nan)
    return np.clip(r, *CLIP)


def group_signals(G: np.ndarray, o: int) -> dict:
    l3, p3, ly3 = _win(G, o, 0, 3), _win(G, o, 3, 6), _win(G, o, 12, 15)
    l6, p6 = _win(G, o, 0, 6), _win(G, o, 6, 12)
    l12, p12 = _win(G, o, 0, 12), _win(G, o, 12, 24)
    g3, g6, y3, y12 = _ratio(l3, p3), _ratio(l6, p6), _ratio(l3, ly3), _ratio(l12, p12)
    lo = max(1, o - 11)
    with np.errstate(all="ignore"):
        ch = np.log1p(G[:, lo: o + 1]) - np.log1p(G[:, lo - 1: o])
        vol = np.nanstd(ch, 1)
    return {"growth_3m": g3, "growth_6m": g6, "accel": g3 - g6, "yoy_3m": y3, "yoy_12m": y12,
            "yoy_accel": y3 - y12, "vol_12": vol}


def cross_features(X: np.ndarray, static: pd.DataFrame, o: int) -> pd.DataFrame:
    Xo = np.nan_to_num(X[:, : o + 1])
    n = Xo.shape[0]
    out = {}
    s3, s12 = _win(Xo, o, 0, 3), _win(Xo, o, 0, 12)
    for name, cols in GROUPS.items():
        if cols:
            lab = static[cols].astype(str).agg("|".join, axis=1).to_numpy()
        else:
            lab = np.zeros(n, dtype=int)
        codes, uniq = pd.factorize(lab)
        G = np.zeros((len(uniq), Xo.shape[1]))
        np.add.at(G, codes, Xo)
        sig = group_signals(G, o)
        for k, v in sig.items():
            out[f"x_{name}_{k}"] = v[codes]
        if cols:
            g3, g12 = _win(G, o, 0, 3)[codes], _win(G, o, 0, 12)[codes]
            with np.errstate(all="ignore"):
                share12 = np.where(g12 > 0, s12 / g12, np.nan)
                share3 = np.where(g3 > 0, s3 / g3, np.nan)
                out[f"x_{name}_share_12"] = share12
                out[f"x_{name}_share_trend"] = np.where(share12 > 0, share3 / share12, np.nan)
    # customer order frequency: share of the customer's series that ordered in the last 3 months
    cust = static["Customer_Name"].astype(str).to_numpy()
    ordered = (Xo[:, max(0, o - 2): o + 1] > 0).any(1).astype(float)
    out["x_cust_order_freq_3m"] = pd.Series(ordered).groupby(cust).transform("mean").to_numpy()
    return pd.DataFrame(out).astype(np.float32)
