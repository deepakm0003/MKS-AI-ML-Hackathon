"""Demand Explorer endpoints (aggregations of contract datasets; global filters as in api/views.py).

  GET /views/seasonality   seasonal profile, year-over-year overlay, zero-order months, demand classes
  GET /views/drilldown     members of one drill-down level (family -> SKU -> region -> customer)
  GET /views/lifecycle     lifecycle status, launches and EOLs in the forecast window, series age
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from api.views import DIM_COL, FILTER_DOC, _clean, _forecast, _history, _need, apply, parse_filters

router = APIRouter(prefix="/views", tags=["explorer"])

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LEVEL_NEXT = {"family": "sku", "sku": "region", "region": "customer", "customer": None}


@lru_cache(maxsize=1)
def _lifecycle() -> pd.DataFrame:
    return _need("sku_lifecycle").set_index("SKU_ID")


@lru_cache(maxsize=1)
def _profile() -> pd.DataFrame:
    return _need("series_profile")


def _window(end: str, n: int) -> str:
    return (pd.Period(end, "M") - (n - 1)).strftime("%Y-%m")


def _str(v):
    return v if isinstance(v, str) and v else None


@router.get("/seasonality")
def seasonality(family: str | None = Query(None, description=FILTER_DOC), sku: str | None = Query(None),
                region: str | None = Query(None), channel: str | None = Query(None),
                customer: str | None = Query(None)):
    """Seasonal profile (last 36 months vs the first 12 forecast months), a year-over-year overlay,
    zero-order months over the last 24 months and the demand-class mix of the selection."""
    f = parse_filters(family, sku, region, channel, customer)
    h, fc = apply(_history(), f), apply(_forecast(), f)
    if h.empty and fc.empty:
        raise HTTPException(404, "no series match these filters")
    end = _history()["Date"].max()

    m = h[h["Date"] >= _window(end, 36)].groupby("Date")["Demand"].sum()
    m.index = pd.PeriodIndex(m.index, freq="M").month
    hist_avg = m.groupby(level=0).mean().reindex(range(1, 13))
    f12 = fc[fc["h"] <= 12].groupby("Date")["Forecast"].sum()
    f12.index = pd.PeriodIndex(f12.index, freq="M").month
    f12 = f12.reindex(range(1, 13))
    hi = hist_avg / hist_avg.mean() if hist_avg.mean() else hist_avg * np.nan
    fi = f12 / f12.mean() if f12.mean() else f12 * np.nan
    by_month = [{"month": i, "label": MONTHS[i - 1], "hist_avg_units": _clean(hist_avg.get(i)),
                 "hist_index": _clean(hi.get(i)), "forecast_units": _clean(f12.get(i)),
                 "forecast_index": _clean(fi.get(i))} for i in range(1, 13)]

    hy = h.groupby("Date")["Demand"].sum()
    fy = fc.groupby("Date")["Forecast"].sum()
    years = []
    for y in sorted({d[:4] for d in hy.index if d >= _window(end, 48)}):
        years.append({"year": y, "kind": "history", "values": [_clean(hy.get(f"{y}-{k:02d}")) for k in range(1, 13)]})
    for y in sorted({d[:4] for d in fy.index}):
        years.append({"year": y, "kind": "forecast", "values": [_clean(fy.get(f"{y}-{k:02d}")) for k in range(1, 13)]})

    # zero-order months: observed months only (a missing month is not a zero - business rule 3)
    h24 = h[(h["Date"] >= _window(end, 24)) & h["Demand"].notna()]
    zero_share = float((h24["Demand"] == 0).mean()) if len(h24) else None
    per_series = h24.assign(z=h24["Demand"] == 0).groupby(["SKU_ID", "Region"])["z"].mean()
    keys = pd.concat([h[["SKU_ID", "Region"]], fc[["SKU_ID", "Region"]]]).drop_duplicates()
    prof = _profile().merge(keys, on=["SKU_ID", "Region"])
    peaks = hi.dropna().nlargest(2).index.tolist()
    return {
        "filters": f, "by_month": by_month, "years": years,
        "stats": {
            "peak_months": [MONTHS[i - 1] for i in peaks],
            "trough_month": MONTHS[int(hi.idxmin()) - 1] if hi.notna().any() else None,
            "amplitude": _clean(hi.max() / hi.min()) if hi.notna().any() and hi.min() > 0 else None,
            "zero_month_share_24m": _clean(zero_share),
            "series_with_30pct_zero_months": int((per_series >= 0.3).sum()),
            "series_observed_24m": int(len(per_series)),
            "demand_classes": {k: int(v) for k, v in prof["Demand_Class"].value_counts().items()},
            "median_order_cycle_months": _clean(prof["Cycle_Last12"].median()) if len(prof) else None,
        },
    }


@router.get("/drilldown")
def drilldown(level: str = Query(..., description="family | sku | region | customer"),
              top: int = Query(50, ge=1, le=600), family: str | None = Query(None, description=FILTER_DOC),
              sku: str | None = Query(None), region: str | None = Query(None), channel: str | None = Query(None),
              customer: str | None = Query(None)):
    """Members of one drill-down level for the current filters: last 12 vs next 12 months, revenue,
    zero-order share, lifecycle / demand class and a 24-month history + 12-month forecast sparkline."""
    if level not in LEVEL_NEXT:
        raise HTTPException(400, f"level must be one of {list(LEVEL_NEXT)}")
    col = DIM_COL[level]
    f = parse_filters(family, sku, region, channel, customer)
    h, fc = apply(_history(), f), apply(_forecast(), f)
    end = _history()["Date"].max()
    s12, s24 = _window(end, 12), _window(end, 24)
    last = h[h["Date"] >= s12].groupby(col)["Demand"].sum()
    h24 = h[(h["Date"] >= s24) & h["Demand"].notna()]
    zero = h24.assign(z=h24["Demand"] == 0).groupby(col)["z"].mean()
    nxt = fc[fc["h"] <= 12].groupby(col).agg(Units_next12=("Forecast", "sum"), Revenue_next12=("Revenue", "sum"))
    sc = list(dict.fromkeys([col, "SKU_ID", "Region"]))          # level column may itself be SKU or region
    series = pd.concat([h[sc], fc[sc]]).drop_duplicates().groupby(col).size()
    t = (pd.DataFrame({"Units_last12": last}).join(nxt, how="outer").join(zero.rename("Zero_share_24m"))
         .join(series.rename("Series")).fillna({"Units_last12": 0, "Units_next12": 0, "Revenue_next12": 0}))
    t["Units_change_pct"] = 100 * (t["Units_next12"] / t["Units_last12"].where(t["Units_last12"] > 0) - 1)
    t = t.sort_values(["Revenue_next12", "Units_last12"], ascending=False)
    members = len(t)
    t = t.head(top)

    hs = h[h["Date"] >= s24].groupby([col, "Date"])["Demand"].sum().unstack()
    fs = fc[fc["h"] <= 12].groupby([col, "Date"])["Forecast"].sum().unstack()
    hist_months = [(pd.Period(end, "M") - i).strftime("%Y-%m") for i in range(23, -1, -1)]
    fc_months = sorted(fc["Date"].unique())[:12]
    prof = _profile().set_index(["SKU_ID", "Region"])
    life = _lifecycle()
    one_sku = f["sku"][0] if len(f.get("sku", [])) == 1 else None
    rows = []
    for k, r in t.iterrows():
        row = {"Member": k}
        row.update({c: _clean(r[c]) for c in ["Series", "Units_last12", "Units_next12", "Revenue_next12",
                                              "Units_change_pct", "Zero_share_24m"]})
        row["spark_history"] = [_clean(hs.loc[k].get(mm)) if k in hs.index else None for mm in hist_months]
        row["spark_forecast"] = [_clean(fs.loc[k].get(mm)) if k in fs.index else None for mm in fc_months]
        if level == "sku" and k in life.index:
            L = life.loc[k]
            row.update({"Label": _str(L["SKU_Description"]), "Lifecycle_Status": _str(L["Lifecycle_Status"]),
                        "Powertrain": _str(L["Powertrain_Application"]), "Launch_Date": _str(L["Launch_Date"]),
                        "EOL_Date": _str(L["EOL_Date"]), "Successor_SKU": _str(L["Successor_SKU"])})
        if one_sku and level in ("region", "customer"):
            reg = k if level == "region" else (f.get("region") or [None])[0]
            if reg and (one_sku, reg) in prof.index:
                P = prof.loc[(one_sku, reg)]
                row.update({"Demand_Class": P["Demand_Class"], "Order_cycle_months": _clean(P["Cycle_Last12"]),
                            "First_Month": P["First_Month"]})
        rows.append(row)
    return {"level": level, "next_level": LEVEL_NEXT[level], "filters": f, "members": members,
            "spark_months": {"history": hist_months, "forecast": fc_months}, "rows": rows}


@router.get("/lifecycle")
def lifecycle(family: str | None = Query(None, description=FILTER_DOC), sku: str | None = Query(None),
              region: str | None = Query(None), channel: str | None = Query(None), customer: str | None = Query(None)):
    """Lifecycle status of the selected SKUs, launches and EOLs inside the forecast window, and the
    history-length mix of the selected series."""
    f = parse_filters(family, sku, region, channel, customer)
    h, fc = apply(_history(), f), apply(_forecast(), f)
    skus = sorted(set(h["SKU_ID"]) | set(fc["SKU_ID"]))
    life = _lifecycle().reindex(skus)
    end = _history()["Date"].max()
    win_end = fc["Date"].max() if len(fc) else end
    events = []
    for s_, L in life.iterrows():
        if _str(L["Launch_Date"]) and L["Launch_Date"] > end:
            g = fc[fc["SKU_ID"] == s_]
            events.append({"type": "LAUNCH", "sku": s_, "date": L["Launch_Date"], "description": _str(L["SKU_Description"]),
                           "related_sku": _str(L["Replaces_SKU"]), "powertrain": _str(L["Powertrain_Application"]),
                           "regions": int(g["Region"].nunique()), "forecast_units": _clean(g["Forecast"].sum())})
        if _str(L["EOL_Date"]) and end < L["EOL_Date"] <= win_end:
            g = fc[(fc["SKU_ID"] == s_) & (fc["Date"] <= L["EOL_Date"])]
            events.append({"type": "EOL", "sku": s_, "date": L["EOL_Date"], "description": _str(L["SKU_Description"]),
                           "related_sku": _str(L["Successor_SKU"]), "powertrain": _str(L["Powertrain_Application"]),
                           "regions": int(g["Region"].nunique()), "forecast_units": _clean(g["Forecast"].sum())})
    keys = pd.concat([h[["SKU_ID", "Region"]], fc[["SKU_ID", "Region"]]]).drop_duplicates()
    months = _profile().merge(keys, on=["SKU_ID", "Region"], how="right")["Months"].fillna(0)
    age = {"new (< 24 months)": int((months < 24).sum()),
           "established (2-5 years)": int(((months >= 24) & (months < 60)).sum()),
           "mature (5+ years)": int((months >= 60).sum())}
    return {"filters": f, "skus": len(skus),
            "status_counts": {k: int(v) for k, v in life["Lifecycle_Status"].value_counts().items()},
            "powertrain_counts": {k: int(v) for k, v in life["Powertrain_Application"].value_counts().items()},
            "series_age": age, "events": sorted(events, key=lambda e: e["date"])}
