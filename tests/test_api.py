"""The read-only API serves the frozen backend."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "outputs" / "final" / "manifest.json").exists(),
                                reason="run the final stage first")
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.app import app
    return TestClient(app)


def test_health_and_kpis(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["validation"] == "PASS"
    k = client.get("/kpis").json()
    assert 0.2 < k["backtest_WAPE"] < 0.35
    assert k["forecast_P10_19m"] < k["forecast_total_19m"] < k["forecast_P90_19m"]


def test_dataset_filtering(client):
    r = client.get("/datasets/forecast_hierarchy", params={"Level": "family", "limit": 5}).json()
    assert r["total"] == 7 * 19 and len(r["rows"]) == 5
    assert client.get("/datasets/nope").status_code == 404
    assert client.get("/datasets/forecast_hierarchy", params={"bad_col": "x"}).status_code == 400


def test_series_drilldown(client):
    r = client.get("/series/BSS-001/Europe").json()
    assert len(r["forecast"]) == 19
    assert all(row["P10"] <= row["Forecast"] <= row["P90"] for row in r["forecast"])
    assert client.get("/series/NOPE/Europe").status_code == 404


def test_hierarchy_total(client):
    rows = client.get("/hierarchy", params={"level": "total"}).json()
    assert len(rows) == 19


INTEL_READY = (ROOT / "outputs" / "intelligence" / "intelligence_report.json").exists()


@pytest.mark.skipif(not INTEL_READY, reason="run the intelligence stage first")
def test_intelligence_endpoints(client):
    r = client.get("/intelligence/report").json()
    assert r["kpis"]["series"] == 3068 and r["briefing"]
    crit = client.get("/intelligence/recommendations", params={"priority": "critical", "limit": 5}).json()
    assert crit["total"] >= 1 and all(c["priority"] == "CRITICAL" for c in crit["cards"])
    proc = client.get("/intelligence/recommendations", params={"owner": "procurement"}).json()
    assert all("procurement" in c["owner"].lower() for c in proc["cards"])


@pytest.mark.skipif(not (ROOT / "artifacts" / "scenarios" / "emulator.json").exists(), reason="build the emulator first")
def test_scenario_lab(client):
    cfg = client.get("/scenario/config").json()
    assert set(cfg["sliders"]) == {"pmi", "auto_production", "vehicle_orders", "raw_material", "ev_adoption"}
    base = client.post("/scenario", json={}).json()
    assert base["total"]["change_pct"] == 0.0
    down = client.post("/scenario", json={"shocks": {"pmi": -3, "auto_production": -2},
                                          "region_overlay": {"Europe": -5}}).json()
    assert down["total"]["change_pct"] < 0 and down["responses"]
    eu = next(x for x in down["by_region"] if x["Region"] == "Europe")
    others = [x["Change_pct"] for x in down["by_region"] if x["Region"] != "Europe"]
    assert eu["Change_pct"] < min(others)
    assert client.post("/scenario", json={"shocks": {"pmi": 40}}).status_code == 400
    assert client.post("/scenario", json={"shocks": {"oil": 1}}).status_code == 400
    assert "Downside" in client.get("/scenario/presets").json()


def test_filter_options(client):
    r = client.get("/meta/filters").json()
    assert len(r["families"]) == 7 and len(r["regions"]) == 6 and len(r["channels"]) == 4
    assert r["combo_fields"] == ["sku", "region", "channel", "customer"]
    n_s, n_r, n_c, n_u = len(r["skus"]), len(r["regions"]), len(r["channels"]), len(r["customers"])
    assert all(0 <= s < n_s and 0 <= g < n_r and 0 <= c < n_c and 0 <= u < n_u for s, g, c, u in r["combos"])
    fc_series = {(row["SKU_ID"], row["Region"]) for row in
                 client.get("/datasets/forecast_detail", params={"limit": 100000}).json()["rows"]}
    combo_series = {(r["skus"][s]["id"], r["regions"][g]) for s, g, _, _ in r["combos"]}
    assert fc_series <= combo_series                        # every forecast series is filterable


# ----------------------------------------------------------------------------- filter-aware views
def test_timeline_view_totals_match_frozen_outputs(client):
    import pandas as pd
    r = client.get("/views/timeline").json()
    assert r["band_method"].startswith("calibrated company band")
    fc = pd.read_csv(ROOT / "outputs" / "final" / "forecast_detail.csv")
    assert abs(r["summary"]["units_19m"] - fc["Forecast"].sum()) < 1
    tl = pd.read_csv(ROOT / "outputs" / "intelligence" / "timeline.csv")
    assert abs(r["summary"]["revenue_19m"] - tl["Revenue_forecast"].sum()) / tl["Revenue_forecast"].sum() < 1e-6
    hist = {p["Date"]: p for p in r["history"]}
    assert len(r["forecast"]) == 19 and hist["2026-10"]["Units_unconstrained"] > 0
    assert all(p["Units_P10"] <= p["Units_forecast"] <= p["Units_P90"] for p in r["forecast"])


def test_timeline_filters_and_band_methods(client):
    one = client.get("/views/timeline", params={"family": "Thermal Management", "region": "Europe"}).json()
    assert one["band_method"].startswith("calibrated family x region band")
    two = client.get("/views/timeline", params={"region": "Europe|India"}).json()
    assert two["band_method"].startswith("sum of 2 calibrated region bands")
    eu = client.get("/views/timeline", params={"region": "Europe"}).json()["summary"]["units_19m"]
    ind = client.get("/views/timeline", params={"region": "India"}).json()["summary"]["units_19m"]
    assert abs(two["summary"]["units_19m"] - (eu + ind)) < 1
    sku = client.get("/views/timeline", params={"sku": "BSS-001"}).json()
    assert sku["band_method"].startswith("sum of SKU-level bands")
    assert client.get("/views/timeline", params={"region": "Atlantis"}).status_code == 404


def test_breakdown_view(client):
    r = client.get("/views/breakdown", params={"dim": "region"}).json()
    assert r["members"] == 6 and len(r["rows"]) == 6
    tot = client.get("/views/timeline").json()["summary"]
    assert abs(sum(x["Units_next12"] for x in r["rows"]) - tot["units_next12"]) < 1
    assert abs(sum(x["Revenue_share_next12"] for x in r["rows"]) - 1) < 1e-3   # shares rounded to 4 dp
    revs = [x["Revenue_next12"] for x in r["rows"]]
    assert revs == sorted(revs, reverse=True)
    top = client.get("/views/breakdown", params={"dim": "sku", "top": 3, "family": "Thermal Management"}).json()
    assert len(top["rows"]) == 4 and top["rows"][-1]["Member"].startswith("Other (")
    assert client.get("/views/breakdown", params={"dim": "planet"}).status_code == 400
