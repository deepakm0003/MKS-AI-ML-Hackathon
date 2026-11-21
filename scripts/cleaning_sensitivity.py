"""Phase D - cleaning sensitivity of the champion (retrains; ~20 min per variant).

For every cleaning variant (robustness.VARIANTS) the champion spec is re-run on three
cutoffs and scored on the common yardstick (months whose truth no cleaning decision
touches), and the final model is re-trained to show how far the Nov 2026 - May 2028
forecast moves.

    python scripts/cleaning_sensitivity.py [variant ...]     # variants can run as parallel processes
    python scripts/cleaning_sensitivity.py --combine          # merge whatever has finished
      -> artifacts/reports/sensitivity/<variant>.json           (one per variant)
         artifacts/reports/cleaning_sensitivity.csv
         artifacts/reports/cleaning_sensitivity_forecast.csv
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from celeris.config import PROCESSED  # noqa: E402
from celeris.experiments import resolve  # noqa: E402
from celeris.features import Panel  # noqa: E402
from celeris.forecast import forecast_test, replacement_curves, train_final  # noqa: E402
from celeris.robustness import (VARIANTS, demand_variant, score_on_yardstick, variant_backtest,  # noqa: E402
                                yardstick)

CUTOFFS = ["2023-04", "2024-04", "2025-03"]
OUT = ROOT / "artifacts" / "reports"
PART = OUT / "sensitivity"
log = lambda *a: print(*a, flush=True)


def combine() -> None:
    parts = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(PART.glob("*.json"))]
    order = {v: i for i, v in enumerate(VARIANTS)}
    parts.sort(key=lambda d: order.get(d["score"]["Variant"], 99))
    res = pd.DataFrame([d["score"] for d in parts])
    res["WAPE_vs_baseline"] = res["WAPE"] - res.loc[res["Variant"] == "baseline", "WAPE"].iloc[0]
    res.round(4).to_csv(OUT / "cleaning_sensitivity.csv", index=False)
    f = pd.DataFrame([d["forecast"] for d in parts]).set_index("Variant")
    pct = (100 * (f / f.loc["baseline"] - 1)).round(2).add_suffix("_vs_base_pct")
    f.round(0).join(pct).reset_index().to_csv(OUT / "cleaning_sensitivity_forecast.csv", index=False)
    log(res[["Variant", "rows", "WAPE", "Bias", "WAPE_vs_baseline"]].round(4).to_string(index=False))
    log(f[["Total_19m"]].join(pct[["Total_19m_vs_base_pct"]]).round(2).to_string())


if "--combine" in sys.argv:
    combine()
    sys.exit()
PART.mkdir(parents=True, exist_ok=True)

rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
demand, sku, macro, evm, test = rd("demand"), rd("sku_master"), rd("macro"), rd("events_monthly"), rd("test")
bt = pd.read_parquet(ROOT / "outputs" / "backtest" / "backtest_predictions.parquet")
impact = pd.read_csv(ROOT / "outputs" / "anomalies" / "event_impact.csv")
ys = yardstick(demand)
spec = resolve("champion")


def forecast_totals(fc: pd.DataFrame) -> dict:
    fc = fc.assign(Year=fc["Date"].str[:4])
    out = {"Total_19m": fc["Forecast"].sum()}
    out.update({f"Year_{y}": v for y, v in fc.groupby("Year")["Forecast"].sum().items()})
    out.update({f"Fam_{f}": v for f, v in fc.groupby("Product_Family")["Forecast"].sum().items()})
    return out


# baseline = the frozen champion's own backtest and final forecast
champ = pd.read_parquet(ROOT / "artifacts" / "experiments" / "champion" / "predictions.parquet")
champ = champ[champ["cutoff"].isin(CUTOFFS)].rename(columns={"target_month": "Date"})
champ["Product_Family"] = champ["Product_Family"].astype(str)
(PART / "baseline.json").write_text(json.dumps({
    "score": {"Variant": "baseline", "Description": VARIANTS["baseline"], "Target_rows_changed": 0,
              "Weight_rows_changed": 0, **score_on_yardstick(champ, ys)},
    "forecast": {"Variant": "baseline",
                 **forecast_totals(pd.read_csv(ROOT / "outputs" / "forecast" / "forecast_detail.csv"))}},
    default=float), encoding="utf-8")

names = [a for a in sys.argv[1:] if not a.startswith("--")] or [v for v in VARIANTS if v != "baseline"]
for name in names:
    t0 = time.time()
    log(f"== variant {name}: {VARIANTS[name]}")
    dv = demand_variant(demand, name)
    changed = int((dv["Demand"].fillna(-1) != demand["Demand"].fillna(-1)).sum())
    wchg = int((dv["Train_Weight"] != demand["Train_Weight"]).sum())
    pred = variant_backtest(dv, spec, CUTOFFS, log)
    pred.to_parquet(ROOT / "artifacts" / "experiments" / f"sens_{name}.parquet", index=False)
    r = score_on_yardstick(pred, ys)
    log(f"   yardstick WAPE {r['WAPE']:.4f} bias {r['Bias']:+.4f}")
    P = Panel(dv, sku, macro, evm, test)
    model, cols, _ = train_final(P)
    fc, _ = forecast_test(P, model, cols, test, sku, dv, evm, impact, bt, replacement_curves(dv, sku))
    tot = forecast_totals(fc)
    (PART / f"{name}.json").write_text(json.dumps({
        "score": {"Variant": name, "Description": VARIANTS[name], "Target_rows_changed": changed,
                  "Weight_rows_changed": wchg, **r},
        "forecast": {"Variant": name, **tot}}, default=float), encoding="utf-8")
    log(f"   19-month total {tot['Total_19m']:,.0f}  [{(time.time() - t0) / 60:.1f} min]")
combine()
log("cleaning sensitivity done")
