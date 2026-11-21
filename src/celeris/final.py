"""Phase F - freeze the backend.

1. Model selection: the registry's best challenger that passes all promotion criteria, or
   the frozen champion when none does.
2. Final forecast Nov 2026 - May 2028 with the selected model: same lifecycle, launch,
   run-down and shutdown rules as stage 4, and the Phase D stratified P10/P50/P90 bands fitted on
   that model's own 6-cutoff backtest. If the champion is kept, its saved model file is
   reused, so the point forecast is the frozen champion's forecast.
3. Validation of every required SKU x Region x Month row and the business rules.
4. Export to outputs/final/ with a manifest (SHA-256 fingerprints) that the API and the
   frontend read through the data contract (contracts/data_contract.yaml).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import PROCESSED, RAW, ROOT
from .experiments import _cats, _cols, _fit_lgb, load_config, resolve
from .features import LAST_HIST, MIDX, MONTHS, Panel
from .forecast import band_coverage, forecast_test, hierarchy, replacement_curves
from .intervals import fit_ratio_quantiles

ART = ROOT / "artifacts"
OUT = ROOT / "outputs" / "final"
KEY = ["Date", "SKU_ID", "Region"]


# ----------------------------------------------------------------------------- 1. selection
def select_model(reg: pd.DataFrame | None = None) -> tuple[str, str]:
    reg = reg if reg is not None else pd.read_csv(ART / "registry" / "registry.csv")
    ok = reg[reg["verdict"].astype(str).str.startswith("PROMOTE")].sort_values("WAPE")
    champ = reg.loc[reg["experiment"] == "champion"].iloc[0]
    if len(ok):
        r = ok.iloc[0]
        return r["experiment"], (f"{r['experiment']} passes all promotion criteria: WAPE {r['WAPE']:.4f} vs "
                                 f"champion {champ['WAPE']:.4f}; {r['verdict']}")
    best = reg[reg["experiment"] != "champion"].sort_values("WAPE").iloc[0]
    return "champion", (f"no challenger passed all promotion criteria (best: {best['experiment']} "
                        f"WAPE {best['WAPE']:.4f} vs champion {champ['WAPE']:.4f}; {best['verdict']})")


# ----------------------------------------------------------------------------- 2. model + forecast
class Member:
    """One fitted model behind a common predict(DataFrame) interface (scale-free output)."""

    def __init__(self, model, cols: list, kind: str, cats: list | None = None):
        self.model, self.cols, self.kind, self.cats = model, cols, kind, cats or []

    def predict(self, X: pd.DataFrame):
        Z = X[self.cols]
        if self.kind == "catboost":
            Z = Z.assign(**{c: Z[c].astype(str) for c in self.cats})
        return self.model.predict(Z)

    def save(self, path: Path, stem: str) -> str:
        name = f"{stem}.cbm" if self.kind == "catboost" else f"{stem}.txt"
        self.model.save_model(str(path / name))
        return name


class Ensemble:
    """Weighted average of members (seed bags, blends); same interface as Booster.predict."""

    def __init__(self, members: list, weights: list | None = None):
        self.members = members
        self.weights = weights or [1 / len(members)] * len(members)

    @property
    def cols(self) -> list:
        out = []
        for m in self.members:
            out += [c for c in m.cols if c not in out]
        return out

    def predict(self, X):
        return np.sum([w * m.predict(X) for m, w in zip(self.members, self.weights)], axis=0)

    def save(self, path: Path) -> list[str]:
        return [m.save(path, f"final_model_{i}_{m.kind}") for i, m in enumerate(self.members)]


def load_inputs() -> dict:
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    return {n: rd(n) for n in ["demand", "sku_master", "macro", "events_monthly", "test"]}


def _training_frame(spec: dict, P: Panel) -> pd.DataFrame:
    first = MIDX[spec["train_first_origin"]]
    parts = []
    for o in range(first, LAST_HIST, spec["train_origin_step"]):
        f = P.frame(o)
        parts.append(f[f["target_idx"] <= LAST_HIST])
    train = pd.concat(parts, ignore_index=True)
    return train[(train["w"] > 0) & train["scale"].notna()]


def _members(name: str, P: Panel, cache: dict, log) -> tuple[list, list, int | None]:
    """Fitted members (and weights) for one experiment, trained on all history."""
    spec = resolve(name)
    if "blend" in spec:
        mem, wts, n = [], [], None
        for m, w in zip(spec["blend"]["members"], spec["blend"]["weights"]):
            ms, ws, n_m = _members(m, P, cache, log)
            mem += ms
            wts += [w * x for x in ws]
            n = n or n_m
        return mem, wts, n
    if name == "champion":                                   # frozen model file -> identical forecast
        card = json.loads((ROOT / "outputs" / "models" / "model_card.json").read_text(encoding="utf-8"))
        booster = lgb.Booster(model_file=str(ROOT / "outputs" / "models" / "lgb_global_tweedie.txt"))
        return [Member(booster, card["features"], "lgb")], [1.0], card.get("trained_rows")
    if spec.get("horizon_models") or spec.get("model", "lgb") not in ("lgb", "catboost"):
        raise NotImplementedError(f"final training for {name} is not wired up")
    key = (spec["feature_set"], spec["train_first_origin"], spec["train_origin_step"])
    if key not in cache:
        cache.clear()
        cache[key] = _training_frame(spec, P)
    train = cache[key]
    cols = _cols(spec, train)
    if spec.get("model", "lgb") == "catboost":
        from catboost import CatBoostRegressor, Pool
        cats = _cats(train, cols)
        log(f"training {name} (CatBoost) on {len(train):,} rows, {len(cols)} features")
        m = CatBoostRegressor(loss_function="Tweedie:variance_power=1.2", iterations=spec.get("cb_iterations", 1500),
                              learning_rate=0.08, depth=8, thread_count=16, random_seed=spec["seeds"][0], verbose=False)
        m.fit(Pool(train[cols].assign(**{c: train[c].astype(str) for c in cats}),
                   (train["y"] / train["scale"]).clip(upper=spec["target_clip"]), weight=train["scale"],
                   cat_features=cats))
        return [Member(m, cols, "catboost", cats)], [1.0], len(train)
    log(f"training {name} (LightGBM) on {len(train):,} rows, {len(cols)} features, seeds {spec['seeds']}")
    ms = [Member(_fit_lgb(spec, train, cols, s), cols, "lgb") for s in spec["seeds"]]
    return ms, [1 / len(ms)] * len(ms), len(train)


def train_selected(name: str, inp: dict, log=print):
    spec = resolve(name)
    P = Panel(inp["demand"], inp["sku_master"], inp["macro"], inp["events_monthly"], inp["test"],
              feature_set=spec["feature_set"])
    members, weights, n_train = _members(name, P, {}, log)
    model = Ensemble(members, weights)
    return model, model.cols, P, spec, n_train


def backtest_for_bands(name: str, demand: pd.DataFrame) -> pd.DataFrame:
    """The selected model's 6-cutoff backtest in the column layout forecast.py expects."""
    p = pd.read_parquet(ART / "experiments" / name / "predictions.parquet")
    ch = demand.groupby(["SKU_ID", "Region"])["Sales_Channel"].last()
    p["Sales_Channel"] = pd.MultiIndex.from_arrays([p["SKU_ID"], p["Region"].astype(str)]).map(ch)
    for c in ["Product_Family", "Region", "Customer_Name"]:
        p[c] = p[c].astype(str)
    return p.rename(columns={"f": "f_lgb_tweedie"})


