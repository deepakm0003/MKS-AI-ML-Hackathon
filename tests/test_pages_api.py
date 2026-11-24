"""Page aggregations (/views/planning, /views/anomalies, /views/data-health) count the FULL datasets,
and the production SPA fallback never swallows API routes."""
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


@pytest.fixture(scope="module")
def need():
    from api.views import _need
    return _need


def test_planning_totals_cover_every_line(client, need):
    nc, seg = need("procurement_next_cycle"), need("segmentation")
    r = client.get("/views/planning", params={"top": 5}).json()
    assert r["next_cycle"]["total"] == len(nc) and len(r["next_cycle"]["rows"]) == 5
    assert r["segmentation"]["total"] == len(seg)
    assert r["kpis"]["lines"] == len(nc)
    assert 0.5 < r["kpis"]["service_level_revenue_weighted"] <= 1
    assert abs(sum(s["Revenue_share"] for s in r["segments"]) - 1) < 1e-3  # shares rounded to 4 places
    assert len(r["monthly"]) == 19


def test_planning_follows_filters(client, need):
    nc = need("procurement_next_cycle")
    r = client.get("/views/planning", params={"region": "Europe", "top": 1}).json()
    assert r["next_cycle"]["total"] == int((nc["Region"] == "Europe").sum())
    assert all(c["Region"] == "Europe" for c in r["capacity"])


def test_anomaly_counts_are_full_register(client, need):
    a = need("anomaly_register")
    r = client.get("/views/anomalies", params={"top": 10}).json()
    assert r["total"] == len(a) and len(r["rows"]) == 10
    assert sum(r["by_category"].values()) == len(a)
    assert sum(m["count"] for m in r["flagged_months"]) == len(a)
    assert r["single_series"] is False and r["points"] is None
    assert len(r["timeline"]) > 24


def test_anomaly_points_for_one_series(client, need):
    a = need("anomaly_register")
    sku, region = a.iloc[0]["SKU_ID"], a.iloc[0]["Region"]
    r = client.get("/views/anomalies", params={"sku": sku, "region": region}).json()
    n = int(((a["SKU_ID"] == sku) & (a["Region"] == region)).sum())
    assert r["single_series"] is True and r["total"] == n and len(r["points"]) == n


def test_data_health_counts_full_log(client, need):
    log, rep = need("dq_issue_log"), need("dq_report")
    r = client.get("/views/data-health", params={"top": 20}).json()
    assert r["total"] == len(log) and len(r["rows"]) == 20
    assert r["total_all_files"] == rep["total_issues"]
    train = next(f for f in r["before_after"] if f["file"] == "train.csv")
    assert train["rows_after"] <= train["rows_before"]
    assert train["null_cells_after"] <= train["null_cells_before"]


def test_api_routes_are_not_shadowed_by_the_spa(client):
    # these broke when the SPA catch-all was registered before the routers
    assert client.get("/scenario/config").headers["content-type"].startswith("application/json")
    assert client.get("/meta/filters").headers["content-type"].startswith("application/json")
    miss = client.get("/views/does-not-exist")
    assert miss.status_code == 404 and miss.headers["content-type"].startswith("application/json")
    # the built dashboard calls /api/<route> when uvicorn serves it directly (deploy.sh)
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/views/planning", params={"top": 1}).status_code == 200
    if (ROOT / "dashboard" / "dist" / "index.html").exists():
        for route in ("/overview", "/scenarios", "/data-health", "/home"):   # /scenarios is not /scenario/*
            page = client.get(route)
            assert page.status_code == 200 and "text/html" in page.headers["content-type"], route
        assert client.get("/../api/app.py").status_code in (200, 404)  # never the source file
        assert "FastAPI" not in client.get("/../api/app.py").text
