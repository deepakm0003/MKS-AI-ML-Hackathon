"""Exception engine - a rule playbook evaluated on computed signals at every planning level.

Each rule is a plain function over the intelligence tables. A hit records the rule id, the
scope, severity, impact in USD, urgency (months until the decision window), confidence and an
EVIDENCE dict holding every number the recommendation text will quote - so each card can be
traced to the forecast, the backtest or the history. Nothing is typed in by hand.

Priority score (0-100) = 40 x impact percentile + 30 x severity + 20 x urgency + 10 x confidence;
CRITICAL >= 70, HIGH >= 50, else MEDIUM.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import HISTORY_END

SEVERITY = {"CRITICAL": 1.0, "HIGH": 0.7, "MEDIUM": 0.4, "LOW": 0.2}
CONF = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}


def _months_until(month: str | None) -> int:
    if not month or month == "release now":
        return 0
    return max(0, (pd.Period(month, "M") - pd.Period(HISTORY_END, "M")).n)


def _urgency(m: int) -> float:
    return 1.0 if m <= 3 else 0.6 if m <= 6 else 0.3


def _hit(rule, level, scope, severity, impact, urgency, confidence, **evidence) -> dict:
    return {"rule_id": rule, "level": level, "scope": scope, "severity": severity,
            "impact_usd": float(max(impact, 0)), "urgency_months": int(urgency), "confidence": confidence,
            "evidence": {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in evidence.items()}}


def _fam_region_price(rev_fc: pd.DataFrame) -> pd.Series:
    g = rev_fc.groupby(["Product_Family", "Region"])[["Revenue", "Forecast"]].sum()
    return g["Revenue"] / g["Forecast"]


# ----------------------------------------------------------------------------- segment rules
def capacity_rules(cap: pd.DataFrame, sr: pd.DataFrame, price: pd.Series) -> list[dict]:
    out = []
    srk = sr.set_index(["Product_Family", "Region"])
    for _, r in cap.iterrows():
        k = (r["Product_Family"], r["Region"])
        risk = srk.loc[k] if k in srk.index else None
        ct = int(risk["Capacity_or_tooling_36m"]) if risk is not None else 0
        p = float(price.get(k, np.nan))
        ev = dict(family=k[0], region=k[1], throughput=round(r["Demonstrated_3m_throughput"]),
                  load_p50=round(r["Peak_3m_load_P50"]), load_p90=round(r["Peak_3m_load_P90"]),
                  util_p50=round(100 * r["Utilisation_P50"], 1), util_p90=round(100 * r["Utilisation_P90"], 1),
                  peak_window=r["Peak_load_window_end"], first_window=r["First_window_above_throughput"],
                  months_above=int(r["Months_above_throughput"]), capacity_tooling_shortages_36m=ct)
        if r["Capacity_flag"] == "ABOVE_DEMONSTRATED_THROUGHPUT":
            sev = "CRITICAL" if ct >= 5 else "HIGH"
            impact = (r["Peak_3m_load_P50"] - r["Demonstrated_3m_throughput"]) * p
            out.append(_hit("CAPACITY_ABOVE_THROUGHPUT", "family_region", f"{k[0]} | {k[1]}", sev, impact,
                            _months_until(r["First_window_above_throughput"]) - 3, "MEDIUM",
                            excess_units=round(r["Peak_3m_load_P50"] - r["Demonstrated_3m_throughput"]), **ev))
        elif r["Capacity_flag"] in ("TIGHT", "UPSIDE_ABOVE_THROUGHPUT") and ct >= 5:
            impact = max(r["Peak_3m_load_P90"] - r["Demonstrated_3m_throughput"], 0) * p
            out.append(_hit("CAPACITY_TIGHT", "family_region", f"{k[0]} | {k[1]}", "MEDIUM", impact,
                            _months_until(r["Peak_load_window_end"]) - 3, "MEDIUM", **ev))
    return out


def supply_rules(sr: pd.DataFrame, seg_sig: pd.DataFrame, rev_fc: pd.DataFrame) -> list[dict]:
    out = []
    fr = seg_sig[seg_sig["Level"] == "family_region"].set_index("Member")
    rev3 = rev_fc[rev_fc["h"] <= 3].groupby(["Product_Family", "Region"])["Revenue"].sum()
    for _, r in sr[sr["Supply_risk_level"].eq("HIGH")].iterrows():
        m = f"{r['Product_Family']} | {r['Region']}"
        if m not in fr.index or fr.at[m, "Direction"] != "GROWING":
            continue
        out.append(_hit("SUPPLY_RISK_ON_GROWING_DEMAND", "family_region", m, "HIGH",
                        rev3.get((r["Product_Family"], r["Region"]), 0.0), 0, "MEDIUM",
                        family=r["Product_Family"], region=r["Region"],
                        shortages_36m=int(r["Non_chip_shortages_36m"]), dominant_reason=r["Dominant_reason_36m"],
                        lost_units_36m=int(r["Lost_units_36m"]), fill_rate=round(float(r["Mean_fill_rate_36m"]), 1),
                        outlook_pct=round(100 * fr.at[m, "Forecast_next12_vs_last12"], 1),
                        revenue_next3=round(rev3.get((r["Product_Family"], r["Region"]), 0.0))))
    return out


def market_rules(seg_sig: pd.DataFrame, rev_fc: pd.DataFrame) -> list[dict]:
    out = []
    revs = {
        "family": rev_fc[rev_fc["h"] <= 12].groupby("Product_Family")["Revenue"].sum(),
        "region": rev_fc[rev_fc["h"] <= 12].groupby("Region")["Revenue"].sum(),
        "family_region": rev_fc[rev_fc["h"] <= 12].assign(
            m=rev_fc["Product_Family"] + " | " + rev_fc["Region"]).groupby("m")["Revenue"].sum(),
    }
    for _, r in seg_sig[seg_sig["Level"].isin(revs)].iterrows():
        rev = float(revs[r["Level"]].get(r["Member"], 0.0))
        ev = dict(segment_level=r["Level"], member=r["Member"], momentum_vs_market=round(100 * r["Momentum_vs_market"], 1),
                  outlook_vs_market=round(100 * r["Outlook_vs_market"], 1),
                  outlook_pct=round(100 * r["Forecast_next12_vs_last12"], 1),
                  yoy_3m=round(100 * r["YoY_last3m"], 1), mix_shift_pts=round(r["Mix_shift_pts"], 2),
                  peak_months=r["Peak_months"], revenue_next12=round(rev))
        if r["Signal"] == "OUTPACING_MARKET" and r["Direction"] == "GROWING":
            out.append(_hit("SEGMENT_OUTPACING_MARKET", r["Level"], r["Member"], "MEDIUM",
                            abs(r["Outlook_vs_market"]) * rev, 1, "HIGH", **ev))
        elif r["Signal"] == "LAGGING_MARKET":
            out.append(_hit("SEGMENT_LAGGING_MARKET", r["Level"], r["Member"], "MEDIUM",
                            abs(min(r["Outlook_vs_market"], r["Momentum_vs_market"])) * rev, 1, "HIGH", **ev))
        elif r["Signal"] == "MIXED":
            out.append(_hit("FORECAST_VS_MOMENTUM_CONFLICT", r["Level"], r["Member"], "HIGH",
                            abs(r["Outlook_vs_market"]) * rev, 0, "MEDIUM", **ev))
    return out


def powertrain_rules(seg_sig: pd.DataFrame, rev_fc: pd.DataFrame, sku: pd.DataFrame) -> list[dict]:
    p = seg_sig[seg_sig["Level"] == "powertrain"].set_index("Member")
    if not {"EV", "ICE"} <= set(p.index):
        return []
    pt = sku.set_index("SKU_ID")["Powertrain_Application"]
    rev = rev_fc[rev_fc["h"] <= 12].assign(P=rev_fc["SKU_ID"].map(pt)).groupby("P")["Revenue"].sum()
    ev, ice = p.loc["EV"], p.loc["ICE"]
    if ev["Signal"] == "OUTPACING_MARKET" and ice["Direction"] in ("DECLINING", "STABLE"):
        return [_hit("EV_SHIFT", "powertrain", "EV vs ICE", "HIGH",
                     abs(ice["Outlook_vs_market"]) * rev.get("ICE", 0) + abs(ev["Outlook_vs_market"]) * rev.get("EV", 0),
                     3, "HIGH", ev_outlook=round(100 * ev["Forecast_next12_vs_last12"], 1),
                     ice_outlook=round(100 * ice["Forecast_next12_vs_last12"], 1),
                     ev_share_next12=round(100 * ev["Share_next12"], 1), ev_share_last12=round(100 * ev["Share_last12"], 1),
                     ice_share_next12=round(100 * ice["Share_next12"], 1), ice_share_last12=round(100 * ice["Share_last12"], 1),
                     ev_revenue_next12=round(rev.get("EV", 0)), ice_revenue_next12=round(rev.get("ICE", 0)))]
    return []


# ----------------------------------------------------------------------------- SKU-region rules
def series_rules(s: pd.DataFrame, nc: pd.DataFrame) -> list[dict]:
    out = []
    ncx = nc.set_index(["SKU_ID", "Region"])
    for (sk, rg), r in s.iterrows():
        scope = f"{sk} | {rg}"
        c = ncx.loc[(sk, rg)] if (sk, rg) in ncx.index else None
        base = dict(sku=sk, region=rg, family=r["Product_Family"], customer=r["Customer_Name"],
                    segment=r.get("Segment"), service_level=int(round(100 * r["Service_level"])) if pd.notna(r.get("Service_level")) else None,
                    fc_next3=round(r["fc_next3"]), fc_next12=round(r["fc_next12"]), hist_last12=round(r["hist_last12"]),
                    cover_next3=round(c["Leadtime_cover"]) if c is not None else None,
                    buffer_next3=round(c["Safety_buffer"]) if c is not None else None,
                    risk_score=float(r["risk_score"]), backtest_wape=round(100 * r["backtest_wape"], 1) if pd.notna(r["backtest_wape"]) else None)
        price = r["revenue_next12"] / r["fc_next12"] if r["fc_next12"] > 0 else 0
        if r["forecast_status"] == "NEW_LAUNCH":
            out.append(_hit("NEW_LAUNCH_READINESS", "sku_region", scope, "HIGH", r["revenue_next12"], 0, "LOW",
                            launch=r["Launch_Date"], predecessor=r["Replaces_SKU"], **base))
            continue
        if r["forecast_status"] == "END_OF_LIFE":
            out.append(_hit("EOL_RUNDOWN", "sku_region", scope, "MEDIUM", r["revenue_next12"],
                            max(_months_until(r["EOL_Date"]) - 3, 0), "MEDIUM", eol=r["EOL_Date"], **base))
            continue
        if r["sustained_surge"]:
            out.append(_hit("SKU_DEMAND_SURGE", "sku_region", scope, "HIGH",
                            r["revenue_upside_next12"] + (base["buffer_next3"] or 0) * price, 0, r["confidence"],
                            growth_3m=round(100 * r["growth_3m_yoy"], 1), growth_6m=round(100 * r["growth_6m_yoy"], 1),
                            vs_family=round(100 * r["growth_3m_vs_family"], 1), z=round(float(r["z_growth_3m"]), 1),
                            forecast_change=round(100 * r["forecast_change_vs_last12"], 1), **base))
        elif r["sustained_decline"] or r["forecast_status"] == "SHARP_DECLINE":
            out.append(_hit("SKU_DEMAND_DECLINE", "sku_region", scope, "MEDIUM", r["revenue_downside_next12"], 0,
                            r["confidence"], growth_3m=round(100 * r["growth_3m_yoy"], 1) if pd.notna(r["growth_3m_yoy"]) else None,
                            forecast_change=round(100 * r["forecast_change_vs_last12"], 1), **base))
        if r["forecast_anomaly"]:
            out.append(_hit("FORECAST_ANOMALY", "sku_region", scope, "HIGH",
                            abs(r["fc_next3"] - r["actual_last3"]) * price, 0, "LOW",
                            actual_last3=round(r["actual_last3"]),
                            jump_3m=round(100 * r["forecast_jump_3m"], 1) if pd.notna(r["forecast_jump_3m"]) else None,
                            forecast_change=round(100 * r["forecast_change_vs_last12"], 1), **base))
        if r["risk_level"] == "HIGH" and r.get("ABC") == "A" and not r["sustained_surge"]:
            out.append(_hit("HIGH_RISK_HIGH_VALUE", "sku_region", scope, "MEDIUM",
                            r["revenue_downside_next12"] + r["revenue_upside_next12"], 0, "LOW",
                            band_low=round(r["p10_next12"]), band_high=round(r["p90_next12"]),
                            top_risk_driver=max(["backtest_error", "band_width", "volatility", "short_history",
                                                 "data_issues", "macro_sensitivity"], key=lambda k: r[f"risk_{k}"]),
                            **base))
        if pd.notna(r.get("new_product_risk")) and r["new_product_risk"] >= 70 and r["forecast_status"] == "RAMPING":
            out.append(_hit("UNSTABLE_RAMP_UP", "sku_region", scope, "MEDIUM", r["revenue_downside_next12"], 0, "LOW",
                            history_months=int(r["history_months"]), ramp_cv=round(float(r["ramp_cv_6m"]), 2),
                            **base))
    return out


def customer_rules(s: pd.DataFrame, rev_fc: pd.DataFrame) -> list[dict]:
    out = []
    shut = rev_fc[rev_fc["method"].str.contains("shutdown", na=False)].copy()
    if shut.empty:
        return out
    shut["factor"] = shut["method"].str.extract(r"shutdown x([\d.]+)").astype(float)
    shut["lost_units"] = shut["Forecast"] / shut["factor"] - shut["Forecast"]
    shut["lost_rev"] = shut["lost_units"] * shut["Unit_Price"]
    for (cust, reg), g in shut.groupby(["Customer_Name", "Region"]):
        ev_id = g["method"].str.extract(r"(EV-\d+)")[0].dropna().iloc[0]
        out.append(_hit("CUSTOMER_SHUTDOWN", "customer", f"{cust} | {reg}", "HIGH", g["lost_rev"].sum(),
                        max(_months_until(g["Date"].min()) - 3, 0), "MEDIUM", customer=cust, region=reg, event=ev_id,
                        shutdown_months=", ".join(sorted(g["Date"].unique())), series=int(g.groupby(["SKU_ID"]).ngroups),
                        units_removed=round(g["lost_units"].sum()), revenue_removed=round(g["lost_rev"].sum())))
    return out


# ----------------------------------------------------------------------------- ranking
def rank(hits: list[dict]) -> pd.DataFrame:
    e = pd.DataFrame(hits)
    imp = np.log1p(e["impact_usd"]).rank(pct=True)
    e["priority_score"] = (40 * imp + 30 * e["severity"].map(SEVERITY) + 20 * e["urgency_months"].map(_urgency)
                           + 10 * e["confidence"].map(CONF)).round(1)
    e["priority"] = np.where(e["priority_score"] >= 70, "CRITICAL", np.where(e["priority_score"] >= 50, "HIGH", "MEDIUM"))
    e = e.sort_values("priority_score", ascending=False).reset_index(drop=True)
    e.insert(0, "exception_id", [f"EX-{i + 1:04d}" for i in range(len(e))])
    return e


def evaluate(ctx: dict) -> pd.DataFrame:
    price = _fam_region_price(ctx["rev_fc"])
    hits = (capacity_rules(ctx["capacity"], ctx["supply"], price)
            + supply_rules(ctx["supply"], ctx["segments"], ctx["rev_fc"])
            + market_rules(ctx["segments"], ctx["rev_fc"])
            + powertrain_rules(ctx["segments"], ctx["rev_fc"], ctx["sku"])
            + series_rules(ctx["series"], ctx["next_cycle"])
            + customer_rules(ctx["series"], ctx["rev_fc"]))
    return rank(hits)
