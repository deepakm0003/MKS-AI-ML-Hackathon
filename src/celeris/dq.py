"""Data-quality issue log.

Every correction the pipeline makes is recorded as one row in an issue log so
that the dashboard (Data Health view) and the jury can trace each change back
to the raw value, the rule that fired and the action taken.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd

ISSUE_COLUMNS = [
    "file", "row_ref", "date", "sku_id", "region", "issue_type", "category",
    "field", "original", "corrected", "action", "rule",
]

# category: what kind of problem this is, used for the Data Health roll-up
#   error      -> data-entry / system error, fixed
#   gap        -> missing value or row, imputed or flagged
#   reference  -> reference/master data contradicts transactions
#   info       -> noted, no change


@dataclass
class DQLog:
    frames: list = field(default_factory=list)
    profiles: dict = field(default_factory=dict)

    def add(self, df: pd.DataFrame, *, file: str, issue_type: str, category: str,
            field_name: str, action: str, rule: str, original=None, corrected=None,
            row_ref: str | None = None) -> int:
        """Log one issue for every row in ``df``.

        ``original`` / ``corrected`` may be column names in ``df`` or scalars.
        """
        if df is None or len(df) == 0:
            return 0

        def pick(v, default=None):
            if v is None:
                return default
            if isinstance(v, str) and v in df.columns:
                return df[v].astype(str).values
            return v

        out = pd.DataFrame({
            "file": file,
            "row_ref": pick(row_ref, "") if row_ref else (df["Record_ID"].values if "Record_ID" in df else df.index.astype(str)),
            "date": df["Date"].astype(str).values if "Date" in df else "",
            "sku_id": df["SKU_ID"].astype(str).values if "SKU_ID" in df else "",
            "region": df["Region"].astype(str).values if "Region" in df else "",
            "issue_type": issue_type,
            "category": category,
            "field": field_name,
            "original": pick(original, ""),
            "corrected": pick(corrected, ""),
            "action": action,
            "rule": rule,
        })
        self.frames.append(out)
        return len(out)

    def profile(self, name: str, df: pd.DataFrame, stage: str) -> None:
        """Store a before/after profile of a table."""
        self.profiles.setdefault(name, {})[stage] = {
            "rows": int(len(df)),
            "columns": int(df.shape[1]),
            "null_cells": int(df.isna().sum().sum()),
            "nulls_by_column": {c: int(v) for c, v in df.isna().sum().items() if v},
        }

    def table(self) -> pd.DataFrame:
        if not self.frames:
            return pd.DataFrame(columns=ISSUE_COLUMNS)
        return pd.concat(self.frames, ignore_index=True)[ISSUE_COLUMNS]

    def summary(self) -> dict:
        t = self.table()
        by_type = (t.groupby(["file", "category", "issue_type", "action"]).size()
                     .rename("rows").reset_index().sort_values("rows", ascending=False))
        return {
            "total_issues": int(len(t)),
            "issues_by_file": t.groupby("file").size().astype(int).to_dict(),
            "issues_by_category": t.groupby("category").size().astype(int).to_dict(),
            "issues": by_type.to_dict(orient="records"),
            "profiles": self.profiles,
        }

    def write(self, out_dir) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.table().to_csv(out_dir / "dq_issue_log.csv", index=False)
        with open(out_dir / "dq_report.json", "w", encoding="utf-8") as f:
            json.dump(self.summary(), f, indent=2, default=str)
