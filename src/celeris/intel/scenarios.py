"""Scenario Lab engine - macro what-if on the frozen final model, served instantly.

1. Simulation (slow, offline): the frozen model re-forecasts the full 19-month window under
   sampled macro shocks (Latin-hypercube over the slider ranges) plus the named stress
   scenarios - same features, lifecycle and event rules as the final forecast.
2. Emulator: per family x region x month, log(scenario / base) is fitted on the shocks with
   linear, squared, cubic and pairwise terms and no intercept (ridge), so zero shocks reproduce
   the frozen forecast exactly. Validated on held-out simulated scenarios.
3. Evaluate (instant, used by the API): emulated family x region x month demand x optional
   region overlays (a planner's judgemental assumption, applied after the model and labelled
   as such), revenue from the price book, a capacity re-check against demonstrated
   throughput, and rule-based planning risks and responses.

Shock semantics as in celeris.stress: PMI, auto production and EV adoption additive points;
new-vehicle orders and raw-material cost multiplicative; applied to every forecast month.
"""
from __future__ import annotations

import json
from itertools import combinations

import numpy as np
import pandas as pd

from ..config import HISTORY_END

SHOCKS = {   # name: (macro column, kind, low, high, unit)
    "pmi": ("ISM_Manufacturing_PMI", "add", -6.0, 6.0, "points"),
    "auto_production": ("Auto_Production_YoY_Pct", "add", -5.0, 5.0, "pp YoY"),
    "vehicle_orders": ("New_Vehicle_Orders_Index", "mul", -12.0, 12.0, "%"),
    "raw_material": ("Raw_Material_Cost_Index", "mul", -20.0, 20.0, "%"),
    "ev_adoption": ("EV_Adoption_Index", "add", -10.0, 10.0, "points"),
}
NAMES = list(SHOCKS)
PRESETS = {
    "Base case": {},
    "Downside": {"pmi": -3, "auto_production": -2, "vehicle_orders": -5, "raw_material": 10},
    "Upside": {"pmi": 3, "auto_production": 2, "vehicle_orders": 5, "raw_material": -10},
    "PMI -3": {"pmi": -3},
    "Auto slowdown": {"auto_production": -4, "vehicle_orders": -8},
    "Raw-material spike": {"raw_material": 20},
    "EV acceleration": {"ev_adoption": 8},
}


def shock_macro(macro: pd.DataFrame, shocks: dict) -> pd.DataFrame:
    m = macro.copy()
    fut = m["Date"] > HISTORY_END
    for k, v in shocks.items():
        col, kind = SHOCKS[k][0], SHOCKS[k][1]
        m.loc[fut, col] = m.loc[fut, col] + v if kind == "add" else m.loc[fut, col] * (1 + v / 100)
    return m


def sample(n: int, seed: int = 0) -> list[dict]:
    """Latin-hypercube sample over the slider ranges."""
    rng = np.random.default_rng(seed)
    cols = []
    for k in NAMES:
        lo, hi = SHOCKS[k][2], SHOCKS[k][3]
        u = (rng.permutation(n) + rng.random(n)) / n
        cols.append(lo + u * (hi - lo))
    return [{k: round(float(c[i]), 3) for k, c in zip(NAMES, cols)} for i in range(n)]


# ----------------------------------------------------------------------------- emulator
def _norm(shocks: dict) -> np.ndarray:
    return np.array([shocks.get(k, 0.0) / max(abs(SHOCKS[k][2]), abs(SHOCKS[k][3])) for k in NAMES])


def design(shocks_list: list[dict]) -> np.ndarray:
    X = np.array([_norm(s) for s in shocks_list])
    # no intercept: zero shocks mean zero change (log ratio 0) by construction
    cols = [X[:, i] for i in range(X.shape[1])] + [X[:, i] ** 2 for i in range(X.shape[1])]
    cols += [X[:, i] ** 3 for i in range(X.shape[1])]
    cols += [X[:, i] * X[:, j] for i, j in combinations(range(X.shape[1]), 2)]
    return np.column_stack(cols)


