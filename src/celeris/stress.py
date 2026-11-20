"""C0 - macro stress test of the final forecast (robustness analysis, not a model experiment).

The champion leans on the macro file: without macro features company-level error rises from
5.4% to 8.9%. For Nov 2026 - May 2028 those macro values are projections, so we ask: how
much does the forecast move if the projections are wrong?

Each scenario shifts the macro inputs for every forecast month (history untouched), rebuilds
the features and re-runs the complete forecast (same model, same lifecycle and event rules).
Shock semantics:
  * PMI / auto-production YoY: additive, persistent (e.g. PMI 3 points lower every month)
  * index series (new vehicle orders, raw material): level shift from Nov 2026 - the
    year-on-year signal the model uses therefore moves in the first 12 months only
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import HISTORY_END
from .features import Panel

SCENARIOS = {
    "PMI -3": {"ISM_Manufacturing_PMI": ("add", -3)},
    "PMI +3": {"ISM_Manufacturing_PMI": ("add", 3)},
    "Auto production YoY -2pp": {"Auto_Production_YoY_Pct": ("add", -2)},
    "Auto production YoY +2pp": {"Auto_Production_YoY_Pct": ("add", 2)},
    "New vehicle orders -5%": {"New_Vehicle_Orders_Index": ("mul", 0.95)},
    "New vehicle orders +5%": {"New_Vehicle_Orders_Index": ("mul", 1.05)},
    "Raw material cost +10%": {"Raw_Material_Cost_Index": ("mul", 1.10)},
    "EV adoption +5 pts": {"EV_Adoption_Index": ("add", 5)},
    "Combined downside": {"ISM_Manufacturing_PMI": ("add", -3), "Auto_Production_YoY_Pct": ("add", -2),
                          "New_Vehicle_Orders_Index": ("mul", 0.95), "Raw_Material_Cost_Index": ("mul", 1.10)},
    "Combined upside": {"ISM_Manufacturing_PMI": ("add", 3), "Auto_Production_YoY_Pct": ("add", 2),
                        "New_Vehicle_Orders_Index": ("mul", 1.05), "Raw_Material_Cost_Index": ("mul", 0.90)},
}


def shock(macro: pd.DataFrame, spec: dict) -> pd.DataFrame:
    m = macro.copy()
    fut = m["Date"] > HISTORY_END
    for col, (kind, v) in spec.items():
        m.loc[fut, col] = m.loc[fut, col] + v if kind == "add" else m.loc[fut, col] * v
    return m


def run_stress(inputs: dict, model: lgb.Booster, cols: list, forecast_fn, extra: dict) -> pd.DataFrame:
    """inputs: demand, sku, macro, events_monthly, test. forecast_fn = forecast.forecast_test."""
    rows = []
    base = None
    for name, spec in [("Base (macro file)", {})] + list(SCENARIOS.items()):
        mac = shock(inputs["macro"], spec)
        P = Panel(inputs["demand"], inputs["sku"], mac, inputs["events_monthly"], inputs["test"])
        fc, _ = forecast_fn(P, model, cols, inputs["test"], inputs["sku"], inputs["demand"],
                            inputs["events_monthly"], **extra)
        fc["Year"] = fc["Date"].str[:4]
        tot = fc["Forecast"].sum()
        fam = fc.groupby("Product_Family")["Forecast"].sum()
        yr = fc.groupby("Year")["Forecast"].sum()
        if base is None:
            base = {"tot": tot, "fam": fam, "yr": yr}
        row = {"Scenario": name, "Total_19m": round(tot), "Total_vs_base_pct": round(100 * (tot / base["tot"] - 1), 2)}
        row.update({f"{y}_vs_base_pct": round(100 * (yr[y] / base["yr"][y] - 1), 2) for y in yr.index})
        row.update({f"{f}_vs_base_pct": round(100 * (fam[f] / base["fam"][f] - 1), 2) for f in fam.index})
        rows.append(row)
    return pd.DataFrame(rows)
