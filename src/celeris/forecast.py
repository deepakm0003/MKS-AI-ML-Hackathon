"""Stage 4 - final model and the 19-month forecast (2026-11 .. 2028-05).

1. Train the global LightGBM on every origin whose targets fall inside the history.
2. Predict every test series that has history, from origin 2026-10.
3. Lifecycle and events the model cannot learn from history (rule-based, evidence-based):
     * no demand after EOL or before launch (business rule 5)
     * new launches without history: predecessor level x empirical ramp-up curve
     * predecessor run-down in the months it overlaps with its successor
     * Orion Driveline NA retooling shutdown Jul-Aug 2027: analogue = the Nexon strike
4. P10 / P50 / P90 from backtest error quantiles (calibrated, see intervals.py).
5. Hierarchy: SKU-region forecasts sum exactly to customer, channel, region, family and
   total; aggregate bands use backtest error quantiles at that level.
"""
from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from .backtest import LGB_PARAMS, N_ROUNDS, fit_lgb, predict_lgb, training_frames
from .features import HORIZON, LAST_HIST, MIDX, MONTHS, Panel
from .intervals import apply_ratio_quantiles, fit_ratio_quantiles

KEY = ["Date", "SKU_ID", "Region"]


# ----------------------------------------------------------------------------- lifecycle evidence
def replacement_curves(demand: pd.DataFrame, sku: pd.DataFrame, months: int = 24) -> dict:
    """Ramp-up of successors and run-down of predecessors, relative to the predecessor's
    average monthly demand in the 12 months before the successor's launch."""
    m = sku.set_index("SKU_ID")
    ramps, rundown = [], []
    for new, r in m[m["Replaces_SKU"].notna()].iterrows():
        old = r["Replaces_SKU"]
        n = demand[demand["SKU_ID"] == new].groupby("Date")["Demand"].sum()
        if len(n) == 0:
            continue
        o = demand[demand["SKU_ID"] == old].groupby("Date")["Demand"].sum()
        L, E = pd.Period(r["Launch_Date"], "M"), pd.Period(m.at[old, "EOL_Date"], "M")
        base = o[o.index < str(L)].tail(12).mean()
        ramps.append([n.get((L + k).strftime("%Y-%m"), np.nan) / base for k in range(months)])
        rundown += [o.get((L + k).strftime("%Y-%m"), np.nan) / base for k in range((E - L).n + 1)]
    ramp = pd.Series(np.nanmean(np.array(ramps), 0))
    smooth = ramp.rolling(3, center=True, min_periods=1).mean()
    smooth.iloc[:3] = ramp.iloc[:3]                       # keep the steep start as observed
    return {"ramp": smooth.round(3).tolist(), "ramp_raw": ramp.round(3).tolist(),
            "rundown_factor": round(float(np.nanmean(rundown)), 3), "pairs": len(ramps)}


def shutdown_factor(event_impact: pd.DataFrame, analogue="EV-038") -> float:
    """Planned customer shutdown -> use the measured impact of the closest analogue."""
    imp = event_impact.set_index("Event_ID").at[analogue, "Shipped_Impact_Pct"]
    return float(1 + imp / 100)


# ----------------------------------------------------------------------------- training
def train_final(P: Panel, params=None, rounds=N_ROUNDS, step=2):
    train = training_frames(P, LAST_HIST, step=step)
    model, cols = fit_lgb(train, params, rounds)
    return model, cols, len(train)


