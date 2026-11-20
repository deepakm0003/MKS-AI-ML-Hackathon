# Celeris Demand Intelligence Control Tower

Demand forecasting & planning control tower for Celeris Automobili Industrial
(MKS AI/ML Hackathon, Phase 2): 598 SKUs x 6 regions, history 2019-01 → 2026-10,
forecast 2026-11 → 2028-05.

## Setup

Python 3.11. From this folder (PowerShell):

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1
```

```powershell
pip install -r requirements.txt
```

## Run

One command rebuilds every output from `data/raw/`:

```powershell
python run_pipeline.py
```

Run one stage only with `--stage clean|anomalies|drivers|backtest` (the backtest takes ~1 hour). Run the tests afterwards:

```powershell
python -m pytest -q
```

## Project layout

| Path | What |
|---|---|
| `data/raw/` | The 7 files exactly as downloaded (never modified) |
| `data/processed/` | Clean tables (parquet) read by the models and dashboard |
| `outputs/quality/dq_report.json` | Machine-readable data-quality report (counts by file / category / issue, before-after profiles) |
| `outputs/quality/dq_issue_log.csv` | One row per correction: file, row, field, original → corrected, action, rule |
| `src/celeris/` | Pipeline code |
| `tests/` | Unit tests (parsers) + invariant tests on the cleaned outputs |

## Stage 1 — Cleaning: decisions and why

Every rule below is applied in code (`src/celeris/`) and every affected row is in the issue log.

| Problem found | Rows | Decision | Why |
|---|---:|---|---|
| ~30 date formats (`2019/01`, `01-2019`, `Jan 2019`…) | 9,821 | Parse to `YYYY-MM` | Date is authoritative (rule 1) |
| Year typo `2062-xx` | 30 | Take year from `Year` column | Digit swap of 2026; month and Year agree |
| `Year`/`Month` disagree with `Date` | 246 | Rebuild from `Date` | The wrong `Month` always equals the load month |
| Same row loaded twice / reloaded `Record_ID` | 2,946 / 736 | Keep latest `Load_Timestamp` | Rule 2 |
| SKU ID formats (`ptc_9`, `PTC009`) | 3,683 | Normalise to `FAM-NNN` | 2,659 raw spellings → 598 SKUs, all in master |
| Region / channel spellings (`APAC`, `ME&A`, `T1 Distributor`) | 5,912 / 3,683 | Map to canonical labels | — |
| Customer typos (`Orion Drivline`, `Apex Tier One Inc.`) | 2,455 | Fuzzy match to the 12 customers in `test.csv` | 184 raw spellings → 12 |
| Missing family / description | 1,228 / 982 | Fill from master | Fixed per SKU |
| Missing region | 942 | Infer: the only region where that SKU is sold to that customer with no row that month | Unique in 100% of cases |
| Missing units | 3,164 | Recover as revenue ÷ list price | Revenue survives where units are blank |
| Negative units | 491 | Flip sign | Revenue is negative too and \|units\| matches the series level |
| Units ×10 / ×100 | 368 | Units = revenue ÷ price | Revenue gives the true value away |
| **Units booked in packs of 10** (India × Aftermarket, Jul–Dec 2021) | 455 | Units and revenue ×10 | Whole segment at exactly 1/10 of normal, no event explains it; stockout file confirms |
| Price ×100 / ×10 (cents, decimal slips) | 614 / 385 | Set to list price | Price is per SKU, same in all regions, changes 1 Jan |
| **Europe prices booked in EUR** (0.89× list) | 498 | Set to USD list price | Currency error, Europe only |
| Price 0 with units > 0 | 295 | Set to list price | — |
| Revenue ×10 | 425 | Recompute | Units match series level, so revenue is the wrong field |
| 6% surcharge Jul–Dec 2022 | — | Kept in expected price | From the events calendar: real, not an error |
| Macro: Auto production YoY stored as fraction in 2019 | 12 | ×100 | `-0.015` → `-1.5 %` |
| Macro: PMI `4.79` | 1 | ×10 | Decimal shift |
| Macro: duplicate 2022-06 | 1 | Keep the row consistent with neighbours | — |
| Master: one Precision Machined SKU in the wrong BU | 1 | Majority BU of the family | Each family belongs to one BU |
| Master: BSS-018 sold from 2025-02 but launch date 2025-06 | 16 | Flag, keep sales | Master is wrong, not the sales |
| Missing rows inside a series | 972 | Flag as gap; **not** zero | Rule 3 |
| Test rows after EOL | 156 | Forecast 0 | Rule 5 |

**Independent validation:** after cleaning, `Units_Sold` equals the stockout file's
`Shipped_Units` on **5,803 / 5,803** overlapping rows (with only labels and keys fixed: ~93%).

Outputs: `sales_clean.parquet` (244,566 rows, one per Date-SKU-Region) and
`panel.parquet` (full monthly grid with a status per cell: `observed`,
`missing_row`, `missing_value`, `not_active`).

## Stage 2 — Anomalies and unconstrained demand

The forecast must be **unconstrained demand** (what customers asked for), so shipped
units are converted into demand before any model sees them
(`src/celeris/anomalies.py`, output `data/processed/demand.parquet`).

| Step | Rows | Rule |
|---|---:|---|
| Listed stockout months | 5,005 | Demand = `Requested_Units` (also fills 25 months with no sales row) |
| Month after a backorder | 1,048 | Demand = shipped − units carried in from last month (shipments there run ~30% high) |
| Chip-shortage months not in the stockout file (Electrical Assemblies, 2021-03 → 2022-09) | 2,564 | Demand = shipped × uplift. The listed rows are the worst-hit, so their ratio (1.57×) would overstate the rest; the level is calibrated by **difference-in-differences** against the unconstrained families (1.37×), keeping the listed rows' month-to-month profile |
| Unlisted stockouts elsewhere | 0 | **Tested, not assumed:** the "partial shipment then catch-up" signature (2,112 months) is *less* common than its noise mirror (2,545), so there is no evidence to adjust |

Every unusual point goes into **`outputs/anomalies/anomaly_register.csv`** with type,
category, detection method, reason, action and confidence:

| Category | Types | Action |
|---|---|---|
| `data_error` | sign, ×10/×100, packs-of-10, blank units | Corrected in stage 1 |
| `stockout` | listed, backorder catch-up, allocation | Demand recovered |
| `real_event` | COVID, strike, price-announcement pull-forward | Kept in history, excluded from model target |
| `real_event` | permanent step (Helios second Indian line) | Kept **as the new level** and used for training |
| `spike` | 246 one-off orders (robust z > 5, > 3× typical order, revenue reconciles) | Kept in history, excluded from model target |
| `gap` | missing months | Excluded from target, normal level used for lags |
| `unknown` | 225 unexplained drops | Flagged for planners |

**Only events with a measured impact are excluded.** The stage runs twice: pass 1
measures every candidate event, pass 2 keeps out of the model target only those that
were material or weak (COVID ×5, Nexon strike, the 2022 price announcement). The Red Sea
disruption showed no effect, so its months stay in. Open-ended events are permanent
changes, never outliers.

For modelling, `Train_Weight` = 0 on excluded months (7.5% of cells) and `Demand_Model`
fills them with the mean of the **previous** 12 usable months — a causal fill, so a
backtest never sees the future through its lag features.

### Which events actually moved demand — `outputs/anomalies/event_impact.csv`

Baseline depends on the event: holidays vs adjacent months (pooled across years),
long events vs 12 months before/after, price announcements vs the same seasonal ratio in
other years, others vs the same months a year before and after.

| Finding | Effect |
|---|---|
| COVID lockdowns | −35% (APAC) to −76% (India), all material |
| Nexon strike, Europe Oct–Nov 2023 | −81% for that customer |
| Chip shortage, Electrical Assemblies | material: shipped 31% below recovered demand |
| Europe August shutdown | −57% every year |
| North America July retooling | −40% every year |
| Lunar New Year (APAC) | −25% to −43% in the month that holds it (moves Jan ↔ Feb) |
| Ramadan (MEA) | about −14%, moves earlier each year |
| 9% price rise announced Nov 2022 | early buying +10% in Nov–Dec, **payback −17% in Jan–Feb 2023 (z = −5.1)** |
| Helios second Indian line (Sep 2025) | +21%; Helios's share of India steps up 20% (t = 4.8), permanent |
| Annual 1-January price rises (not announced in advance) | **no measurable effect** (any year) |
| Trade fair, rebrand, CRM upgrade, new director, dealer conference, Red Sea | **no measurable effect** |

### Structural changes — `outputs/anomalies/structural_register.csv`

* **39 ordering-cycle changes** (18 monthly → every 2 months, 18 quarterly → monthly, 3 monthly → quarterly)
* **23 customer switches** on an SKU-region (the account moved to another customer)
* **0 lost accounts** without replacement; 25 series ended exactly at their EOL
* **1 level shift** (Helios India, matches EV-052)
* **Master vs transactions:** BSS-018 sold from 2025-02 but master says launch 2025-06;
  3 planned launches with no history (PMP-020, PTC-029, THM-012 → forecast from predecessors)

`data/processed/series_profile.parquet` holds per series: ordering cycle (2,455 monthly,
369 every 2 months, 242 quarterly), months since last order, ADI/CV² demand class
(2,230 smooth, 769 intermittent, 69 erratic, 15 lumpy).

## Stage 3 — Demand drivers, features and backtest

### Which indicator leads which family — `outputs/drivers/`

Family demand growth (3-month total vs a year earlier) against each indicator shifted
0–12 months ahead, post-COVID (2021-01 → 2026-10):

| Family | Leading indicator | Lead | r |
|---|---|---:|---:|
| Brake & Safety | Auto production YoY | 3 m | 0.72 |
| Chassis & Structural | Auto production YoY | 4 m | 0.83 |
| Thermal Management | Auto production YoY | 4 m | 0.76 |
| Electrical Assemblies | New vehicle orders | 3 m | 0.88 |
| Hydraulic Systems | New vehicle orders | 4 m | 0.86 |
| Powertrain Components | New vehicle orders | 4 m | 0.82 |
| Precision Machined | New vehicle orders | 4 m | 0.75 |

Two groups: **vehicle-build families** follow auto production, **industrial families**
follow new orders (and PMI at 0–2 months). **Is the lag stable?** Splitting the period in
two halves, 12 indicator–family links keep the same sign, a lag within ±2 months and
|r| ≥ 0.3 in both — including every link in the table above (`lag_stability.csv`).

**EV shift:** EV parts went from 0% to 9.8% of demand and ICE parts from 24% to 13%
(2019 → 2026); EV share tracks the EV adoption index (r = 0.95, +0.27 share-points per
index point) — but it has **flattened at ~9.8% since 2025** while the index keeps rising.

### Features — `src/celeris/features.py`

Direct multi-horizon design: one row = (series, origin month, horizon 1–19). 87
features, all computed from data up to the origin (a test scrambles every later month
and checks that no feature changes): lags 1–12, rolling means/volatility, trend,
non-zero share, **ordering cycle and phase** (is the target month an order month?),
**SKU-level seasonality** (same month 1–3 years back — demand correlates at lag 12, not
lag 1), family×region seasonal index, holidays by kind (Lunar New Year, Ramadan, summer
shutdowns) in the target month, scheduled customer shutdowns, lifecycle (months since
launch / to EOL), the leading indicators at their lead and their change since the
origin, and categorical family / region / channel / customer / powertrain / size.

### Rolling-origin backtest — `outputs/backtest/`

Cutoffs 2023-10, 2024-04, 2024-10, 2025-03; each forecasts the next 19 months from data
up to the cutoff only; 224,797 SKU-region-months scored against recovered demand.

| Model | WAPE | Bias |
|---|---:|---:|
| Moving average (12 m) | 0.499 | −3.2% |
| Seasonal moving average (family×region index) | 0.492 | −2.9% |
| TSB (intermittent demand) | 0.492 | −5.8% |
| Cycle naive (same phase, last cycle) | 0.437 | +2.7% |
| Seasonal naive (same month last year) | 0.376 | −3.5% |
| LightGBM, L1 loss | 0.283 | −6.5% |
| **LightGBM global model, Tweedie loss** | **0.277** | −4.0% |

* **26% lower error than the best baseline**, consistent in all 4 cutoffs (0.268–0.289),
  all 7 families and all 6 regions; MEA is hardest (0.363, the youngest region).
* At planning level the error is small: **6.7%** WAPE by family-month, **4.8%** for the
  company total per month (seasonal naive: 9.7% / 7.5%).
* Open issue for stage 4: a steady **−3.5% under-forecast** even on clean months.
