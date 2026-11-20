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

## Stage 4 — Final model and the 19-month forecast

`python run_pipeline.py --stage forecast` → `outputs/forecast/submission.csv`
(58,219 rows, test.csv order, non-negative integers, no blanks).

### Model choices — each one tested in the rolling backtest

| Option tested | Result | Decision |
|---|---|---|
| Global LightGBM, Tweedie loss on a scale-free target | WAPE 0.277 (best) | **Final model** |
| Blend with L1 model / seasonal naive (weights chosen leave-one-cutoff-out) | No gain on 3 of 4 held-out cutoffs, worse on the 4th | Rejected |
| Bigger trees, Tweedie power 1.4, recency weighting, faster learning rate | Equal or worse on both test cutoffs | Rejected |
| Macro top-down alignment (family growth from leading indicators) | Fixes bias in 2024 but over-forecasts 2025–26 (+4–9%) and raises WAPE | Rejected for the point forecast; kept for what-if |
| Fixed bias multiplier | Bias was period-specific (2024 boom: −7%), recent cutoffs unbiased (−0.4%) | Rejected |

Final model: trained on 1.7 M (series, origin, horizon) rows covering all history,
saved in `outputs/models/` with a model card (features, parameters, backtest metrics).

### What the model cannot learn from history — explicit, evidence-based rules

| Situation | Rule | Evidence |
|---|---|---|
| After EOL / before launch (156 test rows) | 0 | Business rule 5 |
| New launches with no history (PMP-020, PTC-029, THM-012) | Predecessor's regional level × ramp-up curve: 16% → 45% → 67% → 72% → 88% … ≥ 100% from month 7 | The 6 past replacements |
| Predecessor while the successor ramps up | 0.59 × its normal level (set, not multiplied — the model already lowers SKUs near EOL) | Same 6 replacements |
| Orion Driveline NA retooling shutdown, Jul–Aug 2027 | × 0.19 | Closest analogue: Nexon strike, −81% |
| Holidays (Lunar New Year and Ramadan move dates) | Learned by the model from holiday-share features | Event-impact analysis |
| 1-January price rises 2027 / 2028 | No adjustment | No measurable effect in any past year |

### Uncertainty and hierarchy

* **P10 / P50 / P90** from the backtest's own errors (quantiles of actual ÷ forecast by
  forecast size and horizon). Held-out check: the P10–P90 band contains **80–83%** of
  actual demand in every cutoff (target 80%).
* **Coherent hierarchy:** SKU-region forecasts add up exactly to customer, channel,
  region, family and company totals (`forecast_hierarchy.csv`).
* **Aggregate bands** need more than row-level noise: a market-wide swing (like the 2024
  upswing) moves every family together, and bands that ignore it held only 37–74% of
  actual company totals in the held-out check. Each level's band therefore combines
  within-period noise with the period-to-period shift, the latter with a small-sample
  t-correction (only 4 backtest periods). Held-out coverage is now **83–87% at every
  level** (`band_coverage.csv`).

### The forecast (2026-11 → 2028-05)

| | Forecast | P10 | P90 |
|---|---:|---:|---:|
| **Company, 19 months** (sum of monthly bands) | **2.84 M units** | 2.75 M | 3.17 M |
| Brake & Safety | 544 k | 508 k | 627 k |
| Precision Machined | 442 k | 413 k | 510 k |
| Chassis & Structural | 439 k | 410 k | 506 k |
| Thermal Management | 429 k | 401 k | 494 k |
| Powertrain | 364 k | 340 k | 420 k |
| Hydraulic | 331 k | 309 k | 381 k |
| Electrical | 287 k | 268 k | 331 k |

* Next 12 months **+6.5%** vs the last 12, carried by the strong Sep–Oct 2026 and a PMI
  rising to 53.
* Second year eases (−3% to −8% vs the same months a year earlier): new vehicle orders
  fall from 107 (mid-2026) to ~99, and the industrial families follow with a 3–4 month lag.
* Bands are skewed upward: in the backtest the model under-forecast more often than it
  over-forecast, so upside risk is larger than downside.

## Forecasting engine — champion, experiments and registry

The model that produced the submission is frozen as the **champion**
(`config/experiments.yaml`, `artifacts/champion/manifest.json`: parameters, the 87 features
by group, cutoffs, seed, deterministic LightGBM settings, library versions and SHA-256
fingerprints of every raw file). Every challenger runs under identical conditions — same
demand panel, 6 rolling cutoffs (2022-10 → 2025-03), 19-month horizon, same metrics — and
is promoted only if it gains ≥ 0.002 WAPE on average, wins ≥ 4 of 6 cutoffs and never
loses more than 0.005 on any cutoff.

```powershell
python run_backtest.py --list
```

```powershell
python run_backtest.py --experiment champion cross_series
```

```powershell
python evaluate.py --segments cross_series
```

Outputs: `artifacts/registry/registry.csv` (leaderboard), `artifacts/experiments/<name>/`
(metrics by cutoff, horizon, family, region, demand class, volume band, lifecycle; spec;
predictions), `artifacts/reports/champion_audit.json` (feature inventory + measured
leakage paths), `artifacts/reports/error_decomposition_<name>.json`.

### Milestone 1 results (6 cutoffs, 19-month horizon)

| Experiment | WAPE | Bias | MAE | 1–3 m | 4–6 m | 7–12 m | 13–19 m | Total-month | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Seasonal naive | 0.388 | | | | | | | | baseline |
| **Champion** | **0.2897** | −3.0% | 13.71 | 0.284 | 0.279 | 0.287 | 0.299 | 5.4% | champion |
| + cross-series market features (53) | 0.2884 | −3.4% | 13.65 | 0.284 | 0.278 | 0.286 | 0.297 | 5.6% | not promoted: +0.0013, wins 5/6 |
| − macro features | 0.3019 | −2.1% | 14.29 | 0.283 | 0.286 | 0.305 | 0.314 | 8.9% | not promoted |

* **Reproducible:** the champion reproduces its original four cutoffs exactly (0.2895 /
  0.2677 / 0.2761 / 0.2735). The two added, older cutoffs are harder (0.328, 0.308), so the
  6-cutoff benchmark (0.290) is stricter than the earlier 0.277.
* **Leakage audit:** all 140 features (87 + 53 cross-series) pass the scramble test; five
  minor paths were measured and are listed with their size in `champion_audit.json`.
* **Macro dependence (robustness risk):** without macro features WAPE rises to 0.302 and
  company-total error from 5.4% to 8.9%, mostly beyond 6 months. The forecast therefore
  leans on the macro file's projections for 2027–28 — they must be stress-tested.
* **Error decomposition (champion):**
  * Error is **not concentrated**: half of it comes from 866 of 3,540 series; the top 20
    series cause 3.2%. There is no small set of SKUs to fix.
  * Getting every series' level exactly right would only lower WAPE from 0.290 to 0.272 —
    **~94% of the error is month-to-month noise**, so remaining gains are small and
    robustness matters more than raw accuracy.
  * **Systematic under-forecast is specific:** the vehicle-build families (Chassis −8.3% in
    6/6 cutoffs, Thermal −5.8%, Brake −5.0%), Middle East & Africa (−6.5%) and **new
    series < 24 months (WAPE 0.391, bias −8.1%)**. Industrial families are unbiased.