# ----------------------------------------------------------------------------- forecast
def forecast_test(P: Panel, model, cols, test: pd.DataFrame, sku: pd.DataFrame,
                  demand: pd.DataFrame, events_monthly: pd.DataFrame, event_impact: pd.DataFrame,
                  bt: pd.DataFrame, curves: dict) -> tuple[pd.DataFrame, dict]:
    o = LAST_HIST
    test = test.copy()
    test["h"] = test["Date"].map(MIDX) - o
    keys = {k: i for i, k in enumerate(zip(P.keys["SKU_ID"], P.keys["Region"]))}
    test["series"] = [keys[k] for k in zip(test["SKU_ID"], test["Region"])]
    has_hist = P.static["first_idx"].to_numpy() <= o
    eligible = np.zeros(len(P.keys), bool)
    eligible[test["series"].unique()] = True
    eligible &= has_hist

    fr = P.frame(o, horizons=range(1, HORIZON + 1), need_target=False, eligible=eligible)
    fr["f_model"] = predict_lgb(model, cols, fr)
    fr["Date"] = [MONTHS[t] for t in fr["target_idx"]]
    out = test.merge(fr[["series", "Date", "f_model"]], on=["series", "Date"], how="left")
    out["method"] = np.where(out["f_model"].notna(), "global LightGBM", "")
    notes = {}

    # -- new launches without history: predecessor level x ramp-up curve
    m = sku.set_index("SKU_ID")
    ramp = curves["ramp"]
    hist_end = MONTHS[o]
    for s in sorted(set(out.loc[out["f_model"].isna(), "SKU_ID"])):
        pred = m.at[s, "Replaces_SKU"]
        L = pd.Period(m.at[s, "Launch_Date"], "M")
        pd_hist = demand[(demand["SKU_ID"] == pred) & (demand["Date"] > MONTHS[o - 12]) & (demand["Date"] <= hist_end)]
        reg_level = pd_hist.groupby("Region")["Demand_Model"].mean()
        fallback = reg_level.mean() if len(reg_level) else 0.0
        sel = out["SKU_ID"].eq(s)
        k = out.loc[sel, "Date"].map(lambda d: (pd.Period(d, "M") - L).n)
        lvl = out.loc[sel, "Region"].map(reg_level).fillna(fallback)
        r = k.map(lambda x: ramp[min(int(x), len(ramp) - 1)] if x >= 0 else 0.0)
        out.loc[sel, "f_model"] = (lvl * r).to_numpy()
        out.loc[sel, "method"] = f"new launch: {pred} level x ramp-up curve"
        notes[s] = {"predecessor": pred, "launch": str(L), "predecessor_level_by_region": reg_level.round(1).to_dict(),
                    "fallback_level": round(float(fallback), 1)}

    # -- predecessor run-down while its successor ramps up
    for s, r in m[m["Replaces_SKU"].notna()].iterrows():
        pred = r["Replaces_SKU"]
        if pd.isna(m.at[pred, "EOL_Date"]) or r["Launch_Date"] <= hist_end:
            continue
        # SET (not multiply) the overlap months to run-down x the predecessor's normal level:
        # the model already lowers SKUs close to EOL (months_to_eol), so multiplying its
        # output would count the run-down twice. The curve is defined on the same base.
        sel = out["SKU_ID"].eq(pred) & out["Date"].between(r["Launch_Date"], m.at[pred, "EOL_Date"])
        base = demand[(demand["SKU_ID"] == pred) & (demand["Date"] > MONTHS[o - 12])
                      & (demand["Date"] <= hist_end)].groupby("Region")["Demand_Model"].mean()
        out.loc[sel, "f_model"] = out.loc[sel, "Region"].map(base).fillna(0).to_numpy() * curves["rundown_factor"]
        out.loc[sel, "method"] += f"; run-down: {curves['rundown_factor']} x normal level while {s} ramps up"

    # -- scheduled customer shutdowns (Orion NA retooling, Jul-Aug 2027)
    fac = shutdown_factor(event_impact)
    # only shutdowns / strikes reduce demand; e.g. EV-052 (Helios capacity increase) is a
    # permanent step that is already in the history and must not be touched
    ce = events_monthly[events_monthly["Event_Type"].eq("Customer Event") & events_monthly["Date"].gt(hist_end)
                        & events_monthly["Description"].str.contains("shutdown|strike", case=False)]
    for _, e in ce.iterrows():
        sel = (out["Customer_Name"].eq(e["Scope_Customer"]) & out["Region"].eq(e["Scope_Region"])
               & out["Date"].eq(e["Date"]))
        f = 1 - (1 - fac) * e["Month_Share"]
        out.loc[sel, "f_model"] *= f
        out.loc[sel, "method"] += f"; {e['Event_ID']} shutdown x{f:.2f} (analogue EV-038)"
        notes.setdefault("customer_shutdowns", []).append(
            {"event": e["Event_ID"], "month": e["Date"], "rows": int(sel.sum()), "factor": round(f, 3)})

    # -- business rule 5: nothing after EOL or before launch
    eol = out["SKU_ID"].map(m["EOL_Date"])
    launch = out["SKU_ID"].map(m["Launch_Date"])
    dead = (eol.notna() & (out["Date"] > eol)) | (out["Date"] < launch)
    out.loc[dead, "f_model"] = 0.0
    out.loc[dead, "method"] = "outside lifecycle (EOL / pre-launch): 0"
    notes["rows_zero_by_lifecycle"] = int(dead.sum())

    # -- bands
    q = fit_ratio_quantiles(bt, "f_lgb_tweedie")
    out = apply_ratio_quantiles(out, "f_model", q)
    out.loc[dead, ["P10", "P50", "P90"]] = 0.0
    out["Forecast"] = out["f_model"].clip(lower=0)
    out["Units_Sold_Forecast"] = np.rint(out["Forecast"]).astype(int)
    out["P10"] = np.minimum(out["P10"], out["Forecast"])
    out["P90"] = np.maximum(out["P90"], out["Forecast"])
    return out, notes


