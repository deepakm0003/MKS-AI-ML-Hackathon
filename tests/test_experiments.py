"""Experiment runner: every model type trains and predicts on a small sample, specs resolve,
and the promotion rule behaves as documented."""
import numpy as np
import pandas as pd
import pytest

from celeris.config import PROCESSED

pytestmark = pytest.mark.skipif(not (PROCESSED / "demand.parquet").exists(), reason="run the pipeline first")


@pytest.fixture(scope="module")
def sample():
    from celeris.experiments import FrameStore
    from celeris.features import MIDX
    st = FrameStore()
    spec = {"feature_set": "base+cross", "train_first_origin": "2023-01", "train_origin_step": 6}
    train = st.training(spec, MIDX["2024-04"]).sample(4000, random_state=0)
    ev = st.evaluation(spec, MIDX["2024-04"]).sample(1500, random_state=0)
    return train, ev


@pytest.mark.parametrize("name", ["champion", "cross_series", "no_macro", "hurdle", "horizon_split",
                                  "seed_bag", "catboost"])
def test_every_model_type_runs(sample, name):
    from celeris.experiments import fit_predict, resolve
    train, ev = sample
    spec = resolve(name)
    spec.update(rounds=10, cb_iterations=10, feature_set="base+cross")
    if name != "cross_series":
        train = train[[c for c in train.columns if not c.startswith("x_")]]
        ev = ev[[c for c in ev.columns if not c.startswith("x_")]]
    f, info = fit_predict(spec, train, ev)
    assert len(f) == len(ev) and np.isfinite(f).all() and (f >= 0).all()
    if name == "no_macro":
        assert info["n_features"] < 87


def test_promotion_rule():
    from celeris.experiments import add_promotion_verdicts, load_config
    cfg = load_config()
    cuts = cfg["evaluation"]["cutoffs"]
    base = {f"WAPE_{c}": 0.28 for c in cuts}
    buckets = [f"WAPE_{lo}-{hi}m" for lo, hi in cfg["evaluation"]["horizon_buckets"]]
    reg = pd.DataFrame([
        {"experiment": "champion", "WAPE": 0.28, "Bias": -0.03, **base, **{b: 0.28 for b in buckets}},
        {"experiment": "better", "WAPE": 0.27, "Bias": -0.02, **{f"WAPE_{c}": 0.27 for c in cuts}, **{b: 0.27 for b in buckets}},
        {"experiment": "lucky", "WAPE": 0.275, "Bias": -0.03, **{b: 0.275 for b in buckets},
         **{f"WAPE_{c}": (0.25 if i == 0 else 0.281) for i, c in enumerate(cuts)}},
        {"experiment": "biased", "WAPE": 0.27, "Bias": -0.06, **{f"WAPE_{c}": 0.27 for c in cuts}, **{b: 0.27 for b in buckets}},
    ])
    v = add_promotion_verdicts(reg, cfg).set_index("experiment")["verdict"]
    assert v["champion"] == "CHAMPION" and v["better"].startswith("PROMOTE") and v["lucky"].startswith("reject")
    assert v["biased"].startswith("reject") and "bias" in v["biased"]
