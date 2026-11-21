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

Run one stage only with `--stage clean|anomalies|drivers|backtest|forecast|final|intelligence`
(the backtest takes ~1 hour). `final` selects the model from the experiment registry, freezes
the forecast in `outputs/final/` and validates it; `intelligence` then reads that frozen
forecast. Run the tests afterwards:

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
| `config/experiments.yaml` | Champion spec, every challenger, cutoffs and the six promotion criteria |
| `artifacts/registry/registry.csv` | Leaderboard of every experiment with its promotion verdict |
| `artifacts/reports/` | Experiment report, error decomposition, macro stress, cleaning sensitivity, reliability |
| `outputs/final/` | Frozen backend: submission, forecast, hierarchy, validation report, manifest |
| `contracts/data_contract.yaml` | Every dataset the dashboard may read, with columns and types |
| `api/app.py` | Read-only FastAPI layer over the data contract |
| `tests/` | Parsers, cleaned-output invariants, features, forecast rules, experiments, robustness, contract, API |

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

### The forecast (2026-11 → 2028-05) — frozen final model (`outputs/final/`)

Produced by the promoted model **C9c** (see Phase C below); the stage-4 champion forecast is
kept in `outputs/forecast/` for comparison (company total 2.84 M; C9c is 0.6% lower).

| | Forecast | P10 | P90 |
|---|---:|---:|---:|
| **Company, 19 months** (sum of monthly bands) | **2.82 M units** | 2.66 M | 3.15 M |
| Brake & Safety | 536 k | 486 k | 621 k |
| Precision Machined | 439 k | 398 k | 508 k |
| Chassis & Structural | 433 k | 393 k | 501 k |
| Thermal Management | 428 k | 388 k | 496 k |
| Powertrain | 363 k | 329 k | 420 k |
| Hydraulic | 332 k | 301 k | 384 k |
| Electrical | 286 k | 259 k | 331 k |

* Next 12 months **+6.1%** vs the last 12, carried by the strong Sep–Oct 2026 and a PMI
  rising to 53.
* Second year eases (−4% to −10% vs the same months a year earlier): new vehicle orders
  fall from 107 (mid-2026) to ~99, and the industrial families follow with a 3–4 month lag.
* Aggregate bands are now fitted on 6 backtest cutoffs (including the harder 2022–23
  periods), so the company band is wider and more honest than the earlier 4-cutoff band;
  held-out coverage 82–86% at every level.

## Forecasting engine — champion, experiments and registry

The model that produced the submission is frozen as the **champion**
(`config/experiments.yaml`, `artifacts/champion/manifest.json`: parameters, the 87 features
by group, cutoffs, seed, deterministic LightGBM settings, library versions and SHA-256
fingerprints of every raw file). Every challenger runs under identical conditions — same
demand panel, 6 rolling cutoffs (2022-10 → 2025-03), 19-month horizon, same metrics — and
is promoted only if **all six** criteria hold (`config/experiments.yaml` → `promotion`):

1. mean WAPE gain ≥ 0.002 over the same 6 cutoffs;
2. no horizon bucket (1–3 / 4–6 / 7–12 / 13–19 m) worse by more than 0.003;
3. |bias| not worse by more than 1 point;
4. better on ≥ 67% of cutoffs and never worse than 0.005 on any cutoff;
5. no product family, region or the new-series segment worse by more than 0.005;
6. the test suite and the leakage audit pass.

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
  * Error is **not concentrated**: half of it comes from 866 of 3,047 series; the top 20
    series cause 3.2%. There is no small set of SKUs to fix.
  * Getting every series' level exactly right would only lower WAPE from 0.290 to 0.272 —
    **~94% of the error is month-to-month noise**, so remaining gains are small and
    robustness matters more than raw accuracy.
  * **Systematic under-forecast is specific:** the vehicle-build families (Chassis −8.3% in
    6/6 cutoffs, Thermal −5.8%, Brake −5.0%), Middle East & Africa (−6.5%) and **new
    series < 24 months (WAPE 0.391, bias −8.1%)**. Industrial families are unbiased.

### Phase C — challengers and the promoted model

Full ranked report: `artifacts/reports/experiment_report.md` (`python scripts/experiment_report.py`).
Every challenger ran on the same 6 cutoffs; the server re-run of the champion matches the
laptop run exactly, so all numbers are comparable.

