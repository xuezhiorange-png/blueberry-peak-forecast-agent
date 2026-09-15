# V0.5-S4 matched lagged-weather incremental-value R1

This document records the first authorized weather/no-weather ablation for the
blueberry known-support daily baseline.  It is an incremental-value study, not
an operational weather backtest and not a new model-selection exercise.

## Frozen scope and protocol

The comparison uses the exact 38-base `YUNNAN_CORE` weather scope and the
accepted ERA5-Land daily fact artifact
`5ad49f11895c76e6aadd01d240ada3ba93d599d25138a2609887e527e58dad3b`.
`乡丰蓝莓基地` remains outside this weather scope.  The source role is
`REANALYSIS_REFERENCE`; historical as-issued forecast PIT is still not
established.

For every origin `D`, both candidates predict `D+1` through `D+15`.  The
control and weather candidates use the same training rows, validation origins,
folds, estimator parameters, random seed, and scoring code.  The weather
candidate adds only the frozen 7-day and 14-day trailing summaries ending at
`D`.  No target-day or future weather is used.  Origins without complete
trailing 14-day weather are removed once from the shared population, so the
control is not given an easier sample.

The fixed estimator is `HistGradientBoostingRegressor` with squared loss,
learning rate `0.05`, `max_iter=300`, `max_leaf_nodes=31`, `max_depth=6`,
`min_samples_leaf=10`, `l2_regularization=0.1`, no early stopping, and random
seed `20260915`.  The fixed season-week median remains a benchmark only; it is
not the attribution control.

## Origin and fold support

| item | Fold A (secondary) | Fold B (primary) |
| --- | ---: | ---: |
| train seasons | 2023-2024 | 2023-2024 + 2024-2025 |
| validation season | 2024-2025 | 2025-2026 |
| train origins | 2,358 | 8,622 |
| validation origins | 6,264 | 9,918 |
| train samples | 30,591 | 123,231 |
| train bases | 9 | 24 |
| validation bases | 24 | 38 |
| natural out-of-base validation bases | 15 | 14 |

Before the shared history filter there were 20,031 W7-capable and 19,463
W15-capable origins.  After requiring complete trailing 14-day weather, there
were 19,108 and 18,540 respectively.  The experiment uses 18,540 origins and
filters 923 origins from each window population.  The filtered origin identity
hash is
`e670463d44157609789154c4899d4a1f3efb051ca9cb0ecf49b58339ee6d0a9f`.

## Fold B primary results

Daily values below are base-equal macro values; row-pooled diagnostics are
kept separately in the private metrics artifact.

| horizon | control WAPE | weather WAPE | weather-control | control MAE kg | weather MAE kg |
| --- | ---: | ---: | ---: | ---: | ---: |
| H1 | 0.769792679792 | 0.785914879458 | +0.016122199666 | 3,404.197815919212 | 3,479.993267978826 |
| H3 | 0.764439813450 | 0.775306088250 | +0.010866274800 | 3,442.281360785503 | 3,505.544395835903 |
| H7 | 0.753498632457 | 0.758614756922 | +0.005116124465 | 3,505.654304649615 | 3,540.087817586696 |
| H15 | 0.735365645524 | 0.723597478398 | -0.011768167126 | 3,710.198994466733 | 3,674.880136557140 |
| overall | 0.750324886980 | 0.750618605576 | +0.000293718596 | 3,544.887183250124 | 3,565.749119337196 |

| window | metric | control | weather | delta | relative delta |
| --- | --- | ---: | ---: | ---: | ---: |
| W7 | total WAPE | 0.712491669120 | 0.708109505437 | -0.004382163683 | -0.006150477083 |
| W7 | peak-date MAE days | 2.424118548799 | 2.512263668881 | +0.088145120082 | +0.036361720067 |
| W7 | peak-kg WAPE | 0.715354369858 | 0.694977750321 | -0.020376619537 | -0.028484650959 |
| W15 | total WAPE | 0.682719257474 | 0.658896666944 | -0.023822590530 | -0.034893684730 |
| W15 | peak-date MAE days | 5.170413898825 | 5.087506387328 | -0.082907511497 | -0.016034985423 |
| W15 | peak-kg WAPE | 0.690307168716 | 0.663095552759 | -0.027211615957 | -0.039419576082 |

Per-base weather-minus-control counts on Fold B are:

| metric | improved | worsened | tied | median base delta |
| --- | ---: | ---: | ---: | ---: |
| daily WAPE | 23 | 15 | 0 | -0.007318833204 |
| W7 total WAPE | 22 | 16 | 0 | -0.010285078478 |
| W7 peak-date MAE | 13 | 25 | 0 | +0.053398058253 |
| W7 peak-kg WAPE | 20 | 18 | 0 | -0.005785322941 |
| W15 total WAPE | 24 | 14 | 0 | -0.012706763283 |
| W15 peak-date MAE | 22 | 16 | 0 | -0.106796116505 |
| W15 peak-kg WAPE | 21 | 17 | 0 | -0.003629522134 |

## Interpretation and limits

The result is `MIXED_WEATHER_EFFECT_NO_CLEAR_GAIN`.  On the primary Fold B,
weather slightly degrades overall daily macro WAPE and W7 peak timing, while
improving W7 total/peak-quantity error and all three W15 metrics.  This is not
a uniform weather gain, so the run does not prove production weather value and
does not authorize changing the product model.

Fold A is retained as a secondary diagnostic.  Its validation population has
only 24 bases while its training population has 9, so its very large macro
WAPE values are evidence of the early cross-season support mismatch, not a
reason to tune the candidate after seeing Fold B.

The prediction phase was closed before validation labels were joined.  Two
independent executions from the same hash-pinned inputs produced equal
candidate manifests, frozen prediction files, scored predictions, and
metrics.  `GDD`, `VPD`, `ET0`, derived RH, climate-zone features, and model
training beyond this pre-authorized ablation were not used.  The private
artifact root is
`blueberry-area-yield-artifacts/s4-lagged-weather-incremental-value-r1-final/`.