# ----------------------------------------------------------------------------- hierarchy
LEVELS = {"total": [], "family": ["Product_Family"], "region": ["Region"],
          "channel": ["Sales_Channel"], "customer": ["Customer_Name"],
          "family_region": ["Product_Family", "Region"]}


def hierarchy(fc: pd.DataFrame, bt: pd.DataFrame) -> pd.DataFrame:
    """Coherent aggregates (exact sums of SKU forecasts) with level-specific bands from the
    backtest: quantiles of actual/forecast for the same level and horizon bucket."""
    rows = []
    for level, by in LEVELS.items():
        g_bt = bt.groupby(["cutoff", "h"] + by)[["y", "f_lgb_tweedie"]].sum().reset_index()
        g_bt["r"] = g_bt["y"] / g_bt["f_lgb_tweedie"].where(g_bt["f_lgb_tweedie"] > 0)
        g_bt["hb"] = pd.cut(g_bt["h"], [0, 6, 12, 19], labels=False)
        q = g_bt.groupby("hb")["r"].quantile([0.1, 0.5, 0.9]).unstack()
        agg = fc.groupby(["Date"] + by)[["Forecast"]].sum().reset_index()
        agg["h"] = agg["Date"].map(MIDX) - LAST_HIST
        hb = pd.cut(agg["h"], [0, 6, 12, 19], labels=False)
        for name, qq in [("P10", 0.1), ("P50", 0.5), ("P90", 0.9)]:
            agg[name] = agg["Forecast"] * hb.map(q[qq]).to_numpy()
        agg["Level"] = level
        agg["Member"] = agg[by].astype(str).agg(" | ".join, axis=1) if by else "Total"
        rows.append(agg[["Level", "Member", "Date", "h", "Forecast", "P10", "P50", "P90"] + by])
    return pd.concat(rows, ignore_index=True)


def save_model(model: lgb.Booster, cols: list, path, meta: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path / "lgb_global_tweedie.txt"))
    with open(path / "model_card.json", "w", encoding="utf-8") as f:
        json.dump({"features": cols, "params": {**LGB_PARAMS}, **meta}, f, indent=2, default=str)
