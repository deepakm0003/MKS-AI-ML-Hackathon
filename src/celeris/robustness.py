"""Phase D - robustness and uncertainty of the champion.

Everything here measures the frozen champion; nothing changes its features, training or
predictions.

1. Cleaning sensitivity - how much do our demand-recovery and exclusion decisions move
   accuracy and the final forecast? Each variant rebuilds the model target with one
   decision reversed, re-runs the champion spec, and is scored on a COMMON yardstick: the
   months every variant agrees on (observed shipments with no anomaly, stockout or event
   flag), so a variant cannot win by redefining the truth.
2. Post-hoc corrections - median (P50) instead of mean, and bias correction learned from
   earlier cutoffs. Tested walk-forward on the champion's backtest.
3. Interval calibration - pooled vs stratified split-conformal bands, leave-one-cutoff-out.
4. Reliability - WAPE by horizon month and a per-series reliability tier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PROCESSED
from .experiments import FrameStore, fit_predict
from .features import MIDX, MONTHS
from .intervals import QS, apply_ratio_quantiles, fit_ratio_quantiles

KEY = ["SKU_ID", "Region"]
EXCLUDED_TYPES = ["one_off_order", "event_window", "price_pull_forward", "missing"]
RECOVERED = ["stockout_file", "allocation_uplift", "backorder_netted"]

VARIANTS = {
    "baseline": "champion cleaning (stockout recovery, DiD allocation uplift, event exclusions)",
    "no_stockout_recovery": "target = shipped units everywhere: no stockout file, backorder netting or allocation uplift",
    "no_allocation_uplift": "stockout file and backorder netting kept; chip-shortage months left at shipped units",
    "exclude_stockouts": "stockout months dropped from training (weight 0, causal fill) instead of recovered",
    "no_training_exclusions": "event windows, price pull-forward and one-off orders kept as training targets",
}
# training-exclusion variants (C9): the demand target is unchanged, only which months train the model
EXCLUSION_SETS = {
    "no_training_exclusions": ["missing"],
    "keep_event_months": ["one_off_order", "missing"],
    "keep_pull_forward": ["one_off_order", "event_window", "missing"],
    "keep_event_windows": ["one_off_order", "price_pull_forward", "missing"],
}


# ----------------------------------------------------------------------------- 1. cleaning variants
def _model_columns(p: pd.DataFrame, excl: pd.Series) -> pd.DataFrame:
    """Same rule as anomalies.build_demand step 7: weight 0 for excluded months, filled with a
    causal trailing-12-month mean for the lag features."""
    p = p.sort_values(KEY + ["Date"]).copy()
    p["Train_Weight"] = np.where(excl, 0.0, 1.0)
    usable = p["Demand"].where(~excl)
    trailing = usable.groupby([p["SKU_ID"], p["Region"]]).transform(
        lambda x: x.shift(1).rolling(12, min_periods=3).mean())
    fill = trailing.fillna(p["Expected"])
    p["Demand_Model"] = p["Demand"].where(~excl, fill).fillna(fill)
    p["Demand_Model"] = p.groupby(KEY)["Demand_Model"].transform(lambda x: x.ffill().bfill()).fillna(0)
    return p


def demand_variant(demand: pd.DataFrame, name: str) -> pd.DataFrame:
    p = demand.copy()
    if name == "baseline":
        return p
    excl = p["Anomaly_Type"].isin(EXCLUDED_TYPES)
    if name in ("no_stockout_recovery", "no_allocation_uplift", "exclude_stockouts"):
        src = RECOVERED if name != "no_allocation_uplift" else ["allocation_uplift"]
        rev = p["Demand_Source"].isin(src)
        p.loc[rev, "Demand"] = p.loc[rev, "Units_Sold"].fillna(p.loc[rev, "Shipped_Units"])
        if name == "exclude_stockouts":
            excl = excl | rev
        else:
            p.loc[rev, "Demand_Source"] = "observed"
    elif name in EXCLUSION_SETS:
        excl = p["Anomaly_Type"].isin(EXCLUSION_SETS[name])
    else:
        raise ValueError(name)
    return _model_columns(p, excl)


def yardstick(demand: pd.DataFrame) -> pd.DataFrame:
    """Months whose truth does not depend on any cleaning decision."""
    ok = (demand["Demand_Source"].eq("observed") & demand["Anomaly_Type"].isin(["", "structural_step"])
          & demand["Units_Sold"].notna())
    return demand.loc[ok, KEY + ["Date", "Units_Sold"]].rename(columns={"Units_Sold": "y_true"})


class VariantStore(FrameStore):
    def __init__(self, demand: pd.DataFrame):
        rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
        self.inputs = (demand, rd("sku_master"), rd("macro"), rd("events_monthly"), rd("test"))
        self.panels, self.frames = {}, {}


def variant_backtest(demand_v: pd.DataFrame, spec: dict, cutoffs: list[str], log=print) -> pd.DataFrame:
    store = VariantStore(demand_v)
    P = store.panel(spec["feature_set"])
    out = []
    for C in cutoffs:
        c = MIDX[C]
        train, ev = store.training(spec, c), store.evaluation(spec, c)
        f, info = fit_predict(spec, train, ev)
        k = P.keys.iloc[ev["series"].to_numpy()]
        out.append(pd.DataFrame({"SKU_ID": k["SKU_ID"].to_numpy(), "Region": k["Region"].to_numpy(),
                                 "Date": [MONTHS[t] for t in ev["target_idx"]], "h": ev["h"].to_numpy(),
                                 "Product_Family": ev["Product_Family"].astype(str).to_numpy(),
                                 "cutoff": C, "f": f}))
        store.frames = {}
        log(f"    {C}: {info['n_train']:,} training rows")
    return pd.concat(out, ignore_index=True)


def score_on_yardstick(pred: pd.DataFrame, ys: pd.DataFrame) -> dict:
    t = pred.merge(ys, on=KEY + ["Date"], how="inner")
    y, f = t["y_true"].to_numpy(float), t["f"].to_numpy(float)
    s = y.sum()
    out = {"rows": len(t), "WAPE": np.abs(f - y).sum() / s, "Bias": (f - y).sum() / s}
    for C, g in t.groupby("cutoff"):
        out[f"WAPE_{C}"] = np.abs(g["f"] - g["y_true"]).sum() / g["y_true"].sum()
    for fam, g in t.groupby("Product_Family"):
        out[f"Bias_{fam}"] = (g["f"] - g["y_true"]).sum() / g["y_true"].sum()
    return out


# ----------------------------------------------------------------------------- 2. post-hoc corrections
def _w(y, f):
    return float(np.abs(np.asarray(f, float) - y).sum() / y.sum())


def post_corrections(pred: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward: corrections for cutoff c are learned from cutoffs before c only."""
    p = pred.copy()
    p["Product_Family"] = p["Product_Family"].astype(str)
    rows = []
    cuts = sorted(p["cutoff"].unique())
    for c in cuts[1:]:
        te, past = p[p["cutoff"] == c].reset_index(drop=True), p[p["cutoff"] < c]
        y = te["y"].to_numpy(float)
        a = apply_ratio_quantiles(te, "f", fit_ratio_quantiles(past, "f"))
        fam = past.groupby("Product_Family").apply(lambda g: g["y"].sum() / g["f"].sum())
        rows.append({"cutoff": c, "model_mean": _w(y, te["f"]), "rounded_to_integer": _w(y, np.rint(te["f"])),
                     "median_P50": _w(y, a["P50"]),
                     "global_bias_correction": _w(y, te["f"] * past["y"].sum() / past["f"].sum()),
                     "family_bias_correction": _w(y, te["f"] * te["Product_Family"].map(fam).astype(float))})
    d = pd.DataFrame(rows)
    mean = d.drop(columns="cutoff").mean().to_dict()
    return pd.concat([d, pd.DataFrame([{"cutoff": "mean", **mean}])], ignore_index=True)


