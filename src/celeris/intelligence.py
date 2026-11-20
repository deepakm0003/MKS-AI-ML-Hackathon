"""Planning Intelligence Engine - turns the forecast into decisions.

Per SKU-region it answers: what is happening (status), how far can the forecast be trusted
(risk score and level), why (reason codes) and what the planner should do (recommendation,
with procurement quantities). Above the series it detects market changes (family, region,
customer) and lifecycle events, and it ranks a planner exception list.

Everything is computed from pipeline outputs - history, the champion forecast with its
bands, the champion's own 6-cutoff backtest errors, the macro stress test and the anomaly
and structural registers - so it re-runs unchanged when a new champion is promoted.

Thresholds are explicit constants below so every flag can be explained.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HISTORY_END
from .intervals import apply_ratio_quantiles, fit_ratio_quantiles

KEY = ["SKU_ID", "Region"]

# --- status thresholds (forecast next 12 months vs actual last 12 months) ---
HIGH_GROWTH, GROWTH, DECLINE, SHARP_DECLINE = 0.15, 0.05, -0.10, -0.25
# --- sustained-change detectors (actuals vs same months a year earlier) ---
SURGE_3M, SURGE_6M = 0.30, 0.15
DROP_3M, DROP_6M = -0.20, -0.20
VS_FAMILY = 0.20          # ... and at least 20 points above / below its own family (SKU-specific, not market)
SURGE_Z, SURGE_Z6 = 2.0, 1.5   # ... and unusual for THIS series: z-score vs its own history of 3m / 6m YoY swings
ACT_NOW_SHARE = 0.10      # top 10% of the exception list by priority = ACT NOW
# --- market change (group-level YoY of last 3 months minus YoY of last 12 months) ---
MARKET_ACCEL = 0.05
# --- risk: share of series flagged HIGH / MEDIUM ---
HIGH_RISK_SHARE, MEDIUM_RISK_SHARE = 0.15, 0.35
TARGET_COVERAGE = 0.80


# ----------------------------------------------------------------------------- helpers
def _months(end: str, n: int) -> list[str]:
    p = pd.Period(end, "M")
    return [(p - i).strftime("%Y-%m") for i in range(n - 1, -1, -1)]


def _window_sum(h: pd.DataFrame, months: list[str]) -> pd.Series:
    return h[h["Date"].isin(months)].groupby(KEY)["Demand"].sum()


def _rel(a, b):
    a, b = a.align(b, fill_value=0)
    return (a / b.where(b > 0) - 1).clip(-1, 5)


def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True).fillna(0.5)


# ----------------------------------------------------------------------------- reliability
def interval_reliability(pred: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Leave-one-cutoff-out coverage of the SKU-level P10-P90 band by segment, and a band
    widening factor for segments below the 80% target (calibrated on the same backtest)."""
    parts = []
    for c in sorted(pred["cutoff"].unique()):
        q = fit_ratio_quantiles(pred[pred["cutoff"] != c].rename(columns={"f": "f_lgb_tweedie"}), "f_lgb_tweedie")
        parts.append(apply_ratio_quantiles(pred[pred["cutoff"] == c].reset_index(drop=True), "f", q))
    t = pd.concat(parts, ignore_index=True)
    t["covered"] = (t["y"] >= t["P10"]) & (t["y"] <= t["P90"])
    t["h_bucket"] = pd.cut(t["h"], [0, 3, 6, 12, 19], labels=["1-3m", "4-6m", "7-12m", "13-19m"]).astype(str)
    rows = []
    for seg in ["h_bucket", "Demand_Class", "Volume_Band", "Lifecycle", "Product_Family", "Region"]:
        for k, g in t.groupby(seg):
            rows.append({"Segment": seg, "Value": k, "Rows": len(g), "Coverage_P10_P90": round(g["covered"].mean(), 3),
                         "Below_P10": round((g["y"] < g["P10"]).mean(), 3),
                         "Above_P90": round((g["y"] > g["P90"]).mean(), 3)})
    rel = pd.DataFrame(rows)
    widen = {}
    for seg, val in [("Lifecycle", "new (<24m)"), ("Region", "Middle East & Africa")]:
        g = t[t[seg] == val]
        if g["covered"].mean() >= TARGET_COVERAGE - 0.02:
            continue
        for k in np.arange(1.0, 3.01, 0.05):
            lo = g["f"] - k * (g["f"] - g["P10"])
            hi = g["f"] + k * (g["P90"] - g["f"])
            if ((g["y"] >= lo) & (g["y"] <= hi)).mean() >= TARGET_COVERAGE:
                widen[(seg, val)] = round(float(k), 2)
                break
    return rel, widen


