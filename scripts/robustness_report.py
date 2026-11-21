"""Phase D (fast part) on a model's 6-cutoff backtest (default: the frozen final model) - no retraining.

    python scripts/robustness_report.py [experiment]    # default: the frozen final model
      -> artifacts/reports/post_corrections.csv
         artifacts/reports/interval_calibration.csv, interval_calibration_segments.csv
         artifacts/reports/horizon_reliability.csv
         artifacts/reports/series_reliability.csv, reliability_tiers.csv
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from celeris.robustness import (horizon_curve, interval_calibration, post_corrections,  # noqa: E402
                                series_reliability)

OUT = ROOT / "artifacts" / "reports"
man = ROOT / "outputs" / "final" / "manifest.json"
name = sys.argv[1] if len(sys.argv) > 1 else (json.loads(man.read_text(encoding="utf-8"))["selected_model"]
                                              if man.exists() else "champion")
print("model:", name)
pred = pd.read_parquet(ROOT / "artifacts" / "experiments" / name / "predictions.parquet")

pc = post_corrections(pred)
pc.round(4).to_csv(OUT / "post_corrections.csv", index=False)
print("post-hoc corrections (walk-forward WAPE):\n", pc.round(4).to_string(index=False), "\n")

summ, seg = interval_calibration(pred)
summ.to_csv(OUT / "interval_calibration.csv", index=False)
seg.to_csv(OUT / "interval_calibration_segments.csv", index=False)
print("interval calibration (leave-one-cutoff-out):\n", summ.to_string(index=False), "\n")

hc = horizon_curve(pred)
hc.to_csv(OUT / "horizon_reliability.csv", index=False)
print("WAPE by horizon month:\n", hc.to_string(index=False), "\n")

s, tiers = series_reliability(pred)
s.to_csv(OUT / "series_reliability.csv", index=False)
tiers.to_csv(OUT / "reliability_tiers.csv", index=False)
print("series reliability tiers:\n", tiers.to_string(index=False))
