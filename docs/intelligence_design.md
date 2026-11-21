# Milestone 3 — Planning Intelligence Engine: research and design

## 1. What the jury grades (problem statement §4–5)

| Requirement | Where the intelligence layer feeds it |
|---|---|
| **Executive overview** — units **and revenue** from history into the forecast on one timeline, mix by family / region / channel, headline 19-month forecast | `pricing.py` (revenue forecast from the announced price list), `report.py` KPIs + briefing |
| **Data health** | existing `outputs/quality/` (DQ log, before/after) |
| **Demand explorer** — family → SKU → region → customer; seasonality, zero months, lifecycle | `demand_signals.py` (seasonal profile, intermittency, lifecycle per series) |
| **Anomaly monitor** — flagged points with type, reason, action | existing anomaly register + `forecast_risk.py` forecast anomalies |
| **Forecast & accuracy** — backtest WAPE / bias by family, region, horizon | existing registry + final metrics |
| Optional: **what-if (PMI −3)** | `scenarios.py` (Scenario Lab) |
| Optional: **procurement plan from P90 forecasts** | `supply.py` procurement plan (calibrated lead-time quantiles) |
| Optional: **lifecycle (EOL and launches)** | existing lifecycle alerts + new-product risk |
| Optional: **stockouts and lost sales** | `supply.py` supply-risk history (lost units, fill rate, reasons) |
| Optional: **exception list for planners** | `exceptions.py` + `recommendations.py` |
| Optional: macro lead/lag heatmap, data download | existing `outputs/drivers/`, contract datasets |

Expert tier = the 5 required views **+ 4 or more optional views, polished**. Two consequences for the
dashboard plan (Milestone 4): "Data health" and "Anomaly monitor" must exist as named views, and
the app needs **one shared filter bar** (family, SKU, region, channel, customer) across the
training-data and prediction parts.

## 2. What strong control towers do (research)

* **Exception-based, prioritised by impact.** Flag exceptions automatically, assess their impact,
  and rank them so planners work the most valuable ones first; attach a standard response
  ("playbook") to each exception type
  ([SAP](https://www.sap.com/india/resources/supply-chain-control-tower),
  [o9](https://o9solutions.com/articles/next-gen-control-tower-and-soe),
  [Blue Yonder](https://blueyonder.com/platform/control-tower)).
* **Prescriptive, with trade-offs.** The best towers diagnose the root cause and prescribe
  corrective actions with their cost / trade-off, not just an alert (o9).
* **Quantile forecasts drive buffers.** The reorder point *is* a quantile of lead-time demand:
  planning to P90 of lead-time demand gives ≈ 90% cycle service; safety stock = P90 − P50 of
  lead-time demand. The quantile must be of the **lead-time sum**, not the sum of monthly P90s
  (which overstates the buffer) ([Lokad](https://lokad.com/reorder-point-definition),
  [Trapero et al.](https://core.ac.uk/download/158138416.pdf)).
* **ABC–XYZ segmentation sets the planning policy.** ABC = value, XYZ = forecastability; each
  cell gets its own service level / planning approach. Raw CV mislabels seasonal series, so we
  measure forecastability by the **model's own backtest error** instead
  ([SAP IBP](https://learning.sap.com/courses/mastering-sap-ibp-for-demand/using-abc-and-xyz-segmentation),
  [Bain](https://bain.com/insights/classify-demand-series-to-improve-the-forecast)).

## 3. Honest boundaries of the data

* **No capacity, inventory or supplier tables.** Capacity is therefore a labelled proxy —
  *demonstrated throughput*: the highest 3-month shipped volume of a family × region in the
  last 36 months. "Forecast above demonstrated throughput" is a planning-attention flag, not a
  claim about plant capacity. Rule 7 says the forecast window has no supply limits, so the
  forecast itself stays unconstrained.
* **Supply risk comes from the stockout file:** reasons (capacity constraint, tooling
  breakdown, supplier quality hold, logistics delay, semiconductor allocation), lost units and
  fill rates by family × region. The file is incomplete, so these are lower bounds.
* **Value = revenue** (units × projected list price); cost data does not exist.
* **Lead time = 3 months** — the problem statement: orders are booked 2–3 months ahead.

## 4. Modules (`src/celeris/intel/`)

| Module | Calculates | Key outputs |
|---|---|---|
| `pricing.py` | 2026 list price per SKU (modal, surcharge-free), projected with the announced 1-January rises (2027 +4.5%, 2028 +4.0%, parsed from the events calendar); back-tested against past announced vs realised rises | price book, revenue forecast with P10/P90, history revenue (shipped and unconstrained) |
| `segmentation.py` | ABC by next-12-month revenue (80 / 15 / 5%), XYZ by backtest WAPE (< 0.25 / < 0.40 / ≥ 0.40), N for launches | segment, service-level target and planning quantile per SKU-region |
| `supply.py` | calibrated lead-time-demand quantiles (backtest ratios of 3-month sums, leave-one-cutoff-out checked); procurement plan per SKU-region-month at the policy quantile; demonstrated throughput vs forecast load per family × region; supply risk from stockout history | procurement plan, capacity check, supply-risk table |
| `demand_signals.py` | growth, acceleration, decline, seasonality (peak months, amplitude), mix shift at family / region / family×region / customer / channel / powertrain level | multi-level signal table |
| `forecast_risk.py` | explainable risk score (existing components) + new-product ramp risk, forecast discontinuity vs recent actuals, macro sensitivity, revenue at risk / upside | risk table with component scores |
| `exceptions.py` | rule playbook evaluated on the signals at every level; each hit carries rule id, evidence values, impact (USD), confidence, urgency | ranked exception list |
| `recommendations.py` | turns each exception into an action with owner, time window, quantities and trade-off, filled from the evidence — no free text | recommendation cards |
| `scenarios.py` | the real model re-run on sampled macro scenarios (server), a validated emulator (response surface per family × region × month) for instant what-if, region overlays, capacity re-check and responses | Scenario Lab API |
| `narrative.py` | executive briefing sentences assembled from computed facts (templates, no LLM) | briefing |
| `report.py` | runs everything, writes CSVs + `intelligence_report.json` (the dashboard contract) | `outputs/intelligence/` |

Every number in a recommendation is a field of the evidence record that produced it, so each
card can show "why" and be traced back to the forecast, the backtest or the history.
