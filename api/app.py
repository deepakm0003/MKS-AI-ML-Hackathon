"""Read-only API over the frozen backend (contracts/data_contract.yaml).

    uvicorn api.app:app --reload            # http://127.0.0.1:8000/docs

Every endpoint serves contract datasets only; nothing is computed or trained here, so the
frontend always shows exactly the frozen, validated outputs.
"""
from __future__ import annotations

import math
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from celeris.contract import dataset_path, load_contract, read_dataset  # noqa: E402

app = FastAPI(title="Celeris demand control tower API", version=load_contract()["version"],
              description="Frozen forecasts, accuracy, anomalies, data quality and planning intelligence.")


@lru_cache(maxsize=32)
def _load(name: str):
    if name not in load_contract()["datasets"]:
        raise HTTPException(404, f"unknown dataset {name}")
    if not dataset_path(name).exists():
        raise HTTPException(503, f"{name} not generated yet - run the pipeline")
    return read_dataset(name)


def _records(df: pd.DataFrame) -> list[dict]:
    rows = df.to_dict("records")
    return [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()} for r in rows]


def _filter(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    for col, val in filters.items():
        if col not in df.columns:
            raise HTTPException(400, f"unknown column {col}")
        df = df[df[col].astype(str) == val]
    return df


# ----------------------------------------------------------------------------- meta
@app.get("/health")
def health():
    m = _load("manifest")
    return {"status": "ok", "validation": m["validation"], "selected_model": m["selected_model"],
            "frozen_at": m["frozen_at"]}


@app.get("/contract")
def contract():
    return load_contract()


@app.get("/kpis")
def kpis():
    """Headline numbers for the landing view."""
    m, val = _load("manifest"), _load("validation_report")
    hier = _load("forecast_hierarchy")
    tot = hier[hier["Level"] == "total"]
    out = {"selected_model": m["selected_model"], "selection_reason": m["selection_reason"],
           "backtest_WAPE": m["backtest"]["WAPE"], "backtest_bias": m["backtest"]["Bias"],
           "family_month_WAPE": m["backtest"]["family_month_WAPE"],
           "total_month_WAPE": m["backtest"]["total_month_WAPE"],
           "forecast_total_19m": float(tot["Forecast"].sum()), "forecast_P10_19m": float(tot["P10"].sum()),
           "forecast_P90_19m": float(tot["P90"].sum()), "next12_vs_last12": val["facts"]["next12_vs_last12"],
           "validation": val["status"]}
    if dataset_path("intelligence_summary").exists():
        s = _load("intelligence_summary")
        out.update({"exceptions": s["exceptions"], "risk_level_counts": s["risk_level_counts"],
                    "market_headline": s["market_headline"]})
    return out


# ----------------------------------------------------------------------------- generic access
@app.get("/datasets")
def datasets():
    return {k: {"path": v["path"], "view": v.get("view"), "description": v.get("description", ""),
                "available": dataset_path(k).exists()} for k, v in load_contract()["datasets"].items()}


@app.get("/datasets/{name}")
def dataset(name: str, request: Request, limit: int = Query(1000, le=100000), offset: int = 0):
    """Any tabular contract dataset; other query parameters filter by exact column value,
    e.g. /datasets/exceptions?tier=ACT_NOW&Region=Europe"""
    d = _load(name)
    if isinstance(d, dict):
        return d
    filters = {k: v for k, v in request.query_params.items() if k not in ("limit", "offset")}
    d = _filter(d, filters)
    return {"total": len(d), "offset": offset, "rows": _records(d.iloc[offset: offset + limit])}


# ----------------------------------------------------------------------------- views
@app.get("/series/{sku_id}/{region}")
def series(sku_id: str, region: str):
    """History + forecast + signals for one SKU x Region (the drill-down view)."""
    fc = _load("forecast_detail")
    f = fc[(fc["SKU_ID"] == sku_id) & (fc["Region"] == region)]
    if f.empty:
        raise HTTPException(404, f"no forecast for {sku_id} / {region}")
    out = {"forecast": _records(f[["Date", "h", "Forecast", "P10", "P50", "P90", "Units_Sold_Forecast", "method"]])}
    if dataset_path("history").exists():
        h = _load("history")
        out["history"] = _records(h[(h["SKU_ID"] == sku_id) & (h["Region"] == region)]
                                  [["Date", "Units_Sold", "Demand", "Demand_Source", "Anomaly_Type"]])
    if dataset_path("series_signals").exists():
        s = _load("series_signals")
        s = s[(s["SKU_ID"] == sku_id) & (s["Region"] == region)]
        out["signals"] = _records(s)[0] if len(s) else None
    a = _load("anomaly_register")
    out["anomalies"] = _records(a[(a["SKU_ID"] == sku_id) & (a["Region"] == region)])
    return out


@app.get("/hierarchy")
def hierarchy_view(level: str = "total", member: str | None = None):
    h = _load("forecast_hierarchy")
    h = h[h["Level"] == level]
    if h.empty:
        raise HTTPException(404, f"unknown level {level}")
    if member:
        h = h[h["Member"] == member]
    return _records(h[["Member", "Date", "h", "Forecast", "P10", "P50", "P90"]])


# ----------------------------------------------------------------------------- planning intelligence
from pydantic import BaseModel, Field  # noqa: E402

INTEL = Path(__file__).resolve().parents[1] / "outputs" / "intelligence"
SCEN = Path(__file__).resolve().parents[1] / "artifacts" / "scenarios"


@lru_cache(maxsize=1)
def _report() -> dict:
    p = INTEL / "intelligence_report.json"
    if not p.exists():
        raise HTTPException(503, "planning intelligence not generated yet - run the intelligence stage")
    import json
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _cards() -> list:
    import json
    p = INTEL / "recommendations.json"
    if not p.exists():
        raise HTTPException(503, "recommendations not generated yet")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/intelligence/report")
def intelligence_report():
    """KPIs, executive briefing, top recommendations, segment matrix, capacity, market, scenario presets."""
    return _report()


@app.get("/intelligence/briefing")
def intelligence_briefing():
    r = _report()
    return {"kpis": r["kpis"], "briefing": r["briefing"]}


@app.get("/intelligence/recommendations")
def recommendations(priority: str | None = None, owner: str | None = None, level: str | None = None,
                    rule_id: str | None = None, q: str | None = None, limit: int = Query(50, le=1000)):
    """Ranked recommendation cards; filter by priority, owner (substring), level, rule or free text in scope."""
    c = _cards()
    if priority:
        c = [x for x in c if x["priority"] == priority.upper()]
    if owner:
        c = [x for x in c if owner.lower() in x["owner"].lower()]
    if level:
        c = [x for x in c if x["level"] == level]
    if rule_id:
        c = [x for x in c if x["rule_id"] == rule_id]
    if q:
        c = [x for x in c if q.lower() in x["scope"].lower()]
    return {"total": len(c), "cards": c[:limit]}


@lru_cache(maxsize=1)
def _scenario_ctx():
    if not (SCEN / "emulator.json").exists():
        raise HTTPException(503, "scenario emulator not built - run scripts/scenario_simulations.py")
    from celeris.intel import scenarios as SC
    return (SC, SC.load(SCEN / "emulator.json"), pd.read_csv(INTEL / "scenario_prices.csv"),
            pd.read_csv(INTEL / "capacity_check.csv"))


class ScenarioRequest(BaseModel):
    shocks: dict[str, float] = Field(default_factory=dict, description="pmi, auto_production, vehicle_orders, raw_material, ev_adoption")
    region_overlay: dict[str, float] = Field(default_factory=dict, description="planner assumption: % change by region")


@app.get("/scenario/config")
def scenario_config():
    SC, emu, _, _ = _scenario_ctx()
    return {"sliders": {k: {"column": v[0], "kind": v[1], "min": v[2], "max": v[3], "unit": v[4]} for k, v in SC.SHOCKS.items()},
            "presets": SC.PRESETS, "regions": sorted({c[1] for c in emu["cells"]})}


@app.get("/scenario/presets")
def scenario_presets():
    import json
    p = INTEL / "scenario_presets.json"
    if not p.exists():
        raise HTTPException(503, "scenario presets not generated yet")
    return json.loads(p.read_text(encoding="utf-8"))


@app.post("/scenario")
def scenario(req: ScenarioRequest):
    """Instant what-if: emulated re-forecast of the frozen model + optional region overlays."""
    SC, emu, price, cap = _scenario_ctx()
    unknown = set(req.shocks) - set(SC.SHOCKS)
    if unknown:
        raise HTTPException(400, f"unknown shocks {sorted(unknown)}")
    try:
        return SC.evaluate(emu, req.shocks, req.region_overlay, price=price, capacity=cap)
    except ValueError as e:
        raise HTTPException(400, str(e))
