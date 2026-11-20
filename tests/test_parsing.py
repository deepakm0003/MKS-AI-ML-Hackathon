import numpy as np
import pytest

from celeris.parsing import build_name_matcher, normalise_sku, parse_month, parse_number


@pytest.mark.parametrize("raw,expected", [
    ("2019-01", "2019-01"), ("2019/01", "2019-01"), ("2019-01-15", "2019-01"),
    ("01-2019", "2019-01"), ("01/2019", "2019-01"), ("Jan 2019", "2019-01"),
    ("Jan-2019", "2019-01"), ("Sep 2026", "2026-09"), (" 2024-12 ", "2024-12"),
    ("2019-13", None), ("garbage", None), (None, None), (np.nan, None),
])
def test_parse_month(raw, expected):
    assert parse_month(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("PTC-009", "PTC-009"), ("ptc-009", "PTC-009"), (" PTC-009", "PTC-009"),
    ("PTC_009", "PTC-009"), ("PTC009", "PTC-009"), ("PTC-9", "PTC-009"), ("PTC-09", "PTC-009"),
    ("XX-1", None), (None, None),
])
def test_normalise_sku(raw, expected):
    assert normalise_sku(raw) == expected


def test_parse_number():
    assert parse_number("9,600") == 9600
    assert parse_number("-35") == -35
    assert np.isnan(parse_number("-"))
    assert np.isnan(parse_number(None))
    assert np.isnan(parse_number(""))


def test_customer_matcher():
    m = build_name_matcher(["Orion Driveline", "Quantum Drive Systems", "Apex Tier One"])
    assert m("Orion Drivline") == "Orion Driveline"
    assert m("QUANTUM  DRIVE SYSTEMS") == "Quantum Drive Systems"
    assert m("Apex Tier One Inc.") == "Apex Tier One"
    assert m("Apextier One") == "Apex Tier One"
    assert m("Totally Different Co") is None
