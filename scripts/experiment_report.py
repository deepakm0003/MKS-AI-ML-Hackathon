"""Ranked experiment report: champion vs every challenger.

    python scripts/experiment_report.py   -> artifacts/reports/experiment_report.md
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
reg = pd.read_csv(ART / "registry" / "registry.csv")
champ = reg[reg["experiment"] == "champion"].iloc[0]
m = lambda n: json.loads((ART / "experiments" / n / "metrics.json").read_text(encoding="utf-8"))
cm = m("champion")

lines = ["# Experiment report — champion vs challengers", "",
         "All runs: same cleaned demand panel, 6 rolling cutoffs (2022-10 → 2025-03), 19-month horizon.", "",
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
out = ART / "reports" / "experiment_report.md"
out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines[:5 + len(reg) + 1]))
