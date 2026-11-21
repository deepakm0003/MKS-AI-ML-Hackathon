## Decision

**Promoted: `c9c_keep_pull_forward`** - the champion's model, features and parameters, unchanged,
trained on the price-announcement months (Nov 2022 - Feb 2023) instead of excluding them.
The demand target is identical, so the comparison is like for like.

| | Champion | C9c | Change |
|---|---:|---:|---:|
| WAPE (6 cutoffs) | 0.2897 | **0.2837** | −0.0060 (bar: 0.002) |
| Cutoffs better / equal / worse | | 5 / 1 / 0 | 2022-10 is identical: the months come after that cutoff |
| Bias | −3.0% | −2.8% | improved |
| Family-month WAPE | 7.65% | 7.33% | improved |
| Company-month WAPE | 5.36% | 5.15% | improved |
| New series (< 24 m) | 0.391 | 0.368 | largest gain |
| Middle East & Africa | 0.379 | 0.362 | second largest gain |

All six promotion criteria hold: every horizon bucket, family, region and lifecycle segment
improves; no cutoff gets worse; features are unchanged, so the leakage audit still applies;
the test suite passes. C9c is also better in every calendar month of the post-2022 backtests,
including January and February of years without a price rise, so it is not fitting a one-off.

**Why:** the price-rise rule removed four whole months (every series) from the training
target and replaced them with a trailing mean in the lag features. The early-buying and
payback effect it guarded against is about ±10%; losing the four most recent real months
cost more. The cleaning-sensitivity test found this first (keeping all event months: −0.0032
on a common yardstick), and the 6-cutoff C9 runs isolated it to the pull-forward months -
keeping the COVID-lockdown and strike months instead (C9d) makes the model worse.

## What was rejected, and what it taught us

* **Near misses (gain 0.001–0.002):** cross-series features (C4 0.2883, better on 5/6 cutoffs),
  seed bagging (0.2893, 5/6), and the CatBoost blends (C8 0.2880, C7 0.2888). Consistent but
  below the bar on their own.
* **CatBoost (C5)** loses at series level (0.2925) but has the **lowest company-month error of
  all models (4.4%)** - the right choice if planners judge mainly on totals.
* **Clear losers:** horizon-split models (C2), the hurdle models (C3b/c), dropping the EV index
  (C6: the EV index carries real signal, not just a trend), dropping macro features entirely.
* **Cleaning decisions confirmed:** stockout recovery is right (without it: +0.0043 WAPE,
  bias −4.9%); recovering stockouts beats dropping them (+0.0036); the chip-shortage uplift is
  neutral. Each cleaning variant moves the 19-month forecast by at most ±0.5%.
* **No post-hoc fixes:** median (P50) instead of mean, global or family bias correction all
  lose walk-forward - the bias is not stable enough over time to correct after the fact.

## Recommendation for the next milestone

1. **Rebase the champion on C9c** (`config/experiments.yaml`) and re-run the near misses on
   top of it - cross-series + seed bagging and the CatBoost blend. Their gains were measured
   against the old champion and may now stack past the promotion bar.
2. **Add an explicit price-announcement feature** so a future price rise is modelled from the
   events calendar rather than inferred from month-of-year (C9c's January bias is −3.8% vs
   −3.0%).
3. **Remaining bias** is concentrated in Chassis (−7.2%), Thermal (−6.2%), new series (−6.4%)
   and Middle East & Africa (−4.9%); the family-specific macro sensitivity of C1 is the most
   promising lever on top of C9c.
4. **Build the dashboard** on the frozen data contract (`contracts/data_contract.yaml`, API in
   `api/app.py`) - the backend no longer changes underneath it.