# ----------------------------------------------------------------------------- 3. interval calibration
def _pin(y, q, tau):
    d = y - q
    return float(np.mean(np.maximum(tau * d, (tau - 1) * d)))


def loco_bands(pred: pd.DataFrame, strata: bool) -> pd.DataFrame:
    parts = []
    for c in sorted(pred["cutoff"].unique()):
        te = pred[pred["cutoff"] == c].reset_index(drop=True)
        parts.append(apply_ratio_quantiles(te, "f", fit_ratio_quantiles(pred[pred["cutoff"] != c], "f", strata)))
    t = pd.concat(parts, ignore_index=True)
    t["covered"] = (t["y"] >= t["P10"]) & (t["y"] <= t["P90"])
    t["h_bucket"] = pd.cut(t["h"], [0, 3, 6, 12, 19], labels=["1-3m", "4-6m", "7-12m", "13-19m"]).astype(str)
    return t


SEGMENTS = ["h_bucket", "Lifecycle", "Region", "Demand_Class", "Volume_Band", "Product_Family"]


def interval_calibration(pred: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    pred = pred.copy()
    for c in SEGMENTS[1:]:
        pred[c] = pred[c].astype(str)
    summary, segs = [], []
    for name, strata in [("pooled (stage 4)", False), ("stratified (Phase D)", True)]:
        t = loco_bands(pred, strata)
        y = t["y"].to_numpy(float)
        seg_cov = []
        for s in SEGMENTS:
            for k, g in t.groupby(s):
                seg_cov.append(g["covered"].mean())
                segs.append({"Method": name, "Segment": s, "Value": k, "Rows": len(g),
                             "Coverage_P10_P90": round(g["covered"].mean(), 3)})
        seg_cov = np.array(seg_cov)
        summary.append({"Method": name, "Coverage_P10_P90": t["covered"].mean(),
                        "Worst_segment_coverage": seg_cov.min(),
                        "Mean_abs_gap_to_80pct": np.abs(seg_cov - 0.8).mean(),
                        "Band_width_vs_forecast": (t["P90"] - t["P10"]).sum() / t["f"].sum(),
                        "Pinball_P10": _pin(y, t["P10"].to_numpy(), 0.1),
                        "Pinball_P90": _pin(y, t["P90"].to_numpy(), 0.9)})
    seg = pd.DataFrame(segs).pivot_table(index=["Segment", "Value"], columns="Method",
                                         values="Coverage_P10_P90").reset_index()
    return pd.DataFrame(summary).round(4), seg


# ----------------------------------------------------------------------------- 4. reliability
TIERS = [(0.25, "A reliable"), (0.40, "B usable"), (0.60, "C weak"), (np.inf, "D unreliable")]


def horizon_curve(pred: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for h, g in pred.groupby("h"):
        fam = g.groupby(["cutoff", "Product_Family", "target_month"], observed=True)[["y", "f"]].sum()
        tot = g.groupby(["cutoff", "target_month"])[["y", "f"]].sum()
        rows.append({"h": h, "WAPE_series": _w(g["y"].to_numpy(float), g["f"]),
                     "Bias_series": float((g["f"] - g["y"]).sum() / g["y"].sum()),
                     "WAPE_family_month": _w(fam["y"].to_numpy(float), fam["f"]),
                     "WAPE_total_month": _w(tot["y"].to_numpy(float), tot["f"])})
    return pd.DataFrame(rows).round(4)


def series_reliability(pred: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = pred.assign(ae=(pred["f"] - pred["y"]).abs(), e=pred["f"] - pred["y"]).groupby(["SKU_ID", "Region"], observed=True)
    s = g.agg(actual=("y", "sum"), abs_err=("ae", "sum"), err=("e", "sum"), rows=("y", "size"),
              Product_Family=("Product_Family", "first"), Demand_Class=("Demand_Class", "first"))
    per_cut = pred.assign(ae=(pred["f"] - pred["y"]).abs()).groupby(["SKU_ID", "Region", "cutoff"], observed=True)[["ae", "y"]].sum()
    wc = (per_cut["ae"] / per_cut["y"].where(per_cut["y"] > 0)).groupby(level=[0, 1])
    s["WAPE"] = s["abs_err"] / s["actual"].where(s["actual"] > 0)
    s["Bias"] = s["err"] / s["actual"].where(s["actual"] > 0)
    s["WAPE_cutoff_std"] = wc.std()
    s["Tier"] = "D unreliable"
    for thr, name in reversed(TIERS):
        s.loc[s["WAPE"] < thr, "Tier"] = name
    s["Volume_share"] = s["actual"] / s["actual"].sum()
    tiers = s.groupby("Tier").agg(Series=("WAPE", "size"), Volume_share=("Volume_share", "sum"),
                                  Median_WAPE=("WAPE", "median")).reset_index()
    tiers["Volume_share"] = tiers["Volume_share"].round(3)
    return s.reset_index().round(4), tiers.round(3)
