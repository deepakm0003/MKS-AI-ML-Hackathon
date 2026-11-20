"""Stage 1 - cleaning. Reads data/raw, writes data/processed + outputs/quality."""
from __future__ import annotations

import time

import pandas as pd

from .clean_reference import clean_events, clean_macro, clean_sku_master, clean_stockouts
from .clean_sales import clean_sales
from .config import PROCESSED, QUALITY, RAW
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
