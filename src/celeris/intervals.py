"""P10 / P50 / P90 from backtest errors (split-conformal style).

The model forecast f is a mean. Its error distribution is learned from the rolling
backtest: for every (forecast-size bin x horizon bucket) cell we keep the 10th, 50th
and 90th percentile of actual / forecast. A new forecast in that cell gets
P10 = f x q10, P50 = f x q50, P90 = f x q90. Because the quantiles come from genuine
out-of-sample forecasts, the bands are calibrated by construction; coverage is checked
leave-one-cutoff-out.

Stratified version (strata=True, Phase D): the ratio quantiles are also split by a
reliability stratum - young series (< 24 months of history) vs established, crossed with
the two volatile regions (Middle East & Africa, Latin America) vs the rest. A pooled
quantile is used wherever a stratified cell has fewer than MIN_CELL backtest rows.
Leave-one-cutoff-out on the champion's 6 cutoffs this lifts the worst segment coverage
from 73% (new series) to 79%, lowers pinball loss at P10 and P90 and narrows the bands
slightly (artifacts/reports/interval_calibration.csv).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

F_EDGES = [0, 1, 3, 6, 10, 15, 22, 32, 45, 65, 100, np.inf]
H_EDGES = [0, 3, 6, 12, 19]
QS = (0.10, 0.50, 0.90)
MIN_CELL = 300
VOLATILE_REGIONS = ("Middle East & Africa", "Latin America")


def stratum(age, region) -> np.ndarray:
    """age = months of history at the forecast origin (NaN = no history -> young)."""
    age = np.asarray(age, float)
    young = np.where(np.isnan(age) | (age < 24), "new", "est")
    vol = np.where(pd.Series(region).astype(str).isin(VOLATILE_REGIONS).to_numpy(), "vol", "core")
    return np.char.add(np.char.add(young.astype(str), "|"), vol.astype(str))


def _cells(f: pd.Series, h: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"fbin": pd.cut(f, F_EDGES, right=False, labels=False),
                         "hbin": pd.cut(h, H_EDGES, right=True, labels=False)})


def _quantiles(g: pd.DataFrame, keys: list) -> pd.DataFrame:
    q = g.groupby(keys)["r"].quantile(list(QS)).unstack()
    q.columns = [f"q{int(100 * x)}" for x in QS]
    q["n"] = g.groupby(keys).size()
    return q.reset_index()


def fit_ratio_quantiles(bt: pd.DataFrame, col: str, strata: bool = False):
    """strata=False: one table by (size bin x horizon bucket), as used by the champion.
    strata=True: (stratified table, pooled table) - needs 'age' and 'Region' columns."""
    c = _cells(bt[col], bt["h"])
    f = bt[col].clip(lower=0.5)                  # tiny forecasts: ratio on a 0.5 floor
    g = pd.concat([c, (bt["y"] / f).rename("r")], axis=1)
    pooled = _quantiles(g, ["fbin", "hbin"])
    if not strata:
        return pooled.drop(columns="n")
    g["s"] = stratum(bt["age"], bt["Region"])
    return _quantiles(g, ["s", "fbin", "hbin"]), pooled


def apply_ratio_quantiles(df: pd.DataFrame, col: str, q) -> pd.DataFrame:
    c = _cells(df[col], df["h"])
    if isinstance(q, tuple):                      # stratified, with pooled fallback
        qs, pooled = q
        c["s"] = stratum(df["age"], df["Region"])
        m = c.merge(qs, on=["s", "fbin", "hbin"], how="left")
        m0 = c.merge(pooled, on=["fbin", "hbin"], how="left")
        small = m["n"].fillna(0).to_numpy() < MIN_CELL
        for name in ["q10", "q50", "q90"]:
            m[name] = np.where(small, m0[name].to_numpy(), m[name].to_numpy())
    else:
        m = c.merge(q, on=["fbin", "hbin"], how="left")
    f = df[col].clip(lower=0.5).to_numpy()
    out = df.copy()
    for name in ["q10", "q50", "q90"]:
        out[f"P{name[1:]}"] = np.clip(f * pd.Series(m[name]).fillna(1.0).to_numpy(), 0, None)
    # where the model forecast is essentially zero keep the low bands at zero
    zero = df[col].to_numpy() < 0.05
    out.loc[zero, ["P10", "P50"]] = 0.0
    return out


def pinball(y, q, tau):
    d = np.asarray(y) - np.asarray(q)
    return float(np.mean(np.maximum(tau * d, (tau - 1) * d)))
