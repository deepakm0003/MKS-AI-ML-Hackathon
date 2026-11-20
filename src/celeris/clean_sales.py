"""Cleaning for train.csv: one clean row per Date-SKU-Region.

Order of operations matters and is deliberate:
  1. de-duplicate reloaded Record_IDs (latest Load_Timestamp wins)
  2. dates (Date is authoritative), keys (SKU, region, channel, customer)
  3. fill product attributes from the master
  4. infer missing regions from customer + SKU coverage
  5. reconcile units x price = revenue, fixing unit / price / sign errors
  6. resolve any remaining Date-SKU-Region duplicates
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (CHANNEL_ALIASES, EUR_PER_USD, HISTORY_END, HISTORY_START, PRICE_TOL, RECON_TOL,
                     REGION_ALIASES)
from .dq import DQLog
from .parsing import build_name_matcher, map_alias, normalise_sku, parse_month, parse_number

F = "train.csv"
KEY = ["Date", "SKU_ID", "Region"]


def _close(a, b, rel=RECON_TOL, abs_=0.05):
    return (a - b).abs() <= np.maximum(abs_, rel * b.abs())


def _nearest_factor(ratio: pd.Series, factors=(10, 100, 0.1, 0.01), tol=0.03) -> pd.Series:
    out = pd.Series(np.nan, index=ratio.index)
    for f in factors:
        out[(ratio / f - 1).abs() <= tol] = f
    return out


def clean_sales(raw: pd.DataFrame, sku: pd.DataFrame, customers: list[str],
                events: pd.DataFrame, events_monthly: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    log.profile(F, raw, "before")
    df = raw.copy()
    df["Load_Timestamp"] = pd.to_datetime(df["Load_Timestamp"], errors="coerce")

    # ---------------------------------------------------------------- 1. reloaded rows
    exact = df.duplicated(keep=False) & df.duplicated()
    log.add(df[exact], file=F, issue_type="exact_duplicate_row", category="error",
            field_name="*", action="dropped", rule="identical row loaded twice")
    df = df[~exact]
    df = df.sort_values("Load_Timestamp")
    reload = df.duplicated("Record_ID", keep="last")
    log.add(df[reload], file=F, issue_type="reloaded_record_id", category="error",
            field_name="Record_ID", action="dropped (older load)",
            rule="repeated Record_ID: latest Load_Timestamp is correct")
    df = df[~reload].copy()

    # ---------------------------------------------------------------- 2a. dates
    df["Date_raw"] = df["Date"]
    df["Date"] = df["Date_raw"].map(parse_month)
    std = df["Date"].notna() & df["Date_raw"].str.fullmatch(r"\d{4}-\d{2}")
    log.add(df[~std & df["Date"].notna()].assign(n=df["Date"]), file=F,
            issue_type="non_standard_date_format", category="error", field_name="Date",
            original="Date_raw", corrected="n", action="standardised", rule="parse to YYYY-MM")

    yr = pd.to_numeric(df["Year"], errors="coerce")
    bad_year = df["Date"].notna() & ~df["Date"].str[:4].between(HISTORY_START[:4], HISTORY_END[:4])
    fixed = yr[bad_year].astype(int).astype(str) + "-" + df.loc[bad_year, "Date"].str[5:]
    log.add(df[bad_year].assign(n=fixed), file=F, issue_type="date_year_typo", category="error",
            field_name="Date", original="Date_raw", corrected="n", action="corrected",
            rule="year outside history (e.g. 2062): take year from Year column (digit swap)")
    df.loc[bad_year, "Date"] = fixed
    unparsed = df["Date"].isna()
    log.add(df[unparsed], file=F, issue_type="unparseable_date", category="error", field_name="Date",
            original="Date_raw", action="dropped", rule="Date must be parseable")
    df = df[~unparsed].copy()

    ym = df["Year"].astype(str) + "-" + pd.to_numeric(df["Month"], errors="coerce").fillna(0).astype(int).astype(str).str.zfill(2)
    mism = ym != df["Date"]
    log.add(df[mism].assign(o=ym[mism]), file=F, issue_type="year_month_disagree_with_date",
            category="error", field_name="Year/Month", original="o", corrected="Date",
            action="rebuilt from Date",
            rule="Date is authoritative (mismatched Month equals the load month)")
    df["Year"] = df["Date"].str[:4].astype(int)
    df["Month"] = df["Date"].str[5:].astype(int)

    # ---------------------------------------------------------------- 2b. keys and labels
    df["SKU_raw"] = df["SKU_ID"]
    df["SKU_ID"] = df["SKU_raw"].map(normalise_sku)
    ch = df["SKU_ID"].notna() & (df["SKU_ID"] != df["SKU_raw"])
    log.add(df[ch], file=F, issue_type="sku_id_format", category="error", field_name="SKU_ID",
            original="SKU_raw", corrected="SKU_ID", action="standardised",
            rule="[FAMILY]-[NNN], upper case, zero padded")
    unknown = ~df["SKU_ID"].isin(sku["SKU_ID"])
    log.add(df[unknown], file=F, issue_type="unknown_sku", category="reference", field_name="SKU_ID",
            original="SKU_raw", action="dropped", rule="SKU must exist in sku_master")
    df = df[~unknown].copy()

    for col, aliases, itype in [("Region", REGION_ALIASES, "region_label"),
                                ("Sales_Channel", CHANNEL_ALIASES, "channel_label")]:
        raw_col = df[col].copy()
        df[col] = map_alias(raw_col, aliases)
        ch = raw_col.notna() & (df[col].astype(object) != raw_col.astype(object))
        log.add(df[ch].assign(o=raw_col[ch]), file=F, issue_type=itype, category="error",
                field_name=col, original="o", corrected=col, action="standardised",
                rule="map spelling variant to canonical label")
        bad = raw_col.notna() & df[col].isna()
        log.add(df[bad].assign(o=raw_col[bad]), file=F, issue_type=f"unknown_{itype}",
                category="error", field_name=col, original="o", action="set missing",
                rule="no canonical match")

    match = build_name_matcher(customers)
    raw_c = df["Customer_Name"].copy()
    df["Customer_Name"] = raw_c.map(match)
    ch = df["Customer_Name"].notna() & (df["Customer_Name"] != raw_c)
    log.add(df[ch].assign(o=raw_c[ch]), file=F, issue_type="customer_name_variant", category="error",
            field_name="Customer_Name", original="o", corrected="Customer_Name",
            action="standardised",
            rule="fuzzy match (case, spacing, 'Inc.', 1-char typos) to the 12 customers in test.csv")

    # ---------------------------------------------------------------- 3. product attributes
    m = sku.set_index("SKU_ID")
    for col in ["Product_Family", "Business_Unit", "SKU_Description"]:
        ref = df["SKU_ID"].map(m[col])
        miss = df[col].isna()
        log.add(df[miss].assign(n=ref[miss]), file=F, issue_type=f"missing_{col.lower()}",
                category="gap", field_name=col, corrected="n", action="filled from sku_master",
                rule="attribute is fixed per SKU")
        conf = df[col].notna() & (df[col] != ref)
        log.add(df[conf].assign(n=ref[conf]), file=F, issue_type=f"{col.lower()}_conflicts_master",
                category="reference", field_name=col, original=col, corrected="n",
                action="set to cleaned master", rule="attribute is fixed per SKU")
        df[col] = ref

    # ---------------------------------------------------------------- 4. missing regions
    df = _infer_regions(df, log)

    # ---------------------------------------------------------------- 5. units / price / revenue
    df = _reconcile_money(df, events, log)

    # ---------------------------------------------------------------- 6. key duplicates
    df = df.sort_values("Load_Timestamp")
    dup = df.duplicated(KEY, keep="last")
    log.add(df[dup], file=F, issue_type="duplicate_date_sku_region", category="error",
            field_name="Date-SKU-Region", action="dropped (older load)",
            rule="one row per Date-SKU-Region; latest load wins")
    df = df[~dup]
    df = fix_uom_blocks(df, events_monthly, log)

    # ---------------------------------------------------------------- lifecycle conflicts
    launch = df["SKU_ID"].map(m["Launch_Date"])
    eol = df["SKU_ID"].map(m["EOL_Date"])
    pre = (df["Date"] < launch) & df["Units_Sold"].gt(0)
    log.add(df[pre].assign(n=launch[pre]), file=F, issue_type="sale_before_launch",
            category="reference", field_name="Date", corrected="n", action="flagged",
            rule="master Launch_Date later than first sale: master likely wrong, sale kept")
    post = eol.notna() & (df["Date"] > eol) & df["Units_Sold"].gt(0)
    log.add(df[post].assign(n=eol[post]), file=F, issue_type="sale_after_eol",
            category="reference", field_name="Date", corrected="n", action="flagged",
            rule="no sales after EOL_Date")

    keep = ["Record_ID", "Date", "Year", "Month", "Product_Family", "Business_Unit", "SKU_ID",
            "SKU_Description", "Customer_Name", "Sales_Channel", "Region", "Units_Sold",
            "Unit_Price_USD", "Revenue_USD", "Load_Timestamp", "Units_Fix", "Price_Fix",
            "Region_Inferred", "Units_Missing"]
    out = df[keep].sort_values(KEY).reset_index(drop=True)
    log.profile(F, out, "after")
    return out


def _infer_regions(df: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    """A row with no Region is assigned to the one region where this SKU is sold to
    this customer (and channel) and that has no row for this month."""
    df["Region_Inferred"] = False
    miss = df["Region"].isna()
    if not miss.any():
        return df
    known = df[~miss]
    present = known.groupby(["SKU_ID", "Date"])["Region"].agg(set).to_dict()
    by_cust = known.groupby(["SKU_ID", "Customer_Name"])["Region"].agg(set).to_dict()
    by_cust_ch = known.groupby(["SKU_ID", "Customer_Name", "Sales_Channel"])["Region"].agg(set).to_dict()
    taken: dict = {}
    fills, ambiguous = {}, []
    for i, r in df[miss].iterrows():
        free = lambda regs: regs - present.get((r.SKU_ID, r.Date), set()) - taken.get((r.SKU_ID, r.Date), set())
        cand = free(by_cust.get((r.SKU_ID, r.Customer_Name), set()))
        if len(cand) > 1:
            cand = cand & free(by_cust_ch.get((r.SKU_ID, r.Customer_Name, r.Sales_Channel), set()))
        if len(cand) == 1:
            reg = cand.pop()
            fills[i] = reg
            taken.setdefault((r.SKU_ID, r.Date), set()).add(reg)
        else:
            ambiguous.append(i)
    idx = list(fills)
    df.loc[idx, "Region"] = pd.Series(fills)
    df.loc[idx, "Region_Inferred"] = True
    log.add(df.loc[idx], file=F, issue_type="missing_region", category="gap", field_name="Region",
            corrected="Region", action="inferred",
            rule="only region where this SKU+customer(+channel) is sold with no row that month")
    log.add(df.loc[ambiguous], file=F, issue_type="missing_region_unresolved", category="gap",
            field_name="Region", action="dropped", rule="no unique candidate region")
    return df.drop(index=ambiguous)


def surcharge_factor(dates: pd.Series, events: pd.DataFrame) -> pd.Series:
    """Global invoice surcharges from the events calendar (e.g. 6% Jul-Dec 2022)."""
    fac = pd.Series(1.0, index=dates.index)
    sur = events[(events["Event_Type"] == "Price Change") & (events["Scope_Type"] == "Global")
                 & events["Description"].str.contains("surcharge", case=False)]
    for _, e in sur.iterrows():
        s, t = e["start_day"].strftime("%Y-%m"), e["end_day"].strftime("%Y-%m")
        fac[(dates >= s) & (dates <= t)] *= 1 + e["Pct"] / 100
    return fac


def reference_prices(df: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    """Expected price per row: the SKU's list price for the year (modal price outside
    surcharge months) times any surcharge in force that month."""
    p = df["Price_raw"]
    fac = surcharge_factor(df["Date"], events)
    base = (p / fac).round(2)
    frame = pd.DataFrame({"SKU_ID": df["SKU_ID"], "Year": df["Year"], "b": base})
    modal = lambda s: s.mode().iloc[0]
    # prefer months without a surcharge; if an SKU only sold in surcharge months that
    # year (e.g. chip-shortage zeros in H1 2022), de-surcharged prices are used instead
    m1 = frame[p.gt(0) & fac.eq(1.0)].groupby(["SKU_ID", "Year"])["b"].agg(modal)
    m2 = frame[p.gt(0)].groupby(["SKU_ID", "Year"])["b"].agg(modal)
    mode = m1.combine_first(m2)
    ref = pd.Series(pd.MultiIndex.from_arrays([df["SKU_ID"], df["Year"]]).map(mode), index=df.index)
    return (ref * fac).round(2)


def _reconcile_money(df: pd.DataFrame, events: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    df["Units_raw"] = df["Units_Sold"]
    df["Price_raw"] = df["Unit_Price_USD"].map(parse_number)
    df["Rev_raw"] = df["Revenue_USD"].map(parse_number)
    U = df["Units_raw"].map(parse_number)
    P = df["Price_raw"]
    R = df["Rev_raw"]
    Pref = reference_prices(df, events)
    df["Units_Fix"] = ""
    df["Price_Fix"] = ""

    # -- price
    ratio = P / Pref
    price_ok = (ratio - 1).abs() <= PRICE_TOL
    zero_ok = P.eq(0) & U.fillna(0).eq(0)          # no order -> price 0 is the ERP convention
    bad_p = ~price_ok & ~zero_ok & Pref.notna()
    fac = _nearest_factor(ratio)
    eur = df["Region"].eq("Europe") & (ratio / EUR_PER_USD - 1).abs().le(PRICE_TOL)
    kind = np.where(P.isna() | P.eq(0), "price_missing_or_zero",
                    np.where(fac.notna(), "price_scale_x" + fac.astype(str).str.replace(".0", "", regex=False),
                             np.where(eur, "price_currency_eur", "price_off_list")))
    for k in pd.unique(kind[bad_p]):
        sel = bad_p & (kind == k)
        log.add(df[sel].assign(n=Pref[sel]), file=F, issue_type=k, category="error",
                field_name="Unit_Price_USD", original="Price_raw", corrected="n", action="corrected",
                rule="price is per SKU, same in all regions, changes 1 Jan (+ calendar surcharges)")
    df.loc[bad_p, "Price_Fix"] = kind[bad_p]

    # -- units: sign errors
    neg = U.lt(0)
    log.add(df[neg].assign(n=U[neg].abs()), file=F, issue_type="negative_units", category="error",
            field_name="Units_Sold", original="Units_raw", corrected="n", action="sign flipped",
            rule="|units| matches the series level and revenue sign also flipped")
    U = U.abs()
    R = R.abs()
    df.loc[neg, "Units_Fix"] = "sign"

    fmt = df["Units_raw"].astype(str).str.contains(",", na=False)
    log.add(df[fmt], file=F, issue_type="units_thousands_separator", category="error",
            field_name="Units_Sold", original="Units_raw", corrected=U[fmt].astype(str).values if fmt.any() else None,
            action="parsed", rule="strip thousands separator")

    # -- units: missing -> recover from revenue
    Pt = Pref.where(Pref.notna(), P)                # best estimate of the true price
    U_from_R = R / Pt
    miss = U.isna()
    rec = miss & R.notna() & Pt.gt(0) & ((U_from_R - U_from_R.round()).abs() < 0.02)
    log.add(df[rec].assign(n=U_from_R[rec].round()), file=F, issue_type="missing_units",
            category="gap", field_name="Units_Sold", original="Units_raw", corrected="n",
            action="recovered from revenue / price", rule="units = revenue / list price")
    U[rec] = U_from_R[rec].round()
    df.loc[rec, "Units_Fix"] = "from_revenue"
    still = U.isna()
    log.add(df[still], file=F, issue_type="missing_units_unrecoverable", category="gap",
            field_name="Units_Sold", original="Units_raw", action="left missing (imputed later)",
            rule="no revenue to recover from")
    df["Units_Missing"] = still

    # -- units: scale errors (units x10 / x100 while revenue is right)
    has = U.notna() & R.notna() & Pt.gt(0) & U.gt(0)
    consistent = has & (_close(U * Pt, R) | _close(U * P, R))
    k = (U / U_from_R).where(has & ~consistent)
    fac_u = _nearest_factor(k, factors=(10, 100))
    sc = fac_u.notna()
    log.add(df[sc].assign(n=U_from_R[sc].round(), f="x" + fac_u[sc].astype(int).astype(str)), file=F,
            issue_type="units_scale_error", category="error", field_name="Units_Sold",
            original="Units_raw", corrected="n", action="corrected from revenue",
            rule="units = revenue / price when recorded units are 10x or 100x the revenue-implied value")
    U[sc] = U_from_R[sc].round()
    df.loc[sc, "Units_Fix"] = "scale_x" + fac_u[sc].astype(int).astype(str)

    # -- revenue
    R_new = (U * Pt).round(2)
    rmiss = df["Rev_raw"].isna() & U.notna()
    log.add(df[rmiss].assign(n=R_new[rmiss]), file=F, issue_type="missing_revenue", category="gap",
            field_name="Revenue_USD", corrected="n", action="recomputed", rule="revenue = units x price")
    rbad = df["Rev_raw"].notna() & U.notna() & ~_close(R_new, R) & ~sc & ~bad_p
    rfac = _nearest_factor(R / R_new, factors=(10, 100, 0.1, 0.01)).where(rbad)
    for name, sel in [("revenue_scale_error", rbad & rfac.notna()), ("revenue_mismatch", rbad & rfac.isna())]:
        log.add(df[sel].assign(n=R_new[sel]), file=F, issue_type=name, category="error",
                field_name="Revenue_USD", original="Rev_raw", corrected="n", action="recomputed",
                rule="revenue = units x price (units match the series level, so revenue is the wrong field)")

    df["Units_Sold"] = U
    df["Unit_Price_USD"] = Pt          # list price, also kept on zero-order rows (useful as a feature)
    df["Revenue_USD"] = R_new.where(U.notna())
    return df


def fix_uom_blocks(df: pd.DataFrame, events_monthly: pd.DataFrame, log: DQLog) -> pd.DataFrame:
    """Units recorded in packs of 10 for a run of months (revenue scaled the same way,
    so the row reconciles and only the level gives it away).

    The error is a whole segment (Region x Channel) for a run of months - in this
    extract India x Aftermarket, 2021-07..2021-12 - so it is detected at segment level:
    a segment-month whose median row sits at 0.05-0.17x of each series' normal level
    (>=10 rows, no disruption / market-entry event) is an entry error, and its rows
    below 0.3x are scaled x10. A real demand shock (strike, COVID) moves one customer
    or a whole region, not one channel at exactly 1/10. Cross-checked against
    inventory_stockouts: Shipped_Units is ~10x the recorded units in these months.
    """
    d = df.copy()
    pos = d["Units_Sold"].where(d["Units_Sold"].gt(0))
    level = pos.groupby([d["SKU_ID"], d["Region"]]).transform("median")
    ratio = d["Units_Sold"] / level
    seg = d.assign(ratio=ratio.where(d["Units_Sold"].gt(0))).groupby(
        ["Region", "Sales_Channel", "Date"])["ratio"].agg(["median", "count"])

    ev = events_monthly[events_monthly["Event_Type"].isin(["Disruption", "Market Entry"])]
    excused = set(zip(ev["Date"], ev["Scope_Region"].fillna("ALL")))
    bad_seg = seg[seg["median"].between(0.05, 0.17) & seg["count"].ge(10)]
    bad_seg = bad_seg[[(dt, r) not in excused and (dt, "ALL") not in excused
                       for r, _, dt in bad_seg.index]]
    in_seg = pd.MultiIndex.from_frame(d[["Region", "Sales_Channel", "Date"]]).isin(bad_seg.index)
    fix = in_seg & ratio.lt(0.3).values
    log.add(d[fix].assign(n=d.loc[fix, "Units_Sold"] * 10), file=F, issue_type="units_uom_block_x0.1",
            category="error", field_name="Units_Sold", original="Units_Sold", corrected="n",
            action="units and revenue x10",
            rule="segment-month (region x channel) at ~1/10 of normal level, no disruption event; "
                 "confirmed by stockout file")
    d.loc[fix, "Units_Sold"] *= 10
    d.loc[fix, "Revenue_USD"] *= 10
    d.loc[fix, "Units_Fix"] = "uom_x10"
    return d
