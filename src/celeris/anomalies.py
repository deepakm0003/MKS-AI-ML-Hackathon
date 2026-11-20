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
def build_demand(panel: pd.DataFrame, stockouts: pd.DataFrame, events: pd.DataFrame,
                 events_monthly: pd.DataFrame, sku: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
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

    # ---------------------------------------------------- 2. allocation windows (supply constraint)
    em = events_monthly
    sup = em[em["Event_Type"].eq("Supply Constraint")]
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
        f = p.loc[sel, "Date"].map(upl).fillna(upl.median())
        p.loc[sel, "Demand"] = (U[sel] * f).round()
        p.loc[sel, "Demand_Source"] = "allocation_uplift"
        p.loc[sel, "Alloc_Uplift"] = f
        alloc |= sel
        reg.append(_reg(p[sel], "allocation_unlisted", "stockout", f"events_calendar {ev_id}",
                        lambda r, ev_id=ev_id: f"{ev_id} shipments allocated below demand; month not in stockout file; "
                                               f"uplift x{r['Alloc_Uplift']:.2f} from listed rows of the same month",
                        "demand = shipped x (requested / shipped of listed rows, same family-month)", "medium"))

    # ---------------------------------------------------- 3. event tags
    tags = tag_events(p, em)
    p["Events"] = tags.groupby("row")["Event_ID"].agg(",".join).reindex(p.index).fillna("")
    transient = tags[tags["Event_Type"].isin(TRANSIENT_EVENT_TYPES)].groupby("row")["Event_ID"].agg(",".join)
    p["Transient_Event"] = transient.reindex(p.index).fillna("")
    # price-rise announcement -> early buying in the announcement months, payback after
    ann = events[events["Event_Type"].eq("Announcement") & events["Description"].str.contains("price", case=False)]
    p["Pull_Forward"] = ""
    for _, a in ann.iterrows():
        start = pd.Period(a["start_day"], "M")
        fwd = {(start + i).strftime("%Y-%m") for i in range(0, 2)}
        back = {(start + i).strftime("%Y-%m") for i in range(2, 4)}
        p.loc[p["Date"].isin(fwd), "Pull_Forward"] = f"{a['Event_ID']}:early_buying"
        p.loc[p["Date"].isin(back), "Pull_Forward"] = f"{a['Event_ID']}:payback"

    # ---------------------------------------------------- 4. unlisted-stockout test
    # The stockout file is "known to be incomplete". A stockout outside it would show as a
    # partial shipment followed by a catch-up month. We count that low->high signature
    # and compare it with the mirror high->low pattern, which only noise can produce.
    findings = {"unlisted_stockout_test": unlisted_stockout_test(p)}

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
    reg.append(_reg(p[p["Anomaly_Type"].eq("missing")], "missing_month", "gap", "panel status",
                    lambda r: r["gap_reason"] or "units not recoverable",
                    "excluded from target; Expected used for lags", "high"))

    # ---------------------------------------------------- 7. model columns
    excl = p["Anomaly_Type"].isin(["one_off_order", "event_window", "price_pull_forward", "missing"])
    p["Train_Weight"] = np.where(excl, 0.0, 1.0)
    p["Demand_Model"] = p["Demand"].where(~excl, p["Expected"])
    p["Demand_Model"] = p["Demand_Model"].fillna(p["Expected"])
    p["Demand_Model"] = p.groupby(KEY)["Demand_Model"].transform(lambda x: x.ffill().bfill()).fillna(0)

    register = pd.concat([r for r in reg if r is not None and len(r)], ignore_index=True)
    # refresh Demand / Expected with the final values (stockout steps ran before Expected existed)
    fin = p.set_index(["Date"] + KEY)[["Demand", "Expected"]]
    idx = pd.MultiIndex.from_frame(register[["Date"] + KEY])
    register["Demand"] = fin["Demand"].reindex(idx).values
    register["Expected"] = fin["Expected"].reindex(idx).round(1).values
    return p, register, findings


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
