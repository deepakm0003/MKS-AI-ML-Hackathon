"""Score uploaded data with the frozen final model.

Two kinds of file, both in the competition formats:

* sales history (train.csv format) - goes through the SAME pipeline as the official data:
  stage-1 cleaning (every fix logged), stockout / anomaly demand recovery, the selected model's
  training-month variant, the feature panel, then the frozen model.
* rows to forecast (test.csv format) - Date x SKU_ID x Region rows to score. If the file also
  carries actual Units_Sold (for example the real outcome of those months), the forecast is
  scored against them: WAPE, bias, P10-P90 coverage and a seasonal-naive comparison.

Without a history file the official cleaned history is used; without a rows file every active
series is forecast for the next 19 months (or up to 2028-05, the end of the macro file). The
forecast origin (cutoff) defaults to the last history month; an earlier cutoff holds the later
months out and scores the forecast against them.

Nothing here retrains or changes the frozen model or its outputs. Uploading the official
train.csv + test.csv reproduces outputs/final/forecast_detail.csv exactly (tested).
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Callable

import numpy as np
import pandas as pd

from .config import CHANNEL_ALIASES, PROCESSED, REGION_ALIASES, ROOT
from .features import HORIZON, LAST_HIST, MIDX, MONTHS

KEY = ["Date", "SKU_ID", "Region"]
SERIES = ["SKU_ID", "Region"]
TRAIN_COLS = ["Record_ID", "Date", "Year", "Month", "Product_Family", "Business_Unit", "SKU_ID",
              "SKU_Description", "Customer_Name", "Sales_Channel", "Region", "Units_Sold", "Unit_Price_USD",
              "Revenue_USD", "Load_Timestamp"]
TEST_COLS = ["Date", "Year", "Month", "Product_Family", "Business_Unit", "SKU_ID", "SKU_Description",
             "Customer_Name", "Sales_Channel", "Region"]
HISTORY_REQUIRED = ["Date", "SKU_ID", "Region", "Units_Sold"]
REQUEST_REQUIRED = ["Date", "SKU_ID", "Region"]
MODEL_TRAIN_END = MONTHS[LAST_HIST]          # the frozen model saw history through this month
LAST_MONTH = MONTHS[-1]                      # macro indicators (known future inputs) end here
MIN_CUTOFF = "2020-12"                       # features need 24 months of history


class ScoringError(ValueError):
    """A problem with the uploaded data, explained in words the user can act on."""


# ----------------------------------------------------------------------------- reading
def read_csv(source) -> pd.DataFrame:
    try:
        df = pd.read_csv(source, dtype=str, keep_default_na=True, skipinitialspace=True)
    except Exception as e:  # noqa: BLE001 - any parser error becomes a user-facing message
        raise ScoringError(f"could not read the file as CSV: {e}") from e
    # tolerate case / spacing differences in the header
    canon = {c.lower().replace(" ", "_"): c for c in TRAIN_COLS + TEST_COLS}
    df.columns = [canon.get(str(c).strip().lower().replace(" ", "_"), str(c).strip()) for c in df.columns]
    return df


def inspect(df: pd.DataFrame) -> dict:
    """What kind of file this looks like, and what is missing."""
    cols = set(df.columns)
    has_units = "Units_Sold" in cols
    train_like = has_units and bool(cols & {"Record_ID", "Load_Timestamp", "Unit_Price_USD", "Revenue_USD"})
    kind = "history" if train_like else "request"
    dates = pd.to_datetime(df["Date"], errors="coerce", format="mixed") if "Date" in cols else pd.Series(dtype="datetime64[ns]")
    months = dates.dt.strftime("%Y-%m").dropna()
    actual_rows = int(pd.to_numeric(df["Units_Sold"], errors="coerce").notna().sum()) if has_units else 0
    return {
        "rows": int(len(df)), "columns": list(df.columns), "detected_kind": kind,
        "missing_history_columns": [c for c in HISTORY_REQUIRED if c not in cols],
        "missing_request_columns": [c for c in REQUEST_REQUIRED if c not in cols],
        "optional_columns_missing": [c for c in (TRAIN_COLS if kind == "history" else TEST_COLS) if c not in cols
                                     and c not in HISTORY_REQUIRED],
        "date_from": months.min() if len(months) else None, "date_to": months.max() if len(months) else None,
        "unparseable_dates": int(dates.isna().sum()) if "Date" in cols else None,
        "series": int(df[SERIES].drop_duplicates().shape[0]) if set(SERIES) <= cols else None,
        "has_actuals": actual_rows > 0, "actual_rows": actual_rows,
    }


# ----------------------------------------------------------------------------- frozen inputs
@lru_cache(maxsize=1)
def _reference() -> dict:
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    return {n: rd(n) for n in ["sku_master", "macro", "events", "events_monthly", "stockouts", "test"]}


@lru_cache(maxsize=1)
def _frozen() -> dict:
    """The frozen model, its manifest, band tables and the rule inputs of the final run."""
    from .anomalies import transient_candidates
    from .experiments import resolve
    from .final import backtest_for_bands, load_final_model
    from .intervals import fit_ratio_quantiles
    from .robustness import demand_variant
    model, cols, man = load_final_model()
    ref = _reference()
    demand0 = pd.read_parquet(PROCESSED / "demand.parquet")
    variant = man.get("demand_variant")
    dv = demand_variant(demand0, variant).sort_index() if variant else demand0
    bt = backtest_for_bands(man["selected_model"], dv)
    findings = json.loads((ROOT / "outputs" / "anomalies" / "findings.json").read_text(encoding="utf-8"))
    notes_p = ROOT / "outputs" / "forecast" / "forecast_notes.json"
    return {
        "model": model, "cols": cols, "manifest": man, "spec": resolve(man["selected_model"]), "variant": variant,
        "bt": bt, "band_q": fit_ratio_quantiles(bt, "f_lgb_tweedie", strata=True),
        "excluded_events": transient_candidates(ref["events"]) - set(findings.get("events_not_excluded_no_effect", [])),
        "impact": pd.read_csv(ROOT / "outputs" / "anomalies" / "event_impact.csv"),
        "curves": json.loads(notes_p.read_text(encoding="utf-8"))["curves"] if notes_p.exists() else None,
        "official_series": int(demand0[SERIES].drop_duplicates().shape[0]),
    }


# ----------------------------------------------------------------------------- normalising
def _norm_month(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    ym = s.str.extract(r"^(\d{4})-(\d{1,2})$")
    out = pd.Series(np.where(ym[0].notna(), ym[0] + "-" + ym[1].str.zfill(2), None), index=s.index, dtype=object)
    rest = out.isna()
    out[rest] = pd.to_datetime(s[rest], errors="coerce", format="mixed").dt.strftime("%Y-%m")
    return out


def _norm_region(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().map(REGION_ALIASES)


def prepare_request(req: pd.DataFrame, sku: pd.DataFrame, demand: pd.DataFrame, cutoff: str,
                    horizon_end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validated rows to forecast + the rows rejected, each with a reason."""
    r = req.copy()
    r["_row"] = np.arange(len(r)) + 2                                  # CSV line number (header = 1)
    r["Date"] = _norm_month(r["Date"])
    r["SKU_ID"] = r["SKU_ID"].astype(str).str.strip().str.upper()
    r["Region"] = _norm_region(r["Region"])
    known = set(sku["SKU_ID"])
    reason = pd.Series("", index=r.index, dtype=object)
    reason[r["Date"].isna()] = "date not understood"
    reason[(reason == "") & ~r["SKU_ID"].isin(known)] = "SKU not in the product master"
    reason[(reason == "") & r["Region"].isna()] = "unknown region"
    reason[(reason == "") & (r["Date"] <= cutoff)] = f"month is not after the forecast origin ({cutoff})"
    reason[(reason == "") & (r["Date"] > horizon_end)] = f"beyond the forecast horizon (last month {horizon_end})"
    dup = r.duplicated(KEY, keep="first") & (reason == "")
    reason[dup] = "duplicate Date-SKU-Region (first one kept)"
    rejected = r[reason != ""].assign(Reason=reason[reason != ""])
    ok = r[reason == ""].copy()

    # fill the descriptive columns forecast output needs: file value, else last history row, else master
    last = demand.sort_values("Date").groupby(SERIES)[["Customer_Name", "Sales_Channel"]].last()
    m = sku.set_index("SKU_ID")
    for c in ["Customer_Name", "Sales_Channel"]:
        hist = pd.MultiIndex.from_frame(ok[SERIES]).map(last[c]) if len(ok) else pd.Index([])
        if c in ok:
            v = ok[c].where(ok[c].notna() & ok[c].astype(str).str.strip().ne(""), None)
            if c == "Sales_Channel":
                v = v.map(lambda x: CHANNEL_ALIASES.get(str(x).strip().lower(), x) if x is not None else None)
            ok[c] = v.fillna(pd.Series(hist, index=ok.index))
        else:
            ok[c] = pd.Series(hist, index=ok.index)
    for c in ["Product_Family", "Business_Unit", "SKU_Description"]:
        ok[c] = ok["SKU_ID"].map(m[c])
    ok["Year"] = ok["Date"].str[:4].astype(int)
    ok["Month"] = ok["Date"].str[5:].astype(int)
    if "Units_Sold" in ok:
        ok["Actual"] = pd.to_numeric(ok["Units_Sold"].astype(str).str.replace(",", ""), errors="coerce")
    keep = TEST_COLS + ["_row"] + (["Actual"] if "Actual" in ok else [])
    return ok[keep].reset_index(drop=True), rejected


