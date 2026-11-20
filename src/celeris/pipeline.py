"""Stage 1 - cleaning. Reads data/raw, writes data/processed + outputs/quality."""
from __future__ import annotations

import json
import time

import pandas as pd

from .clean_reference import clean_events, clean_macro, clean_sku_master, clean_stockouts
from .clean_sales import clean_sales
from .config import PROCESSED, QUALITY, RAW, ROOT

ROOT_OUT = ROOT / "outputs"
from .dq import DQLog
from .panel import build_panel


def read_raw(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / name, dtype=str, keep_default_na=True)


def check_test(test: pd.DataFrame, sku: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    f = "test.csv"
    log.profile(f, test, "before")
    dup = test[test.duplicated(["Date", "SKU_ID", "Region"])]
    log.add(dup, file=f, issue_type="duplicate_key", category="error", field_name="Date-SKU-Region",
            action="flagged", rule="test keys must be unique")
    eol = test["SKU_ID"].map(sku.set_index("SKU_ID")["EOL_Date"])
    launch = test["SKU_ID"].map(sku.set_index("SKU_ID")["Launch_Date"])
    after = eol.notna() & (test["Date"] > eol)
    log.add(test[after].assign(n=eol[after]), file=f, issue_type="row_after_eol", category="info",
            field_name="Date", corrected="n", action="forecast forced to 0",
            rule="no sales after EOL_Date (business rule 5)", row_ref="(test row)")
    before = test["Date"] < launch
    log.add(test[before].assign(n=launch[before]), file=f, issue_type="row_before_launch",
            category="info", field_name="Date", corrected="n", action="forecast forced to 0",
            rule="no sales before Launch_Date (business rule 5)", row_ref="(test row)")
    log.profile(f, test, "after")
    return test


def refine_with_stockouts(sales: pd.DataFrame, so: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    """Rows rebuilt x10 lose the last digit (18 was booked as 2 -> 20). Where the stockout
    file records the exact Shipped_Units for that month, use it."""
    k = ["Date", "SKU_ID", "Region"]
    j = sales.merge(so.loc[so["Valid"], k + ["Shipped_Units"]], on=k, how="left")
    sel = j["Units_Fix"].eq("uom_x10") & j["Shipped_Units"].notna() & (j["Shipped_Units"] != j["Units_Sold"])
    log.add(j[sel], file="train.csv", issue_type="units_uom_precision", category="error",
            field_name="Units_Sold", original="Units_Sold", corrected="Shipped_Units",
            action="set to stockout-file shipped units",
            rule="x10 rebuild loses the last digit; stockout file has the exact shipment")
    price = j["Unit_Price_USD"]
    j.loc[sel, "Units_Sold"] = j.loc[sel, "Shipped_Units"]
    j.loc[sel, "Revenue_USD"] = (j.loc[sel, "Units_Sold"] * price[sel]).round(2)
    return j.drop(columns="Shipped_Units")


UNIT_ERROR_TYPES = {
    "negative_units": "sign error",
    "units_scale_error": "units x10/x100 entry error",
    "units_uom_block_x0.1": "units booked in packs of 10",
    "missing_units": "blank units recovered from revenue",
}


def run_anomalies(verbose: bool = True) -> dict:
    from .anomalies import build_demand, transient_candidates
    from .structural import event_impact, series_profile, structural_register
    t0 = time.time()
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    panel, so, ev, evm, sku = rd("panel"), rd("stockouts"), rd("events"), rd("events_monthly"), rd("sku_master")

    # Pass 1: measure every candidate event; pass 2: exclude from the model target only
    # the events whose impact is measurable (a "no effect" event leaves the data alone).
    prelim, _, _ = build_demand(panel, so, ev, evm, sku)
    impact0 = event_impact(prelim, ev, evm)
    cands = transient_candidates(ev)
    measured = set(impact0.loc[impact0["Event_ID"].isin(cands)
                               & impact0["Verdict"].isin(["material", "weak"]), "Event_ID"])
    demand, register, findings = build_demand(panel, so, ev, evm, sku, excluded_events=measured)
    findings["events_not_excluded_no_effect"] = sorted(cands - measured)

    # data errors fixed in stage 1 that changed units also belong in the anomaly register
    log = pd.read_csv(QUALITY / "dq_issue_log.csv", dtype=str)
    err = log[log["issue_type"].isin(UNIT_ERROR_TYPES)]
    errs = pd.DataFrame({
        "Date": err["date"], "SKU_ID": err["sku_id"], "Region": err["region"],
        "Units_Shipped": pd.to_numeric(err["corrected"], errors="coerce"),
        "Type": err["issue_type"], "Category": "data_error", "Detection": "stage-1 reconciliation",
        "Reason": err["issue_type"].map(UNIT_ERROR_TYPES) + ": raw value " + err["original"].fillna(""),
        "Action": "corrected (" + err["rule"] + ")", "Confidence": "high"})
    attrs = demand.set_index(["Date", "SKU_ID", "Region"])[
        ["Product_Family", "Customer_Name", "Sales_Channel", "Demand", "Expected"]]
    errs = errs.join(attrs, on=["Date", "SKU_ID", "Region"])
    register = pd.concat([errs[register.columns], register], ignore_index=True)
    register = register.sort_values(["Date", "SKU_ID", "Region", "Category"]).reset_index(drop=True)

    test = rd("test")
    impact = event_impact(demand, ev, evm)
    profile = series_profile(demand)
    struct = structural_register(demand, sku, test, ev)

    out = ROOT_OUT / "anomalies"
    out.mkdir(parents=True, exist_ok=True)
    impact.to_csv(out / "event_impact.csv", index=False)
    struct.to_csv(out / "structural_register.csv", index=False)
    profile.to_parquet(PROCESSED / "series_profile.parquet", index=False)
    demand.to_parquet(PROCESSED / "demand.parquet", index=False)
    register.to_csv(out / "anomaly_register.csv", index=False)
    with open(out / "findings.json", "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, default=str)
    if verbose:
        print(f"anomalies done in {time.time() - t0:.1f}s; register rows {len(register):,}")
        print(register.groupby(["Category", "Type"]).size().rename("rows").to_string())
        print(demand["Demand_Source"].value_counts().to_string())
        print(json.dumps(findings, indent=1, default=str))
        print(impact[["Event_ID", "Event_Type", "Scope", "Start", "Shipped_Impact_Pct", "Shipped_Z", "Demand_Impact_Pct", "Typical_Impact_Pct", "Verdict"]].to_string())
        print(struct.groupby("Type").size().to_string())
        print(profile["Demand_Class"].value_counts().to_string())
    return {"demand": demand, "register": register}


def run_cleaning(verbose: bool = True) -> dict:
    t0 = time.time()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    log = DQLog()

    sku = clean_sku_master(read_raw("sku_master.csv"), log)
    macro = clean_macro(read_raw("macro_indicators.csv"), log)
    events, events_monthly = clean_events(read_raw("events_calendar.csv"), log)
    stockouts = clean_stockouts(read_raw("inventory_stockouts.csv"), log)
    test = check_test(read_raw("test.csv"), sku, log)
    customers = sorted(test["Customer_Name"].dropna().unique())
    sales = clean_sales(read_raw("train.csv"), sku, customers, events, events_monthly, log)
    sales = refine_with_stockouts(sales, stockouts, log)
    panel = build_panel(sales, sku, events_monthly, log)

    sku.to_parquet(PROCESSED / "sku_master.parquet", index=False)
    macro.to_parquet(PROCESSED / "macro.parquet", index=False)
    events.to_parquet(PROCESSED / "events.parquet", index=False)
    events_monthly.to_parquet(PROCESSED / "events_monthly.parquet", index=False)
    stockouts.to_parquet(PROCESSED / "stockouts.parquet", index=False)
    sales.to_parquet(PROCESSED / "sales_clean.parquet", index=False)
    panel.to_parquet(PROCESSED / "panel.parquet", index=False)
    test.to_parquet(PROCESSED / "test.parquet", index=False)
    log.write(QUALITY)

    summary = log.summary()
    if verbose:
        print(f"cleaning done in {time.time() - t0:.1f}s")
        print(f"  sales rows: raw {summary['profiles']['train.csv']['before']['rows']:,} -> "
              f"clean {len(sales):,};  panel cells {len(panel):,}")
        print(f"  issues logged: {summary['total_issues']:,}")
        for r in summary["issues"]:
            print(f"    {r['file']:<26}{r['category']:<10}{r['issue_type']:<38}{r['rows']:>7,}  {r['action']}")
    return {"sales": sales, "panel": panel, "sku": sku, "macro": macro, "events": events,
            "events_monthly": events_monthly, "stockouts": stockouts, "test": test, "log": log}


def run_drivers(verbose: bool = True) -> dict:
    """Stage 3a: macro lead/lag (with stability check) and the EV shift."""
    from .drivers import best_lags, ev_shift, lag_stability, lead_lag
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    demand, macro, sku = rd("demand"), rd("macro"), rd("sku_master")
    out = ROOT_OUT / "drivers"
    out.mkdir(parents=True, exist_ok=True)
    ll = lead_lag(demand, macro)
    best = best_lags(ll)
    stab = lag_stability(demand, macro)
    ev_table, ev_stats = ev_shift(demand, sku, macro)
    ll.to_csv(out / "lead_lag.csv", index=False)
    best.to_csv(out / "best_lags.csv", index=False)
    stab.to_csv(out / "lag_stability.csv", index=False)
    ev_table.to_csv(out / "ev_shift_by_year.csv", index=False)
    with open(out / "ev_shift.json", "w", encoding="utf-8") as f:
        json.dump(ev_stats, f, indent=2)
    if verbose:
        top = best.loc[best.groupby("Product_Family")["Corr"].apply(lambda s: s.abs().idxmax())]
        print("strongest leading indicator per family:")
        print(top[["Product_Family", "Indicator", "Lag", "Corr"]].round(2).to_string(index=False))
        print(f"stable indicator-family links: {int(stab['Stable'].sum())} of {len(stab)}")
        print(json.dumps(ev_stats))
    return {"lead_lag": ll, "best": best, "stability": stab}


def run_backtest_stage(verbose: bool = True, cutoffs=None, variants=None) -> dict:
    """Stage 3c: rolling-origin backtest (19-month horizon) of baselines and the global model."""
    from .backtest import CUTOFFS, run_backtest, score
    from .features import Panel
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    P = Panel(rd("demand"), rd("sku_master"), rd("macro"), rd("events_monthly"), rd("test"))
    bt = run_backtest(P, cutoffs=cutoffs or CUTOFFS, lgb_variants=variants, verbose=verbose)
    out = ROOT_OUT / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    keep = ["cutoff", "target_month", "h", "series", "Product_Family", "Region", "Sales_Channel",
            "Customer_Name", "y", "w"] + [c for c in bt.columns if c.startswith("f_")]
    bt[keep].to_parquet(out / "backtest_predictions.parquet", index=False)
    pc = [c for c in bt.columns if c.startswith("f_")]
    tables = {"overall": score(bt, pc), "by_cutoff": score(bt, pc, "cutoff"),
              "by_family": score(bt, pc, "Product_Family"), "by_region": score(bt, pc, "Region"),
              "by_horizon": score(bt, pc, "h")}
    for name, t in tables.items():
        t.columns = [f"{a.removeprefix('f_')}_{b}" for a, b in t.columns]
        t.round(4).to_csv(out / f"metrics_{name}.csv")
    if verbose:
        print(tables["overall"].T.round(3).to_string())
    return {"backtest": bt, **tables}
