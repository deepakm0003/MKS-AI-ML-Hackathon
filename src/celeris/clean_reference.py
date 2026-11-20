"""Cleaning for the reference files: sku_master, macro_indicators, events_calendar,
inventory_stockouts."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import FORECAST_END, HISTORY_END, REGION_ALIASES
from .dq import DQLog
from .parsing import map_alias, normalise_sku, parse_month


# --------------------------------------------------------------------------- sku master
def clean_sku_master(raw: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    f = "sku_master.csv"
    log.profile(f, raw, "before")
    sk = raw.copy()
    sk["SKU_ID"] = sk["SKU_ID"].map(normalise_sku)

    dups = sk[sk.duplicated("SKU_ID", keep="first")]
    log.add(dups, file=f, issue_type="duplicate_sku", category="error", field_name="SKU_ID",
            action="dropped", rule="one row per SKU", row_ref="SKU_ID")
    sk = sk.drop_duplicates("SKU_ID", keep="first")

    # Each family belongs to exactly one business unit: the majority BU is authoritative.
    fam_bu = sk.groupby("Product_Family")["Business_Unit"].agg(lambda s: s.mode().iloc[0])
    bad = sk[sk["Business_Unit"] != sk["Product_Family"].map(fam_bu)].copy()
    bad["fix"] = bad["Product_Family"].map(fam_bu)
    log.add(bad, file=f, issue_type="bu_family_conflict", category="reference",
            field_name="Business_Unit", original="Business_Unit", corrected="fix",
            action="corrected", rule="each family belongs to exactly one BU (majority BU)",
            row_ref="SKU_ID")
    sk["Business_Unit"] = sk["Product_Family"].map(fam_bu)

    for c in ["Launch_Date", "EOL_Date"]:
        sk[c] = sk[c].map(parse_month)
    sk["Replaces_SKU"] = sk["Replaces_SKU"].map(normalise_sku)

    # Lifecycle status must agree with the dates (as of the end of history).
    exp = np.select(
        [sk["Launch_Date"] > HISTORY_END,
         sk["EOL_Date"].notna() & (sk["EOL_Date"] <= HISTORY_END),
         sk["EOL_Date"].notna() & (sk["EOL_Date"] > HISTORY_END)],
        ["Planned Launch", "Discontinued", "EOL Announced"], default="Active")
    bad = sk[sk["Lifecycle_Status"] != exp].assign(exp=exp[sk["Lifecycle_Status"] != exp])
    log.add(bad, file=f, issue_type="lifecycle_status_conflict", category="reference",
            field_name="Lifecycle_Status", original="Lifecycle_Status", corrected="exp",
            action="flagged", rule="status implied by Launch/EOL dates", row_ref="SKU_ID")

    orphan = sk[sk["Replaces_SKU"].notna() & ~sk["Replaces_SKU"].isin(sk["SKU_ID"])]
    log.add(orphan, file=f, issue_type="unknown_predecessor", category="reference",
            field_name="Replaces_SKU", original="Replaces_SKU", action="flagged",
            rule="Replaces_SKU must exist in master", row_ref="SKU_ID")

    log.profile(f, sk, "after")
    return sk.reset_index(drop=True)


# --------------------------------------------------------------------------- macro
def clean_macro(raw: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    f = "macro_indicators.csv"
    log.profile(f, raw, "before")
    m = raw.copy()
    m["Date"] = m["Date"].map(parse_month)
    cols = [c for c in m.columns if c not in ("Date", "Year", "Month")]
    m[cols] = m[cols].apply(pd.to_numeric, errors="coerce")

    # Duplicate months: keep the version that is most consistent with its neighbours.
    m = m.sort_values("Date").reset_index(drop=True)
    dup_dates = m.loc[m["Date"].duplicated(keep=False), "Date"].unique()
    drop_idx = []
    for d in dup_dates:
        idx = m.index[m["Date"] == d]
        prev_ = m.loc[m["Date"] < d, cols].tail(1).mean()
        next_ = m.loc[m["Date"] > d, cols].head(1).mean()
        target = (prev_ + next_) / 2
        scale = m[cols].std()
        dist = [((m.loc[i, cols] - target).abs() / scale).sum() for i in idx]
        keep = idx[int(np.argmin(dist))]
        drop_idx += [i for i in idx if i != keep]
    log.add(m.loc[drop_idx], file=f, issue_type="duplicate_month", category="error",
            field_name="Date", action="dropped",
            rule="keep the duplicate closest to the neighbouring months", row_ref="Date")
    m = m.drop(index=drop_idx).reset_index(drop=True)

    # Year / Month columns are rebuilt from Date.
    m["Year"] = m["Date"].str[:4].astype(int)
    m["Month"] = m["Date"].str[5:].astype(int)

    # Percent stored as a fraction (e.g. -0.015 instead of -1.5).
    c = "Auto_Production_YoY_Pct"
    mask = m[c].abs().lt(0.1) & m[c].ne(0)
    log.add(m[mask].assign(o=m.loc[mask, c], n=m.loc[mask, c] * 100), file=f,
            issue_type="unit_error_fraction_vs_percent", category="error", field_name=c,
            original="o", corrected="n", action="corrected", rule="value x100 (stored as fraction)",
            row_ref="Date")
    m.loc[mask, c] = m.loc[mask, c] * 100

    # Decimal-shift errors: a value ~10x off its neighbours (e.g. PMI 4.79 -> 47.9).
    for c in cols:
        s = m[c]
        nb = pd.concat([s.shift(1), s.shift(-1), s.shift(2), s.shift(-2)], axis=1).median(axis=1)
        ratio = s / nb
        for factor, lo, hi in [(10, 0.07, 0.14), (0.1, 7, 14)]:
            mask = ratio.between(lo, hi) & nb.abs().gt(1)
            if mask.any():
                log.add(m[mask].assign(o=s[mask], n=s[mask] * factor), file=f,
                        issue_type="decimal_shift", category="error", field_name=c,
                        original="o", corrected="n", action="corrected",
                        rule=f"value x{factor} (≈10x off neighbouring months)", row_ref="Date")
                m.loc[mask, c] = s[mask] * factor

    # Missing values: linear interpolation in time.
    for c in cols:
        miss = m[c].isna()
        if miss.any():
            filled = m[c].interpolate(limit_direction="both")
            log.add(m[miss].assign(n=filled[miss].round(2)), file=f, issue_type="missing_value",
                    category="gap", field_name=c, corrected="n", action="imputed",
                    rule="linear interpolation between neighbouring months", row_ref="Date")
            m[c] = filled

    full = pd.period_range(m["Date"].min(), FORECAST_END, freq="M").strftime("%Y-%m")
    missing_months = sorted(set(full) - set(m["Date"]))
    if missing_months:
        log.add(pd.DataFrame({"Date": missing_months}), file=f, issue_type="missing_month",
                category="gap", field_name="Date", action="flagged",
                rule="every month must be present", row_ref="Date")

    log.profile(f, m, "after")
    return m


# --------------------------------------------------------------------------- events
def clean_events(raw: pd.DataFrame, log: DQLog) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (events, events_monthly). events_monthly has one row per event-month with
    the share of the month that the event covers (useful for holidays such as Ramadan)."""
    f = "events_calendar.csv"
    log.profile(f, raw, "before")
    ev = raw.copy()

    def to_day(v, end=False):
        if pd.isna(v) or str(v).strip() == "":
            return pd.NaT
        s = str(v).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return pd.Timestamp(s)
        p = pd.Period(parse_month(s), freq="M")
        return p.end_time.normalize() if end else p.start_time

    ev["start_day"] = ev["Start_Date"].map(to_day)
    ev["end_day"] = ev["End_Date"].map(lambda v: to_day(v, end=True))
    open_ended = ev["end_day"].isna()
    log.add(ev[open_ended], file=f, issue_type="open_ended_event", category="info",
            field_name="End_Date", action="end set to forecast end",
            rule="blank End_Date = event still in force", row_ref="Event_ID")
    ev.loc[open_ended, "end_day"] = pd.Period(FORECAST_END, freq="M").end_time.normalize()

    # Customer scope is 'Customer | Region'.
    parts = ev["Scope_Value"].str.split("|", expand=True)
    ev["Scope_Customer"] = np.where(ev["Scope_Type"] == "Customer", parts[0].str.strip(), None)
    ev["Scope_Region"] = np.where(ev["Scope_Type"] == "Customer", parts[1].str.strip() if parts.shape[1] > 1 else None,
                                  np.where(ev["Scope_Type"] == "Region", ev["Scope_Value"], None))
    ev["Scope_Region"] = map_alias(pd.Series(ev["Scope_Region"]), REGION_ALIASES).fillna(pd.Series(ev["Scope_Region"]))
    pct = ev["Description"].str.extract(r"(\d+(?:\.\d+)?)\s*%")[0].astype(float)
    ev["Pct"] = pct

    rows = []
    for _, r in ev.iterrows():
        for p in pd.period_range(r["start_day"], r["end_day"], freq="M"):
            a = max(r["start_day"], p.start_time)
            b = min(r["end_day"], p.end_time.normalize())
            share = ((b - a).days + 1) / p.days_in_month
            rows.append({"Date": p.strftime("%Y-%m"), "Event_ID": r["Event_ID"],
                         "Event_Type": r["Event_Type"], "Scope_Type": r["Scope_Type"],
                         "Scope_Value": r["Scope_Value"], "Scope_Customer": r["Scope_Customer"],
                         "Scope_Region": r["Scope_Region"], "Month_Share": round(share, 3),
                         "Pct": r["Pct"], "Description": r["Description"]})
    monthly = pd.DataFrame(rows)
    log.profile(f, ev, "after")
    return ev, monthly


