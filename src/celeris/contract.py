"""Load and enforce the frozen data contract (contracts/data_contract.yaml)."""
from __future__ import annotations

import json
import re
from functools import lru_cache

import pandas as pd
import yaml

from .config import ROOT

CONTRACT = ROOT / "contracts" / "data_contract.yaml"
MONTH = re.compile(r"^\d{4}-\d{2}$")


@lru_cache(maxsize=1)
def load_contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def dataset_path(name: str):
    return ROOT / load_contract()["datasets"][name]["path"]


def read_dataset(name: str):
    spec = load_contract()["datasets"][name]
    p = ROOT / spec["path"]
    if spec.get("format") == "json":
        return json.loads(p.read_text(encoding="utf-8"))
    return pd.read_csv(p, keep_default_na=True, low_memory=False)


def _type_ok(s: pd.Series, t: str) -> bool:
    v = s.dropna()
    if v.empty:
        return True
    if t == "string":
        return s.dtype == object or pd.api.types.is_string_dtype(s)
    if t == "month":
        return v.astype(str).str.match(MONTH).all()
    if t == "int":
        return pd.api.types.is_integer_dtype(s) or (pd.api.types.is_float_dtype(s) and (v % 1 == 0).all())
    if t == "float":
        return pd.api.types.is_numeric_dtype(s)
    if t == "bool":
        return pd.api.types.is_bool_dtype(s) or set(v.astype(str)) <= {"True", "False"}
    return True


def check_dataset(name: str) -> list[str]:
    """Problems found in one dataset ([] = conforms). Raises FileNotFoundError if absent."""
    spec = load_contract()["datasets"][name]
    p = ROOT / spec["path"]
    if not p.exists():
        raise FileNotFoundError(p)
    problems = []
    if spec.get("format") == "json":
        d = json.loads(p.read_text(encoding="utf-8"))
        problems += [f"missing key {k}" for k in spec.get("required_keys", []) if k not in d]
        return problems
    df = read_dataset(name)
    for col, t in (spec.get("columns") or {}).items():
        if col not in df.columns:
            problems.append(f"missing column {col}")
        elif not _type_ok(df[col], t):
            problems.append(f"column {col} is not {t} (dtype {df[col].dtype})")
    pk = spec.get("primary_key")
    if pk and set(pk) <= set(df.columns) and df.duplicated(pk).any():
        problems.append(f"primary key {pk} not unique ({int(df.duplicated(pk).sum())} duplicates)")
    return problems
