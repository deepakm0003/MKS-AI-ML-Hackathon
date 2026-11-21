"""Filter-aware view endpoints for the dashboard (aggregations of contract datasets only).

Every endpoint accepts the global filters as query parameters - family, sku, region, channel,
customer - each a single value or several joined by "|" (e.g. region=Europe|India). Nothing is
re-forecast: history, forecast, bands and prices come from the frozen outputs.

Bands of a filtered aggregate (`band_method` says which applies):
  * no filter or one member of a forecast-hierarchy level (family, region, channel, customer,
    family x region): that level's calibrated band;
  * several members of one such level: the sum of their calibrated bands (slightly wider than
    the combined band, since member errors partly offset);
  * SKU or mixed-dimension selections: the sum of SKU-level P10 / P90 (wider still).
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from celeris.contract import dataset_path, read_dataset

router = APIRouter(prefix="/views", tags=["views"])

DIM_COL = {"family": "Product_Family", "sku": "SKU_ID", "region": "Region", "channel": "Sales_Channel",
           "customer": "Customer_Name"}
HIER = {("Product_Family",): "family", ("Region",): "region", ("Sales_Channel",): "channel",
        ("Customer_Name",): "customer", ("Product_Family", "Region"): "family_region"}


def _need(name: str):
    if not dataset_path(name).exists():
        raise HTTPException(503, f"{name} not generated yet - run the pipeline")
    return read_dataset(name)


@lru_cache(maxsize=1)
def _forecast() -> pd.DataFrame:
    fc = _need("forecast_detail")
    book = _need("price_book").set_index("SKU_ID")
    yr = fc["Date"].str[:4]
    price = np.full(len(fc), np.nan)
    for y in yr.unique():
        sel = (yr == y).to_numpy()
        price[sel] = fc.loc[sel, "SKU_ID"].map(book[f"Price_{y}"]).to_numpy()
    fc = fc.assign(Unit_Price=price)
    fc["Revenue"] = fc["Forecast"] * fc["Unit_Price"]
    return fc


@lru_cache(maxsize=1)
def _history() -> pd.DataFrame:
    return _need("history")


@lru_cache(maxsize=1)
def _hierarchy() -> pd.DataFrame:
    return _need("forecast_hierarchy")


def parse_filters(family: str | None, sku: str | None, region: str | None, channel: str | None,
                  customer: str | None) -> dict[str, list[str]]:
    raw = {"family": family, "sku": sku, "region": region, "channel": channel, "customer": customer}
    return {k: [x for x in v.split("|") if x] for k, v in raw.items() if v}


def apply(df: pd.DataFrame, f: dict[str, list[str]]) -> pd.DataFrame:
    m = np.ones(len(df), bool)
    for k, vals in f.items():
        m &= df[DIM_COL[k]].isin(vals).to_numpy()
    return df[m]


def _clean(v):
    if isinstance(v, (float, np.floating)) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


def _rows(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def _band(f: dict[str, list[str]], fc: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Monthly P10 / P90 for the filtered aggregate and how they were obtained."""
    h = _hierarchy()
    if not f:
        return h[h["Level"] == "total"][["Date", "P10", "P90"]], "calibrated company band (aggregate error model)"
    order = ["family", "region", "channel", "customer"]
    level = None if "sku" in f else HIER.get(tuple(DIM_COL[k] for k in sorted(f, key=order.index)))
    if level:
        keys = sorted(f, key=order.index)
        members = [" | ".join(c) for c in pd.MultiIndex.from_product([f[k] for k in keys]).tolist()]             if len(keys) > 1 else f[keys[0]]
        hb = h[(h["Level"] == level) & h["Member"].isin(members)]
        if hb["Member"].nunique() == len(members):
            b = hb.groupby("Date")[["P10", "P90"]].sum().reset_index()
            name = level.replace("_", " x ")
            if len(members) == 1:
                return b, f"calibrated {name} band (aggregate error model)"
            return b, f"sum of {len(members)} calibrated {name} bands (slightly wider than the combined band)"
    b = fc.groupby("Date")[["P10", "P90"]].sum().reset_index()
    return b, "sum of SKU-level bands (wider than the true aggregate band)"


FILTER_DOC = "single value or several joined by '|'"


