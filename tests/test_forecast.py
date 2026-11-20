"""Submission format, business rules and hierarchy coherence."""
import numpy as np
import pandas as pd
import pytest

from celeris.config import RAW, ROOT

OUT = ROOT / "outputs" / "forecast"
pytestmark = pytest.mark.skipif(not (OUT / "submission.csv").exists(), reason="run the forecast stage first")


@pytest.fixture(scope="module")
def sub():
    return pd.read_csv(OUT / "submission.csv")


@pytest.fixture(scope="module")
def fc():
    return pd.read_csv(OUT / "forecast_detail.csv")


def test_submission_format(sub):
    test = pd.read_csv(RAW / "test.csv")
    assert list(sub.columns) == ["Date", "SKU_ID", "Region", "Units_Sold_Forecast"]
    assert len(sub) == len(test) == 58219
    assert (sub[["Date", "SKU_ID", "Region"]].values == test[["Date", "SKU_ID", "Region"]].values).all()
    assert sub["Units_Sold_Forecast"].notna().all()
    assert (sub["Units_Sold_Forecast"] >= 0).all()
    assert pd.api.types.is_integer_dtype(sub["Units_Sold_Forecast"])


def test_no_demand_outside_lifecycle(fc):
    sku = pd.read_csv(RAW / "sku_master.csv").set_index("SKU_ID")
    eol = fc["SKU_ID"].map(sku["EOL_Date"])
    launch = fc["SKU_ID"].map(sku["Launch_Date"])
    dead = (eol.notna() & (fc["Date"] > eol)) | (fc["Date"] < launch)
    assert dead.sum() == 156
    assert (fc.loc[dead, "Units_Sold_Forecast"] == 0).all()


def test_new_launches_ramp_up(fc):
    for s in ["PMP-020", "PTC-029", "THM-012"]:
        x = fc[fc["SKU_ID"] == s].groupby("Date")["Forecast"].sum()
        x = x[x > 0]
        assert len(x) > 0 and x.iloc[0] < x.iloc[min(5, len(x) - 1)]


def test_orion_shutdown_applied(fc):
    o = fc[(fc["Customer_Name"] == "Orion Driveline") & (fc["Region"] == "North America")]
    m = o.groupby("Date")["Forecast"].sum()
    assert m["2027-07"] < 0.3 * m["2027-05"] and m["2027-08"] < 0.3 * m["2027-10"]


def test_helios_capacity_step_not_cut(fc):
    h = fc[(fc["Customer_Name"] == "Helios Auto Parts") & (fc["Region"] == "India")]
    assert "shutdown" not in " ".join(h["method"].unique())


def test_bands_ordered(fc):
    assert (fc["P10"] <= fc["Forecast"] + 1e-9).all() and (fc["Forecast"] <= fc["P90"] + 1e-9).all()


def test_hierarchy_is_coherent(fc):
    h = pd.read_csv(OUT / "forecast_hierarchy.csv")
    tot = h[h["Level"] == "total"].set_index("Date")["Forecast"]
    for level in ["family", "region", "channel", "customer", "family_region"]:
        s = h[h["Level"] == level].groupby("Date")["Forecast"].sum()
        assert np.allclose(s, tot.reindex(s.index))
    assert np.allclose(fc.groupby("Date")["Forecast"].sum(), tot.reindex(sorted(fc["Date"].unique())))
