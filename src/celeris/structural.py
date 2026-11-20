"""Stage 2b - structural analysis (Expert tier).

* event_impact       which calendar events measurably moved demand, and by how much
* series_profile     per SKU-region: ordering cycle, phase, intermittency class (ADI / CV2)
* structural register
    - ordering_cycle_change   a customer moved from e.g. monthly to quarterly ordering
    - customer_switch         the SKU-region's customer changed
    - lost_account            a series stopped without an EOL
    - level_shift             a customer's share of its region stepped up / down
    - master_conflict         master data contradicts the transactions
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HISTORY_END

KEY = ["SKU_ID", "Region"]


# ----------------------------------------------------------------------------- events
def _scope_mask(d: pd.DataFrame, e: pd.Series) -> pd.Series:
    st = e["Scope_Type"]
    if st == "Region":
        return d["Region"].eq(e["Scope_Region"])
    if st == "Product_Family":
        return d["Product_Family"].eq(e["Scope_Value"])
    if st == "Channel":
        return d["Sales_Channel"].eq(e["Scope_Value"])
    if st == "Customer":
        return d["Customer_Name"].eq(e["Scope_Customer"]) & d["Region"].eq(e["Scope_Region"])
    return pd.Series(True, index=d.index)


def event_impact(d: pd.DataFrame, events: pd.DataFrame, events_monthly: pd.DataFrame) -> pd.DataFrame:
    """How much did each event move demand in its scope? The baseline depends on the
    kind of event, so that recurring patterns do not cancel themselves out:

      holiday (recurs every year)   event month vs the average of the month before and after
      long event (> 6 months)       event window vs 12 months before and 12 months after
      other events                  event months vs the same months one year before / after
                                    ("YoY sandwich": cancels seasonality and trend)

    Significance: the same statistic is computed for every month of the scope, and
    the event's value is expressed as a z-score against that spread."""
    rows = []
    for _, e in events.iterrows():
        em = events_monthly[events_monthly["Event_ID"].eq(e["Event_ID"])]
        if e["Event_Type"] == "Holiday":
            # count the months a holiday really covers; a 10-day holiday split over two
            # months counts in the month with the larger share
            em = em[em["Month_Share"] >= min(0.3, em["Month_Share"].max())]
        months = sorted(em["Date"])
        hist = [m for m in months if m <= HISTORY_END]
        base = {"Event_ID": e["Event_ID"], "Event_Type": e["Event_Type"], "Scope": e["Scope_Value"],
                "Start": months[0] if months else "", "End": months[-1] if months else "",
                "Description": e["Description"]}
        if not hist:
            rows.append({**base, "Method": "", "Verdict": "in forecast window"})
            continue
        sel = d[_scope_mask(d, e)]
        method = ("holiday: vs adjacent months" if e["Event_Type"] == "Holiday" else
                  "long event: vs 12m before/after" if len(hist) > 6 else "YoY sandwich")
        for col, name in [("Units_Sold", "Shipped"), ("Demand", "Demand")]:
            s = sel.groupby("Date")[col].sum()
            s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M").strftime("%Y-%m"))
            if method.startswith("holiday"):
                ref = (s.shift(1) + s.shift(-1)) / 2
                lr = np.log(s / ref).replace([np.inf, -np.inf], np.nan)
                act, rf = s.reindex(hist).sum(), ref.reindex(hist).sum()
                noise, n = _robust_std(lr), len(hist)
            elif method.startswith("long"):
                pre = s[s.index < hist[0]].tail(12).mean()
                post = s[s.index > hist[-1]].head(12).mean()
                ref_level = np.nanmean([pre, post])
                act, rf = s.reindex(hist).mean(), ref_level
                roll = np.log(s.rolling(len(hist)).mean() / s.shift(len(hist)).rolling(12).mean())
                noise, n = _robust_std(roll), 1
            else:
                ref = pd.concat([s.shift(12), s.shift(-12)], axis=1).mean(axis=1)
                lr = np.log(s / ref).replace([np.inf, -np.inf], np.nan)
                act, rf = s.reindex(hist).sum(), ref.reindex(hist).sum()
                noise, n = _robust_std(lr), len(hist)
            imp = np.log(act / rf) if rf and rf > 0 and act > 0 else np.nan
            z = imp / (noise / np.sqrt(n)) if noise and noise > 0 and pd.notna(imp) else np.nan
            base[f"{name}_Impact_Pct"] = round(100 * (np.exp(imp) - 1), 1) if pd.notna(imp) else np.nan
            base[f"{name}_Z"] = round(z, 1) if pd.notna(z) else np.nan
        z = base.get("Shipped_Z", np.nan)
        if e["Event_Type"] == "Supply Constraint":
            # what matters is the gap between what shipped and what was asked for
            w = sel[sel["Date"].isin(hist)]
            gap = w["Units_Sold"].sum() / w["Demand"].sum() - 1
            base["Shipped_vs_Demand_Pct"] = round(100 * gap, 1)
            method = "supply: shipped vs recovered demand in window"
            z = -9.9 if gap <= -0.10 else 0.0
        base["Method"] = method
        base["Verdict"] = ("material" if pd.notna(z) and abs(z) >= 3 else
                           "weak" if pd.notna(z) and abs(z) >= 2 else
                           "no data (scope not active)" if pd.isna(z) else "no measurable effect")
        rows.append(base)
    out = pd.DataFrame(rows)
    # Holidays recur: judge them on all years together (pooled z = sum z / sqrt(n)).
    hol = out["Event_Type"].eq("Holiday") & out["Shipped_Z"].notna()
    pooled = out[hol].groupby(["Scope", "Description"])["Shipped_Z"].agg(lambda z: z.sum() / np.sqrt(len(z)))
    mean_imp = out[hol].groupby(["Scope", "Description"])["Shipped_Impact_Pct"].mean()
    key = list(zip(out["Scope"], out["Description"]))
    out["Pooled_Z"] = [pooled.get(k, np.nan) if h else np.nan for k, h in zip(key, out["Event_Type"].eq("Holiday"))]
    out["Typical_Impact_Pct"] = [round(mean_imp.get(k, np.nan), 1) if h else np.nan
                                 for k, h in zip(key, out["Event_Type"].eq("Holiday"))]
    rec = out["Pooled_Z"].abs().ge(3)
    out.loc[rec & out["Shipped_Z"].notna(), "Verdict"] = "material (recurring)"
    out.loc[rec & out["Verdict"].eq("in forecast window"), "Verdict"] = "in forecast window: expect recurring effect"
    out["Pooled_Z"] = out["Pooled_Z"].round(1)
    return out


