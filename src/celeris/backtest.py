"""Stage 3c - rolling-origin backtest with a 19-month horizon.

For each cutoff C the models see data up to C only and forecast C+1 .. C+19, which is
scored against the recovered (unconstrained) demand. Four cutoffs, six months apart,
cover 2023-11 .. 2026-10.
"""
from __future__ import annotations

import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from .features import HORIZON, LAST_HIST, MIDX, MONTHS, Panel, feature_columns

CUTOFFS = ["2023-10", "2024-04", "2024-10", "2025-03"]
TRAIN_FIRST_ORIGIN = 12          # need a year of history for lags
TRAIN_ORIGIN_STEP = 2


# ----------------------------------------------------------------------------- metrics
def wape(y, f):
    y, f = np.asarray(y, float), np.asarray(f, float)
    return float(np.abs(f - y).sum() / max(np.abs(y).sum(), 1e-9))


def bias(y, f):
    y, f = np.asarray(y, float), np.asarray(f, float)
    return float((f - y).sum() / max(np.abs(y).sum(), 1e-9))


def score(df: pd.DataFrame, pred_cols: list[str], by: str | None = None) -> pd.DataFrame:
    def one(g):
        out = {}
        for c in pred_cols:
            out[(c, "WAPE")] = wape(g["y"], g[c])
            out[(c, "Bias")] = bias(g["y"], g[c])
        out[("n", "rows")] = len(g)
        return pd.Series(out)
    if by is None:
        return one(df).to_frame().T
    return df.groupby(by).apply(one)


# ----------------------------------------------------------------------------- baselines
def tsb_forecast(X: np.ndarray, alpha=0.1, beta=0.1) -> np.ndarray:
    """Teunter-Syntetos-Babai: smoothed demand probability x smoothed order size."""
    n, T = X.shape
    p = np.full(n, np.nan)
    z = np.full(n, np.nan)
    for t in range(T):
        x = X[:, t]
        ok = ~np.isnan(x)
        nz = ok & (x > 0)
        init = ok & np.isnan(p)
        p[init] = (x[init] > 0).astype(float)
        z[init & nz] = x[init & nz]
        upd = ok & ~init
        p[upd] = p[upd] + beta * ((x[upd] > 0) - p[upd])
        zz = upd & nz
        z[zz] = np.where(np.isnan(z[zz]), x[zz], z[zz] + alpha * (x[zz] - z[zz]))
    return np.nan_to_num(p) * np.nan_to_num(z)


def add_baselines(ev: pd.DataFrame, P: Panel, c: int) -> pd.DataFrame:
    ev = ev.copy()
    m12 = ev["mean_12"].fillna(ev["mean_3"]).fillna(0)
    ev["f_naive_seasonal"] = ev["same_month_ly"].fillna(m12)
    ev["f_ma12"] = m12
    ev["f_seasonal_ma"] = m12 * ev["seas_idx"]
    ev["f_cycle_naive"] = ev["cycle_naive"].fillna(m12)
    tsb = tsb_forecast(P.X[:, : c + 1])
    ev["f_tsb"] = tsb[ev["series"].to_numpy()] * ev["seas_idx"]
    return ev


# ----------------------------------------------------------------------------- global model
LGB_PARAMS = dict(
    objective="tweedie", tweedie_variance_power=1.2, learning_rate=0.03, num_leaves=63,
    min_data_in_leaf=200, feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1,
    lambda_l2=1.0, verbose=-1, num_threads=0, seed=7)
N_ROUNDS = 1200


def training_frames(P: Panel, last_target: int, step=TRAIN_ORIGIN_STEP,
                    cache: dict | None = None) -> pd.DataFrame:
    frames = []
    for o in range(TRAIN_FIRST_ORIGIN, last_target, step):
        if cache is not None and o in cache:
            f = cache[o]
        else:
            f = P.frame(o, horizons=range(1, HORIZON + 1))
            if cache is not None:
                cache[o] = f
        frames.append(f[f["target_idx"] <= last_target])
    df = pd.concat(frames, ignore_index=True)
    return df[(df["w"] > 0) & df["scale"].notna()]


def fit_lgb(train: pd.DataFrame, params=None, rounds=N_ROUNDS):
    params = {**LGB_PARAMS, **(params or {})}
    cols = feature_columns(train)
    yr = (train["y"] / train["scale"]).clip(upper=20)           # scale-free target
    ds = lgb.Dataset(train[cols], yr, weight=train["scale"],    # weight by scale -> optimises units
                     categorical_feature=[c for c in cols if str(train[c].dtype) == "category"],
                     free_raw_data=False)
    model = lgb.train(params, ds, num_boost_round=rounds)
    return model, cols


def predict_lgb(model, cols, ev: pd.DataFrame) -> np.ndarray:
    r = model.predict(ev[cols])
    s = ev["scale"].fillna(ev["mean_3"]).fillna(0).to_numpy()
    return np.clip(r * s, 0, None)


# ----------------------------------------------------------------------------- driver
def run_backtest(P: Panel, cutoffs=CUTOFFS, lgb_variants: dict | None = None, verbose=True):
    lgb_variants = lgb_variants or {"lgb": {}}
    cache: dict = {}
    results = []
    for C in cutoffs:
        t0 = time.time()
        c = MIDX[C]
        ev = P.frame(c, horizons=range(1, HORIZON + 1))
        ev = ev[ev["target_idx"] <= LAST_HIST]
        ev = add_baselines(ev, P, c)
        train = training_frames(P, c, cache=cache)
        for name, params in lgb_variants.items():
            model, cols = fit_lgb(train, params)
            ev[f"f_{name}"] = predict_lgb(model, cols, ev)
        ev["cutoff"] = C
        ev["target_month"] = [MONTHS[i] for i in ev["target_idx"]]
        results.append(ev)
        if verbose:
            pc = [x for x in ev.columns if x.startswith("f_")]
            s = score(ev, pc).iloc[0]
            print(f"cutoff {C}: train rows {len(train):,}, eval rows {len(ev):,}, {time.time()-t0:.0f}s  " +
                  "  ".join(f"{p[2:]} {s[(p, 'WAPE')]:.3f}" for p in pc))
    return pd.concat(results, ignore_index=True)
