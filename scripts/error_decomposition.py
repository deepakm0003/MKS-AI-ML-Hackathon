"""Where does the forecast error come from?  (what the aggregate WAPE hides)

    python scripts/error_decomposition.py [experiment]   -> artifacts/reports/error_decomposition_<exp>.json

Answers: which SKUs cause the most error, which families are systematically under- or
over-forecast, which regions are unstable across periods, where accuracy deteriorates with
horizon, and how much of the error is plain noise vs. bias.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
exp = sys.argv[1] if len(sys.argv) > 1 else "champion"
p = pd.read_parquet(ROOT / "artifacts" / "experiments" / exp / "predictions.parquet")
p["err"] = p["f"] - p["y"]
p["abs"] = p["err"].abs()
TOT_ABS, TOT_Y = p["abs"].sum(), p["y"].sum()


def table(by):
    g = p.groupby(by).agg(y=("y", "sum"), abs=("abs", "sum"), err=("err", "sum"), rows=("y", "size"))
    g["WAPE"] = g["abs"] / g["y"]
    g["Bias"] = g["err"] / g["y"]
    g["share_of_error"] = g["abs"] / TOT_ABS
    g["share_of_demand"] = g["y"] / TOT_Y
    return g


rep = {"experiment": exp, "rows": len(p), "WAPE": float(TOT_ABS / TOT_Y), "Bias": float(p["err"].sum() / TOT_Y)}

# 1. concentration: how many SKU-regions make up half the error?
s = table(["SKU_ID", "Region"]).sort_values("abs", ascending=False)
cum = s["share_of_error"].cumsum().to_numpy()
rep["error_concentration"] = {
    "series": len(s),
    "series_for_50pct_of_error": int(np.searchsorted(cum, 0.5) + 1),
    "series_for_80pct_of_error": int(np.searchsorted(cum, 0.8) + 1),
    "top20_series_share_of_error": float(cum[19]),
    "top20_series_share_of_demand": float(s["share_of_demand"].head(20).sum()),
}
rep["top_error_series"] = s.head(15).reset_index()[["SKU_ID", "Region", "WAPE", "Bias", "share_of_error",
                                                    "share_of_demand"]].round(4).to_dict("records")
sk = table("SKU_ID").sort_values("abs", ascending=False)
rep["top_error_skus"] = sk.head(10).reset_index()[["SKU_ID", "WAPE", "Bias", "share_of_error"]].round(4).to_dict("records")

# 2. systematic bias: family / region / customer bias with consistency across cutoffs
for seg in ["Product_Family", "Region", "Customer_Name"]:
    t = table(seg)
    cons = p.groupby([seg, "cutoff"]).apply(lambda g: g["err"].sum() / g["y"].sum()).unstack()
    t["cutoffs_under"] = (cons < 0).sum(1)
    t["cutoffs_over"] = (cons > 0).sum(1)
    t["WAPE_std_across_cutoffs"] = p.groupby([seg, "cutoff"]).apply(lambda g: g["abs"].sum() / g["y"].sum()).unstack().std(1)
    rep[f"by_{seg}"] = t.round(4).reset_index().to_dict("records")

# 3. horizon deterioration
h = table("h")
rep["by_horizon"] = h[["WAPE", "Bias"]].round(4).reset_index().to_dict("records")
rep["horizon_deterioration"] = {"WAPE_h1_3": float(table(p["h"].between(1, 3)).loc[True, "WAPE"]),
                                "WAPE_h13_19": float(table(p["h"].between(13, 19)).loc[True, "WAPE"])}

# 4. segments
for seg in ["Demand_Class", "Volume_Band", "Lifecycle", "cutoff"]:
    rep[f"by_{seg}"] = table(seg)[["WAPE", "Bias", "share_of_error", "share_of_demand", "rows"]].round(4).reset_index().to_dict("records")

# 5. noise vs bias: error left if every series' total bias were removed
sb = p.groupby(["cutoff", "SKU_ID", "Region"])
adj = p["f"] - sb["err"].transform("mean")
rep["noise_vs_bias"] = {
    "WAPE_actual": float(TOT_ABS / TOT_Y),
    "WAPE_if_each_series_level_were_perfect": float((adj.clip(lower=0) - p["y"]).abs().sum() / TOT_Y),
    "reading": "the gap between these two is error from getting series LEVELS wrong; the rest is month-to-month noise",
}
out = ROOT / "artifacts" / "reports"
out.mkdir(parents=True, exist_ok=True)
(out / f"error_decomposition_{exp}.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")

pd.set_option("display.width", 220)
print(f"{exp}: WAPE {rep['WAPE']:.4f} bias {rep['Bias']:+.4f}")
print("concentration:", rep["error_concentration"])
print("noise vs level:", {k: round(v, 4) for k, v in rep["noise_vs_bias"].items() if k != "reading"})
print("horizon:", {k: round(v, 4) for k, v in rep["horizon_deterioration"].items()})
for seg in ["Product_Family", "Region", "Customer_Name", "Demand_Class", "Volume_Band", "Lifecycle", "cutoff"]:
    t = pd.DataFrame(rep[f"by_{seg}"]).set_index(seg if seg != "cutoff" else "cutoff")
    keep = [c for c in ["WAPE", "Bias", "share_of_error", "share_of_demand", "cutoffs_under", "cutoffs_over",
                        "WAPE_std_across_cutoffs"] if c in t]
    print(f"\n{seg}\n{t[keep].round(3).to_string()}")
print("\ntop error series\n", pd.DataFrame(rep["top_error_series"]).to_string(index=False))
