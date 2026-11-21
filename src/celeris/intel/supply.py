"""Production and procurement intelligence.

1. Lead-time demand quantiles. Procurement covers LEAD_TIME = 3 months (orders are booked 2-3
   months ahead). The buffer must come from the quantile of the 3-month SUM, not from the sum
   of monthly P90s (months are correlated, and summing monthly P90s overstates the buffer). We
   calibrate it like the monthly bands: in the final model's 6-cutoff backtest, every series
   and every 3-month window gives actual_sum / forecast_sum; its quantiles by window-size bin and
   start-horizon bucket are the multipliers. Coverage is checked leave-one-cutoff-out.
2. Procurement plan: per SKU-region and delivery month - P50, monthly P90 (the problem
   statement's "procurement plan from P90 forecasts"), and the lead-time cover at the
   segment's service level with the safety buffer it implies; order release month = delivery
   month - LEAD_TIME (earlier than Nov 2026 = release now). Windows forecast below 3 units
   (under one unit a month) are make-to-order: no safety stock.
3. Production check: demonstrated throughput = highest 3-month SHIPPED volume of a family x
   region in the last 36 months (a labelled proxy - there is no capacity table). Forecast
   3-month load (P50, and a P90 calibrated on 3-month family x region load windows in the
   backtest) is compared against it.
4. Supply risk: stockout-file history by family x region - shortage months by reason, lost
   units, fill rate (the file is incomplete, so these are lower bounds).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import HISTORY_END

KEY = ["SKU_ID", "Region"]
LEAD_TIME = 3
MTO_UNITS = 3.0                              # 3-month forecast below this -> make to order
TAUS = (0.50, 0.80, 0.85, 0.90, 0.95)
W_EDGES = [0, 3, 10, 30, 60, 100, 160, 260, 450, np.inf]
H_START = [0, 3, 9, 17]                      # window start h: 1-3 / 4-9 / 10-17
CAPACITY_LOOKBACK = 36
NON_CHIP = ["Capacity constraint", "Tooling breakdown", "Supplier quality hold", "Logistics delay"]


def _months_back(end: str, n: int) -> list[str]:
    p = pd.Period(end, "M")
    return [(p - i).strftime("%Y-%m") for i in range(n - 1, -1, -1)]


def _window_sums(M: np.ndarray, L: int = LEAD_TIME) -> np.ndarray:
    """M: rows x horizons (h=1..H). Returns rows x (H-L+1) sums of L consecutive months."""
    c = np.nancumsum(np.c_[np.zeros(len(M)), M], axis=1)
    return c[:, L:] - c[:, :-L]


# ----------------------------------------------------------------------------- 1. lead-time quantiles
def backtest_windows(pred: pd.DataFrame, L: int = LEAD_TIME) -> pd.DataFrame:
    rows = []
    for c, g in pred.groupby("cutoff"):
        Y = g.pivot_table(index="series", columns="h", values="y", aggfunc="sum")
        F = g.pivot_table(index="series", columns="h", values="f", aggfunc="sum")
        Y, F = Y.reindex(columns=range(1, 20)), F.reindex(columns=range(1, 20))
        ok = Y.notna().to_numpy()
        ys, fs = _window_sums(Y.to_numpy()), _window_sums(F.to_numpy())
        full = np.lib.stride_tricks.sliding_window_view(ok, L, axis=1).all(-1)
        for j in range(ys.shape[1]):
            m = full[:, j]
            rows.append(pd.DataFrame({"cutoff": c, "series": Y.index[m], "start_h": j + 1,
                                      "y_sum": ys[m, j], "f_sum": fs[m, j]}))
    return pd.concat(rows, ignore_index=True)


def _cells(fsum, start_h) -> pd.DataFrame:
    return pd.DataFrame({"wbin": pd.cut(fsum, W_EDGES, right=False, labels=False),
                         "hbin": pd.cut(start_h, H_START, right=True, labels=False)})


def fit_window_quantiles(win: pd.DataFrame) -> pd.DataFrame:
    c = _cells(win["f_sum"], win["start_h"])
    r = win["y_sum"] / win["f_sum"].clip(lower=1.0)
    q = pd.concat([c, r.rename("r")], axis=1).groupby(["wbin", "hbin"])["r"].quantile(list(TAUS)).unstack()
    q.columns = [f"q{int(round(100 * t))}" for t in TAUS]
    return q.reset_index()


def apply_window_quantiles(fsum: np.ndarray, start_h: np.ndarray, q: pd.DataFrame) -> pd.DataFrame:
    c = _cells(pd.Series(fsum), pd.Series(start_h)).merge(q, on=["wbin", "hbin"], how="left")
    base = np.clip(fsum, 1.0, None)
    out = pd.DataFrame(index=range(len(fsum)))
    for t in TAUS:
        k = f"q{int(round(100 * t))}"
        out[k] = np.where(fsum < 0.05, 0.0, np.maximum(base * c[k].fillna(1.0).to_numpy(), 0))
    return out


def window_coverage(pred: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-cutoff-out: share of 3-month actual sums at or below each calibrated quantile."""
    win = backtest_windows(pred)
    rows = []
    for c in sorted(win["cutoff"].unique()):
        q = fit_window_quantiles(win[win["cutoff"] != c])
        te = win[win["cutoff"] == c].reset_index(drop=True)
        a = apply_window_quantiles(te["f_sum"].to_numpy(), te["start_h"].to_numpy(), q)
        row = {"Held_out_cutoff": c, "Windows": len(te)}
        for t in TAUS[1:]:
            k = f"q{int(round(100 * t))}"
            row[f"Coverage_{k}"] = round(float((te["y_sum"] <= a[k]).mean()), 3)
        n_naive = te["y_sum"] <= te["f_sum"] * 1.0
        row["Coverage_forecast_only"] = round(float(n_naive.mean()), 3)
        rows.append(row)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- 2. procurement