# ----------------------------------------------------------------------------- engine
def build_signals(demand: pd.DataFrame, fc: pd.DataFrame, pred: pd.DataFrame, stress: pd.DataFrame,
                  register: pd.DataFrame, structural: pd.DataFrame, sku: pd.DataFrame,
                  widen: dict) -> pd.DataFrame:
    h = demand[demand["Date"] <= HISTORY_END]
    last3, last6, last12 = _months(HISTORY_END, 3), _months(HISTORY_END, 6), _months(HISTORY_END, 12)
    ly = lambda ms: [(pd.Period(m, "M") - 12).strftime("%Y-%m") for m in ms]
    keys = pd.MultiIndex.from_frame(fc[KEY].drop_duplicates()).sort_values()
    s = pd.DataFrame(index=keys).join(pd.DataFrame({
        "hist_last12": _window_sum(h, last12),
        "hist_prev12": _window_sum(h, ly(last12)),
        "growth_3m_yoy": _rel(_window_sum(h, last3), _window_sum(h, ly(last3))),
        "growth_6m_yoy": _rel(_window_sum(h, last6), _window_sum(h, ly(last6))),
    }))
    s[["hist_last12", "hist_prev12"]] = s[["hist_last12", "hist_prev12"]].fillna(0)   # new launches: no history
    s["growth_12m_yoy"] = _rel(s["hist_last12"], s["hist_prev12"])
    # each series' own history of 3- and 6-month YoY growth (2021 onward, excluding the latest value)
    piv = h.pivot_table(index=KEY, columns="Date", values="Demand_Model", aggfunc="sum").sort_index(axis=1)
    piv = piv.loc[:, piv.columns >= "2020-01"]
    for k, name in [(3, "z_growth_3m"), (6, "z_growth_6m")]:
        r = piv.T.rolling(k).sum().T
        g = np.log((r + 1) / (r.shift(12, axis=1) + 1))
        hist_g = g.loc[:, (g.columns >= "2021-07") & (g.columns < HISTORY_END)]
        mu, sd = hist_g.mean(1), hist_g.std(1)
        s[name] = ((g[HISTORY_END] - mu) / sd.where(sd > 0)).reindex(s.index)

    f = fc.copy()
    f["m"] = f["h"]
    nxt12 = f[f["m"] <= 12].groupby(KEY)
    s["fc_next12"] = nxt12["Forecast"].sum()
    s["fc_next6"] = f[f["m"] <= 6].groupby(KEY)["Forecast"].sum()
    s["p90_next6"] = f[f["m"] <= 6].groupby(KEY)["P90"].sum()
    s["p10_next12"] = nxt12["P10"].sum()
    s["p90_next12"] = nxt12["P90"].sum()
    s["forecast_change_vs_last12"] = _rel(s["fc_next12"], s["hist_last12"])
    s["band_width"] = (s["p90_next12"] - s["p10_next12"]) / s["fc_next12"].where(s["fc_next12"] > 0)

    # attributes
    attrs = fc.groupby(KEY)[["Product_Family", "Customer_Name", "Sales_Channel"]].first()
    s = s.join(attrs)
    m = sku.set_index("SKU_ID")
    idx = s.index.get_level_values(0)
    s["EOL_Date"] = idx.map(m["EOL_Date"])
    s["Launch_Date"] = idx.map(m["Launch_Date"])
    s["Replaces_SKU"] = idx.map(m["Replaces_SKU"])
    s["Powertrain"] = idx.map(m["Powertrain_Application"])
    first = h[h["Demand"].notna()].groupby(KEY)["Date"].min()
    s["history_months"] = first.reindex(s.index).map(
        lambda d: (pd.Period(HISTORY_END, "M") - pd.Period(d, "M")).n + 1 if pd.notna(d) else 0)
    mon = h[h["Date"].isin(_months(HISTORY_END, 24))].groupby(KEY)["Demand"]
    s["cv_24"] = (mon.std() / mon.mean().where(mon.mean() > 0)).reindex(s.index)
    s["zero_share_24"] = mon.apply(lambda x: (x == 0).mean()).reindex(s.index)

    # backtest reliability of this series (champion, 6 cutoffs)
    err = pred.assign(a=(pred["f"] - pred["y"]).abs(), d=pred["f"] - pred["y"]).groupby(KEY)[["a", "d", "y"]].sum()
    s["backtest_wape"] = (err["a"] / err["y"].where(err["y"] > 0)).reindex(s.index)
    s["backtest_bias"] = (err["d"] / err["y"].where(err["y"] > 0)).reindex(s.index)

    # macro sensitivity: family change under the combined downside scenario
    down = stress.set_index("Scenario").loc["Combined downside"]
    s["macro_downside_pct"] = s["Product_Family"].map(lambda fam: down.get(f"{fam}_vs_base_pct", np.nan))

    # recent anomalies / corrections / stockouts (last 24 months)
    recent = register[register["Date"] > _months(HISTORY_END, 24)[0]]
    cnt = recent.groupby(KEY + ["Category"]).size().unstack(fill_value=0)
    for c in ["data_error", "stockout", "spike", "unknown"]:
        s[f"recent_{c}"] = cnt[c].reindex(s.index).fillna(0).astype(int) if c in cnt else 0
    # structural changes
    st = structural.dropna(subset=["SKU_ID"])
    recent_st = st[st["Date"].astype(str) >= "2025"]
    for typ, col in [("ordering_cycle_change", "cycle_changed_recently"), ("customer_switch", "customer_switched_recently")]:
        k = set(zip(recent_st.loc[recent_st["Type"] == typ, "SKU_ID"], recent_st.loc[recent_st["Type"] == typ, "Region"]))
        s[col] = [i in k for i in s.index]
    shut = fc[fc["method"].str.contains("shutdown", na=False)]
    s["customer_shutdown_in_window"] = [i in set(zip(shut["SKU_ID"], shut["Region"])) for i in s.index]
    new = fc[fc["method"].str.startswith("new launch", na=False)]
    s["new_launch"] = [i in set(zip(new["SKU_ID"], new["Region"])) for i in s.index]
    rd = fc[fc["method"].str.contains("run-down", na=False)]
    s["predecessor_rundown"] = [i in set(zip(rd["SKU_ID"], rd["Region"])) for i in s.index]
    s["eol_in_window"] = s["EOL_Date"].notna() & (s["EOL_Date"] > HISTORY_END)

    # band widening for segments whose bands under-cover in the backtest
    k_new = widen.get(("Lifecycle", "new (<24m)"), 1.0)
    k_mea = widen.get(("Region", "Middle East & Africa"), 1.0)
    k = np.where(s["history_months"] < 24, k_new, 1.0)
    k = np.maximum(k, np.where(s.index.get_level_values(1) == "Middle East & Africa", k_mea, 1.0))
    s["band_widening"] = k
    s["p90_next6_planning"] = s["fc_next6"] + k * (s["p90_next6"] - s["fc_next6"])
    return s


