"""Phase D: cleaning variants, stratified bands and reliability tables."""
import numpy as np
import pandas as pd
import pytest

from celeris.config import PROCESSED, ROOT
from celeris.intervals import apply_ratio_quantiles, fit_ratio_quantiles, stratum
from celeris.robustness import (EXCLUDED_TYPES, VARIANTS, _model_columns, demand_variant, series_reliability,
                                yardstick)

pytestmark = pytest.mark.skipif(not (PROCESSED / "demand.parquet").exists(), reason="run the pipeline first")
PRED = ROOT / "artifacts" / "experiments" / "champion" / "predictions.parquet"


@pytest.fixture(scope="module")
def demand():
    return pd.read_parquet(PROCESSED / "demand.parquet")


def test_model_columns_reproduce_the_champion_target(demand):
    r = _model_columns(demand, demand["Anomaly_Type"].isin(EXCLUDED_TYPES)).sort_index()
    assert (r["Train_Weight"] == demand["Train_Weight"]).all()
    assert np.allclose(r["Demand_Model"], demand["Demand_Model"])


def test_variants_change_only_what_they_claim(demand):
    rec = demand["Demand_Source"].isin(["stockout_file", "allocation_uplift", "backorder_netted"])
    v = demand_variant(demand, "no_stockout_recovery").sort_index()
    changed = v["Demand"].fillna(-1) != demand["Demand"].fillna(-1)
    assert changed.any() and not (changed & ~rec).any()
    assert (v.loc[rec, "Demand"] == demand.loc[rec, "Units_Sold"].fillna(demand.loc[rec, "Shipped_Units"])).all()
    v = demand_variant(demand, "no_training_exclusions")
    assert (v["Train_Weight"] == 0).sum() == demand["Anomaly_Type"].eq("missing").sum()
    v = demand_variant(demand, "exclude_stockouts").sort_index()
    assert (v.loc[rec, "Train_Weight"] == 0).all()
    assert set(VARIANTS) >= {"baseline", "no_stockout_recovery", "no_training_exclusions"}


def test_yardstick_excludes_every_cleaned_month(demand):
    ys = yardstick(demand).merge(demand, on=["SKU_ID", "Region", "Date"])
    assert ys["Demand_Source"].eq("observed").all()
    assert not ys["Anomaly_Type"].isin(EXCLUDED_TYPES + ["stockout", "backorder_catch_up"]).any()


def test_stratum_labels():
    s = stratum([np.nan, 5, 30, 30], ["Europe", "Europe", "Latin America", "India"])
    assert list(s) == ["new|core", "new|core", "est|vol", "est|core"]


@pytest.mark.skipif(not PRED.exists(), reason="run the champion backtest first")
def test_stratified_bands_are_calibrated_and_ordered():
    p = pd.read_parquet(PRED)
    tr, te = p[p["cutoff"] != "2025-03"], p[p["cutoff"] == "2025-03"].reset_index(drop=True)
    a = apply_ratio_quantiles(te, "f", fit_ratio_quantiles(tr, "f", strata=True))
    assert (a["P10"] <= a["P50"] + 1e-9).all() and (a["P50"] <= a["P90"] + 1e-9).all()
    cov = ((te["y"] >= a["P10"]) & (te["y"] <= a["P90"])).mean()
    assert 0.75 <= cov <= 0.90
    new = te["age"] < 24
    assert ((te.loc[new, "y"] >= a.loc[new, "P10"]) & (te.loc[new, "y"] <= a.loc[new, "P90"])).mean() > 0.74


@pytest.mark.skipif(not PRED.exists(), reason="run the champion backtest first")
def test_reliability_tiers_cover_all_series():
    p = pd.read_parquet(PRED)
    s, tiers = series_reliability(p)
    assert tiers["Series"].sum() == len(s) == p.groupby(["SKU_ID", "Region"], observed=True).ngroups
    assert abs(tiers["Volume_share"].sum() - 1) < 0.01
