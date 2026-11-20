"""Print the experiment leaderboard and promotion verdicts.

    python evaluate.py
    python evaluate.py --segments cross_series      # segment comparison vs champion
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
REG = ROOT / "artifacts" / "registry" / "registry.csv"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", nargs="*", default=[])
    a = ap.parse_args()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    reg = pd.read_csv(REG).sort_values("WAPE")
    cols = ["experiment", "WAPE", "Bias", "MAE", "RMSE", "WAPE_1-3m", "WAPE_4-6m", "WAPE_7-12m",
            "WAPE_13-19m", "WAPE_std_cutoffs", "WAPE_family_month", "WAPE_total_month", "verdict"]
    print(reg[[c for c in cols if c in reg.columns]].to_string(index=False))
    for name in a.segments:
        ch = json.loads((ROOT / "artifacts/experiments/champion/metrics.json").read_text())
        ex = json.loads((ROOT / f"artifacts/experiments/{name}/metrics.json").read_text())
        for seg in ["by_cutoff", "by_horizon_bucket", "by_Product_Family", "by_Region", "by_Demand_Class",
                    "by_Volume_Band", "by_Lifecycle"]:
            t = pd.DataFrame({"champion": {k: v["WAPE"] for k, v in ch[seg].items()},
                              name: {k: v["WAPE"] for k, v in ex[seg].items()}})
            t["delta"] = t[name] - t["champion"]
            print(f"\n{seg}\n{t.round(4).to_string()}")
    sys.exit(0)
