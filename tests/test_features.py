"""Feature matrix: no look-ahead, and sane values. Needs the processed data."""
import numpy as np
import pandas as pd
import pytest

from celeris.config import PROCESSED

pytestmark = pytest.mark.skipif(not (PROCESSED / "demand.parquet").exists(), reason="run the pipeline first")


@pytest.fixture(scope="module")
def panel():
    from celeris.features import Panel
    rd = lambda n: pd.read_parquet(PROCESSED / f"{n}.parquet")
    return Panel(rd("demand"), rd("sku_master"), rd("macro"), rd("events_monthly"), rd("test"))


def test_no_look_ahead(panel):
    """Scrambling every month after the origin must not change any feature."""
    from celeris.features import MIDX, feature_columns
    o = MIDX["2024-10"]
    a = panel.frame(o, need_target=False)
    X, Y = panel.X.copy(), panel.Y.copy()
    rng = np.random.default_rng(0)
    panel.X[:, o + 1:] = rng.uniform(0, 500, panel.X[:, o + 1:].shape)
    panel.Y[:, o + 1:] = rng.uniform(0, 500, panel.Y[:, o + 1:].shape)
    try:
        b = panel.frame(o, need_target=False)
    finally:
        panel.X, panel.Y = X, Y
    cols = [c for c in feature_columns(a) if str(a[c].dtype) != "category"]
    pd.testing.assert_frame_equal(a[cols], b[cols])


def test_target_matches_demand(panel):
    from celeris.features import MIDX, MONTHS
    o = MIDX["2024-10"]
    f = panel.frame(o, horizons=[3])
    d = pd.read_parquet(PROCESSED / "demand.parquet").set_index(["SKU_ID", "Region", "Date"])["Demand"]
    k = panel.keys.iloc[f["series"].to_numpy()]
    expect = d.reindex(pd.MultiIndex.from_arrays([k["SKU_ID"], k["Region"], [MONTHS[o + 3]] * len(k)])).to_numpy()
    assert np.allclose(f["y"].to_numpy(), expect)


def test_phase_flags(panel):
    from celeris.features import MIDX
    f = panel.frame(MIDX["2024-10"], horizons=range(1, 7))
    assert set(np.unique(f["phase_due"])) <= {0.0, 1.0}
    monthly = f["cycle"].eq(1)
    assert (f.loc[monthly, "phase_due"] == 1).all()