def _robust_std(x: pd.Series) -> float:
    x = x.dropna()
    return float(1.4826 * (x - x.median()).abs().median()) if len(x) > 5 else np.nan


# ----------------------------------------------------------------------------- series profile
def _cycle(x: np.ndarray) -> float:
    idx = np.flatnonzero(x > 0)
    if len(idx) < 3:
        return np.nan
    gaps = np.diff(idx)
    vals, cnt = np.unique(gaps, return_counts=True)
    return float(vals[np.argmax(cnt)])


def series_profile(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (s, r), g in d.groupby(KEY, sort=False):
        g = g.sort_values("Date")
        x = g["Demand_Model"].to_numpy()
        obs = g["Demand"].to_numpy()
        last24 = np.nan_to_num(obs[-24:])
        nz = last24[last24 > 0]
        adi = len(last24) / len(nz) if len(nz) else np.inf
        cv2 = (nz.std() / nz.mean()) ** 2 if len(nz) > 1 else np.nan
        cls = ("smooth" if adi < 1.32 and cv2 < 0.49 else "erratic" if adi < 1.32 else
               "intermittent" if cv2 < 0.49 else "lumpy") if len(nz) > 1 else "sparse"
        pos = np.flatnonzero(np.nan_to_num(obs) > 0)
        last_order = g["Date"].iloc[pos[-1]] if len(pos) else None
        rows.append({
            "SKU_ID": s, "Region": r, "Product_Family": g["Product_Family"].iloc[-1],
            "Customer_Name": g["Customer_Name"].iloc[-1], "Sales_Channel": g["Sales_Channel"].iloc[-1],
            "First_Month": g["Date"].iloc[0], "Last_Month": g["Date"].iloc[-1],
            "Months": len(g), "Cycle_Last12": _cycle(np.nan_to_num(obs[-12:])),
            "Cycle_Last24": _cycle(last24), "Last_Order": last_order,
            "Months_Since_Order": (pd.Period(HISTORY_END, "M") - pd.Period(last_order, "M")).n if last_order else np.nan,
            "Nonzero_Share_24": round(len(nz) / max(len(last24), 1), 3),
            "ADI": round(adi, 2) if np.isfinite(adi) else np.nan, "CV2": round(cv2, 3) if pd.notna(cv2) else np.nan,
            "Demand_Class": cls,
            "Mean_12": round(float(np.nanmean(x[-12:])), 2), "Mean_24": round(float(np.nanmean(x[-24:])), 2),
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- structural register
def _reg(rows: list, typ, date, sku, region, customer, detail, evidence, action):
    rows.append({"Type": typ, "Date": date, "SKU_ID": sku, "Region": region,
                 "Customer_Name": customer, "Detail": detail, "Evidence": evidence, "Action": action})


def cycle_changes(d: pd.DataFrame, rows: list) -> None:
    """Dominant gap between orders per calendar year; a change that persists for the
    following year is an ordering-cycle change (not a one-off skipped order)."""
    for (s, r), g in d.groupby(KEY, sort=False):
        g = g.sort_values("Date")
        yrs = g.groupby(g["Date"].str[:4])["Demand"].apply(lambda x: _cycle(np.nan_to_num(x.to_numpy())))
        yrs = yrs[g.groupby(g["Date"].str[:4]).size() >= 10].dropna()
        v = yrs.to_numpy()
        for i in range(1, len(v) - 1):
            if v[i] != v[i - 1] and v[i] == v[i + 1]:
                _reg(rows, "ordering_cycle_change", f"{yrs.index[i]}", s, r, g["Customer_Name"].iloc[-1],
                     f"orders every {v[i-1]:.0f} -> every {v[i]:.0f} month(s)",
                     f"dominant gap {yrs.index[i-1]}={v[i-1]:.0f}, {yrs.index[i]}={v[i]:.0f}, {yrs.index[i+1]}={v[i+1]:.0f}",
                     "forecast uses the latest cycle and phase")


def customer_switches(d: pd.DataFrame, rows: list) -> None:
    o = d[d["status"].eq("observed")].sort_values(KEY + ["Date"])
    prev = o.groupby(KEY)["Customer_Name"].shift()
    sw = o[prev.notna() & o["Customer_Name"].ne(prev)].assign(prev=prev)
    for _, x in sw.iterrows():
        g = o[(o["SKU_ID"] == x["SKU_ID"]) & (o["Region"] == x["Region"])]
        before = g[g["Date"] < x["Date"]].tail(12)["Demand"].mean()
        after = g[g["Date"] >= x["Date"]].head(12)["Demand"].mean()
        _reg(rows, "customer_switch", x["Date"], x["SKU_ID"], x["Region"], x["Customer_Name"],
             f"{x['prev']} -> {x['Customer_Name']}",
             f"avg demand 12m before {before:.1f}, 12m after {after:.1f}",
             "history kept; new customer's level used for the forecast")


def lost_accounts(d: pd.DataFrame, sku: pd.DataFrame, test: pd.DataFrame, rows: list) -> None:
    last = d[d["status"].eq("observed")].groupby(KEY)["Date"].max()
    eol = sku.set_index("SKU_ID")["EOL_Date"]
    in_test = set(zip(test["SKU_ID"], test["Region"]))
    for (s, r), lm in last.items():
        gap = (pd.Period(HISTORY_END, "M") - pd.Period(lm, "M")).n
        e = eol.get(s)
        if gap >= 3 and (pd.isna(e) or lm < e):
            cust = d.loc[(d["SKU_ID"] == s) & (d["Region"] == r), "Customer_Name"].iloc[-1]
            _reg(rows, "lost_account", lm, s, r, cust, f"no rows for {gap} months, no EOL",
                 f"in test.csv: {(s, r) in in_test}",
                 "forecast 0 unless the series is in test.csv" if (s, r) not in in_test else "review: test expects demand")
        elif pd.notna(e) and lm <= e and gap >= 1:
            _reg(rows, "eol_exit", lm, s, r, None, f"last sale {lm}, EOL {e}", "lifecycle as planned",
                 "forecast 0 after EOL")


def level_shifts(d: pd.DataFrame, events: pd.DataFrame, rows: list) -> None:
    """Customer x region share of the region's demand; the strongest 12-vs-12 month
    step after 2021-06 (past COVID and the chip shortage) is reported if large and clear."""
    o = d.copy()
    cr = o.groupby(["Customer_Name", "Region", "Date"])["Demand"].sum()
    rt = o.groupby(["Region", "Date"])["Demand"].sum()
    share = (cr / cr.index.droplevel(0).map(rt).values).rename("share").reset_index()
    for (c, r), g in share.groupby(["Customer_Name", "Region"]):
        g = g.sort_values("Date").reset_index(drop=True)
        best = None
        for i in range(12, len(g) - 6):
            if g.loc[i, "Date"] < "2021-07":
                continue
            a, b = g["share"].iloc[i - 12:i], g["share"].iloc[i:i + 12]
            if a.mean() <= 0:
                continue
            se = np.sqrt(a.var() / len(a) + b.var() / len(b))
            t = (b.mean() - a.mean()) / se if se > 0 else 0
            if best is None or abs(t) > abs(best[1]):
                best = (i, t, b.mean() / a.mean() - 1)
        if best and abs(best[1]) >= 4 and abs(best[2]) >= 0.15:
            dt = g.loc[best[0], "Date"]
            ev = events[(events["Scope_Type"] == "Customer") & events["Scope_Value"].str.startswith(c)
                        & events["Scope_Value"].str.endswith(r)]
            expl = ", ".join(ev["Event_ID"] + " " + ev["Description"]) if len(ev) else "no event in calendar"
            _reg(rows, "level_shift", dt, None, r, c, f"share of {r} demand {best[2]:+.0%}",
                 f"t={best[1]:.1f}; {expl}",
                 "treated as the new level (permanent)" if len(ev) else "review with sales: permanent or temporary?")


def master_conflicts(d: pd.DataFrame, sku: pd.DataFrame, test: pd.DataFrame, rows: list) -> None:
    m = sku.set_index("SKU_ID")
    first = d[d["status"].eq("observed") & d["Demand"].gt(0)].groupby("SKU_ID")["Date"].min()
    for s, f in first.items():
        la = m.at[s, "Launch_Date"]
        if pd.notna(la) and f < la:
            _reg(rows, "master_conflict", f, s, None, None, f"first sale {f} before Launch_Date {la}",
                 "transactions consistent across regions", "trust transactions; master launch date likely wrong")
    hist = set(d["SKU_ID"])
    for s in sorted(set(test["SKU_ID"]) - hist):
        _reg(rows, "new_launch", m.at[s, "Launch_Date"], s, None, None,
             f"no history; replaces {m.at[s, 'Replaces_SKU']} ({m.at[s, 'Powertrain_Application']})",
             f"status {m.at[s, 'Lifecycle_Status']}", "forecast from predecessor ramp curve")
    for s, x in m[m["Replaces_SKU"].notna()].iterrows():
        pe = m.at[x["Replaces_SKU"], "EOL_Date"] if x["Replaces_SKU"] in m.index else None
        if pd.notna(pe) and x["Launch_Date"] > pe:
            _reg(rows, "master_conflict", x["Launch_Date"], s, None, None,
                 f"successor launches {x['Launch_Date']} after predecessor EOL {pe}", "supply gap",
                 "flag for planners")


def structural_register(d, sku, test, events) -> pd.DataFrame:
    rows: list = []
    cycle_changes(d, rows)
    customer_switches(d, rows)
    lost_accounts(d, sku, test, rows)
    level_shifts(d, events, rows)
    master_conflicts(d, sku, test, rows)
    return pd.DataFrame(rows)