def default_request(demand: pd.DataFrame, sku: pd.DataFrame, cutoff: str, horizon_end: str) -> pd.DataFrame:
    """Every series that sold in the 12 months before the origin and is not past its EOL,
    for each month of the horizon."""
    o = MIDX[cutoff]
    recent = demand[(demand["Date"] > MONTHS[o - 12]) & (demand["Date"] <= cutoff)]
    active = recent.groupby(SERIES)["Demand"].sum()
    active = active[active > 0].reset_index()[SERIES]
    eol = active["SKU_ID"].map(sku.set_index("SKU_ID")["EOL_Date"])
    active = active[eol.isna() | (eol > cutoff)]
    months = MONTHS[o + 1: MIDX[horizon_end] + 1]
    grid = active.merge(pd.DataFrame({"Date": months}), how="cross")
    return grid


# ----------------------------------------------------------------------------- scoring
def score(history: pd.DataFrame | None = None, request: pd.DataFrame | None = None, cutoff: str | None = None,
          progress: Callable[[str, str], None] = lambda step, state: None) -> dict:
    """Run the frozen pipeline on the uploaded data. Returns the result payload plus the
    full tables to write as downloads (key 'files')."""
    from .anomalies import build_demand
    from .clean_sales import clean_sales
    from .dq import DQLog
    from .features import Panel
    from .forecast import forecast_test, hierarchy
    from .intel.pricing import history_revenue, price_book, revenue_forecast
    from .panel import build_panel
    from .pipeline import refine_with_stockouts
    from .robustness import demand_variant

    t0 = time.time()
    ref, fz = _reference(), _frozen()
    sku, macro, ev, evm, so = ref["sku_master"], ref["macro"], ref["events"], ref["events_monthly"], ref["stockouts"]
    warnings: list[str] = []
    checks: dict = {}

    # ---- 1. history: the uploaded sales through the full cleaning + recovery pipeline
    progress("clean", "running")
    if history is not None:
        miss = [c for c in HISTORY_REQUIRED if c not in history.columns]
        if miss:
            raise ScoringError(f"the sales history file needs the columns {', '.join(miss)} (train.csv format)")
        raw = history.copy()
        filled = [c for c in TRAIN_COLS if c not in raw.columns]
        for c in filled:
            raw[c] = np.nan
        if "Record_ID" in filled:
            raw["Record_ID"] = [f"UP-{i:07d}" for i in range(len(raw))]
        if filled:
            warnings.append(f"history columns not in the file were left blank and recovered by the cleaning rules "
                            f"where possible: {', '.join(filled)}")
        log = DQLog()
        customers = sorted(ref["test"]["Customer_Name"].dropna().unique())
        sales = clean_sales(raw[TRAIN_COLS], sku, customers, ev, evm, log)
        sales = refine_with_stockouts(sales, so, log)
        out_of_range = ~sales["Date"].isin(MONTHS)
        if out_of_range.any():
            warnings.append(f"{int(out_of_range.sum()):,} history rows fall outside 2019-01..{LAST_MONTH} and were ignored")
            sales = sales[~out_of_range]
        if sales.empty:
            raise ScoringError("no usable history rows after cleaning (check SKU_ID, Region and Date)")
        prof = log.profiles.get("train.csv", {})
        dq_table = log.table()
        checks["cleaning"] = {
            "rows_in": int(len(history)), "rows_clean": int(len(sales)),
            "issues": int(len(dq_table)),
            "by_type": (dq_table.groupby(["issue_type", "category", "action"]).size().rename("rows").reset_index()
                        .sort_values("rows", ascending=False).head(25).to_dict("records")) if len(dq_table) else [],
            "null_cells_before": (prof.get("before") or {}).get("null_cells"),
            "null_cells_after": (prof.get("after") or {}).get("null_cells"),
        }
        hist_source = "uploaded"
        hist_end = sales["Date"].max()
    else:
        sales = pd.read_parquet(PROCESSED / "sales_clean.parquet")
        dq_table = None
        hist_source = "official"
        hist_end = MODEL_TRAIN_END
    progress("clean", "done")

    cutoff = cutoff or hist_end
    if cutoff not in MIDX or cutoff < MIN_CUTOFF:
        raise ScoringError(f"forecast origin must be a month between {MIN_CUTOFF} and {MONTHS[-2]}")
    if cutoff > hist_end:
        raise ScoringError(f"forecast origin {cutoff} is after the last history month ({hist_end})")
    if cutoff >= LAST_MONTH:
        raise ScoringError(f"nothing to forecast after {cutoff}: the macro indicators end in {LAST_MONTH}")
    o = MIDX[cutoff]
    horizon_end = MONTHS[min(o + HORIZON, len(MONTHS) - 1)]
    if MIDX[horizon_end] - o < HORIZON:
        warnings.append(f"the horizon is {MIDX[horizon_end] - o} months: the macro indicators the model needs end in {LAST_MONTH}")

    # ---- 2. demand recovery on the history up to the origin only (no look-ahead)
    progress("recover", "running")
    if history is None and cutoff == MODEL_TRAIN_END:
        demand = pd.read_parquet(PROCESSED / "demand.parquet")
        register = pd.read_csv(ROOT / "outputs" / "anomalies" / "anomaly_register.csv")
    else:
        log2 = DQLog()
        panel = build_panel(sales[sales["Date"] <= cutoff], sku, evm, log2)
        demand, register, _ = build_demand(panel, so, ev, evm, sku, excluded_events=fz["excluded_events"])
    checks["anomalies"] = {
        "flagged": int(len(register)),
        "by_category": {k: int(v) for k, v in register["Category"].value_counts().items()},
        "demand_source": {k: int(v) for k, v in demand["Demand_Source"].value_counts().items()},
    }
    progress("recover", "done")

    # ---- 3. rows to forecast
    progress("features", "running")
    if request is not None:
        miss = [c for c in REQUEST_REQUIRED if c not in request.columns]
        if miss:
            raise ScoringError(f"the rows-to-forecast file needs the columns {', '.join(miss)} (test.csv format)")
        req, rejected = prepare_request(request, sku, demand, cutoff, horizon_end)
        req_source = "uploaded"
    else:
        grid = default_request(demand, sku, cutoff, horizon_end)
        req, rejected = prepare_request(grid, sku, demand, cutoff, horizon_end)
        req = req.drop(columns="_row")
        req_source = "all active series"
    if req.empty:
        raise ScoringError("no rows left to forecast after validation"
                           + (f" ({rejected['Reason'].value_counts().index[0]})" if len(rejected) else ""))
    checks["request"] = {
        "rows_in": int(len(request)) if request is not None else int(len(req)), "accepted": int(len(req)),
        "rejected": int(len(rejected)),
        "rejected_by_reason": {k: int(v) for k, v in rejected["Reason"].value_counts().items()} if len(rejected) else {},
    }

    # actuals: from the rows file, else the uploaded / official history after the origin
    actual = req.pop("Actual") if "Actual" in req else None
    if actual is None or actual.notna().sum() == 0:
        later = sales[(sales["Date"] > cutoff)].groupby(KEY)["Units_Sold"].sum(min_count=1)
        if len(later):
            actual = pd.Series(pd.MultiIndex.from_frame(req[KEY]).map(later), index=req.index)
            actual_source = "history after the origin"
        else:
            actual, actual_source = None, None
    else:
        actual_source = "rows file (Units_Sold)"

    # ---- 4. features + frozen model + the same lifecycle / launch / shutdown rules and bands
    dv = demand_variant(demand, fz["variant"]).sort_index() if fz["variant"] else demand
    P = Panel(dv, sku, macro, evm, req, feature_set=fz["spec"]["feature_set"])
    progress("features", "done")
    progress("score", "running")
    curves = fz["curves"]
    if curves is None:
        from .forecast import replacement_curves
        curves = replacement_curves(dv, sku)
    fc, notes = forecast_test(P, fz["model"], fz["cols"], req.drop(columns=["_row"], errors="ignore"), sku, dv, evm,
                              fz["impact"], fz["bt"], curves, band_q=fz["band_q"], origin=o)
    fc["h"] = fc["Date"].map(MIDX) - o
    if "_row" in req:
        fc["_row"] = req["_row"].to_numpy()
    progress("score", "done")

    # ---- 5. aggregates, revenue, accuracy
    progress("evaluate", "running")
    years = tuple(range(int(cutoff[:4]) + 1, int(horizon_end[:4]) + 1))
    book = price_book(dv, sku, ev, years=years, base_year=int(cutoff[:4]))
    fc = revenue_forecast(fc, book)
    hier = hierarchy(fc, fz["bt"])
    n_series = int(fc[SERIES].drop_duplicates().shape[0])
    full = n_series >= 0.9 * fz["official_series"]
    band_method = ("calibrated company band (aggregate error model)" if full
                   else "sum of SKU bands (a subset of series: wider than the true aggregate range)")
    month_tot = fc.groupby("Date").agg(Units_forecast=("Forecast", "sum"), Revenue_forecast=("Revenue", "sum"),
                                       sP10=("P10", "sum"), sP90=("P90", "sum")).reset_index()
    if full:
        tb = hier[hier["Level"] == "total"].set_index("Date")
        month_tot["Units_P10"] = month_tot["Date"].map(tb["P10"])
        month_tot["Units_P90"] = month_tot["Date"].map(tb["P90"])
    else:
        month_tot["Units_P10"], month_tot["Units_P90"] = month_tot["sP10"], month_tot["sP90"]
    ratio = (month_tot["Revenue_forecast"] / month_tot["Units_forecast"]).replace([np.inf, -np.inf], np.nan)
    month_tot["Revenue_P10"] = month_tot["Units_P10"] * ratio
    month_tot["Revenue_P90"] = month_tot["Units_P90"] * ratio

    scored_series = fc[SERIES].drop_duplicates()
    hrev = history_revenue(dv.merge(scored_series, on=SERIES))
    hist_m = (hrev[(hrev["Date"] <= cutoff) & (hrev["Date"] > MONTHS[max(0, o - 36)])]
              .groupby("Date").agg(Units_shipped=("Units_Sold", "sum"), Units_unconstrained=("Demand", "sum"),
                                   Revenue_shipped=("Revenue_shipped", "sum"),
                                   Revenue_unconstrained=("Revenue_unconstrained", "sum")).reset_index())
    last12 = hist_m[hist_m["Date"] > MONTHS[o - 12]]
    nxt12 = month_tot[month_tot["Date"] <= MONTHS[min(o + 12, len(MONTHS) - 1)]]
    pct = lambda a, b: float(a / b - 1) if b else None
    timeline = {
        "filters": {}, "band_method": band_method,
        "summary": {
            "series": n_series, "forecast_series": n_series, "history_end": cutoff,
            "units_last12": float(last12["Units_unconstrained"].sum()), "units_next12": float(nxt12["Units_forecast"].sum()),
            "revenue_last12": float(last12["Revenue_unconstrained"].sum()), "revenue_next12": float(nxt12["Revenue_forecast"].sum()),
            "units_19m": float(month_tot["Units_forecast"].sum()), "units_19m_p10": float(month_tot["Units_P10"].sum()),
            "units_19m_p90": float(month_tot["Units_P90"].sum()), "revenue_19m": float(month_tot["Revenue_forecast"].sum()),
            "units_next12_vs_last12": pct(nxt12["Units_forecast"].sum(), last12["Units_unconstrained"].sum()),
            "revenue_next12_vs_last12": pct(nxt12["Revenue_forecast"].sum(), last12["Revenue_unconstrained"].sum()),
        },
        "history": _records(hist_m),
        "forecast": _records(month_tot[["Date", "Units_forecast", "Revenue_forecast", "Units_P10", "Units_P90",
                                        "Revenue_P10", "Revenue_P90"]]),
    }

    def breakdown(col: str) -> list[dict]:
        g = fc.groupby(col).agg(Units=("Forecast", "sum"), P10=("P10", "sum"), P90=("P90", "sum"),
                                Revenue=("Revenue", "sum")).reset_index()
        g["Series"] = fc.drop_duplicates(SERIES).groupby(col).size().reindex(g[col]).to_numpy()
        return _records(g.rename(columns={col: "Member"}).sort_values("Units", ascending=False))

    first = fc.groupby(SERIES)["method"].first().str.split(";").str[0]
    per_series = (fc.groupby(SERIES + ["Product_Family", "Customer_Name", "Sales_Channel"], dropna=False)
                  .agg(Units=("Forecast", "sum"), P10=("P10", "sum"), P90=("P90", "sum"), Revenue=("Revenue", "sum"),
                       Months=("Date", "size")).reset_index())
    per_series["Method"] = pd.MultiIndex.from_frame(per_series[SERIES]).map(first)
    h12 = dv[(dv["Date"] > MONTHS[o - 12]) & (dv["Date"] <= cutoff)].groupby(SERIES)["Demand"].sum()
    per_series["Demand_last12"] = pd.MultiIndex.from_frame(per_series[SERIES]).map(h12)

    accuracy = None
    if actual is not None and actual.notna().any():
        fc["Actual"] = actual.to_numpy()
        accuracy = _accuracy(fc, dv, o, hier if full else None)
        accuracy["source"] = actual_source
        accuracy["in_sample"] = bool(fc.loc[fc["Actual"].notna(), "Date"].min() <= MODEL_TRAIN_END)
        if accuracy["in_sample"]:
            warnings.append(f"some scored months are on or before {MODEL_TRAIN_END}, inside the frozen model's training "
                            "window: that accuracy is in-sample, not a fair test (the honest out-of-sample numbers are "
                            "the 6-cutoff backtest on Model Trust)")
        e = fc[fc["Actual"].notna()].assign(AbsErr=lambda d: (d["Forecast"] - d["Actual"]).abs())
        ser = e.groupby(SERIES).agg(Actual=("Actual", "sum"), AbsErr=("AbsErr", "sum")).reset_index()
        per_series = per_series.merge(ser, on=SERIES, how="left")
        per_series["WAPE"] = per_series["AbsErr"] / per_series["Actual"].replace(0, np.nan)

    # reproducibility: the same keys in the frozen final forecast
    frozen_cmp = None
    fzd = pd.read_csv(ROOT / "outputs" / "final" / "forecast_detail.csv", usecols=KEY + ["Forecast"])
    ov = fc[KEY + ["Forecast"]].merge(fzd, on=KEY, suffixes=("", "_frozen"))
    if len(ov):
        d = (ov["Forecast"] - ov["Forecast_frozen"]).abs()
        frozen_cmp = {"rows": int(len(ov)), "max_abs_diff": float(d.max()), "identical": bool(d.max() < 1e-6),
                      "total": float(ov["Forecast"].sum()), "total_frozen": float(ov["Forecast_frozen"].sum()),
                      "change_pct": pct(ov["Forecast"].sum(), ov["Forecast_frozen"].sum())}
    progress("evaluate", "done")

    fc_out = fc.sort_values("_row") if "_row" in fc else fc
    detail_cols = ["Date", "SKU_ID", "Region", "Product_Family", "Customer_Name", "Sales_Channel", "h", "Forecast",
                   "P10", "P50", "P90", "Units_Sold_Forecast", "Unit_Price", "Revenue", "method"] + \
                  (["Actual"] if "Actual" in fc else [])
    files = {
        "submission.csv": fc_out[KEY + ["Units_Sold_Forecast"]],
        "forecast_detail.csv": fc_out[detail_cols],
        "series_summary.csv": per_series.sort_values("Units", ascending=False),
    }
    if len(rejected):
        files["rejected_rows.csv"] = rejected.rename(columns={"_row": "CSV_line"})
    if dq_table is not None and len(dq_table):
        files["dq_issue_log.csv"] = dq_table
    if len(register):
        files["anomaly_register.csv"] = register

    result = {
        "status": "done", "seconds": round(time.time() - t0, 1),
        "model": {"name": fz["manifest"]["selected_model"], "frozen_at": fz["manifest"]["frozen_at"],
                  "trained_through": MODEL_TRAIN_END, "features": len(fz["cols"])},
        "inputs": {"history": hist_source, "history_end": hist_end, "rows_to_forecast": req_source,
                   "cutoff": cutoff, "horizon": [MONTHS[o + 1], horizon_end], "horizon_months": MIDX[horizon_end] - o},
        "kpis": {
            "rows": int(len(fc)), "series": n_series, "units": float(fc["Forecast"].sum()),
            "units_p10": timeline["summary"]["units_19m_p10"], "units_p90": timeline["summary"]["units_19m_p90"],
            "revenue": float(fc["Revenue"].sum()), "band_method": band_method,
            "zero_by_lifecycle": int(notes.get("rows_zero_by_lifecycle", 0)),
            "methods": {k: int(v) for k, v in fc["method"].str.split(";").str[0].value_counts().items()},
        },
        "timeline": timeline,
        "by_family": breakdown("Product_Family"), "by_region": breakdown("Region"),
        "series": _records(per_series.sort_values("Units", ascending=False).head(500)),
        "series_total": int(len(per_series)),
        "accuracy": accuracy, "frozen_comparison": frozen_cmp,
        "checks": checks, "rejected_sample": _records(rejected.rename(columns={"_row": "CSV_line"}).head(50)) if len(rejected) else [],
        "warnings": warnings, "files": sorted(files),
    }
    return {"result": result, "tables": files}


