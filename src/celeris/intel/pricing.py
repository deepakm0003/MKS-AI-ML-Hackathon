"""Revenue: price book and revenue forecast.

Business rule 4: prices are per SKU, the same in every region, and change on 1 January
(surcharges aside). The events calendar announces the 1-January list-price rises for the
forecast window (2027 about +4.5%, 2028 about +4.0%). Price book:

  * 2026 list price per SKU = its (single) 2026 price in the cleaned history;
  * SKUs without a 2026 price: last known list price rolled forward with the announced rises,
    else the predecessor's (Replaces_SKU) 2026 price for launches, else the median 2026 price of
    the same family and size class;
  * 2027 / 2028 = previous year x (1 + announced rise).

`price_rise_check` back-tests the rule: announced vs realised median rise for every past year.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

KEY = ["SKU_ID", "Region"]


def announced_rises(events: pd.DataFrame) -> dict[int, float]:
    """{year: fractional list-price rise} from 'Annual list-price increase of about X%' events."""
    out = {}
    pc = events[events["Event_Type"].astype(str).str.contains("Price Change", case=False)]
    for _, e in pc.iterrows():
        m = re.search(r"list-price increase of about ([\d.]+)%", str(e["Description"]))
        if m:
            out[int(str(e["Start_Date"])[:4])] = float(m.group(1)) / 100
    return dict(sorted(out.items()))


def yearly_list_prices(demand: pd.DataFrame) -> pd.DataFrame:
    """Modal positive price per SKU and year (SKU x year)."""
    d = demand[demand["Unit_Price_USD"].gt(0)]
    return d.groupby(["SKU_ID", "Year"])["Unit_Price_USD"].agg(lambda s: s.mode().iloc[0]).unstack()


def price_rise_check(demand: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    p = yearly_list_prices(demand)
    rises = announced_rises(events)
    rows = []
    for y in p.columns[1:]:
        r = (p[y] / p[y - 1] - 1).dropna()
        rows.append({"Year": int(y), "Announced_rise": rises.get(int(y)), "Realised_median_rise": round(float(r.median()), 4),
                     "Realised_IQR": f"{r.quantile(0.25):.3f}-{r.quantile(0.75):.3f}", "SKUs": int(len(r))})
    return pd.DataFrame(rows)


def price_book(demand: pd.DataFrame, sku: pd.DataFrame, events: pd.DataFrame,
               years=(2027, 2028), base_year: int = 2026) -> pd.DataFrame:
    p = yearly_list_prices(demand)
    rises = announced_rises(events)
    m = sku.set_index("SKU_ID")
    base = pd.Series(np.nan, index=m.index, name=base_year)
    source = pd.Series("", index=m.index)
    have = p[base_year].dropna() if base_year in p else pd.Series(dtype=float)
    base[have.index.intersection(base.index)] = have
    source[have.index.intersection(base.index)] = f"{base_year} list price"
    for s in base.index[base.isna()]:
        hist = p.loc[s].dropna() if s in p.index else pd.Series(dtype=float)
        if len(hist):                                            # roll the last known price forward
            y0, v = int(hist.index[-1]), float(hist.iloc[-1])
            for y in range(y0 + 1, base_year + 1):
                v *= 1 + rises.get(y, 0.0)
            base[s], source[s] = v, f"{y0} price rolled forward with announced rises"
    for s in base.index[base.isna()]:
        pred = m.at[s, "Replaces_SKU"]
        if pd.notna(pred) and pd.notna(base.get(pred)):
            base[s], source[s] = base[pred], f"predecessor {pred} price"
    peer = pd.DataFrame({"b": base, "fam": m["Product_Family"], "size": m["Size_Class"]})
    med = peer.groupby(["fam", "size"])["b"].transform("median")
    fill = base.isna() & med.notna()
    base[fill], source[fill] = med[fill], "family x size-class median"
    book = pd.DataFrame({f"Price_{base_year}": base.round(2), "Price_source": source})
    v = base.copy()
    for y in years:
        v = v * (1 + rises.get(y, 0.0))
        book[f"Price_{y}"] = v.round(2)
    book.index.name = "SKU_ID"
    return book.reset_index()


def revenue_forecast(fc: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    """Adds Unit_Price and Revenue / Revenue_P10 / Revenue_P50 / Revenue_P90 to forecast rows."""
    b = book.set_index("SKU_ID")
    yr = fc["Date"].str[:4].astype(int)
    price = np.full(len(fc), np.nan)
    for y in yr.unique():
        col = f"Price_{y}"
        sel = (yr == y).to_numpy()
        price[sel] = fc.loc[sel, "SKU_ID"].map(b[col]).to_numpy()
    out = fc.copy()
    out["Unit_Price"] = price
    for c, src in [("Revenue", "Forecast"), ("Revenue_P10", "P10"), ("Revenue_P50", "P50"), ("Revenue_P90", "P90")]:
        out[c] = out[src] * out["Unit_Price"]
    return out


def history_revenue(demand: pd.DataFrame) -> pd.DataFrame:
    """Monthly shipped revenue (cleaned) and unconstrained revenue (recovered demand x price)."""
    d = demand.copy()
    lp = yearly_list_prices(d).stack().rename("lp")
    price = d["Unit_Price_USD"].where(d["Unit_Price_USD"].gt(0))
    price = price.fillna(pd.Series(pd.MultiIndex.from_arrays([d["SKU_ID"], d["Year"]]).map(lp), index=d.index))
    d["Revenue_shipped"] = d["Revenue_USD"].fillna(d["Units_Sold"] * price)
    d["Revenue_unconstrained"] = d["Demand"] * price
    return d
