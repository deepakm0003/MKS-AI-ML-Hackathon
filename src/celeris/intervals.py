"""P10 / P50 / P90 from backtest errors (split-conformal style).

The model forecast f is a mean. Its error distribution is learned from the rolling
backtest: for every (forecast-size bin x horizon bucket) cell we keep the 10th, 50th
and 90th percentile of actual / forecast. A new forecast in that cell gets
P10 = f x q10, P50 = f x q50, P90 = f x q90. Because the quantiles come from genuine
out-of-sample forecasts, the bands are calibrated by construction; coverage is checked
leave-one-cutoff-out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

F_EDGES = [0, 1, 3, 6, 10, 15, 22, 32, 45, 65, 100, np.inf]
H_EDGES = [0, 3, 6, 12, 19]
QS = (0.10, 0.50, 0.90)


def _cells(f: pd.Series, h: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"fbin": pd.cut(f, F_EDGES, right=False, labels=False),
                         "hbin": pd.cut(h, H_EDGES, right=True, labels=False)})


def fit_ratio_quantiles(bt: pd.DataFrame, col: str) -> pd.DataFrame:
    c = _cells(bt[col], bt["h"])
    f = bt[col].clip(lower=0.5)                  # tiny forecasts: ratio on a 0.5 floor
    r = (bt["y"] / f).rename("r")
    q = pd.concat([c, r], axis=1).groupby(["fbin", "hbin"])["r"].quantile(list(QS)).unstack()
    q.columns = [f"q{int(100 * x)}" for x in QS]
    return q.reset_index()


def apply_ratio_quantiles(df: pd.DataFrame, col: str, q: pd.DataFrame) -> pd.DataFrame:
    c = _cells(df[col], df["h"])
    m = c.merge(q, on=["fbin", "hbin"], how="left")
    f = df[col].clip(lower=0.5).to_numpy()
    out = df.copy()
    for name in ["q10", "q50", "q90"]:
        out[f"P{name[1:]}"] = np.clip(f * m[name].fillna(1.0).to_numpy(), 0, None)
    # where the model forecast is essentially zero keep the low bands at zero
    zero = df[col].to_numpy() < 0.05
    out.loc[zero, ["P10", "P50"]] = 0.0
    return out


def pinball(y, q, tau):
    d = np.asarray(y) - np.asarray(q)
    return float(np.mean(np.maximum(tau * d, (tau - 1) * d)))
