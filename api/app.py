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

from api.explorer import router as explorer_router  # noqa: E402
from api.views import router as views_router  # noqa: E402

app.include_router(views_router)
app.include_router(explorer_router)


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
    if dataset_path("series_profile").exists():
        p = _load("series_profile")
        p = p[(p["SKU_ID"] == sku_id) & (p["Region"] == region)]
        out["profile"] = _records(p)[0] if len(p) else None
    if dataset_path("sku_lifecycle").exists():
        lc = _load("sku_lifecycle")
        lc = lc[lc["SKU_ID"] == sku_id]
        out["lifecycle"] = _records(lc)[0] if len(lc) else None
    if dataset_path("series_risk").exists():
        r = _load("series_risk")
        r = r[(r["SKU_ID"] == sku_id) & (r["Region"] == region)]
        keep = [c for c in r.columns if c.startswith("risk_") or c in (
            "confidence", "Segment", "Service_level", "backtest_wape", "backtest_bias", "forecast_status",
            "reason_codes", "recommendation", "revenue_next12", "revenue_downside_next12", "revenue_upside_next12")]
        out["risk"] = _records(r[keep])[0] if len(r) else None
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
                    rule_id: str | None = None, q: str | None = None, limit: int = Query(50, le=1000),
                    family: str | None = None, sku: str | None = None, region: str | None = None,
                    channel: str | None = None, customer: str | None = None):
    """Ranked recommendation cards; filter by priority, owner (substring), level, rule, free text in
    scope, and the global filters (family, sku, region, channel, customer; '|' for several values).
    With global filters, each card gets `match`: "direct" (its scope is inside the selection) or
    "context" (a broader card - e.g. a family-wide signal while one region is selected); cards whose
    scope lies outside the selection are dropped. Direct matches come first."""
    from api.views import parse_filters
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
    f = parse_filters(family, sku, region, channel, customer)
    if f:
        allowed = _allowed_values(f)
        out = []
        for x in c:
            m = _card_match(x, f, allowed)
            if m:
                out.append({**x, "match": m})
        c = [x for x in out if x["match"] == "direct"] + [x for x in out if x["match"] == "context"]
    by_priority = {}
    for x in c:
        by_priority[x["priority"]] = by_priority.get(x["priority"], 0) + 1
    direct = sum(1 for x in c if x.get("match", "direct") == "direct")
    return {"total": len(c), "direct": direct, "by_priority": by_priority, "cards": c[:limit]}


@lru_cache(maxsize=1)
def _channel_of() -> dict:
    fc = _load("forecast_detail")
    return fc.drop_duplicates(["SKU_ID", "Region"]).set_index(["SKU_ID", "Region"])["Sales_Channel"].to_dict()


def _card_scope(card: dict) -> dict:
    """The planning dimensions a card is about, read from its evidence."""
    e = card.get("evidence") or {}
    d = {k: e[k] for k in ("family", "region", "sku", "customer") if e.get(k)}
    lvl, member = e.get("segment_level"), e.get("member")
    if lvl and member:
        if lvl == "family":
            d["family"] = member
        elif lvl == "region":
            d["region"] = member
        elif lvl == "family_region" and " | " in member:
            d["family"], d["region"] = member.split(" | ", 1)
    if "sku" in d and "region" in d:
        ch = _channel_of().get((d["sku"], d["region"]))
        if ch:
            d["channel"] = ch
    return d


def _allowed_values(f: dict) -> dict:
    """Values of every dimension that co-occur with the selection in the valid combinations
    (a SKU filter implies its family, regions, channels and customers)."""
    o = _filter_options()
    names = {"sku": [s["id"] for s in o["skus"]], "region": o["regions"], "channel": o["channels"],
             "customer": o["customers"]}
    fam_of = {s["id"]: o["families"][s["family"]] for s in o["skus"]}
    allowed = {k: set() for k in ("family", "sku", "region", "channel", "customer")}
    for si, ri, ci, ui in o["combos"]:
        row = {"sku": names["sku"][si], "region": names["region"][ri], "channel": names["channel"][ci],
               "customer": names["customer"][ui]}
        row["family"] = fam_of[row["sku"]]
        if all(row[d] in v for d, v in f.items()):
            for d in allowed:
                allowed[d].add(row[d])
    return allowed


def _card_match(card: dict, f: dict, allowed: dict) -> str | None:
    scope = _card_scope(card)
    if any(v not in allowed.get(d, {v}) for d, v in scope.items()):
        return None
    return "direct" if all(dim in scope for dim in f) else "context"


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


# ----------------------------------------------------------------------------- static files (production deployment)
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

DIST = Path(__file__).resolve().parents[1] / "dashboard" / "dist"

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")

    @app.get("/", response_class=FileResponse)
    def serve_root():
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}", response_class=FileResponse)
    def serve_spa(path: str):
        """Serve static files, fallback to index.html for SPA routing."""
        file = DIST / path
        if file.exists() and file.is_file():
            return FileResponse(file)
        # SPA fallback for /overview, /scenarios, etc.
        return FileResponse(DIST / "index.html")


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


# ----------------------------------------------------------------------------- shared filter options
@lru_cache(maxsize=1)
def _filter_options() -> dict:
    """Every valid (family, SKU, region, channel, customer) combination in the recent history and
    the forecast, index-encoded, so the global filter bar can cascade without extra calls."""
    cols = ["Product_Family", "SKU_ID", "Region", "Sales_Channel", "Customer_Name"]
    fc = _load("forecast_detail")
    frames = [fc[cols + ["SKU_Description"]]]
    if dataset_path("history").exists():
        h = _load("history")
        h = h[h["Date"] >= "2024-01"].merge(fc[["SKU_ID", "SKU_Description"]].drop_duplicates(), on="SKU_ID", how="left")
        frames.append(h[cols + ["SKU_Description"]])
    combo = pd.concat(frames).dropna(subset=cols).drop_duplicates(cols)
    fam = sorted(combo["Product_Family"].unique())
    reg = sorted(combo["Region"].unique())
    chan = sorted(combo["Sales_Channel"].unique())
    cust = sorted(combo["Customer_Name"].unique())
    sk = combo.drop_duplicates("SKU_ID").sort_values("SKU_ID")
    sku_ix = {s: i for i, s in enumerate(sk["SKU_ID"])}
    ix = lambda vals: {v: i for i, v in enumerate(vals)}
    fi, ri, ci, ui = ix(fam), ix(reg), ix(chan), ix(cust)
    return {
        "families": fam, "regions": reg, "channels": chan, "customers": cust,
        "skus": [{"id": r.SKU_ID, "description": r.SKU_Description if isinstance(r.SKU_Description, str) else "",
                  "family": fi[r.Product_Family]} for r in sk.itertuples()],
        "combos": [[sku_ix[r.SKU_ID], ri[r.Region], ci[r.Sales_Channel], ui[r.Customer_Name]]
                   for r in combo.itertuples()],
        "combo_fields": ["sku", "region", "channel", "customer"],
    }


@app.get("/meta/filters")
def meta_filters():
    """Options for the global filter bar (family, SKU, region, channel, customer) with valid combinations."""
    return _filter_options()