def _accuracy(fc: pd.DataFrame, dv: pd.DataFrame, o: int, hier: pd.DataFrame | None) -> dict:
    """Forecast vs actual: SKU-month, family-month and total-month WAPE, bias, P10-P90
    coverage, and the seasonal-naive forecast (same month last year) on the same rows."""
    e = fc[fc["Actual"].notna()].copy()
    # seasonal naive: the latest same-calendar-month value at or before the origin
    hist = dv.set_index(KEY)["Units_Sold"]
    t = e["Date"].map(MIDX).to_numpy()
    back = t - 12 * np.ceil((t - o) / 12).astype(int)
    e["Naive"] = pd.MultiIndex.from_arrays([pd.Series(back).map(lambda i: MONTHS[i]).to_numpy(),
                                            e["SKU_ID"].to_numpy(), e["Region"].to_numpy()]).map(hist).to_numpy()
    e["Naive"] = e["Naive"].fillna(0.0)

    def m(d: pd.DataFrame) -> dict:
        y, f = d["Actual"].sum(), d["Forecast"].sum()
        return {"rows": int(len(d)), "actual": float(y), "forecast": float(f),
                "WAPE": float((d["Forecast"] - d["Actual"]).abs().sum() / y) if y else None,
                "Bias": float((f - y) / y) if y else None,
                "MAE": float((d["Forecast"] - d["Actual"]).abs().mean()),
                "Naive_WAPE": float((d["Naive"] - d["Actual"]).abs().sum() / y) if y else None,
                "Coverage_P10_P90": float(((d["Actual"] >= d["P10"]) & (d["Actual"] <= d["P90"])).mean())}

    def agg_wape(by: list) -> float | None:
        g = e.groupby(["Date"] + by)[["Actual", "Forecast"]].sum()
        return float((g["Forecast"] - g["Actual"]).abs().sum() / g["Actual"].sum()) if g["Actual"].sum() else None

    bucket = pd.cut(e["h"], [0, 3, 6, 12, 19], labels=["1-3m", "4-6m", "7-12m", "13-19m"])
    monthly = e.groupby("Date").agg(Actual=("Actual", "sum"), Forecast=("Forecast", "sum"),
                                    P10=("P10", "sum"), P90=("P90", "sum"), Naive=("Naive", "sum")).reset_index()
    if hier is not None:
        tb = hier[hier["Level"] == "total"].set_index("Date")
        monthly["P10"], monthly["P90"] = monthly["Date"].map(tb["P10"]), monthly["Date"].map(tb["P90"])
    return {
        "overall": m(e),
        "family_month_WAPE": agg_wape(["Product_Family"]), "total_month_WAPE": agg_wape([]),
        "by_family": [{"Member": k, **m(g)} for k, g in e.groupby("Product_Family")],
        "by_region": [{"Member": k, **m(g)} for k, g in e.groupby("Region")],
        "by_horizon": [{"Member": str(k), **m(g)} for k, g in e.groupby(bucket, observed=True)],
        "monthly": _records(monthly),
    }


def _records(df: pd.DataFrame) -> list[dict]:
    out = df.replace([np.inf, -np.inf], np.nan).astype(object).where(df.notna(), None)
    recs = out.to_dict("records")
    for r in recs:
        for k, v in r.items():
            if isinstance(v, (np.floating, float)):
                r[k] = None if v != v else round(float(v), 4)
            elif isinstance(v, np.integer):
                r[k] = int(v)
            elif isinstance(v, np.bool_):
                r[k] = bool(v)
    return recs

