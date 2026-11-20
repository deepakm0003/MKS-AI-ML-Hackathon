"""Invariants for stage 2 (anomalies + unconstrained demand). Run the pipeline first."""
import json

import numpy as np
import pandas as pd
import pytest

from celeris.config import PROCESSED, ROOT

OUT = ROOT / "outputs" / "anomalies"
pytestmark = pytest.mark.skipif(not (PROCESSED / "demand.parquet").exists(), reason="run the pipeline first")


@pytest.fixture(scope="module")
def demand():
    return pd.read_parquet(PROCESSED / "demand.parquet")


def test_demand_columns_valid(demand):
    assert (demand["Demand"].dropna() >= 0).all()
    assert demand["Demand_Model"].notna().all()
    assert set(demand["Train_Weight"]) <= {0.0, 1.0}
    assert set(demand["Demand_Source"]) <= {"observed", "stockout_file", "backorder_netted",
                                            "allocation_uplift", "missing"}


def test_stockout_months_use_requested_units(demand):
    s = demand[demand["Demand_Source"].eq("stockout_file")]
    assert len(s) > 0
    assert np.allclose(s["Demand"], s["Requested_Units"])
    # shipments may exceed this month's request only by the backorder carried in
    # (a few stockout months have no sales row at all: the file still gives their demand)
    s = s.dropna(subset=["Units_Sold"])
    assert (s["Demand"] >= s["Units_Sold"] - s["Carried_In_Units"] - 0.5).all()


def test_backorder_netted(demand):
    b = demand[demand["Demand_Source"].eq("backorder_netted")]
    assert np.allclose(b["Demand"], (b["Units_Sold"] - b["Backorder_In"]).clip(lower=0))


def test_unconstrained_demand_not_below_shipments_in_allocation(demand):
    a = demand[demand["Demand_Source"].eq("allocation_uplift")]
    assert (a["Demand"] >= a["Units_Sold"] - 0.5).all()


def test_excluded_months_use_expected_for_lags(demand):
    x = demand[demand["Train_Weight"].eq(0) & demand["Expected"].notna()]
    assert np.allclose(x["Demand_Model"], x["Expected"])


def test_register_rows_point_to_panel(demand):
    reg = pd.read_csv(OUT / "anomaly_register.csv")
    need = {"Date", "SKU_ID", "Region", "Type", "Category", "Reason", "Action", "Confidence"}
    assert need <= set(reg.columns)
    keys = set(zip(demand["Date"], demand["SKU_ID"], demand["Region"]))
    assert all(k in keys for k in zip(reg["Date"], reg["SKU_ID"], reg["Region"]))
    assert set(reg["Category"]) <= {"data_error", "stockout", "real_event", "spike", "gap", "unknown"}


def test_event_impact_sanity():
    ev = pd.read_csv(OUT / "event_impact.csv").set_index("Event_ID")
    for covid in ["EV-010", "EV-011", "EV-012", "EV-013"]:      # COVID lockdowns
        assert ev.at[covid, "Verdict"] == "material" and ev.at[covid, "Shipped_Impact_Pct"] < -40
    assert ev.at["EV-038", "Shipped_Impact_Pct"] < -50            # Nexon strike
    assert ev.at["EV-043", "Verdict"] == "no measurable effect"   # trade fair


def test_series_profile_one_row_per_series(demand):
    prof = pd.read_parquet(PROCESSED / "series_profile.parquet")
    assert not prof.duplicated(["SKU_ID", "Region"]).any()
    assert len(prof) == demand.groupby(["SKU_ID", "Region"]).ngroups
    assert set(prof["Demand_Class"]) <= {"smooth", "erratic", "intermittent", "lumpy", "sparse"}


def test_findings_written():
    f = json.loads((OUT / "findings.json").read_text(encoding="utf-8"))
    assert "unlisted_stockout_test" in f
