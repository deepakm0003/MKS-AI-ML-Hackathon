"""Ranked experiment report: champion vs every challenger.

    python scripts/experiment_report.py   -> artifacts/reports/experiment_report.md
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
reg = pd.read_csv(ART / "registry" / "registry.csv")
champ = reg[reg["experiment"] == "champion"].iloc[0]
m = lambda n: json.loads((ART / "experiments" / n / "metrics.json").read_text(encoding="utf-8"))
cm = m("champion")

lines = ["# Experiment report — champion vs challengers", "",
         "All runs: same cleaned demand panel, 6 rolling cutoffs (2022-10 → 2025-03), 19-month horizon.",
         "Minutes are wall-clock (c4 includes ~8 h of laptop sleep; C6, C9, seed_bag and origin_step1 ran "
         "in parallel on the 56-core server, which reproduces the champion exactly).", "",
         "| Rank | Experiment | WAPE | Δ vs champion | Bias | MAE | 1–3 m | 4–6 m | 7–12 m | 13–19 m | "
         "Family-month | Total-month | Cutoffs won | Minutes | Verdict |",
         "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
cut_cols = [c for c in reg.columns if c.startswith("WAPE_20")]
for i, (_, r) in enumerate(reg.sort_values("WAPE").iterrows(), 1):
    won = "—" if r["experiment"] == "champion" else f"{int(sum(r[c] < champ[c] for c in cut_cols))}/{len(cut_cols)}"
    verdict = str(r.get("verdict", "")).split(" | ")[0]
    lines.append(f"| {i} | {r['experiment']} | {r['WAPE']:.4f} | {r['WAPE'] - champ['WAPE']:+.4f} | "
                 f"{100 * r['Bias']:+.1f}% | {r['MAE']:.2f} | {r['WAPE_1-3m']:.3f} | {r['WAPE_4-6m']:.3f} | "
                 f"{r['WAPE_7-12m']:.3f} | {r['WAPE_13-19m']:.3f} | {100 * r['WAPE_family_month']:.1f}% | "
                 f"{100 * r['WAPE_total_month']:.1f}% | {won} | {r['minutes']} | {verdict} |")

lines += ["", "## Where each challenger gains or loses (Δ WAPE vs champion; negative = better)", ""]
segs = {"by_Product_Family": "Family", "by_Region": "Region", "by_Lifecycle": "Lifecycle",
        "by_Demand_Class": "Demand class", "by_Volume_Band": "Volume"}
names = [n for n in reg.sort_values("WAPE")["experiment"] if n != "champion"]
for seg, label in segs.items():
    t = pd.DataFrame({n: {k: m(n)[seg][k]["WAPE"] - v["WAPE"] for k, v in cm[seg].items() if k in m(n)[seg]}
                      for n in names})
    lines += [f"### {label}", "", t.round(4).to_markdown(), ""]
bias = pd.DataFrame({n: {k: v["Bias"] for k, v in m(n)["by_Product_Family"].items()} for n in ["champion"] + names})
lines += ["### Bias by family (the champion's known weakness: vehicle-build families)", "",
          (100 * bias).round(1).to_markdown(), ""]
# ---- aggregate accuracy (what planners see): family-month and company-month error
agg = reg.set_index("experiment")[["WAPE", "WAPE_family_month", "WAPE_total_month"]].sort_values("WAPE_total_month")
lines += ["## Aggregate accuracy (family-month and company-month WAPE)", "",
          "Series-level WAPE decides promotion; the aggregate columns show which models planners would "
          "trust for family and company totals.", "", (100 * agg).round(2).to_markdown(), ""]

# ---- Phase D robustness tables (if generated)
R = ART / "reports"
extra = [("cleaning_sensitivity.csv", "Cleaning sensitivity (3 cutoffs, common yardstick of untouched months)",
          ["Variant", "Description", "rows", "WAPE", "Bias", "WAPE_vs_baseline"]),
         ("cleaning_sensitivity_forecast.csv", "Cleaning sensitivity - final 19-month forecast",
          ["Variant", "Total_19m", "Total_19m_vs_base_pct"]),
         ("post_corrections.csv", "Post-hoc corrections (walk-forward WAPE)", None),
         ("interval_calibration.csv", "Interval calibration (leave-one-cutoff-out)", None),
         ("reliability_tiers.csv", "Series reliability tiers (champion)", None)]
for f, title, cols in extra:
    if (R / f).exists():
        t = pd.read_csv(R / f)
        t = t[[c for c in (cols or t.columns) if c in t.columns]]
        lines += [f"## {title}", "", t.round(4).to_markdown(index=False), ""]
if (R / "recommendation.md").exists():
    lines += [(R / "recommendation.md").read_text(encoding="utf-8")]

out = ART / "reports" / "experiment_report.md"
out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines[:5 + len(reg) + 1]))
