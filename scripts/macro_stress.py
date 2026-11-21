"""C0 macro stress test of the final forecast.

    python scripts/macro_stress.py   -> artifacts/reports/macro_stress.csv
Uses the frozen final model (outputs/final) when it exists, else the stage-4 champion.
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from celeris.forecast import forecast_test, replacement_curves  # noqa: E402
from celeris.stress import run_stress  # noqa: E402

rd = lambda n: pd.read_parquet(ROOT / "data" / "processed" / f"{n}.parquet")
inputs = {"demand": rd("demand"), "sku": rd("sku_master"), "macro": rd("macro"),
          "events_monthly": rd("events_monthly"), "test": rd("test")}
extra = {"event_impact": pd.read_csv(ROOT / "outputs/anomalies/event_impact.csv"),
         "bt": pd.read_parquet(ROOT / "outputs/backtest/backtest_predictions.parquet"),
         "curves": replacement_curves(inputs["demand"], inputs["sku"])}
if (ROOT / "outputs/final/manifest.json").exists():
    from celeris.final import load_final_model
    from celeris.robustness import demand_variant
    model, cols, man = load_final_model()
    if man.get("demand_variant"):
        inputs["demand"] = demand_variant(inputs["demand"], man["demand_variant"]).sort_index()
    print("stress-testing the frozen final model:", man["selected_model"])
else:
    model = lgb.Booster(model_file=str(ROOT / "outputs/models/lgb_global_tweedie.txt"))
    cols = json.loads((ROOT / "outputs/models/model_card.json").read_text(encoding="utf-8"))["features"]
res = run_stress(inputs, model, cols, forecast_test, extra)
out = ROOT / "artifacts" / "reports"
out.mkdir(parents=True, exist_ok=True)
res.to_csv(out / "macro_stress.csv", index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
print(res.to_string(index=False))
