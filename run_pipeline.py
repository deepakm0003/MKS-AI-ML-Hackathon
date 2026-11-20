"""One command to rebuild every output from data/raw.

    python run_pipeline.py            # all stages
    python run_pipeline.py --stage clean
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from celeris.pipeline import run_anomalies, run_cleaning  # noqa: E402

STAGES = {"clean": run_cleaning, "anomalies": run_anomalies}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["all", *STAGES], default="all")
    args = ap.parse_args()
    for name, fn in STAGES.items():
        if args.stage in ("all", name):
            print(f"== stage: {name}")
            fn()