def classify(s: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    s = s.copy()
    fc_ch = s["forecast_change_vs_last12"]
    status = np.select(
        [s["new_launch"], s["eol_in_window"], s["history_months"] < 24,
         fc_ch >= HIGH_GROWTH, fc_ch >= GROWTH, fc_ch <= SHARP_DECLINE, fc_ch <= DECLINE],
        ["NEW_LAUNCH", "END_OF_LIFE", "RAMPING", "HIGH_GROWTH", "GROWTH", "SHARP_DECLINE", "DECLINE"], "STABLE")
    s["forecast_status"] = status
    fam3 = s["Product_Family"].map(market[market["Level"] == "family"].set_index("Member")["yoy_last3m"])
    s["growth_3m_vs_family"] = (s["growth_3m_yoy"] - fam3).round(3)
    s["sustained_surge"] = (s["growth_3m_yoy"] >= SURGE_3M) & (s["growth_6m_yoy"] >= SURGE_6M)         & (s["growth_3m_vs_family"] >= VS_FAMILY) & (s["z_growth_3m"] >= SURGE_Z) & (s["z_growth_6m"] >= SURGE_Z6)
    s["sustained_decline"] = (s["growth_3m_yoy"] <= DROP_3M) & (s["growth_6m_yoy"] <= DROP_6M)         & (s["growth_3m_vs_family"] <= -VS_FAMILY) & (s["z_growth_3m"] <= -SURGE_Z) & (s["z_growth_6m"] <= -SURGE_Z6)

    # risk score: percentile-ranked components (0-100), weights sum to 1
    comp = pd.DataFrame({
        "backtest_error": _pct_rank(s["backtest_wape"]),
        "band_width": _pct_rank(s["band_width"]),
        "volatility": _pct_rank(s["cv_24"]),
        "short_history": (1 - (s["history_months"].clip(upper=36) / 36)),
        "data_issues": _pct_rank(s["recent_data_error"] + s["recent_unknown"] + s["recent_spike"]),
        "macro_sensitivity": _pct_rank(-s["macro_downside_pct"]),
    })
    w = {"backtest_error": 0.35, "band_width": 0.20, "volatility": 0.15, "short_history": 0.10,
         "data_issues": 0.10, "macro_sensitivity": 0.10}
    s["risk_score"] = (100 * sum(comp[c] * w[c] for c in w)).round(1)
    bump = s["new_launch"] | s["eol_in_window"] | s["customer_shutdown_in_window"]
    s.loc[bump, "risk_score"] = np.minimum(100, s.loc[bump, "risk_score"] + 10)
    hi_cut = s["risk_score"].quantile(1 - HIGH_RISK_SHARE)
    med_cut = s["risk_score"].quantile(1 - HIGH_RISK_SHARE - MEDIUM_RISK_SHARE)
    s["risk_level"] = np.where(s["risk_score"] >= hi_cut, "HIGH", np.where(s["risk_score"] >= med_cut, "MEDIUM", "LOW"))
    for c in comp:
        s[f"risk_{c}"] = comp[c].round(3)

    # reason codes
    fam_m = market[market["Level"] == "family"].set_index("Member")
    reg_m = market[market["Level"] == "region"].set_index("Member")
    q80 = lambda c: s[c].quantile(0.8)
    codes = []
    for (sk, rg), r in s.iterrows():
        c = []
        fm, rm = fam_m.loc[r["Product_Family"]], reg_m.loc[rg]
        if fm["signal"] == "OUTPACING_MARKET":
            c.append("FAMILY_OUTPACING_MARKET")
        if fm["signal"] == "LAGGING_MARKET":
            c.append("FAMILY_LAGGING_MARKET")
        if rm["signal"] == "OUTPACING_MARKET":
            c.append("REGION_OUTPACING_MARKET")
        if rm["signal"] == "LAGGING_MARKET":
            c.append("REGION_LAGGING_MARKET")
        if r["sustained_surge"]:
            c.append("SUSTAINED_ORDER_GROWTH")
        elif r["growth_3m_yoy"] >= 0.15 and r["z_growth_3m"] >= 1:
            c.append("RECENT_ORDER_GROWTH")
        if r["sustained_decline"]:
            c.append("SUSTAINED_ORDER_DECLINE")
        elif r["growth_3m_yoy"] <= -0.15 and r["z_growth_3m"] <= -1:
            c.append("RECENT_ORDER_DECLINE")
        if (r["sustained_decline"] and r["forecast_change_vs_last12"] > 0) or                 (r["sustained_surge"] and r["forecast_change_vs_last12"] < 0):
            c.append("FORECAST_CONFLICTS_WITH_RECENT_TREND")
        if r["band_width"] >= q80("band_width"):
            c.append("HIGH_FORECAST_VARIANCE")
        if r["backtest_wape"] >= q80("backtest_wape"):
            c.append("LOW_HISTORICAL_ACCURACY")
        if r["history_months"] < 24:
            c.append("SHORT_HISTORY")
        if r["zero_share_24"] >= 0.3:
            c.append("INTERMITTENT_DEMAND")
        if r["cycle_changed_recently"]:
            c.append("ORDER_CYCLE_CHANGED")
        if r["customer_switched_recently"]:
            c.append("CUSTOMER_SWITCHED")
        if r["recent_stockout"] > 0:
            c.append("SUPPLY_CONSTRAINED_HISTORY")
        if r["recent_data_error"] >= 2:
            c.append("REPEATED_DATA_CORRECTIONS")
        if r["macro_downside_pct"] <= -7:
            c.append("MACRO_SENSITIVE_FAMILY")
        if r["eol_in_window"]:
            c.append("APPROACHING_EOL")
        if r["new_launch"]:
            c.append("NEW_LAUNCH_RAMP")
        if r["predecessor_rundown"]:
            c.append("PREDECESSOR_RUNDOWN")
        if r["customer_shutdown_in_window"]:
            c.append("CUSTOMER_SHUTDOWN_IN_WINDOW")
        if r["band_widening"] > 1:
            c.append("BANDS_WIDENED_LOW_COVERAGE_SEGMENT")
        codes.append(c)
    s["reason_codes"] = codes
    s["recommendation"] = [recommend(r) for _, r in s.iterrows()]
    return s


def recommend(r: pd.Series) -> str:
    p90 = int(round(r["p90_next6_planning"])) if pd.notna(r["p90_next6_planning"]) else 0
    f6 = int(round(r["fc_next6"])) if pd.notna(r["fc_next6"]) else 0
    st = r["forecast_status"]
    if st == "END_OF_LIFE":
        return (f"Run inventory down to EOL {r['EOL_Date']}: buy only to the forecast ({f6} units next 6 months), "
                f"no safety stock; align last-time-buy with the successor plan.")
    if st == "NEW_LAUNCH":
        return (f"Launch stock: plan to P90 ({p90} units next 6 months, bands widened for short history); "
                f"track actuals against the ramp-up curve monthly.")
    if r["customer_shutdown_in_window"]:
        return "Customer shutdown scheduled in the window: cut replenishment for those months, re-check restart date."
    if st == "HIGH_GROWTH" or r["sustained_surge"]:
        return (f"Review procurement capacity and inventory allocation: secure supply for up to {p90} units "
                f"next 6 months (P90) vs forecast {f6}.")
    if st in ("SHARP_DECLINE",) or r["sustained_decline"]:
        return f"Reduce replenishment to the forecast ({f6} units next 6 months); confirm demand outlook with sales."
    if r["risk_level"] == "HIGH":
        return (f"Low forecast confidence: hold safety stock toward P90 ({p90} units next 6 months) "
                f"and review this forecast monthly.")
    if "SUPPLY_CONSTRAINED_HISTORY" in r["reason_codes"]:
        return "Past demand was supply-constrained: confirm supplier capacity covers the unconstrained forecast."
    if st == "GROWTH":
        return f"Growing demand: raise replenishment to the forecast ({f6} units next 6 months)."
    if st == "DECLINE":
        return f"Softening demand: trim orders to the forecast ({f6} units next 6 months)."
    return f"Plan to forecast ({f6} units next 6 months); standard safety stock."


def market_changes(demand: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    """Family / region / customer / channel momentum and forecast direction."""
    h = demand[demand["Date"] <= HISTORY_END]
    last3, last12 = _months(HISTORY_END, 3), _months(HISTORY_END, 12)
    ly = lambda ms: [(pd.Period(m, "M") - 12).strftime("%Y-%m") for m in ms]
    rows = []
    for level, col in [("family", "Product_Family"), ("region", "Region"), ("customer", "Customer_Name"),
                       ("channel", "Sales_Channel"), ("total", None)]:
        g = h.assign(_k=h[col] if col else "Total")
        f = fc.assign(_k=fc[col] if col else "Total")
        for k, gg in g.groupby("_k"):
            y3 = gg[gg["Date"].isin(last3)]["Demand"].sum() / max(gg[gg["Date"].isin(ly(last3))]["Demand"].sum(), 1) - 1
            y12 = gg[gg["Date"].isin(last12)]["Demand"].sum() / max(gg[gg["Date"].isin(ly(last12))]["Demand"].sum(), 1) - 1
            f12 = f[(f["_k"] == k) & (f["h"] <= 12)]["Forecast"].sum()
            l12 = gg[gg["Date"].isin(last12)]["Demand"].sum()
            rows.append({"Level": level, "Member": k, "yoy_last3m": round(y3, 3), "yoy_last12m": round(y12, 3),
                         "acceleration": round(y3 - y12, 3), "forecast_next12_vs_last12": round(f12 / max(l12, 1) - 1, 3)})
    m = pd.DataFrame(rows)
    tot = m[m["Level"] == "total"].iloc[0]
    m["vs_market_last3m"] = (m["yoy_last3m"] - tot["yoy_last3m"]).round(3)
    m["signal"] = np.where(m["Level"] == "total",
                           np.where(tot["acceleration"] >= MARKET_ACCEL, "MARKET_UPTURN",
                                    np.where(tot["acceleration"] <= -MARKET_ACCEL, "MARKET_DOWNTURN", "MARKET_STEADY")),
                           np.where(m["vs_market_last3m"] >= MARKET_ACCEL, "OUTPACING_MARKET",
                                    np.where(m["vs_market_last3m"] <= -MARKET_ACCEL, "LAGGING_MARKET", "IN_LINE")))
    return m


def lifecycle_alerts(fc: pd.DataFrame, sku: pd.DataFrame) -> pd.DataFrame:
    m = sku.set_index("SKU_ID")
    rows = []
    for s, r in m.iterrows():
        if pd.notna(r["EOL_Date"]) and r["EOL_Date"] > HISTORY_END:
            succ = m.index[m["Replaces_SKU"] == s].tolist()
            rows.append({"Alert": "APPROACHING_EOL", "SKU_ID": s, "Date": r["EOL_Date"],
                         "Detail": f"EOL {r['EOL_Date']}; successor {', '.join(succ) or 'none'}",
                         "Forecast_until_EOL": round(fc[(fc["SKU_ID"] == s)]["Forecast"].sum())})
        if r["Launch_Date"] > HISTORY_END:
            rows.append({"Alert": "NEW_LAUNCH", "SKU_ID": s, "Date": r["Launch_Date"],
                         "Detail": f"replaces {r['Replaces_SKU']} ({r['Powertrain_Application']}); regions: "
                                   f"{', '.join(sorted(fc.loc[fc['SKU_ID'] == s, 'Region'].unique()))}",
                         "Forecast_until_2028_05": round(fc[fc["SKU_ID"] == s]["Forecast"].sum())})
    return pd.DataFrame(rows).sort_values("Date")


def exceptions(s: pd.DataFrame) -> pd.DataFrame:
    """Planner worklist: series that need a decision, ranked by units at stake x risk."""
    trigger = (s["risk_level"].eq("HIGH") | s["forecast_status"].isin(["SHARP_DECLINE", "NEW_LAUNCH", "END_OF_LIFE"])
               | (s["forecast_status"].eq("HIGH_GROWTH") & s["sustained_surge"])
               | s["sustained_surge"] | s["sustained_decline"] | s["customer_shutdown_in_window"])
    e = s[trigger].copy()
    e["units_at_stake_next12"] = (e["p90_next12"] - e["p10_next12"]).round()
    e["priority_score"] = (e["units_at_stake_next12"].rank(pct=True) * 50 + e["risk_score"] / 2).round(1)
    must = e["forecast_status"].isin(["NEW_LAUNCH", "END_OF_LIFE"]) | e["customer_shutdown_in_window"]
    cut = e["priority_score"].quantile(1 - ACT_NOW_SHARE)
    e["tier"] = np.where(must | (e["priority_score"] >= cut), "ACT_NOW", "REVIEW")
    e["trigger"] = np.select(
        [e["forecast_status"].isin(["NEW_LAUNCH", "END_OF_LIFE"]), e["customer_shutdown_in_window"],
         e["sustained_surge"], e["sustained_decline"], e["forecast_status"].eq("SHARP_DECLINE")],
        ["lifecycle", "customer shutdown", "SKU-specific surge", "SKU-specific decline", "sharp forecast decline"],
        "high forecast risk")
    return e.sort_values(["tier", "priority_score"], ascending=[True, False])


def to_json_records(s: pd.DataFrame) -> list[dict]:
    out = []
    for (sk, rg), r in s.iterrows():
        out.append({
            "sku_id": sk, "region": rg, "product_family": r["Product_Family"], "customer": r["Customer_Name"],
            "forecast_status": r["forecast_status"],
            "demand_growth_3m": None if pd.isna(r["growth_3m_yoy"]) else round(float(r["growth_3m_yoy"]), 3),
            "forecast_change_vs_last_12m": None if pd.isna(r["forecast_change_vs_last12"]) else round(float(r["forecast_change_vs_last12"]), 3),
            "forecast_next_12m": round(float(r["fc_next12"]), 1),
            "p10_next_12m": round(float(r["p10_next12"]), 1), "p90_next_12m": round(float(r["p90_next12"]), 1),
            "risk_score": float(r["risk_score"]), "risk_level": r["risk_level"],
            "reason_codes": r["reason_codes"], "recommendation": r["recommendation"],
        })
    return out
