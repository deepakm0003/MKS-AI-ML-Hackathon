"""Experiment runner and model registry.

Every experiment = the frozen champion spec + the overrides in config/experiments.yaml.
All experiments share the cleaned demand panel, the cutoffs, the 19-month horizon and the
metrics, so their numbers are directly comparable. Each run writes

  artifacts/experiments/<name>/predictions.parquet   every backtest forecast
  artifacts/experiments/<name>/metrics.json          headline + per-cutoff + per-segment
  artifacts/experiments/<name>/spec.yaml             the exact resolved spec
  artifacts/registry/registry.csv                    one row per experiment (leaderboard)
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import yaml

from .backtest import add_baselines
from .config import PROCESSED, ROOT
from .features import HORIZON, LAST_HIST, MIDX, MONTHS, Panel, feature_columns

CONFIG = ROOT / "config" / "experiments.yaml"
ART = ROOT / "artifacts"


# ----------------------------------------------------------------------------- spec
def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def resolve(name: str, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    spec = copy.deepcopy(cfg["champion"])
    if name != "champion":
        over = copy.deepcopy(cfg["experiments"][name])
        if "params" in over:
            spec["params"].update(over.pop("params"))
        spec.update(over)
    spec["name"] = name
    spec.setdefault("seeds", [spec["params"]["seed"]])
    return spec


# ----------------------------------------------------------------------------- data
class FrameStore:
    """Panels and per-origin feature frames, cached in memory per feature set."""

    def __init__(self):
        rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
        self.inputs = (rd("demand"), rd("sku_master"), rd("macro"), rd("events_monthly"), rd("test"))
        self.panels: dict = {}
        self.frames: dict = {}

    def panel(self, feature_set: str) -> Panel:
        if feature_set not in self.panels:
            self.panels[feature_set] = Panel(*self.inputs, feature_set=feature_set)
        return self.panels[feature_set]

    def frame(self, feature_set: str, o: int) -> pd.DataFrame:
        k = (feature_set, o)
        if k not in self.frames:
            self.frames[k] = self.panel(feature_set).frame(o, horizons=range(1, HORIZON + 1))
        return self.frames[k]

    def training(self, spec: dict, cutoff: int) -> pd.DataFrame:
        first = MIDX[spec["train_first_origin"]]
        parts = [self.frame(spec["feature_set"], o) for o in range(first, cutoff, spec["train_origin_step"])]
        df = pd.concat([p[p["target_idx"] <= cutoff] for p in parts], ignore_index=True)
        return df[(df["w"] > 0) & df["scale"].notna()]

    def evaluation(self, spec: dict, cutoff: int) -> pd.DataFrame:
        ev = self.frame(spec["feature_set"], cutoff)
        return ev[ev["target_idx"] <= LAST_HIST].copy()


# ----------------------------------------------------------------------------- models
def _cols(spec: dict, df: pd.DataFrame) -> list[str]:
    cols = feature_columns(df)
    for pre in spec.get("drop_feature_prefix", []):
        cols = [c for c in cols if not c.startswith(pre)]
    return cols


def _cats(df, cols):
    return [c for c in cols if str(df[c].dtype) == "category"]


def _scale(df):
    return df["scale"].fillna(df["mean_3"]).fillna(0).to_numpy()


def _fit_lgb(spec, train, cols, seed, objective=None, label=None, weight=None):
    params = {**spec["params"], "seed": seed}
    if objective:
        params = {k: v for k, v in params.items() if k != "tweedie_variance_power"}
        params["objective"] = objective
    y = label if label is not None else (train["y"] / train["scale"]).clip(upper=spec["target_clip"])
    w = weight if weight is not None else train["scale"]
    ds = lgb.Dataset(train[cols], y, weight=w, categorical_feature=_cats(train, cols), free_raw_data=False)
    return lgb.train(params, ds, num_boost_round=spec["rounds"])


def fit_predict(spec: dict, train: pd.DataFrame, ev: pd.DataFrame) -> tuple[np.ndarray, dict]:
    cols = _cols(spec, train)
    info = {"n_features": len(cols), "n_train": len(train)}
    model = spec.get("model", "lgb")
    ranges = spec.get("horizon_models") or [[1, HORIZON]]
    pred = np.zeros(len(ev))
    for lo, hi in ranges:
        tr = train[train["h"].between(lo, hi)]
        m_ev = ev["h"].between(lo, hi).to_numpy()
        if not m_ev.any():
            continue
        E = ev[m_ev]
        if model == "lgb":
            r = np.mean([_fit_lgb(spec, tr, cols, s).predict(E[cols]) for s in spec["seeds"]], axis=0)
            pred[m_ev] = r * _scale(E)
        elif model == "hurdle":
            occ = (tr["y"] > 0).astype(float)
            clf = _fit_lgb(spec, tr, cols, spec["seeds"][0], "binary", occ, np.ones(len(tr)))
            pos = tr[tr["y"] > 0]
            reg = _fit_lgb(spec, pos, cols, spec["seeds"][0], "regression",
                           (pos["y"] / pos["scale"]).clip(upper=spec["target_clip"]), pos["scale"])
            pred[m_ev] = clf.predict(E[cols]) * reg.predict(E[cols]) * _scale(E)
        elif model == "catboost":
            from catboost import CatBoostRegressor, Pool
            cats = _cats(tr, cols)
            prep = lambda d: d[cols].assign(**{c: d[c].astype(str) for c in cats})
            m = CatBoostRegressor(loss_function="Tweedie:variance_power=1.2", iterations=spec.get("cb_iterations", 1500),
                                  learning_rate=0.08, depth=8, thread_count=16, random_seed=spec["seeds"][0],
                                  verbose=False)
            m.fit(Pool(prep(tr), (tr["y"] / tr["scale"]).clip(upper=spec["target_clip"]),
                       weight=tr["scale"], cat_features=cats))
            pred[m_ev] = m.predict(Pool(prep(E), cat_features=cats)) * _scale(E)
        else:
            raise ValueError(model)
    return np.clip(pred, 0, None), info


# ----------------------------------------------------------------------------- metrics
def _m(y, f):
    y, f = np.asarray(y, float), np.asarray(f, float)
    s = max(np.abs(y).sum(), 1e-9)
    return {"WAPE": float(np.abs(f - y).sum() / s), "Bias": float((f - y).sum() / s),
            "MAE": float(np.abs(f - y).mean()), "RMSE": float(np.sqrt(((f - y) ** 2).mean()))}


def metrics(pred: pd.DataFrame, col: str, buckets) -> dict:
    out = {"overall": _m(pred["y"], pred[col])}
    out["by_cutoff"] = {c: _m(g["y"], g[col]) for c, g in pred.groupby("cutoff")}
    out["by_horizon_bucket"] = {f"{lo}-{hi}m": _m(g["y"], g[col])
                                for lo, hi in buckets for g in [pred[pred["h"].between(lo, hi)]]}
    for seg in ["Product_Family", "Region", "Demand_Class", "Volume_Band", "Lifecycle"]:
        out[f"by_{seg}"] = {str(k): _m(g["y"], g[col]) for k, g in pred.groupby(seg)}
    fam = pred.groupby(["cutoff", "Product_Family", "target_month"])[["y", col]].sum()
    out["family_month"] = _m(fam["y"], fam[col])
    tot = pred.groupby(["cutoff", "target_month"])[["y", col]].sum()
    out["total_month"] = _m(tot["y"], tot[col])
    return out


def _segments(ev: pd.DataFrame, P: Panel) -> pd.DataFrame:
    prof = pd.read_parquet(PROCESSED / "series_profile.parquet").set_index(["SKU_ID", "Region"])
    k = P.keys.iloc[ev["series"].to_numpy()]
    idx = pd.MultiIndex.from_arrays([k["SKU_ID"], k["Region"]])
    ev["SKU_ID"] = k["SKU_ID"].to_numpy()
    ev["Demand_Class"] = prof["Demand_Class"].reindex(idx).fillna("sparse").to_numpy()
    vol = ev.groupby("series")["mean_12"].transform("first")
    ev["Volume_Band"] = pd.qcut(vol.rank(method="first"), 5, labels=["Q1 low", "Q2", "Q3", "Q4", "Q5 high"]).astype(str)
    ev["Lifecycle"] = np.select([ev["age"] < 24, ev["trend_12"] < 0.8, ev["months_to_eol"] < 60],
                                ["new (<24m)", "declining", "approaching EOL"], "established")
    return ev


# ----------------------------------------------------------------------------- runner
def run(name: str, store: FrameStore | None = None, verbose=True) -> dict:
    cfg = load_config()
    spec = resolve(name, cfg)
    ev_cfg = cfg["evaluation"]
    store = store or FrameStore()
    P = store.panel(spec["feature_set"])
    t0 = time.time()
    preds, infos = [], {}
    for C in ev_cfg["cutoffs"]:
        c = MIDX[C]
        t1 = time.time()
        train, ev = store.training(spec, c), store.evaluation(spec, c)
        f, info = fit_predict(spec, train, ev)
        ev = add_baselines(ev, P, c)
        keep = ev[["series", "h", "target_idx", "y", "w", "Product_Family", "Region", "Customer_Name",
                   "mean_12", "age", "trend_12", "months_to_eol", "f_naive_seasonal"]].copy()
        keep["f"] = f
        keep["cutoff"] = C
        keep["target_month"] = [MONTHS[i] for i in keep["target_idx"]]
        preds.append(_segments(keep, P))
        infos[C] = {**info, "seconds": round(time.time() - t1)}
        if verbose:
            m = _m(keep["y"], keep["f"])
            print(f"  [{name}] {C}: WAPE {m['WAPE']:.4f} bias {m['Bias']:+.4f} "
                  f"({info['n_train']:,} rows, {info['n_features']} feats, {time.time()-t1:.0f}s)", flush=True)
    pred = pd.concat(preds, ignore_index=True)
    met = metrics(pred, "f", ev_cfg["horizon_buckets"])
    met["seasonal_naive_overall"] = _m(pred["y"], pred["f_naive_seasonal"])
    met["train_info"] = infos
    met["minutes"] = round((time.time() - t0) / 60, 1)

    d = ART / "experiments" / name
    d.mkdir(parents=True, exist_ok=True)
    pred.to_parquet(d / "predictions.parquet", index=False)
    (d / "metrics.json").write_text(json.dumps(met, indent=2), encoding="utf-8")
    (d / "spec.yaml").write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    update_registry(name, spec, met, cfg)
    return met


def update_registry(name: str, spec: dict, met: dict, cfg: dict) -> pd.DataFrame:
    reg_path = ART / "registry" / "registry.csv"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg = pd.read_csv(reg_path) if reg_path.exists() else pd.DataFrame()
    o = met["overall"]
    row = {"experiment": name, "description": spec.get("description", ""),
           "WAPE": round(o["WAPE"], 4), "Bias": round(o["Bias"], 4), "MAE": round(o["MAE"], 3),
           "RMSE": round(o["RMSE"], 3),
           **{f"WAPE_{k}": round(v["WAPE"], 4) for k, v in met["by_horizon_bucket"].items()},
           **{f"WAPE_{k}": round(v["WAPE"], 4) for k, v in met["by_cutoff"].items()},
           "WAPE_std_cutoffs": round(float(np.std([v["WAPE"] for v in met["by_cutoff"].values()])), 4),
           "WAPE_family_month": round(met["family_month"]["WAPE"], 4),
           "WAPE_total_month": round(met["total_month"]["WAPE"], 4),
           "minutes": met["minutes"], "run_at": time.strftime("%Y-%m-%d %H:%M")}
    if len(reg):
        reg = reg[reg["experiment"] != name]
    reg = pd.concat([reg, pd.DataFrame([row])], ignore_index=True)
    reg = add_promotion_verdicts(reg, cfg)
    reg.to_csv(reg_path, index=False)
    return reg


def _segment_metrics(name: str) -> dict | None:
    f = ART / "experiments" / name / "metrics.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def add_promotion_verdicts(reg: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Six promotion criteria (all must hold):
      1. mean WAPE gain >= min_mean_wape_gain over the same cutoffs
      2. no horizon bucket worse by more than max_bucket_loss
      3. bias controlled: |bias| not worse by more than max_abs_bias_increase
      4. wins >= min_share_cutoffs_won of cutoffs and no cutoff worse than max_single_cutoff_loss
      5. no family / region / new-series segment worse by more than max_segment_loss
      6. tests + leakage audit pass (checked by the test suite, not here)"""
    if "champion" not in set(reg["experiment"]):
        return reg
    rule = cfg["evaluation"]["promotion"]
    champ = reg[reg["experiment"] == "champion"].iloc[0]
    cut_cols = [f"WAPE_{c}" for c in cfg["evaluation"]["cutoffs"]]
    bucket_cols = [f"WAPE_{lo}-{hi}m" for lo, hi in cfg["evaluation"]["horizon_buckets"]]
    cm = _segment_metrics("champion")
    verdicts = []
    for _, r in reg.iterrows():
        if r["experiment"] == "champion":
            verdicts.append("CHAMPION")
            continue
        fails = []
        gain = champ["WAPE"] - r["WAPE"]
        if gain < rule["min_mean_wape_gain"]:
            fails.append(f"gain {gain:+.4f}")
        bdiff = min([champ[c] - r[c] for c in bucket_cols if c in r and pd.notna(r[c])] or [0.0])
        if bdiff < -rule.get("max_bucket_loss", 1):
            fails.append(f"horizon bucket {bdiff:+.4f}")
        if abs(r.get("Bias", 0)) - abs(champ.get("Bias", 0)) > rule.get("max_abs_bias_increase", 1):
            fails.append(f"bias {r['Bias']:+.3f}")
        diff = np.array([champ[c] - r[c] for c in cut_cols])
        won = float((diff > 0).mean())
        if won < rule["min_share_cutoffs_won"] or diff.min() < -rule["max_single_cutoff_loss"]:
            fails.append(f"won {won:.0%} of cutoffs, worst {diff.min():+.4f}")
        em = _segment_metrics(r["experiment"])
        if cm and em:
            worst = []
            for seg in ["by_Product_Family", "by_Region"]:
                for k, v in cm[seg].items():
                    if k in em[seg]:
                        worst.append((em[seg][k]["WAPE"] - v["WAPE"], k))
            new_c, new_e = cm["by_Lifecycle"].get("new (<24m)"), em["by_Lifecycle"].get("new (<24m)")
            if new_c and new_e:
                worst.append((new_e["WAPE"] - new_c["WAPE"], "new series"))
            d, k = max(worst) if worst else (0.0, "")
            if d > rule.get("max_segment_loss", 1):
                fails.append(f"segment {k} {d:+.4f}")
        head = "PROMOTE" if not fails else "reject: " + "; ".join(fails)
        verdicts.append(f"{head} | gain {gain:+.4f}, won {won:.0%}, worst cutoff {diff.min():+.4f}")
    reg["verdict"] = verdicts
    return reg
