"""Monthly panel: one row for every month of every SKU-Region series.

Business rule 3: a missing row is NOT a zero. Each grid cell therefore gets a status:
  observed       a cleaned row exists (Units may be 0 = no order)
  missing_value  a row exists but units could not be recovered
  missing_row    no row although the series was active (gap)
  not_active     before the series started / after it ended (launch, EOL, lost account,
                 region not yet open) - structural, not a gap
"""
from __future__ import annotations

import pandas as pd

from .config import HISTORY_END
from .dq import DQLog


def build_panel(sales: pd.DataFrame, sku: pd.DataFrame, events_monthly: pd.DataFrame,
                log: DQLog) -> pd.DataFrame:
    s = sales.copy()
    first = s.groupby(["SKU_ID", "Region"])["Date"].min()
    last = s.groupby(["SKU_ID", "Region"])["Date"].max()
    # A series only 'ends' early at its EOL or after >=3 silent months; a missing final
    # month or two is a gap (missing_row), not a lost account.
    eol_s = last.index.get_level_values(0).map(sku.set_index("SKU_ID")["EOL_Date"])
    gap_m = (pd.Period(HISTORY_END, freq="M") - pd.PeriodIndex(last.values, freq="M")).map(lambda x: x.n)
    ended = (pd.Series(eol_s, index=last.index).notna() & (last >= pd.Series(eol_s, index=last.index).fillna("9999"))) | (gap_m >= 3)
    last = last.where(ended, HISTORY_END)
    months = pd.period_range(s["Date"].min(), HISTORY_END, freq="M").strftime("%Y-%m")

    series = first.reset_index()[["SKU_ID", "Region"]]
    grid = series.merge(pd.DataFrame({"Date": months}), how="cross")
    grid["first"] = grid.set_index(["SKU_ID", "Region"]).index.map(first).values
    grid["last"] = grid.set_index(["SKU_ID", "Region"]).index.map(last).values
    eol = grid["SKU_ID"].map(sku.set_index("SKU_ID")["EOL_Date"])

    p = grid.merge(s, on=["Date", "SKU_ID", "Region"], how="left", indicator=True)
    in_life = (p["Date"] >= p["first"]) & (p["Date"] <= p["last"])
    # a series that stops before the end of history: an ended account / EOL, not a gap
    p["status"] = "not_active"
    p.loc[in_life & (p["_merge"] == "left_only"), "status"] = "missing_row"
    p.loc[p["_merge"] == "both", "status"] = "observed"
    p.loc[(p["_merge"] == "both") & p["Units_Missing"].fillna(False).astype(bool), "status"] = "missing_value"

    # Explain gaps with the events calendar where possible (e.g. ERP migration).
    sys_ev = events_monthly[events_monthly["Event_Type"].isin(["System"])]
    sys_keys = set(zip(sys_ev["Date"], sys_ev["Scope_Region"].fillna("ALL")))
    explained = [(d, r) in sys_keys or (d, "ALL") in sys_keys for d, r in zip(p["Date"], p["Region"])]
    p["gap_reason"] = ""
    gap = p["status"].eq("missing_row")
    p.loc[gap & pd.Series(explained, index=p.index), "gap_reason"] = "system event (e.g. ERP migration)"
    p.loc[gap & p["gap_reason"].eq(""), "gap_reason"] = "unexplained missing row"

    log.add(p[gap].assign(Record_ID=""), file="train.csv", issue_type="missing_row",
            category="gap", field_name="(row)", action="flagged; imputed for features, excluded from training target",
            rule="a missing row is not a zero (business rule 3)",
            corrected="gap_reason", row_ref="(none)")

    ended = p.groupby(["SKU_ID", "Region"])["last"].first()
    ended = ended[ended < HISTORY_END].reset_index()
    ended["eol"] = ended["SKU_ID"].map(sku.set_index("SKU_ID")["EOL_Date"])
    ended["Date"] = ended["last"]
    log.add(ended, file="train.csv", issue_type="series_ended_early", category="info",
            field_name="(series)", original="last", corrected="eol", action="flagged for anomaly review",
            rule="series stops before 2026-10: EOL or lost account", row_ref="(series)")

    p["Units_Sold"] = p["Units_Sold"].where(p["status"].eq("observed"))
    # carry slowly-changing attributes into gap months so filters still work
    for c in ["Product_Family", "Business_Unit", "SKU_Description", "Customer_Name", "Sales_Channel"]:
        p[c] = p.groupby(["SKU_ID", "Region"])[c].transform(lambda x: x.ffill().bfill())
    p["Year"] = p["Date"].str[:4].astype(int)
    p["Month"] = p["Date"].str[5:].astype(int)
    p["EOL_Date"] = eol.values
    cols = ["Date", "Year", "Month", "SKU_ID", "Region", "Product_Family", "Business_Unit",
            "SKU_Description", "Customer_Name", "Sales_Channel", "Units_Sold", "Unit_Price_USD",
            "Revenue_USD", "status", "gap_reason", "Units_Fix", "Price_Fix", "Region_Inferred",
            "first", "last"]
    return p[cols].rename(columns={"first": "Series_First", "last": "Series_Last"}) \
                  .sort_values(["SKU_ID", "Region", "Date"]).reset_index(drop=True)
