"""Upload & score: the frozen model run on uploaded files.

The key guarantee: uploading the official train.csv + test.csv goes through cleaning, demand
recovery, features and the frozen model and reproduces the frozen submission exactly.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "outputs" / "final" / "model").exists(),
                                reason="run the final stage first (frozen model files)")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.app import app
    return TestClient(app)


def _upload(client, path_or_bytes, kind, name="f.csv"):
    data = path_or_bytes.read_bytes() if isinstance(path_or_bytes, Path) else path_or_bytes
    r = client.post("/score/uploads", files={"file": (name, data, "text/csv")}, data={"kind": kind})
    assert r.status_code == 200, r.text
    return r.json()


def _wait(client, job_id, timeout=600):
    t = time.time()
    while time.time() - t < timeout:
        s = client.get(f"/score/jobs/{job_id}").json()
        if s["status"] in ("done", "error"):
            return s
        time.sleep(0.5)
    raise AssertionError("scoring job did not finish")


def test_official_files_reproduce_the_frozen_submission(client):
    h = _upload(client, ROOT / "data" / "raw" / "train.csv", "auto", "train.csv")
    r = _upload(client, ROOT / "data" / "raw" / "test.csv", "auto", "test.csv")
    assert h["detected_kind"] == "history" and r["detected_kind"] == "request" and h["ok"] and r["ok"]
    job = client.post("/score/jobs", json={"history_upload": h["upload_id"], "request_upload": r["upload_id"]}).json()
    s = _wait(client, job["job_id"])
    assert s["status"] == "done", s["error"]
    res = client.get(f"/score/jobs/{job['job_id']}/result").json()
    assert res["frozen_comparison"]["identical"] and res["frozen_comparison"]["rows"] == res["kpis"]["rows"]
    sub = pd.read_csv(ROOT / "outputs" / "final" / "submission.csv")
    got = client.get(f"/score/jobs/{job['job_id']}/files/submission.csv")
    assert got.status_code == 200
    from io import StringIO
    mine = pd.read_csv(StringIO(got.text))
    assert len(mine) == len(sub) and (mine.values == sub.values).all()
    assert client.get(f"/score/jobs/{job['job_id']}/files/../../x").status_code == 404


def test_request_with_actuals_is_scored_and_bad_rows_rejected(client):
    rows = pd.DataFrame({
        "Date": ["2026-11", "2026-12", "2027-01", "2026-11", "2030-01", "2026-09", "2026-11"],
        "SKU_ID": ["BSS-001", "BSS-001", "bss-001", "NOPE-1", "BSS-001", "BSS-001", "BSS-001"],
        "Region": ["Europe", "Europe", "EU", "Europe", "Europe", "Europe", "Atlantis"],
        "Units_Sold": [40, 50, 45, 1, 1, 1, 1],
    })
    r = _upload(client, rows.to_csv(index=False).encode(), "request")
    assert r["has_actuals"] and r["ok"]
    job = client.post("/score/jobs", json={"request_upload": r["upload_id"]}).json()
    s = _wait(client, job["job_id"])
    assert s["status"] == "done", s["error"]
    res = client.get(f"/score/jobs/{job['job_id']}/result").json()
    assert res["kpis"]["rows"] == 3                       # 'bss-001' + 'EU' normalised and kept
    reasons = res["checks"]["request"]["rejected_by_reason"]
    assert sum(reasons.values()) == 4 and "SKU not in the product master" in reasons and "unknown region" in reasons
    acc = res["accuracy"]["overall"]
    assert acc["rows"] == 3 and acc["actual"] == 135 and acc["WAPE"] is not None
    assert res["frozen_comparison"]["identical"]          # official history -> same numbers as the frozen forecast


def test_default_request_matches_the_frozen_forecast(client):
    # every active series, no uploads: a subset of the frozen run's series must get the same numbers
    job = client.post("/score/jobs", json={}).json()
    s = _wait(client, job["job_id"])
    assert s["status"] == "done", s["error"]
    res = client.get(f"/score/jobs/{job['job_id']}/result").json()
    assert res["frozen_comparison"]["identical"], res["frozen_comparison"]


def test_bad_inputs_get_clear_errors(client):
    bad = _upload(client, b"Date,Units_Sold\n2026-11,5\n", "history")
    assert not bad["ok"] and "SKU_ID" in bad["problem"]
    assert client.post("/score/uploads", files={"file": ("e.csv", b"", "text/csv")}).status_code == 400
    assert client.post("/score/jobs", json={"request_upload": "0" * 32}).status_code == 404
    assert client.post("/score/jobs", json={"cutoff": "Oct 2026"}).status_code == 400
    job = client.post("/score/jobs", json={"cutoff": "2028-05"}).json()
    s = _wait(client, job["job_id"])
    assert s["status"] == "error" and "after the last history month" in s["error"]
    assert client.get("/score/templates/train_format_sample.csv").status_code == 200
