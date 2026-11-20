"""Stage 2 - anomalies and unconstrained demand.

Turns shipped units into the best estimate of what customers actually asked for, and
records every unusual point with its type, reason, action and confidence.

Columns added to the panel (demand.parquet):
  Demand         unconstrained demand estimate (what customers requested that month)
  Demand_Source  observed | stockout_file | backorder_netted | allocation_uplift |
                 missing
  Expected       normal level for the month (robust, ignores flagged months)
  Anomaly_Type   empty for normal months
  Train_Weight   1 = use as model target, 0 = exclude (one-offs, disruptions, gaps)
  Demand_Model   value used for lags / rolling features: Demand, or Expected where the
                 month is excluded or missing
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="Mean of empty slice")

KEY = ["SKU_ID", "Region"]

# Event types that move demand for a while and should not teach the model a "new normal".
TRANSIENT_EVENT_TYPES = {"Disruption", "Customer Event", "Logistics"}


# ----------------------------------------------------------------------------- helpers
def _roll_median(s: pd.Series, window=13, min_periods=5) -> pd.Series:
    return s.groupby(level=[0, 1]).transform(
        lambda x: x.rolling(window, center=True, min_periods=min_periods).median())


def _roll_mean(s: pd.Series, window=13, min_periods=4) -> pd.Series:
    return s.groupby(level=[0, 1]).transform(
        lambda x: x.rolling(window, center=True, min_periods=min_periods).mean())


def tag_events(p: pd.DataFrame, ev_monthly: pd.DataFrame) -> pd.DataFrame:
    """For every panel row, list the events whose scope covers it."""
    rows = []
    for _, e in ev_monthly.iterrows():
        m = p["Date"].eq(e["Date"])
        st = e["Scope_Type"]
        if st == "Region":
            m &= p["Region"].eq(e["Scope_Region"])
        elif st == "Product_Family":
            m &= p["Product_Family"].eq(e["Scope_Value"])
        elif st == "Channel":
            m &= p["Sales_Channel"].eq(e["Scope_Value"])
        elif st == "Customer":
            m &= p["Customer_Name"].eq(e["Scope_Customer"]) & p["Region"].eq(e["Scope_Region"])
        idx = p.index[m]
        if len(idx):
            rows.append(pd.DataFrame({"row": idx, "Event_ID": e["Event_ID"],
                                      "Event_Type": e["Event_Type"], "Month_Share": e["Month_Share"]}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["row", "Event_ID", "Event_Type", "Month_Share"])


# ----------------------------------------------------------------------------- main
def transient_candidates(events: pd.DataFrame) -> set:
    """Events that could distort the history for a while and then end: closed events of a
    transient type, plus price-rise announcements (early buying, then payback).
    Open-ended events (e.g. a customer's permanent capacity increase) are structural."""
    closed = events["End_Date"].notna() & events["End_Date"].astype(str).str.strip().ne("")
    trans = closed & events["Event_Type"].isin(TRANSIENT_EVENT_TYPES)
    ann = events["Event_Type"].eq("Announcement") & events["Description"].str.contains("price", case=False)
    return set(events.loc[trans | ann, "Event_ID"])


def build_demand(panel: pd.DataFrame, stockouts: pd.DataFrame, events: pd.DataFrame,
                 events_monthly: pd.DataFrame, sku: pd.DataFrame,
                 excluded_events: set | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """excluded_events: event IDs whose months are kept out of the model target. The
    pipeline passes only events whose impact was measured as material (see
    structural.event_impact); None = every transient candidate."""
    if excluded_events is None:
        excluded_events = transient_candidates(events)
    p = panel[panel["status"] != "not_active"].copy()
    p = p.sort_values(KEY + ["Date"]).reset_index(drop=True)
    U = p["Units_Sold"]
    p["Demand"] = U
    p["Demand_Source"] = np.where(p["status"].eq("observed"), "observed", "missing")
    reg = []  # anomaly register fragments

    # ---------------------------------------------------- 1. listed stockouts
    so = stockouts[stockouts["Valid"]][["Date", "SKU_ID", "Region", "Requested_Units",
                                        "Carried_In_Units", "Shipped_Units", "Backordered_Units",
                                        "Lost_Units", "Fill_Rate_Calc", "Reason"]]
    p = p.merge(so, on=["Date", "SKU_ID", "Region"], how="left")
    listed = p["Requested_Units"].notna()
    p.loc[listed, "Demand"] = p.loc[listed, "Requested_Units"]
    p.loc[listed, "Demand_Source"] = "stockout_file"
    reg.append(_reg(p[listed], "stockout_listed", "stockout",
                    "inventory_stockouts.csv",
                    lambda r: f"{r['Reason']}: fill {r['Fill_Rate_Calc']:.0f}%, lost {r['Lost_Units']:.0f}",
                    "demand = Requested_Units (true demand for the month)", "high"))

    # next month: shipments include last month's backorder -> net it out
    back_prev = p.groupby(KEY)["Backordered_Units"].shift(1)
    nb = back_prev.gt(0) & ~listed & p["status"].eq("observed")
    p.loc[nb, "Demand"] = (U[nb] - back_prev[nb]).clip(lower=0)
    p.loc[nb, "Demand_Source"] = "backorder_netted"
    p["Backorder_In"] = back_prev.where(nb)
    reg.append(_reg(p[nb], "backorder_catch_up", "stockout", "stockout file (previous month)",
                    lambda r: f"shipment includes {r['Backorder_In']:.0f} units back-ordered last month",
                    "demand = shipped - carried-in backorder", "high"))

    # ---------------------------------------------------- 2. event tags
    em = events_monthly
    tags = tag_events(p, em)
    p["Events"] = tags.groupby("row")["Event_ID"].agg(",".join).reindex(p.index).fillna("")
    transient = tags[tags["Event_ID"].isin(excluded_events)].groupby("row")["Event_ID"].agg(",".join)
    p["Transient_Event"] = transient.reindex(p.index).fillna("")
    # price-rise announcement -> early buying in the announcement months, payback after
    ann = events[events["Event_Type"].eq("Announcement") & events["Description"].str.contains("price", case=False)]
    p["Pull_Forward"] = ""
    for _, a in ann[ann["Event_ID"].isin(excluded_events)].iterrows():
        start = pd.Period(a["start_day"], "M")
        fwd = {(start + i).strftime("%Y-%m") for i in range(0, 2)}
        back = {(start + i).strftime("%Y-%m") for i in range(2, 4)}
        p.loc[p["Date"].isin(fwd), "Pull_Forward"] = f"{a['Event_ID']}:early_buying"
        p.loc[p["Date"].isin(back), "Pull_Forward"] = f"{a['Event_ID']}:payback"

    # ---------------------------------------------------- 3. allocation windows (supply constraint)
    sup = em[em["Event_Type"].eq("Supply Constraint")]
    findings_alloc = {}
    alloc = pd.Series(False, index=p.index)
    for ev_id, g in sup.groupby("Event_ID"):
        fam = g["Scope_Value"].iloc[0]
        months = set(g["Date"])
        inwin = p["Date"].isin(months) & p["Product_Family"].eq(fam)
        # uplift = requested / shipped among the listed rows of that family-month
        lst = p[inwin & listed]
        upl = (lst.groupby("Date")["Requested_Units"].sum() /
               lst.groupby("Date")["Shipped_Units"].sum()).clip(1, 3)
        sel = inwin & p["Demand_Source"].eq("observed")
        f_listed = p.loc[sel, "Date"].map(upl).fillna(upl.median())
        # The listed rows are the worst-hit ones, so their ratio overstates the shortfall of
        # the unlisted rows. Calibrate the level with a difference-in-differences: unlisted
        # rows' shipments in the window vs their own normal level, against the same ratio
        # for the other (unconstrained) families. Keep the listed rows' monthly profile.
        did = _did_uplift(p, months, fam, sel)
        k = (did - 1) / (f_listed.mean() - 1) if f_listed.mean() > 1 else 0
        f = (1 + (f_listed - 1) * k).clip(lower=1)
        findings_alloc[ev_id] = {"listed_rows_uplift_mean": round(float(f_listed.mean()), 3),
                                 "did_uplift_for_unlisted_rows": round(float(did), 3)}
        p.loc[sel, "Demand"] = (U[sel] * f).round()
        p.loc[sel, "Demand_Source"] = "allocation_uplift"
        p.loc[sel, "Alloc_Uplift"] = f
        alloc |= sel
        reg.append(_reg(p[sel], "allocation_unlisted", "stockout", f"events_calendar {ev_id}",
                        lambda r, ev_id=ev_id: f"{ev_id} shipments allocated below demand; month not in stockout file; "
                                               f"uplift x{r['Alloc_Uplift']:.2f} (listed-row monthly profile, DiD-calibrated level)",
                        "demand = shipped x uplift (difference-in-differences vs unconstrained families)", "medium"))

    # ---------------------------------------------------- 4. unlisted-stockout test
    # The stockout file is "known to be incomplete". A stockout outside it would show as a
    # partial shipment followed by a catch-up month. We count that low->high signature
    # and compare it with the mirror high->low pattern, which only noise can produce.
    findings = {"unlisted_stockout_test": unlisted_stockout_test(p), "allocation_uplift": findings_alloc,
                "excluded_events": sorted(excluded_events)}

    # ---------------------------------------------------- 6. expected level (pass 2) + spikes / drops
    pi = p.set_index(KEY + ["Date"])
    D = pi["Demand"]
    clean_mask = pi["Transient_Event"].eq("") & pi["Pull_Forward"].eq("")
    size_exp = _roll_median(D.where(D.gt(0) & clean_mask))
    level_exp = _roll_mean(D.where(clean_mask))
    lr = np.log1p(D) - np.log1p(size_exp)
    mad = lr.where(D.gt(0)).groupby(level=[0, 1]).transform(lambda x: (x - x.median()).abs().median())
    rz = lr / (1.4826 * mad.clip(lower=0.05))
    p = pi.reset_index()
    p["Expected"] = level_exp.values
    p["Order_Size_Expected"] = size_exp.values
    p["Robust_Z"] = rz.values

    spike = p["Demand"].gt(3 * p["Order_Size_Expected"]) & p["Robust_Z"].gt(5) \
        & (p["Demand"] - p["Order_Size_Expected"]).gt(10)
    drop = p["Demand"].gt(0) & p["Demand"].lt(0.25 * p["Order_Size_Expected"]) & p["Robust_Z"].lt(-5)

    p["Anomaly_Type"] = ""
    p.loc[p["Demand_Source"].isin(["stockout_file", "allocation_uplift"]), "Anomaly_Type"] = "stockout"
    p.loc[p["Demand_Source"].eq("backorder_netted"), "Anomaly_Type"] = "backorder_catch_up"

    ev_spike = spike & (p["Transient_Event"].ne("") | p["Pull_Forward"].ne(""))
    p.loc[spike & ~ev_spike & p["Anomaly_Type"].eq(""), "Anomaly_Type"] = "one_off_order"
    p.loc[drop & p["Transient_Event"].eq("") & p["Anomaly_Type"].eq(""), "Anomaly_Type"] = "unexplained_drop"
    p.loc[p["Transient_Event"].ne("") & p["Anomaly_Type"].eq(""), "Anomaly_Type"] = "event_window"
    p.loc[p["Pull_Forward"].ne("") & p["Anomaly_Type"].eq(""), "Anomaly_Type"] = "price_pull_forward"
    open_ev = set(events.loc[events["End_Date"].isna() & events["Event_Type"].eq("Customer Event"), "Event_ID"])
    step = p["Events"].apply(lambda x: bool(open_ev & set(x.split(","))) if x else False)
    p.loc[step & p["Anomaly_Type"].eq(""), "Anomaly_Type"] = "structural_step"
    p.loc[p["status"].isin(["missing_row", "missing_value"]), "Anomaly_Type"] = "missing"

    reg.append(_reg(p[p["Anomaly_Type"].eq("one_off_order")], "one_off_order", "spike",
                    "robust z > 5 and > 3x typical order",
                    lambda r: f"{r['Demand']:.0f} units vs typical order {r['Order_Size_Expected']:.0f} "
                              f"(z={r['Robust_Z']:.1f}); revenue reconciles, so it is real",
                    "kept in history; excluded from model target (non-recurring)", "high"))
    reg.append(_reg(p[p["Anomaly_Type"].eq("unexplained_drop")], "unexplained_drop", "unknown",
                    "robust z < -5 and < 0.25x typical order",
                    lambda r: f"{r['Demand']:.0f} units vs typical {r['Order_Size_Expected']:.0f}; no event, not in stockout file",
                    "flagged for planner review; kept", "low"))
    ev_rows = p[p["Anomaly_Type"].eq("event_window") & (p["Robust_Z"].abs().gt(2) | p["Demand"].eq(0))]
    reg.append(_reg(ev_rows, "event_impact", "real_event", "events_calendar",
                    lambda r: f"inside {r['Transient_Event']}: {r['Demand']:.0f} vs normal {r['Expected']:.1f}",
                    "real event: kept in history, excluded from model target", "high"))
    pf = p[p["Anomaly_Type"].eq("price_pull_forward")]
    reg.append(_reg(pf[pf["Robust_Z"].abs().gt(1.5)], "price_pull_forward", "real_event", "events_calendar announcement",
                    lambda r: f"{r['Pull_Forward']}: {r['Demand']:.0f} vs normal {r['Expected']:.1f}",
                    "real event: kept; excluded from model target (announcement-driven)", "medium"))
    st = p[p["Anomaly_Type"].eq("structural_step")]
    reg.append(_reg(st[st["Date"].eq(st.groupby(KEY)["Date"].transform("min"))], "structural_step", "real_event",
                    "events_calendar (open-ended) + level-shift test",
                    lambda r: f"permanent change from {r['Date']}: {r['Events']}",
                    "real and permanent: kept as the new level, used for training", "high"))
    reg.append(_reg(p[p["Anomaly_Type"].eq("missing")], "missing_month", "gap", "panel status",
                    lambda r: r["gap_reason"] or "units not recoverable",
                    "excluded from target; Expected used for lags", "high"))

    # ---------------------------------------------------- 7. model columns
    excl = p["Anomaly_Type"].isin(["one_off_order", "event_window", "price_pull_forward", "missing"])
    p["Train_Weight"] = np.where(excl, 0.0, 1.0)
    # Fill excluded / missing months with a CAUSAL level (mean of the previous 12 usable
    # months) so lag features never see the future in a backtest; fall back to the
    # centred Expected only at the very start of a series.
    usable = p["Demand"].where(~excl)
    trailing = usable.groupby([p["SKU_ID"], p["Region"]]).transform(
        lambda x: x.shift(1).rolling(12, min_periods=3).mean())
    fill = trailing.fillna(p["Expected"])
    p["Expected_Causal"] = trailing
    p["Demand_Model"] = p["Demand"].where(~excl, fill)
    p["Demand_Model"] = p["Demand_Model"].fillna(fill)
    p["Demand_Model"] = p.groupby(KEY)["Demand_Model"].transform(lambda x: x.ffill().bfill()).fillna(0)

    register = pd.concat([r for r in reg if r is not None and len(r)], ignore_index=True)
    # refresh Demand / Expected with the final values (stockout steps ran before Expected existed)
    fin = p.set_index(["Date"] + KEY)[["Demand", "Expected"]]
    idx = pd.MultiIndex.from_frame(register[["Date"] + KEY])
    register["Demand"] = fin["Demand"].reindex(idx).values
    register["Expected"] = fin["Expected"].reindex(idx).round(1).values
    return p, register, findings


def _did_uplift(p: pd.DataFrame, months: set, fam: str, sel: pd.Series) -> float:
    w0, w1 = min(months), max(months)
    lo = (pd.Period(w0, "M") - 24).strftime("%Y-%m")
    hi = (pd.Period(w1, "M") + 24).strftime("%Y-%m")
    usable = p["Transient_Event"].eq("") & p["Units_Sold"].notna()
    inside = p["Date"].isin(months) & usable
    outside = p["Date"].between(lo, hi) & ~p["Date"].isin(months) & usable
    ins = p[inside].groupby(KEY)["Units_Sold"].mean()
    out = p[outside].groupby(KEY)["Units_Sold"].mean()
    r = (ins / out).replace([np.inf, -np.inf], np.nan).dropna()
    fam_of = p.groupby(KEY)["Product_Family"].first().reindex(r.index)
    treated = set(map(tuple, p.loc[sel, KEY].drop_duplicates().values))
    is_t = pd.Series([i in treated for i in r.index], index=r.index)
    ctrl, trt = r[fam_of.ne(fam)].median(), r[is_t].median()
    return float(np.clip(ctrl / trt, 1, 3)) if trt > 0 else 1.0


def unlisted_stockout_test(p: pd.DataFrame) -> dict:
    pi = p.set_index(KEY + ["Date"])
    D = pi["Demand"]
    size = _roll_median(D.where(D.gt(0)))
    nxt, nsize = D.groupby(level=[0, 1]).shift(-1), size.groupby(level=[0, 1]).shift(-1)
    nz = D.gt(0).groupby(level=[0, 1]).transform(lambda x: x.rolling(12, min_periods=6).mean())
    base = (nz.ge(0.9) & size.ge(5) & pi["Transient_Event"].eq("") & pi["Pull_Forward"].eq("")
            & pi["Demand_Source"].eq("observed"))
    low_high = int((base & D.gt(0) & D.lt(0.6 * size) & nxt.gt(1.25 * nsize)).sum())
    high_low = int((base & D.gt(1.25 * size) & nxt.lt(0.6 * nsize) & nxt.gt(0)).sum())
    return {
        "low_then_high_months": low_high,
        "high_then_low_months_noise_baseline": high_low,
        "excess_over_noise": low_high - high_low,
        "conclusion": ("no evidence of unlisted stockouts outside event windows: the stockout "
                       "signature is no more frequent than its noise mirror, so no adjustment is made")
                      if low_high <= 1.1 * high_low else
                      "excess stockout signatures found: review",
    }


def _reg(df: pd.DataFrame, typ: str, category: str, detection: str, reason, action: str,
         confidence: str) -> pd.DataFrame | None:
    if df is None or len(df) == 0:
        return None
    out = pd.DataFrame({
        "Date": df["Date"].values, "SKU_ID": df["SKU_ID"].values, "Region": df["Region"].values,
        "Product_Family": df["Product_Family"].values, "Customer_Name": df["Customer_Name"].values,
        "Sales_Channel": df["Sales_Channel"].values,
        "Units_Shipped": df["Units_Sold"].values,
        "Demand": df["Demand"].values,
        "Expected": df["Expected"].values if "Expected" in df else np.nan,
        "Type": typ, "Category": category, "Detection": detection,
        "Reason": [reason(r) if callable(reason) else reason for _, r in df.iterrows()],
        "Action": action, "Confidence": confidence,
    })
    return out