def fit(sims: pd.DataFrame, base: pd.DataFrame, ridge: float = 1e-3) -> dict:
    """sims: scenario_id, <shock cols>, Product_Family, Region, Date, Forecast; base: same cells, scenario 'base'."""
    cells = base.set_index(["Product_Family", "Region", "Date"])["Forecast"]
    scen = sims.drop_duplicates("scenario_id").set_index("scenario_id")[NAMES]
    Y = sims.pivot_table(index="scenario_id", columns=["Product_Family", "Region", "Date"], values="Forecast")
    Y = Y.reindex(index=scen.index, columns=cells.index)
    L = np.log(np.clip(Y.to_numpy(), 1e-6, None) / np.clip(cells.to_numpy(), 1e-6, None))
    X = design(scen.to_dict("records"))
    B = np.linalg.solve(X.T @ X + ridge * np.eye(X.shape[1]), X.T @ L)
    return {"cells": [list(c) for c in cells.index], "base": cells.round(4).tolist(), "coef": B.round(6).tolist(),
            "terms": X.shape[1], "trained_on": int(len(scen)), "shock_ranges": {k: SHOCKS[k][2:] for k in NAMES}}


def predict_cells(model: dict, shocks: dict) -> pd.DataFrame:
    B = np.array(model["coef"])
    mult = np.exp(design([shocks]) @ B)[0]   # no intercept, so zero shocks return the frozen forecast exactly
    idx = pd.MultiIndex.from_tuples([tuple(c) for c in model["cells"]], names=["Product_Family", "Region", "Date"])
    base = np.array(model["base"])
    return pd.DataFrame({"Base": base, "Scenario": base * mult}, index=idx).reset_index()


def validate(model: dict, holdout: pd.DataFrame) -> pd.DataFrame:
    """Emulated vs simulated % change for held-out scenarios at three levels."""
    rows = []
    base = pd.DataFrame({"k": [tuple(c) for c in model["cells"]], "b": model["base"]})
    btot = base["b"].sum()
    for sid, g in holdout.groupby("scenario_id"):
        shocks = g.iloc[0][NAMES].to_dict()
        e = predict_cells(model, shocks)
        sim = g.set_index(["Product_Family", "Region", "Date"])["Forecast"]
        e["Sim"] = sim.reindex(pd.MultiIndex.from_frame(e[["Product_Family", "Region", "Date"]])).to_numpy()
        tot_sim, tot_emu = e["Sim"].sum() / btot - 1, e["Scenario"].sum() / btot - 1
        fam = e.groupby("Product_Family")[["Base", "Scenario", "Sim"]].sum()
        fr = e.groupby(["Product_Family", "Region"])[["Base", "Scenario", "Sim"]].sum()
        rows.append({"scenario_id": sid, **{k: shocks[k] for k in NAMES},
                     "total_sim_pct": 100 * tot_sim, "total_emulated_pct": 100 * tot_emu,
                     "total_abs_err_pts": 100 * abs(tot_sim - tot_emu),
                     "family_mae_pts": 100 * float(((fam["Scenario"] - fam["Sim"]) / fam["Base"]).abs().mean()),
                     "family_region_mae_pts": 100 * float(((fr["Scenario"] - fr["Sim"]) / fr["Base"]).abs().mean())})
    return pd.DataFrame(rows).round(3)


# ----------------------------------------------------------------------------- evaluate (API)
def simulated_cells(sims: pd.DataFrame, scenario_id: str) -> pd.DataFrame:
    """Exact model result of a simulated scenario in the emulator's cell layout."""
    base = sims[sims["scenario_id"] == "base"].set_index(["Product_Family", "Region", "Date"])["Forecast"]
    sc = sims[sims["scenario_id"] == scenario_id].set_index(["Product_Family", "Region", "Date"])["Forecast"]
    return pd.DataFrame({"Base": base, "Scenario": sc.reindex(base.index)}).reset_index()