| Experiment | WAPE | Δ | Total-month | Verdict |
|---|---:|---:|---:|---|
| **C9c — train on the price pull-forward months** | **0.2837** | **−0.0060** | 5.1% | **PROMOTED** (5/6 cutoffs better, 1 equal, none worse) |
| C9b — also keep COVID / strike months | 0.2850 | −0.0047 | 5.7% | passes, weaker than C9c |
| C9a — train on every observed month | 0.2864 | −0.0033 | 5.2% | rejected (worst cutoff −0.0048) |
| C8 — blend: C4 + CatBoost | 0.2880 | −0.0017 | 4.9% | rejected (gain < 0.002) |
| C4 — cross-series + 3-seed bag | 0.2883 | −0.0014 | 5.6% | rejected (gain < 0.002) |
| C7 — blend: champion + CatBoost | 0.2888 | −0.0009 | 4.8% | rejected |
| C1 — growth / family-macro features | 0.2890 | −0.0007 | 5.2% | rejected |
| Champion | 0.2897 | — | 5.4% | |
| C3a — intermittent-demand features | 0.2903 | +0.0006 | 5.4% | rejected |
| C9d — keep only COVID / strike months | 0.2920 | +0.0023 | 5.9% | rejected |
| C5 — CatBoost | 0.2925 | +0.0028 | **4.4%** | rejected (best company-level error) |
| C6 — without the EV-adoption index | 0.2937 | +0.0040 | 5.7% | rejected: the EV index is real signal |
| C3b / C3c — hurdle P(order) × size | 0.2947 / 0.2956 | +0.005 | 4.9% | rejected |
| C2 — separate models for 1–6 / 7–19 m | 0.2952 | +0.0055 | 6.2% | rejected |

**Why C9c wins.** The price-rise rule excluded four whole months (Nov 2022 – Feb 2023, every
series) from the training target and filled them with a trailing mean in the lag features.
The early-buying / payback effect it guarded against is about ±10%; losing the four most
recent real months cost more. C9c improves **every** family, region, lifecycle stage,
demand class and horizon bucket — most for **new series (WAPE 0.391 → 0.368, bias −8.1% →
−6.4%)** and **Middle East & Africa (0.379 → 0.362)**, the two known weak spots — and every
calendar month of the post-2022 backtests, including Jan–Feb of years without a price rise
(it is not fitting a one-off). Model, features and parameters are the champion's; only the
training months changed, so the leakage audit still applies.

### Phase D — robustness and uncertainty (`python scripts/robustness_report.py`)

* **Seed averaging and more training origins** change nothing material (0.2893 and 0.2896;
  seed bagging is better on 5/6 cutoffs but by only 0.0004) — the champion is not a lucky seed.
* **Cleaning sensitivity** (`scripts/cleaning_sensitivity.py`): each cleaning decision is
  reversed, the champion re-trained, and every variant scored on the **same yardstick** —
  the months no cleaning step touches — so no variant can win by redefining the truth:

  | Variant | WAPE vs our cleaning | Bias | 19-month forecast |
  |---|---:|---:|---:|
  | Our cleaning | 0.2779 | −3.7% | 2.836 M |
  | No stockout recovery (shipped = demand) | +0.0043 | −4.9% | +0.5% |
  | Drop stockout months instead of recovering them | +0.0036 | −3.8% | +0.5% |
  | No chip-shortage allocation uplift | +0.0002 | −3.6% | +0.0% |
  | Keep event / pull-forward months in training | **−0.0032** | −1.2% | −0.5% |

  Stockout recovery is confirmed; the training-exclusion result led to C9. Every decision
  moves the forecast by at most ±0.5% — the forecast is robust to the cleaning choices.
* **Macro stress** (`artifacts/reports/macro_stress.csv`, final model): combined downside
  −6.9%, upside +4.9%; PMI ±3 points ±2.2%; auto production −2 pp −2.3%.
* **No post-hoc corrections:** P50 instead of the mean, global or family bias factors all
  lose walk-forward (`post_corrections.csv`) — the bias is not stable enough to correct.
* **Calibrated bands by segment:** the split-conformal quantiles are now also stratified by
  young/established series × volatile regions (MEA, LatAm). Leave-one-cutoff-out, the worst
  segment's P10–P90 coverage rises from 75% to 79% with lower pinball loss and slightly
  narrower bands (`interval_calibration.csv`) — no ad-hoc band widening is needed any more.
* **Reliability:** error is flat across the horizon (0.26–0.30 for months 1–19;
  `horizon_reliability.csv`). Series tiers (`reliability_tiers.csv`): A reliable (WAPE <
  0.25) 861 series / 37% of volume, B usable 1,824 / 56%, C weak 316 / 6%, D unreliable 46 / 1%.

## Planning Intelligence engine — `python run_pipeline.py --stage intelligence`

Turns the forecast into decisions, from pipeline outputs only (history, champion forecast
and bands, the champion's own 6-cutoff backtest errors, the macro stress test, the
anomaly and structural registers), so it re-runs unchanged for a new champion.
Outputs in `outputs/intelligence/`: `series_signals.csv|json` (one record per SKU-region,
the frontend contract), `exceptions.csv`, `market_signals.csv`, `lifecycle_alerts.csv`,
`interval_reliability.csv`, `summary.json`.

