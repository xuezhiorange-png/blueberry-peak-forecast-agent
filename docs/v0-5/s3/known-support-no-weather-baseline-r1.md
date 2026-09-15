# V0.5-S3 known-support no-weather baseline R1

`V0_5_S3_KNOWN_SUPPORT_NO_WEATHER_BASELINE_R1` is the first authorized S3
known-support model run.  It uses the corrected R3 Base Registry authority and
does not claim complete-season coverage.  The model is a fixed
`HistGradientBoostingRegressor`; the reference is a fixed normalized
season-week median.  No weather or climate-zone value is used as a feature.

## Frozen scope and split

The active Registry and known-support population both contain 39 canonical
bases.  The 38-base `YUNNAN_CORE` weather scope is retained as a separate
common-comparable subset; `乡丰蓝莓基地` remains in the no-weather extended
scope and is not given substitute weather data.  Full-season total eligibility
remains zero, so every score below is explicitly known-support evidence.

The primary forward fold is Fold B:

`2023-2024 + 2024-2025 -> 2025-2026`

It has 25 seen bases and 14 natural out-of-base bases.  Fold A
(`2023-2024 -> 2024-2025`) is a secondary stability diagnostic.  Candidate
definition, estimator parameters, features, reference aggregation, and split
roles were frozen before fitting and validation label values were read only
after the prediction file was frozen.

## Fixed candidates

The model target is `observed_harvest_kg` on known daily labels.  The only
features are:

`productive_area_mu`, `business_season_day_index`,
`business_season_progress`, `business_season_progress_sin`, and
`business_season_progress_cos`.

The reported reference is
`AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1`: per-base 7-day-bin mean kg/mu,
then cross-base median, with the frozen nearest-bin/equal-distance-earlier
policy.  W7 and W15 are aggregated directly from frozen daily predictions;
they are not separately trained models.  Macro values are base-equal.  The
row-pooled values are diagnostics only.

## Fold B primary results

| candidate | daily WAPE | daily MAE kg | daily bias kg | W7 total WAPE | W15 total WAPE |
| --- | ---: | ---: | ---: | ---: | ---: |
| `NO_WEATHER_HGBR_DAILY_V1` (all 39) | 0.838297828753 | 3200.752718903354 | -1843.913950625608 | 0.694795552375 | 0.682695349371 |
| `AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1` (all 39) | 0.825783879425 | 3207.929790381826 | -2173.528377570322 | 0.679262173997 | 0.681542288125 |
| `NO_WEATHER_HGBR_DAILY_V1` (seen 25) | 0.895537851998 | 2727.056706165972 | -1073.400908842848 | 0.691522898647 | 0.680502445489 |
| `NO_WEATHER_HGBR_DAILY_V1` (natural OOB 14) | 0.736083501531 | 2475.016873607060 | -656.095786906975 | 0.700639576890 | 0.686611249161 |

The corresponding all-39 peak diagnostics are: HGBR W7 peak-date MAE
`2.391924275102` days and peak-kg WAPE `0.698179749731`; HGBR W15
peak-date MAE `5.228030868808` days and peak-kg WAPE `0.693669727091`.
The reference values are respectively W7 `2.480589503954` days /
`0.721037636886`, and W15 `5.229773462783` days / `0.736350153660`.

The 38-base common-weather diagnostics for HGBR are daily WAPE
`0.842484715152`, W7 total WAPE `0.700264874618`, and W15 total WAPE
`0.688424558592`.  They are reported for future apples-to-apples weather
ablation only and do not change the 39-base no-weather denominator.

## Reproducibility and limitations

The private experiment root is
`blueberry-area-yield-artifacts/s3-known-support-no-weather-baseline-r1/`.
Two independent executions from the same hash-pinned private inputs produced
identical artifact manifests, candidate manifest, prediction freeze, scored
predictions, and metrics.  Replay comparison is recorded in the companion
evidence JSON.

This run establishes engineering execution and known-support baseline
evidence.  It does not establish a full-season total/yield model, weather
incremental value, climate-zone value, or production readiness.  Unknown
labels remain unknown and are never converted to zero.  The HGBR and reference
are both reported; this task does not authorize a new model-selection or S4
weather-ablation decision.
