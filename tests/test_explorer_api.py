"""Demand Explorer endpoints: seasonality, drill-down, lifecycle and the series detail."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "outputs" / "intelligence" / "sku_lifecycle.csv").exists(),
                                reason="run the final and intelligence stages first")
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.app import app
    return TestClient(app)


def test_seasonality(client):
    r = client.get("/views/seasonality").json()
    idx = [m["hist_index"] for m in r["by_month"]]
    assert len(idx) == 12 and abs(sum(idx) / 12 - 1) < 1e-9          # index averages to 1
    s = r["stats"]
    assert len(s["peak_months"]) == 2 and 0 < s["zero_month_share_24m"] < 1
    assert sum(s["demand_classes"].values()) > 3000
    assert {y["kind"] for y in r["years"]} == {"history", "forecast"}
    eu = client.get("/views/seasonality", params={"region": "Europe"}).json()["stats"]
    assert eu["trough_month"] == "Aug" and eu["amplitude"] > s["amplitude"]   # European summer shutdown


def test_drilldown_levels_and_totals(client):
    fam = client.get("/views/drilldown", params={"level": "family"}).json()
    assert fam["members"] == 7 and fam["next_level"] == "sku"
    tl = client.get("/views/timeline").json()["summary"]
    assert abs(sum(x["Units_next12"] for x in fam["rows"]) - tl["units_next12"]) < 1
    assert all(len(x["spark_history"]) == 24 and len(x["spark_forecast"]) == 12 for x in fam["rows"])
    sku = client.get("/views/drilldown", params={"level": "sku", "family": "Powertrain Components"}).json()
    ptc5 = next(x for x in sku["rows"] if x["Member"] == "PTC-005")
    assert ptc5["Lifecycle_Status"] == "EOL Announced" and ptc5["EOL_Date"] == "2027-05" and ptc5["Successor_SKU"] == "PTC-029"
    reg = client.get("/views/drilldown", params={"level": "region", "sku": "BSS-001"}).json()
    assert reg["members"] == 6 and all(x["Demand_Class"] in {"smooth", "intermittent", "erratic", "lumpy"} for x in reg["rows"])
    assert client.get("/views/drilldown", params={"level": "planet"}).status_code == 400


def test_lifecycle(client):
    r = client.get("/views/lifecycle").json()
    assert r["status_counts"] == {"Active": 589, "Discontinued": 6, "EOL Announced": 3, "Planned Launch": 3}
    launches = {e["sku"]: e for e in r["events"] if e["type"] == "LAUNCH"}
    eols = {e["sku"]: e for e in r["events"] if e["type"] == "EOL"}
    assert set(launches) == {"PTC-029", "PMP-020", "THM-012"}
    assert all(eols[launches[s]["related_sku"]]["related_sku"] == s for s in launches)   # handover pairs
    dates = [e["date"] for e in r["events"]]
    assert dates == sorted(dates)
    one = client.get("/views/lifecycle", params={"family": "Thermal Management"}).json()
    assert {e["sku"] for e in one["events"]} == {"THM-012", "THM-001"}


def test_series_detail_includes_profile_lifecycle_and_risk(client):
    r = client.get("/series/PTC-005/India").json()
    assert r["profile"]["Demand_Class"] in {"smooth", "intermittent", "erratic", "lumpy"}
    assert r["lifecycle"]["Successor_SKU"] == "PTC-029"
    assert 0 <= r["risk"]["risk_score"] <= 100 and r["risk"]["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    parts = ["risk_backtest_error", "risk_band_width", "risk_volatility", "risk_short_history", "risk_data_issues",
             "risk_macro_sensitivity"]
    w = [0.35, 0.20, 0.15, 0.10, 0.10, 0.10]
    base = 100 * sum(wi * r["risk"][p] for wi, p in zip(w, parts))
    assert r["risk"]["risk_score"] in (pytest.approx(base, abs=0.6), pytest.approx(min(100, base + 10), abs=0.6))