@router.get("/timeline")
def timeline(family: str | None = Query(None, description=FILTER_DOC), sku: str | None = Query(None),
             region: str | None = Query(None), channel: str | None = Query(None), customer: str | None = Query(None)):
    """Monthly units and revenue for the filtered selection: history (shipped and unconstrained)
    continuing into the forecast with P10 / P90 - one continuous timeline."""
    f = parse_filters(family, sku, region, channel, customer)
    h, fc = apply(_history(), f), apply(_forecast(), f)
    if h.empty and fc.empty:
        raise HTTPException(404, "no series match these filters")
    hist = h.groupby("Date").agg(Units_shipped=("Units_Sold", "sum"), Units_unconstrained=("Demand", "sum"),
                                 Revenue_shipped=("Revenue_shipped", "sum"),
                                 Revenue_unconstrained=("Revenue_unconstrained", "sum")).reset_index()
    fore = fc.groupby("Date").agg(Units_forecast=("Forecast", "sum"), Revenue_forecast=("Revenue", "sum")).reset_index()
    band, method = _band(f, fc)
    fore = fore.merge(band, on="Date", how="left").rename(columns={"P10": "Units_P10", "P90": "Units_P90"})
    ratio = fore["Revenue_forecast"] / fore["Units_forecast"].where(fore["Units_forecast"] > 0)
    fore["Revenue_P10"], fore["Revenue_P90"] = fore["Units_P10"] * ratio, fore["Units_P90"] * ratio
    l12 = hist.tail(12)
    n12 = fore.head(12)
    summary = {
        "series": int(pd.concat([h[["SKU_ID", "Region"]], fc[["SKU_ID", "Region"]]]).drop_duplicates().shape[0]),
        "forecast_series": int(fc[["SKU_ID", "Region"]].drop_duplicates().shape[0]),
        "history_end": hist["Date"].max() if len(hist) else None,
        "units_last12": float(l12["Units_unconstrained"].sum()), "units_next12": float(n12["Units_forecast"].sum()),
        "revenue_last12": float(l12["Revenue_unconstrained"].sum()), "revenue_next12": float(n12["Revenue_forecast"].sum()),
        "units_19m": float(fore["Units_forecast"].sum()), "units_19m_p10": float(fore["Units_P10"].sum()),
        "units_19m_p90": float(fore["Units_P90"].sum()), "revenue_19m": float(fore["Revenue_forecast"].sum()),
    }
    summary["units_next12_vs_last12"] = summary["units_next12"] / summary["units_last12"] - 1 if summary["units_last12"] else None
    summary["revenue_next12_vs_last12"] = (summary["revenue_next12"] / summary["revenue_last12"] - 1
                                           if summary["revenue_last12"] else None)
    return {"filters": f, "band_method": method, "summary": {k: _clean(v) for k, v in summary.items()},
            "history": _rows(hist.round(2)), "forecast": _rows(fore.round(2))}


@router.get("/breakdown")
def breakdown(dim: str = Query(..., description="family | region | channel | customer | sku"),
              top: int = Query(25, ge=1, le=1000), family: str | None = Query(None, description=FILTER_DOC),
              sku: str | None = Query(None), region: str | None = Query(None), channel: str | None = Query(None),
              customer: str | None = Query(None)):
    """Last 12 months vs next 12 months, units and revenue, by one dimension (largest first)."""
    if dim not in DIM_COL:
        raise HTTPException(400, f"dim must be one of {sorted(DIM_COL)}")
    col = DIM_COL[dim]
    f = parse_filters(family, sku, region, channel, customer)
    h, fc = apply(_history(), f), apply(_forecast(), f)
    end = _history()["Date"].max()
    start = (pd.Period(end, "M") - 11).strftime("%Y-%m")
    a = h[h["Date"] >= start].groupby(col).agg(Units_last12=("Demand", "sum"), Revenue_last12=("Revenue_unconstrained", "sum"))
    b = fc[fc["h"] <= 12].groupby(col).agg(Units_next12=("Forecast", "sum"), Revenue_next12=("Revenue", "sum"))
    t = a.join(b, how="outer").fillna(0.0)
    t["Units_change_pct"] = 100 * (t["Units_next12"] / t["Units_last12"].where(t["Units_last12"] > 0) - 1)
    t["Revenue_change_pct"] = 100 * (t["Revenue_next12"] / t["Revenue_last12"].where(t["Revenue_last12"] > 0) - 1)
    tot = t["Revenue_next12"].sum()
    t["Revenue_share_next12"] = t["Revenue_next12"] / tot if tot else np.nan
    t = t.sort_values("Revenue_next12", ascending=False)
    total_members = len(t)
    rows = t.head(top).reset_index().rename(columns={col: "Member"})
    if total_members > top:
        rest = t.iloc[top:].sum(numeric_only=True)
        other = {"Member": f"Other ({total_members - top})", **rest.to_dict()}
        for k, a_, b_ in [("Units_change_pct", "Units_last12", "Units_next12"),
                          ("Revenue_change_pct", "Revenue_last12", "Revenue_next12")]:
            other[k] = 100 * (other[b_] / other[a_] - 1) if other[a_] else None
        other["Revenue_share_next12"] = other["Revenue_next12"] / tot if tot else None
        rows = pd.concat([rows, pd.DataFrame([other])], ignore_index=True)
    return {"dim": dim, "filters": f, "members": total_members, "rows": _rows(rows.round(4))}
