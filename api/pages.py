"""Server-side aggregations for the Planning, Anomaly Monitor and Data Health views.

Pages must never add up a truncated slice of a dataset (the generic /datasets endpoint returns
at most `limit` rows), so totals, counts and charts are computed here over the FULL contract
datasets, with the global filters applied (family, sku, region, channel, customer; '|' for
several values). Tables get the top rows plus the true total.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query

from api.views import FILTER_DOC, _clean, _need, _rows, apply, parse_filters

router = APIRouter(prefix="/views", tags=["pages"])
KEY = ["SKU_ID", "Region"]


@lru_cache(maxsize=1)
def _dims() -> pd.DataFrame:
    """Family / channel / customer per SKU x region (from the frozen forecast) for joining onto
    datasets that lack some filter columns."""
    fc = _need("forecast_detail")
    return fc.drop_duplicates(KEY)[KEY + ["Product_Family", "Sales_Channel", "Customer_Name"]]


def _with_dims(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ("Product_Family", "Sales_Channel", "Customer_Name") if c not in df.columns]
    if not missing:
        return df
    return df.merge(_dims()[KEY + missing], on=KEY, how="left")


@lru_cache(maxsize=1)
def _plan() -> pd.DataFrame:
    return _with_dims(_need("procurement_plan"))


@lru_cache(maxsize=1)
def _next_cycle() -> pd.DataFrame:
    return _with_dims(_need("procurement_next_cycle"))


@lru_cache(maxsize=1)
def _segmentation() -> pd.DataFrame:
    return _with_dims(_need("segmentation"))


# ----------------------------------------------------------------------------- planning
@router.get("/planning")
def planning(top: int = Query(500, ge=1, le=5000), family: str | None = Query(None, description=FILTER_DOC),
             sku: str | None = Query(None), region: str | None = Query(None), channel: str | None = Query(None),
             customer: str | None = Query(None)):
    """Procurement KPIs, monthly plan, ABC-XYZ mix, next-cycle lines and capacity for the selection."""
    f = parse_filters(family, sku, region, channel, customer)
    nc, seg, plan = apply(_next_cycle(), f), apply(_segmentation(), f), apply(_plan(), f)
    rev = seg["Revenue_next12"].sum()
    kpis = {
        "lines": int(len(nc)),
        "cover_units": float(nc["Leadtime_cover"].sum()),
        "forecast_units_next3": float(nc["Leadtime_P50"].sum()),
        "buffer_units": float(nc["Safety_buffer"].sum()),
        "cover_value_usd": float(nc["Cover_value_usd"].sum()),
        "buffer_value_usd": float(nc["Buffer_value_usd"].sum()) if "Buffer_value_usd" in nc else None,
        "service_level_revenue_weighted": float((seg["Service_level"] * seg["Revenue_next12"]).sum() / rev) if rev else None,
        "series": int(len(seg)),
        "make_to_order_lines": int((plan["Policy"] == "make to order").groupby([plan["SKU_ID"], plan["Region"]]).any().sum())
        if "Policy" in plan else None,
    }
    monthly = plan.groupby("Date").agg(Forecast=("Forecast", "sum"), P90=("P90", "sum"),
                                       Revenue=("Revenue", "sum") if "Revenue" in plan else ("Forecast", "sum")).reset_index()
    seg_mix = (seg.groupby(["Segment", "ABC", "XYZ"])
               .agg(Series=("SKU_ID", "size"), Revenue_next12=("Revenue_next12", "sum"), Service_level=("Service_level", "first"))
               .reset_index().sort_values(["ABC", "XYZ"]))
    seg_mix["Revenue_share"] = seg_mix["Revenue_next12"] / rev if rev else np.nan
    cap = _need("capacity_check")
    if "family" in f:
        cap = cap[cap["Product_Family"].isin(f["family"])]
    if "region" in f:
        cap = cap[cap["Region"].isin(f["region"])]
    nc_cols = ["SKU_ID", "Region", "Product_Family", "Segment", "Service_level", "Leadtime_P50", "Leadtime_cover",
               "Safety_buffer", "Cover_value_usd"]
    seg_cols = ["SKU_ID", "Region", "Product_Family", "Revenue_next12", "ABC", "XYZ", "Segment", "Service_level",
                "Planning_approach"]
    return {
        "filters": f, "kpis": {k: _clean(v) for k, v in kpis.items()},
        "monthly": _rows(monthly.round(2)), "segments": _rows(seg_mix.round(4)),
        "next_cycle": {"total": int(len(nc)), "rows": _rows(nc.sort_values("Cover_value_usd", ascending=False).head(top)[nc_cols].round(2))},
        "segmentation": {"total": int(len(seg)), "rows": _rows(seg.sort_values("Revenue_next12", ascending=False).head(top)[seg_cols].round(4))},
        "capacity": _rows(cap.round(4)),
    }


# ----------------------------------------------------------------------------- anomaly monitor
TYPE_LABEL = {"unexplained_drop": "Unexplained drop", "one_off_order": "One-off order", "stockout_file": "Stockout (file)",
              "allocation_unlisted": "Allocation shortfall", "backorder_catch_up": "Backorder catch-up"}


@router.get("/anomalies")
def anomalies(top: int = Query(500, ge=1, le=5000), family: str | None = Query(None, description=FILTER_DOC),
              sku: str | None = Query(None), region: str | None = Query(None), channel: str | None = Query(None),
              customer: str | None = Query(None)):
    """Counts over the FULL anomaly register for the selection, flagged months on the demand time
    series (aggregate, or the exact points when one SKU x region is selected), and the top rows."""
    f = parse_filters(family, sku, region, channel, customer)
    a = apply(_need("anomaly_register"), f)
    hist = apply(_need("history"), f)
    by_cat = a["Category"].value_counts().to_dict()
    by_type = a["Type"].value_counts().to_dict()
    per_month = a.groupby(["Date", "Category"]).size().unstack(fill_value=0)
    series = hist.groupby("Date").agg(Demand=("Demand", "sum"), Shipped=("Units_Sold", "sum")).reset_index()
    flagged = []
    for d, row in per_month.iterrows():
        flagged.append({"Date": d, "count": int(row.sum()), "by_category": {k: int(v) for k, v in row.items() if v}})
    single = len(f.get("sku", [])) == 1 and len(f.get("region", [])) == 1
    points = _rows(a.sort_values("Date")[["Date", "Type", "Category", "Reason", "Action", "Units_Shipped", "Demand",
                                          "Expected", "Confidence"]]) if single else None
    struct = apply(_need("structural_register"), {k: v for k, v in f.items() if k in ("sku", "region")})
    cols = ["Date", "SKU_ID", "Region", "Product_Family", "Customer_Name", "Type", "Category", "Detection", "Reason",
            "Action", "Confidence", "Units_Shipped", "Demand", "Expected"]
    return {
        "filters": f, "total": int(len(a)), "series_affected": int(a[KEY].drop_duplicates().shape[0]),
        "by_category": {k: int(v) for k, v in by_cat.items()},
        "by_type": [{"type": k, "label": TYPE_LABEL.get(k, k.replace("_", " ")), "count": int(v)} for k, v in by_type.items()],
        "timeline": _rows(series.round(2)), "flagged_months": flagged, "single_series": single, "points": points,
        "rows": _rows(a.sort_values("Date", ascending=False).head(top)[[c for c in cols if c in a.columns]]),
        "structural": {"total": int(len(struct)), "rows": _rows(struct.head(top))},
    }


# ----------------------------------------------------------------------------- data health
@router.get("/data-health")
def data_health(top: int = Query(500, ge=1, le=5000), file: str | None = Query(None),
                category: str | None = Query(None)):
    """Data-quality counts over the FULL issue log, the before / after profile of every raw file,
    and the top logged corrections. (Issues concern raw files and rows, so the product filters
    do not apply here.)"""
    log = _need("dq_issue_log")
    rep = _need("dq_report")
    if file:
        log = log[log["file"] == file]
    if category:
        log = log[log["category"] == category]
    before_after = []
    for fname, p in rep.get("profiles", {}).items():
        b, a = p.get("before", {}), p.get("after", {})
        before_after.append({
            "file": fname, "rows_before": b.get("rows"), "rows_after": a.get("rows"),
            "columns_before": b.get("columns"), "columns_after": a.get("columns"),
            "null_cells_before": b.get("null_cells"), "null_cells_after": a.get("null_cells"),
            "nulls_by_column_before": b.get("nulls_by_column", {}), "nulls_by_column_after": a.get("nulls_by_column", {}),
        })
    return {
        "total": int(len(log)), "total_all_files": int(rep.get("total_issues", len(log))),
        "rows_affected": int(log[["file", "row_ref"]].drop_duplicates().shape[0]),
        "by_issue_type": [{"issue_type": k, "count": int(v)} for k, v in log["issue_type"].value_counts().items()],
        "by_category": {k: int(v) for k, v in log["category"].value_counts().items()},
        "by_file": {k: int(v) for k, v in log["file"].value_counts().items()},
        "rule_summary": rep.get("issues", []),
        "before_after": before_after,
        "rows": _rows(log.head(top)),
    }
