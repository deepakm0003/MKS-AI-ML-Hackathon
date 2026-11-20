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

Run the tests afterwards:

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