# --------------------------------------------------------------------------- stockouts
def clean_stockouts(raw: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    f = "inventory_stockouts.csv"
    log.profile(f, raw, "before")
    so = raw.copy()
    so["Date"] = so["Date"].map(parse_month)
    so["SKU_ID"] = so["SKU_ID"].map(normalise_sku)
    so["Region"] = map_alias(so["Region"], REGION_ALIASES).fillna(so["Region"])
    num = ["Requested_Units", "Carried_In_Units", "Shipped_Units", "Backordered_Units",
           "Lost_Units", "Fill_Rate_Pct", "Stockout_Days"]
    so[num] = so[num].apply(pd.to_numeric, errors="coerce")

    dups = so[so.duplicated(["Date", "SKU_ID", "Region"], keep="last")]
    log.add(dups, file=f, issue_type="duplicate_key", category="error", field_name="Date-SKU-Region",
            action="dropped", rule="one row per Date-SKU-Region (keep last)")
    so = so.drop_duplicates(["Date", "SKU_ID", "Region"], keep="last").reset_index(drop=True)

    avail = so["Requested_Units"] + so["Carried_In_Units"]
    lost_calc = avail - so["Shipped_Units"] - so["Backordered_Units"]
    bad = so[(lost_calc - so["Lost_Units"]).abs() > 1]
    log.add(bad.assign(o=bad["Lost_Units"], n=lost_calc[bad.index]), file=f,
            issue_type="lost_units_identity", category="error", field_name="Lost_Units",
            original="o", corrected="n", action="flagged",
            rule="Lost = Requested + Carried_In - Shipped - Backordered")

    fr_calc = np.where(avail > 0, 100 * so["Shipped_Units"] / avail.replace(0, np.nan), np.nan)
    so["Fill_Rate_Calc"] = np.round(fr_calc, 1)
    bad = so[(so["Fill_Rate_Calc"] - so["Fill_Rate_Pct"]).abs() > 10.0]
    log.add(bad, file=f, issue_type="fill_rate_mismatch", category="error", field_name="Fill_Rate_Pct",
            original="Fill_Rate_Pct", corrected="Fill_Rate_Calc", action="recomputed",
            rule="Fill = Shipped / (Requested + Carried_In); >10 pt gap flagged (small gaps are rounding)")
    zero = so[avail.eq(0)]
    log.add(zero, file=f, issue_type="empty_stockout_record", category="error",
            field_name="Requested_Units", action="excluded from demand recovery",
            rule="no demand and no carry-in: record carries no information")
    so["Valid"] = avail.gt(0)

    # Backorder chain: Carried_In this month should equal Backordered last month.
    prev = so[["Date", "SKU_ID", "Region", "Backordered_Units"]].copy()
    prev["Date"] = (pd.PeriodIndex(prev["Date"], freq="M") + 1).strftime("%Y-%m")
    chk = so.merge(prev.rename(columns={"Backordered_Units": "Prev_Back"}),
                   on=["Date", "SKU_ID", "Region"], how="left")
    bad = chk[chk["Prev_Back"].notna() & (chk["Prev_Back"] != chk["Carried_In_Units"])]
    log.add(bad, file=f, issue_type="backorder_chain_break", category="error",
            field_name="Carried_In_Units", original="Carried_In_Units", corrected="Prev_Back",
            action="flagged", rule="Carried_In(m) = Backordered(m-1)")

    log.profile(f, so, "after")
    return so