| Component | Logic (thresholds are constants in `intelligence.py`) |
|---|---|
| **Status** | Forecast next 12 m vs actual last 12 m: HIGH_GROWTH ≥ +15%, GROWTH ≥ +5%, DECLINE ≤ −10%, SHARP_DECLINE ≤ −25%; lifecycle overrides (NEW_LAUNCH, END_OF_LIFE, RAMPING < 24 m history) |
| **Surge / decline detector** | Last 3 m ≥ +30% and last 6 m ≥ +15% YoY, ≥ 20 pts above its own family, **and** unusual for that series (z ≥ 2 vs its history of 3-month swings, z ≥ 1.5 for 6 months). Mirror rule for declines |
| **Risk score (0–100)** | Percentile-weighted: backtest error of that series 35%, band width 20%, volatility 15%, short history 10%, recent data issues 10%, macro sensitivity of its family 10%; +10 for launches, EOL, customer shutdowns. Top 15% HIGH, next 35% MEDIUM |
| **Market change** | Family / region / customer / channel YoY of the last 3 months **relative to the whole market** (OUTPACING / LAGGING / IN_LINE); the market itself gets one headline signal |
| **Reason codes** | 21 codes, e.g. SUSTAINED_ORDER_GROWTH, FAMILY_LAGGING_MARKET, LOW_HISTORICAL_ACCURACY, HIGH_FORECAST_VARIANCE, SUPPLY_CONSTRAINED_HISTORY, FORECAST_CONFLICTS_WITH_RECENT_TREND, CUSTOMER_SHUTDOWN_IN_WINDOW, APPROACHING_EOL |
| **Recommendation** | Rule per status / risk with procurement quantities (forecast and P90 for the next 6 months) |
| **Exceptions** | High risk, SKU-specific surges/declines, sharp declines, lifecycle, shutdowns; ranked by units at stake × risk; top 10% + all lifecycle/shutdown items = ACT_NOW |

**Interval reliability by segment** (final model backtest, leave-one-cutoff-out): with the
Phase D stratified bands the P10–P90 band holds 79–87% in every lifecycle stage, region,
demand class and horizon (`interval_reliability.csv`), so planning quantities use the
bands as they are.

**Current read-out (final model, forecast from 2026-10):**
* **Market upturn:** total demand +13.6% YoY over the last 3 months (vs −0.6% over 12 months);
  Electrical Assemblies is outpacing the market, Chassis & Structural lagging it.
* 50 SKU-specific surges and 23 declines; 33 series where the forecast contradicts a
  sustained recent trend (flagged for planner judgement).
* 596 exceptions, **142 ACT_NOW** (all 28 lifecycle items, 61 Orion-shutdown series, the
  highest-risk / largest-volume items); 464 series HIGH risk.

## Frozen backend — `python run_pipeline.py --stage final`

1. **Model selection** from the registry: the best challenger passing all six promotion
   criteria, else the champion (`outputs/final/manifest.json` records the model, the reason,
   the spec, the features, the backtest headline and SHA-256 fingerprints of every file).
2. **Final forecast** with the selected model, the same lifecycle / launch / run-down /
   shutdown rules as stage 4 and the stratified bands fitted on that model's own backtest.
3. **Validation** (`validation_report.json`, all PASS): 58,219 rows in test order, no
   duplicates / missing / negative values, integers, zero outside launch–EOL, P10 ≤ P50 ≤ P90,
   hierarchy totals equal the SKU sums, next-12-month growth plausible, every active
   series forecast.
4. **Data contract** — `contracts/data_contract.yaml` lists every dataset the dashboard may
   read (path, grain, primary key, columns, types, which view uses it);
   `tests/test_contract.py` enforces it on every run.
5. **Read-only API** over the contract (no computation, so the frontend always shows the
   frozen, validated numbers):

```powershell
uvicorn api.app:app --reload
```

`/health`, `/kpis`, `/datasets`, `/datasets/{name}?col=value`, `/series/{sku}/{region}`
(history + forecast + signals + anomalies), `/hierarchy?level=family`; docs at
`http://127.0.0.1:8000/docs`.

**Submission file:** `outputs/final/submission.csv`. Big files (forecast detail, history,
model) are regenerated by the pipeline and published as a GitHub Release.

## Milestone 3 — Planning Intelligence Engine (`src/celeris/intel/`)

Turns the frozen forecast into decisions. Research and design: `docs/intelligence_design.md`
(what the jury grades, what strong control towers do, and the honest limits of the data).
Runs inside `python run_pipeline.py --stage intelligence` in about 10 seconds, reads only
pipeline outputs and never re-forecasts.

