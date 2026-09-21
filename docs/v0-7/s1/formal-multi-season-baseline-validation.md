# V0.7-S1 Frozen Model and Business Boundary Correction

## Status

`TASK_ID=V0_7_S1_FROZEN_MODEL_AND_BUSINESS_BOUNDARY_CORRECTION_R2`

This document supersedes the original S1 report. The original all-39
prediction scope and its metrics are not an accepted baseline: the correction
restores the frozen immediate-prior Model A contract and the existing
season-boundary authority.

The correction is implemented on PR #645. It does not add weather, create
Model B, tune the model, or change the Model A mathematics.

## Frozen model contract

| Item | Frozen value |
| --- | --- |
| Model A | `AREA_PLUS_HISTORICAL_HARVEST` |
| Total model | `BASE_AWARE_BASELINE_R1` |
| Temporal model | `AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE` |
| History policy | `IMMEDIATE_PRIOR_SEASON_ONLY_FAIL_CLOSED_NO_GLOBAL_FALLBACK` |
| Fold A prior | `2023-2024` |
| Fold B prior | `2024-2025` |
| Weather | `false` |
| Model B | not created |
| Model tuning/search | disabled |
| Production accuracy approval | `false` |

Only Bases with a mapped, legal immediate-prior history enter prediction
scope. A Base without that history is recorded as
`NOT_ELIGIBLE_PRIOR_SEASON_HISTORY_MISSING`; it is not predicted with a
global median, an older season, or any latest-available fallback.

The rolling adapter uses the same immediate-prior yield-times-area rule as the
frozen product contract. Product parity is covered by the unit regression
against `AreaForecastProduct` and by the fold parity check.

## Business-season authority

The boundary is selected and hashed before validation labels are loaded.

| Season | Business start | Business end | Authority |
| --- | --- | --- | --- |
| 2023-2024 | 2023-07-01 | 2024-04-15 | existing model calendar authority |
| 2024-2025 | 2024-07-01 | 2025-04-15 | existing model calendar authority |
| 2025-2026 | 2025-07-22 | 2026-04-15 | `USER_CONFIRMED_2526_BUSINESS_WINDOW_R7B` |

The 2025-2026 boundary authority is
`docs/next-version/evidence/three-season-business-boundary-r7b.json`, SHA256
`e8ccfc929f301690511e09601bb544ffe94c3b805a87ca498297ccf098af8cc4`.
July 1-21 is outside that business window, and post-April-15 data is outside
scope. The 40 in-window global unknown dates remain unknown; they are never
zero-filled. R7B's business-total and shape/peak eligibility are intersected
with prediction eligibility rather than replaced by a new all-calendar rule.

## Area semantics

All areas in this validation are:

```ini
AREA_TYPE=REFERENCE_AREA
AREA_SEMANTICS=REFERENCE_AREA_ONLY
HISTORICAL_ACTUAL_PRODUCTIVE_AREA_AUTHORITY=false
```

`REFERENCE_AREA` is a frozen Model A input. It is not an assertion that the
historical season had that actual productive area.

## Label-blind protocol

Each fold executes in this order:

1. qualify prediction scope from registry, identity, area, model, and the
   immediate-prior history only;
2. seal prediction rows, training identity, business boundary, and hashes;
3. load validation actuals and score only after the seal.

The validation quantity labels cannot change prediction scope, model identity,
prediction rows, or prediction hash. Confirmed zero remains comparable;
unknown/missing remains non-comparable and is not converted to zero.

```ini
VALIDATION_LABEL_LEAKAGE=false
VALIDATION_BLINDNESS=PASS
PREDICTIONS_SEALED_BEFORE_VALIDATION_LABEL_SCORING=true
POST_PREDICTION_SCORING_ONLY=true
```

## Corrected fold scope and metrics

WAPE is always pooled absolute error divided by pooled actual, not an average
of run-level WAPEs. Negative bias means underprediction.

| Fold | Declared train | Model prior used | Validate | Registry | Eligible | Ineligible | Comparable daily rows | Complete total rows | Non-complete rows |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 2023-2024 | 2023-2024 | 2024-2025 | 39 | 13 | 26 | 1,909 | 0 | 13 |
| B | 2023-2024 + 2024-2025 | 2024-2025 | 2025-2026 | 39 | 30 | 9 | 5,077 | 1 | 29 |

All ineligible rows use the single reason
`NOT_ELIGIBLE_PRIOR_SEASON_HISTORY_MISSING`.

