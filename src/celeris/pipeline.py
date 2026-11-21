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


def write_run_report(log: DQLog, sales: pd.DataFrame, panel: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Machine-readable summary of one cleaning run, with hard validation checks."""
    t = log.table()
    n = lambda types: int(t["issue_type"].isin(types).sum())
    tr = t[t["file"] == "train.csv"]
    checks = {
        "one_row_per_date_sku_region": bool(not sales.duplicated(["Date", "SKU_ID", "Region"]).any()),
        "no_negative_units": bool((sales["Units_Sold"].dropna() >= 0).all()),
        "revenue_reconciles": bool(((sales["Revenue_USD"] - sales["Units_Sold"] * sales["Unit_Price_USD"]).abs()
                                    .dropna() <= 0.05).all()),
        "all_skus_in_master": bool(sales["SKU_ID"].notna().all()),
        "test_keys_unique": bool(not test.duplicated(["Date", "SKU_ID", "Region"]).any()),
    }
    rep = {
        "run_id": time.strftime("%Y-%m-%d_%H%M%S"),
        "rows_ingested": int(log.profiles["train.csv"]["before"]["rows"]),
        "rows_clean": int(len(sales)),
        "duplicates_removed": n(["exact_duplicate_row", "reloaded_record_id", "duplicate_date_sku_region"]),
        "date_corrections": n(["non_standard_date_format", "date_year_typo", "year_month_disagree_with_date"]),
        "label_corrections": n(["sku_id_format", "region_label", "channel_label", "customer_name_variant"]),
        "unit_corrections": n(["negative_units", "units_scale_error", "units_uom_block_x0.1", "units_uom_precision",
                               "units_thousands_separator"]),
        "price_corrections": int(tr["issue_type"].str.startswith("price_").sum()),
        "revenue_corrections": n(["revenue_scale_error", "revenue_mismatch", "missing_revenue"]),
        "missing_values_recovered": n(["missing_units", "missing_region", "missing_product_family",
                                       "missing_sku_description"]),
        "missing_values_unrecoverable": n(["missing_units_unrecoverable", "missing_region_unresolved"]),
        "missing_rows_flagged": int((panel["status"] == "missing_row").sum()),
        "reference_conflicts": int((t["category"] == "reference").sum()),
        "issues_by_file": t.groupby("file").size().astype(int).to_dict(),
        "checks": checks,
        "validation_status": "PASS" if all(checks.values()) else "FAIL",
    }
    with open(QUALITY / "run_report.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    return rep


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
    write_run_report(log, sales, panel, test)

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


def run_forecast(verbose: bool = True, params=None, rounds=None) -> dict:
    """Stage 4: train the final model on all history and forecast the test window."""
    from .backtest import N_ROUNDS
    from .features import Panel
    from .forecast import band_coverage, forecast_test, hierarchy, replacement_curves, save_model, train_final
    t0 = time.time()
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    demand, sku, macro, evm, test = rd("demand"), rd("sku_master"), rd("macro"), rd("events_monthly"), rd("test")
    bt = pd.read_parquet(ROOT_OUT / "backtest" / "backtest_predictions.parquet")
    impact = pd.read_csv(ROOT_OUT / "anomalies" / "event_impact.csv")
    P = Panel(demand, sku, macro, evm, test)
    model, cols, n_train = train_final(P, params, rounds or N_ROUNDS)
    curves = replacement_curves(demand, sku)
    fc, notes = forecast_test(P, model, cols, test, sku, demand, evm, impact, bt, curves)

    out = ROOT_OUT / "forecast"
    out.mkdir(parents=True, exist_ok=True)
    sub = fc[["Date", "SKU_ID", "Region", "Units_Sold_Forecast"]]
    assert len(sub) == len(test) and sub["Units_Sold_Forecast"].notna().all()
    assert (sub["Units_Sold_Forecast"] >= 0).all()
    assert (sub[["Date", "SKU_ID", "Region"]].values == test[["Date", "SKU_ID", "Region"]].values).all()
    sub.to_csv(out / "submission.csv", index=False)
    cols_out = ["Date", "Year", "Month", "Product_Family", "Business_Unit", "SKU_ID", "SKU_Description",
                "Customer_Name", "Sales_Channel", "Region", "h", "Forecast", "P10", "P50", "P90",
                "Units_Sold_Forecast", "method"]
    fc[cols_out].to_csv(out / "forecast_detail.csv", index=False)
    hier = hierarchy(fc, bt)
    hier.to_csv(out / "forecast_hierarchy.csv", index=False)
    cov = band_coverage(bt)
    cov.to_csv(out / "band_coverage.csv", index=False)
    meta = {"trained_rows": n_train, "history_end": "2026-10", "horizon": 19,
            "backtest": json.loads(pd.read_csv(ROOT_OUT / "backtest" / "metrics_overall.csv").to_json(orient="records"))[0],
            "lifecycle_curves": curves, "rules": notes}
    save_model(model, cols, ROOT_OUT / "models", meta)
    with open(out / "forecast_notes.json", "w", encoding="utf-8") as f:
        json.dump({"curves": curves, **notes}, f, indent=2, default=str)
    if verbose:
        tot = hier[hier["Level"] == "total"]
        print(f"forecast done in {time.time() - t0:.0f}s; trained on {n_train:,} rows; {len(sub):,} test rows")
        print(f"19-month total: {tot['Forecast'].sum():,.0f} units "
              f"(P10 {tot['P10'].sum():,.0f} / P90 {tot['P90'].sum():,.0f})")
        print(fc["method"].str.split(";").str[0].value_counts().to_string())
        print("held-out P10-P90 coverage by level:", cov.groupby("Level")["Coverage_P10_P90"].mean().round(2).to_dict())
        print(json.dumps(notes, indent=1, default=str)[:1500])
    return {"forecast": fc, "hierarchy": hier, "model": model}


def run_intelligence(verbose: bool = True) -> dict:
    """Stage 6: planning intelligence on the champion forecast."""
    from .intelligence import (build_signals, classify, exceptions, interval_reliability, lifecycle_alerts,
                               market_changes, to_json_records)
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    demand, sku = rd("demand"), rd("sku_master")
    # the frozen final forecast (Phase F) when it exists, else the stage-4 champion forecast
    final = ROOT_OUT / "final" / "manifest.json"
    if final.exists():
        model_name = json.loads(final.read_text(encoding="utf-8"))["selected_model"]
        fc = pd.read_csv(ROOT_OUT / "final" / "forecast_detail.csv")
        strata = True
    else:
        model_name, strata = "champion", False
        fc = pd.read_csv(ROOT_OUT / "forecast" / "forecast_detail.csv")
    pred = pd.read_parquet(ROOT / "artifacts" / "experiments" / model_name / "predictions.parquet")
    stress = pd.read_csv(ROOT / "artifacts" / "reports" / "macro_stress.csv")
    reg = pd.read_csv(ROOT_OUT / "anomalies" / "anomaly_register.csv")
    struct = pd.read_csv(ROOT_OUT / "anomalies" / "structural_register.csv")

    rel, widen = interval_reliability(pred, strata)
    market = market_changes(demand, fc)
    sig = build_signals(demand, fc, pred, stress, reg, struct, sku, widen)
    sig = classify(sig, market)
    exc = exceptions(sig)
    life = lifecycle_alerts(fc, sku)

    out = ROOT_OUT / "intelligence"
    out.mkdir(parents=True, exist_ok=True)
    flat = sig.copy()
    flat["reason_codes"] = flat["reason_codes"].map(lambda c: "|".join(c))
    flat.reset_index().to_csv(out / "series_signals.csv", index=False)
    exc_flat = exc.copy()
    exc_flat["reason_codes"] = exc_flat["reason_codes"].map(lambda c: "|".join(c))
    exc_flat.reset_index().to_csv(out / "exceptions.csv", index=False)
    market.to_csv(out / "market_signals.csv", index=False)
    life.to_csv(out / "lifecycle_alerts.csv", index=False)
    rel.to_csv(out / "interval_reliability.csv", index=False)
    with open(out / "series_signals.json", "w", encoding="utf-8") as f:
        json.dump(to_json_records(sig), f, indent=1)
    codes = pd.Series([c for cs in sig["reason_codes"] for c in cs]).value_counts()
    summary = {
        "forecast_model": model_name,
        "series": int(len(sig)),
        "status_counts": sig["forecast_status"].value_counts().to_dict(),
        "risk_level_counts": sig["risk_level"].value_counts().to_dict(),
        "sustained_surge": int(sig["sustained_surge"].sum()), "sustained_decline": int(sig["sustained_decline"].sum()),
        "exceptions": int(len(exc)), "exceptions_by_tier": exc["tier"].value_counts().to_dict(),
        "exceptions_by_trigger": exc["trigger"].value_counts().to_dict(), "reason_code_counts": codes.to_dict(),
        "market_headline": market[market["Level"] == "total"][["signal", "yoy_last3m", "yoy_last12m",
                                                               "forecast_next12_vs_last12"]].to_dict("records")[0],
        "band_widening": {f"{k[0]}={k[1]}": v for k, v in widen.items()},
        "market_signals": market[market["signal"] != "STEADY"][["Level", "Member", "signal", "acceleration"]]
            .to_dict("records"),
    }
    with open(out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    if verbose:
        print(json.dumps({k: v for k, v in summary.items() if k != "market_signals"}, indent=1, default=str))
        print(market.to_string(index=False))
    return {"signals": sig, "exceptions": exc, "market": market, "lifecycle": life, "reliability": rel}


def run_final_stage(verbose: bool = True) -> dict:
    """Stage 7 (Phase F): select the model, freeze the final forecast, validate and export."""
    from .final import run_final
    return run_final(log=print if verbose else (lambda *a: None))