def evaluate(model: dict, shocks: dict, region_overlay: dict | None = None, price: pd.DataFrame | None = None,
             capacity: pd.DataFrame | None = None, cells: pd.DataFrame | None = None) -> dict:
    """cells: exact simulated result (simulated_cells) - used for presets instead of the emulator."""
    shocks = {k: float(v) for k, v in (shocks or {}).items() if k in SHOCKS}
    for k, v in shocks.items():
        lo, hi = SHOCKS[k][2], SHOCKS[k][3]
        if not lo <= v <= hi:
            raise ValueError(f"{k}={v} outside the simulated range [{lo}, {hi}]")
    e = cells.copy() if cells is not None else predict_cells(model, shocks)
    region_overlay = {k: float(v) for k, v in (region_overlay or {}).items()}
    if region_overlay:
        e["Scenario"] *= 1 + e["Region"].map(region_overlay).fillna(0.0) / 100
    if price is not None:
        p = price.set_index(["Product_Family", "Region", "Date"])["Avg_price"]
        k = pd.MultiIndex.from_frame(e[["Product_Family", "Region", "Date"]])
        e["Price"] = p.reindex(k).to_numpy()
        e["Base_revenue"], e["Scenario_revenue"] = e["Base"] * e["Price"], e["Scenario"] * e["Price"]

    def by(col):
        g = e.groupby(col)[["Base", "Scenario"] + (["Base_revenue", "Scenario_revenue"] if price is not None else [])].sum()
        g["Change_pct"] = 100 * (g["Scenario"] / g["Base"] - 1)
        g["Change_units"] = g["Scenario"] - g["Base"]
        return g.round(2).reset_index()

    fam, reg, mon = by("Product_Family"), by("Region"), by("Date")
    tot_b, tot_s = e["Base"].sum(), e["Scenario"].sum()
    out = {"shocks": shocks, "region_overlay": region_overlay,
           "method": "exact model re-forecast (simulated)" if cells is not None else
                     "emulator of the model (mean held-out error about 0.6 pts on the company total)",
           "total": {"base_units": round(tot_b), "scenario_units": round(tot_s),
                     "change_units": round(tot_s - tot_b), "change_pct": round(100 * (tot_s / tot_b - 1), 2)},
           "by_family": fam.to_dict("records"), "by_region": reg.to_dict("records"), "by_month": mon.to_dict("records")}
    if price is not None:
        rb, rs = e["Base_revenue"].sum(), e["Scenario_revenue"].sum()
        out["total"].update({"base_revenue": round(rb), "scenario_revenue": round(rs), "change_revenue": round(rs - rb)})
    risks = []
    if capacity is not None:
        cap = capacity.set_index(["Product_Family", "Region"])["Demonstrated_3m_throughput"]
        piv = e.pivot_table(index=["Product_Family", "Region"], columns="Date", values="Scenario", aggfunc="sum")
        load = piv.T.rolling(3).sum().T.max(1)
        util = (load / cap.reindex(load.index)).dropna()
        base_piv = e.pivot_table(index=["Product_Family", "Region"], columns="Date", values="Base", aggfunc="sum")
        base_util = (base_piv.T.rolling(3).sum().T.max(1) / cap.reindex(load.index)).dropna()
        for k, u in util.sort_values(ascending=False).items():
            if u > 1.0:
                risks.append({"type": "CAPACITY", "scope": f"{k[0]} | {k[1]}", "utilisation_pct": round(100 * u, 1),
                              "base_utilisation_pct": round(100 * base_util.get(k, np.nan), 1)})
        out["capacity"] = [{"Product_Family": k[0], "Region": k[1], "Utilisation_pct": round(100 * v, 1)}
                           for k, v in util.items()]
    for _, r in fam.iterrows():
        if r["Change_pct"] <= -5:
            risks.append({"type": "DEMAND_DROP", "scope": r["Product_Family"], "change_pct": r["Change_pct"]})
        elif r["Change_pct"] >= 5:
            risks.append({"type": "DEMAND_RISE", "scope": r["Product_Family"], "change_pct": r["Change_pct"]})
    out["planning_risks"] = risks
    out["responses"] = responses(out)
    return out


def responses(res: dict) -> list[str]:
    """Rule-based planner responses to a scenario result (numbers from the result only)."""
    t = res["total"]["change_pct"]
    out = []
    if t <= -3:
        out.append(f"Demand {t:+.1f}% vs base: slow purchase-order releases to the scenario forecast, "
                   f"keep safety stock only on A-class items, and review fixed supplier commitments.")
    elif t >= 3:
        out.append(f"Demand {t:+.1f}% vs base: confirm supplier capacity for the extra "
                   f"{res['total']['change_units']:,} units and bring forward orders for long-lead parts.")
    else:
        out.append(f"Demand {t:+.1f}% vs base: within normal forecast error (company-month WAPE about 5%); "
                   f"no change to the plan needed.")
    cap = [r for r in res["planning_risks"] if r["type"] == "CAPACITY"]
    new_cap = [r for r in cap if r["base_utilisation_pct"] <= 100]
    if new_cap:
        names = ", ".join(r["scope"] for r in new_cap[:4])
        out.append(f"{len(new_cap)} family-region(s) move above demonstrated throughput in this scenario ({names}): "
                   f"plan overtime or pre-build before their peak windows.")
    drops = [r for r in res["planning_risks"] if r["type"] == "DEMAND_DROP"]
    if drops:
        worst = min(drops, key=lambda r: r["change_pct"])
        out.append(f"Most exposed family: {worst['scope']} ({worst['change_pct']:+.1f}%) - prioritise it in the "
                   f"inventory and capacity review.")
    return out


def save(model: dict, path) -> None:
    path.write_text(json.dumps(model), encoding="utf-8")


def load(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
