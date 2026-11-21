"""Milestone 3 planning-intelligence engine: one block of checks per module."""
import json
import re

import numpy as np
import pandas as pd
import pytest

from celeris.config import PROCESSED, RAW, ROOT

INTEL = ROOT / "outputs" / "intelligence"
pytestmark = pytest.mark.skipif(not (INTEL / "intelligence_report.json").exists(),
                                reason="run the intelligence stage first")
PRED = ROOT / "artifacts" / "experiments" / "c9c_keep_pull_forward" / "predictions.parquet"


@pytest.fixture(scope="module")
def demand():
    return pd.read_parquet(PROCESSED / "demand.parquet")


@pytest.fixture(scope="module")
def fc():
    return pd.read_csv(ROOT / "outputs" / "final" / "forecast_detail.csv")


@pytest.fixture(scope="module")
def cards():
    return json.loads((INTEL / "recommendations.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- pricing
def test_announced_price_rises_match_history(demand):
    from celeris.intel.pricing import announced_rises, price_rise_check
    ev = pd.read_csv(RAW / "events_calendar.csv")
    r = announced_rises(ev)
    assert r[2027] == pytest.approx(0.045) and r[2028] == pytest.approx(0.04)
    chk = price_rise_check(demand, ev).dropna()
    assert (chk["Realised_median_rise"] - chk["Announced_rise"]).abs().max() < 0.005


def test_price_book_covers_every_forecast_sku(fc):
    book = pd.read_csv(INTEL / "price_book.csv").set_index("SKU_ID")
    assert set(fc["SKU_ID"]) <= set(book.index)
    sub = book.loc[sorted(set(fc["SKU_ID"]))]
    assert sub[["Price_2026", "Price_2027", "Price_2028"]].notna().all().all()
    assert np.allclose(sub["Price_2027"], sub["Price_2026"] * 1.045, rtol=1e-3)


def test_timeline_continues_history_into_forecast():
    t = pd.read_csv(INTEL / "timeline.csv")
    h, f = t[t["Part"] == "history"], t[t["Part"] == "forecast"]
    assert h["Date"].max() == "2026-10" and f["Date"].min() == "2026-11" and len(f) == 19
    assert (f["Units_P10"] <= f["Units_forecast"]).all() and (f["Units_forecast"] <= f["Units_P90"]).all()
    # recovered demand >= shipments overall (single backorder catch-up months can be lower)
    assert h["Units_unconstrained"].sum() >= h["Units_shipped"].sum()


# ----------------------------------------------------------------------------- segmentation
def test_abc_xyz_segments():
    s = pd.read_csv(INTEL / "segmentation.csv")
    assert not s.duplicated(["SKU_ID", "Region"]).any()
    a_share = s.loc[s["ABC"] == "A", "Revenue_next12"].sum() / s["Revenue_next12"].sum()
    assert 0.78 <= a_share <= 0.81
    assert set(s["XYZ"]) <= {"X", "Y", "Z", "N"} and s["Service_level"].between(0.8, 0.95).all()
    x = s[s["XYZ"] == "X"]
    assert (x["Backtest_WAPE"] <= 0.25).all()


# ----------------------------------------------------------------------------- supply
def test_leadtime_quantiles_are_calibrated():
    c = pd.read_csv(INTEL / "leadtime_calibration.csv")
    assert 0.86 <= c["Coverage_q90"].mean() <= 0.94
    assert 0.92 <= c["Coverage_q95"].mean() <= 0.97
    assert (c["Coverage_q90"] > c["Coverage_forecast_only"]).all()


def test_procurement_plan(fc):
    p = pd.read_csv(INTEL / "procurement_plan.csv")
    assert len(p) == len(fc)
    w = p.dropna(subset=["Leadtime_cover"])
    assert (w["Leadtime_cover"] >= w["Leadtime_P50"] - 1e-6).all()
    assert (w["Safety_buffer"] >= 0).all()
    assert (w.loc[w["Leadtime_P50"] < 3, "Safety_buffer"] == 0).all()                # make to order
    first = p[p["h"] <= 3]["Order_release_month"]
    assert (first == "release now").all()                              # lead time 3 months
    later = p[p["h"] >= 4]["Order_release_month"]
    assert later.str.match(r"^\d{4}-\d{2}$").all()


def test_capacity_check_definitions(demand):
    c = pd.read_csv(INTEL / "capacity_check.csv")
    assert len(c) == demand.groupby(["Product_Family", "Region"]).ngroups
    assert np.allclose(c["Utilisation_P50"], c["Peak_3m_load_P50"] / c["Demonstrated_3m_throughput"], atol=1e-3)
    above = c["Capacity_flag"] == "ABOVE_DEMONSTRATED_THROUGHPUT"
    assert (c.loc[above, "Utilisation_P50"] > 1).all() and (c.loc[~above, "Utilisation_P50"] <= 1).all()


def test_supply_risk_from_stockout_file():
    s = pd.read_csv(INTEL / "supply_risk.csv")
    so = pd.read_parquet(PROCESSED / "stockouts.parquet")
    assert s["Shortage_months_all"].sum() == so["Valid"].sum()
    assert set(s["Supply_risk_level"]) <= {"HIGH", "MEDIUM", "LOW"}


# ----------------------------------------------------------------------------- demand signals
def test_demand_signals_levels_and_shares():
    s = pd.read_csv(INTEL / "demand_signals.csv")
    assert {"total", "family", "region", "family_region", "customer", "channel", "powertrain"} <= set(s["Level"])
    for lvl in ["family", "region", "channel", "powertrain"]:
        g = s[s["Level"] == lvl]
        assert g["Share_last12"].sum() == pytest.approx(1, abs=0.01)
        assert g["Share_next12"].sum() == pytest.approx(1, abs=0.01)
    mixed = s[s["Signal"] == "MIXED"]
    assert (np.sign(mixed["Momentum_vs_market"]) != np.sign(mixed["Outlook_vs_market"])).all()
    assert s.loc[s["Level"] == "total", "Signal"].iloc[0].startswith("MARKET_")


# ----------------------------------------------------------------------------- risk
def test_series_risk_is_explainable():
    from celeris.intel.forecast_risk import risk_explanation
    r = pd.read_csv(INTEL / "series_risk.csv")
    assert len(r) == 3068 and set(r["confidence"]) <= {"HIGH", "MEDIUM", "LOW"}
    row = r.iloc[0]
    parts = risk_explanation(row)
    base = sum(p["points"] for p in parts)
    bump = 10 if (row["new_launch"] or row["eol_in_window"] or row["customer_shutdown_in_window"]) else 0
    assert row["risk_score"] == pytest.approx(min(100, base + bump), abs=0.6)
    assert (r["revenue_downside_next12"] >= 0).all() and (r["revenue_upside_next12"] >= 0).all()


# ----------------------------------------------------------------------------- exceptions + recommendations
def test_every_card_is_filled_from_evidence(cards):
    from celeris.intel.recommendations import PLAYBOOK
    assert cards and all(c["rule_id"] in PLAYBOOK for c in cards)
    for c in cards:
        for field in ["finding", "action", "window", "trade_off"]:
            assert "{" not in c[field] and "}" not in c[field]
        tmpl = PLAYBOOK[c["rule_id"]]["finding"] + PLAYBOOK[c["rule_id"]]["action"]
        for key in re.findall(r"{(\w+)}", tmpl):
            assert key in c["evidence"], (c["id"], key)
    scores = [c["priority_score"] for c in cards]
    assert scores == sorted(scores, reverse=True)
    assert {c["priority"] for c in cards} <= {"CRITICAL", "HIGH", "MEDIUM"}


def test_exception_numbers_trace_to_outputs(cards):
    cap = pd.read_csv(INTEL / "capacity_check.csv").set_index(["Product_Family", "Region"])
    for c in [c for c in cards if c["rule_id"] == "CAPACITY_ABOVE_THROUGHPUT"]:
        e = c["evidence"]
        r = cap.loc[(e["family"], e["region"])]
        assert e["throughput"] == round(r["Demonstrated_3m_throughput"])
        assert e["util_p50"] == pytest.approx(100 * r["Utilisation_P50"], abs=0.11)


def test_priority_formula():
    from celeris.intel.exceptions import rank
    hits = [{"rule_id": "X", "level": "l", "scope": str(i), "severity": "HIGH", "impact_usd": 10 ** i,
             "urgency_months": 0, "confidence": "HIGH", "evidence": {}} for i in range(1, 6)]
    e = rank(hits)
    assert e["impact_usd"].iloc[0] == 10 ** 5 and e["priority_score"].iloc[0] == pytest.approx(40 + 21 + 20 + 10)


# ----------------------------------------------------------------------------- scenarios
def test_emulator_exact_at_base_and_validated():
    from celeris.intel import scenarios as SC
    p = ROOT / "artifacts" / "scenarios" / "emulator.json"
    if not p.exists():
        pytest.skip("run scripts/scenario_simulations.py first")
    m = SC.load(p)
    r = SC.evaluate(m, {})
    assert r["total"]["change_pct"] == 0.0
    v = pd.read_csv(ROOT / "artifacts" / "scenarios" / "emulator_validation.csv")
    assert v["total_abs_err_pts"].mean() < 1.0 and v["family_mae_pts"].mean() < 1.2
    with pytest.raises(ValueError):
        SC.evaluate(m, {"pmi": 25})
    o = SC.evaluate(m, {}, region_overlay={"Europe": 10})
    eu = next(x for x in o["by_region"] if x["Region"] == "Europe")
    assert eu["Change_pct"] == pytest.approx(10, abs=0.01)


def test_scenario_presets_match_the_stress_test():
    pre = json.loads((INTEL / "scenario_presets.json").read_text(encoding="utf-8"))
    stress = pd.read_csv(ROOT / "artifacts" / "reports" / "macro_stress.csv").set_index("Scenario")
    assert pre["Downside"]["total"]["change_pct"] == pytest.approx(stress.at["Combined downside", "Total_vs_base_pct"], abs=0.05)
    assert pre["PMI -3"]["total"]["change_pct"] == pytest.approx(stress.at["PMI -3", "Total_vs_base_pct"], abs=0.05)
    assert pre["Base case"]["total"]["change_pct"] == 0.0


# ----------------------------------------------------------------------------- report
def test_report_briefing_numbers_come_from_kpis():
    r = json.loads((INTEL / "intelligence_report.json").read_text(encoding="utf-8"))
    k = r["kpis"]
    assert f"{k['units_next12']:,.0f}" in r["briefing"][0]["text"]
    assert all(b["sources"] for b in r["briefing"])
    assert k["exceptions"] == sum(k["exceptions_by_priority"].values())