def procurement_plan(fc: pd.DataFrame, seg: pd.DataFrame, q: pd.DataFrame) -> pd.DataFrame:
    """One row per SKU-region-delivery month."""
    f = fc.sort_values(KEY + ["h"]).copy()
    P = f.pivot_table(index=KEY, columns="h", values="Forecast", aggfunc="sum").reindex(columns=range(1, 20)).fillna(0)
    S = _window_sums(P.to_numpy())                          # windows starting h = 1..17
    starts = np.arange(1, S.shape[1] + 1)
    sl = seg.set_index(KEY)["Service_level"].reindex(P.index).fillna(0.90).to_numpy()
    tau_key = np.array([f"q{int(round(100 * t))}" for t in sl])
    cover = np.zeros_like(S)
    for j, h0 in enumerate(starts):
        a = apply_window_quantiles(S[:, j], np.full(len(S), h0), q)
        cover[:, j] = a.to_numpy()[np.arange(len(S)), [list(a.columns).index(k) for k in tau_key]]
    plan = pd.DataFrame({"SKU_ID": np.repeat(P.index.get_level_values(0), len(starts)),
                         "Region": np.repeat(P.index.get_level_values(1), len(starts)),
                         "h": np.tile(starts, len(P)),
                         "Leadtime_P50": S.reshape(-1), "Leadtime_cover": cover.reshape(-1)})
    mto = plan["Leadtime_P50"] < MTO_UNITS                  # < 1 unit / month expected: make to order, no stock
    plan.loc[mto, "Leadtime_cover"] = plan.loc[mto, "Leadtime_P50"]
    plan["Leadtime_cover"] = np.maximum(plan["Leadtime_cover"], plan["Leadtime_P50"])
    plan["Policy"] = np.where(mto, "make to order", "stock to service level")
    plan["Safety_buffer"] = (plan["Leadtime_cover"] - plan["Leadtime_P50"]).clip(lower=0)
    out = f.merge(plan, on=KEY + ["h"], how="left")
    out = out.merge(seg[KEY + ["Segment", "Service_level"]], on=KEY, how="left")
    rel = (pd.PeriodIndex(out["Date"], freq="M") - LEAD_TIME).strftime("%Y-%m")
    out["Order_release_month"] = np.where(rel <= HISTORY_END, "release now", rel)
    cols = ["Date", "SKU_ID", "Region", "Product_Family", "Customer_Name", "h", "Forecast", "P50", "P90",
            "Segment", "Service_level", "Policy", "Leadtime_P50", "Leadtime_cover", "Safety_buffer", "Order_release_month"]
    if "Revenue" in out:
        cols += ["Unit_Price", "Revenue"]
    return out[cols].round(2)


def next_cycle(plan: pd.DataFrame) -> pd.DataFrame:
    """The decision now: deliveries in the first lead-time window (h = 1..3), per SKU-region."""
    p = plan[plan["h"] == 1].copy()
    p["Cover_value_usd"] = p["Leadtime_cover"] * p.get("Unit_Price", np.nan)
    p["Buffer_value_usd"] = p["Safety_buffer"] * p.get("Unit_Price", np.nan)
    return p[["SKU_ID", "Region", "Product_Family", "Segment", "Service_level", "Leadtime_P50", "Leadtime_cover",
              "Safety_buffer", "Cover_value_usd", "Buffer_value_usd"]].sort_values("Cover_value_usd", ascending=False)


# ----------------------------------------------------------------------------- 3. production check
def load_upside_multiplier(pred: pd.DataFrame, tau: float = 0.90) -> float:
    """Empirical tau-quantile of actual / forecast for 3-month family x region load windows in
    the backtest (pooled over cutoffs and window starts) - the calibrated upside of the load."""
    g = pred.assign(Product_Family=pred["Product_Family"].astype(str), Region=pred["Region"].astype(str))
    agg = g.groupby(["cutoff", "Product_Family", "Region", "h"])[["y", "f"]].sum().reset_index()
    ratios = []
    for _, w in agg.groupby(["cutoff", "Product_Family", "Region"]):
        w = w.sort_values("h")
        ys, fs = w["y"].rolling(LEAD_TIME).sum(), w["f"].rolling(LEAD_TIME).sum()
        ratios.append((ys / fs).dropna())
    return float(pd.concat(ratios).quantile(tau))