| Module | What it calculates |
|---|---|
| `pricing.py` | **Revenue.** 2026 list price per SKU, rolled forward with the 1-January rises announced in the events calendar (2027 +4.5%, 2028 +4.0%). Back-test: announced vs realised median rise matched within 0.1 pt in every year 2020–2026. Next 12 months: **$1.61 B (+11.0%)**; 19 months $2.54 B |
| `segmentation.py` | **ABC–XYZ policy.** ABC by next-year revenue (80/15/5%), XYZ by the model's own backtest error (not raw CV, which mislabels seasonal series). Each cell gets a service level (A-X/Y 95% … C-Y/Z 80%) |
| `supply.py` | **Procurement plan from P90 forecasts** with calibrated **lead-time (3-month) quantiles**: held out cutoff by cutoff, the 3-month P90 covers **89.8%** of actual demand and P95 94.8% (the forecast alone: 50%). Make-to-order below 1 unit/month. **Production check:** forecast 3-month load vs the highest 3-month volume shipped in 36 months (labelled proxy — there is no capacity table). **Supply risk** from the stockout file (reasons, lost units, fill rate) |
| `demand_signals.py` | Momentum, outlook, mix shift, seasonality and a **market-relative** signal (OUTPACING / LAGGING / MIXED / IN_LINE) for family, region, family × region, customer, channel and powertrain (EV shift) |
| `forecast_risk.py` | Explainable risk score (named, weighted components) + new-product ramp risk, forecast anomalies (forecast breaks with both recent and last-year actuals), revenue at risk / upside, confidence |
| `exceptions.py` | **Rule playbook** (15 rules) evaluated at every level; each hit stores its evidence, impact in USD, urgency and confidence; priority = 40 impact + 30 severity + 20 urgency + 10 confidence |
| `recommendations.py` | Action card per exception — owner, finding, action, trade-off, decision window — **every number filled from the evidence** (tested), no free text |
| `scenarios.py` | **Scenario Lab.** The frozen model re-forecast 447 macro scenarios on the server; an emulator per family × region × month (no intercept, so zero shocks = the frozen forecast) answers custom sliders instantly with **0.6 pt mean error** on 46 held-out scenarios; named presets use the exact simulations. Region overlays are labelled planner assumptions. Capacity re-check and rule-based responses per scenario |
| `narrative.py` | Executive briefing assembled from computed facts, each bullet listing its sources |
| `report.py` | Writes `outputs/intelligence/` and `intelligence_report.json` (the dashboard contract) |

**Current read-out**
* Next 12 months: 1.81 M units (+6.1%), **$1.61 B revenue (+11.0%)**; market upturn (+13.6% YoY in the last 3 months).
* **EV shift:** EV SKUs +27% next 12 months (share 9.8% → 11.8%), ICE −4.4%.
* **Capacity:** 8 family-regions are forecast above their highest 3-month volume of the last 3 years
  (largest: Chassis in Middle East & Africa, 106%); 17 more are tight.
* **Supply risk:** 6 growing family-regions with a fragile supply history, e.g. Thermal Management in North
  America (17 shortage months in 36, mostly tooling breakdowns, 39% fill rate in those months).
* **Next procurement cycle:** $561 M at each segment's service level, of which $166 M is safety buffer.
* **351 exceptions → 351 action cards: 62 CRITICAL**, 201 HIGH, 88 MEDIUM.
* **Scenarios (exact):** downside −6.9% (−$179 M), upside +4.9% (+$142 M), PMI −3 −2.3%, auto slowdown −4.1%,
  EV acceleration +1.9%.

**API** (read-only, nothing re-forecast): `/intelligence/report`, `/intelligence/briefing`,
`/intelligence/recommendations?priority=CRITICAL&owner=procurement`, `/scenario/config`,
`/scenario/presets`, and `POST /scenario` with
`{"shocks": {"pmi": -3, "auto_production": -2}, "region_overlay": {"Europe": -5}}`.

Rebuild the Scenario Lab emulator (about 4 minutes on the 56-core server):

```powershell
python scripts/scenario_simulations.py --train 400 --holdout 40 --workers 14
```

## Milestone 4 — Dashboard (`dashboard/`, Phase 1: shell)

React + TypeScript + Vite control tower on top of the read-only API. Architecture, design
research, design system and phase plan: `docs/dashboard_architecture.md`; live API shapes:
`docs/api_contracts.md` (`python scripts/document_api.py`).

Run (two terminals, from the project folder):

```powershell
uvicorn api.app:app --port 8000
```

```powershell
npm --prefix dashboard install
```

```powershell
npm --prefix dashboard run dev
```

Open http://localhost:5173. Tests and build:

```powershell
npm --prefix dashboard test
```

```powershell
npm --prefix dashboard run build
```

Phase 1 delivers the app shell (sidebar with the six sections + Data Health and Anomaly
Monitor, header with live model / validation status, global filter bar shared through the URL),
the design system (validated dark palette, typography, states) and route placeholders that
report live data readiness - no static or invented values.

