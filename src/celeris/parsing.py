"""Small, pure parsing helpers (unit-tested in tests/test_parsing.py)."""
from __future__ import annotations

import difflib
import re

import numpy as np
import pandas as pd

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_month(value) -> str | None:
    """Parse any of the date spellings in the ERP extract to 'YYYY-MM'.

    Handles 2019-01, 2019/01, 2019-01-15, 01-2019, 01/2019, Jan 2019, Jan-2019.
    Returns None if the value cannot be parsed.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip()
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?", s)
    if m:
        y, mo = int(m[1]), int(m[2])
    else:
        m = re.fullmatch(r"(\d{1,2})[-/](\d{4})", s)
        if m:
            y, mo = int(m[2]), int(m[1])
        else:
            m = re.fullmatch(r"([A-Za-z]{3})[A-Za-z]*[ \-](\d{4})", s)
            if not m or m[1].lower() not in _MONTHS:
                return None
            y, mo = int(m[2]), _MONTHS[m[1].lower()]
    if not 1 <= mo <= 12:
        return None
    return f"{y:04d}-{mo:02d}"


def normalise_sku(value) -> str | None:
    """' ptc_9' / 'PTC009' / 'ptc-009' -> 'PTC-009'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip().upper().replace("_", "-").replace(" ", "")
    m = re.fullmatch(r"([A-Z]{3})-?(\d{1,3})", s)
    return f"{m[1]}-{int(m[2]):03d}" if m else None


def parse_number(value) -> float:
    """'9,600' -> 9600.0; '-' / '' / None -> NaN."""
    if value is None:
        return np.nan
    s = str(value).strip().replace(",", "")
    if s in {"", "-", "nan", "NaN", "None"}:
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def map_alias(series: pd.Series, aliases: dict) -> pd.Series:
    key = series.astype("string").str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    return key.map(aliases)


def _name_key(s: str) -> str:
    s = re.sub(r"\binc\.?$", "", s.strip(), flags=re.I)
    return re.sub(r"[^a-z]", "", s.lower())


def build_name_matcher(canonical: list[str], cutoff: float = 0.8):
    """Return a function mapping a messy customer name to its canonical spelling.

    Matching is on letters only (case, spaces, punctuation and an 'Inc.' suffix
    are ignored) and tolerates the 1-character typos found in the extract.
    """
    keys = {_name_key(c): c for c in canonical}
    cache: dict[str, str | None] = {}

    def match(name) -> str | None:
        if name is None or (isinstance(name, float) and np.isnan(name)):
            return None
        if name in cache:
            return cache[name]
        k = _name_key(str(name))
        if k in keys:
            res = keys[k]
        else:
            best = difflib.get_close_matches(k, list(keys), n=1, cutoff=cutoff)
            res = keys[best[0]] if best else None
        cache[name] = res
        return res

    return match