def capacity_check(history: pd.DataFrame, fc: pd.DataFrame, upside: float) -> pd.DataFrame:
    """Forecast 3-month load vs demonstrated 3-month throughput, per family x region.
    upside = load_upside_multiplier(backtest): calibrated P90 / forecast for a 3-month load."""
    h = history[history["Date"].isin(_months_back(HISTORY_END, CAPACITY_LOOKBACK))]
    ship = h.groupby(["Product_Family", "Region", "Date"])["Units_Sold"].sum().unstack().fillna(0)
    roll = ship.T.rolling(LEAD_TIME).sum().T
    cap = roll.max(1).rename("Demonstrated_3m_throughput")
    peak_month = roll.idxmax(1).rename("Throughput_peak_window_end")
    load = fc.groupby(["Product_Family", "Region", "Date"])["Forecast"].sum().unstack().fillna(0)
    l50 = load.T.rolling(LEAD_TIME).sum().T
    out = pd.concat([cap, peak_month], axis=1).reindex(load.index)
    out["Peak_3m_load_P50"] = l50.max(1)
    out["Peak_load_window_end"] = l50.idxmax(1)
    out["Peak_3m_load_P90"] = out["Peak_3m_load_P50"] * upside
    out["Utilisation_P50"] = out["Peak_3m_load_P50"] / out["Demonstrated_3m_throughput"]
    out["Utilisation_P90"] = out["Peak_3m_load_P90"] / out["Demonstrated_3m_throughput"]
    over = l50.div(out["Demonstrated_3m_throughput"], axis=0) > 1.0
    out["First_window_above_throughput"] = [r.index[r.to_numpy()][0] if r.any() else None for _, r in over.iterrows()]
    out["Months_above_throughput"] = over.sum(1)
    out["Capacity_flag"] = np.select(
        [out["Utilisation_P50"] > 1.0, out["Utilisation_P50"] >= 0.95, out["Utilisation_P90"] > 1.0],
        ["ABOVE_DEMONSTRATED_THROUGHPUT", "TIGHT", "UPSIDE_ABOVE_THROUGHPUT"], "OK")
    out["Upside_multiplier"] = round(upside, 3)
    return out.reset_index().round(3)


# ----------------------------------------------------------------------------- 4. supply risk
def supply_risk(stockouts: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    so = stockouts.copy()
    if "Valid" in so:
        so = so[so["Valid"]]
    fam = history.groupby("SKU_ID")["Product_Family"].first()
    so["Product_Family"] = so["SKU_ID"].map(fam)
    recent = so[so["Date"].isin(_months_back(HISTORY_END, CAPACITY_LOOKBACK))]
    g = recent.groupby(["Product_Family", "Region"])
    out = pd.DataFrame({
        "Shortage_months_36m": g.size(),
        "Non_chip_shortages_36m": recent[recent["Reason"].isin(NON_CHIP)].groupby(["Product_Family", "Region"]).size(),
        "Capacity_or_tooling_36m": recent[recent["Reason"].isin(["Capacity constraint", "Tooling breakdown"])]
        .groupby(["Product_Family", "Region"]).size(),
        "Supplier_or_logistics_36m": recent[recent["Reason"].isin(["Supplier quality hold", "Logistics delay"])]
        .groupby(["Product_Family", "Region"]).size(),
        "Lost_units_36m": g["Lost_Units"].sum(),
        "Mean_fill_rate_36m": g["Fill_Rate_Pct"].mean(),
    })
    allg = so.groupby(["Product_Family", "Region"])
    out["Chip_allocation_months_all"] = so[so["Reason"].eq("Semiconductor allocation")].groupby(["Product_Family", "Region"]).size()
    out["Shortage_months_all"] = allg.size()
    idx = history.groupby(["Product_Family", "Region"]).size().index
    out = out.reindex(idx).fillna({c: 0 for c in out.columns if c != "Mean_fill_rate_36m"})
    out["Dominant_reason_36m"] = recent.groupby(["Product_Family", "Region"])["Reason"].agg(
        lambda s: s.value_counts().index[0]).reindex(idx)
    rank = lambda s: s.rank(pct=True)
    out["Supply_risk_score"] = (100 * (0.5 * rank(out["Non_chip_shortages_36m"]) + 0.3 * rank(out["Lost_units_36m"])
                                       + 0.2 * rank(100 - out["Mean_fill_rate_36m"].fillna(100)))).round(1)
    out["Supply_risk_level"] = np.where(out["Supply_risk_score"] >= 75, "HIGH",
                                        np.where(out["Supply_risk_score"] >= 45, "MEDIUM", "LOW"))
    return out.reset_index()
