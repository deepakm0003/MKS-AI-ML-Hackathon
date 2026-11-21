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