# ----------------------------------------------------------------------------- 3. validation
def validate(fc: pd.DataFrame, sub: pd.DataFrame, hier: pd.DataFrame, inp: dict) -> dict:
    test = pd.read_csv(RAW / "test.csv")
    sku = inp["sku_master"].set_index("SKU_ID")
    eol, launch = fc["SKU_ID"].map(sku["EOL_Date"]), fc["SKU_ID"].map(sku["Launch_Date"])
    dead = (eol.notna() & (fc["Date"] > eol)) | (fc["Date"] < launch)
    tot = hier[hier["Level"] == "total"].set_index("Date")["Forecast"]
    hist = inp["demand"]
    last12 = hist[hist["Date"].isin(MONTHS[LAST_HIST - 11: LAST_HIST + 1])]["Demand"].sum()
    nxt12 = fc[fc["h"] <= 12]["Forecast"].sum()
    checks = {
        "row_count_matches_test": len(sub) == len(test),
        "keys_match_test_in_order": bool((sub[KEY].values == test[KEY].values).all()),
        "no_duplicate_keys": not sub.duplicated(KEY).any(),
        "no_missing_forecast": bool(sub["Units_Sold_Forecast"].notna().all()),
        "integer_forecast": bool(pd.api.types.is_integer_dtype(sub["Units_Sold_Forecast"])),
        "no_negative_forecast": bool((sub["Units_Sold_Forecast"] >= 0).all()),
        "zero_outside_lifecycle": bool((fc.loc[dead, "Units_Sold_Forecast"] == 0).all()),
        "bands_ordered": bool(((fc["P10"] <= fc["P50"] + 1e-9) & (fc["P50"] <= fc["P90"] + 1e-9)
                               & (fc["P10"] <= fc["Forecast"] + 1e-9) & (fc["Forecast"] <= fc["P90"] + 1e-9)).all()),
        "hierarchy_total_equals_sku_sum": bool(np.allclose(tot.sort_index(),
                                                           fc.groupby("Date")["Forecast"].sum().sort_index())),
        "next12_vs_last12_plausible": bool(0.8 <= nxt12 / last12 <= 1.3),
        "every_active_series_forecast": bool((fc.loc[~dead].groupby(["SKU_ID", "Region"])["Forecast"].sum() > 0).mean() > 0.99),
    }
    facts = {"rows": len(sub), "rows_zero_by_lifecycle": int(dead.sum()), "series": int(fc.groupby(["SKU_ID", "Region"]).ngroups),
             "total_19m": round(float(fc["Forecast"].sum())), "next12_vs_last12": round(float(nxt12 / last12 - 1), 4),
             "methods": fc["method"].str.split(";").str[0].value_counts().to_dict()}
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "facts": facts}


