"""Freeze the champion: everything needed to reproduce the 0.277-WAPE model.

    python scripts/freeze_champion.py   -> artifacts/champion/manifest.json (+ copies of
                                           backtest predictions and the model file)
Large files (model, predictions) are published as a GitHub Release, not committed.
"""
import hashlib
import json
import platform
import shutil
import sys
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from celeris.experiments import resolve  # noqa: E402

out = ROOT / "artifacts" / "champion"
out.mkdir(parents=True, exist_ok=True)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


audit = json.loads((ROOT / "artifacts/reports/champion_audit.json").read_text(encoding="utf-8"))
cfg = yaml.safe_load((ROOT / "config/experiments.yaml").read_text(encoding="utf-8"))
m4 = pd.read_csv(ROOT / "outputs/backtest/metrics_by_cutoff.csv", index_col=0)

manifest = {
    "champion": "global LightGBM, Tweedie, 87 features",
    "frozen_on": "2026-11-20",
    "spec": resolve("champion"),
    "evaluation": cfg["evaluation"],
    "features": audit["features"],
    "training_rows": audit["training_rows"],
    "preprocessing": {
        "cleaning": "README.md stage 1 table; every correction in outputs/quality/dq_issue_log.csv",
        "demand_recovery": "README.md stage 2; outputs/anomalies/findings.json",
        "target": "Demand (unconstrained); Train_Weight=0 rows excluded; lags use causal Demand_Model",
    },
    "original_backtest_4_cutoffs": {
        "WAPE": 0.2766, "Bias": -0.040,
        "by_cutoff": m4["lgb_tweedie_WAPE"].round(4).to_dict(),
    },
    "reproducibility": {
        "seed": 7, "lightgbm_deterministic": True, "force_row_wise": True, "num_threads": 16,
        "python": platform.python_version(),
        "libraries": {p: version(p) for p in ["pandas", "numpy", "lightgbm", "scikit-learn", "pyarrow"]},
        "raw_data_sha256_16": {p.name: sha(p) for p in sorted((ROOT / "data/raw").glob("*.csv"))},
        "processed_demand_sha256_16": sha(ROOT / "data/processed/demand.parquet"),
    },
    "artifacts": {
        "model": "artifacts/champion/lgb_global_tweedie.txt (release asset)",
        "backtest_predictions_4_cutoffs": "artifacts/champion/backtest_predictions_4cutoffs.parquet (release asset)",
        "backtest_predictions_6_cutoffs": "artifacts/experiments/champion/predictions.parquet",
    },
}
shutil.copy(ROOT / "outputs/models/lgb_global_tweedie.txt", out / "lgb_global_tweedie.txt")
shutil.copy(ROOT / "outputs/backtest/backtest_predictions.parquet", out / "backtest_predictions_4cutoffs.parquet")
(out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
print(json.dumps(manifest["reproducibility"], indent=1))
