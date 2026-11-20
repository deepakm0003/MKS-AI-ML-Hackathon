"""Planning intelligence outputs: coverage, consistency and explainability."""
import json

import pandas as pd
import pytest

from celeris.config import ROOT

OUT = ROOT / "outputs" / "intelligence"
pytestmark = pytest.mark.skipif(not (OUT / "series_signals.csv").exists(), reason="run the intelligence stage first")

STATUSES = {"NEW_LAUNCH", "END_OF_LIFE", "RAMPING", "HIGH_GROWTH", "GROWTH", "STABLE", "DECLINE", "SHARP_DECLINE"}


@pytest.fixture(scope="module")
def sig():
    return pd.read_csv(OUT / "series_signals.csv")


def test_every_forecast_series_has_a_signal(sig):
    fc = pd.read_csv(ROOT / "outputs" / "forecast" / "forecast_detail.csv")
    assert set(zip(fc["SKU_ID"], fc["Region"])) == set(zip(sig["SKU_ID"], sig["Region"]))


def test_status_and_risk_values(sig):
    assert set(sig["forecast_status"]) <= STATUSES
    assert set(sig["risk_level"]) == {"LOW", "MEDIUM", "HIGH"}
    assert sig["risk_score"].between(0, 100).all()
    share_high = (sig["risk_level"] == "HIGH").mean()
    assert 0.10 <= share_high <= 0.20


def test_lifecycle_and_shutdown_flagged(sig):
    eol = sig[sig["SKU_ID"].isin(["PTC-005", "PMP-003", "THM-001"])]
    assert (eol["forecast_status"] == "END_OF_LIFE").all()
    new = sig[sig["SKU_ID"].isin(["PMP-020", "PTC-029", "THM-012"])]
    assert (new["forecast_status"] == "NEW_LAUNCH").all()
    orion = sig[(sig["Customer_Name"] == "Orion Driveline") & (sig["Region"] == "North America")]
    assert orion["reason_codes"].str.contains("CUSTOMER_SHUTDOWN_IN_WINDOW").all()


def test_every_series_has_a_recommendation(sig):
    assert sig["recommendation"].notna().all() and (sig["recommendation"].str.len() > 20).all()


def test_exceptions_are_focused_and_tiered():
    e = pd.read_csv(OUT / "exceptions.csv")
    s = pd.read_csv(OUT / "series_signals.csv")
    assert len(e) < 0.3 * len(s)
    assert set(e["tier"]) == {"ACT_NOW", "REVIEW"}
    assert e.loc[e["forecast_status"].isin(["NEW_LAUNCH", "END_OF_LIFE"]), "tier"].eq("ACT_NOW").all()


def test_market_signals_relative_to_market():
    m = pd.read_csv(OUT / "market_signals.csv")
    assert (m["Level"] == "total").sum() == 1
    assert set(m.loc[m["Level"] != "total", "signal"]) <= {"OUTPACING_MARKET", "LAGGING_MARKET", "IN_LINE"}


def test_json_contract():
    recs = json.loads((OUT / "series_signals.json").read_text(encoding="utf-8"))
    need = {"sku_id", "region", "forecast_status", "demand_growth_3m", "forecast_change_vs_last_12m",
            "risk_level", "risk_score", "reason_codes", "recommendation"}
    assert need <= set(recs[0]) and isinstance(recs[0]["reason_codes"], list)


def test_interval_reliability_reported():
    r = pd.read_csv(OUT / "interval_reliability.csv")
    assert {"h_bucket", "Demand_Class", "Lifecycle", "Region"} <= set(r["Segment"])
    assert r.loc[r["Segment"] == "h_bucket", "Coverage_P10_P90"].between(0.75, 0.9).all()