| Metric | Fold A | Fold B | Combined OOT |
| --- | ---: | ---: | ---: |
| Season-total WAPE | `NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY` | 0.5389045665598414871408878679 (1 Base) | 0.5389045665598414871408878679 (pooled computable rows) |
| Daily WAPE | 0.6384665136922065255391352980 | 0.7507992930315132720520321240 | 0.7245703036857014811985535015 |
| Daily Bias kg/row | -2479.389925403352540597171294 | -4429.695973961985424463265708 | -3896.753768594331520183223590 |
| Single-day peak quantity WAPE | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` | 0.8361096255097708003558018616 (2 Bases) | 0.8361096255097708003558018616 |
| Single-day peak date MAE days | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` | 24 | 24 |
| Rolling-7 quantity WAPE | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` | 0.8155329607742376504592426572 (2 Bases) | 0.8155329607742376504592426572 |
| Rolling-7 start-date MAE days | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` | 23 | 23 |

The combined daily result contains 6,986 comparable rows, pooled actual
`51,641,502.295 kg`, and pooled absolute error `37,417,899.000674 kg`.
Combined totals/peaks are deliberately limited to the computable authority
intersection; they are not extrapolated to all eligible Bases.

Daily absolute-error distributions (median / P75 / P90 / max kg) are:

| View | Median | P75 | P90 | Max |
| --- | ---: | ---: | ---: | ---: |
| Fold A | 2,959.7757190 | 5,923.69708800 | 9,497.4734714 | 18,677.533468 |
| Fold B | 3,898.8123440 | 8,437.39232000 | 14,021.4906918 | 51,380.735465 |
| Combined | 3,594.7019630 | 7,686.77707775 | 12,615.8046435 | 51,380.735465 |

Per-Base daily, total, peak, rolling-7, coverage, and unknown-status rows are
retained in the private generated evidence set. The repository evidence file
records the scope counts, metric hashes, and private artifact hashes without
committing raw business data.

## Authority identities

| Authority | SHA256 |
| --- | --- |
| 2023-2024 primary source | `8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20` |
| 2024-2025 primary source | `f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6` |
| 2025-2026 primary source | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| Base Registry config | `0d382e644b271df4d9b8e7f31f8e4148816135faf70aa1e21a97ee2eb6374b85` |
| Historical identity mapping | `8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044` |
| Base member mapping | `d40dbc3a1328d79e10670999ee613fcef8fa3ee32659db16dfe67db3e6b91b5b` |
| Combined identity authority | `c46e198cda2e6c4296db184af5c2e1f3b200a944309aa43039fa3be42a0bbd0e` |
| Temporal model config | `cf0e1c4bffc4acc404dd0479c36b02f78df893ef25dda819359eaa317157dabf` |
| R7B coverage qualification | `2bd4bfdfa53c5ad17bda7817e5a2ee09d25c0ab7650903ee3924d2d7bba2da24` |

## Determinism and correction acceptance

```ini
IMMEDIATE_PRIOR_POLICY_PASS=PASS
NO_GLOBAL_FALLBACK_PASS=PASS
FROZEN_MODEL_A_PARITY_PASS=PASS
DATASET_MANIFEST_DETERMINISM_PASS=PASS
SPLIT_MANIFEST_DETERMINISM_PASS=PASS
MODEL_ARTIFACT_DETERMINISM_PASS=PASS
PREDICTION_DETERMINISM_PASS=PASS
METRIC_DETERMINISM_PASS=PASS
FRESH_PROCESS_REPLAY_PASS=PASS
```

The fresh-process replay evidence hash is
`c9ac7c7a891f4185a7acd9566c32dd1a0c5ca14520675af168f0abd29a053986`.
The fold prediction and score identities are listed in the machine-readable
evidence file. Changing validation actuals after sealing changes score output
only, not prediction output or prediction hash.

## Formal conclusion

```ini
THREE_SEASON_DATA_AUTHORITY_PASS=PASS
ROLLING_OOT_FOLD_A_PASS=PASS
ROLLING_OOT_FOLD_B_PASS=PASS
BUSINESS_BOUNDARY_AUTHORITY_PASS=PASS
MODEL_A_FORMAL_HISTORICAL_BASELINE_ESTABLISHED=true
CURRENT_AREA_MODEL_VALIDATION_STATUS=VALIDATED_WITH_MEASURED_ERROR;TOTAL_PEAK_COVERAGE_LIMITED
BUSINESS_ACCURACY_THRESHOLD_STATUS=NOT_FROZEN
PRODUCTION_ACCURACY_APPROVED=false
WEATHER_USED=false
MODEL_B_CREATED=false
V0_7_S2_IMPLEMENTATION_AUTHORIZED=false
```

This correction establishes an honest, label-blind historical baseline under
the frozen product policy. It does not approve production accuracy, does not
make the partial/unknown actual authority complete, and does not authorize
S2 or weather work.
