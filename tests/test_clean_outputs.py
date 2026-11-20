"""Invariants the cleaned outputs must satisfy. Run `python run_pipeline.py --stage clean` first."""
import json

import numpy as np
import pandas as pd
import pytest

from celeris.config import CHANNELS, HISTORY_END, HISTORY_START, PROCESSED, QUALITY, REGIONS

pytestmark = pytest.mark.skipif(not (PROCESSED / "sales_clean.parquet").exists(),
                                reason="run the pipeline first")


@pytest.fixture(scope="module")
def sales():
    return pd.read_parquet(PROCESSED / "sales_clean.parquet")


@pytest.fixture(scope="module")
def panel():
    return pd.read_parquet(PROCESSED / "panel.parquet")


def test_one_row_per_date_sku_region(sales):
    assert not sales.duplicated(["Date", "SKU_ID", "Region"]).any()


def test_dates_in_history(sales):
    assert sales["Date"].between(HISTORY_START, HISTORY_END).all()
    assert (sales["Year"] == sales["Date"].str[:4].astype(int)).all()
    assert (sales["Month"] == sales["Date"].str[5:].astype(int)).all()


def test_canonical_labels(sales):
    assert set(sales["Region"]) <= set(REGIONS)
    assert set(sales["Sales_Channel"].dropna()) <= set(CHANNELS)
    test = pd.read_parquet(PROCESSED / "test.parquet")
    assert set(sales["Customer_Name"].dropna()) <= set(test["Customer_Name"])
    sku = pd.read_parquet(PROCESSED / "sku_master.parquet")
    assert set(sales["SKU_ID"]) <= set(sku["SKU_ID"])


def test_units_non_negative(sales):
    assert (sales["Units_Sold"].dropna() >= 0).all()


def test_revenue_reconciles(sales):
    s = sales.dropna(subset=["Units_Sold"])
    assert np.allclose(s["Revenue_USD"], s["Units_Sold"] * s["Unit_Price_USD"], atol=0.05)


def test_price_same_in_every_region(sales):
    n = sales.groupby(["SKU_ID", "Date"])["Unit_Price_USD"].nunique()
    assert (n <= 1).mean() > 0.9999


def test_product_attributes_complete(sales):
    assert sales[["Product_Family", "Business_Unit", "SKU_Description"]].notna().all().all()


def test_stockout_shipments_match_sales(sales):
    """Independent check: the stockout file's Shipped_Units equals cleaned Units_Sold."""
    so = pd.read_parquet(PROCESSED / "stockouts.parquet")
    j = so.merge(sales, on=["Date", "SKU_ID", "Region"], how="inner")
    assert np.isclose(j["Shipped_Units"], j["Units_Sold"], atol=0.5).mean() > 0.999


def test_panel_status(panel):
    assert set(panel["status"]) <= {"observed", "missing_row", "missing_value", "not_active"}
    assert panel.loc[panel["status"] != "observed", "Units_Sold"].isna().all()


def test_macro_clean():
    m = pd.read_parquet(PROCESSED / "macro.parquet")
    assert not m["Date"].duplicated().any()
    assert m.drop(columns=["Date"]).notna().all().all()
    assert m["ISM_Manufacturing_PMI"].between(30, 70).all()
    full = pd.period_range(m["Date"].min(), m["Date"].max(), freq="M").strftime("%Y-%m")
    assert list(m["Date"]) == list(full)


def test_dq_report_machine_readable():
    rep = json.loads((QUALITY / "dq_report.json").read_text(encoding="utf-8"))
    assert rep["total_issues"] > 0
    log = pd.read_csv(QUALITY / "dq_issue_log.csv")
    assert len(log) == rep["total_issues"]
    assert {"file", "issue_type", "category", "action", "rule"} <= set(log.columns)
