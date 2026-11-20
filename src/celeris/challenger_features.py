"""Phase C feature sets (challengers only - the champion's 87 features are untouched).

C1 growth  - aimed at the measured under-forecast of young series, the vehicle-build
             families and Middle East & Africa:
   series momentum (3/6-month growth, YoY, acceleration, 6/12-month slope), age-aware
   growth (young flag x slope, ramp ratio since launch) and a FAMILY-SPECIFIC macro
   sensitivity: at each origin a small regression of the family's YoY growth on its
   leading indicator is fitted on months <= origin, and the implied growth for the
   target month (and its change since the origin) becomes a feature.
C3 interm  - intermittent-demand statistics: ADI, CV2, TSB probability and size, Croston-SBA
   rate, and how overdue the next order is relative to the usual interval.

All values at origin o use data up to o only (macro values for the target month are the
known-in-advance inputs, as for the champion).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FAMILY_DRIVER = {   # family -> (macro column in Panel.macro, lead in months); see drivers.best_lags
    "Brake & Safety Systems": ("Auto_Production_YoY_Pct", 3),
    "Chassis & Structural": ("Auto_Production_YoY_Pct", 4),
    "Thermal Management": ("Auto_Production_YoY_Pct", 4),
    "Electrical Assemblies": ("New_Vehicle_Orders_Index", 3),
    "Hydraulic Systems": ("New_Vehicle_Orders_Index", 4),
    "Powertrain Components": ("New_Vehicle_Orders_Index", 4),
    "Precision Machined Parts": ("New_Vehicle_Orders_Index", 4),
}


def _sum(M, o, a, b):
    lo, hi = max(0, o - b + 1), o - a + 1
    return M[:, lo:hi].sum(1) if hi > lo else np.full(M.shape[0], np.nan)


def _rel(a, b):
    with np.errstate(all="ignore"):
        return np.clip(np.where(b > 0, a / b - 1, np.nan), -1, 3)


def _slope(M, o, k):
    lo = max(0, o - k + 1)
    W = M[:, lo: o + 1]
    t = np.arange(W.shape[1], dtype=float)
    t -= t.mean()
    with np.errstate(all="ignore"):
        m = W.mean(1)
        b = (W * t).sum(1) / max((t ** 2).sum(), 1e-9)
        return np.where(m > 0, b / m, np.nan)


# ----------------------------------------------------------------------------- C1
def growth_series_features(X: np.ndarray, static: pd.DataFrame, o: int) -> pd.DataFrame:
    Xo = np.nan_to_num(X[:, : o + 1])
    age = o - static["first_idx"].to_numpy().astype(float)
    g3 = _rel(_sum(Xo, o, 0, 3), _sum(Xo, o, 3, 6))
    g6 = _rel(_sum(Xo, o, 0, 6), _sum(Xo, o, 6, 12))
    y3 = _rel(_sum(Xo, o, 0, 3), _sum(Xo, o, 12, 15))
    s12, s6 = _slope(Xo, o, 12), _slope(Xo, o, 6)
    young = (age < 24).astype(float)
    # ramp: recent 6 months vs the series' first 6 active months (young series only)
    first = static["first_idx"].to_numpy()
    ramp = np.full(len(Xo), np.nan)
    ok = (age >= 9) & (age < 36)
    for i in np.flatnonzero(ok):
        f0 = int(first[i])
        early = Xo[i, f0: f0 + 6].mean()
        ramp[i] = Xo[i, o - 5: o + 1].mean() / early if early > 0 else np.nan
    return pd.DataFrame({
        "g_growth_3m": g3, "g_growth_6m": g6, "g_accel": g3 - g6, "g_yoy_3m": y3,
        "g_slope_12": s12, "g_slope_6": s6, "g_age_log": np.log1p(np.clip(age, 0, None)),
        "g_young": young, "g_young_slope": young * s12, "g_ramp_ratio": ramp,
    }).astype(np.float32)


def family_macro_models(X: np.ndarray, static: pd.DataFrame, macro: np.ndarray, macro_cols: list,
                        o: int, window: int = 48) -> dict:
    """Per family: g_t = a + b * signal(t - lead), fitted on months <= o (last `window`)."""
    fam = static["Product_Family"].astype(str).to_numpy()
    Xo = np.nan_to_num(X[:, : o + 1])
    out = {}
    for f, (ind, lead) in FAMILY_DRIVER.items():
        tot = Xo[fam == f].sum(0)
        t = np.arange(max(12 + lead, o - window + 1), o + 1)
        if len(t) < 12:
            continue
        with np.errstate(all="ignore"):
            g = np.log(tot[t] / tot[t - 12])
        x = macro[t - lead, macro_cols.index(ind)]
        ok = np.isfinite(g) & np.isfinite(x)
        if ok.sum() < 12:
            continue
        b, a = np.polyfit(x[ok], g[ok], 1)
        out[f] = (a, b, macro_cols.index(ind), lead)
    return out


def growth_target_features(models: dict, fam: np.ndarray, macro: np.ndarray, o: int, t: int) -> dict:
    n = len(fam)
    imp_t, imp_o, beta = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    for f, (a, b, j, lead) in models.items():
        m = fam == f
        imp_t[m] = a + b * macro[t - lead, j]
        imp_o[m] = a + b * macro[o - lead, j]
        beta[m] = b
    return {"g_fam_implied_yoy": imp_t, "g_fam_implied_change": imp_t - imp_o, "g_fam_macro_beta": beta}


# ----------------------------------------------------------------------------- C3
def intermittent_features(X: np.ndarray, o: int, alpha=0.1, beta=0.1) -> pd.DataFrame:
    Xo = X[:, : o + 1]
    n = Xo.shape[0]
    W = np.nan_to_num(Xo[:, max(0, o - 23): o + 1])
    nz = (W > 0).sum(1)
    with np.errstate(all="ignore"):
        adi = np.where(nz > 0, W.shape[1] / nz, np.nan)
        pos = np.where(W > 0, W, np.nan)
        cv2 = (np.nanstd(pos, 1) / np.nanmean(pos, 1)) ** 2
    # TSB on the full history up to o
    p = np.full(n, np.nan)
    z = np.full(n, np.nan)
    for t in range(Xo.shape[1]):
        x = Xo[:, t]
        okx = ~np.isnan(x)
        init = okx & np.isnan(p)
        p[init] = (x[init] > 0)
        z[init & (x > 0)] = x[init & (x > 0)]
        upd = okx & ~init
        p[upd] += beta * ((x[upd] > 0) - p[upd])
        zz = upd & (x > 0)
        z[zz] = np.where(np.isnan(z[zz]), x[zz], z[zz] + alpha * (x[zz] - z[zz]))
    last = np.full(n, np.nan)
    for i in range(n):
        idx = np.flatnonzero(W[i] > 0)
        if len(idx):
            last[i] = W.shape[1] - 1 - idx[-1]
    with np.errstate(all="ignore"):
        sba = (1 - alpha / 2) * z / adi
        overdue = last / adi
    return pd.DataFrame({"i_adi_24": adi, "i_cv2_24": cv2, "i_tsb_p": p, "i_tsb_z": z,
                         "i_tsb_rate": np.nan_to_num(p) * np.nan_to_num(z), "i_sba_rate": sba,
                         "i_overdue": overdue}).astype(np.float32)
