"""Run backtest experiments under identical conditions and update the registry.

    python run_backtest.py --list
    python run_backtest.py --experiment champion
    python run_backtest.py --experiment cross_series no_macro
    python evaluate.py                      # leaderboard
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from celeris.experiments import FrameStore, load_config, run  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", nargs="*", default=["champion"])
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.list:
        print("champion:", cfg["champion"]["description"])
        for k, v in cfg["experiments"].items():
            print(f"{k}: {v['description']}")
        sys.exit()
    store = FrameStore()
    for name in a.experiment:
        print(f"== experiment {name}", flush=True)
        m = run(name, store)
        o = m["overall"]
        print(f"== {name}: WAPE {o['WAPE']:.4f}  bias {o['Bias']:+.4f}  MAE {o['MAE']:.2f}  "
              f"RMSE {o['RMSE']:.2f}  ({m['minutes']} min)", flush=True)
