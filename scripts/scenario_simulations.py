"""Simulate macro scenarios with the frozen final model and fit the Scenario Lab emulator.

    python scripts/scenario_simulations.py --train 80 --holdout 20 --workers 10
      -> artifacts/scenarios/simulations.parquet   family x region x month forecast per scenario
         artifacts/scenarios/emulator.json         response surface used by the API
         artifacts/scenarios/emulator_validation.csv  held-out scenario errors
Runs best on the many-core server (each scenario = one full 19-month re-forecast).
"""
import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from celeris.intel import scenarios as SC  # noqa: E402

OUT = ROOT / "artifacts" / "scenarios"
_W = {}


def _init():
    from celeris.final import load_final_model
    from celeris.forecast import replacement_curves
    from celeris.robustness import demand_variant
    rd = lambda n: pd.read_parquet(ROOT / "data" / "processed" / f"{n}.parquet")
    model, cols, man = load_final_model()
    demand = rd("demand")
    if man.get("demand_variant"):
        demand = demand_variant(demand, man["demand_variant"]).sort_index()
    _W.update(model=model, cols=cols, demand=demand, sku=rd("sku_master"), macro=rd("macro"),
              evm=rd("events_monthly"), test=rd("test"),
              impact=pd.read_csv(ROOT / "outputs" / "anomalies" / "event_impact.csv"),
              bt=pd.read_parquet(ROOT / "outputs" / "backtest" / "backtest_predictions.parquet"),
              curves=replacement_curves(demand, rd("sku_master")))


def _run(job):
    sid, shocks = job
    from celeris.features import Panel
    from celeris.forecast import forecast_test
    w = _W
    P = Panel(w["demand"], w["sku"], SC.shock_macro(w["macro"], shocks), w["evm"], w["test"])
    fc, _ = forecast_test(P, w["model"], w["cols"], w["test"], w["sku"], w["demand"], w["evm"], w["impact"],
                          w["bt"], w["curves"])
    g = fc.groupby(["Product_Family", "Region", "Date"])["Forecast"].sum().reset_index()
    g["scenario_id"] = sid
    for k in SC.NAMES:
        g[k] = shocks.get(k, 0.0)
    return g


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=80)
    ap.add_argument("--holdout", type=int, default=20)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [("base", {})]
    jobs += [(f"train_{i:03d}", s) for i, s in enumerate(SC.sample(a.train, seed=1))]
    jobs += [(f"holdout_{i:03d}", s) for i, s in enumerate(SC.sample(a.holdout, seed=99))]
    jobs += [(f"preset_{n}", s) for n, s in SC.PRESETS.items() if s]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init) as ex:
        parts = []
        for i, g in enumerate(ex.map(_run, jobs)):
            parts.append(g)
            if i % 10 == 0:
                print(f"{i + 1}/{len(jobs)} scenarios, {time.time() - t0:.0f}s", flush=True)
    sims = pd.concat(parts, ignore_index=True)
    sims.to_parquet(OUT / "simulations.parquet", index=False)
    base = sims[sims["scenario_id"] == "base"]
    model = SC.fit(sims[sims["scenario_id"].str.startswith("train_")], base)
    SC.save(model, OUT / "emulator.json")
    val = SC.validate(model, sims[sims["scenario_id"].str.startswith(("holdout_", "preset_"))])
    val.to_csv(OUT / "emulator_validation.csv", index=False)
    print(val[["scenario_id", "total_sim_pct", "total_emulated_pct", "total_abs_err_pts", "family_mae_pts",
               "family_region_mae_pts"]].to_string(index=False))
    print("mean abs error (pts): total %.3f, family %.3f, family x region %.3f" % (
        val["total_abs_err_pts"].mean(), val["family_mae_pts"].mean(), val["family_region_mae_pts"].mean()))
    print(f"done in {time.time() - t0:.0f}s")