# ----------------------------------------------------------------------------- 4. export
def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def run_final(name: str | None = None, log=print) -> dict:
    t0 = time.time()
    inp = load_inputs()
    reason = "requested explicitly"
    if name is None:
        name, reason = select_model()
    log(f"selected model: {name} - {reason}")
    variant = resolve(name).get("demand_variant")
    if variant:                                   # C9-type model: same target, different training months
        from .robustness import demand_variant
        inp["demand"] = demand_variant(inp["demand"], variant).sort_index()
        log(f"training months from demand variant '{variant}'")
    model, cols, P, spec, n_train = train_selected(name, inp, log)
    bt = backtest_for_bands(name, inp["demand"])
    q = fit_ratio_quantiles(bt, "f_lgb_tweedie", strata=True)
    impact = pd.read_csv(ROOT / "outputs" / "anomalies" / "event_impact.csv")
    curves = replacement_curves(inp["demand"], inp["sku_master"])
    fc, notes = forecast_test(P, model, cols, inp["test"], inp["sku_master"], inp["demand"],
                              inp["events_monthly"], impact, bt, curves, band_q=q)
    sub = fc[KEY + ["Units_Sold_Forecast"]]
    hier = hierarchy(fc, bt)
    cov = band_coverage(bt)
    report = validate(fc, sub, hier, inp)

    OUT.mkdir(parents=True, exist_ok=True)
    sub.to_csv(OUT / "submission.csv", index=False)
    detail_cols = ["Date", "Year", "Month", "Product_Family", "Business_Unit", "SKU_ID", "SKU_Description",
                   "Customer_Name", "Sales_Channel", "Region", "h", "Forecast", "P10", "P50", "P90",
                   "Units_Sold_Forecast", "method"]
    fc[detail_cols].to_csv(OUT / "forecast_detail.csv", index=False)
    hier.to_csv(OUT / "forecast_hierarchy.csv", index=False)
    cov.to_csv(OUT / "band_coverage.csv", index=False)
    (OUT / "validation_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    met = json.loads((ART / "experiments" / name / "metrics.json").read_text(encoding="utf-8"))
    (OUT / "backtest_metrics.json").write_text(json.dumps(met, indent=2), encoding="utf-8")
    from .intel.pricing import history_revenue           # cleaned shipped revenue + unconstrained revenue
    hist = history_revenue(inp["demand"])[["Date", "SKU_ID", "Region", "Product_Family", "Customer_Name",
                                           "Sales_Channel", "Units_Sold", "Demand", "Revenue_shipped",
                                           "Revenue_unconstrained", "Demand_Source", "Anomaly_Type", "Train_Weight"]]
    hist.sort_values(["SKU_ID", "Region", "Date"]).to_csv(OUT / "history.csv", index=False)
    mdir = OUT / "model"
    mdir.mkdir(exist_ok=True)
    model_files = model.save(mdir)

    files = sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "manifest.json")
    cfg = load_config()
    manifest = {
        "frozen_at": time.strftime("%Y-%m-%d %H:%M"),
        "selected_model": name, "selection_reason": reason, "spec": spec,
        "features": cols, "trained_rows": n_train, "model_files": model_files,
        "model_weights": model.weights, "member_features": [m.cols for m in model.members],
        "demand_variant": variant,
        "history_end": MONTHS[LAST_HIST], "forecast_window": [MONTHS[LAST_HIST + 1], MONTHS[LAST_HIST + 19]],
        "backtest": {"cutoffs": cfg["evaluation"]["cutoffs"], **met["overall"],
                     "family_month_WAPE": met["family_month"]["WAPE"], "total_month_WAPE": met["total_month"]["WAPE"]},
        "bands": "stratified split-conformal (size bin x horizon bucket x young/established x volatile region), "
                 "fitted on the selected model's 6-cutoff backtest; aggregate bands from the level error model",
        "band_coverage_by_level": cov.groupby("Level")["Coverage_P10_P90"].mean().round(3).to_dict(),
        "lifecycle_rules": {k: v for k, v in notes.items() if not k.startswith(("CSS", "BSS", "THM", "PMP",
                                                                                "PTC", "HYD", "ELA"))},
        "validation": report["status"],
        "files_sha256_16": {str(p.relative_to(OUT)).replace("\\", "/"): sha(p) for p in files},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    log(f"final forecast frozen in {time.time() - t0:.0f}s: validation {report['status']}, "
        f"19-month total {report['facts']['total_19m']:,} units")
    return {"forecast": fc, "report": report, "manifest": manifest}


def load_final_model() -> tuple[Ensemble, list, dict]:
    """The frozen final model from outputs/final (for stress tests and re-scoring), its
    feature list and the manifest."""
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    members = []
    for f, cols in zip(man["model_files"], man["member_features"]):
        path = OUT / "model" / f
        if f.endswith(".cbm"):
            from catboost import CatBoostRegressor
            m = CatBoostRegressor()
            m.load_model(str(path))
            members.append(Member(m, cols, "catboost", [c for c in cols if c in ("Product_Family", "Region",
                                  "Customer_Name", "Sales_Channel", "Business_Unit", "Powertrain")]))
        else:
            members.append(Member(lgb.Booster(model_file=str(path)), cols, "lgb"))
    model = Ensemble(members, man["model_weights"])
    return model, model.cols, man
